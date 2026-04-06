"""
Unified cortical region exporter -- STL and PLY output from a single entry point.

Extracts atlas-labelled cortical regions (and optionally the whole GM surface)
from a SimNIBS surface mesh.  Dispatches on :attr:`RegionConfig.format`
to produce either binary STL or colored/scalar PLY output.

Examples (programmatic):
    from tit.blender.config import RegionConfig
    from tit.blender.region_exporter import run_regions

    cfg = RegionConfig(subject_id="ernie", simulation_name="L_Insula")
    run_regions(cfg)
"""

from __future__ import annotations

import logging
import os
import tempfile

import numpy as np
from simnibs import read_msh
from simnibs.utils.transformations import atlas2subject

from tit.blender.config import RegionConfig
from tit.blender.io import (
    field_to_colormap,
    write_binary_stl,
    write_ply_with_colors,
    write_ply_with_scalars,
)
from tit.blender.utils import create_roi_mesh, extract_roi_region_no_zeros

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_selected(regions: list[str], atlas_keys: set[str]) -> set[str]:
    """Expand bare region names to lh./rh. prefixed atlas keys.

    Users can specify "insula" to match both "lh.insula" and "rh.insula",
    or "lh.insula" to match only the left hemisphere.
    """
    selected: set[str] = set()
    for r in regions:
        if r in atlas_keys:
            selected.add(r)
        else:
            for prefix in ("lh.", "rh."):
                candidate = f"{prefix}{r}"
                if candidate in atlas_keys:
                    selected.add(candidate)
    return selected


def _calculate_global_field_range(nifti_path: str, mesh_path: str | None = None):
    """Compute (vmin, vmax) from a NIfTI field file."""
    try:
        import nibabel as nib

        nii = nib.load(nifti_path)
        data = nii.get_fdata()
        valid = data[data > 0]
        vmin = float(np.min(valid)) if valid.size else float(np.min(data))
        vmax = float(np.max(valid)) if valid.size else float(np.max(data))

        if mesh_path and os.path.exists(mesh_path):
            try:
                m = read_msh(mesh_path)
                if hasattr(m, "nodedata") and len(m.nodedata) > 0:
                    for nd in m.nodedata:
                        if hasattr(nd, "field_name"):
                            vals = nd.value
                            pos = vals[vals > 0]
                            if pos.size:
                                vmin = max(vmin, float(np.min(pos)))
                            vmax = min(vmax, float(np.max(vals)))
            except Exception:
                pass
        return vmin, vmax
    except Exception as exc:
        logger.warning(
            "Could not compute global field range from %s: %s", nifti_path, exc
        )
        return None, None


def _mesh_vertices_faces_and_field(mesh, field_name="TI_max"):
    """Extract (vertices, faces, field_data) from a SimNIBS mesh.

    Returns (None, None, None) when triangular elements are missing.
    """
    triangles = mesh.elm[mesh.elm.elm_type == 2]
    if len(triangles) == 0:
        return None, None, None

    if hasattr(triangles, "node_number_list"):
        triangle_nodes = triangles.node_number_list[:, :3] - 1
    else:
        triangle_nodes = triangles[:, :3] - 1

    unique_nodes = np.unique(triangle_nodes.flatten())
    node_map = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_nodes)}
    vertices = mesh.nodes.node_coord[unique_nodes]
    faces = np.array(
        [[node_map[idx] for idx in tri] for tri in triangle_nodes], dtype=np.int32
    )

    field_data = None
    if hasattr(mesh, "nodedata") and len(mesh.nodedata) > 0:
        for nd in mesh.nodedata:
            if hasattr(nd, "field_name") and nd.field_name == field_name:
                field_data = nd.value[unique_nodes]
                break
    if field_data is None and hasattr(mesh, "field") and field_name in mesh.field:
        field_data = mesh.field[field_name].value[unique_nodes]

    return vertices, faces, field_data


# ──────────────────────────────────────────────────────────────────────────────
# STL export path
# ──────────────────────────────────────────────────────────────────────────────


def _export_region_stl(
    surface_mesh, atlas, region_name, field_name, regions_dir, temp_dir
) -> bool:
    """Export a single atlas region as a binary STL file."""

    roi_mask = atlas[region_name]
    if np.sum(roi_mask) == 0:
        return False

    field_values = surface_mesh.field[field_name].value
    if np.sum(field_values[roi_mask] > 0) == 0:
        return False

    temp_mesh_path = create_roi_mesh(
        surface_mesh, roi_mask, field_values, field_name, region_name, temp_dir
    )
    roi_mesh = read_msh(temp_mesh_path)
    roi_field = roi_mesh.field[field_name].value
    vertices, faces = extract_roi_region_no_zeros(
        roi_mesh, roi_field, return_field_values=False
    )
    if vertices is None or faces is None:
        return False

    stl_path = os.path.join(regions_dir, f"{region_name}.stl")
    write_binary_stl(
        stl_path, vertices, faces, header_text="Generated from SimNIBS ROI mesh"
    )

    os.remove(temp_mesh_path)
    return True


def _export_whole_gm_stl(surface_mesh, cortical_dir):
    """Export the full GM surface as a binary STL file."""

    triangular = surface_mesh.elm.elm_type == 2
    triangle_nodes = surface_mesh.elm.node_number_list[triangular] - 1
    if triangle_nodes.ndim == 1:
        triangle_nodes = triangle_nodes.reshape(-1, 3)

    unique_verts = np.unique(triangle_nodes.flatten())
    vert_map = {old: new for new, old in enumerate(unique_verts)}
    remapped = np.array([[vert_map[idx] for idx in tri] for tri in triangle_nodes])
    vertices = surface_mesh.nodes.node_coord[unique_verts]

    stl_path = os.path.join(cortical_dir, "whole_gm.stl")
    write_binary_stl(
        stl_path, vertices, remapped, header_text="Generated from SimNIBS ROI mesh"
    )
    logger.info("Exported whole GM STL: %s", stl_path)


def _run_stl_export(config: RegionConfig, mesh_path: str) -> int:
    """Execute the STL export workflow."""
    converted = 0
    surface_mesh = read_msh(mesh_path)

    atlas_raw = atlas2subject(config.m2m_dir, config.atlas, split_labels=True)
    lh_labels = atlas_raw.get("lh", {})
    rh_labels = atlas_raw.get("rh", {})
    n_lh = len(next(iter(lh_labels.values()))) if lh_labels else 0
    n_rh = len(next(iter(rh_labels.values()))) if rh_labels else 0

    atlas = {}
    for name, mask in lh_labels.items():
        key = name if name.startswith("lh.") else f"lh.{name}"
        atlas[key] = np.concatenate([mask, np.zeros(n_rh, dtype=bool)])
    for name, mask in rh_labels.items():
        key = name if name.startswith("rh.") else f"rh.{name}"
        atlas[key] = np.concatenate([np.zeros(n_lh, dtype=bool), mask])

    cortical_dir = os.path.join(config.output_dir, "cortical_stls")
    regions_dir = os.path.join(cortical_dir, "regions")
    os.makedirs(regions_dir, exist_ok=True)

    selected = (
        _resolve_selected(config.regions, set(atlas.keys())) if config.regions else None
    )

    if not config.skip_regions:
        with tempfile.TemporaryDirectory() as temp_dir:
            for region_name in atlas.keys():
                if selected and region_name not in selected:
                    continue
                if _export_region_stl(
                    surface_mesh,
                    atlas,
                    region_name,
                    config.field_name,
                    regions_dir,
                    temp_dir,
                ):
                    converted += 1
        logger.info("Converted %d cortical regions (STL)", converted)

    if not config.skip_whole_gm:
        _export_whole_gm_stl(surface_mesh, cortical_dir)

    return converted


# ──────────────────────────────────────────────────────────────────────────────
# PLY export path
# ──────────────────────────────────────────────────────────────────────────────


def _write_ply_from_field(
    vertices,
    faces,
    field_data,
    ply_path,
    field_name,
    use_colors,
    colormap,
    field_range,
) -> bool:
    """Write a single PLY file with either vertex colors or scalars."""
    if vertices is None or faces is None:
        return False

    vmin, vmax = field_range if field_range else (None, None)
    comment = f"Generated from SimNIBS mesh with {field_name} field"

    if use_colors:
        if field_data is not None:
            colors = field_to_colormap(field_data, colormap, vmin, vmax)
        else:
            colors = np.full((len(vertices), 3), 128, dtype=np.uint8)
        write_ply_with_colors(ply_path, vertices, faces, colors, comment=comment)
    else:
        scalars = field_data if field_data is not None else np.zeros(len(vertices))
        write_ply_with_scalars(
            ply_path,
            vertices,
            faces,
            scalars,
            scalar_name=field_name,
            comment=comment,
        )
    return True


def _export_region_ply(
    mesh,
    atlas,
    region_name,
    field_name,
    regions_dir,
    temp_dir,
    use_colors,
    colormap,
    field_range,
    keep_meshes,
    meshes_dir,
) -> bool:
    """Export a single atlas region as a PLY file."""
    region_mask = atlas[region_name]
    if np.sum(region_mask) == 0:
        return False

    field_values = mesh.field[field_name].value
    if np.sum(field_values[region_mask] > 0) == 0:
        return False

    temp_mesh_path = create_roi_mesh(
        mesh,
        region_mask,
        field_values,
        field_name,
        region_name,
        temp_dir,
    )
    roi_mesh = read_msh(temp_mesh_path)
    roi_field = roi_mesh.field[field_name].value

    vertices, faces, vertex_field = extract_roi_region_no_zeros(
        roi_mesh,
        roi_field,
        return_field_values=True,
    )
    if vertices is None or faces is None:
        return False

    ply_path = os.path.join(regions_dir, f"{region_name}.ply")
    ok = _write_ply_from_field(
        vertices,
        faces,
        vertex_field,
        ply_path,
        field_name,
        use_colors,
        colormap,
        field_range,
    )

    if keep_meshes and meshes_dir:
        msh_path = os.path.join(meshes_dir, f"{region_name}_region.msh")
        roi_mesh.write(msh_path)
        _write_opt_file(roi_mesh, msh_path, field_name)

    os.remove(temp_mesh_path)
    return ok


def _export_whole_gm_ply(
    mesh,
    cortical_dir,
    mesh_path,
    field_name,
    use_colors,
    colormap,
    field_range,
    keep_meshes,
    output_dir,
):
    """Export the full GM surface as a PLY file."""
    ply_path = os.path.join(cortical_dir, "whole_gm.ply")
    vertices, faces, field_data = _mesh_vertices_faces_and_field(mesh, field_name)

    if vertices is None or faces is None:
        logger.warning("Failed to extract geometry for whole GM PLY")
        return

    _write_ply_from_field(
        vertices,
        faces,
        field_data,
        ply_path,
        field_name,
        use_colors,
        colormap,
        field_range,
    )
    logger.info("Exported whole GM PLY: %s", ply_path)

    if keep_meshes:
        whole_msh = os.path.join(output_dir, "whole_gm.msh")
        mesh.write(whole_msh)
        _write_opt_file(mesh, whole_msh, field_name)


def _write_opt_file(mesh, msh_path, field_name):
    """Create a Gmsh .opt visualization file for a mesh."""
    from tit.tools.gmsh_opt import create_mesh_opt_file

    field_values = mesh.field[field_name].value
    positive = field_values[field_values > 0]
    max_value = float(np.max(positive)) if len(positive) > 0 else 1.0

    field_info = {
        "fields": [field_name],
        "max_values": {field_name: max_value},
        "field_type": "node",
    }
    create_mesh_opt_file(msh_path, field_info)


def _effective_field_range(config, mesh, mesh_path):
    """Determine the color-mapping field range.

    Priority: explicit config.field_range > global_from_nifti > mesh positive values.
    """
    if config.field_range is not None:
        return tuple(config.field_range)

    if config.global_from_nifti:
        vmin, vmax = _calculate_global_field_range(config.global_from_nifti, mesh_path)
        if vmin is not None and vmax is not None:
            return (vmin, vmax)

    field_values = mesh.field[config.field_name].value
    positive = field_values[field_values > 0]
    if len(positive) > 0:
        return (float(np.min(positive)), float(np.max(positive)))
    return (0.0, 1.0)


def _run_ply_export(config: RegionConfig, mesh_path: str) -> int:
    """Execute the PLY export workflow."""
    converted = 0
    mesh = read_msh(mesh_path)

    atlas_raw = atlas2subject(config.m2m_dir, config.atlas, split_labels=True)
    lh_labels = atlas_raw.get("lh", {})
    rh_labels = atlas_raw.get("rh", {})
    n_lh = len(next(iter(lh_labels.values()))) if lh_labels else 0
    n_rh = len(next(iter(rh_labels.values()))) if rh_labels else 0

    atlas = {}
    for name, mask in lh_labels.items():
        key = name if name.startswith("lh.") else f"lh.{name}"
        atlas[key] = np.concatenate([mask, np.zeros(n_rh, dtype=bool)])
    for name, mask in rh_labels.items():
        key = name if name.startswith("rh.") else f"rh.{name}"
        atlas[key] = np.concatenate([np.zeros(n_lh, dtype=bool), mask])

    cortical_dir = os.path.join(config.output_dir, "cortical_plys")
    regions_dir = os.path.join(cortical_dir, "regions")
    os.makedirs(regions_dir, exist_ok=True)

    meshes_dir = None
    if config.keep_meshes:
        meshes_dir = os.path.join(config.output_dir, "meshes")
        os.makedirs(meshes_dir, exist_ok=True)

    use_colors = not config.scalars
    fr = _effective_field_range(config, mesh, mesh_path)
    selected = (
        _resolve_selected(config.regions, set(atlas.keys())) if config.regions else None
    )

    if not config.skip_regions:
        with tempfile.TemporaryDirectory() as temp_dir:
            for region_name, region_mask in atlas.items():
                if selected and region_name not in selected:
                    continue
                if _export_region_ply(
                    mesh,
                    atlas,
                    region_name,
                    config.field_name,
                    regions_dir,
                    temp_dir,
                    use_colors,
                    config.colormap,
                    fr,
                    config.keep_meshes,
                    meshes_dir,
                ):
                    converted += 1
        logger.info("Converted %d cortical regions (PLY)", converted)

    if not config.skip_whole_gm:
        _export_whole_gm_ply(
            mesh,
            cortical_dir,
            mesh_path,
            config.field_name,
            use_colors,
            config.colormap,
            fr,
            config.keep_meshes,
            config.output_dir,
        )

    return converted


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_paths(config: RegionConfig) -> None:
    """Resolve all paths from subject_id + simulation_name via PathManager."""
    from tit.paths import get_path_manager

    pm = get_path_manager()
    sid = config.subject_id
    sim = config.simulation_name

    config.m2m_dir = pm.m2m(sid)
    config.mesh = pm.ti_central_surface(sid, sim)
    fmt = str(config.format).lower()
    config.output_dir = os.path.join(
        pm.ti_toolbox(), "visual_exports", f"sub-{sid}", sim, fmt
    )


def run_regions(config: RegionConfig) -> int:
    """Export atlas-labelled cortical regions (and whole GM) as mesh files.

    Dispatches to the STL or PLY export path based on ``config.format``.

    Args:
        config: A :class:`RegionConfig` with ``subject_id`` +
            ``simulation_name``.

    Returns:
        Number of individual regions successfully exported.

    Raises:
        ValueError: If the mesh is missing the requested field.
        FileNotFoundError: If a required input file is missing.
    """
    _resolve_paths(config)
    from tit.telemetry import track_event
    from tit import constants as _const

    track_event(_const.TELEMETRY_OP_BLENDER_REGIONS, {"status": "start"})

    logger.info("Starting region export (format=%s)", config.format)

    mesh_path = config.mesh

    os.makedirs(config.output_dir, exist_ok=True)

    if config.format == RegionConfig.Format.STL:
        converted = _run_stl_export(config, mesh_path)
        out_subdir = os.path.join(config.output_dir, "cortical_stls")
    else:
        converted = _run_ply_export(config, mesh_path)
        out_subdir = os.path.join(config.output_dir, "cortical_plys")

    logger.info("Output: %s", out_subdir)
    logger.info("Done")
    return converted

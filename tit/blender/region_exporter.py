"""
Unified cortical region exporter -- STL and PLY output from a single entry point.

Extracts atlas-labelled cortical regions (and optionally the whole GM surface)
from a SimNIBS surface mesh.  Dispatches on :attr:`RegionConfig.format`
to produce either binary STL or colored/scalar PLY output.

Examples (programmatic):
    from tit.blender.config import RegionConfig
    from tit.blender.region_exporter import run_regions

    cfg = RegionConfig(
        m2m_dir="/data/m2m_001",
        output_dir="/data/out",
        mesh="/data/central.msh",
        format=RegionConfig.Format.PLY,
    )
    run_regions(cfg)
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import simnibs
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


def _resolve_msh2cortex(explicit_path: str | None) -> str | None:
    """Resolve the ``msh2cortex`` executable on disk or PATH."""
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return str(p)
    exe_name = (
        "msh2cortex.exe"
        if platform.system().lower().startswith("win")
        else "msh2cortex"
    )
    found = shutil.which("msh2cortex") or shutil.which(exe_name)
    if found:
        return found
    try:
        simnibs_root = Path(simnibs.__file__).resolve().parents[1]
        candidates = [
            simnibs_root / "bin" / exe_name,
            simnibs_root / "bin" / "msh2cortex",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        for sub in ("bin", "."):
            for p in (simnibs_root / sub).rglob("msh2cortex*"):
                if p.is_file():
                    return str(p)
    except Exception:
        pass
    return None


def _generate_cortical_surface(
    gm_mesh_path: str,
    m2m_dir: str,
    surface: str = "central",
    msh2cortex_path: str | None = None,
) -> str | None:
    """Run ``msh2cortex`` to produce a cortical surface mesh from a GM tetra mesh."""
    exe = _resolve_msh2cortex(msh2cortex_path)
    if not exe:
        logger.error("msh2cortex executable not found")
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        cmd = [exe, "-i", gm_mesh_path, "-m", str(m2m_dir), "-o", str(out_dir)]
        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as exc:
            logger.error("msh2cortex failed: %s", exc)
            return None

        candidates = list(out_dir.glob(f"*_{surface}.msh"))
        if not candidates and surface != "central":
            candidates = list(out_dir.glob("*_central.msh"))
        if not candidates:
            candidates = list(out_dir.glob("*.msh"))
        if not candidates:
            logger.error("msh2cortex produced no output meshes")
            return None

        selected = candidates[0]
        tmp_copy = Path(tempfile.mkstemp(suffix=f"_{surface}.msh")[1])
        tmp_copy.write_bytes(selected.read_bytes())
        return str(tmp_copy)


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
    try:
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
    except Exception as exc:
        logger.debug("Skipping region %s (STL): %s", region_name, exc)
        return False


def _export_whole_gm_stl(surface_mesh, cortical_dir):
    """Export the full GM surface as a binary STL file."""
    try:
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
    except Exception as exc:
        logger.warning("Failed to export whole GM STL: %s", exc)


def _run_stl_export(config: RegionConfig, mesh_path: str) -> int:
    """Execute the STL export workflow."""
    converted = 0
    surface_mesh = read_msh(mesh_path)

    if config.field_name not in surface_mesh.field:
        raise ValueError(f"Field '{config.field_name}' not found in mesh: {mesh_path}")

    atlas = {}
    for hemi_dict in atlas2subject(config.m2m_dir, config.atlas, split_labels=True).values():
        atlas.update(hemi_dict)

    cortical_dir = os.path.join(config.output_dir, "cortical_stls")
    regions_dir = os.path.join(cortical_dir, "regions")
    os.makedirs(regions_dir, exist_ok=True)

    selected = set(config.regions) if config.regions else None

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
    try:
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
            try:
                roi_mesh.write(msh_path)
                _write_opt_file(roi_mesh, msh_path, field_name)
            except Exception as exc:
                logger.debug("Could not save mesh for %s: %s", region_name, exc)

        os.remove(temp_mesh_path)
        return ok
    except Exception as exc:
        logger.debug("Skipping region %s (PLY): %s", region_name, exc)
        return False


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
        try:
            mesh.write(whole_msh)
            _write_opt_file(mesh, whole_msh, field_name)
        except Exception as exc:
            logger.debug("Could not save whole GM mesh: %s", exc)


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

    if config.field_name not in getattr(mesh, "field", {}):
        raise ValueError(f"Field '{config.field_name}' not found in mesh: {mesh_path}")

    atlas = {}
    for hemi_dict in atlas2subject(config.m2m_dir, config.atlas, split_labels=True).values():
        atlas.update(hemi_dict)

    cortical_dir = os.path.join(config.output_dir, "cortical_plys")
    regions_dir = os.path.join(cortical_dir, "regions")
    os.makedirs(regions_dir, exist_ok=True)

    meshes_dir = None
    if config.keep_meshes:
        meshes_dir = os.path.join(config.output_dir, "meshes")
        os.makedirs(meshes_dir, exist_ok=True)

    use_colors = not config.scalars
    fr = _effective_field_range(config, mesh, mesh_path)
    selected = set(config.regions) if config.regions else None

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


def run_regions(config: RegionConfig) -> int:
    """Export atlas-labelled cortical regions (and whole GM) as mesh files.

    Dispatches to the STL or PLY export path based on ``config.format``.

    Args:
        config: A fully-populated :class:`RegionConfig`.

    Returns:
        Number of individual regions successfully exported.

    Raises:
        ValueError: If the mesh is missing the requested field.
        FileNotFoundError: If a required input file is missing.
    """
    logger.info("Starting region export (format=%s)", config.format)

    # Resolve mesh path (may need msh2cortex for gm_mesh input)
    mesh_path = config.mesh
    if config.gm_mesh:
        if not os.path.exists(config.gm_mesh):
            raise FileNotFoundError(f"GM mesh not found: {config.gm_mesh}")
        generated = _generate_cortical_surface(
            config.gm_mesh,
            config.m2m_dir,
            str(config.surface),
            config.msh2cortex_path,
        )
        if not generated:
            raise RuntimeError("msh2cortex failed to produce a cortical surface mesh")
        mesh_path = generated

    if not os.path.exists(mesh_path):
        raise FileNotFoundError(f"Mesh file not found: {mesh_path}")
    if not os.path.isdir(config.m2m_dir):
        raise FileNotFoundError(f"m2m directory not found: {config.m2m_dir}")

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

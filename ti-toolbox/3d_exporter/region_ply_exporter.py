#!/usr/bin/env simnibs_python
"""
Single-tool converter: generate atlas-accurate cortical region PLYs and a whole-GM PLY.

Features:
- Loads subject cortical surface mesh (.msh from msh2cortex) and subject atlas (default DKTatlas40)
- Exports individual region meshes as PLY
- Exports the full GM surface as a single PLY
- Optional: keep individual region meshes and whole GM mesh as .msh files
- Optional: sample a NIfTI field onto mesh nodes; colorize via colormap or store scalars
- Optional: global colormap normalization from NIfTI min/max

Examples:
    simnibs_python region_ply_exporter.py \
        --mesh subject_central.msh \
        --m2m m2m_subject \
        --output-dir out \
        --atlas DKTatlas40 \
        --field-file subject_TI_max.nii.gz

    simnibs_python region_ply_exporter.py \
        --mesh subject_central.msh \
        --m2m m2m_subject \
        --output-dir out \
        --global-from-nifti subject_TI_max.nii.gz

    simnibs_python region_ply_exporter.py \
        --mesh subject_central.msh \
        --m2m m2m_subject \
        --output-dir out \
        --keep-meshes
"""


import nibabel as nib
import simnibs
import numpy as np

from simnibs import read_msh
from simnibs.utils.transformations import subject_atlas

import argparse
import os
import sys
from pathlib import Path
import tempfile
import subprocess
import shutil
import platform

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.mesh import create_mesh_opt_file


# ──────────────────────────────────────────────────────────────────────────────
# PLY Writers and Colormaps
# ──────────────────────────────────────────────────────────────────────────────

def write_ply_with_colors(vertices, faces, colors, output_path, field_name="TI_max"):
    """Write PLY file with vertex colors."""
    n_vertices = len(vertices)
    n_faces = len(faces)
    with open(output_path, 'w') as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"comment Generated from SimNIBS mesh with {field_name} field\n")
        f.write(f"element vertex {n_vertices}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write(f"element face {n_faces}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")
        for i in range(n_vertices):
            x, y, z = vertices[i]
            r, g, b = colors[i].astype(int)
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {r} {g} {b}\n")
        for face in faces:
            f.write(f"3 {face[0]} {face[1]} {face[2]}\n")


def write_ply_with_scalars(vertices, faces, scalars, output_path, field_name="TI_max"):
    """Write PLY file with scalar field data."""
    n_vertices = len(vertices)
    n_faces = len(faces)
    with open(output_path, 'w') as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"comment Generated from SimNIBS mesh with {field_name} field\n")
        f.write(f"element vertex {n_vertices}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write(f"property float {field_name}\n")
        f.write(f"element face {n_faces}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")
        for i in range(n_vertices):
            x, y, z = vertices[i]
            s = scalars[i]
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {s:.6f}\n")
        for face in faces:
            f.write(f"3 {face[0]} {face[1]} {face[2]}\n")


def simple_colormap(field_values, vmin=None, vmax=None):
    """Create simple blue-red colormap for field values."""
    if vmin is None:
        vmin = np.nanmin(field_values)
    if vmax is None:
        vmax = np.nanmax(field_values)
    if vmax == vmin:
        colors = np.zeros((len(field_values), 3), dtype=np.uint8)
        colors[:, 2] = 255
        return colors
    normalized = (field_values - vmin) / (vmax - vmin)
    normalized = np.clip(normalized, 0, 1)
    colors = np.zeros((len(field_values), 3), dtype=np.uint8)
    colors[:, 0] = (normalized * 255).astype(np.uint8)
    colors[:, 2] = ((1 - normalized) * 255).astype(np.uint8)
    return colors


def field_to_colormap(field_values, colormap='viridis', vmin=None, vmax=None):
    """Apply matplotlib colormap to field values."""
    try:
        import matplotlib.cm as cm
    except ImportError:
        # Matplotlib not available, using simple blue-red colormap
        return simple_colormap(field_values, vmin, vmax)
    if vmin is None:
        vmin = np.nanmin(field_values)
    if vmax is None:
        vmax = np.nanmax(field_values)
    if vmax == vmin:
        normalized = np.zeros_like(field_values)
    else:
        normalized = (field_values - vmin) / (vmax - vmin)
        normalized = np.clip(normalized, 0, 1)
    cmap = cm.get_cmap(colormap)
    colors_rgba = cmap(normalized)
    colors_rgb = (colors_rgba[:, :3] * 255).astype(np.uint8)
    return colors_rgb


# ──────────────────────────────────────────────────────────────────────────────
# Field Utilities
# ──────────────────────────────────────────────────────────────────────────────

def calculate_global_field_range(field_file_path, mesh_file_path=None):
    """Calculate global min/max field range from NIfTI file."""
    try:
        nii = nib.load(field_file_path)
        field_data = nii.get_fdata()
        valid_data = field_data[field_data > 0]
        global_min = float(np.min(valid_data)) if valid_data.size else float(np.min(field_data))
        global_max = float(np.max(valid_data)) if valid_data.size else float(np.max(field_data))
        if mesh_file_path and os.path.exists(mesh_file_path):
            try:
                mesh = read_msh(mesh_file_path)
                if hasattr(mesh, 'nodedata') and len(mesh.nodedata) > 0:
                    for nodedata in mesh.nodedata:
                        if hasattr(nodedata, 'field_name'):
                            mesh_values = nodedata.value
                            mesh_pos = mesh_values[mesh_values > 0]
                            if mesh_pos.size:
                                mesh_min = float(np.min(mesh_pos))
                            else:
                                mesh_min = float(np.min(mesh_values))
                            mesh_max = float(np.max(mesh_values))
                            if mesh_min > global_min:
                                global_min = mesh_min
                            if mesh_max < global_max:
                                global_max = mesh_max
            except Exception as e:
                pass
        return global_min, global_max
    except Exception as e:
        return None, None


# ──────────────────────────────────────────────────────────────────────────────
# Mesh/Atlas Utilities
# ──────────────────────────────────────────────────────────────────────────────

def create_roi_mesh(surface_mesh, roi_mask, field_values, field_name, region_name, temp_dir):
    """
    Create a ROI mesh with preserved field values for the specified region.
    
    Args:
        surface_mesh: The surface mesh object
        roi_mask: Boolean mask for the ROI
        field_values: Original field values
        field_name: Name of the field
        region_name: Name of the region
        temp_dir: Temporary directory for intermediate files
        
    Returns:
        str: Path to the temporary ROI mesh file
    """
    # Create new field values array initialized to zeros
    roi_field_values = np.zeros_like(field_values)
    
    # Preserve original field values only for ROI nodes
    roi_field_values[roi_mask] = field_values[roi_mask]
    
    # Create a new mesh by reading the original mesh file and modifying it
    # This avoids the copy() method issues
    temp_mesh_path = os.path.join(temp_dir, f"{region_name}_roi.msh")
    
    # Write the original mesh to temp file first
    surface_mesh.write(temp_mesh_path)
    
    # Read it back and modify the field
    roi_mesh = read_msh(temp_mesh_path)
    
    # Replace the field with our ROI version
    roi_mesh.field[field_name].value = roi_field_values
    
    # Write the modified mesh
    roi_mesh.write(temp_mesh_path)

    # Create .opt file for Gmsh visualization
    if len(roi_field_values[roi_mask]) > 0:
        max_value = np.max(roi_field_values[roi_mask])
    else:
        max_value = 1.0

    field_info = {
        'fields': [field_name],
        'max_values': {field_name: max_value},
        'field_type': 'node'
    }
    create_mesh_opt_file(temp_mesh_path, field_info)

    return temp_mesh_path


def extract_roi_region_no_zeros(mesh, roi_values, min_triangles=10):
    """Extract ROI region by removing only zero values (no threshold)."""
    
    # Find nodes with non-zero values
    roi_nodes = np.where(roi_values > 0)[0]
    roi_node_set = set(roi_nodes)
    
    if len(roi_nodes) == 0:
        return None, None, None
    
    # Get triangular elements
    triangular_elements = mesh.elm.elm_type == 2
    triangle_indices = np.where(triangular_elements)[0]
    triangle_nodes = mesh.elm.node_number_list[triangular_elements] - 1  # Convert to 0-based
    
    # Find triangles where at least 2 out of 3 vertices are in the ROI
    triangles_in_roi = []
    for i, triangle in enumerate(triangle_nodes):
        vertices_in_roi = sum(1 for node_idx in triangle if node_idx in roi_node_set)
        if vertices_in_roi >= 2:  # At least 2 out of 3 vertices in ROI
            triangles_in_roi.append(i)
    
    if len(triangles_in_roi) < min_triangles:
        return None, None, None
    
    # Get the triangles that are in the ROI
    roi_triangles = triangle_nodes[triangles_in_roi]
    
    # Get unique vertices used in these triangles
    unique_vertices = np.unique(roi_triangles.flatten())
    
    # Create vertex mapping (old index -> new index)
    vertex_mapping = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_vertices)}
    
    # Remap triangle indices to new vertex indices
    remapped_triangles = np.array([
        [vertex_mapping[face[0]], vertex_mapping[face[1]], vertex_mapping[face[2]]] 
        for face in roi_triangles
    ])
    
    # Extract vertex coordinates
    vertices = mesh.nodes.node_coord[unique_vertices]
    
    # Extract field values for the unique vertices
    vertex_field_values = roi_values[unique_vertices]
    
    return vertices, remapped_triangles, vertex_field_values


def mesh_vertices_faces_and_field(mesh, field_name="TI_max"):
    """Extract vertices, faces, and field data from mesh."""
    triangles = mesh.elm[mesh.elm.elm_type == 2]
    if len(triangles) == 0:
        return None, None, None
    if hasattr(triangles, 'node_number_list'):
        triangle_nodes = triangles.node_number_list[:, :3] - 1
    else:
        triangle_nodes = triangles[:, :3] - 1
    unique_nodes = np.unique(triangle_nodes.flatten())
    node_map = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_nodes)}
    vertices = mesh.nodes.node_coord[unique_nodes]
    faces = np.array([[node_map[idx] for idx in tri] for tri in triangle_nodes], dtype=np.int32)
    field_data = None
    if hasattr(mesh, 'nodedata') and len(mesh.nodedata) > 0:
        field_idx = None
        for i, nd in enumerate(mesh.nodedata):
            if hasattr(nd, 'field_name') and nd.field_name == field_name:
                field_idx = i
                break
        if field_idx is not None:
            field_full = mesh.nodedata[field_idx].value
            field_data = field_full[unique_nodes]
    return vertices, faces, field_data




# ──────────────────────────────────────────────────────────────────────────────
# Main Orchestration
# ──────────────────────────────────────────────────────────────────────────────

def create_ply_from_vertices_faces(vertices, faces, vertex_field_values, ply_path, field_name, use_colors, colormap, field_range):
    """Create PLY file from vertices, faces, and field values."""
    if vertices is None or faces is None:
        return False
    
    vmin, vmax = field_range if field_range else (None, None)
    if use_colors:
        colors = field_to_colormap(vertex_field_values, colormap, vmin, vmax)
        write_ply_with_colors(vertices, faces, colors, ply_path, field_name)
    else:
        write_ply_with_scalars(vertices, faces, vertex_field_values, ply_path, field_name)
    return True


def export_mesh_to_ply(mesh, ply_path, field_name, use_colors, colormap, field_range):
    """Export mesh to PLY format with optional field coloring."""
    vertices, faces, field_data = mesh_vertices_faces_and_field(mesh, field_name)
    if vertices is None or faces is None:
        return False
    if field_data is None:
        if use_colors:
            colors = np.full((len(vertices), 3), 128, dtype=np.uint8)
            write_ply_with_colors(vertices, faces, colors, ply_path, field_name)
        else:
            scalars = np.zeros(len(vertices))
            write_ply_with_scalars(vertices, faces, scalars, ply_path, field_name)
        return True
    vmin, vmax = field_range if field_range else (None, None)
    if use_colors:
        colors = field_to_colormap(field_data, colormap, vmin, vmax)
        write_ply_with_colors(vertices, faces, colors, ply_path, field_name)
    else:
        write_ply_with_scalars(vertices, faces, field_data, ply_path, field_name)
    return True


def run_conversion(mesh_path, m2m_dir, output_dir, atlas_name, field_name,
                   use_colors, colormap, field_range, global_from_nifti,
                   export_regions, export_whole_gm, keep_meshes,
                   regions_filter=None):
    """Main conversion workflow."""
    converted_count = 0
    mesh = read_msh(mesh_path)
    if not hasattr(mesh, 'field') or field_name not in getattr(mesh, 'field', {}):
        raise ValueError(f"Field '{field_name}' not found in mesh: {mesh_path}")
    atlas = subject_atlas(atlas_name, str(m2m_dir))

    cortical_plys_dir = Path(output_dir) / "cortical_plys"
    # Unified: use 'regions' subfolder for region outputs
    regions_out_dir = cortical_plys_dir / "regions"
    regions_out_dir.mkdir(parents=True, exist_ok=True)
    
    # Create meshes directory if keeping meshes
    if keep_meshes:
        meshes_out_dir = Path(output_dir) / "meshes"
        meshes_out_dir.mkdir(parents=True, exist_ok=True)

    effective_field_range = None
    if field_range is not None:
        effective_field_range = tuple(field_range)
    elif global_from_nifti:
        vmin, vmax = calculate_global_field_range(global_from_nifti, mesh_path)
        if vmin is not None and vmax is not None:
            effective_field_range = (vmin, vmax)

    if export_regions:
        success_count = 0
        mesh_success_count = 0
        
        # Calculate global field range from the whole mesh if not already set
        if effective_field_range is None:
            field_values = mesh.field[field_name].value
            positive_values = field_values[field_values > 0]
            if len(positive_values) > 0:
                global_min = float(np.min(positive_values))
                global_max = float(np.max(positive_values))
                effective_field_range = (global_min, global_max)
            else:
                effective_field_range = (0.0, 1.0)
        
        # Create temporary directory for ROI meshes
        with tempfile.TemporaryDirectory() as temp_dir:
            for region_name, region_mask in atlas.items():
                if regions_filter and region_name not in regions_filter:
                    continue
                try:
                    # Check if we have any nodes in the ROI
                    roi_nodes_count = np.sum(region_mask)
                    if roi_nodes_count == 0:
                        continue
                    
                    # Get the field values within the ROI
                    field_values = mesh.field[field_name].value
                    field_values_in_roi = field_values[region_mask]
                    
                    # Filter for positive values in ROI
                    positive_mask = field_values_in_roi > 0
                    field_values_positive = field_values_in_roi[positive_mask]
                    
                    # Check if we have any positive values in the ROI
                    positive_count = len(field_values_positive)
                    if positive_count == 0:
                        continue
                    
                    # Create ROI mesh
                    temp_mesh_path = create_roi_mesh(mesh, region_mask, field_values, field_name, region_name, temp_dir)
                    
                    # Load the ROI mesh for PLY conversion
                    roi_mesh = read_msh(temp_mesh_path)
                    
                    # Get the ROI field values for extraction
                    roi_field_values = roi_mesh.field[field_name].value
                    
                    # Extract ROI region (remove zero values)
                    vertices, faces, vertex_field_values = extract_roi_region_no_zeros(roi_mesh, roi_field_values)
                    
                    if vertices is None or faces is None:
                        continue
                    
                    # Create PLY with field data using global field range
                    ply_path = regions_out_dir / f"{region_name}.ply"
                    if create_ply_from_vertices_faces(vertices, faces, vertex_field_values, str(ply_path), field_name, use_colors, colormap, effective_field_range):
                        success_count += 1
                        converted_count += 1
                    
                    # Export MSH if requested
                    if keep_meshes:
                        msh_path = meshes_out_dir / f"{region_name}_region.msh"
                        try:
                            roi_mesh.write(str(msh_path))
                            mesh_success_count += 1

                            # Create .opt file for Gmsh visualization
                            field_values = roi_mesh.field[field_name].value
                            if len(field_values[field_values > 0]) > 0:
                                max_value = np.max(field_values[field_values > 0])
                            else:
                                max_value = 1.0

                            field_info = {
                                'fields': [field_name],
                                'max_values': {field_name: max_value},
                                'field_type': 'node'
                            }
                            create_mesh_opt_file(str(msh_path), field_info)
                        except Exception as e:
                            pass
                    
                    # Clean up temporary mesh file
                    os.remove(temp_mesh_path)
                    
                except Exception as e:
                    continue

    if export_whole_gm:
        # Name whole GM consistently: gm_<simulation>.ply
        base_name = os.path.basename(mesh_path)
        name_wo_ext = os.path.splitext(base_name)[0]
        sim_name = name_wo_ext.split('_TI')[0]
        # Unified whole GM filename
        whole_ply = cortical_plys_dir / "whole_gm.ply"
        export_mesh_to_ply(mesh, str(whole_ply), field_name, use_colors, colormap, effective_field_range)
    
    # Export whole GM mesh if requested
    if keep_meshes and export_whole_gm:
        whole_msh = Path(output_dir) / "whole_gm.msh"
        try:
            mesh.write(str(whole_msh))

            # Create .opt file for Gmsh visualization
            field_values = mesh.field[field_name].value
            if len(field_values[field_values > 0]) > 0:
                max_value = np.max(field_values[field_values > 0])
            else:
                max_value = 1.0

            field_info = {
                'fields': [field_name],
                'max_values': {field_name: max_value},
                'field_type': 'node'
            }
            create_mesh_opt_file(str(whole_msh), field_info)
        except Exception as e:
            pass
    
    return converted_count


def _resolve_msh2cortex(explicit_path: str | None) -> str | None:
    """Resolve msh2cortex executable path."""
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return str(p)
    # Try PATH
    exe_name = "msh2cortex.exe" if platform.system().lower().startswith("win") else "msh2cortex"
    found = shutil.which("msh2cortex") or shutil.which(exe_name)
    if found:
        return found
    # Try locating near simnibs installation
    try:
        simnibs_root = Path(simnibs.__file__).resolve().parents[1]
        candidates = [
            simnibs_root / "bin" / exe_name,
            simnibs_root / "bin" / "msh2cortex",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        # Fallback: recursive search (limited depth)
        for sub in ("bin", "."):
            for p in (simnibs_root / sub).rglob("msh2cortex*"):
                if p.is_file():
                    return str(p)
    except Exception:
        pass
    return None


def generate_cortical_surface_from_tetra(gm_mesh_path, m2m_dir, surface="central", msh2cortex_path: str | None = None):
    """Generate cortical surface mesh from tetrahedral GM mesh using msh2cortex."""
    exe = _resolve_msh2cortex(msh2cortex_path)
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        cmd = [
            exe,
            "-i", gm_mesh_path,
            "-m", str(m2m_dir),
            "-o", str(out_dir)
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            return None

        # Try to find the requested surface mesh
        candidates = list(out_dir.glob(f"*_{surface}.msh"))
        if not candidates:
            # Fallbacks: try central if requested not found, then any *_central.msh present
            if surface != "central":
                candidates = list(out_dir.glob("*_central.msh"))
        if not candidates:
            # Last resort: any .msh produced
            candidates = list(out_dir.glob("*.msh"))
        if not candidates:
            return None

        # Move/copy the selected mesh to a stable temp file we control
        selected = candidates[0]
        tmp_copy = Path(tempfile.mkstemp(suffix=f"_{surface}.msh")[1])
        tmp_copy.write_bytes(selected.read_bytes())
        return str(tmp_copy)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Export cortical regions and whole GM surface to PLY")
    parser.add_argument("--mesh", help="Input cortical surface mesh (.msh) from msh2cortex")
    parser.add_argument("--gm-mesh", help="Input tetrahedral GM .msh (volumetric); will run msh2cortex")
    parser.add_argument("--m2m", required=True, help="Subject m2m directory")
    parser.add_argument("--output-dir", required=True, help="Output directory for PLY files")
    parser.add_argument("--atlas", default="DK40", help="Atlas name (default: DK40)")
    parser.add_argument("--surface", default="central", choices=["central", "pial", "white"], help="Cortical surface to extract when using --gm-mesh (default: central)")
    parser.add_argument("--msh2cortex", help="Path to msh2cortex executable (optional override)")
    parser.add_argument("--field", default="TI_max", help="Field name to use/store (default: TI_max)")
    parser.add_argument("--scalars", action="store_true", help="Store field as scalars instead of colors")
    parser.add_argument("--colormap", default="viridis", help="Colormap for colors mode")
    parser.add_argument("--field-range", nargs=2, type=float, metavar=("MIN", "MAX"), help="Explicit field range for mapping")
    parser.add_argument("--global-from-nifti", help="Use global min/max from this NIfTI for color mapping")
    parser.add_argument("--skip-regions", action="store_true", help="Do not export individual region PLYs")
    parser.add_argument("--skip-whole-gm", action="store_true", help="Do not export the whole GM PLY")
    parser.add_argument("--regions", help="Comma-separated list of region names to export (subset)")
    parser.add_argument("--keep-meshes", action="store_true", help="Keep individual cortical region meshes as .msh files")
    return parser.parse_args()


def main():
    """Main entry point."""
    print("Starting...")
    args = parse_args()
    mesh_path = args.mesh
    m2m_dir = args.m2m
    output_dir = args.output_dir
    atlas_name = args.atlas
    surface = args.surface
    field_name = args.field
    use_colors = not args.scalars
    colormap = args.colormap
    field_range = tuple(args.field_range) if args.field_range else None
    global_from_nifti = args.global_from_nifti
    export_regions = not args.skip_regions
    export_whole_gm = not args.skip_whole_gm
    keep_meshes = args.keep_meshes

    if not mesh_path and not args.gm_mesh:
        return 1
    if args.gm_mesh:
        if not os.path.exists(args.gm_mesh):
            return 1
        generated_surface = generate_cortical_surface_from_tetra(args.gm_mesh, m2m_dir, surface, args.msh2cortex)
        if not generated_surface:
            return 1
        mesh_path = generated_surface
    if not os.path.exists(mesh_path):
        return 1
    if not os.path.isdir(m2m_dir):
        return 1
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print("Converting...")
    regions_filter = None
    if args.regions:
        regions_filter = set([r.strip() for r in args.regions.split(',') if r.strip()])

    try:
        converted_count = run_conversion(
            mesh_path,
            m2m_dir,
            output_dir,
            atlas_name,
            field_name,
            use_colors,
            colormap,
            field_range,
            global_from_nifti,
            export_regions,
            export_whole_gm,
            keep_meshes,
            regions_filter=regions_filter,
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    print(f"Converted {converted_count} cortical regions.")
    print(f"Output: {os.path.join(output_dir, 'cortical_plys')}")
    print("Finishing...")
    return 0


if __name__ == "__main__":
    sys.exit(main())



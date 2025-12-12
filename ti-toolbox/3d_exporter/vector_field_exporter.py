#!/usr/bin/env simnibs_python
"""
One-command exporter for TI/mTI (and optional CH1, CH2, SUM, TI_normal) vector arrows to PLY.
Vectors are placed at face barycenters of the central surface mesh.

Examples:
  simnibs_python vector_field_exporter.py tdcs1.msh tdcs2.msh output_dir --central-surface central.msh
  simnibs_python vector_field_exporter.py tdcs1.msh tdcs2.msh output_dir --central-surface central.msh --export-ch1-ch2 --sum --ti-normal
  simnibs_python vector_field_exporter.py tdcs1.msh tdcs2.msh output_dir --central-surface central.msh --mti tdcs3.msh tdcs4.msh
"""

import os
import sys
import argparse
import numpy as np
import simnibs
import trimesh
from scipy.spatial.transform import Rotation

# Import shared core utilities
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.calc import get_TI_vectors, get_mTI_vectors

# Baseline visualization scaling so that user-facing defaults of 1.00 produce
# a practical visual size without requiring large/small numeric inputs.
BASE_VECTOR_SCALE = 1.0
BASE_VECTOR_LENGTH = 1.0
BASE_LENGTH_SCALE = 10.0
BASE_VECTOR_WIDTH = 0.10


# ──────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ──────────────────────────────────────────────────────────────────────────────

def create_arrow(position, direction, magnitude, *,
                 vector_scale=0.4, base_length=1.0, shaft_width=0.05,
                 length_mode: str = 'linear', length_scale: float = 1.0,
                 anchor: str = 'tail'):
    """Create a small arrow mesh for a vector with configurable length mapping."""
    # Determine arrow length from magnitude
    if length_mode == 'linear':
        scaled_length = max(1e-9, float(length_scale) * float(magnitude))
    else:
        magnitude_scale_factor = 0.005
        scaled_length = base_length * (1.0 + magnitude_scale_factor * float(magnitude))

    shaft_length = scaled_length * 0.8
    shaft_radius = shaft_width * 0.5
    head_length = scaled_length * 0.2
    head_radius = shaft_width * 1.5

    # Trimesh cylinder: centered at origin, extends from -height/2 to +height/2 along Z
    # Trimesh cone: base at z=0, tip at z=height (pointing up)
    shaft = trimesh.creation.cylinder(radius=shaft_radius, height=shaft_length)
    head = trimesh.creation.cone(radius=head_radius, height=head_length)
    
    # Position cone so its base connects to shaft end
    # Shaft extends from -shaft_length/2 to +shaft_length/2
    # Cone base should be at +shaft_length/2, so translate cone by +shaft_length/2
    head.apply_translation([0, 0, shaft_length / 2.0])
    
    arrow = trimesh.util.concatenate([shaft, head])
    
    # After concatenation, arrow extends from -shaft_length/2 to +shaft_length/2 + head_length along Z
    # Center is at origin

    # Global scale
    arrow.apply_scale(vector_scale)
    
    # After scaling:
    # - Shaft extends from -actual_shaft_len/2 to +actual_shaft_len/2
    # - Head extends from +actual_shaft_len/2 to +actual_shaft_len/2 + actual_head_len
    # - Tail is at -actual_shaft_len/2
    # - Tip is at +actual_shaft_len/2 + actual_head_len
    actual_shaft_len = shaft_length * vector_scale
    actual_head_len = head_length * vector_scale

    # Orientation (align +Z to direction)
    dir_norm = np.linalg.norm(direction)
    if dir_norm > 1e-12:
        ndir = direction / dir_norm
        z = np.array([0.0, 0.0, 1.0])
        axis = np.cross(z, ndir)
        angle = np.arccos(np.clip(np.dot(z, ndir), -1.0, 1.0))
        if np.linalg.norm(axis) > 1e-12:
            axis = axis / np.linalg.norm(axis)
            rot = Rotation.from_rotvec(angle * axis)
            T = np.eye(4)
            T[:3, :3] = rot.as_matrix()
            arrow.apply_transform(T)
    else:
        ndir = np.array([0.0, 0.0, 1.0])
    
    # After rotation, arrow's local +Z (which was [0,0,1]) is now aligned with ndir in world space
    # So in world space:
    # - Tail is at: -ndir * (actual_shaft_len/2)
    # - Tip is at: +ndir * (actual_shaft_len/2 + actual_head_len)
    
    # Translate based on anchor
    # After rotation, arrow is centered at origin with +Z aligned with ndir
    # Tail is at: -ndir * (actual_shaft_len/2)
    # Tip is at: +ndir * (actual_shaft_len/2 + actual_head_len)
    
    if anchor == 'head':
        # Place tip at position
        # Tip is currently at: origin + ndir * (actual_shaft_len/2 + actual_head_len)
        # To move tip to position, translate by: position - ndir * (actual_shaft_len/2 + actual_head_len)
        tip_position = ndir * (actual_shaft_len / 2.0 + actual_head_len)
        arrow.apply_translation(position - tip_position)
    else:
        # Place tail at position  
        # Tail is currently at: origin - ndir * (actual_shaft_len/2) = -ndir * (actual_shaft_len/2)
        # To move tail to position, translate by: position - tail_position
        # position - (-ndir * actual_shaft_len/2) = position + ndir * actual_shaft_len/2
        tail_position = -ndir * (actual_shaft_len / 2.0)
        # Translation: position - tail_position = position - (-ndir * actual_shaft_len/2) = position + ndir * actual_shaft_len/2
        arrow.apply_translation(position - tail_position)

    return arrow


def write_ply_arrows(output_file, positions, vectors, magnitudes, colors, *,
                     length_mode: str = 'linear', length_scale: float = 1.0,
                     anchor: str = 'tail', vector_scale: float = 0.4,
                     base_length: float = 1.0, shaft_width: float = 0.05):
    """Write multiple arrows as a colored PLY file (ASCII)."""
    total = len(positions)
    if total == 0:
        return

    all_vertices = []
    all_faces = []
    all_colors = []

    for i in range(total):
        arrow = create_arrow(
            positions[i], vectors[i], magnitudes[i],
            vector_scale=vector_scale, base_length=base_length, shaft_width=shaft_width,
            length_mode=length_mode, length_scale=length_scale, anchor=anchor,
        )
        start = len(all_vertices)
        all_vertices.extend(arrow.vertices)
        for f in arrow.faces:
            all_faces.append([start + int(f[0]), start + int(f[1]), start + int(f[2])])
        for _ in range(len(arrow.vertices)):
            all_colors.append(colors[i])

    if not all_vertices:
        return

    with open(output_file, 'w') as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(all_vertices)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write("property uchar alpha\n")
        f.write(f"element face {len(all_faces)}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")
        for v, c in zip(all_vertices, all_colors):
            f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f} {int(c[0])} {int(c[1])} {int(c[2])} {int(c[3])}\n")
        for face in all_faces:
            f.write(f"3 {face[0]} {face[1]} {face[2]}\n")


# ──────────────────────────────────────────────────────────────────────────────
# Data helpers
# ──────────────────────────────────────────────────────────────────────────────

def barycenters_for_mesh(m):
    try:
        return m.elements_baricenters().value
    except Exception:
        node_coords = m.nodes.node_coord
        element_nodes = m.elm.node_number_list - 1
        return np.mean(node_coords[element_nodes], axis=1)


def surface_normals_for_mesh(m):
    """Approximate per-element surface normals for triangular elements."""
    try:
        node_coords = m.nodes.node_coord
        element_nodes = m.elm.node_number_list - 1
        normals = []
        for element in element_nodes:
            nodes = node_coords[element[:3]]
            edge1 = nodes[1] - nodes[0]
            edge2 = nodes[2] - nodes[0]
            normal = np.cross(edge1, edge2)
            norm = np.linalg.norm(normal)
            if norm > 1e-12:
                normal = normal / norm
            else:
                normal = np.array([0.0, 0.0, 1.0])
            normals.append(normal)
        return np.array(normals)
    except Exception:
        # Fallback: up-vector
        return np.tile(np.array([0.0, 0.0, 1.0]), (len(m.elm.node_number_list), 1))


def surface_normals_at_face_indices(surface_mesh, face_indices):
    """
    Get surface normals for specific face indices.
    
    Args:
        surface_mesh: SimNIBS surface mesh
        face_indices: Array of face indices
        
    Returns:
        Array of [N, 3] normals corresponding to the face indices
    """
    if face_indices is None:
        return None
    
    try:
        # Get all surface normals
        all_normals = surface_normals_for_mesh(surface_mesh)
        # Get triangular elements
        triangular_elements = surface_mesh.elm.elm_type == 2
        if not np.any(triangular_elements):
            triangular_elements = np.ones(len(surface_mesh.elm.node_number_list), dtype=bool)
        
        # Get normals for triangular elements only
        triangle_normals = all_normals[triangular_elements]
        
        # Get normals at the specified face indices
        # Ensure indices are within bounds
        valid_indices = face_indices < len(triangle_normals)
        normals = np.zeros((len(face_indices), 3))
        normals[valid_indices] = triangle_normals[face_indices[valid_indices]]
        # Fill invalid indices with default normal
        normals[~valid_indices] = np.array([0.0, 0.0, 1.0])
        
        return normals
    except Exception:
        return None


def get_surface_face_barycenters(surface_mesh):
    """
    Get barycenters (centers) of triangular faces in a surface mesh.
    
    Args:
        surface_mesh: SimNIBS surface mesh (triangular surface)
        
    Returns:
        Array of [N, 3] barycenter positions for each triangle
    """
    # Get triangular elements (elm_type == 2 for triangles)
    triangular_elements = surface_mesh.elm.elm_type == 2
    if not np.any(triangular_elements):
        # Fallback: try to get all elements if no triangles found
        triangular_elements = np.ones(len(surface_mesh.elm.node_number_list), dtype=bool)
    
    triangle_nodes = surface_mesh.elm.node_number_list[triangular_elements] - 1  # Convert to 0-based
    # Take first 3 nodes (assuming triangular elements)
    triangle_nodes = triangle_nodes[:, :3]
    
    # Get node coordinates
    node_coords = surface_mesh.nodes.node_coord
    
    # Calculate barycenters (centers) of each triangle
    barycenters = np.mean(node_coords[triangle_nodes], axis=1)
    
    return barycenters


def interpolate_field_to_surface_positions(volumetric_mesh, target_positions, field_name='E'):
    """
    Interpolate a field from volumetric mesh to target positions (e.g., face barycenters).
    
    Args:
        volumetric_mesh: SimNIBS volumetric mesh with field data
        target_positions: Array of [N, 3] target positions to interpolate to
        field_name: Name of the field to interpolate (default: 'E')
        
    Returns:
        Array of [N, 3] field values at target positions
    """
    if field_name not in volumetric_mesh.field:
        raise ValueError(f"Field '{field_name}' not found in volumetric mesh")
    
    # Get field values from volumetric mesh (element-based)
    field_elm = volumetric_mesh.field[field_name].value  # [n_elements, 3]
    
    # Method 1: Try to convert element-based to node-based, then interpolate to target positions
    try:
        from scipy.spatial import cKDTree
        
        # Convert element-based field to node-based using SimNIBS elm2node_matrix
        M = volumetric_mesh.elm2node_matrix()
        vol_field_nodes = np.zeros((M.shape[0], 3))
        for i in range(3):
            vol_field_nodes[:, i] = M.dot(field_elm[:, i])
        
        # Get volumetric mesh node positions
        vol_node_positions = volumetric_mesh.nodes.node_coord
        
        # Find nearest volumetric mesh nodes for each target position
        tree = cKDTree(vol_node_positions)
        distances, indices = tree.query(target_positions)
        
        # Map field values from volumetric nodes to target positions
        field_values = vol_field_nodes[indices]
        
        return field_values
    except Exception:
        # Fallback: use element barycenters for interpolation
        from scipy.spatial import cKDTree
        
        # Get element barycenters
        elm_positions = barycenters_for_mesh(volumetric_mesh)
        
        # Interpolate using nearest neighbor from element barycenters
        field_values = np.zeros((len(target_positions), 3))
        tree = cKDTree(elm_positions)
        distances, indices = tree.query(target_positions)
        
        for i in range(len(target_positions)):
            field_values[i] = field_elm[indices[i]]
        
        return field_values


def project_positions_to_surface(positions, surface_mesh):
    """
    Project positions to the nearest points on a surface mesh.
    
    Args:
        positions: Array of [N, 3] positions to project
        surface_mesh: SimNIBS surface mesh (triangular surface mesh)
        
    Returns:
        tuple: (projected_positions, face_indices) where:
            - projected_positions: Array of [N, 3] projected positions on the surface
            - face_indices: Array of [N] indices of the closest faces (for normal computation)
    """
    # Extract vertices and faces from surface mesh
    try:
        # Get triangular elements (elm_type == 2 for triangles)
        triangular_elements = surface_mesh.elm.elm_type == 2
        if not np.any(triangular_elements):
            # Fallback: try to get all elements if no triangles found
            triangular_elements = np.ones(len(surface_mesh.elm.node_number_list), dtype=bool)
        
        triangle_nodes = surface_mesh.elm.node_number_list[triangular_elements] - 1  # Convert to 0-based
        # Take first 3 nodes (assuming triangular elements)
        triangle_nodes = triangle_nodes[:, :3]
        
        vertices = surface_mesh.nodes.node_coord
        faces = triangle_nodes
        
        # Create trimesh object from surface
        surface_trimesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        
        # Find nearest points on surface
        # trimesh.proximity.closest_point returns (closest_points, distances, face_indices)
        closest_points, distances, face_indices = trimesh.proximity.closest_point(surface_trimesh, positions)
        
        return closest_points, face_indices
    except Exception as e:
        # Fallback: return original positions if projection fails
        print(f"Warning: Failed to project positions to surface: {e}")
        return positions, None


def map_magnitude_to_colors_magscale(magnitudes, *,
                                     all_magnitudes_full,
                                     blue_pct: float, green_pct: float, red_pct: float):
    # Percentiles across full-mesh magnitudes to reduce outlier skew
    blue_pct = float(min(max(blue_pct, 0.0), 100.0))
    green_pct = float(min(max(green_pct, 0.0), 100.0))
    red_pct = float(min(max(red_pct, 0.0), 100.0))
    if green_pct < blue_pct:
        green_pct = blue_pct
    if red_pct < green_pct:
        red_pct = green_pct

    mag_blue = np.percentile(all_magnitudes_full, blue_pct)
    mag_green = np.percentile(all_magnitudes_full, green_pct)
    mag_red = np.percentile(all_magnitudes_full, red_pct)

    def map_one(mag):
        if mag <= mag_blue:
            return np.array([0, 0, 255, 255], dtype=np.uint8)
        if mag <= mag_green:
            denom = (mag_green - mag_blue)
            t = 0.0 if denom <= 0 else float((mag - mag_blue) / denom)
            r, g, b = 0, int(255 * t), int(255 * (1.0 - t))
            return np.array([r, g, b, 255], dtype=np.uint8)
        if mag <= mag_red:
            denom = (mag_red - mag_green)
            t = 1.0 if denom <= 0 else float((mag - mag_green) / denom)
            r, g, b = int(255 * t), int(255 * (1.0 - t)), 0
            return np.array([r, g, b, 255], dtype=np.uint8)
        return np.array([255, 0, 0, 255], dtype=np.uint8)

    return np.array([map_one(m) for m in magnitudes])


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("Starting...")
    ap = argparse.ArgumentParser(
        description="Export TI/mTI vector arrows to PLY at face barycenters (optional CH1, CH2, SUM, TI_normal)")

    ap.add_argument('mesh1', help='TDCS mesh 1 (with E field)')
    ap.add_argument('mesh2', help='TDCS mesh 2 (with E field)')
    ap.add_argument('output_prefix', help='Output directory for PLY files (TI.ply, CH1.ply, etc.)')

    ap.add_argument('--mti', nargs=2, metavar=('mesh3', 'mesh4'),
                    help='Enable mTI mode with two extra meshes (mesh3, mesh4)')

    # Optional outputs
    ap.add_argument('--export-ch1-ch2', dest='export_ch1_ch2', action='store_true', help='Export CH1 and CH2 vectors (default: only TI)')
    ap.add_argument('--sum', dest='do_sum', action='store_true', help='Also export E_sum (TI: E1+E2, mTI: E1+E2+E3+E4)')
    ap.add_argument('--ti-normal', dest='do_ti_normal', action='store_true', help='Also export TI_normal (projection onto surface normals)')
    ap.add_argument('--combined', action='store_true', help='Also export combined PLY containing all requested types')

    # Filtering & sampling
    ap.add_argument('--central-surface', required=True, help='Central surface mesh (.msh from msh2cortex) to place vectors at face barycenters (matches STL surface)')
    ap.add_argument('--top-percent', type=float, default=None, help='Keep only top X percent by |TI/mTI| before sampling')
    ap.add_argument('--count', type=int, default=100000, help='Number of vectors to sample')
    ap.add_argument('--all-nodes', action='store_true', help='Use all available vectors (disable sampling)')
    ap.add_argument('--seed', type=int, default=42, help='Random seed for sampling reproducibility')

    # Arrow styling
    ap.add_argument('--length-mode', choices=['linear', 'visual'], default='linear', help="Arrow length mapping mode")
    ap.add_argument('--length-scale', type=float, default=1.0, help='Unitless length scaling (internally normalized)')
    ap.add_argument('--vector-scale', type=float, default=1.0, help='Unitless global arrow scale (internally normalized)')
    ap.add_argument('--vector-width', type=float, default=1.0, help='Unitless shaft width (internally normalized)')
    ap.add_argument('--vector-length', type=float, default=1.0, help='Unitless base arrow length (internally normalized)')
    ap.add_argument('--anchor', choices=['tail', 'head'], default='tail', help='Which end of the arrow touches the barycenter')

    # Colors
    ap.add_argument('--color', choices=['rgb', 'magscale'], default='rgb',
                    help="Color mode: rgb=CH1 red, CH2 blue, TI green (default); magscale=by magnitude")
    ap.add_argument('--blue-percentile', type=float, default=50.0, help='Percentile mapped to full blue (magscale)')
    ap.add_argument('--green-percentile', type=float, default=80.0, help='Percentile mapped to green pivot (magscale)')
    ap.add_argument('--red-percentile', type=float, default=95.0, help='Percentile mapped to full red (magscale)')

    ap.add_argument('--verbose', action='store_true', help='Verbose logging')

    args = ap.parse_args()

    # Validate paths
    for p in [args.mesh1, args.mesh2]:
        if not os.path.exists(p):
            return 1
    m3 = m4 = None
    is_mti = args.mti is not None
    if is_mti:
        m3_path, m4_path = args.mti
        if not os.path.exists(m3_path) or not os.path.exists(m4_path):
            return 1

    # Read meshes
    m1 = simnibs.read_msh(args.mesh1)
    m2 = simnibs.read_msh(args.mesh2)
    if is_mti:
        m3 = simnibs.read_msh(m3_path)
        m4 = simnibs.read_msh(m4_path)

    # Use central surface mesh for vector positions (required)
    if not os.path.exists(args.central_surface):
        print(f"Error: Central surface mesh not found: {args.central_surface}")
        return 1
    
    try:
        central_surface_mesh = simnibs.read_msh(args.central_surface)
        print(f"Using central surface for vector positions: {args.central_surface}")
    except Exception as e:
        print(f"Error: Failed to load central surface mesh: {e}")
        return 1

    # Extract E fields from volumetric meshes
    for idx, m in enumerate([m1, m2] + ([m3, m4] if is_mti else []), start=1):
        if 'E' not in m.field:
            return 1

    # Use central surface face barycenters and interpolate E fields to them
    print("Using central surface face barycenters for vector positions...")
    positions = get_surface_face_barycenters(central_surface_mesh)
    print(f"Interpolating E fields to {len(positions)} surface face barycenters...")
    E1 = interpolate_field_to_surface_positions(m1, positions, 'E')
    E2 = interpolate_field_to_surface_positions(m2, positions, 'E')
    if is_mti:
        E3 = interpolate_field_to_surface_positions(m3, positions, 'E')
        E4 = interpolate_field_to_surface_positions(m4, positions, 'E')
    print(f"Interpolated E fields to {len(positions)} face barycenters")
    # Note: When using central surface, anchor='head' is recommended so tip is at barycenter
    # This ensures the arrow extends outward from the surface
    if args.anchor != 'head':
        print(f"Note: Using anchor='{args.anchor}' - for surface vectors, anchor='head' is recommended")

    # Align sizes
    if is_mti:
        min_len = min(len(positions), len(E1), len(E2), len(E3), len(E4))
    else:
        min_len = min(len(positions), len(E1), len(E2))
    positions = positions[:min_len]
    E1 = E1[:min_len]
    E2 = E2[:min_len]
    if is_mti:
        E3 = E3[:min_len]
        E4 = E4[:min_len]

    # Compute TI / mTI and optional E_sum
    if is_mti:
        TI = get_mTI_vectors(E1, E2, E3, E4)
        E_sum = (E1 + E2 + E3 + E4) if args.do_sum else None
    else:
        TI = get_TI_vectors(E1, E2)
        E_sum = (E1 + E2) if args.do_sum else None

    # Surface normals for TI_normal
    TI_normal = None
    if args.do_ti_normal:
        # Use central surface mesh for normals
        if central_surface_mesh is not None:
            # Get face normals from surface mesh (one normal per triangle)
            try:
                surf_normals = surface_normals_for_mesh(central_surface_mesh)
                
                # Filter to only triangular elements (elm_type == 2)
                triangular_elements = central_surface_mesh.elm.elm_type == 2
                if not np.any(triangular_elements):
                    triangular_elements = np.ones(len(central_surface_mesh.elm.node_number_list), dtype=bool)
                
                # Get normals for triangular elements only
                triangle_normals = surf_normals[triangular_elements]
                
                # Align with positions (one normal per face barycenter)
                if len(triangle_normals) > len(TI):
                    surf_normals = triangle_normals[:len(TI)]
                elif len(triangle_normals) < len(TI):
                    default_normal = np.array([0.0, 0.0, 1.0])
                    pad = np.tile(default_normal, (len(TI) - len(triangle_normals), 1))
                    surf_normals = np.vstack([triangle_normals, pad])
                else:
                    surf_normals = triangle_normals
            except Exception:
                # Fallback to TDCS mesh normals
                surf_normals = surface_normals_for_mesh(m1)
                if len(surf_normals) > len(TI):
                    surf_normals = surf_normals[:len(TI)]
                elif len(surf_normals) < len(TI):
                    default_normal = np.array([0.0, 0.0, 1.0])
                    pad = np.tile(default_normal, (len(TI) - len(surf_normals), 1))
                    surf_normals = np.vstack([surf_normals, pad])
        else:
            # Use TDCS mesh normals
            surf_normals = surface_normals_for_mesh(m1)
            # Align normals count with TI count
            if len(surf_normals) > len(TI):
                surf_normals = surf_normals[:len(TI)]
            elif len(surf_normals) < len(TI):
                default_normal = np.array([0.0, 0.0, 1.0])
                pad = np.tile(default_normal, (len(TI) - len(surf_normals), 1))
                surf_normals = np.vstack([surf_normals, pad])
        
        TI_normal = np.sum(TI * surf_normals, axis=1, keepdims=True) * surf_normals

    # Full magnitudes (pre-filter) for color normalization
    mag_E1_full = np.linalg.norm(E1, axis=1)
    mag_E2_full = np.linalg.norm(E2, axis=1)
    mag_TI_full = np.linalg.norm(TI, axis=1)
    mag_E_sum_full = np.linalg.norm(E_sum, axis=1) if E_sum is not None else np.zeros_like(mag_TI_full)
    mag_TI_normal_full = np.linalg.norm(TI_normal, axis=1) if TI_normal is not None else np.zeros_like(mag_TI_full)

    # Filter non-zero TI
    mag_TI = np.linalg.norm(TI, axis=1)
    nz = mag_TI > 1e-10
    positions = positions[nz]
    E1 = E1[nz]
    E2 = E2[nz]
    TI = TI[nz]
    mag_TI = mag_TI[nz]
    if E_sum is not None:
        E_sum = E_sum[nz]
    if TI_normal is not None:
        TI_normal = TI_normal[nz]

    # Top-percent filter by |TI|
    if args.top_percent is not None:
        pct = max(0.0, min(100.0, float(args.top_percent)))
        if pct > 0.0 and len(mag_TI) > 0:
            cutoff = np.percentile(mag_TI, 100.0 - pct)
            mask = mag_TI >= cutoff
            positions = positions[mask]
            E1 = E1[mask]
            E2 = E2[mask]
            TI = TI[mask]
            mag_TI = mag_TI[mask]
            if E_sum is not None:
                E_sum = E_sum[mask]
            if TI_normal is not None:
                TI_normal = TI_normal[mask]

    # Sampling
    np.random.seed(args.seed)
    if args.all_nodes:
        pos_s = positions
        E1_s = E1
        E2_s = E2
        TI_s = TI
        E_sum_s = E_sum if E_sum is not None else None
        TI_normal_s = TI_normal if TI_normal is not None else None
    else:
        sel_count = min(int(args.count), len(positions))
        if sel_count <= 0:
            return 1
        idx = np.random.choice(len(positions), sel_count, replace=False)

        pos_s = positions[idx]
        E1_s = E1[idx]
        E2_s = E2[idx]
        TI_s = TI[idx]
        E_sum_s = E_sum[idx] if E_sum is not None else None
        TI_normal_s = TI_normal[idx] if TI_normal is not None else None

    mag_E1_s = np.linalg.norm(E1_s, axis=1)
    mag_E2_s = np.linalg.norm(E2_s, axis=1)
    mag_TI_s = np.linalg.norm(TI_s, axis=1)
    mag_E_sum_s = np.linalg.norm(E_sum_s, axis=1) if E_sum_s is not None else None
    mag_TI_normal_s = np.linalg.norm(TI_normal_s, axis=1) if TI_normal_s is not None else None

    # Colors
    BLUE = (0, 0, 255, 255)
    GREEN = (0, 255, 0, 255)
    RED = (255, 0, 0, 255)
    YELLOW = (255, 255, 0, 255)
    CYAN = (0, 255, 255, 255)

    if args.color == 'magscale':
        # magscale across full magnitudes of all fields present
        stacks = [mag_E1_full, mag_E2_full, mag_TI_full]
        if E_sum is not None:
            stacks.append(mag_E_sum_full)
        if TI_normal is not None:
            stacks.append(mag_TI_normal_full)
        all_full = np.concatenate(stacks) if stacks else mag_TI_full
        ch1_colors = map_magnitude_to_colors_magscale(mag_E1_s, all_magnitudes_full=all_full,
                                                      blue_pct=args.blue_percentile,
                                                      green_pct=args.green_percentile,
                                                      red_pct=args.red_percentile)
        ch2_colors = map_magnitude_to_colors_magscale(mag_E2_s, all_magnitudes_full=all_full,
                                                      blue_pct=args.blue_percentile,
                                                      green_pct=args.green_percentile,
                                                      red_pct=args.red_percentile)
        ti_colors = map_magnitude_to_colors_magscale(mag_TI_s, all_magnitudes_full=all_full,
                                                     blue_pct=args.blue_percentile,
                                                     green_pct=args.green_percentile,
                                                     red_pct=args.red_percentile)
        sum_colors = (map_magnitude_to_colors_magscale(mag_E_sum_s, all_magnitudes_full=all_full,
                                                       blue_pct=args.blue_percentile,
                                                       green_pct=args.green_percentile,
                                                       red_pct=args.red_percentile)
                      if E_sum_s is not None else None)
        ti_normal_colors = (map_magnitude_to_colors_magscale(mag_TI_normal_s, all_magnitudes_full=all_full,
                                                             blue_pct=args.blue_percentile,
                                                             green_pct=args.green_percentile,
                                                             red_pct=args.red_percentile)
                            if TI_normal_s is not None else None)
    else:
        ch1_colors = np.tile(np.array(RED), (len(pos_s), 1))
        ch2_colors = np.tile(np.array(BLUE), (len(pos_s), 1))
        ti_colors = np.tile(np.array(GREEN), (len(pos_s), 1))
        sum_colors = np.tile(np.array(YELLOW), (len(pos_s), 1)) if E_sum_s is not None else None
        ti_normal_colors = np.tile(np.array(CYAN), (len(pos_s), 1)) if TI_normal_s is not None else None

    # Ensure output dir
    out_dir = os.path.dirname(args.output_prefix)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    print("Converting...")

    # Normalize user inputs so that 1.00 corresponds to the baseline visuals
    eff_length_scale = float(args.length_scale) * BASE_LENGTH_SCALE
    eff_vector_scale = float(args.vector_scale) * BASE_VECTOR_SCALE
    eff_vector_width = float(args.vector_width) * BASE_VECTOR_WIDTH
    eff_vector_length = float(args.vector_length) * BASE_VECTOR_LENGTH
    
    # Get output directory from prefix (prefix is now the output directory)
    output_dir = args.output_prefix if os.path.isdir(args.output_prefix) else (os.path.dirname(args.output_prefix) if os.path.dirname(args.output_prefix) else '.')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # Write per-type PLYs
    # CH1 and CH2 only if requested
    if args.export_ch1_ch2:
        write_ply_arrows(
            os.path.join(output_dir, "CH1.ply"), pos_s, E1_s, mag_E1_s, ch1_colors,
            length_mode=args.length_mode, length_scale=eff_length_scale, anchor=args.anchor,
            vector_scale=eff_vector_scale, base_length=eff_vector_length, shaft_width=eff_vector_width,
        )
        write_ply_arrows(
            os.path.join(output_dir, "CH2.ply"), pos_s, E2_s, mag_E2_s, ch2_colors,
            length_mode=args.length_mode, length_scale=eff_length_scale, anchor=args.anchor,
            vector_scale=eff_vector_scale, base_length=eff_vector_length, shaft_width=eff_vector_width,
        )

    # Always write TI/mTI
    if is_mti:
        write_ply_arrows(
            os.path.join(output_dir, "mTI.ply"), pos_s, TI_s, mag_TI_s, ti_colors,
            length_mode=args.length_mode, length_scale=eff_length_scale, anchor=args.anchor,
            vector_scale=eff_vector_scale, base_length=eff_vector_length, shaft_width=eff_vector_width,
        )
    else:
        write_ply_arrows(
            os.path.join(output_dir, "TI.ply"), pos_s, TI_s, mag_TI_s, ti_colors,
            length_mode=args.length_mode, length_scale=eff_length_scale, anchor=args.anchor,
            vector_scale=eff_vector_scale, base_length=eff_vector_length, shaft_width=eff_vector_width,
        )

    if E_sum_s is not None:
        write_ply_arrows(
            os.path.join(output_dir, "TI_sum.ply"), pos_s, E_sum_s, mag_E_sum_s, sum_colors,
            length_mode=args.length_mode, length_scale=eff_length_scale, anchor=args.anchor,
            vector_scale=eff_vector_scale, base_length=eff_vector_length, shaft_width=eff_vector_width,
        )

    if TI_normal_s is not None:
        write_ply_arrows(
            os.path.join(output_dir, "TI_normal.ply"), pos_s, TI_normal_s, mag_TI_normal_s, ti_normal_colors,
            length_mode=args.length_mode, length_scale=eff_length_scale, anchor=args.anchor,
            vector_scale=eff_vector_scale, base_length=eff_vector_length, shaft_width=eff_vector_width,
        )

    # Combined (optional): concat whatever types were written
    if args.combined:
        parts = [(pos_s, TI_s, mag_TI_s, ti_colors)]  # Always include TI
        if args.export_ch1_ch2:
            parts.append((pos_s, E1_s, mag_E1_s, ch1_colors))
            parts.append((pos_s, E2_s, mag_E2_s, ch2_colors))
        if E_sum_s is not None:
            parts.append((pos_s, E_sum_s, mag_E_sum_s, sum_colors))
        if TI_normal_s is not None:
            parts.append((pos_s, TI_normal_s, mag_TI_normal_s, ti_normal_colors))

        all_pos = np.concatenate([p[0] for p in parts], axis=0)
        all_vec = np.concatenate([p[1] for p in parts], axis=0)
        all_mag = np.concatenate([p[2] for p in parts], axis=0)
        all_col = np.concatenate([p[3] for p in parts], axis=0)

        write_ply_arrows(
            os.path.join(output_dir, "combined.ply"), all_pos, all_vec, all_mag, all_col,
            length_mode=args.length_mode, length_scale=eff_length_scale, anchor=args.anchor,
            vector_scale=eff_vector_scale, base_length=eff_vector_length, shaft_width=eff_vector_width,
        )

    # Count exported files
    exported_count = 1  # TI/mTI (always exported)
    if args.export_ch1_ch2:
        exported_count += 2  # CH1, CH2
    if E_sum_s is not None:
        exported_count += 1  # TI_sum
    if TI_normal_s is not None:
        exported_count += 1  # TI_normal
    if args.combined:
        exported_count += 1  # combined

    print(f"Converted {exported_count} vector PLY files.")
    print(f"Output: {output_dir}")
    print("Finishing...")
    return 0


if __name__ == '__main__':
    sys.exit(main())



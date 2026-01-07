#!/usr/bin/env simnibs_python
"""
TI-Toolbox 3D Exporter Shared Utilities

Common utilities and functions shared across all 3D export modules.
Provides:
- STL/PLY file I/O
- Mesh extraction and processing
- Electrode parsing and geometry
- Color mapping utilities
"""

import simnibs
import numpy as np

import os
import struct
import logging
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path

# Setup logger for module
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Simulation Config Reader
# ─────────────────────────────────────────────────────────────────────────────

def load_simulation_config(subject_id: str, simulation_name: str) -> Optional[Dict[str, Any]]:
    """Load simulation configuration from config.json file.

    This function reads the config.json file created during simulation
    to auto-populate visualization parameters.

    Args:
        subject_id: Subject ID
        simulation_name: Simulation/montage name

    Returns:
        Dictionary with simulation configuration, or None if not found
    """
   
    import json
    from tit.core import get_path_manager

    pm = get_path_manager()

    # Construct path to config file
    sim_dir = pm.path_optional("simulation", subject_id=subject_id, simulation_name=simulation_name)
    if not sim_dir:
        logger.warning(f"Simulation directory not found for {subject_id}/{simulation_name}")
        return None

    config_file = os.path.join(sim_dir, "documentation", "config.json")

    if not os.path.exists(config_file):
        logger.warning(f"Config file not found: {config_file}")
        logger.info("This simulation may have been run before config.json feature was added")
        return None

    # Read config file
    with open(config_file, 'r') as f:
        config = json.load(f)

    logger.info(f"Loaded simulation config from: {config_file}")
    logger.debug(f"Config: {config}")

    return config



def get_montage_from_config(subject_id: str, simulation_name: str) -> Optional[List[Tuple[str, str]]]:
    """Extract electrode montage/pairs from simulation config.

    Args:
        subject_id: Subject ID
        simulation_name: Simulation name

    Returns:
        List of electrode pairs, or None if not found
        Example: [("E1", "E2"), ("E3", "E4")]
    """
    config = load_simulation_config(subject_id, simulation_name)
    if not config:
        return None

    electrode_pairs = config.get('electrode_pairs', [])
    if not electrode_pairs:
        logger.warning(f"No electrode pairs found in config for {subject_id}/{simulation_name}")
        return None

    # Convert to list of tuples if needed
    if isinstance(electrode_pairs, list):
        return [tuple(pair) if isinstance(pair, list) else pair for pair in electrode_pairs]

    return None


def get_eeg_net_from_config(subject_id: str, simulation_name: str) -> Optional[str]:
    """Extract EEG net name from simulation config.

    Args:
        subject_id: Subject ID
        simulation_name: Simulation name

    Returns:
        EEG net filename (e.g., "EGI_template.csv"), or None if not found
    """
    config = load_simulation_config(subject_id, simulation_name)
    if not config:
        return None

    return config.get('eeg_net')


def write_binary_stl(vertices: np.ndarray, faces: np.ndarray, output_path: str, header_text: str = "TI-Toolbox Mesh"):
    """Write binary STL file from vertices and faces.

    Args:
        vertices: Array of [N, 3] vertex coordinates
        faces: Array of [M, 3] face indices
        output_path: Path to output STL file
        header_text: Header text for STL file
    """
    n_faces = len(faces)

    with open(output_path, 'wb') as f:
        # Write 80-byte header
        header = header_text.encode('ascii')
        header = header.ljust(80, b'\x00')
        f.write(header)

        # Write number of triangles (4 bytes, little-endian)
        f.write(struct.pack('<I', n_faces))

        # Write each triangle
        for face in faces:
            # Get triangle vertices
            v0 = vertices[face[0]]
            v1 = vertices[face[1]]
            v2 = vertices[face[2]]

            # Calculate normal vector
            edge1 = v1 - v0
            edge2 = v2 - v0
            normal = np.cross(edge1, edge2)
            normal_length = np.linalg.norm(normal)

            if normal_length > 1e-12:
                normal = normal / normal_length
            else:
                normal = np.array([0.0, 0.0, 1.0])  # Default normal

            # Write normal (3 floats, little-endian)
            f.write(struct.pack('<fff', normal[0], normal[1], normal[2]))

            # Write vertices (9 floats, little-endian)
            f.write(struct.pack('<fff', v0[0], v0[1], v0[2]))
            f.write(struct.pack('<fff', v1[0], v1[1], v1[2]))
            f.write(struct.pack('<fff', v2[0], v2[1], v2[2]))

            # Write attribute byte count (2 bytes, little-endian)
            f.write(struct.pack('<H', 0))


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
    roi_mesh = simnibs.read_msh(temp_mesh_path)

    # Replace the field with our ROI version
    roi_mesh.field[field_name].value = roi_field_values

    # Write the modified mesh
    roi_mesh.write(temp_mesh_path)

    # Create .opt file for Gmsh visualization
    from tit.core.mesh import create_mesh_opt_file

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


def extract_roi_region_no_zeros(mesh, roi_values, min_triangles=10, return_field_values=False):
    """Extract ROI region by removing only zero values (no threshold).

    Args:
        mesh: SimNIBS mesh object
        roi_values: Field values for ROI extraction
        min_triangles: Minimum number of triangles required
        return_field_values: Whether to return field values for vertices

    Returns:
        tuple: (vertices, faces) or (vertices, faces, field_values) depending on return_field_values
    """
    # Find nodes with non-zero values
    roi_nodes = np.where(roi_values > 0)[0]
    roi_node_set = set(roi_nodes)

    if len(roi_nodes) == 0:
        if return_field_values:
            return None, None, None
        else:
            return None, None

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
        if return_field_values:
            return None, None, None
        else:
            return None, None

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

    if return_field_values:
        # Extract field values for the unique vertices
        vertex_field_values = roi_values[unique_vertices]
        return vertices, remapped_triangles, vertex_field_values
    else:
        return vertices, remapped_triangles


def parse_electrode_csv(csv_path: str) -> List[Tuple[str, float, float, float]]:
    """Parse electrode CSV file to extract positions.

    Args:
        csv_path: Path to electrode CSV file

    Returns:
        List of (name, x, y, z) tuples
    """
    from simnibs.utils.csv_reader import read_csv_positions

    type_, coordinates, extra, name, extra_cols, header = read_csv_positions(csv_path)

    electrodes = []
    for t, coord, n in zip(type_, coordinates, name):
        if t in ['Electrode', 'ReferenceElectrode']:
            label = n if n else "Electrode"
            x, y, z = coord
            electrodes.append((label, x, y, z))

    return electrodes


def clear_blender_scene():
    """Clear all objects from the current Blender scene."""
    import bpy

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


def find_mesh_files(subject_dir: str, simulation_name: str) -> Tuple[str, str]:
    """Find the simulation mesh files (central surface and tetrahedral).

    Args:
        subject_dir: Subject directory path
        simulation_name: Simulation name

    Returns:
        Tuple of (central_mesh_path, tetrahedral_mesh_path)
    """
    sim_dir = os.path.join(subject_dir, simulation_name)

    # Look for central surface mesh
    central_mesh = None
    tetrahedral_mesh = None

    # Check in simulation directory for meshes
    sim_meshes_dir = os.path.join(sim_dir, "TI", "meshes")
    if os.path.exists(sim_meshes_dir):
        for file in os.listdir(sim_meshes_dir):
            if file.endswith("_central.msh"):
                central_mesh = os.path.join(sim_meshes_dir, file)
            elif file.endswith("_final.msh") or file.endswith("_T1.msh"):
                tetrahedral_mesh = os.path.join(sim_meshes_dir, file)

    # Fallback: look in main simulation directory
    if not central_mesh:
        for file in os.listdir(sim_dir):
            if file.endswith("_central.msh"):
                central_mesh = os.path.join(sim_dir, file)

    if not central_mesh:
        raise FileNotFoundError(f"Central surface mesh not found for {simulation_name}")

    return central_mesh, tetrahedral_mesh


def find_electrode_csv(subject_dir: str, simulation_name: str) -> str:
    """Find the electrode CSV file used in the simulation.

    Args:
        subject_dir: Subject directory path
        simulation_name: Simulation name

    Returns:
        Path to electrode CSV file
    """
    sim_dir = os.path.join(subject_dir, simulation_name)

    # Look in simulation directory for electrode montage file
    montage_dir = os.path.join(sim_dir, "montage")
    if os.path.exists(montage_dir):
        for file in os.listdir(montage_dir):
            if file.endswith('.csv'):
                return os.path.join(montage_dir, file)

    # Fallback: look for any CSV in simulation directory
    for file in os.listdir(sim_dir):
        if file.endswith('.csv'):
            return os.path.join(sim_dir, file)

    raise FileNotFoundError(f"Electrode CSV not found for simulation {simulation_name}")


def get_simulation_electrodes(subject_dir: str, simulation_name: str) -> List[str]:
    """Get the list of electrodes used in this simulation.

    Args:
        subject_dir: Subject directory path
        simulation_name: Simulation name

    Returns:
        List of electrode names used in the simulation
    """
    sim_dir = os.path.join(subject_dir, simulation_name)

    # Try to find montage file
    montage_file = None
    montage_dir = os.path.join(sim_dir, "montage")

    if os.path.exists(montage_dir):
        for file in os.listdir(montage_dir):
            if file.endswith('.json'):
                montage_file = os.path.join(montage_dir, file)
                break

    if not montage_file:
        # Look for montage file in main simulation directory
        for file in os.listdir(sim_dir):
            if file.endswith('.json') and 'montage' in file.lower():
                montage_file = os.path.join(sim_dir, file)
                break

    if montage_file:
        try:
            import json
            with open(montage_file, 'r') as f:
                montage_data = json.load(f)

            # Extract electrode names from montage
            used_electrodes = set()
            for pair in montage_data.get('pairs', []):
                used_electrodes.add(pair[0])
                used_electrodes.add(pair[1])

            return list(used_electrodes)
        except Exception:
            # Montage file parsing may fail - continue with fallback
            pass

    # Fallback: return empty list (all electrodes will be treated equally)
    return []


def create_electrode_geometry(x: float, y: float, z: float,
                             radius: float = 4.0, height: float = 8.0,
                             segments: int = 8) -> Tuple[List[List[float]], List[List[int]]]:
    """Create simple cylinder geometry for an electrode.

    Args:
        x, y, z: Position
        radius: Electrode radius in mm
        height: Electrode height in mm
        segments: Number of radial segments

    Returns:
        Tuple of (vertices, faces)
    """
    import math

    vertices = []
    faces = []

    # Convert mm to m (SimNIBS uses meters)
    radius = radius / 1000.0
    height = height / 1000.0

    # Create bottom and top circles
    for h in [0, height]:
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            vx = x + radius * math.cos(angle)
            vy = y + radius * math.sin(angle)
            vz = z + h
            vertices.append([vx, vy, vz])

    # Bottom center
    vertices.append([x, y, z])
    bottom_center_idx = len(vertices) - 1

    # Top center
    vertices.append([x, y, z + height])
    top_center_idx = len(vertices) - 1

    # Create side faces
    for i in range(segments):
        next_i = (i + 1) % segments

        # Bottom vertices
        b1 = i
        b2 = next_i

        # Top vertices
        t1 = i + segments
        t2 = next_i + segments

        # Side face
        faces.append([b1, b2, t2])
        faces.append([b1, t2, t1])

    # Create bottom cap
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append([bottom_center_idx, i, next_i])

    # Create top cap
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append([top_center_idx, segments + next_i, segments + i])

    return vertices, faces


# ─────────────────────────────────────────────────────────────────────────────
# PLY File I/O
# ─────────────────────────────────────────────────────────────────────────────

def write_ply_with_colors(vertices: np.ndarray, faces: np.ndarray, colors: np.ndarray,
                          output_path: str, field_name: str = "TI_max") -> None:
    """Write PLY file with vertex colors (ASCII format).

    Args:
        vertices: Array of [N, 3] vertex coordinates
        faces: Array of [M, 3] face indices
        colors: Array of [N, 3] RGB colors (0-255)
        output_path: Path to output PLY file
        field_name: Name of the field (for comment)
    """
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


def write_ply_with_scalars(vertices: np.ndarray, faces: np.ndarray, scalars: np.ndarray,
                           output_path: str, field_name: str = "TI_max") -> None:
    """Write PLY file with scalar field data (ASCII format).

    Args:
        vertices: Array of [N, 3] vertex coordinates
        faces: Array of [M, 3] face indices
        scalars: Array of [N] scalar values
        output_path: Path to output PLY file
        field_name: Name of the scalar field
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# Color Mapping Utilities
# ─────────────────────────────────────────────────────────────────────────────

def simple_colormap(field_values: np.ndarray, vmin: Optional[float] = None,
                   vmax: Optional[float] = None) -> np.ndarray:
    """Create simple blue-red colormap for field values.

    Args:
        field_values: Array of field values
        vmin: Minimum value for normalization (None = auto)
        vmax: Maximum value for normalization (None = auto)

    Returns:
        Array of RGB colors (0-255)
    """
    if vmin is None:
        vmin = np.nanmin(field_values)
    if vmax is None:
        vmax = np.nanmax(field_values)

    if vmax == vmin:
        colors = np.zeros((len(field_values), 3), dtype=np.uint8)
        colors[:, 2] = 255  # All blue
        return colors

    normalized = (field_values - vmin) / (vmax - vmin)
    normalized = np.clip(normalized, 0, 1)

    colors = np.zeros((len(field_values), 3), dtype=np.uint8)
    colors[:, 0] = (normalized * 255).astype(np.uint8)  # Red channel
    colors[:, 2] = ((1 - normalized) * 255).astype(np.uint8)  # Blue channel

    return colors


def field_to_colormap(field_values: np.ndarray, colormap: str = 'viridis',
                     vmin: Optional[float] = None, vmax: Optional[float] = None) -> np.ndarray:
    """Apply matplotlib colormap to field values.

    Args:
        field_values: Array of field values
        colormap: Matplotlib colormap name
        vmin: Minimum value for normalization (None = auto)
        vmax: Maximum value for normalization (None = auto)

    Returns:
        Array of RGB colors (0-255)
    """
    try:
        import matplotlib.cm as cm
    except ImportError:
        logger.warning("Matplotlib not available, using simple blue-red colormap")
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


# ─────────────────────────────────────────────────────────────────────────────
# Mesh Extraction Utilities
# ─────────────────────────────────────────────────────────────────────────────

def extract_scalp_from_msh(msh_path: str, skin_tag: int = 1005) -> Tuple[np.ndarray, np.ndarray]:
    """Extract scalp surface from SimNIBS .msh file.

    Args:
        msh_path: Path to SimNIBS mesh file
        skin_tag: SimNIBS tag for skin/scalp tissue (default: 1005)

    Returns:
        Tuple of (vertices, faces) as numpy arrays

    Raises:
        ValueError: If no skin triangles found
        FileNotFoundError: If mesh file not found
    """
    if not os.path.exists(msh_path):
        raise FileNotFoundError(f"Mesh file not found: {msh_path}")

    logger.info(f"Loading mesh: {msh_path}")
    mesh = simnibs.read_msh(msh_path)

    # Get triangular elements (type 2) with skin tag
    triangular = mesh.elm.elm_type == 2
    skin_mask = mesh.elm.tag1 == skin_tag
    skin_triangles_mask = triangular & skin_mask

    triangle_nodes = mesh.elm.node_number_list[skin_triangles_mask][:, :3]
    num_triangles = len(triangle_nodes)

    logger.info(f"Found {num_triangles} skin triangles (tag {skin_tag})")

    if num_triangles == 0:
        raise ValueError(f"No skin triangles found with tag {skin_tag}")

    # Create vertex mapping
    unique_nodes = np.unique(triangle_nodes.flatten())
    node_to_idx = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_nodes)}

    # Extract vertices (1-indexed to 0-indexed)
    vertices = mesh.nodes.node_coord[unique_nodes - 1]

    # Remap faces
    faces = np.array([[node_to_idx[n] for n in tri] for tri in triangle_nodes])

    logger.info(f"Extracted {len(vertices)} vertices, {len(faces)} faces")

    return vertices, faces


# ─────────────────────────────────────────────────────────────────────────────
# Mesh Processing Utilities
# ─────────────────────────────────────────────────────────────────────────────

def export_mesh_to_ply(mesh, ply_path: str, field_name: str, use_colors: bool = True,
                      colormap: str = 'viridis', field_range: Optional[Tuple[float, float]] = None) -> bool:
    """Export SimNIBS mesh to PLY format with optional field coloring.

    Args:
        mesh: SimNIBS mesh object
        ply_path: Output PLY file path
        field_name: Name of field to export
        use_colors: If True, export as vertex colors; if False, as scalars
        colormap: Matplotlib colormap name (if use_colors=True)
        field_range: Optional (vmin, vmax) tuple for color normalization

    Returns:
        True if successful, False otherwise
    """
    # Extract geometry from mesh
    vertices, faces, field_data = mesh_vertices_faces_and_field(mesh, field_name)

    if vertices is None or faces is None:
        logger.warning(f"Failed to extract geometry from mesh")
        return False

    if field_data is None:
        logger.warning(f"Field '{field_name}' not found in mesh, using default values")
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


def mesh_vertices_faces_and_field(mesh, field_name: str = "TI_max") -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """Extract vertices, faces, and field data from SimNIBS mesh.

    Args:
        mesh: SimNIBS mesh object
        field_name: Name of field to extract

    Returns:
        Tuple of (vertices, faces, field_data) or (None, None, None) on failure
    """
    # Get triangular elements
    triangles = mesh.elm[mesh.elm.elm_type == 2]
    if len(triangles) == 0:
        logger.warning("No triangular elements found in mesh")
        return None, None, None

    # Extract triangle nodes
    if hasattr(triangles, 'node_number_list'):
        triangle_nodes = triangles.node_number_list[:, :3] - 1  # Convert to 0-indexed
    else:
        triangle_nodes = triangles[:, :3] - 1

    # Create vertex mapping
    unique_nodes = np.unique(triangle_nodes.flatten())
    node_map = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_nodes)}

    # Extract vertices
    vertices = mesh.nodes.node_coord[unique_nodes]

    # Remap faces
    faces = np.array([[node_map[idx] for idx in tri] for tri in triangle_nodes], dtype=np.int32)

    # Extract field data
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

    # Also check mesh.field if nodedata not found
    if field_data is None and hasattr(mesh, 'field') and field_name in mesh.field:
        field_full = mesh.field[field_name].value
        field_data = field_full[unique_nodes]

    return vertices, faces, field_data

#!/usr/bin/env simnibs_python
"""
TI-Toolbox 3D Exporter Shared Utilities

Helpers shared by the 3D export modules:
- the simulation's recorded config (:func:`load_simulation_config`)
- ROI surface meshes (:func:`create_roi_mesh`, :func:`extract_roi_region_no_zeros`)
- the scalp surface of a head mesh (:func:`extract_scalp_from_msh`)

Low-level I/O (STL/PLY read/write, colormaps, vertex deduplication) lives
in :mod:`tit.blender.io`.
"""

import simnibs
import numpy as np

import os
import logging
from typing import Any

# Setup logger for module
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Simulation Config Reader
# ─────────────────────────────────────────────────────────────────────────────


def load_simulation_config(
    subject_id: str, simulation_name: str
) -> dict[str, Any] | None:
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
    from tit.paths import get_path_manager

    pm = get_path_manager()

    # Construct path to config file
    sim_dir = pm.simulation(subject_id, simulation_name)
    if not sim_dir:
        logger.warning(
            f"Simulation directory not found for {subject_id}/{simulation_name}"
        )
        return None

    config_file = os.path.join(sim_dir, "documentation", "config.json")

    if not os.path.exists(config_file):
        logger.warning(f"Config file not found: {config_file}")
        logger.info(
            "This simulation may have been run before config.json feature was added"
        )
        return None

    # Read config file
    with open(config_file, "r") as f:
        config = json.load(f)

    logger.info(f"Loaded simulation config from: {config_file}")
    logger.debug(f"Config: {config}")

    return config


def create_roi_mesh(
    surface_mesh, roi_mask, field_values, field_name, region_name, temp_dir
):
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
    from tit.tools.gmsh_opt import create_mesh_opt_file

    if len(roi_field_values[roi_mask]) > 0:
        max_value = np.max(roi_field_values[roi_mask])
    else:
        max_value = 1.0

    field_info = {
        "fields": [field_name],
        "max_values": {field_name: max_value},
        "field_type": "node",
    }
    create_mesh_opt_file(temp_mesh_path, field_info)

    return temp_mesh_path


def extract_roi_region_no_zeros(
    mesh, roi_values, min_triangles=10, return_field_values=False
):
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
    triangle_nodes = (
        mesh.elm.node_number_list[triangular_elements] - 1
    )  # Convert to 0-based

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
    vertex_mapping = {
        old_idx: new_idx for new_idx, old_idx in enumerate(unique_vertices)
    }

    # Remap triangle indices to new vertex indices
    remapped_triangles = np.array(
        [
            [vertex_mapping[face[0]], vertex_mapping[face[1]], vertex_mapping[face[2]]]
            for face in roi_triangles
        ]
    )

    # Extract vertex coordinates
    vertices = mesh.nodes.node_coord[unique_vertices]

    if return_field_values:
        # Extract field values for the unique vertices
        vertex_field_values = roi_values[unique_vertices]
        return vertices, remapped_triangles, vertex_field_values
    else:
        return vertices, remapped_triangles


# ─────────────────────────────────────────────────────────────────────────────
# Mesh Extraction Utilities
# ─────────────────────────────────────────────────────────────────────────────


def extract_scalp_from_msh(
    msh_path: str, skin_tag: int = 1005
) -> tuple[np.ndarray, np.ndarray]:
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

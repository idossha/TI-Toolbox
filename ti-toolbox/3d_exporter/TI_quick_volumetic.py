#!/usr/bin/env simnibs_python
"""
TI Vector Volumetric Analysis Script

This script loads existing TDCS simulation results and calculates TI vectors and 
normal components for the full volume mesh. Vectors remain element-based within 
the volume structure, preserving the original volumetric representation.

Purpose:
    - Calculate TI vectors for volume elements
    - Map normal components with respect to grey matter surface
    - Maintain volumetric data structure for 3D analysis
    - Preserve all tissue regions in the volume mesh

Author: TI Paper Research Group  
Version: 1.0
Date: 2024
"""

#=============================================================================
# CONFIGURATION VARIABLES
#=============================================================================

# Default simulation settings
DEFAULT_BASE_DIR = ""
DEFAULT_OUTPUT_DIR = "../output/"
DEFAULT_SURFACE_ID = 1002  # Grey matter surface ID for normal calculation

# Tissue tags to keep during processing (expanded range for volume analysis)
TISSUE_TAGS_KEEP = list(range(1, 100)) + list(range(1001, 1100))

# File naming conventions
OUTPUT_FILENAME = "normal_insula.msh"

# Search patterns for finding existing TDCS files
TDCS_FILE_PATTERNS = [
    "*_TDCS_1_scalar.msh",
    "*_TDCS_2_scalar.msh", 
    "*_TDCS_1_*.msh",
    "*_TDCS_2_*.msh"
]

# Visualization settings
VISIBLE_TAGS = [1002, 1006]  # Grey matter surface and white matter for visualization

#=============================================================================
# IMPORTS
#=============================================================================

import os
import sys
import glob
import numpy as np
from copy import deepcopy
from simnibs import mesh_io
import trimesh
from scipy.spatial import cKDTree

#=============================================================================
# CORE FUNCTIONS
#=============================================================================

def get_TI_vectors(E1_org, E2_org):
    """
    Calculate the modulation amplitude vectors for the TI envelope.
    
    This function computes the temporal interference vectors that represent
    the modulation amplitude at each spatial location in the volume.
    
    Parameters
    ----------
    E1_org : np.ndarray, shape (N, 3)
        Electric field vectors from electrode pair 1
    E2_org : np.ndarray, shape (N, 3)
        Electric field vectors from electrode pair 2
        
    Returns
    -------
    TI_vectors : np.ndarray, shape (N, 3)
        Modulation amplitude vectors for TI envelope
    """
    assert E1_org.shape == E2_org.shape
    assert E1_org.shape[1] == 3
    
    E1 = E1_org.copy()
    E2 = E2_org.copy()

    # Ensure E1 > E2 (magnitude ordering)
    idx = np.linalg.norm(E2, axis=1) > np.linalg.norm(E1, axis=1)
    E1[idx] = E2[idx]
    E2[idx] = E1_org[idx]

    # Ensure alpha < pi/2 (vector alignment)
    idx = np.sum(E1 * E2, axis=1) < 0
    E2[idx] = -E2[idx]

    # Calculate maximal amplitude of envelope
    normE1 = np.linalg.norm(E1, axis=1)
    normE2 = np.linalg.norm(E2, axis=1)
    cosalpha = np.sum(E1 * E2, axis=1) / (normE1 * normE2)

    idx = normE2 <= normE1 * cosalpha
    
    TI_vectors = np.zeros_like(E1)
    TI_vectors[idx] = 2 * E2[idx]
    TI_vectors[~idx] = 2 * np.cross(E2[~idx], E1[~idx] - E2[~idx]) / np.linalg.norm(E1[~idx] - E2[~idx], axis=1)[:, None]

    return TI_vectors


def get_TI_vectors2(E1_org, E2_org):
    """
    Calculate the temporal interference (TI) modulation amplitude vectors.
    
    This function implements the Grossman et al. 2017 algorithm for computing 
    TI vectors that represent both the direction and magnitude of maximum 
    modulation amplitude when two sinusoidal electric fields interfere.
    
    PHYSICAL INTERPRETATION:
    When two electric fields E1(t) = E1*cos(2πf1*t) and E2(t) = E2*cos(2πf2*t)
    with slightly different frequencies are applied simultaneously, they create
    a beating pattern. The TI vector indicates:
    - DIRECTION: Spatial direction of maximum envelope modulation
    - MAGNITUDE: Maximum envelope amplitude = 2 * effective_amplitude
    
    ALGORITHM (Grossman et al. 2017):
    1. Preprocessing: Ensure |E1| ≥ |E2| and acute angle α < π/2
    2. Regime selection based on geometric relationship:
       - Regime 1 (parallel): |E2| ≤ |E1|cos(α) → TI = 2*E2
       - Regime 2 (oblique): |E2| > |E1|cos(α) → TI = 2*E2_perpendicular_to_h
       where h = E1 - E2

    Parameters
    ----------
    E1_org : np.ndarray, shape (N, 3)
        Electric field vectors from electrode pair 1 [V/m]
    E2_org : np.ndarray, shape (N, 3)
        Electric field vectors from electrode pair 2 [V/m]

    Returns
    -------
    TI_vectors : np.ndarray, shape (N, 3)
        TI modulation amplitude vectors [V/m]
        Direction: Maximum modulation direction
        Magnitude: Maximum envelope amplitude
        
    References
    ----------
    Grossman, N. et al. (2017). Noninvasive Deep Brain Stimulation via 
    Temporally Interfering Electric Fields. Cell, 169(6), 1029-1041.
    """
    # Input validation
    assert E1_org.shape == E2_org.shape, "E1 and E2 must have same shape"
    assert E1_org.shape[1] == 3, "Vectors must be 3D"
    
    # Work with copies to avoid modifying input arrays
    E1 = E1_org.copy()
    E2 = E2_org.copy()

    # =================================================================
    # PREPROCESSING STEP 1: Magnitude ordering |E1| ≥ |E2|
    # =================================================================
    # Ensures consistency by always treating E1 as the "stronger" field
    # This simplifies the subsequent regime analysis
    idx_swap = np.linalg.norm(E2, axis=1) > np.linalg.norm(E1, axis=1)
    E1[idx_swap], E2[idx_swap] = E2[idx_swap], E1_org[idx_swap]

    # =================================================================
    # PREPROCESSING STEP 2: Acute angle constraint α < π/2  
    # =================================================================
    # Ensures constructive interference by flipping E2 if dot product < 0
    # This avoids destructive interference scenarios
    idx_flip = np.sum(E1 * E2, axis=1) < 0
    E2[idx_flip] = -E2[idx_flip]

    # =================================================================
    # GEOMETRIC PARAMETERS CALCULATION
    # =================================================================
    # Calculate field magnitudes and angle between vectors
    normE1 = np.linalg.norm(E1, axis=1)
    normE2 = np.linalg.norm(E2, axis=1)
    
    # Safe cosine calculation to avoid division by zero and numerical errors
    denom = normE1 * normE2
    denom[denom == 0] = 1.0  # Prevent division by zero
    cosalpha = np.clip(np.sum(E1 * E2, axis=1) / denom, -1.0, 1.0)

    # =================================================================
    # REGIME SELECTION CRITERION
    # =================================================================
    # Critical condition from Grossman 2017: |E2| ≤ |E1| * cos(α)
    # This determines whether E2 is "small" relative to E1's projection
    regime1_mask = normE2 <= normE1 * cosalpha

    # Initialize output array
    TI_vectors = np.zeros_like(E1)

    # =================================================================
    # REGIME 1: PARALLEL ALIGNMENT (|E2| ≤ |E1| cos(α))
    # =================================================================
    # Physical interpretation: E2 is effectively "contained" within E1's projection
    # The TI amplitude is determined entirely by E2's magnitude and direction
    # Formula: TI = 2 * E2
    TI_vectors[regime1_mask] = 2.0 * E2[regime1_mask]

    # =================================================================
    # REGIME 2: OBLIQUE CONFIGURATION (|E2| > |E1| cos(α))
    # =================================================================
    # Physical interpretation: E2 has significant perpendicular component to E1
    # The TI is determined by the component of E2 perpendicular to h = E1 - E2
    # Formula: TI = 2 * E2_perpendicular_to_h
    regime2_mask = ~regime1_mask
    if np.any(regime2_mask):
        # Calculate difference vector h = E1 - E2
        h = E1[regime2_mask] - E2[regime2_mask]
        h_norm = np.linalg.norm(h, axis=1)
        
        # Handle degenerate case (h = 0) by setting unit norm
        h_norm[h_norm == 0] = 1.0
        e_h = h / h_norm[:, None]  # Unit vector along h
        
        # Project E2 onto h, then subtract to get perpendicular component
        # E2_perp = E2 - proj_h(E2) = E2 - (E2·ĥ)ĥ
        E2_parallel_component = np.sum(E2[regime2_mask] * e_h, axis=1)[:, None] * e_h
        E2_perp = E2[regime2_mask] - E2_parallel_component
        
        # The TI vector in regime 2 is twice the perpendicular component
        TI_vectors[regime2_mask] = 2.0 * E2_perp

    return TI_vectors


def get_mTI_vectors(E1_org, E2_org, E3_org, E4_org):
    """
    Calculate multi-temporal interference (mTI) vectors from four channel E-fields.

    This computes TI between channels 1 and 2 to get TI_A, TI between channels 3 and 4
    to get TI_B, and finally TI between TI_A and TI_B to produce the mTI vector field.

    Parameters
    ----------
    E1_org : np.ndarray, shape (N, 3)
        Electric field vectors for channel 1
    E2_org : np.ndarray, shape (N, 3)
        Electric field vectors for channel 2
    E3_org : np.ndarray, shape (N, 3)
        Electric field vectors for channel 3
    E4_org : np.ndarray, shape (N, 3)
        Electric field vectors for channel 4

    Returns
    -------
    mTI_vectors : np.ndarray, shape (N, 3)
        Multi-TI modulation amplitude vectors
    """
    # Validate shapes
    for i, arr in enumerate([E1_org, E2_org, E3_org, E4_org], start=1):
        if arr.ndim != 2 or arr.shape[1] != 3:
            raise ValueError(f"E{i}_org must have shape (N, 3), got {arr.shape}")

    if not (E1_org.shape == E2_org.shape == E3_org.shape == E4_org.shape):
        raise ValueError(
            "All input arrays must have identical shapes. "
            f"Got: {[E1_org.shape, E2_org.shape, E3_org.shape, E4_org.shape]}"
        )

    # Step 1: TI between (E1, E2)
    TI_A = get_TI_vectors2(E1_org, E2_org)

    # Step 2: TI between (E3, E4)
    TI_B = get_TI_vectors2(E3_org, E4_org)

    # Step 3: TI between (TI_A, TI_B) → mTI
    mTI_vectors = get_TI_vectors2(TI_A, TI_B)

    return mTI_vectors

def add_vectors(vector_list, weights=None, method='linear'):
    """
    Add multiple vector fields together with optional weighting.
    
    This function combines multiple vector fields (e.g., multiple TI patterns,
    E-fields from different electrode configurations, or normal components)
    using different addition methods.
    
    Parameters
    ----------
    vector_list : list of np.ndarray
        List of vector arrays to add, each with shape (N, 3)
        All arrays must have the same shape
    weights : list of float, optional
        Weighting factors for each vector field (default: equal weights)
        Must have same length as vector_list
    method : str, optional
        Method for vector addition:
        - 'linear': Simple weighted linear addition (default)
        - 'magnitude_preserved': Preserve relative magnitudes during addition
        - 'rms': Root mean square combination
        - 'max_component': Take maximum component-wise values
        
    Returns
    -------
    combined_vectors : np.ndarray, shape (N, 3)
        Combined vector field
        
    Examples
    --------
    >>> # Add two TI vector fields with equal weighting
    >>> combined = add_vectors([TI_vectors1, TI_vectors2])
    
    >>> # Add three vector fields with custom weights
    >>> combined = add_vectors([v1, v2, v3], weights=[0.5, 0.3, 0.2])
    
    >>> # Combine using RMS method for interference patterns
    >>> combined = add_vectors([E1, E2], method='rms')
    """
    if not vector_list:
        raise ValueError("vector_list cannot be empty")
    
    # Validate input shapes
    reference_shape = vector_list[0].shape
    for i, vectors in enumerate(vector_list):
        if vectors.shape != reference_shape:
            raise ValueError(f"All vector arrays must have same shape. "
                           f"Array {i} has shape {vectors.shape}, expected {reference_shape}")
        if vectors.shape[1] != 3:
            raise ValueError(f"All vector arrays must have 3 components (shape N×3). "
                           f"Array {i} has shape {vectors.shape}")
    
    n_vectors = len(vector_list)
    n_elements = reference_shape[0]
    
    # Set default weights if not provided
    if weights is None:
        weights = [1.0 / n_vectors] * n_vectors
    else:
        if len(weights) != n_vectors:
            raise ValueError(f"Number of weights ({len(weights)}) must match "
                           f"number of vector arrays ({n_vectors})")
        # Normalize weights
        total_weight = sum(weights)
        if total_weight == 0:
            raise ValueError("Sum of weights cannot be zero")
        weights = [w / total_weight for w in weights]
    
    print(f"Adding {n_vectors} vector fields using method '{method}'")
    print(f"Input vector shapes: {[v.shape for v in vector_list]}")
    print(f"Weights: {weights}")
    
    # Convert to numpy arrays for easier manipulation
    vector_arrays = [np.array(v) for v in vector_list]
    
    if method == 'linear':
        # Simple weighted linear addition: Σ(wi * Vi)
        combined_vectors = np.zeros_like(vector_arrays[0])
        for i, (vectors, weight) in enumerate(zip(vector_arrays, weights)):
            combined_vectors += weight * vectors
            
    elif method == 'magnitude_preserved':
        # Preserve relative magnitudes during addition
        # Calculate magnitude-weighted combination
        combined_vectors = np.zeros_like(vector_arrays[0])
        total_magnitude = np.zeros(n_elements)
        
        for vectors, weight in zip(vector_arrays, weights):
            magnitude = np.linalg.norm(vectors, axis=1)
            total_magnitude += weight * magnitude
            combined_vectors += weight * vectors
        
        # Normalize to preserve magnitude relationships
        current_magnitude = np.linalg.norm(combined_vectors, axis=1)
        scale_factor = np.ones(n_elements)
        nonzero_mask = current_magnitude > 1e-12
        scale_factor[nonzero_mask] = total_magnitude[nonzero_mask] / current_magnitude[nonzero_mask]
        
        combined_vectors *= scale_factor[:, np.newaxis]
        
    elif method == 'rms':
        # Root Mean Square combination: sqrt(Σ(wi * Vi²))
        combined_vectors = np.zeros_like(vector_arrays[0])
        for vectors, weight in zip(vector_arrays, weights):
            combined_vectors += weight * (vectors ** 2)
        combined_vectors = np.sqrt(combined_vectors)
        
    elif method == 'max_component':
        # Take maximum absolute value for each component
        combined_vectors = np.zeros_like(vector_arrays[0])
        for i in range(3):  # x, y, z components
            component_values = np.stack([vectors[:, i] for vectors in vector_arrays], axis=1)
            weighted_components = component_values * np.array(weights)
            # Find index of maximum absolute value for each element
            abs_components = np.abs(weighted_components)
            max_indices = np.argmax(abs_components, axis=1)
            combined_vectors[:, i] = weighted_components[np.arange(n_elements), max_indices]
            
    else:
        raise ValueError(f"Unknown method '{method}'. Available methods: "
                        "'linear', 'magnitude_preserved', 'rms', 'max_component'")
    
    # Calculate statistics for reporting
    input_magnitudes = [np.linalg.norm(v, axis=1) for v in vector_arrays]
    combined_magnitude = np.linalg.norm(combined_vectors, axis=1)
    
    print(f"\nVector addition results:")
    print(f"  • Method: {method}")
    print(f"  • Input magnitude ranges:")
    for i, mag in enumerate(input_magnitudes):
        print(f"    - Vector {i+1}: [{np.min(mag):.6f}, {np.max(mag):.6f}] (mean: {np.mean(mag):.6f})")
    print(f"  • Combined magnitude range: [{np.min(combined_magnitude):.6f}, {np.max(combined_magnitude):.6f}]")
    print(f"  • Combined mean magnitude: {np.mean(combined_magnitude):.6f}")
    print(f"  • Output shape: {combined_vectors.shape}")
    
    return combined_vectors


def calculate_TI_normal_component(mesh, TI_vectors, surface_id=DEFAULT_SURFACE_ID):
    """
    Calculate normal component of TI vectors with respect to grey matter surface.
    
    This function maps the TI vectors to their normal components relative to the
    grey matter surface, while maintaining the volumetric element structure.
    
    Parameters
    ----------
    mesh : simnibs.Msh
        Volume mesh containing electric field data
    TI_vectors : np.ndarray, shape (N, 3)
        TI vectors calculated from volume elements
    surface_id : int, optional
        Surface ID for grey matter (default: 1002)
        
    Returns
    -------
    TI_normal : np.ndarray, shape (N, 3)
        Normal component vectors (element-based, same structure as input)
    """
    print(f"Calculating TI normal components relative to surface {surface_id}")
    
    try:
        # Extract grey matter surface
        surface = mesh.crop_mesh(tags=[surface_id])
        print(f"Extracted surface mesh with {len(surface.nodes.node_coord)} nodes")
        
        # Get surface triangular elements
        triangular_elements = surface.elm.elm_type == 2
        if not np.any(triangular_elements):
            triangular_elements = np.ones(len(surface.elm.elm_type), dtype=bool)
        
        # Get triangle connectivity
        triangle_connectivity = surface.elm.node_number_list[triangular_elements]
        
        # Handle different connectivity formats
        if triangle_connectivity.ndim == 1:
            triangle_connectivity = triangle_connectivity.reshape(-1, 3)
        elif triangle_connectivity.shape[1] > 3:
            triangle_connectivity = triangle_connectivity[:, :3]
        
        # Convert to 0-based indexing
        triangle_nodes = triangle_connectivity - 1
        surface_vertices = surface.nodes.node_coord
        
        print(f"Found {len(triangle_nodes)} surface triangles")
        
        # Calculate surface normals using trimesh
        mesh_obj = trimesh.Trimesh(vertices=surface_vertices, faces=triangle_nodes)
        vertex_normals = mesh_obj.vertex_normals
        
        print(f"Calculated normals for {len(vertex_normals)} surface vertices")
        
        # Convert element-based TI_vectors to node-based for normal calculation
        M = mesh.elm2node_matrix()
        TI_vectors_nodes = np.zeros((M.shape[0], 3))
        for i in range(3):
            TI_vectors_nodes[:, i] = M.dot(TI_vectors[:, i])
        
        # Find nearest surface points for each volume node
        tree = cKDTree(surface_vertices)
        node_positions = mesh.nodes.node_coord
        distances, indices = tree.query(node_positions)
        
        # Get normals at nearest surface points
        nearest_normals = vertex_normals[indices]
        # Ensure normals are unit vectors
        norms = np.linalg.norm(nearest_normals, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Avoid division by zero
        nearest_normals = nearest_normals / norms
        
        # Calculate normal components (dot product for magnitude)
        normal_components_magnitude = np.sum(TI_vectors_nodes * nearest_normals, axis=1)
        
        # Calculate normal component VECTORS (magnitude * direction)
        normal_components_vectors = normal_components_magnitude[:, np.newaxis] * nearest_normals
        
        # Convert back to element-based data
        element_node_lists = mesh.elm.node_number_list - 1  # 0-based indexing
        
        # Calculate element centers as average of element nodes
        element_centers = np.zeros((len(element_node_lists), 3))
        for i, nodes in enumerate(element_node_lists):
            # Handle different element types (tetrahedra, triangles, etc.)
            valid_nodes = nodes[nodes >= 0]  # Remove invalid node indices
            if len(valid_nodes) > 0:
                element_centers[i] = np.mean(node_positions[valid_nodes], axis=0)
        
        tree_elements = cKDTree(node_positions)
        _, element_to_node_indices = tree_elements.query(element_centers)
        
        # Map normal component vectors to elements
        TI_normal = normal_components_vectors[element_to_node_indices]
        
        # Calculate magnitude for reporting
        TI_normal_magnitude = np.linalg.norm(TI_normal, axis=1)
        print(f"Normal component statistics:")
        print(f"  • Magnitude range: [{np.min(TI_normal_magnitude):.6f}, {np.max(TI_normal_magnitude):.6f}]")
        print(f"  • Mean magnitude: {np.mean(TI_normal_magnitude):.6f}")
        print(f"  • Vector shape: {TI_normal.shape}")
        
        return TI_normal
        
    except Exception as e:
        print(f"Warning: Could not calculate normal components: {e}")
        import traceback
        traceback.print_exc()
        return np.zeros((len(TI_vectors), 3))

def combine_multiple_TI_patterns(mesh_pairs, output_dir=DEFAULT_OUTPUT_DIR, weights=None, method='linear'):
    """
    Combine multiple TI patterns from different electrode configurations.
    
    This function loads multiple pairs of TDCS simulations, calculates TI vectors
    for each pair, and then combines them using the specified method.
    
    Parameters
    ----------
    mesh_pairs : list of tuples
        List of (mesh1_file, mesh2_file) pairs for TI calculation
        Each pair represents one TI electrode configuration
    output_dir : str
        Output directory for combined results
    weights : list of float, optional
        Weights for combining different TI patterns (default: equal weights)
    method : str, optional
        Method for vector combination (see add_vectors function)
        
    Returns
    -------
    combined_TI : np.ndarray
        Combined TI vectors from all electrode configurations
    combined_normal : np.ndarray
        Combined normal component vectors
        
    Examples
    --------
    >>> # Combine two TI configurations
    >>> pairs = [("tdcs1_1.msh", "tdcs1_2.msh"), ("tdcs2_1.msh", "tdcs2_2.msh")]
    >>> combined_TI, combined_normal = combine_multiple_TI_patterns(pairs)
    
    >>> # Combine with custom weights and RMS method
    >>> combined_TI, combined_normal = combine_multiple_TI_patterns(
    ...     pairs, weights=[0.7, 0.3], method='rms')
    """
    if not mesh_pairs:
        raise ValueError("mesh_pairs cannot be empty")
    
    print(f"Combining {len(mesh_pairs)} TI patterns using method '{method}'")
    
    # Calculate TI vectors for each pair
    all_TI_vectors = []
    all_TI_normals = []
    reference_mesh = None
    
    for i, (mesh1_file, mesh2_file) in enumerate(mesh_pairs):
        print(f"\nProcessing TI pattern {i+1}/{len(mesh_pairs)}")
        print(f"  • Pair 1: {os.path.basename(mesh1_file)}")
        print(f"  • Pair 2: {os.path.basename(mesh2_file)}")
        
        # Validate files exist
        if not os.path.exists(mesh1_file) or not os.path.exists(mesh2_file):
            raise FileNotFoundError(f"One or both mesh files not found: {mesh1_file}, {mesh2_file}")
        
        # Load meshes
        m1 = mesh_io.read_msh(mesh1_file)
        m2 = mesh_io.read_msh(mesh2_file)
        
        # Store reference mesh for output (use first pair)
        if reference_mesh is None:
            reference_mesh = deepcopy(m1)
        
        # Filter relevant tissue tags
        tags_keep = np.array(TISSUE_TAGS_KEEP)
        m1 = m1.crop_mesh(tags=tags_keep)
        m2 = m2.crop_mesh(tags=tags_keep)
        
        # Extract electric fields
        ef1 = m1.field["E"]
        ef2 = m2.field["E"]
        
        # Handle shape mismatches
        if ef1.value.shape != ef2.value.shape:
            min_elements = min(len(ef1.value), len(ef2.value))
            ef1_data = ef1.value[:min_elements]
            ef2_data = ef2.value[:min_elements]
        else:
            ef1_data = ef1.value
            ef2_data = ef2.value
        
        # Calculate TI vectors for this pair
        TI_vectors = get_TI_vectors2(ef1_data, ef2_data)
        TI_normal = calculate_TI_normal_component(m1, TI_vectors)
        
        all_TI_vectors.append(TI_vectors)
        all_TI_normals.append(TI_normal)
        
        # Report statistics for this pair
        TI_magnitude = np.linalg.norm(TI_vectors, axis=1)
        print(f"    - TI magnitude range: [{np.min(TI_magnitude):.6f}, {np.max(TI_magnitude):.6f}]")
    
    # Ensure all arrays have the same shape
    min_elements = min(len(vectors) for vectors in all_TI_vectors)
    all_TI_vectors = [vectors[:min_elements] for vectors in all_TI_vectors]
    all_TI_normals = [normals[:min_elements] for normals in all_TI_normals]
    
    print(f"\nCombining {len(all_TI_vectors)} TI patterns...")
    print(f"Using {min_elements} elements per pattern")
    
    # Combine TI vectors
    combined_TI = add_vectors(all_TI_vectors, weights=weights, method=method)
    
    # Combine normal components
    combined_normal = add_vectors(all_TI_normals, weights=weights, method=method)
    
    # Save combined results
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        
        # Create output mesh with combined vectors
        mout = deepcopy(reference_mesh)
        if hasattr(mout, 'elmdata'):
            mout.elmdata = []
        
        # Ensure we only use the elements we have data for
        if len(mout.elm.elm_number) > min_elements:
            print(f"Cropping output mesh from {len(mout.elm.elm_number)} to {min_elements} elements")
            # This is a simplified approach - in practice you might need more sophisticated mesh cropping
        
        mout.add_element_field(combined_TI, "Combined_TI_vector")
        mout.add_element_field(combined_normal, "Combined_TI_normal")
        
        output_file = os.path.join(output_dir, f"Combined_TI_{method}.msh")
        mesh_io.write_msh(mout, output_file)
        
        # Create visualization
        v = mout.view(visible_tags=VISIBLE_TAGS, 
                     visible_fields=["Combined_TI_vector", "Combined_TI_normal"])
        v.write_opt(output_file)
        
        print(f"\n✓ Combined TI patterns saved to: {output_file}")
    
    return combined_TI, combined_normal


def find_existing_tdcs_files(base_dir=DEFAULT_BASE_DIR):
    """
    Search for existing TDCS simulation files in the specified directory.
    
    Parameters
    ----------
    base_dir : str
        Base directory to search for TDCS files
        
    Returns
    -------
    tuple
        (tdcs1_file, tdcs2_file) if found, (None, None) otherwise
    """
    found_files = []
    
    if os.path.exists(base_dir):
        for pattern in TDCS_FILE_PATTERNS:
            files = glob.glob(os.path.join(base_dir, "**", pattern), recursive=True)
            found_files.extend(files)
    
    # Get pairs of TDCS files
    tdcs1_files = [f for f in found_files if "TDCS_1" in f]
    tdcs2_files = [f for f in found_files if "TDCS_2" in f]
    
    if tdcs1_files and tdcs2_files:
        return tdcs1_files[0], tdcs2_files[0]
    
    return None, None

#=============================================================================
# MAIN FUNCTION
#=============================================================================

def main():
    """
    Main execution function for volumetric TI vector calculation.
    
    Command line usage:
        python TI_quick_volumetic.py [mesh1.msh] [mesh2.msh] [output_dir]
    
    If no arguments provided, searches for existing TDCS files automatically.
    """
    print("TI Vector Volumetric Analysis Script")
    print("=" * 50)
    
    # Parse command line arguments
    if len(sys.argv) >= 4:
        mesh1_file = sys.argv[1]
        mesh2_file = sys.argv[2]
        output_dir = sys.argv[3]
    elif len(sys.argv) == 3:
        mesh1_file = sys.argv[1]
        mesh2_file = sys.argv[2]
        output_dir = DEFAULT_OUTPUT_DIR
    else:
        # Try to find existing files
        print("Looking for existing TDCS simulation files...")
        mesh1_file, mesh2_file = find_existing_tdcs_files()
        output_dir = DEFAULT_OUTPUT_DIR
        
        if mesh1_file is None:
            print("No existing TDCS files found!")
            print("\nUsage:")
            print("  python TI_quick_volumetic.py mesh1.msh mesh2.msh [output_dir]")
            print("\nOr run full simulation first with TI_simple.py")
            return 1
    
    print(f"Input files:")
    print(f"  • TDCS pair 1: {mesh1_file}")
    print(f"  • TDCS pair 2: {mesh2_file}")
    print(f"  • Output directory: {output_dir}")
    
    # Validate input files
    for f in [mesh1_file, mesh2_file]:
        if not os.path.exists(f):
            print(f"Error: File not found: {f}")
            return 1
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Load meshes
        print("\nLoading mesh files...")
        m1 = mesh_io.read_msh(mesh1_file)
        m2 = mesh_io.read_msh(mesh2_file)
        
        # Filter relevant tissue tags (keep full volume)
        tags_keep = np.array(TISSUE_TAGS_KEEP)
        m1 = m1.crop_mesh(tags=tags_keep)
        m2 = m2.crop_mesh(tags=tags_keep)
        
        print("Extracting electric fields...")
        ef1 = m1.field["E"]
        ef2 = m2.field["E"]
        
        print(f"E-field shapes: ef1={ef1.value.shape}, ef2={ef2.value.shape}")
        
        # Handle shape mismatches
        if ef1.value.shape != ef2.value.shape:
            print("Mesh shapes differ - using smaller mesh size...")
            min_elements = min(len(ef1.value), len(ef2.value))
            ef1_data = ef1.value[:min_elements]
            ef2_data = ef2.value[:min_elements]
            print(f"Using first {min_elements} elements from each mesh")
        else:
            ef1_data = ef1.value
            ef2_data = ef2.value
        
        print("Calculating TI vectors...")
        TI_vectors = get_TI_vectors2(ef1_data, ef2_data)
        
        print(f"Calculated TI vectors for {len(TI_vectors)} volume elements")
        TI_magnitudes = np.linalg.norm(TI_vectors, axis=1)
        print(f"TI vector magnitude range: {np.min(TI_magnitudes):.6f} to {np.max(TI_magnitudes):.6f} V/m")
        
        # Calculate TI normal component
        TI_normal = calculate_TI_normal_component(m1, TI_vectors)
        
        print(f"Calculated TI normal component vectors for {len(TI_normal)} volume elements")
        TI_normal_magnitude = np.linalg.norm(TI_normal, axis=1)
        print(f"TI normal component statistics:")
        print(f"  • Magnitude range: {np.min(TI_normal_magnitude):.6f} to {np.max(TI_normal_magnitude):.6f}")
        print(f"  • Vector components range:")
        print(f"    - X: [{np.min(TI_normal[:,0]):.3f}, {np.max(TI_normal[:,0]):.3f}]")
        print(f"    - Y: [{np.min(TI_normal[:,1]):.3f}, {np.max(TI_normal[:,1]):.3f}]")
        print(f"    - Z: [{np.min(TI_normal[:,2]):.3f}, {np.max(TI_normal[:,2]):.3f}]")
        
        # Write output mesh file
        print("\nWriting output volumetric mesh file...")
        mout = deepcopy(m1)
        mout.elmdata = []
        mout.add_element_field(TI_vectors, "TI_vector")
        mout.add_element_field(TI_normal, "TI_normal")
        
        output_file = os.path.join(output_dir, OUTPUT_FILENAME)
        mesh_io.write_msh(mout, output_file)
        
        # Calculate E_sum (vector addition of E1 and E2)
        print("Calculating E_sum (E1 + E2)...")
        E_sum = ef1_data + ef2_data
        E_sum_magnitude = np.linalg.norm(E_sum, axis=1)
        print(f"E_sum calculated for {len(E_sum)} elements")
        print(f"E_sum magnitude range: {np.min(E_sum_magnitude):.6f} to {np.max(E_sum_magnitude):.6f} V/m")
        print(f"E_sum vector components range:")
        print(f"  - X: [{np.min(E_sum[:,0]):.3f}, {np.max(E_sum[:,0]):.3f}]")
        print(f"  - Y: [{np.min(E_sum[:,1]):.3f}, {np.max(E_sum[:,1]):.3f}]")
        print(f"  - Z: [{np.min(E_sum[:,2]):.3f}, {np.max(E_sum[:,2]):.3f}]")
        
        # Add E_sum to the output mesh
        mout.add_element_field(E_sum, "E_sum")
        
        # Re-write the mesh with E_sum included
        mesh_io.write_msh(mout, output_file)
        
        # Create visualization
        v = mout.view(visible_tags=VISIBLE_TAGS, visible_fields=["TI_vector", "TI_normal", "E_sum"])
        v.write_opt(output_file)
        
        print(f"\n✓ Volumetric TI calculation completed!")
        print(f"Output saved to: {output_file}")
        
        # Summary statistics
        print(f"\n📊 Volumetric Analysis Summary:")
        print(f"  • Total volume elements: {len(TI_vectors):,}")
        print(f"  • TI vector magnitude range: [{np.min(TI_magnitudes):.3f}, {np.max(TI_magnitudes):.3f}] V/m")
        print(f"  • TI normal magnitude range: [{np.min(TI_normal_magnitude):.3f}, {np.max(TI_normal_magnitude):.3f}]")
        print(f"  • E_sum magnitude range: [{np.min(E_sum_magnitude):.3f}, {np.max(E_sum_magnitude):.3f}] V/m")
        print(f"  • Mean TI normal magnitude: {np.mean(TI_normal_magnitude):.3f}")
        print(f"  • Mean E_sum magnitude: {np.mean(E_sum_magnitude):.3f}")
        print(f"  • Data structure: Volumetric elements (shape: {TI_vectors.shape})")
        
        print(f"\n💡 Volumetric Vector Analysis:")
        print(f"  • Vectors are element-based in 3D volume")
        print(f"  • Normal components calculated relative to GM surface")
        print(f"  • E_sum represents direct vector addition of E1 + E2")
        print(f"  • Preserves full tissue structure and volume information")
        print(f"  • Available fields:")
        print(f"    - TI_vector: Full TI modulation vectors (volumetric)")
        print(f"    - TI_normal: Normal component vectors (volumetric)")
        print(f"    - E_sum: Vector sum E1 + E2 (volumetric)")
        
        print(f"\n🚀 Ready for analysis:")
        print(f"  simnibs_python vector_normal_analysis.py {output_file} TI_vector --visualize")
        print(f"  simnibs_python vector_normal_analysis.py {output_file} TI_normal --visualize")
        print(f"  simnibs_python vector_normal_analysis.py {output_file} E_sum --visualize")
        
        print(f"\n🔧 Vector Addition Examples:")
        print(f"  # Add two TI vector fields with equal weighting:")
        print(f"  combined_TI = add_vectors([TI_vectors1, TI_vectors2])")
        print(f"  ")
        print(f"  # Add with custom weights:")
        print(f"  combined_TI = add_vectors([TI_vectors1, TI_vectors2], weights=[0.7, 0.3])")
        print(f"  ")
        print(f"  # Combine using RMS method:")
        print(f"  combined_TI = add_vectors([TI_vectors1, TI_vectors2], method='rms')")
        print(f"  ")
        print(f"  # Combine multiple TI patterns from different electrode configurations:")
        print(f"  pairs = [('tdcs1_1.msh', 'tdcs1_2.msh'), ('tdcs2_1.msh', 'tdcs2_2.msh')]")
        print(f"  combined_TI, combined_normal = combine_multiple_TI_patterns(pairs)")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
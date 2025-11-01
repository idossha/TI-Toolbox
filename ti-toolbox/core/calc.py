#!/usr/bin/env simnibs_python
"""
Shared TI Field Calculation Utilities
Used by both ex-search and MOVEA optimization tools
"""

import numpy as np


def get_TI_vectors(E1_org, E2_org):
    """Calculate modulation amplitude vectors for the TI envelope"""
    assert E1_org.shape == E2_org.shape and E1_org.shape[1] == 3
    
    E1, E2 = E1_org.copy(), E2_org.copy()
    
    # Ensure E1>E2
    idx = np.linalg.norm(E2, axis=1) > np.linalg.norm(E1, axis=1)
    E1[idx], E2[idx] = E2[idx], E1_org[idx]
    
    # Ensure alpha < pi/2
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

def envelope(e1, e2):
    """
    TI envelope calculation using geometric method
    
    Args:
        e1: Electric field from pair 1 [n_voxels, 3] in V/m
        e2: Electric field from pair 2 [n_voxels, 3] in V/m
    
    Returns:
        envelope: TI envelope amplitude [n_voxels] in V/m
    """
    # Calculate magnitudes
    norm_e1 = np.linalg.norm(e1, axis=1)
    norm_e2 = np.linalg.norm(e2, axis=1)
    
    # Calculate dot product
    dot_product = np.einsum('ij,ij->i', e1, e2)
    
    # Avoid division by zero
    valid = (norm_e1 > 1e-10) & (norm_e2 > 1e-10)
    cos_angle = np.zeros(len(e1))
    cos_angle[valid] = dot_product[valid] / (norm_e1[valid] * norm_e2[valid])
    cos_angle = np.clip(cos_angle, -1, 1)
    
    # Flip e1 if angle > 90 degrees
    mask = cos_angle < 0
    e1_corrected = e1.copy()
    e1_corrected[mask] = -e1_corrected[mask]
    cos_angle[mask] = -cos_angle[mask]
    
    # Check for equal vectors
    equal_vectors = np.all(np.abs(e1_corrected - e2) < 1e-10, axis=1)
    
    # Initialize envelope
    envelope_result = np.zeros(len(e1))
    
    # Case 1: Equal vectors -> 2 * magnitude
    envelope_result[equal_vectors] = 2 * norm_e1[equal_vectors]
    
    # Case 2: e2 < e1 AND e2 < e1 * cos_angle -> envelope = 2 * e2
    not_equal = ~equal_vectors
    mask2 = not_equal & (norm_e2 < norm_e1)
    mask3 = not_equal & (norm_e1 < norm_e2 * cos_angle)
    both_conditions = mask2 & mask3
    envelope_result[both_conditions] = 2 * norm_e2[both_conditions]
    
    # Case 3: e2 < e1 but NOT (e1 < e2 * cos) -> use cross product
    mask2_not3 = mask2 & ~mask3
    if np.any(mask2_not3):
        cross_prod = np.cross(e2[mask2_not3], e1_corrected[mask2_not3] - e2[mask2_not3])
        diff_norm = np.linalg.norm(e1_corrected[mask2_not3] - e2[mask2_not3], axis=1)
        valid_diff = diff_norm > 1e-10
        temp_env = np.zeros(np.sum(mask2_not3))
        temp_env[valid_diff] = 2 * np.linalg.norm(cross_prod[valid_diff], axis=1) / diff_norm[valid_diff]
        envelope_result[mask2_not3] = temp_env
    
    # Case 4: e1 < e2 AND e1 < e2 * cos_angle -> envelope = 2 * e1
    mask5 = not_equal & (norm_e1 < norm_e2)
    mask4 = not_equal & (norm_e2 < norm_e1 * cos_angle)
    both_conditions2 = mask5 & mask4
    envelope_result[both_conditions2] = 2 * norm_e1[both_conditions2]
    
    # Case 5: e1 < e2 but NOT (e2 < e1 * cos) -> use cross product
    mask5_not4 = mask5 & ~mask4
    if np.any(mask5_not4):
        cross_prod = np.cross(e1_corrected[mask5_not4], e2[mask5_not4] - e1_corrected[mask5_not4])
        diff_norm = np.linalg.norm(e2[mask5_not4] - e1_corrected[mask5_not4], axis=1)
        valid_diff = diff_norm > 1e-10
        temp_env = np.zeros(np.sum(mask5_not4))
        temp_env[valid_diff] = 2 * np.linalg.norm(cross_prod[valid_diff], axis=1) / diff_norm[valid_diff]
        envelope_result[mask5_not4] = temp_env
    
    return envelope_result


def calculate_ti_field_from_leadfield(leadfield, stim1, stim2, target_indices=None):
    """
    Calculate TI field from leadfield matrix and stimulation patterns
    
    Args:
        leadfield: Leadfield matrix [n_electrodes, n_elements, 3] in mV/mm (from SimNIBS)
        stim1: Stimulation pattern 1 [n_electrodes] in mA
        stim2: Stimulation pattern 2 [n_electrodes] in mA
        target_indices: Optional element indices to calculate only for subset (for speed)
    
    Returns:
        ti_field: TI field magnitude [n_elements] or [n_target_elements] in V/m
    """
    # Calculate electric fields from each stimulation pattern
    # E = leadfield @ stim gives E-field at each element (shape: [n_elements, 3])
    # leadfield is in mV/mm, divide by 1000 to convert to V/m
    E1 = np.einsum('ijk,i->jk', leadfield, stim1) / 1000.0
    E2 = np.einsum('ijk,i->jk', leadfield, stim2) / 1000.0
    
    # If target indices specified, only calculate for those elements
    if target_indices is not None:
        E1 = E1[target_indices]
        E2 = E2[target_indices]
    
    # Calculate TI envelope
    ti_field = envelope(E1, E2)
    
    return ti_field

def create_stim_patterns(electrode_names, e1_plus, e1_minus, e2_plus, e2_minus, intensity=0.001):
    """
    Create bipolar stimulation patterns from electrode lists
    
    Args:
        electrode_names: List of all electrode names in leadfield
        e1_plus: List of E1+ electrode names
        e1_minus: List of E1- electrode names
        e2_plus: List of E2+ electrode names
        e2_minus: List of E2- electrode names
        intensity: Stimulation intensity in Amperes (default: 0.001 = 1mA)
    
    Returns:
        stim1: Stimulation pattern 1 [n_electrodes] in mA
        stim2: Stimulation pattern 2 [n_electrodes] in mA
    """
    n_electrodes = len(electrode_names)
    stim1 = np.zeros(n_electrodes)
    stim2 = np.zeros(n_electrodes)
    
    # Convert intensity to mA for consistency
    intensity_ma = intensity * 1000.0
    
    # Create electrode name to index mapping
    electrode_map = {name: idx for idx, name in enumerate(electrode_names)}
    
    # Set E1+ electrodes
    for elec in e1_plus:
        if elec in electrode_map:
            stim1[electrode_map[elec]] = intensity_ma / len(e1_plus)
    
    # Set E1- electrodes
    for elec in e1_minus:
        if elec in electrode_map:
            stim1[electrode_map[elec]] = -intensity_ma / len(e1_minus)
    
    # Set E2+ electrodes
    for elec in e2_plus:
        if elec in electrode_map:
            stim2[electrode_map[elec]] = intensity_ma / len(e2_plus)
    
    # Set E2- electrodes
    for elec in e2_minus:
        if elec in electrode_map:
            stim2[electrode_map[elec]] = -intensity_ma / len(e2_minus)
    
    return stim1, stim2

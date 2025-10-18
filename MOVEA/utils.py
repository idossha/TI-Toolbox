"""
Utility functions for MOVEA TI optimization
"""

import numpy as np


def calculate_ti_field(leadfield_matrix, stim1, stim2, target_indices=None):
    """
    Calculate TI field from two stimulation patterns using leadfield matrix
    Uses the original MOVEA envelope calculation method
    
    Args:
        leadfield_matrix: Leadfield matrix [n_electrodes, n_voxels, 3] in mV/mm
        stim1: Stimulation pattern 1 [n_electrodes] in mA
        stim2: Stimulation pattern 2 [n_electrodes] in mA
        target_indices: Indices of target voxels (if None, calculate for all voxels)
    
    Returns:
        ti_field: TI field magnitude at each voxel [n_voxels or n_target_voxels] in V/m
    """
    # Calculate electric fields from each stimulation pattern
    # E = leadfield @ stim gives E-field at each voxel (shape: [n_voxels, 3])
    # leadfield is in mV/mm, divide by 1000 to convert to V/m
    E1 = np.einsum('ijk,i->jk', leadfield_matrix, stim1) / 1000.0
    E2 = np.einsum('ijk,i->jk', leadfield_matrix, stim2) / 1000.0
    
    # If target indices specified, only calculate for those voxels
    if target_indices is not None:
        E1 = E1[target_indices]
        E2 = E2[target_indices]
    
    # Calculate TI envelope using original MOVEA method
    ti_field = envelope(E1, E2)
    
    return ti_field


def envelope(e1, e2):
    """
    TI envelope calculation using geometric method
    From original MOVEA envelop() function (util.py line 46-71)
    
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
    envelope = np.zeros(len(e1))
    
    # Case 1: Equal vectors -> 2 * magnitude
    envelope[equal_vectors] = 2 * norm_e1[equal_vectors]
    
    # Case 2: e2 < e1 AND e2 < e1 * cos_angle -> envelope = 2 * e2
    not_equal = ~equal_vectors
    mask2 = not_equal & (norm_e2 < norm_e1)
    mask3 = not_equal & (norm_e1 < norm_e2 * cos_angle)
    both_conditions = mask2 & mask3
    envelope[both_conditions] = 2 * norm_e2[both_conditions]
    
    # Case 3: e2 < e1 but NOT (e1 < e2 * cos) -> use cross product
    mask2_not3 = mask2 & ~mask3
    if np.any(mask2_not3):
        cross_prod = np.cross(e2[mask2_not3], e1_corrected[mask2_not3] - e2[mask2_not3])
        diff_norm = np.linalg.norm(e1_corrected[mask2_not3] - e2[mask2_not3], axis=1)
        valid_diff = diff_norm > 1e-10
        temp_env = np.zeros(np.sum(mask2_not3))
        temp_env[valid_diff] = 2 * np.linalg.norm(cross_prod[valid_diff], axis=1) / diff_norm[valid_diff]
        envelope[mask2_not3] = temp_env
    
    # Case 4: e1 < e2 AND e1 < e2 * cos_angle -> envelope = 2 * e1
    mask5 = not_equal & (norm_e1 < norm_e2)
    mask4 = not_equal & (norm_e2 < norm_e1 * cos_angle)
    both_conditions2 = mask5 & mask4
    envelope[both_conditions2] = 2 * norm_e1[both_conditions2]
    
    # Case 5: e1 < e2 but NOT (e2 < e1 * cos) -> use cross product
    mask5_not4 = mask5 & ~mask4
    if np.any(mask5_not4):
        cross_prod = np.cross(e1_corrected[mask5_not4], e2[mask5_not4] - e1_corrected[mask5_not4])
        diff_norm = np.linalg.norm(e2[mask5_not4] - e1_corrected[mask5_not4], axis=1)
        valid_diff = diff_norm > 1e-10
        temp_env = np.zeros(np.sum(mask5_not4))
        temp_env[valid_diff] = 2 * np.linalg.norm(cross_prod[valid_diff], axis=1) / diff_norm[valid_diff]
        envelope[mask5_not4] = temp_env
    
    return envelope


def find_target_voxels(voxel_positions, target_mni, roi_radius_mm=10):
    """
    Find voxel indices within radius of target MNI coordinate
    
    Args:
        voxel_positions: Voxel MNI coordinates [n_voxels, 3]
        target_mni: Target MNI coordinate [x, y, z]
        roi_radius_mm: ROI radius in mm
    
    Returns:
        indices: Array of voxel indices within radius
    """
    target_mni = np.array(target_mni)
    distances = np.linalg.norm(voxel_positions - target_mni, axis=1)
    indices = np.where(distances <= roi_radius_mm)[0]
    return indices


def validate_ti_montage(electrode_indices):
    """
    Validate that a TI montage has 4 unique electrodes
    
    Args:
        electrode_indices: Array of 4 electrode indices [e1, e2, e3, e4]
    
    Returns:
        valid: True if montage is valid
    """
    if len(electrode_indices) != 4:
        return False
    
    # Check that all electrodes are unique
    if len(set(electrode_indices)) != 4:
        return False
    
    # Check that indices are non-negative
    if np.any(np.array(electrode_indices) < 0):
        return False
    
    return True


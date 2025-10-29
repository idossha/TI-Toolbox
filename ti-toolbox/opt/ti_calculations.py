#!/usr/bin/env python3
"""
Bridge module for TI calculations
Imports shared calculation utilities from core module and re-exports them
This maintains backward compatibility for opt scripts
"""

# Import calculation functions from core.calc
from core.calc import (
    get_TI_vectors,
    envelope,
    calculate_ti_field_from_leadfield,
    create_stim_patterns
)

# Import utility functions from core.utils
from core.utils import (
    find_sphere_element_indices as find_roi_element_indices,
    find_grey_matter_indices,
    calculate_roi_metrics
)

# Additional utility functions for optimization workflows
import numpy as np


def find_target_voxels(voxel_positions, center, radius):
    """
    Find voxel indices within a spherical ROI.
    Used by MOVEA-style optimization.
    
    Args:
        voxel_positions: Array of voxel positions [N, 3]
        center: Center coordinate [x, y, z]
        radius: Radius in mm
    
    Returns:
        Array of voxel indices within the sphere
    """
    center = np.array(center)
    distances = np.linalg.norm(voxel_positions - center, axis=1)
    return np.where(distances <= radius)[0]


def validate_ti_montage(electrodes, num_electrodes):
    """
    Validate TI montage electrode configuration.
    
    Args:
        electrodes: Array of 4 electrode indices
        num_electrodes: Total number of available electrodes
    
    Returns:
        bool: True if valid, False otherwise
    """
    if len(electrodes) != 4:
        return False
    if len(set(electrodes)) != 4:  # Check for duplicates
        return False
    if any(e < 0 or e >= num_electrodes for e in electrodes):
        return False
    return True


# Re-export all for convenience
__all__ = [
    'get_TI_vectors',
    'envelope',
    'calculate_ti_field_from_leadfield',
    'create_stim_patterns',
    'find_roi_element_indices',
    'find_grey_matter_indices',
    'calculate_roi_metrics',
    'find_target_voxels',
    'validate_ti_montage'
]


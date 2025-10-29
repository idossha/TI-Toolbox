"""
Utility functions for MOVEA TI optimization
Now imports from shared opt.ti_calculations module
"""

# Import all shared TI calculation utilities
from opt.ti_calculations import (
    envelope,
    calculate_ti_field_from_leadfield as calculate_ti_field,
    find_target_voxels,
    validate_ti_montage
)

# Re-export for backward compatibility
__all__ = [
    'envelope',
    'calculate_ti_field',
    'find_target_voxels',
    'validate_ti_montage'
]

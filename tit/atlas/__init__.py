"""Shared atlas module for TI-Toolbox.

Provides mesh (surface) and voxel (volumetric) atlas discovery,
region listing, and overlap analysis.
"""

from tit.atlas.constants import (
    BUILTIN_ATLASES,
    MNI_ATLAS_FILES,
    VOXEL_ATLASES,
    VOXEL_ATLAS_FILES,
)
from tit.atlas.mesh import MeshAtlasManager
from tit.atlas.overlap import atlas_overlap_analysis, check_and_resample_atlas
from tit.atlas.voxel import VoxelAtlasManager

__all__ = [
    "BUILTIN_ATLASES",
    "MNI_ATLAS_FILES",
    "VOXEL_ATLASES",
    "VOXEL_ATLAS_FILES",
    "MeshAtlasManager",
    "VoxelAtlasManager",
    "atlas_overlap_analysis",
    "check_and_resample_atlas",
]

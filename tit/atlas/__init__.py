"""Shared atlas module for TI-Toolbox.

Provides mesh (surface) and voxel (volumetric) atlas discovery,
region listing, and overlap analysis.
"""

from tit.atlas.constants import (
    BUILTIN_ATLASES,
    DEFAULT_MNI_ATLAS,
    MNI_ATLAS_DIR,
    MNI_ATLAS_FILES,
    MNI_TEMPLATE,
    VOXEL_ATLASES,
    VOXEL_ATLAS_FILES,
)
from tit.atlas.mesh import MeshAtlasManager


def __getattr__(name: str):
    if name in {"atlas_overlap_analysis", "check_and_resample_atlas"}:
        from tit.atlas import overlap

        return getattr(overlap, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


from tit.atlas.voxel import VoxelAtlasManager

__all__ = [
    "BUILTIN_ATLASES",
    "DEFAULT_MNI_ATLAS",
    "MNI_ATLAS_DIR",
    "MNI_ATLAS_FILES",
    "MNI_TEMPLATE",
    "VOXEL_ATLASES",
    "VOXEL_ATLAS_FILES",
    "MeshAtlasManager",
    "VoxelAtlasManager",
    "atlas_overlap_analysis",
    "check_and_resample_atlas",
]

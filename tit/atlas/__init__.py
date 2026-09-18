"""Shared atlas module for TI-Toolbox.

Provides mesh (surface) and voxel (volumetric) atlas discovery,
region listing, and overlap analysis.
"""

from tit.atlas.constants import (
    BUILTIN_ATLASES,
    MNI_ATLAS_DIR,
    MNI_TEMPLATE,
    VOXEL_ATLASES,
    VOXEL_ATLAS_FILES,
)
from tit.atlas.mesh import MeshAtlasManager
from tit.atlas.overlap import atlas_overlap_analysis, check_and_resample_atlas
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

# ``MNI_ATLAS_FILES``/``DEFAULT_MNI_ATLAS`` come from
# ``resources/atlas/manifest.json``. They are re-exported lazily rather than
# imported: reading the manifest is a filesystem access, and importing this
# package must not touch the filesystem (``dev/route_import_guard.py`` --
# every server route module imports ``tit.catalog``, which imports this).


def __getattr__(name):
    if name in ("MNI_ATLAS_FILES", "DEFAULT_MNI_ATLAS"):
        from tit.atlas import constants

        return getattr(constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

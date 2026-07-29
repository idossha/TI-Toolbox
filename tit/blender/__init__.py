"""Blender/SimNIBS 3D export utilities for TI-Toolbox.

This package generates publication-ready Blender scenes, vector-field
PLY arrow files, and atlas-labelled cortical region meshes from
SimNIBS simulation outputs.  It runs inside ``simnibs_python`` (which
bundles a headless Blender ``bpy``).

Modules
-------
config
    Dataclass configurations: `MontageConfig`, `VectorConfig`,
    `RegionConfig`.
montage_publication
    Build scalp + GM + electrode Blender scene for publication.
vector_field_exporter
    Export TI/mTI vector arrows as coloured PLY geometry.
region_exporter
    Export atlas-labelled cortical regions as STL or PLY meshes.
electrode_placement
    Place electrode objects on a scalp surface in Blender.
io
    Low-level binary STL / PLY read-write and colourmap utilities.
scene_setup
    Reusable Blender scene helpers (cameras, lights, materials).
utils
    Shared mesh extraction, electrode parsing, and config readers.

See Also
--------
tit.sim : Simulation pipeline that produces the input meshes.
tit.analyzer : Field analysis that consumes the exported surfaces.
"""

from tit.blender.config import (
    MontageConfig,
    VectorConfig,
    RegionConfig,
)
from tit.blender.montage_publication import (
    run_montage,
    MontageResult,
)
from tit.blender.vector_field_exporter import run_vectors
from tit.blender.region_exporter import run_regions

__all__ = [
    "MontageConfig",
    "VectorConfig",
    "RegionConfig",
    "run_montage",
    "MontageResult",
    "run_vectors",
    "run_regions",
]

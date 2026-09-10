"""Blender/SimNIBS 3D export utilities for TI-Toolbox.

This package generates publication-ready Blender scenes, vector-field
PLY arrow files, and atlas-labelled cortical region meshes from
SimNIBS simulation outputs.  Scientific preparation runs inside ``simnibs_python``; montage scene creation
runs in the standalone Blender background process.

Modules
-------
config
    Dataclass configurations: `MontageConfig`, `VectorConfig`,
    `RegionConfig`, `SubcorticalConfig`.
montage_publication
    Build scalp + GM + electrode Blender scene for publication.
vector_field_exporter
    Export TI/mTI vector arrows as coloured PLY geometry.
region_exporter
    Export atlas-labelled cortical regions as STL or PLY meshes.
subcortical_exporter
    Export sub-cortical structures from a labelled NIfTI as STL/MSH/PLY.
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

from importlib import import_module

# Rendering imports must never pull SimNIBS/NumPy2 into Blender's bundled Python.
_EXPORTS = {
    "MontageConfig": "config",
    "VectorConfig": "config",
    "RegionConfig": "config",
    "SubcorticalConfig": "config",
    "MontageResult": "montage_publication",
    "run_montage": "montage_publication",
    "run_vectors": "vector_field_exporter",
    "run_regions": "region_exporter",
    "run_subcortical": "subcortical_exporter",
}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{_EXPORTS[name]}"), name)
    globals()[name] = value
    return value

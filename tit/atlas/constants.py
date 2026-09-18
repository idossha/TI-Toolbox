"""Atlas constants shared across the TI-Toolbox."""

import os
from pathlib import Path

from tit.paths import resolve_resource_path

# Built-in mesh atlas names (always available via SimNIBS subject_atlas)
BUILTIN_ATLASES = ["DK40", "a2009s", "HCP_MMP1"]

# Voxel atlas files: filename → hemisphere ("both", "lh", or "rh").
# Labels file is always {stem}_labels.txt in the same directory (written by
# tit.atlas.segstats). Single canonical source used by analyzer, flex
# subcortical, and the NIfTI viewer.
#
# FastSurfer's own output ships both an .mgz and the .nii.gz copy
# tit.pre.fastsurfer writes beside it; readers that cannot open MGH pick the
# NIfTI. FreeSurfer lists retain the established names first, followed by
# the optional worker's segment_subregions default output names.
FASTSURFER_ATLASES = {
    "aparc.DKTatlas+aseg.deep.mgz": "both",
    "aparc.DKTatlas+aseg.deep.nii.gz": "both",
}

LEGACY_FREESURFER_ATLASES = {
    "aparc.DKTatlas+aseg.mgz": "both",
    "aparc.a2009s+aseg.mgz": "both",
    "lh.hippoAmygLabels-T1.v22.mgz": "lh",
    "rh.hippoAmygLabels-T1.v22.mgz": "rh",
    "ThalamicNuclei.v13.T1.mgz": "both",
}

FREESURFER_SUBREGION_ATLASES = {
    "lh.hippoAmygLabels.mgz": "lh",
    "rh.hippoAmygLabels.mgz": "rh",
    "ThalamicNuclei.mgz": "both",
}

VOXEL_ATLASES = {
    **FASTSURFER_ATLASES,
    **LEGACY_FREESURFER_ATLASES,
    **FREESURFER_SUBREGION_ATLASES,
}

# Flat lists for callers that only need filenames, in search order:
# FastSurfer first, then legacy FreeSurfer.
FASTSURFER_ATLAS_FILES = list(FASTSURFER_ATLASES)
LEGACY_FREESURFER_ATLAS_FILES = list(LEGACY_FREESURFER_ATLASES)
FREESURFER_ATLAS_FILES = [*LEGACY_FREESURFER_ATLASES, *FREESURFER_SUBREGION_ATLASES]
VOXEL_ATLAS_FILES = list(VOXEL_ATLASES)

# Custom per-subject masks live in m2m_{subject}/masks/. Any integer label
# volume with one of these extensions is auto-discovered as a targetable atlas.
MASK_EXTENSIONS = (".nii.gz", ".nii", ".mgz")

MNI_ATLAS_DIR = resolve_resource_path("atlas")

MNI_TEMPLATE = "MNI152_T1_1mm.nii.gz"

# ``MNI_ATLAS_FILES`` and ``DEFAULT_MNI_ATLAS`` are no longer written here: the
# shipped MNI atlases, their kind (surface vs volume), template space, LUT,
# licence and citation all live in ``resources/atlas/manifest.json`` and are read
# by :mod:`tit.atlas.manifest`.  They stay importable from this module under
# their old names, resolved lazily on first access so that reading the manifest
# cannot run while this module is still being imported.
_MANIFEST_NAMES = ("MNI_ATLAS_FILES", "DEFAULT_MNI_ATLAS")


def __getattr__(name):
    if name in _MANIFEST_NAMES:
        from tit.atlas.manifest import mni_atlas_files

        files = mni_atlas_files()
        if name == "MNI_ATLAS_FILES":
            return files
        return files[0] if files else ""
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def mni_resources_dir() -> str:
    """``MNI_ATLAS_DIR`` if it exists, else the repo-relative fallback.

    Same resolution as :mod:`tit.opt.roi_spec` uses, so the bundled MNI
    atlases, LUTs and
    template are found whether the caller runs inside the container
    (``/ti-toolbox/resources/atlas``) or from a host checkout.
    """
    if os.path.isdir(MNI_ATLAS_DIR):
        return MNI_ATLAS_DIR
    return str(Path(__file__).resolve().parents[2] / "resources" / "atlas")

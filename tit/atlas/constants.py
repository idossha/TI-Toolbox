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
# NIfTI. Everything below it is legacy FreeSurfer recon-all output, still
# discovered for projects that carry it (TI-Toolbox no longer produces it).
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

VOXEL_ATLASES = {**FASTSURFER_ATLASES, **LEGACY_FREESURFER_ATLASES}

# Flat lists for callers that only need filenames, in search order:
# FastSurfer first, then legacy FreeSurfer.
FASTSURFER_ATLAS_FILES = list(FASTSURFER_ATLASES)
LEGACY_FREESURFER_ATLAS_FILES = list(LEGACY_FREESURFER_ATLASES)
VOXEL_ATLAS_FILES = list(VOXEL_ATLASES)

# Custom per-subject masks live in m2m_{subject}/masks/. Any integer label
# volume with one of these extensions is auto-discovered as a targetable atlas.
MASK_EXTENSIONS = (".nii.gz", ".nii", ".mgz")

MNI_ATLAS_DIR = resolve_resource_path("atlas")

MNI_TEMPLATE = "MNI152_T1_1mm.nii.gz"

MNI_ATLAS_FILES = [
    "CIT168_labeling_MNI152NLin2009cAsym.nii.gz",
    "MorelMNI152_labeling_1mm.nii.gz",
    "MNI_Glasser_HCP_v1.0.nii.gz",
    "massp2021-parcellation_decade-18to40.nii.gz",
]

DEFAULT_MNI_ATLAS = MNI_ATLAS_FILES[0]


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

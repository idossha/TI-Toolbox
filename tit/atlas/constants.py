"""Atlas constants shared across the TI-Toolbox."""

import os

# Built-in mesh atlas names (always available via SimNIBS subject_atlas)
BUILTIN_ATLASES = ["DK40", "a2009s", "HCP_MMP1"]

# Voxel atlas files: filename → hemisphere ("both", "lh", or "rh").
# Labels file is always {stem}_labels.txt in the same directory (via mri_segstats).
# Single canonical source used by analyzer, flex subcortical, and NIfTI viewer.
VOXEL_ATLASES = {
    "aparc.DKTatlas+aseg.mgz": "both",
    "aparc.a2009s+aseg.mgz": "both",
    "lh.hippoAmygLabels-T1.v22.mgz": "lh",
    "rh.hippoAmygLabels-T1.v22.mgz": "rh",
    "ThalamicNuclei.v13.T1.mgz": "both",
}

# Flat list for callers that only need filenames.
VOXEL_ATLAS_FILES = list(VOXEL_ATLASES)

MNI_ATLAS_DIR = "/ti-toolbox/resources/atlas"

MNI_TEMPLATE = "MNI152_T1_1mm.nii.gz"

MNI_ATLAS_FILES = [
    "MNI_Glasser_HCP_v1.0.nii.gz",
    "massp2021-parcellation_decade-18to40.nii.gz",
]

DEFAULT_MNI_ATLAS = MNI_ATLAS_FILES[0]

"""Atlas constants shared across the TI-Toolbox."""

# Built-in mesh atlas names (always available via SimNIBS subject_atlas)
BUILTIN_ATLASES = ["DK40", "a2009s", "HCP_MMP1"]

# DK40 region names (fallback when .annot files are unavailable)
DK40_REGIONS = [
    "bankssts", "caudalanteriorcingulate", "caudalmiddlefrontal",
    "cuneus", "entorhinal", "frontalpole", "fusiform",
    "inferiorparietal", "inferiortemporal", "insula",
    "isthmuscingulate", "lateraloccipital", "lateralorbitofrontal",
    "lingual", "medialorbitofrontal", "middletemporal",
    "paracentral", "parahippocampal", "parsopercularis",
    "parsorbitalis", "parstriangularis", "pericalcarine",
    "postcentral", "posteriorcingulate", "precentral",
    "precuneus", "rostralanteriorcingulate", "rostralmiddlefrontal",
    "superiorfrontal", "superiorparietal", "superiortemporal",
    "supramarginal", "temporalpole", "transversetemporal",
]

# Voxel atlas files to look for in FreeSurfer mri/ and segmentation/ dirs.
# Single canonical list used by analyzer, flex subcortical, and NIfTI viewer.
VOXEL_ATLAS_FILES = [
    "aparc.DKTatlas+aseg.mgz",
    "aparc.a2009s+aseg.mgz",
    "aparc+aseg.mgz",
    "aseg.mgz",
    "lh.hippoAmygLabels-T1.v22.CA.mgz",
    "lh.hippoAmygLabels-T1.v22.mgz",
]

# MNI atlas filenames (looked up in assets/atlas/)
MNI_ATLAS_FILES = [
    "MNI_Glasser_HCP_v1.0.nii.gz",
    "HarvardOxford-sub-maxprob-thr0-1mm.nii.gz",
    "HOS-thr0-1mm.nii.gz",
]

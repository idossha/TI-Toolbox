# Atlas Resources

This directory stores MNI-space atlas resources used by TI-Toolbox workflows. Label maps are distributed with FreeSurfer-style lookup tables when region colors/names are needed (`ID Name R G B A`).

## CIT168 Subcortical Atlas

Source: NeuroVault collection 3145, "A high-resolution probabilistic in vivo atlas of human subcortical brain nuclei".

Reference:
Pauli W. M., Nili A. N., and Tyszka J. M. A high-resolution probabilistic in vivo atlas of human subcortical brain nuclei. Scientific Data 5, 180063 (2018). https://doi.org/10.1038/sdata.2018.63

Space:
MNI152 2009c nonlinear asymmetric space, according to the NeuroVault metadata.

Files:
- `CIT168_labeling_MNI152NLin2009cAsym.nii.gz`: deterministic integer label map generated from the probabilistic masks.
- `CIT168_labeling_MNI152NLin2009cAsym_LUT.txt`: FreeSurfer-style color lookup table.

Notes:
The original CIT168 atlas is probabilistic, so source masks can overlap. The deterministic label map assigns each voxel to the label with the highest probability when that maximum probability is at least 0.05; lower-probability voxels are background. The source probability maps are not stored here to keep the repository resource small.

## Morel MNI152 Thalamus Atlas

Source: Morel Atlas of the Human Thalamus, MNI152 space, voxelized version. Zenodo DOI: https://doi.org/10.5281/zenodo.13918589

License:
Creative Commons Attribution Non Commercial Share Alike 4.0 International.

Copyright notice:
(C) University of Zurich and ETH Zurich, Andras Jakab, Remi Blanc and Gabor Szekely.

Recommended citations:
- Jakab A., Blanc R., Berenyi E., and Szekely G. Generation of individualized thalamus target maps by using statistical shape models and thalamocortical tractography. AJNR 33(11):2110-2116, 2012.
- Krauth A., Blanc R., Poveda A., Jeanmonod D., Morel A., and Szekely G. A mean three-dimensional atlas of the human thalamus: Generation from multiple histological data. NeuroImage 49(3):2053-2062, 2010.

Files:
- `MorelMNI152_labeling_1mm.nii.gz`: deterministic integer label map in MNI152 1 mm space.
- `MorelMNI152_labeling_1mm_LUT.txt`: FreeSurfer-style color lookup table.

Notes:
The source archive provides separate binary masks for each nucleus and hemisphere. This resource combines the 1 mm left and right nucleus masks into one label image. The LUT reserves labels 1-38 for left-sided structures and 101-138 for right-sided structures; 0 is background. Where source masks overlap, the first listed label in the LUT is retained. In the generated 1 mm image, labels 27 and 127 have no remaining voxels after this overlap rule.

## MASSP 2021 Subcortical Parcellation

Files:
- `massp2021-parcellation_decade-18to40.nii.gz`: MNI-space subcortical parcellation.
- `massp2021_labels.txt`: FreeSurfer-style lookup table.

Notes:
This atlas includes left/right thalamus labels and several subcortical targets, including subthalamic nucleus labels. It does not provide detailed thalamic nuclei segmentation.

## Glasser HCP-MMP1 Atlas

Files:
- `MNI_Glasser_HCP_v1.0.nii.gz`: MNI-space Glasser/HCP multimodal cortical parcellation.
- `MNI_Glasser_HCP_v1.0.txt`: label table.
- `HCP-Multi-Modal-Parcellation-1.0.xml`: source metadata.
- `Glasser_2016_Table.xlsx`: Glasser region table.

Notes:
This is a cortical parcellation and is not intended for subthalamic or thalamic nuclei targeting.

## MNI152 Template

Files:
- `MNI152_T1_1mm.nii.gz`: MNI152 T1-weighted 1 mm template used for visualization and coordinate reference.

## FreeSurfer Usage

For label maps with a matching LUT:

```bash
mri_segstats \
  --seg <atlas_labeling.nii.gz> \
  --ctab <atlas_LUT.txt> \
  --sum stats.txt
```

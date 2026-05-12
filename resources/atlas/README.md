# CIT168 Subcortical Atlas

Source: NeuroVault collection 3145, "A high-resolution probabilistic in vivo atlas of human subcortical brain nuclei".

Reference:
Pauli W. M., Nili A. N., and Tyszka J. M. A high-resolution probabilistic in vivo atlas of human subcortical brain nuclei. Scientific Data 5, 180063 (2018). https://doi.org/10.1038/sdata.2018.63

Space:
The probabilistic masks are in MNI152 2009c nonlinear asymmetric space according to the NeuroVault metadata.

Files:
- `CIT168_labeling_MNI152NLin2009cAsym.nii.gz`: deterministic integer label map generated from the probabilistic masks.
- `CIT168_labeling_MNI152NLin2009cAsym_LUT.txt`: FreeSurfer-style color lookup table (`ID Name R G B A`) for the deterministic map.

Notes:
The original CIT168 atlas is probabilistic, so source masks can overlap. The deterministic label map assigns each voxel to the label with the highest probability when that maximum probability is at least 0.05; lower-probability voxels are background. The source probability maps are not stored here to keep the repository resource small.

FreeSurfer usage:
Use the LUT with FreeSurfer commands that accept a color table, for example `mri_segstats --seg CIT168_labeling_MNI152NLin2009cAsym.nii.gz --ctab CIT168_labeling_MNI152NLin2009cAsym_LUT.txt --sum stats.txt`.

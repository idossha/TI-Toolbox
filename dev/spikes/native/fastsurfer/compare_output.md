# FastSurfer vs FreeSurfer vs charm -- label comparison (sub-ernie)

- `fastsurfer`: `/private/tmp/claude-501/-Users-idohaber-01-production-TI-toolbox/2f1d440f-51f9-4340-bb8a-c347107a12b1/scratchpad/native/fastsurfer/out/sub-ernie/mri/aparc.DKTatlas+aseg.deep.mgz`  exists=True
- `freesurfer`: `/Users/idohaber/datasets/000/derivatives/freesurfer/sub-ernie/mri/aparc.DKTatlas+aseg.mgz`  exists=True
- `charm`: `/Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/segmentation/labeling.nii.gz`  exists=True
- `freesurfer_preresampled`: `/Users/idohaber/datasets/000/derivatives/freesurfer/sub-ernie/mri/aparc_DKTatlas+aseg_resampled_256x256x208_45dfa12d.nii.gz`  exists=True

## 1. Grid / affine check

| Source | Shape | Affine (flattened) |
|---|---|---|
| freesurfer (real recon-all) | (np.int32(256), np.int32(256), np.int32(256)) | `-1.000 0.000 0.000 132.263 0.000 0.000 1.000 -101.812 0.000 -1.000 0.000 112.358` |
| fastsurfer (--seg_only) | (np.int32(256), np.int32(256), np.int32(256)) | `-1.000 0.000 0.000 132.263 0.000 0.000 1.000 -101.812 0.000 -1.000 0.000 112.358` |
| charm (labeling.nii.gz) | (256, 256, 208) | `-0.000 -0.000 1.000 -99.737 -1.000 0.000 -0.000 154.188 0.000 1.000 0.000 -143.642` |

FreeSurfer-conform grid match (FastSurfer vs real recon-all): **True**

## 2. FastSurfer vs real FreeSurfer recon-all (FreeSurfer-conform grid)

### 2a. Subcortical structures (Dice, volumes)

| Structure | Dice | Vol FreeSurfer (mm3) | Vol FastSurfer (mm3) | %diff | Centroid dist (mm) |
|---|---|---|---|---|---|
| Left-Thalamus | 0.956 | 9903 | 10085 | +1.8% | 0.18 |
| Right-Thalamus | 0.928 | 8250 | 9133 | +10.7% | 0.56 |
| Left-Caudate | 0.952 | 3533 | 3515 | -0.5% | 0.11 |
| Right-Caudate | 0.938 | 3768 | 3758 | -0.3% | 0.59 |
| Left-Putamen | 0.948 | 5321 | 5564 | +4.6% | 0.34 |
| Right-Putamen | 0.944 | 5215 | 5372 | +3.0% | 0.13 |
| Left-Pallidum | 0.925 | 2046 | 2136 | +4.4% | 0.24 |
| Right-Pallidum | 0.904 | 2269 | 2296 | +1.2% | 0.76 |
| Left-Hippocampus | 0.932 | 4434 | 4431 | -0.1% | 0.29 |
| Right-Hippocampus | 0.939 | 4577 | 4669 | +2.0% | 0.44 |
| Left-Amygdala | 0.910 | 1975 | 1905 | -3.5% | 0.11 |
| Right-Amygdala | 0.915 | 1929 | 1939 | +0.5% | 0.80 |
| Left-Accumbens | 0.885 | 602 | 637 | +5.8% | 0.51 |
| Right-Accumbens | 0.826 | 680 | 799 | +17.5% | 1.04 |

### 2b. Cortical DKT labels (Dice, volumes)

| Region | Dice | Vol FreeSurfer (mm3) | Vol FastSurfer (mm3) | %diff | Centroid dist (mm) |
|---|---|---|---|---|---|
| ctx-lh-precentral | 0.916 | 16789 | 15781 | -6.0% | 1.08 |
| ctx-rh-precentral | 0.931 | 15809 | 14965 | -5.3% | 1.09 |
| ctx-lh-postcentral | 0.916 | 14247 | 14152 | -0.7% | 0.69 |
| ctx-rh-postcentral | 0.924 | 11984 | 11713 | -2.3% | 0.13 |
| ctx-lh-superiorfrontal | 0.934 | 30452 | 30577 | +0.4% | 0.44 |
| ctx-rh-superiorfrontal | 0.927 | 30653 | 30852 | +0.6% | 1.33 |
| ctx-lh-insula | 0.926 | 7040 | 7241 | +2.9% | 0.31 |
| ctx-rh-insula | 0.942 | 7067 | 7181 | +1.6% | 0.26 |
| ctx-lh-inferiorparietal | 0.884 | 12796 | 13266 | +3.7% | 1.32 |
| ctx-rh-inferiorparietal | 0.915 | 17392 | 17655 | +1.5% | 0.69 |
| ctx-lh-superiortemporal | 0.897 | 18288 | 18454 | +0.9% | 3.07 |
| ctx-rh-superiortemporal | 0.929 | 18149 | 17952 | -1.1% | 0.30 |
| ctx-lh-precuneus | 0.920 | 11896 | 12145 | +2.1% | 0.51 |
| ctx-rh-precuneus | 0.919 | 11572 | 11384 | -1.6% | 1.11 |
| ctx-lh-lateraloccipital | 0.887 | 13836 | 13777 | -0.4% | 2.04 |
| ctx-rh-lateraloccipital | 0.911 | 14805 | 15177 | +2.5% | 0.77 |
| ctx-lh-superiorparietal | 0.911 | 14323 | 13719 | -4.2% | 0.65 |
| ctx-rh-superiorparietal | 0.912 | 13219 | 13281 | +0.5% | 0.55 |
| ctx-lh-parsopercularis | 0.860 | 4673 | 5057 | +8.2% | 1.38 |
| ctx-rh-parsopercularis | 0.910 | 5501 | 5520 | +0.3% | 0.57 |

Mean subcortical Dice (FastSurfer vs real FreeSurfer): 0.922
Mean cortical Dice (FastSurfer vs real FreeSurfer): 0.914

## 3. Subcortical vs charm `labeling.nii.gz` (different grid, resampled)

(resampled both onto charm's (256, 256, 208) grid in 1.08s)

**Cross-check**: our nearest-neighbour resample of real FreeSurfer's aparc.DKTatlas+aseg onto the charm grid agrees with the pipeline's own pre-existing `mri_convert --reslice_like` output at **100.00%** of voxels (grid: (256, 256, 208)).

| Structure | Dice(FastSurfer,charm) | Dice(FreeSurfer,charm) | Vol charm (mm3) | Vol FreeSurfer (mm3) | Vol FastSurfer (mm3) | Centroid dist FS-charm (mm) | Centroid dist FreeSurfer-charm (mm) |
|---|---|---|---|---|---|---|---|
| Left-Thalamus | 0.852 | 0.852 | 8128 | 9903 | 10085 | 1.33 | 1.31 |
| Right-Thalamus | 0.851 | 0.881 | 7346 | 8250 | 9133 | 1.63 | 1.39 |
| Left-Caudate | 0.898 | 0.893 | 3375 | 3533 | 3515 | 0.96 | 0.94 |
| Right-Caudate | 0.906 | 0.894 | 3433 | 3768 | 3758 | 0.39 | 0.70 |
| Left-Putamen | 0.914 | 0.889 | 6109 | 5321 | 5564 | 1.04 | 0.86 |
| Right-Putamen | 0.925 | 0.898 | 5727 | 5215 | 5372 | 0.68 | 0.76 |
| Left-Pallidum | 0.785 | 0.781 | 2352 | 2046 | 2136 | 3.15 | 3.02 |
| Right-Pallidum | 0.733 | 0.750 | 2509 | 2269 | 2296 | 4.38 | 3.68 |
| Left-Hippocampus | 0.858 | 0.837 | 4298 | 4434 | 4431 | 1.79 | 2.06 |
| Right-Hippocampus | 0.892 | 0.877 | 4709 | 4577 | 4669 | 0.78 | 1.12 |
| Left-Amygdala | 0.841 | 0.807 | 1978 | 1975 | 1905 | 0.82 | 0.90 |
| Right-Amygdala | 0.896 | 0.851 | 1966 | 1929 | 1939 | 0.36 | 1.08 |
| Left-Accumbens | 0.831 | 0.791 | 620 | 602 | 637 | 0.87 | 0.65 |
| Right-Accumbens | 0.800 | 0.736 | 613 | 680 | 799 | 0.81 | 1.49 |

Total compare.py wall time: 10.0s


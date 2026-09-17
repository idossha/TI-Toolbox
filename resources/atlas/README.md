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

## FreeSurfer ThalamicNuclei v13 (legacy `recon-all` atlas)

Source: FreeSurfer's own `distribution/FreeSurferColorLUT.txt` (fetched from
https://raw.githubusercontent.com/freesurfer/freesurfer/dev/distribution/FreeSurferColorLUT.txt on
2026-09-03), the section headed "Labels for thalamus parcellation using histological atlas
(Iglesias et al.)" -- ids 8103-8136 (left) / 8203-8236 (right).

Reference:
Iglesias J. E., Insausti R., Lerma-Usabiaga G., Bocchetta M., Van Leemput K., Greve D. N., van der
Kouwe A., Fischl B., Caballero-Gaudes C., and Paz-Alonso P. M. A probabilistic atlas of the human
thalamic nuclei combining ex vivo MRI and histology. NeuroImage 183:314-326 (2018).
https://doi.org/10.1016/j.neuroimage.2018.08.012

Files:
- `ThalamicNuclei_LUT.txt`: FreeSurfer-style colour lookup table for `ThalamicNuclei.v13.T1.mgz`
  / `ThalamicNuclei.v13.T1.FSvoxelSpace.mgz`, the per-subject `recon-all` output this atlas names
  when no atlas-specific sidecar sits next to it -- `tit/atlas/segstats.py::resolve_lut_for_atlas`
  special-cases this atlas family onto this table (bundled `FreeSurferColorLUT.txt` predates the
  8100s/8200s range and has no entries there).

Notes:
This is a fixed, subject-independent id -> name mapping, not derived from the per-subject
`ThalamicNuclei.v13.T1.volumes.txt` sidecar `recon-all` also writes: that file's name order is
anatomically grouped, not numeric-id order, and does not line up 1:1 against any one subject's own
sorted voxel-label ids (small nuclei carry zero voxels in some subjects and not others) -- see
`ThalamicNuclei_LUT.txt`'s own header for the verification detail.

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

## Survey: which MNI-space atlases TI-Toolbox may ship (2026-09-17)

TI-Toolbox is GPL-3.0. Atlas volumes are *data*, not code linked into `tit`, so the GPL does not by
itself decide this; the practical test is whether the file can be redistributed by **anyone**,
including the commercial users GPL-3 grants rights to, without written permission. Under that test:
permissive (MIT / CC0 / CC BY / "any purpose without fee") ships; CC BY-SA ships (the share-alike
binds the atlas file, not `tit`); anything non-commercial or with an explicit no-redistribution
clause does not, and becomes an optional download the user fetches from upstream themselves.

### Space: what SimNIBS's warps assume

`mni2subject` / `mni2subject_coords` warp against **`MNI152_T1_1mm.nii.gz`** — SimNIBS's
`file_finder.Templates().mni_volume`, the same file charm writes its `mni2conf_nonl` warps against,
and byte-identical in size to the copy in this directory. That file is FSL's
`$FSLDIR/data/standard/MNI152_T1_1mm.nii.gz`, i.e. **MNI152NLin6Asym**.

An atlas defined in **MNI152NLin2009cAsym** (or 2009b) is therefore in a *different* template from
the one SimNIBS warps. Measured on the TemplateFlow 1 mm brain masks of both templates, the global
difference is about **1.3 mm** (brain-mask centroids: NLin6Asym (0.56, -21.53, 9.83) vs 2009cAsym
(-0.51, -22.12, 9.48) RAS mm; bounding boxes agree within 2 mm on every face). It is not a bulk
shift: it is a ~1 mm global term plus local nonlinear differences that are largest at small deep
nuclei. For a cortical TI target that is negligible against the focality of the field; for
thalamic/basal-ganglia targeting it is of the order of the structure itself, and the
`tpl-MNI152NLin6Asym_from-MNI152NLin2009cAsym_mode-image_xfm.h5` transform should be applied first.
**No such correction is applied today**; the `roi_confirmation.png` every MNI job writes
(`tit/roi_confirmation.py`) is what lets a user see where a target actually landed.

### What is shipped today

| Atlas | Space | Regions | Licence | GPL-3 redistribution | Decision |
|---|---|---|---|---|---|
| CIT168 | MNI152NLin2009cAsym | 16 | CC BY 4.0 (OSF `jkzwp`/`r2hvk`); NeuroVault CC0; code MIT | yes | **ship** (kept) |
| Morel thalamus | MNI152NLin6Asym (header `FSL4.0`, 182x218x182) | 74 | **CC BY-NC-SA 4.0** (Zenodo 13918589 DataCite `cc-by-nc-sa-4.0`) | **no — non-commercial** | **open question** (below) |
| MNI Glasser HCP-MMP1.0 | MNI152NLin2009cAsym world coords on a FreeSurfer-conformed 256^3 grid (AFNI `MNI_Glasser_HCP_2019_v1.0`) | 360 | WU-Minn HCP Open Access Data Use Terms, clause 4: redistribution permitted "as long as the data are redistributed under these same Data Use Terms" | conditional yes | **ship, with terms** (acknowledgement below) |
| MASSP 2021 | MNI152NLin2009bAsym, 0.5 mm | 17 structures / 31 LUT rows | CC BY 4.0 (figshare 19646328 / DOI 10.21942/uva.19646328) | yes | **ship** (kept) |
| `MNI152_T1_1mm.nii.gz` | MNI152NLin6Asym | - | MNI/McGill: "Permission to use, copy, modify, and distribute ... for any purpose and without fee is hereby granted, provided that the above copyright notice appear in all copies." (c) Louis Collins, McConnell BIC, MNI, McGill | yes | **ship** (kept) |

**Open question for the maintainer — the Morel atlas.** It is CC BY-NC-SA 4.0, which forbids
commercial use, and it is in this repository and in the Docker image today. That is a licence
problem that predates this survey and is **not** fixed here, because removing a shipped atlas
changes what existing configurations resolve. The options are: (a) obtain written permission from
A. Jakab / University of Zurich, (b) move it to a `tit.examples`-style optional download the user
fetches from Zenodo themselves, or (c) drop it. Until then, `tit/scene/guide-mni/` also packages
surfaces derived from it.

### FSL (`$FSLDIR/data/atlases`)

| Atlas | Space | Regions | Licence | GPL-3 redistribution | Decision |
|---|---|---|---|---|---|
| Harvard-Oxford cortical + subcortical | MNI152NLin6Asym (FSL standard space; affine-registered origin) | 48 + 21 | **CC BY-SA 4.0** — FSL licence page: "The Cerebellum and Harvard-Oxford atlases, whilst not being the property of Oxford, are released under the CC BY-SA 4.0 licence" | yes | **add** — the most-asked-for general-purpose atlas, and it matches SimNIBS's template exactly |
| Cerebellum (Diedrichsen 2009), MNIfnirt | MNI152NLin6Asym | 28 | CC BY-SA 4.0 (same sentence) | yes | **add** (MNIfnirt variant only; MNIflirt is affine-only) |
| MNI structural | ICBM152, generation unstated | 9 | FSL licence (non-commercial) per NeuroDebian `fsldata` copyright | no | skip — 9 lobar labels are not a TI target |
| JHU ICBM-DTI-81 + tractography | ICBM152, generation unstated | 48 / 20 | FSL licence page: "The JHU, Juelich, Striatum and Thalamus atlases ... should therefore not be used for commercial purposes" | **no** | optional download |
| Juelich histological (FSL build) | ICBM152, generation unstated | ~121 | same FSL sentence | **no** | optional download |
| Talairach Daemon labels | Talairach + Lancaster 2007 affine into MNI152 | ~1100 | BrainMap/RIC-UTHSCSA: "for educational and scientific, non-commercial purposes"; commercial use "requires a written consent from RIC-UTHSCSA" | **no** | skip |
| Oxford Thalamic Connectivity | FSL standard space | 7 | FSL licence (non-commercial) | **no** | optional download |
| Oxford-GSK-Imanova Striatal | "manually delineated on the non-linear MNI152 template" -> NLin6Asym | 7 / 3 | FSL licence (non-commercial) | **no** | optional download |

### Brainstorm's MNI template atlases

Brainstorm's default anatomy is ICBM152 2009c nonlinear asymmetric; its volume atlases arrive via
CAT12 and FreeSurfer. Brainstorm publishes no licence statement for them and links upstream, so its
bundling is not precedent.

| Atlas | Space | Regions | Licence | GPL-3 redistribution | Decision |
|---|---|---|---|---|---|
| AAL2 / AAL3 | defined on MNI single-subject **Colin27**, resampled to 2009c by CAT12 | 120 / 166 | **GPL** — AAL3 User Guide (April 2024): "available to the scientific community as copyright freeware under the terms of the GNU General Public License" | yes | optional — permitted, but Colin27-derived; low value beside Harvard-Oxford |
| Schaefer 2018 (CBIG) | FSL MNI152 volumes (generation per file unverified) | 100-1000 x 7/17 networks | **MIT** (CBIG `LICENSE.md`) | yes | **add** (one resolution, e.g. 400 parcels / 7 networks, 1 mm) |
| Neuromorphometrics (SPM12 / OASIS) | SPM12 MNI, unspecified | 93 | CC BY-NC + "Users may not share or distribute the Labeled Scans to any third party outside of their research group" | **no** | skip |
| Julich-Brain (EBRAINS v2.2-v3.1) | MNI152NLin2009cAsym (and Colin27) | ~227 | **CC BY-NC-SA 4.0** (DataCite rights for 10.25493/TAKY-64D, vsmk-h94, knsn-xb4) | **no** | optional download from EBRAINS |
| Hammers n30r83 | "MNI space", generation unstated | 83 | Imperial College academic EULA: "You shall not (i) sub-licence or distribute the Materials to third parties" | **no** | skip — cannot even be offered as our own download |
| Brodmann (Brainstorm) | FreeSurfer `BA_exvivo` on template surfaces | ~14 areas/hemi | FreeSurfer licence: "limited to non-commercial internal research and educational purposes by not-for-profit entities" | **no** | skip |
| Desikan-Killiany / Destrieux (template FreeSurfer) | fsaverage surfaces | 34 / 74 per hemi | FreeSurfer licence (non-commercial) | **no** | skip as *shipped MNI files* — TI-Toolbox already reads these per subject from the user's own `recon-all`, which is the user's own licence to hold |

### Attribution required by what is shipped

* **CIT168** — Pauli W. M., Nili A. N., Tyszka J. M., *Sci Data* 5:180063 (2018); CC BY 4.0.
* **MASSP 2021** — figshare DOI 10.21942/uva.19646328; CC BY 4.0.
* **MNI Glasser HCP-MMP1.0** — "Data were provided [in part] by the Human Connectome Project,
  WU-Minn Consortium (Principal Investigators: David Van Essen and Kamil Ugurbil; 1U54MH091657)
  funded by the 16 NIH Institutes and Centers that support the NIH Blueprint for Neuroscience
  Research; and by the McDonnell Center for Systems Neuroscience at Washington University."
  Cite Glasser M. F. et al., *Nature* 536:171-178 (2016). Redistribution is under the same HCP Open
  Access Data Use Terms.
* **MNI152 template** — Copyright (C) 1993-2009 Louis Collins, McConnell Brain Imaging Centre,
  Montreal Neurological Institute, McGill University.
* **Morel** — see the open question above.

## FreeSurfer Usage

For label maps with a matching LUT:

```bash
mri_segstats \
  --seg <atlas_labeling.nii.gz> \
  --ctab <atlas_LUT.txt> \
  --sum stats.txt
```

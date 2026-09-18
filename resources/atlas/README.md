# Atlas Resources

`manifest.json` is the one description of every atlas shipped here: for each one, the file, its
**kind** (`volume` or `surface` — which targeting flow can read it), its template space, its
labels/LUT file, its licence, the attribution it requires, whether it may be redistributed, and
what to cite. :mod:`tit.atlas.manifest` is the only reader; `tit/atlas/constants.py`,
`tit/catalog.py` and the desktop ROI picker all resolve through it, so the ROI picker in MNI mode
offers a volume atlas to the subcortical flow and a surface atlas to the cortical flow and never
the wrong one. `tests/test_atlas_manifest.py` fails if an atlas here is undescribed, or described
and not shipped, or missing its LUT or a licence field.

The prose below stays as the survey and the working notes; the manifest is what the code reads.

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

## Harvard-Oxford cortical and subcortical structural atlases

Source: the FSL atlas files as distributed, taken unmodified from the NeuroDebian package
`fsl-harvard-oxford-atlases_5.0.7-2_all.deb`
(<http://neuro.debian.net/debian/pool/non-free/f/fsldata/fsl-harvard-oxford-atlases_5.0.7-2_all.deb>,
sha256 `235a9be15b8061caf2ab9caaaab41ffacaf025232b0507259f660218a01249b4`), fetched 2026-09-17.

License:
CC BY-SA 4.0. The FSL licence page (<https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html>) states:
"The Cerebellum and Harvard-Oxford atlases, whilst not being the property of Oxford, are released
under the CC BY-SA 4.0 licence". (The 2014 Debian `copyright` file inside that package predates
this carve-out and still quotes the blanket FSL licence; the FSL page is the current statement.)
Share-alike binds the atlas volumes and their LUTs, which stay CC BY-SA 4.0; the files are shipped
byte-identical.

Attribution: Harvard-Oxford structural atlases, Harvard Center for Morphometric Analysis (CMA),
distributed with FSL.

References:
- Desikan R. S. et al. An automated labeling system for subdividing the human cerebral cortex on MRI
  scans into gyral based regions of interest. NeuroImage 31(3):968-980 (2006).
- Frazier J. A. et al. Structural brain magnetic resonance imaging of limbic and thalamic volumes in
  pediatric bipolar disorder. Am J Psychiatry 162(7):1256-1265 (2005).
- Makris N. et al. Decreased volume of left and total anterior insular lobule in schizophrenia.
  Schizophr Res 83(2-3):155-171 (2006).

Files:
- `HarvardOxford-cort-maxprob-thr25-1mm.nii.gz`: cortical maximum-probability map, threshold 25 %,
  1 mm, 48 labels (package member
  `usr/share/data/harvard-oxford-atlases/HarvardOxford/HarvardOxford-cort-maxprob-thr25-1mm.nii.gz`).
- `HarvardOxford-sub-maxprob-thr25-1mm.nii.gz`: subcortical maximum-probability map, threshold 25 %,
  1 mm, 21 labels.
- `HarvardOxford-cort-maxprob-thr25-1mm_LUT.txt`, `HarvardOxford-sub-maxprob-thr25-1mm_LUT.txt`:
  FreeSurfer-style LUTs generated from FSL's `HarvardOxford-Cortical.xml` /
  `HarvardOxford-Subcortical.xml`. FSL's XML `index` is 0-based and the value in a `maxprob` image
  is index + 1, so the LUT ids are XML index + 1; names are FSL's with spaces replaced by hyphens;
  colours are TI-Toolbox's own (FSL's XML carries none).

Space:
MNI152NLin6Asym, FSL standard space. Header verified in the container against the shipped
`MNI152_T1_1mm.nii.gz`: 182x218x182, 1 mm, identical affine (origin 90, -126, -72 with a negative
x step, i.e. world x from +90 down to -91). This is the template SimNIBS's `mni2subject` warps
assume, so these atlases need no template correction.

Notes:
The subcortical map's labels 1, 2, 12 and 13 are whole-hemisphere white matter / cortex and 3, 14
are the lateral ventricles; they are not TI targets but are kept so the file is unmodified.

## Cerebellum-MNIfnirt (Diedrichsen 2009)

Source: the FSL atlas file as distributed, taken unmodified from the NeuroDebian package
`fsl-bangor-cerebellar-atlas_5.0.7-2_all.deb`
(<http://neuro.debian.net/debian/pool/non-free/f/fsldata/fsl-bangor-cerebellar-atlas_5.0.7-2_all.deb>,
sha256 `fad71fd734674ff57d0dfb28e7c5fc38b42491a559d3b579b1301f64a1f73acf`), fetched 2026-09-17.

License: CC BY-SA 4.0, by the same FSL licence sentence as Harvard-Oxford above.

Reference:
Diedrichsen J., Balsters J. H., Flavell J., Cussans E., Ramnani N. A probabilistic MR atlas of the
human cerebellum. NeuroImage 46(1):39-46 (2009). https://doi.org/10.1016/j.neuroimage.2009.01.045

Files:
- `Cerebellum-MNIfnirt-maxprob-thr25-1mm.nii.gz`: maximum-probability map after FNIRT
  normalisation, threshold 25 %, 1 mm, 28 labels (lobules I-IV to X, left / right / vermis). The
  MNIflirt (affine-only) variant is deliberately not shipped.
- `Cerebellum-MNIfnirt-maxprob-thr25-1mm_LUT.txt`: FreeSurfer-style LUT generated from FSL's
  `Cerebellum_MNIfnirt.xml` (ids = XML index + 1, as above).

Space: MNI152NLin6Asym; header verified identical to `MNI152_T1_1mm.nii.gz` (182x218x182, 1 mm).

## Schaefer 2018, 400 parcels, 7 networks

Source: ThomasYeoLab/CBIG, commit `35b5664bec8822e2f77da5e090e96f91d0095be6` (master, 2026-08-31),
`stable_projects/brain_parcellation/Schaefer2018_LocalGlobal/Parcellations/MNI/`, fetched
2026-09-17:
- `Schaefer2018_400Parcels_7Networks_order_FSLMNI152_1mm.nii.gz`, sha256
  `abb8032840af30603995fd59634fd6bcd816088870de9061bbf90ad42c408d4d`
- `freeview_lut/Schaefer2018_400Parcels_7Networks_order.txt`, sha256
  `f62cdc9de9696e11bda9fe1cd51fc013b1da27ba180d2dcead8f3fd94bf3cbc1`

License: MIT — `LICENSE.md` at the repository root at that commit reads "Copyright (c) 2016
Computational Brain Imaging Group (CBIG)" followed by the standard MIT permission notice.

Reference:
Schaefer A., Kong R., Gordon E. M., Laumann T. O., Zuo X.-N., Holmes A. J., Eickhoff S. B.,
Yeo B. T. T. Local-global parcellation of the human cerebral cortex from intrinsic functional
connectivity MRI. Cerebral Cortex 28(9):3095-3114 (2018). https://doi.org/10.1093/cercor/bhx179

Files:
- `Schaefer2018_400Parcels_7Networks_order_FSLMNI152_1mm.nii.gz`: 400 cortical parcels
  (1-200 left, 201-400 right), each assigned to one of the Yeo 7 networks.
- `Schaefer2018_400Parcels_7Networks_order.txt`: CBIG's own FreeSurfer-style LUT, unmodified
  (the manifest's `labels` field names it, so the sidecar lookup does not need a matching stem).

Space:
CBIG documents this file as aligned to the FSL MNI152 1 mm template. Header verified in the
container against the shipped `MNI152_T1_1mm.nii.gz`: 182x218x182, 1 mm, identical affine, so it
is on the FSL MNI152NLin6Asym grid (the header `descrip` says "FreeSurfer May 13 2013", which is the
writer, not the space). Like Glasser it is a cortical parcellation distributed as a label volume,
so its manifest kind is `volume` and it is targeted through the subcortical/volumetric flow.

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
**No such correction is applied today**, and as of 2026-09-17 that is a decision rather than an
omission: measured on `ernie`, warping a CIT168 or MASSP label into subject space and comparing its
centroid against `charm`'s own `labeling.nii.gz` label for the same structure gives 1.05 mm
(CIT168 putamen), 2.20 mm (CIT168 caudate), 2.00 mm (MASSP thalamus left) and 1.19 mm (MASSP
thalamus right) — the same order as the disagreement between two segmentations of one structure.
See `docs/dev/DECISIONS.md § 2026-09-17 (Atlas manifest, the MNI target transform, and atlas
licences)`. The ROI plate (`roi_plate.png`) every job writes (`tit/roi_confirmation.py`) is what
lets a user see where a target actually landed.

`tit.opt.flex` transforms an MNI atlas label into the subject *itself* (`prepare_mask`, one
documented warp) rather than handing SimNIBS the whole atlas with `mask_space="mni"`, so the
island cleanup and the confirmation plate operate on the same subject-space mask the search does.

### What is shipped today

| Atlas | Space | Regions | Licence | GPL-3 redistribution | Decision |
|---|---|---|---|---|---|
| CIT168 | MNI152NLin2009cAsym | 16 | CC BY 4.0 (OSF `jkzwp`/`r2hvk`); NeuroVault CC0; code MIT | yes | **ship** (kept) |
| MNI Glasser HCP-MMP1.0 | MNI152NLin2009cAsym world coords on a FreeSurfer-conformed 256^3 grid (AFNI `MNI_Glasser_HCP_2019_v1.0`) | 360 | WU-Minn HCP Open Access Data Use Terms, clause 4: redistribution permitted "as long as the data are redistributed under these same Data Use Terms" | conditional yes | **ship, with terms** (acknowledgement below) |
| MASSP 2021 | MNI152NLin2009bAsym, 0.5 mm | 17 structures / 31 LUT rows | CC BY 4.0 (figshare 19646328 / DOI 10.21942/uva.19646328) | yes | **ship** (kept) |
| Harvard-Oxford cortical | MNI152NLin6Asym (header `FSL3.3`, 182x218x182, affine identical to the template) | 48 | **CC BY-SA 4.0** (FSL licence page) | yes | **ship** (added 2026-09-17) |
| Harvard-Oxford subcortical | MNI152NLin6Asym (header `FSL5.0`, 182x218x182, affine identical) | 21 | **CC BY-SA 4.0** (FSL licence page) | yes | **ship** (added 2026-09-17) |
| Cerebellum-MNIfnirt (Diedrichsen 2009) | MNI152NLin6Asym (header `FSL4.0`, 182x218x182, affine identical) | 28 | **CC BY-SA 4.0** (FSL licence page) | yes | **ship** (added 2026-09-17) |
| Schaefer 2018 400 / 7 networks | MNI152NLin6Asym (CBIG `FSLMNI152_1mm`; 182x218x182, affine identical) | 400 | **MIT** (CBIG `LICENSE.md` @ `35b5664b`) | yes | **ship** (added 2026-09-17) |
| `MNI152_T1_1mm.nii.gz` | MNI152NLin6Asym | - | MNI/McGill: "Permission to use, copy, modify, and distribute ... for any purpose and without fee is hereby granted, provided that the above copyright notice appear in all copies." (c) Louis Collins, McConnell BIC, MNI, McGill | yes | **ship** (kept) |

### Not shipped

**Morel thalamus atlas** (`MorelMNI152_labeling_1mm.nii.gz`, 74 nuclei, MNI152NLin6Asym) — removed
on 2026-09-17. It is CC BY-NC-SA 4.0 (Zenodo record 13918589, DataCite `cc-by-nc-sa-4.0`;
(C) University of Zurich and ETH Zurich, Andras Jakab, Remi Blanc and Gabor Szekely), which forbids
commercial use, and a GPL-3 project cannot redistribute it: it was in this repository and in the
Docker image from the first release until then, together with surfaces derived from it in
`tit/scene/guide-mni/`. Both were deleted, not moved. A configuration that still names it fails
with "The Morel atlas is no longer shipped (CC BY-NC-SA); see docs/wiki/atlases.md" (the sentence
comes from `manifest.json § not_shipped`). Citations, for anyone who fetches it themselves:
Krauth A. et al. *NeuroImage* 49(3):2053-2062 (2010); Jakab A. et al. *AJNR* 33(11):2110-2116 (2012).

*Path to reinstating it as an optional download:* add a `tit.examples`-style catalog part
(`tit/examples/catalog.json`, sha256-pinned) that fetches the Zenodo archive
<https://doi.org/10.5281/zenodo.13918589> into the user's own project, rebuild the combined 1 mm
label image from the per-nucleus masks with the LUT rule that used to live here (labels 1-38 left,
101-138 right, first listed label wins where masks overlap), and register the result as a
subject-independent user atlas rather than a shipped one. The user then holds the CC BY-NC-SA
licence, not TI-Toolbox. The old LUT is in history at commit `33e68f0c`
(`resources/atlas/MorelMNI152_labeling_1mm_LUT.txt`).

### FSL (`$FSLDIR/data/atlases`)

| Atlas | Space | Regions | Licence | GPL-3 redistribution | Decision |
|---|---|---|---|---|---|
| Harvard-Oxford cortical + subcortical | MNI152NLin6Asym (FSL standard space; affine-registered origin) | 48 + 21 | **CC BY-SA 4.0** — FSL licence page: "The Cerebellum and Harvard-Oxford atlases, whilst not being the property of Oxford, are released under the CC BY-SA 4.0 licence" | yes | **shipped since 2026-09-17** — the most-asked-for general-purpose atlas, and it matches SimNIBS's template exactly |
| Cerebellum (Diedrichsen 2009), MNIfnirt | MNI152NLin6Asym | 28 | CC BY-SA 4.0 (same sentence) | yes | **shipped since 2026-09-17** (MNIfnirt variant only; MNIflirt is affine-only) |
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
| Schaefer 2018 (CBIG) | FSL MNI152 volumes; the 400/7 1 mm file verified on the NLin6Asym grid | 100-1000 x 7/17 networks | **MIT** (CBIG `LICENSE.md`) | yes | **shipped since 2026-09-17** (400 parcels / 7 networks, 1 mm) |
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
* **Harvard-Oxford cortical / subcortical** — Harvard Center for Morphometric Analysis, distributed
  with FSL; CC BY-SA 4.0. Cite Desikan R. S. et al., *NeuroImage* 31:968-980 (2006); Frazier J. A.
  et al., *Am J Psychiatry* 162:1256-1265 (2005); Makris N. et al., *Schizophr Res* 83:155-171 (2006).
* **Cerebellum-MNIfnirt** — Diedrichsen J. et al., *NeuroImage* 46:39-46 (2009); CC BY-SA 4.0.
* **Schaefer 2018** — Copyright (c) 2016 Computational Brain Imaging Group (CBIG), MIT. Cite
  Schaefer A. et al., *Cerebral Cortex* 28:3095-3114 (2018).

The repository-root `NOTICE` file carries these notices verbatim for redistributors.

## FreeSurfer Usage

For label maps with a matching LUT:

```bash
mri_segstats \
  --seg <atlas_labeling.nii.gz> \
  --ctab <atlas_LUT.txt> \
  --sum stats.txt
```

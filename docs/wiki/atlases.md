---
layout: wiki
title: Brain Atlases
permalink: /wiki/atlases/
---

## Overview

Atlases reach TI-Toolbox two different ways, and the distinction matters when you define an ROI:

- **[MNI-space atlases](#mni-space-atlases)** are _shipped with the toolbox_ as ready-to-use NIfTI volumes in `resources/atlas/`. They are the same seven volumes for every user, and SimNIBS transforms a selected label into your subject's space at run time.
- **[Subject-space atlases](#subject-space-atlases)** are _generated per subject_ during preprocessing by SimNIBS `charm`/`subject_atlas` and FastSurfer or optional FreeSurfer. Existing FreeSurfer outputs are also read. Nothing is shipped — they only exist once you have run the pipeline on a head model. The browser below uses the `ernie` example subject so you can see what they look like.

Both families are queried through the same ROI picker used in flex-search, ex-search, and the analyzer.

|                          | MNI-space                  | Subject-space              |
| ------------------------ | -------------------------- | -------------------------- |
| Shipped with the toolbox | Yes, in `resources/atlas/` | No — generated per subject |
| Same for every user      | Yes                        | No                         |
| Produced by              | Bundled with TI-Toolbox    | `charm` and `recon-all`    |

---

# MNI-Space Atlases

TI-Toolbox ships seven atlases as MNI-space NIfTI volumes:

| Atlas                                   | Regions | Native space                                        |
| --------------------------------------- | ------- | --------------------------------------------------- |
| CIT168 Subcortical (left/right)         | 32      | MNI152NLin2009cAsym                                 |
| Glasser HCP-MMP1.0                      | 360     | FreeSurfer-conformed 256x256x256 1mm grid           |
| MASSP Subcortical                       | 31      | ICBM152 2009b nonlinear asymmetric, hi-res 0.5mm    |
| Harvard-Oxford cortical, lateralized    | 96      | MNI152NLin6Asym, FSL 182x218x182 1mm grid           |
| Harvard-Oxford subcortical              | 21      | MNI152NLin6Asym, FSL 182x218x182 1mm grid           |
| Cerebellum-MNIfnirt (Diedrichsen 2009)  | 28      | MNI152NLin6Asym, FSL 182x218x182 1mm grid           |
| Schaefer 2018, 400 parcels / 7 networks | 400     | MNI152NLin6Asym, FSL 182x218x182 1mm grid           |

The four FSL-grid atlases sit on exactly the grid SimNIBS's `mni2subject` warps assume (their
headers were checked against the shipped `MNI152_T1_1mm.nii.gz`), so they need no template
correction; see [Which MNI template](#which-mni-template-and-how-far-off) for the other three.

Every one of them is a **label volume**, including Glasser: that is a cortical parcellation, but it
is distributed as a NIfTI, so you target it through the ROI picker's **Subcortical** mode, not the
**Cortical** mode. The picker knows which is which because each atlas declares it in
`resources/atlas/manifest.json`, and it will not offer you an atlas the mode you are in cannot read.
TI-Toolbox ships no MNI-space *surface* parcellation; the Cortical mode's atlases are your own
subject's, built by preprocessing.

In MNI space the Optimizer's and Analyzer's 3D pane has an **Explode** button beside **Clear
selection**: the scalp fades out and the atlas regions pull apart, mostly left from right, so deep
structures can be seen and clicked. Press it again to put them back. It only changes the view — the
selected regions stay selected.

## Licence, attribution and citation

Atlases are other people's data. If you publish work that used one, cite it; if you redistribute
TI-Toolbox, these are the terms you are redistributing under. Each row is also machine-readable in
`resources/atlas/manifest.json`.

| Atlas | Licence | May be redistributed | Cite |
| --- | --- | --- | --- |
| CIT168 Subcortical | CC BY 4.0 | Yes | Pauli W. M., Nili A. N., Tyszka J. M. *Scientific Data* 5:180063 (2018). [doi:10.1038/sdata.2018.63](https://doi.org/10.1038/sdata.2018.63) |
| MASSP 2021 Subcortical | CC BY 4.0 | Yes | Bazin P.-L. et al. *eLife* 9:e59430 (2020); atlas release [doi:10.21942/uva.19646328](https://doi.org/10.21942/uva.19646328) |
| Glasser HCP-MMP1.0 | WU-Minn HCP Open Access Data Use Terms | Yes, **under those same terms** | Glasser M. F. et al. *Nature* 536:171-178 (2016). [doi:10.1038/nature18933](https://doi.org/10.1038/nature18933) |
| Harvard-Oxford cortical / subcortical | CC BY-SA 4.0 ([FSL licence page](https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html)) | Yes, share-alike | Desikan R. S. et al. *NeuroImage* 31:968-980 (2006); Frazier J. A. et al. *Am J Psychiatry* 162:1256-1265 (2005); Makris N. et al. *Schizophr Res* 83:155-171 (2006) |
| Cerebellum-MNIfnirt | CC BY-SA 4.0 (same FSL sentence) | Yes, share-alike | Diedrichsen J. et al. *NeuroImage* 46:39-46 (2009). [doi:10.1016/j.neuroimage.2009.01.045](https://doi.org/10.1016/j.neuroimage.2009.01.045) |
| Schaefer 2018 400/7 | MIT (CBIG) | Yes | Schaefer A. et al. *Cerebral Cortex* 28:3095-3114 (2018). [doi:10.1093/cercor/bhx179](https://doi.org/10.1093/cercor/bhx179) |
| MNI152 T1 1mm template | MNI/McGill permissive (any purpose, without fee, keep the notice) | Yes | Copyright (C) 1993-2009 Louis Collins, McConnell Brain Imaging Centre, MNI, McGill University |

Using Glasser also carries an acknowledgement: *"Data were provided [in part] by the Human
Connectome Project, WU-Minn Consortium (Principal Investigators: David Van Essen and Kamil Ugurbil;
1U54MH091657) funded by the 16 NIH Institutes and Centers that support the NIH Blueprint for
Neuroscience Research; and by the McDonnell Center for Systems Neuroscience at Washington
University."*

The full notices, with copyright holders, are in the repository's `NOTICE` file.

Every shipped atlas names **one hemisphere per label**, apart from true midline structures
(cerebellar vermis, brain stem, third and fourth ventricle, fornix). Picking "Left-Putamen" targets
the left putamen only; to target both, pick both.

### Not shipped

**Bilateral CIT168 and Harvard-Oxford cortical** (`CIT168_labeling_MNI152NLin2009cAsym.nii.gz`,
`HarvardOxford-cort-maxprob-thr25-1mm.nii.gz`) were shipped until 2026-09-23. Each of their labels
covered a structure in *both* hemispheres, so choosing one region silently targeted both sides.
They were replaced by `CIT168_labeling_lateralized_MNI152NLin2009cAsym.nii.gz` (label k became
2k-1 left and 2k right) and FSL's own lateralized `HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz`
(same numbering). A configuration that still names an old file stops with a sentence naming its
replacement; pick the side(s) you meant from the new atlas.


**Morel thalamus atlas** (`MorelMNI152_labeling_1mm.nii.gz`, 74 nuclei) was shipped until
2026-09-17 and has been removed. Its licence is **CC BY-NC-SA 4.0** ([Zenodo record
13918589](https://doi.org/10.5281/zenodo.13918589); (C) University of Zurich and ETH Zurich, Andras
Jakab, Remi Blanc and Gabor Szekely), which forbids commercial use — a promise TI-Toolbox's own
GPL-3 licence cannot make for you, so a GPL-3 project cannot redistribute it. A configuration that
still names it stops with *"The Morel atlas is no longer shipped (CC BY-NC-SA); see
docs/wiki/atlases.md"*; pick another thalamic target (Harvard-Oxford subcortical or MASSP both label
the thalamus; neither subdivides it into nuclei) or, if your own use is non-commercial, fetch the
atlas from Zenodo yourself and import it as a custom NIfTI mask. The plan for bringing it back as an
optional, user-fetched download is recorded in `resources/atlas/README.md § Not shipped`. Cite,
if you use it: Krauth A. et al. *NeuroImage* 49(3):2053-2062 (2010); Jakab A. et al. *AJNR*
33(11):2110-2116 (2012).

## Which MNI template, and how far off

SimNIBS warps between MNI and your subject with the deformation fields `charm` wrote into
`m2m_<id>/toMNI/`, and those were computed against **FSL's `MNI152_T1_1mm.nii.gz`, i.e.
MNI152NLin6Asym**. CIT168 and Glasser are defined in MNI152NLin2009cAsym and MASSP in 2009b, so
their labels travel through a warp that targets a slightly different template. The templates differ
by roughly **1.3 mm** globally.

Measured on the `ernie` example subject, against `charm`'s own subcortical segmentation
(`m2m_ernie/segmentation/labeling.nii.gz`) for the same structure:

| Target | Distance between centroids |
| --- | --- |
| CIT168 putamen vs charm Left+Right-Putamen | 1.05 mm |
| CIT168 caudate vs charm Left+Right-Caudate | 2.20 mm |
| MASSP thalamus (left) vs charm Left-Thalamus | 2.00 mm |
| MASSP thalamus (right) vs charm Right-Thalamus | 1.19 mm |

That is the same order as the disagreement between two segmentations of the same structure, and it
is accepted rather than corrected. Every optimization and analysis writes a **ROI plate**
(`roi_plate.png`) showing the mask that will actually be used on your subject's own T1 — look at it
before you trust a deep target.

Pick an atlas from the dropdown to load it over the MNI152 template. The browser shows CIT168, Glasser and MASSP; the Harvard-Oxford, Cerebellum and Schaefer atlases are described below and offered in the ROI picker, but are not yet in this browser. Click any row in a label table below to jump the crosshair to that region's centroid — the viewer switches atlases automatically if needed. Only the template and the currently selected atlas are ever loaded.

<div class="atlas-viewer" data-space="mni">
  <div class="atlas-controls">
    <label for="atlas-select-mni">Atlas:</label>
    <select id="atlas-select-mni" class="atlas-select" data-space="mni">
      <option value="cit168">CIT168 Subcortical</option>
      <option value="glasser">Glasser HCP-MMP1.0</option>
      <option value="massp">MASSP Subcortical</option>
    </select>
    <span class="atlas-status" data-space="mni"></span>
  </div>
  <div class="atlas-canvas-wrap"><canvas id="atlas-canvas-mni" width="640" height="480"></canvas></div>
  <p class="atlas-hint">Overlay opacity is fixed at 70% over the grayscale MNI152 template. Colours match each atlas's own lookup table.</p>
</div>

<div class="atlas-no-webgl" data-space="mni" style="display:none;">
  <p><strong>Interactive viewer unavailable.</strong> Your browser does not support WebGL2, which the viewer requires. The label tables remain fully searchable — use the centroid column to locate a region in your own viewer.</p>
</div>

## CIT168 Subcortical Atlas

Pauli WM, Nili AN, Tyszka JM. A high-resolution probabilistic in vivo atlas of human subcortical brain nuclei. _Scientific Data_ 5:180063 (2018). doi:[10.1038/sdata.2018.63](https://doi.org/10.1038/sdata.2018.63).

The shipped volume is a **deterministic** label map, derived locally from the paper's probabilistic masks by winner-takes-highest-probability at a 0.05 minimum-probability threshold. The probability maps themselves are not shipped — only the resulting hard segmentation.

The published labeling is **bilateral** (16 labels, each covering a structure in both hemispheres). TI-Toolbox ships it **split at the midline** (x = 0 mm of its own template) since 2026-09-23: 32 labels, where the paper's label k is `2k-1` (`Left-…`, x < 0) and `2k` (`Right-…`, x ≥ 0), made by `dev/build_lateralized_atlases.py`. Nothing else about the map changes.

The label table below comes from the docs atlas browser, which still carries the 16 bilateral labels until its assets are regenerated with `dev/build_atlas_assets.py`; its centroids therefore fall near the midline.

<div class="atlas-table-tools">
  <input type="text" class="atlas-filter" data-target="table-mni-cit168" placeholder="Filter CIT168 regions by name or id…">
  <span class="atlas-count">{{ site.data.atlases.mni.atlases.cit168.rows | size }} regions</span>
</div>
<div class="atlas-table-scroll">
<table id="table-mni-cit168" data-space="mni" data-atlas="cit168">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (MNI, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.mni.atlases.cit168.rows %}
    <tr data-id="{{ row.id }}" data-mni="{{ row.centroid_mni | join: ',' }}">
      <td>{{ row.id }}</td>
      <td class="atlas-name">{{ row.name }}</td>
      <td><span class="atlas-swatch" style="background: rgb({{ row.r }}, {{ row.g }}, {{ row.b }});"></span></td>
      <td>{{ row.volume_mm3 }} mm&sup3;</td>
      <td>{{ row.centroid_mni | join: ", " }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>

<br>

## Glasser HCP-MMP1.0 Atlas

Glasser MF, Coalson TS, Robinson EC, et al. A multi-modal parcellation of human cerebral cortex. _Nature_ 536(7615):171-178 (2016). doi:[10.1038/nature18933](https://doi.org/10.1038/nature18933).

360 labels (180 per hemisphere), using the atlas's native sparse indexing scheme: left-hemisphere regions are numbered 1-180, right-hemisphere regions 1001-1180. The shipped volume is natively on a FreeSurfer-conformed 256x256x256 1mm grid, **not** the 182x218x182 MNI152 grid, so it was resampled onto the template grid for the viewer.

<div class="atlas-table-tools">
  <input type="text" class="atlas-filter" data-target="table-mni-glasser" placeholder="Filter Glasser regions by name or id…">
  <span class="atlas-count">{{ site.data.atlases.mni.atlases.glasser.rows | size }} regions</span>
</div>
<div class="atlas-table-scroll">
<table id="table-mni-glasser" data-space="mni" data-atlas="glasser">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (MNI, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.mni.atlases.glasser.rows %}
    <tr data-id="{{ row.id }}" data-mni="{{ row.centroid_mni | join: ',' }}">
      <td>{{ row.id }}</td>
      <td class="atlas-name">{{ row.name }}</td>
      <td><span class="atlas-swatch" style="background: rgb({{ row.r }}, {{ row.g }}, {{ row.b }});"></span></td>
      <td>{{ row.volume_mm3 }} mm&sup3;</td>
      <td>{{ row.centroid_mni | join: ", " }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>

<br>

## MASSP Subcortical Parcellation

31 labels, natively at 0.5mm resolution in ICBM152 2009b nonlinear-asymmetric hi-res space — the highest native resolution of the shipped atlases. It was resampled onto the 1mm template grid for the viewer.

<div class="atlas-table-tools">
  <input type="text" class="atlas-filter" data-target="table-mni-massp" placeholder="Filter MASSP regions by name or id…">
  <span class="atlas-count">{{ site.data.atlases.mni.atlases.massp.rows | size }} regions</span>
</div>
<div class="atlas-table-scroll">
<table id="table-mni-massp" data-space="mni" data-atlas="massp">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (MNI, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.mni.atlases.massp.rows %}
    <tr data-id="{{ row.id }}" data-mni="{{ row.centroid_mni | join: ',' }}">
      <td>{{ row.id }}</td>
      <td class="atlas-name">{{ row.name }}</td>
      <td><span class="atlas-swatch" style="background: rgb({{ row.r }}, {{ row.g }}, {{ row.b }});"></span></td>
      <td>{{ row.volume_mm3 }} mm&sup3;</td>
      <td>{{ row.centroid_mni | join: ", " }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>

## Harvard-Oxford Cortical and Subcortical Atlases

The FSL structural atlases from the Harvard Center for Morphometric Analysis, shipped as the
maximum-probability maps at the 25 % threshold, 1 mm (`HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz`,
FSL's **lateralized** cortical map, 96 labels = 48 structures x left/right, odd = left, even =
right; `HarvardOxford-sub-maxprob-thr25-1mm.nii.gz`, 21 subcortical labels). The files are FSL's
own, unmodified (NeuroDebian `fsl-harvard-oxford-cortical-lateralized-atlas` and
`fsl-harvard-oxford-atlases`, both 5.0.7-2); the label names come from FSL's XML, with ids = XML
index + 1 as FSL's `maxprob` images encode them. Until 2026-09-23 the non-lateralized 48-label
cortical map was shipped instead, whose labels each covered both hemispheres.

Licence CC BY-SA 4.0 — the FSL licence page states that "The Cerebellum and Harvard-Oxford atlases,
whilst not being the property of Oxford, are released under the CC BY-SA 4.0 licence".

The subcortical map labels the thalamus, caudate, putamen, pallidum, hippocampus, amygdala,
accumbens and brain stem per hemisphere, plus whole-hemisphere cortex / white matter and the
ventricles (kept so the file is unmodified; they are not TI targets). Both maps are natively on the
FSL 182x218x182 1 mm grid, the same grid as the shipped template.

## Cerebellum-MNIfnirt Atlas

Diedrichsen J., Balsters J. H., Flavell J., Cussans E., Ramnani N. A probabilistic MR atlas of the
human cerebellum. _NeuroImage_ 46(1):39-46 (2009).
doi:[10.1016/j.neuroimage.2009.01.045](https://doi.org/10.1016/j.neuroimage.2009.01.045).

The FNIRT-normalised maximum-probability map at the 25 % threshold, 1 mm
(`Cerebellum-MNIfnirt-maxprob-thr25-1mm.nii.gz`, 28 labels: lobules I-IV to X, left / right /
vermis). CC BY-SA 4.0 by the same FSL sentence as Harvard-Oxford. Natively on the FSL 1 mm grid.

## Schaefer 2018 Atlas (400 parcels, 7 networks)

Schaefer A., Kong R., Gordon E. M., Laumann T. O., Zuo X.-N., Holmes A. J., Eickhoff S. B.,
Yeo B. T. T. Local-global parcellation of the human cerebral cortex from intrinsic functional
connectivity MRI. _Cerebral Cortex_ 28(9):3095-3114 (2018).
doi:[10.1093/cercor/bhx179](https://doi.org/10.1093/cercor/bhx179).

`Schaefer2018_400Parcels_7Networks_order_FSLMNI152_1mm.nii.gz` from ThomasYeoLab/CBIG (MIT), with
CBIG's own LUT. 400 cortical parcels — 1-200 left, 201-400 right — each named by its Yeo 7-network
membership (`7Networks_LH_Vis_1`, `7Networks_RH_Default_PFCdPFCm_3`, …). Its header matches the
shipped FSL `MNI152_T1_1mm.nii.gz` exactly, so it is on the MNI152NLin6Asym grid. Like Glasser it is
a cortical parcellation distributed as a label volume, so you target it through the picker's
**Subcortical** mode.

---

# Subject-Space Atlases

These are **not shipped**. They are produced for each subject during preprocessing, and live under that subject's own derivatives:

- **SimNIBS `charm`** writes the tissue segmentation `m2m_{subject}/segmentation/labeling.nii.gz`, plus the surface parcellations `lh/rh.{subject}_DK40.annot`, `_a2009s.annot` and `_HCP_MMP1.annot`.
- **FastSurfer `--seg_only` (v3)** writes `aparc.DKTatlas+aseg.deep.mgz`. It does not produce thalamic nuclei or hippocampal/amygdala subregion atlases. See [pre-processing]({{ site.baseurl }}/wiki/pre-processing/#what-changed-from-freesurfer).
- **Optional FreeSurfer `recon-all`** produces the volumetric parcellations `aparc.DKTatlas+aseg.mgz`, `aparc.a2009s+aseg.mgz`, `aparc+aseg.mgz` and `aseg.mgz`, with finer thalamic nuclei and hippocampal/amygdala subregions available as additional operations after reconstruction. Existing `ThalamicNuclei.v13.T1.mgz` and `lh/rh.hippoAmygLabels-T1.v22.mgz` outputs remain readable.

The gallery includes legacy FreeSurfer atlases for reference; their presence here does not mean a new v3 FastSurfer run produces them.

The viewer below uses the **`ernie` example subject** that ships with SimNIBS, so the anatomy is a real head model rather than a template average. The surface `.annot` parcellations are not shown — they are cortical surface files, not volumes, and cannot be overlaid on a NIfTI.

**Read the coordinates as subject space.** The centroid column here is in ernie's own scanner/world coordinates, **not** MNI. The same structure will sit at different coordinates in your own subject.

<div class="atlas-viewer" data-space="subject">
  <div class="atlas-controls">
    <label for="atlas-select-subject">Atlas:</label>
    <select id="atlas-select-subject" class="atlas-select" data-space="subject">
      <option value="charm">CHARM tissue labeling</option>
      <option value="dkt">Desikan-Killiany-Tourville (aparc.DKTatlas+aseg)</option>
      <option value="a2009s">Destrieux (aparc.a2009s+aseg)</option>
      <option value="massp">MASSP subcortical (subject space)</option>
    </select>
    <span class="atlas-status" data-space="subject"></span>
  </div>
  <div class="atlas-canvas-wrap"><canvas id="atlas-canvas-subject" width="640" height="480"></canvas></div>
  <p class="atlas-hint">Overlaid on ernie's own T1, not a template. Colours come from each atlas's lookup table — the FreeSurfer parcellations use the standard <code>FreeSurferColorLUT.txt</code> shipped in <code>resources/atlas/</code>.</p>
</div>

<div class="atlas-no-webgl" data-space="subject" style="display:none;">
  <p><strong>Interactive viewer unavailable.</strong> Your browser does not support WebGL2. The label tables remain fully searchable.</p>
</div>

<br>

## CHARM Tissue Labeling

Produced by SimNIBS `charm` as `m2m_{subject}/segmentation/labeling.nii.gz`, with its own `labeling_LUT.txt` alongside. This is the **tissue** segmentation the head model is built from — grey and white matter, CSF, skull, scalp and the rest — not a cortical parcellation. It is what the analyzer reads when you pick a tissue-level ROI in voxel space.

<div class="atlas-table-tools">
  <input type="text" class="atlas-filter" data-target="table-subject-charm" placeholder="Filter CHARM labels by name or id…">
  <span class="atlas-count">{{ site.data.atlases.subject.atlases.charm.rows | size }} regions</span>
</div>
<div class="atlas-table-scroll">
<table id="table-subject-charm" data-space="subject" data-atlas="charm">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (subject, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.subject.atlases.charm.rows %}
    <tr data-id="{{ row.id }}" data-mni="{{ row.centroid_mni | join: ',' }}">
      <td>{{ row.id }}</td>
      <td class="atlas-name">{{ row.name }}</td>
      <td><span class="atlas-swatch" style="background: rgb({{ row.r }}, {{ row.g }}, {{ row.b }});"></span></td>
      <td>{{ row.volume_mm3 }} mm&sup3;</td>
      <td>{{ row.centroid_mni | join: ", " }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>

<br>

## Desikan-Killiany-Tourville (aparc.DKTatlas+aseg)

FreeSurfer `recon-all` output combining the DKT cortical parcellation with the `aseg` subcortical segmentation in one volume. Klein A, Tourville J. 101 labeled brain images and a consistent human cortical labeling protocol. _Frontiers in Neuroscience_ 6:171 (2012). doi:[10.3389/fnins.2012.00171](https://doi.org/10.3389/fnins.2012.00171).

Cortical labels use FreeSurfer's `1000+`/`2000+` convention (left/right hemisphere); subcortical structures keep their `aseg` ids below 100. This is one of the voxel atlases the analyzer offers.

<div class="atlas-table-tools">
  <input type="text" class="atlas-filter" data-target="table-subject-dkt" placeholder="Filter DKT regions by name or id…">
  <span class="atlas-count">{{ site.data.atlases.subject.atlases.dkt.rows | size }} regions</span>
</div>
<div class="atlas-table-scroll">
<table id="table-subject-dkt" data-space="subject" data-atlas="dkt">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (subject, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.subject.atlases.dkt.rows %}
    <tr data-id="{{ row.id }}" data-mni="{{ row.centroid_mni | join: ',' }}">
      <td>{{ row.id }}</td>
      <td class="atlas-name">{{ row.name }}</td>
      <td><span class="atlas-swatch" style="background: rgb({{ row.r }}, {{ row.g }}, {{ row.b }});"></span></td>
      <td>{{ row.volume_mm3 }} mm&sup3;</td>
      <td>{{ row.centroid_mni | join: ", " }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>

<br>

## Destrieux (aparc.a2009s+aseg)

FreeSurfer `recon-all` output combining the Destrieux cortical parcellation with `aseg`. Destrieux C, Fischl B, Dale A, Halgren E. Automatic parcellation of human cortical gyri and sulci using standard anatomical nomenclature. _NeuroImage_ 53(1):1-15 (2010). doi:[10.1016/j.neuroimage.2010.06.010](https://doi.org/10.1016/j.neuroimage.2010.06.010).

The finest of the cortical parcellations here, splitting cortex into gyral (`G_`) and sulcal (`S_`) units. Cortical ids run in the `11100+`/`12100+` range.

<div class="atlas-table-tools">
  <input type="text" class="atlas-filter" data-target="table-subject-a2009s" placeholder="Filter Destrieux regions by name or id…">
  <span class="atlas-count">{{ site.data.atlases.subject.atlases.a2009s.rows | size }} regions</span>
</div>
<div class="atlas-table-scroll">
<table id="table-subject-a2009s" data-space="subject" data-atlas="a2009s">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (subject, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.subject.atlases.a2009s.rows %}
    <tr data-id="{{ row.id }}" data-mni="{{ row.centroid_mni | join: ',' }}">
      <td>{{ row.id }}</td>
      <td class="atlas-name">{{ row.name }}</td>
      <td><span class="atlas-swatch" style="background: rgb({{ row.r }}, {{ row.g }}, {{ row.b }});"></span></td>
      <td>{{ row.volume_mm3 }} mm&sup3;</td>
      <td>{{ row.centroid_mni | join: ", " }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>

<br>

## MASSP Subcortical (Subject Space)

The bundled MNI MASSP parcellation warped into the subject's own space, written by preprocessing as `m2m_{subject}/segmentation/massp2021_subject.nii.gz`. Same 31 labels as the [MNI-space MASSP](#massp-subcortical-parcellation) above, and the same provenance caveat applies — no citation, license or DOI is recorded in this repository.

Comparing this table with the MNI one is a useful check on how far a subject's subcortical anatomy departs from the template.

<div class="atlas-table-tools">
  <input type="text" class="atlas-filter" data-target="table-subject-massp" placeholder="Filter MASSP regions by name or id…">
  <span class="atlas-count">{{ site.data.atlases.subject.atlases.massp.rows | size }} regions</span>
</div>
<div class="atlas-table-scroll">
<table id="table-subject-massp" data-space="subject" data-atlas="massp">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (subject, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.subject.atlases.massp.rows %}
    <tr data-id="{{ row.id }}" data-mni="{{ row.centroid_mni | join: ',' }}">
      <td>{{ row.id }}</td>
      <td class="atlas-name">{{ row.name }}</td>
      <td><span class="atlas-swatch" style="background: rgb({{ row.r }}, {{ row.g }}, {{ row.b }});"></span></td>
      <td>{{ row.volume_mm3 }} mm&sup3;</td>
      <td>{{ row.centroid_mni | join: ", " }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>

<br>

## Atlas Resampling

Voxel-space ROI analysis requires the atlas and the field NIfTI to sit on the **same voxel grid**. They often do not: the field is written on the simulation's grid, while a subject-space parcellation comes off `recon-all` at whatever resolution that ran at. Before masking, `Analyzer` brings the atlas onto the field's grid so the two are compared voxel-for-voxel.

<a href="{{ site.baseurl }}/assets/imgs/atlas-resampling/atlas_resample_validation.png">
  <img src="{{ site.baseurl }}/assets/imgs/atlas-resampling/atlas_resample_validation.png" alt="Voxel-level validation of atlas resampling" style="width: 100%; max-width: 1000px;">
</a>

_Validation on sub-ernie with the DKT parcellation. **Top:** an atlas cropped to the field's dimensions keeps its own affine, so the shapes match but the geometry does not — a shape-only check passes it straight through and the parcellation lands on the wrong anatomy, with only 13% of labelled voxels agreeing with where they belong. Comparing the affine as well forces the resample, and agreement goes to 100%. **Bottom:** on a 0.5 mm target grid, voxel centres fall between source centres. An interpolating order blends neighbouring region ids and produces 3,708 values (1.80% of voxels, magenta) that exist in neither the atlas nor `FreeSurferColorLUT.txt`; nearest-neighbour produces none. Axial slices, neurological convention._

### ROI analysis on the corrected grid

<a href="{{ site.baseurl }}/assets/imgs/atlas-resampling/atlas_resample_roi_analysis.png">
  <img src="{{ site.baseurl }}/assets/imgs/atlas-resampling/atlas_resample_roi_analysis.png" alt="Left insula and left thalamus ROI analysis on the corrected grid" style="width: 100%; max-width: 1000px;">
</a>

\_Two ROI analyses on sub-ernie, each shown as the region on the subject T1, the TI field it sits in, and the statistics the analyzer reports once the atlas is on the field grid. **Left insula** (`L_Insula` simulation): 6,528 voxels, mean 0.076 V/m. **Left thalamus** (`Thalamus` simulation): 8,045 voxels, mean 0.127 V/m. The cyan outline is the atlas region; the coloured area is that region intersected with the tissue.

**A grid is a shape _and_ an affine.** A volume is left untouched only when it already matches the field on both. Shape alone does not identify a grid — two volumes can agree on dimensions while sampling entirely different anatomy, and that case is silent: the analysis returns an ROI mask, statistics and a CSV, all describing the wrong tissue.

**Labels are discrete, so the interpolation order is nearest-neighbour, always.** Atlases carry region ids and tissue masks carry 0/1 flags. Any interpolating order averages neighbouring values, and the average of two region ids is a third id belonging to some unrelated structure — or to nothing at all. The resample uses `nibabel.processing.resample_from_to(..., order=0)`; voxels falling outside the source field of view become 0 (background). The same routine handles tissue-mask NIfTIs, and both `.nii`/`.nii.gz` and FreeSurfer `.mgz` atlases are accepted.

**Caching.** The result is written next to the original atlas as `{atlas_stem}_resampled_{width}x{height}x{depth}_{grid}.nii.gz`, where `{grid}` is a short hash of the target affine — part of the key for the same reason it is part of the equality check. A later analysis on the same grid reuses that file, so the cost is paid once per (atlas, grid) pair. Original atlas files are never modified, and caching is best-effort: if the atlas directory is not writable, the analysis proceeds on the in-memory result rather than failing.

Resampling is logged at INFO level, so a mismatch is visible in the analyzer's log rather than silent:

```
INFO | tit.analyzer | Resampling aparc.DKTatlas+aseg.mgz: (256, 256, 256) -> (256, 256, 208) (nearest-neighbour)
```

<br>

## See Also

- [Analyzer]({{ site.baseurl }}/wiki/analyzer/) — the primary consumer of ROI/atlas selection
- [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/) — how the subject-space atlases get generated
- Return to [Wiki]({{ site.baseurl }}/wiki/)

<script type="application/json" id="atlas-data">{{ site.data.atlases | jsonify }}</script>
<script src="{{ '/assets/js/niivue.min.js' | relative_url }}"></script>
<!-- ?v= is a cache buster. This page's element ids changed when the browser
     gained a second viewer, and an older cached copy of atlas-browser.js
     silently does nothing against the new markup (it looks for ids that no
     longer exist), leaving both canvases black. Bump v whenever the markup
     contract or the script changes. -->
<script src="{{ '/assets/js/atlas-browser.js' | relative_url }}?v=2"></script>

<style>
.atlas-viewer {
  margin: 1.5rem 0;
}
.atlas-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}
.atlas-controls select {
  padding: 0.3rem 0.5rem;
  max-width: 100%;
}
.atlas-status {
  color: #666;
  font-size: 0.9rem;
  min-height: 1.2em;
}
.atlas-canvas-wrap {
  height: 480px;
  background: #000;
  border-radius: 4px;
  overflow: hidden;
}
.atlas-viewer canvas {
  width: 100%;
  height: 100%;
  display: block;
}
.atlas-hint {
  font-size: 0.85rem;
  color: #666;
  margin-top: 0.5rem;
}
.atlas-no-webgl {
  padding: 1rem 1.25rem;
  border-left: 4px solid #c0392b;
  background: #fdf2f2;
  margin: 1.5rem 0;
}
.atlas-table-tools {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1.5rem 0 0.5rem;
  flex-wrap: wrap;
}
.atlas-table-tools input {
  flex: 1 1 260px;
  max-width: 420px;
  padding: 0.4rem 0.6rem;
  box-sizing: border-box;
}
.atlas-count {
  font-size: 0.85rem;
  color: #666;
  white-space: nowrap;
}
/* Show roughly seven rows, then scroll, so a 360-row table does not run away
   with the page. The header stays put while the body scrolls. */
.atlas-table-scroll {
  max-height: 23rem;
  overflow-y: auto;
  overflow-x: auto;
  border: 1px solid #e2e2e2;
  border-radius: 4px;
}
.atlas-table-scroll table {
  margin: 0;
  border: 0;
}
.atlas-table-scroll thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #fff;
  box-shadow: inset 0 -1px 0 #e2e2e2;
}
.atlas-swatch {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  border: 1px solid rgba(0, 0, 0, 0.25);
  vertical-align: middle;
}
table[data-atlas] tbody tr {
  cursor: pointer;
}
table[data-atlas] tbody tr:hover {
  background: rgba(0, 0, 0, 0.05);
}
table[data-atlas] mark {
  background: #fff3a3;
  padding: 0 2px;
}
</style>

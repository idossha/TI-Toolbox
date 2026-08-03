---
layout: wiki
title: Brain Atlases
permalink: /wiki/atlases/
---

## Overview

Atlases reach TI-Toolbox two different ways, and the distinction matters when you define an ROI:

- **[MNI-space atlases](#mni-space-atlases)** are *shipped with the toolbox* as ready-to-use NIfTI volumes in `resources/atlas/`. They are the same four volumes for every user, and SimNIBS transforms a selected label into your subject's space at run time.
- **[Subject-space atlases](#subject-space-atlases)** are *generated per subject* during preprocessing by SimNIBS `charm` and FreeSurfer `recon-all`. Nothing is shipped — they only exist once you have run the pipeline on a head model. The browser below uses the `ernie` example subject so you can see what they look like.

Both families are queried through the same ROI picker used in flex-search, ex-search, and the analyzer.

> **About the volumes behind the viewers.** The `.nii.gz` files this page loads are display copies, not the files the toolbox uses. Templates are requantised to 8-bit, atlases are resampled onto their template's grid, and label values are renumbered to a compact `1..N` so the colour lookup stays within the texture size limit some GPUs impose. The **ID** column in every table below is the atlas's real label — the number you pass to an ROI — not the renumbered display value. The atlases the toolbox actually reads are untouched in `resources/atlas/` and in each subject's derivatives.

| | MNI-space | Subject-space |
|---|---|---|
| Shipped with the toolbox | Yes, in `resources/atlas/` | No — generated per subject |
| Same for every user | Yes | No |
| Produced by | Bundled with TI-Toolbox | `charm` and `recon-all` |
| Selected as | Atlas file + label id | Atlas file + label id, or a surface region name |

---

# MNI-Space Atlases

TI-Toolbox ships four atlases as MNI-space NIfTI volumes:

| Atlas | Regions | Native space |
|-------|---------|--------------|
| CIT168 Subcortical | 16 | MNI152NLin2009cAsym |
| Morel Thalamus | 74 | MNI152, FSL-aligned 182x218x182 1mm grid |
| Glasser HCP-MMP1.0 | 360 | FreeSurfer-conformed 256x256x256 1mm grid |
| MASSP Subcortical | 31 | ICBM152 2009b nonlinear asymmetric, hi-res 0.5mm |

**Accuracy note.** The viewer draws every atlas on the same grid as the shipped `MNI152_T1_1mm.nii.gz` template (FSL-derived, 182x218x182, 1mm isotropic — most likely MNI152NLin6Asym, though the repository does not record the exact template variant). Only the Morel atlas is natively on that grid. CIT168, Glasser, and MASSP were resampled onto it with nearest-neighbour interpolation for display, and their native spaces differ from the template. The overlays are therefore approximate and are not a substitute for the original shipped volumes if you need exact voxel-for-voxel correspondence.

Pick an atlas from the dropdown to load it over the MNI152 template. Click any row in a label table below to jump the crosshair to that region's centroid — the viewer switches atlases automatically if needed. Only the template and the currently selected atlas are ever loaded.

<div class="atlas-viewer" data-space="mni">
  <div class="atlas-controls">
    <label for="atlas-select-mni">Atlas:</label>
    <select id="atlas-select-mni" class="atlas-select" data-space="mni">
      <option value="cit168">CIT168 Subcortical</option>
      <option value="morel">Morel Thalamus</option>
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

Pauli WM, Nili AN, Tyszka JM. A high-resolution probabilistic in vivo atlas of human subcortical brain nuclei. *Scientific Data* 5:180063 (2018). doi:[10.1038/sdata.2018.63](https://doi.org/10.1038/sdata.2018.63).

The shipped volume is a **deterministic** label map, derived locally from the paper's probabilistic masks by winner-takes-highest-probability at a 0.05 minimum-probability threshold. The probability maps themselves are not shipped — only the resulting hard segmentation.

All 16 labels are **bilateral**: each label merges the left and right instance of a structure into one region (e.g. "Putamen" covers both hemispheres). There are no separate left/right label pairs, so this atlas has 16 structures total, not 8 per hemisphere.

One consequence for the viewer: because a bilateral label spans both hemispheres, its centroid falls near the midline. Clicking a CIT168 row centres the crosshair between the two instances of the structure rather than on either one — scroll laterally in the axial view to reach them. The other atlases label left and right separately, so their centroids are properly lateralised.

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

## Morel Thalamus Atlas

> **License: CC BY-NC-SA 4.0 (Attribution-NonCommercial-ShareAlike).** &copy; University of Zurich and ETH Zurich; Andras Jakab, Remi Blanc, Gabor Szekely. This is the only one of the four shipped atlases with a non-permissive license — republishing or reusing it commercially is not permitted without separate arrangement with the copyright holders.

Source: Morel Atlas of the Human Thalamus, MNI152 space, voxelized version. Zenodo doi:[10.5281/zenodo.13918589](https://doi.org/10.5281/zenodo.13918589).

Cite: Jakab et al. *AJNR* 33(11):2110-2116 (2012); Krauth et al. *NeuroImage* 49(3):2053-2062 (2010).

The source LUT declares 76 labels (38 nuclei/structures per hemisphere), but 2 of them — ids 27 and 127, both "sPf" (subparafascicular nucleus) — have zero voxels in the shipped volume after the source atlas's overlap-resolution rule. The table lists the 74 labels that are actually present.

This is the only one of the four atlases natively on the same 182x218x182 1mm grid as the shipped MNI152 template, so it required no resampling.

<div class="atlas-table-tools">
  <input type="text" class="atlas-filter" data-target="table-mni-morel" placeholder="Filter Morel regions by name or id…">
  <span class="atlas-count">{{ site.data.atlases.mni.atlases.morel.rows | size }} regions</span>
</div>
<div class="atlas-table-scroll">
<table id="table-mni-morel" data-space="mni" data-atlas="morel">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (MNI, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.mni.atlases.morel.rows %}
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

## Glasser HCP-MMP1.0 Atlas

Glasser MF, Coalson TS, Robinson EC, et al. A multi-modal parcellation of human cerebral cortex. *Nature* 536(7615):171-178 (2016). doi:[10.1038/nature18933](https://doi.org/10.1038/nature18933).

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

## MASSP Subcortical Parcellation

**Provenance not recorded in this repository — no citation, license, or DOI is shipped with this atlas.** `resources/atlas/README.md` documents only its filename and a usage caveat; there is no reference to an upstream paper anywhere in the codebase. The filename (`massp2021-parcellation_decade-18to40.nii.gz`) suggests an age-stratified template (18-40 year decade), implying other variants exist upstream, but none of that is verifiable from this repository. Treat the region names and colours as provisional until a source is confirmed.

31 labels, natively at 0.5mm resolution in ICBM152 2009b nonlinear-asymmetric hi-res space — the highest native resolution of the four shipped atlases. It was resampled onto the 1mm template grid for the viewer.

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

---

# Subject-Space Atlases

These are **not shipped**. They are produced for each subject during preprocessing, and live under that subject's own derivatives:

- **SimNIBS `charm`** writes the tissue segmentation `m2m_{subject}/segmentation/labeling.nii.gz`, plus the surface parcellations `lh/rh.{subject}_DK40.annot`, `_a2009s.annot` and `_HCP_MMP1.annot`.
- **FreeSurfer `recon-all`** writes the volumetric parcellations `aparc.DKTatlas+aseg.mgz`, `aparc.a2009s+aseg.mgz`, `aparc+aseg.mgz` and `aseg.mgz`, along with the finer `ThalamicNuclei.v13.T1.mgz` and `lh/rh.hippoAmygLabels-T1.v22.mgz` segmentations.

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

## Desikan-Killiany-Tourville (aparc.DKTatlas+aseg)

FreeSurfer `recon-all` output combining the DKT cortical parcellation with the `aseg` subcortical segmentation in one volume. Klein A, Tourville J. 101 labeled brain images and a consistent human cortical labeling protocol. *Frontiers in Neuroscience* 6:171 (2012). doi:[10.3389/fnins.2012.00171](https://doi.org/10.3389/fnins.2012.00171).

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

## Destrieux (aparc.a2009s+aseg)

FreeSurfer `recon-all` output combining the Destrieux cortical parcellation with `aseg`. Destrieux C, Fischl B, Dale A, Halgren E. Automatic parcellation of human cortical gyri and sulci using standard anatomical nomenclature. *NeuroImage* 53(1):1-15 (2010). doi:[10.1016/j.neuroimage.2010.06.010](https://doi.org/10.1016/j.neuroimage.2010.06.010).

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

## Surface Parcellations (Not Shown Here)

`charm` also writes three cortical **surface** parcellations per subject as FreeSurfer `.annot` files under `m2m_{subject}/segmentation/`: DK40 (Desikan-Killiany), a2009s (Destrieux) and HCP_MMP1 (Glasser). These are what the analyzer uses in *mesh* space, and what the ROI picker offers as hemisphere-prefixed region names like `lh.precentral`.

They are not in the viewer above because they label surface vertices rather than voxels. Per the toolbox documentation DK40 has 68 regions, a2009s 148, and HCP_MMP1 360 — these are documentation claims, not values computed anywhere in the codebase.

## See Also

- [Atlas Resampling]({{ site.baseurl }}/wiki/atlas-resampling/) — how the toolbox aligns an atlas to a subject's field data
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

---
layout: wiki
title: Brain Atlases
permalink: /wiki/atlases/
---

## Overview

TI-Toolbox ships four brain atlases as MNI-space NIfTI volumes, browsable below. These are separate from the **per-subject atlases** that SimNIBS and FreeSurfer generate during preprocessing (DK40, a2009s, HCP_MMP1 surface parcellations, and a set of FreeSurfer voxel segmentations) — those are computed per subject and are not distributed with the toolbox. See [Per-Subject Atlases](#per-subject-atlases-not-shipped) below.

The four shipped MNI atlases are:

| Atlas | Regions | Native space |
|-------|---------|--------------|
| CIT168 Subcortical | 16 | MNI152NLin2009cAsym |
| Morel Thalamus | 74 | MNI152, FSL-aligned 182x218x182 1mm grid |
| Glasser HCP-MMP1.0 | 360 | FreeSurfer-conformed 256x256x256 1mm grid |
| MASSP Subcortical | 31 | ICBM152 2009b nonlinear asymmetric, hi-res 0.5mm |

## Accuracy Note

The viewer below draws every atlas on the same grid as the shipped `MNI152_T1_1mm.nii.gz` template (FSL-derived, 182x218x182, 1mm isotropic — most likely MNI152NLin6Asym, though the repository does not record the exact template variant). Only the Morel atlas is natively on that grid. CIT168, Glasser, and MASSP were resampled onto it with nearest-neighbour interpolation for display, and their native spaces differ from the template (2009cAsym, a FreeSurfer-conformed grid, and 2009b hi-res, respectively). The overlays here are therefore approximate and should not be treated as a substitute for the original shipped volumes if you need exact voxel-for-voxel correspondence.

## Interactive Viewer

Pick an atlas from the dropdown to load it over the MNI152 template. Click any row in a label table further down the page to jump the crosshair to that region's MNI centroid — the viewer will switch atlases automatically if needed. Only the template and the currently selected atlas are ever loaded; switching atlases fetches just that one volume.

<div id="atlas-viewer" class="atlas-viewer">
  <div class="atlas-controls">
    <label for="atlas-select">Atlas:</label>
    <select id="atlas-select">
      <option value="cit168">CIT168 Subcortical</option>
      <option value="morel">Morel Thalamus</option>
      <option value="glasser">Glasser HCP-MMP1.0</option>
      <option value="massp">MASSP Subcortical</option>
    </select>
    <span id="atlas-status" class="atlas-status"></span>
  </div>
  <canvas id="atlas-canvas" width="640" height="480"></canvas>
  <p class="atlas-hint">Overlay opacity is fixed at 70% over the grayscale MNI152 template. Colours match each atlas's own lookup table.</p>
</div>

<div id="atlas-no-webgl" class="atlas-no-webgl" style="display:none;">
  <p><strong>Interactive viewer unavailable.</strong> Your browser does not support WebGL2, which the viewer requires. The label tables below remain fully searchable — use the MNI centroid column to locate a region in your own viewer.</p>
</div>

<script type="application/json" id="atlas-data">{{ site.data.atlases | jsonify }}</script>
<script src="{{ '/assets/js/niivue.min.js' | relative_url }}"></script>
<script src="{{ '/assets/js/atlas-browser.js' | relative_url }}"></script>

## CIT168 Subcortical Atlas

Pauli WM, Nili AN, Tyszka JM. A high-resolution probabilistic in vivo atlas of human subcortical brain nuclei. *Scientific Data* 5:180063 (2018). doi:[10.1038/sdata.2018.63](https://doi.org/10.1038/sdata.2018.63).

The shipped volume is a **deterministic** label map, derived locally from the paper's probabilistic masks by winner-takes-highest-probability at a 0.05 minimum-probability threshold. The probability maps themselves are not shipped — only the resulting hard segmentation.

All 16 labels are **bilateral**: each label merges the left and right instance of a structure into one region (e.g. "Putamen" covers both hemispheres). There are no separate left/right label pairs, so this atlas has 16 structures total, not 8 per hemisphere.

One consequence for the viewer above: because a bilateral label spans both hemispheres, its centroid falls near the midline. Clicking a CIT168 row therefore centres the crosshair between the two instances of the structure rather than on either one — scroll laterally in the axial view to reach them. The other three atlases label left and right separately, so their centroids are properly lateralised.

<div class="atlas-table-tools">
  <input type="text" id="filter-cit168" class="atlas-filter" data-target="table-cit168" placeholder="Filter CIT168 regions by name or id...">
</div>
<div class="table-wrap">
<table id="table-cit168" data-atlas="cit168">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (MNI, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.cit168.rows %}
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

The source LUT declares 76 labels (38 nuclei/structures per hemisphere), but 2 of them — ids 27 and 127, both "sPf" (subparafascicular nucleus) — have zero voxels in the shipped volume after the source atlas's overlap-resolution rule. The table below lists the 74 labels that are actually present.

This is the only one of the four atlases that is natively on the same 182x218x182 1mm grid as the shipped MNI152 template, so it required no resampling for the viewer above.

<div class="atlas-table-tools">
  <input type="text" id="filter-morel" class="atlas-filter" data-target="table-morel" placeholder="Filter Morel regions by name or id...">
</div>
<div class="table-wrap">
<table id="table-morel" data-atlas="morel">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (MNI, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.morel.rows %}
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

360 labels (180 per hemisphere), using the atlas's native sparse indexing scheme: left-hemisphere regions are numbered 1-180, right-hemisphere regions 1001-1180. The shipped volume is natively on a FreeSurfer-conformed 256x256x256 1mm grid, **not** the 182x218x182 MNI152 grid the other three atlases (after resampling) share with the template — it was resampled onto the template grid for the viewer above.

<div class="atlas-table-tools">
  <input type="text" id="filter-glasser" class="atlas-filter" data-target="table-glasser" placeholder="Filter Glasser regions by name or id...">
</div>
<div class="table-wrap">
<table id="table-glasser" data-atlas="glasser">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (MNI, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.glasser.rows %}
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

**Provenance not recorded in this repository — no citation, license, or DOI is shipped with this atlas.** `resources/atlas/README.md` documents only its filename and a usage caveat; there is no reference to an upstream paper anywhere in the codebase. The filename (`massp2021-parcellation_decade-18to40.nii.gz`) suggests an age-stratified template (18-40 year decade), implying other age-stratified variants exist upstream, but none of that is verifiable from this repository. Treat the region names and colours as provisional until a source is confirmed.

31 labels, natively at 0.5mm resolution in ICBM152 2009b nonlinear-asymmetric hi-res space — the highest native resolution of the four shipped atlases. It was resampled onto the 1mm template grid for the viewer above.

<div class="atlas-table-tools">
  <input type="text" id="filter-massp" class="atlas-filter" data-target="table-massp" placeholder="Filter MASSP regions by name or id...">
</div>
<div class="table-wrap">
<table id="table-massp" data-atlas="massp">
  <thead>
    <tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (MNI, mm)</th></tr>
  </thead>
  <tbody>
    {% for row in site.data.atlases.massp.rows %}
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

## Per-Subject Atlases (Not Shipped)

The four atlases above are the only ones distributed as ready-to-use MNI-space volumes. TI-Toolbox also generates **per-subject** cortical atlases during preprocessing, once a subject's head model exists — these are not shipped because they only make sense in that subject's own space:

- **Mesh (surface) atlases** — DK40 (Desikan-Killiany), a2009s (Destrieux), and HCP_MMP1 (Glasser) are generated via the `subject_atlas` tool after CHARM segmentation and written as FreeSurfer `.annot` files under `m2m_{subject}/segmentation/`. According to the toolbox documentation, DK40 has 68 regions, a2009s has 148, and HCP_MMP1 has 360 — these counts are documentation claims, not values computed anywhere in the codebase, since nothing in the repository enumerates them independently of the SimNIBS/FreeSurfer templates that generate them.
- **Voxel atlases** — a set of FreeSurfer `recon-all` outputs used for volumetric ROI analysis: `aparc.DKTatlas+aseg.mgz`, `aparc.a2009s+aseg.mgz`, `lh.hippoAmygLabels-T1.v22.mgz`, `rh.hippoAmygLabels-T1.v22.mgz`, and `ThalamicNuclei.v13.T1.mgz`, plus the SimNIBS CHARM tissue segmentation (`labeling.nii.gz`). Like the mesh atlases, these only exist after a subject has been preprocessed.

Both families are queried through the same ROI picker used in flex-search, ex-search, and the analyzer, and both may need dimension resampling against your field data before an analysis can use them — see [Atlas Resampling]({{ site.baseurl }}/wiki/atlas-resampling/) for how that works.

## See Also

- [Atlas Resampling]({{ site.baseurl }}/wiki/atlas-resampling/) — how the toolbox aligns an atlas to a subject's field data
- [Analyzer]({{ site.baseurl }}/wiki/analyzer/) — the primary consumer of ROI/atlas selection
- Return to [Wiki]({{ site.baseurl }}/wiki/)

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
}
.atlas-status {
  color: #666;
  font-size: 0.9rem;
  min-height: 1.2em;
}
#atlas-canvas {
  width: 100%;
  height: 480px;
  display: block;
  background: #000;
  border-radius: 4px;
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
  margin: 1.5rem 0 0.5rem;
}
.atlas-table-tools input {
  width: 100%;
  max-width: 420px;
  padding: 0.4rem 0.6rem;
  box-sizing: border-box;
}
.table-wrap {
  overflow-x: auto;
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

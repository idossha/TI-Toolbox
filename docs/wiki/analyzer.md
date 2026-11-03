---
layout: wiki
title: Analyzer Module
permalink: /wiki/analyzer/
---

The Analyzer answers two questions about a simulated montage: how strong is the TI field in your target, and how focal is it compared with the rest of the brain? It is the last step of the pipeline, run after the [Simulator]({{ site.baseurl }}/wiki/simulator/), and works on one subject or on a group.

<span id="quantities-of-interest"></span><span id="safety-metrics"></span>
What each field (`TI_max`, `TI_normal`, `hf_peak`, …) means and how it is computed is on [Field definitions]({{ site.baseurl }}/wiki/field-definitions/).

---

## In the application

<div id="defining-the-roi"></div>
Pick a target in the row's **Job settings**:

- **Sphere**: X / Y / Z and radius in subject or MNI space; several spheres run as separate analyses.
- **Atlas region**: cortical (surface atlases `DK40`, `a2009s`, `HCP_MMP1`) or subcortical (subject label volumes or the shipped MNI atlases); several regions combine into one ROI unless you untick **Combine regions into one ROI**.
- **NIfTI mask**: a `.nii`/`.nii.gz` in subject or MNI space; every positive voxel is in the target.
- **Tissue**: grey matter, white matter or both; voxel space only.

MNI targets are moved into each subject's anatomy automatically.

<div class="split" style="align-items: flex-start;">
<div>
<p><strong>Mesh</strong> reads the field on the grey-matter surface, weighting each node by its area (sizes in mm²); use it for cortical targets and <code>TI_normal</code>.</p>
<img style="display: block; margin: 0 auto; width: 100%; height: auto; max-width: 440px;" src="{{ site.baseurl }}/assets/imgs/v3/analyzer/analyzer_mesh_example.webp" alt="TI_max on the left insula (montage L_Insula): central-surface outlines on a sagittal T1 slice with the insula outlined in green, and the field-coloured central surface in 3-D">
</div>
<div>
<p><strong>Voxel</strong> reads the field on the subject's image grid inside the chosen tissue, weighting each voxel by its volume (sizes in mm³); use it for deep structures.</p>
<img style="display: block; margin: 0 auto; width: 100%; height: auto; max-width: 440px;" src="{{ site.baseurl }}/assets/imgs/v3/analyzer/analyzer_voxel_example.webp" alt="TI_max in the left hippocampus (montage LH2): grey-matter field on a coronal T1 slice with the hippocampus outlined in green, and a close-up of the field inside it">
</div>
</div>

---

<span id="statistics"></span><span id="outputs"></span>
## Results

Each run reports the target's mean, maximum and focality, percentiles and hot-spot sizes, and the carrier focality ratios, and writes a `results.csv`, the settings, an overlay and a TetraVox scene to `Analyses/<Mesh|Voxel>/<name>/`. Both are described on [Reading the results]({{ site.baseurl }}/wiki/analyzer-results/).

---

## Several subjects {#group-analysis}

Switch on **Combine into one group analysis** to run the same analysis over every row's subject.

- Every row must share the simulation, space, field and target; otherwise the run is refused with the difference named.
- MNI coordinates, masks and atlases are moved into each subject's anatomy; a group mask must be in MNI space.
- Several spheres, or uncombined regions, give one group job each.

```
derivatives/ti-toolbox/group_analysis/<simulation>_<space>_<target>_<YYYYMMDD>_<HHMMSS>/
├── group_summary.csv               # one row per subject plus an AVERAGE row
├── group_comparison.pdf            # 2×2 bars per subject: ROI mean, max, focality, normal mean
└── group_analysis_<timestamp>.log
```

---

## Learn more

- [Reading the results]({{ site.baseurl }}/wiki/analyzer-results/): metrics table, histogram and output files
- [Field definitions]({{ site.baseurl }}/wiki/field-definitions/): the maths behind every field and ratio
- [Simulator output fields]({{ site.baseurl }}/wiki/simulator/#output-fields)
- [Ex-search metrics]({{ site.baseurl }}/wiki/ex-search/#metrics)
- [Results]({{ site.baseurl }}/wiki/results/)

<span id="mti-analyses"></span>Multipolar (mTI) simulations are analysed the same way; `TI_max` resolves to `mTI_max`.

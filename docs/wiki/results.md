---
layout: wiki
title: Results
permalink: /wiki/results/
---

**Results** (⌘6) is the only outputs browser in the app. Everything a job wrote for a subject is
here.

<img src="{{ site.baseurl }}/assets/imgs/v3/results-page.png" alt="The Results page: subject 101 selected, its simulations, flex and ex runs, analyses and reports listed, and the L_Insula simulation's details, montage figure and field files in the preview pane" style="width: 100%; max-width: 1000px;">
<em>Subject list, outputs tree with type badges, and the preview pane for the selected L_Insula simulation.</em>

Selecting an output opens its details on the right, including when that pane was collapsed.
The job artifact action **Open in Tetravox** opens the selected supported file directly in
the embedded viewer.

## On disk

Nothing here is a database — the tree is the BIDS derivatives tree, read at the moment you look:

```
derivatives/SimNIBS/sub-<ID>/
├── m2m_<ID>/                      # head model
├── Simulations/<name>/
│   ├── TI/ (or mTI/)              # the envelope fields, and montage_imgs/
│   ├── high_Frequency/            # the per-pair carrier fields
│   ├── documentation/             # the config the run was launched with
│   └── Analyses/{Mesh,Voxel}/     # per-analysis outputs
├── flex-search/<run>/             # flex_meta.json, optimised positions, mappings,
│                                  #   candidate_history/ (evaluated candidates)
└── ex-search/<roi>/               # final_output.csv and per-montage outputs
```

A flex run's `candidate_history/<NN>/` (one folder per optimization run) holds `candidates.csv` (scalar metrics per valid
trial), `candidate_geometry.jsonl` (full-precision poses) and `candidate_manifest.json` (the
objective and stopping reason); invalid placements are only counted. Flex metrics use unweighted
samples from the declared ROI and non-ROI, whereas ex-search's recorded whole-gray-matter mean
includes the target, so the two are not the same region definition. Ex replay uses the CSV's
recorded precision and the Simulator's editable electrode defaults, since ex CSVs carry no
electrode dimensions. Final simulated fields can differ from the optimizer's estimates.

See [Reports]({{ site.baseurl }}/wiki/reports/) for what a report contains and
[Analyzer]({{ site.baseurl }}/wiki/analyzer/) for the analysis outputs themselves.

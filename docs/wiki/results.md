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
**Open in viewer**, at the foot of the preview pane, opens the selection in the
[TetraVox]({{ site.baseurl }}/wiki/visualizers/) app.

The **Group** entry, pinned at the bottom of the subject list, holds the project-level outputs:
group statistics, Nilearn visuals and group analyses.

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
├── ex-search/<run>/               # final_output.csv and per-montage outputs
└── m-ex-search/<run>/             # the same for the multipolar (mTI) search

derivatives/ti-toolbox/
├── reports/                       # generated reports
└── stats/<type>/<name>/           # group statistics (the Group entry)
```

An ex or mex `<run>` folder is named after the run name you gave, or a timestamp when you gave none.

A flex, ex or mex run's **Evaluated candidates** section lists the candidates the optimizer
scored; **Use in Simulator** turns one into an editable Simulator draft (see
[Flex search: Results]({{ site.baseurl }}/wiki/flex-search/#results)). Flex metrics use the
declared ROI and non-ROI, whereas ex-search's recorded whole-gray-matter mean includes the target,
so the two are not the same region definition. Final simulated fields can differ from the
optimizer's estimates.

See [Reports]({{ site.baseurl }}/wiki/reports/) for what a report contains and
[Analyzer]({{ site.baseurl }}/wiki/analyzer/) for the analysis outputs themselves.

---
layout: wiki
title: Results
permalink: /wiki/results/
---

# Results

**Results** (⌘7) is the only outputs browser in the app. Everything a job wrote for a subject is
here, and every "Open" from here is an in-app navigation to the
[Viewer]({{ site.baseurl }}/wiki/visualizers/) — nothing launches an external program.

<img src="{{ site.baseurl }}/assets/imgs/v3/results.png" alt="The Results page: subject list, outputs tree and preview pane" style="width: 100%; max-width: 1000px;">
<em>Subject list, outputs tree with type badges, and the preview pane.</em>

## Three columns

1. **Subjects** (200 px) — every subject with its output count.
2. **Outputs** — a tree of what that subject has, with a type badge per row and a filter over the
   whole tree: simulations, optimization runs, analyses, reports, exports and group outputs.
3. **Preview** — rendered only when something is selected, so the page is never a wide empty box.

## What the preview shows

| Output | Preview |
|---|---|
| Simulation report | The HTML report **inline**, in a sandboxed frame |
| Simulation artifacts | The NIfTI/mesh files, with Open (Viewer) and Reveal (file manager) |
| Flex-search run | The run's `flex_meta.json` manifest and its artifacts |
| Ex / mEx search | The run table read from `final_output.csv` |
| Analysis | The summary tables and the PDF |
| Group outputs | The tables written by `stats`, `nilearn` and NIfTI group averaging |

> **What's new in v3.** In 2.x, results were scattered across the tab that produced them — the
> Ex-Search tab had its own results panel, the Analyzer had an output section, and a report opened
> in your operating system's browser. v3 collects all of it here, subject-first, and renders
> reports in place.
>
> One caveat to know: an artifact row's **Open** is scoped to the whole simulation or analysis it
> belongs to, not to that single file. Use the Viewer's **Menu** to trim the list before opening if
> you want exactly one layer.

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
├── flex-search/<run>/             # flex_meta.json, optimised positions, mappings
└── ex-search/<roi>/               # final_output.csv and per-montage outputs
```

See [Reports]({{ site.baseurl }}/wiki/reports/) for what a report contains and
[Analyzer]({{ site.baseurl }}/wiki/analyzer/) for the analysis outputs themselves.

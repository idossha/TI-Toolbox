---
layout: wiki
title: TI-Toolbox Reports
permalink: /wiki/reports/
---

Every head model, DTI extraction, simulation and optimization writes one self-contained HTML report.
Open them in **Results ▸ sub-… ▸ Reports**, or from the job in **Jobs**. They follow the app's light or
dark theme, work offline and can be shared as single files.

## The five reports

- **Head model (charm) report** — SimNIBS's own report, copied from `m2m_<id>/charm_report.html` when
  charm finishes. Check the segmentation and the T1/T2 registration in its viewer.
- **DTI QC report** — written by the DTI tensor step: a verdict, the one published-range gate, advisories
  such as missing distortion correction, and registration and fibre-orientation figures.
- **Simulation report** — written after every simulated montage: the grey-matter envelope (99.9th
  percentile and median) and where its maximum is (MNI coordinate), the montage on the EEG cap
  with the current per channel and in total, the conductivity model (and whether the DTI tensor was used),
  and the TI envelope in three planes through the hot spot.
- **Flex-search report** — the target by name with the run's own target figure, what the score means in
  words, the best montage (optimised electrode positions and the valid-scalp figure), the dose, and one
  row per optimizer run.
- **Ex-search report** — the winning montage's electrodes and dose, every montage's ROI mean against
  focality in one chart, the top 25 as a sortable table, and the ROI and ranking in words.

Each opens with the few things you need; methods text with references and the run's configuration are
under **Technical details**.

## Example: simulation report

A simulation report for `sub-ernie` of the example dataset (AF3–PO10 and AF4–Oz, 1 mA per channel,
anisotropic conductivity from the subject's DTI tensor):

<iframe src="{{ site.baseurl }}/assets/other/simulation_report_ernie.html"
        width="100%"
        height="800px"
        style="border: 1px solid #ddd; border-radius: 8px;">
</iframe>

## Checks

Only the DTI QC report has checks. Each says what it is for: a **gate** blocks a result, a **software
check** tests TI-Toolbox's own consistency, an **advisory** warns but never blocks, and a **reported**
value is shown next to a published reference. The simulation, flex-search and ex-search reports have no
checks.

## Where reports are written

```
derivatives/ti-toolbox/reports/sub-ernie/
├── charm_report.html
├── dti_qc_20260927_230922.html
├── simulation_report_20260928_123736.html
├── flex_search_report_20260928_124706.html
└── ex_search_report_20260928_125409.html
```

Reports are self-contained HTML: no sidecar files, no links between reports, no PDF export.

## Rebuilding a report

A report can be rebuilt from a run's outputs without re-running it. In the container:

```bash
simnibs_python -m tit.reporting.generators.simulation  /mnt/project ernie AF3_PO10_and_AF4_Oz
simnibs_python -m tit.reporting.generators.flex_search /mnt/project ernie <flex-search run folder>
simnibs_python -m tit.reporting.generators.ex_search   /mnt/project ernie <ex-search run name>
simnibs_python -m tit.reporting.generators.dti_qc      /mnt/project ernie
```

Add `--out DIR` to write the report somewhere else.

---

_Last Updated: September 2026_

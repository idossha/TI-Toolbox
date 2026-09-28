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
- **Simulation report** — written after every simulated montage: the result, the montage on the EEG cap
  with the current per channel and in total, the conductivity model (and whether the DTI tensor was used),
  the TI envelope at the target, the ROI mean against the published TI range once the Analyzer has run on
  the simulation, and the safety advisories.
- **Flex-search report** — the target by name, what the score means in words, the best montage (flex
  electrodes are free positions; the cap figure shows each at its nearest cap electrode), the dose, and
  whether independent optimizer runs agree.
- **Ex-search report** — the winning montage on the cap with its dose, every montage's ROI mean against
  focality in one chart, and the top 25 as a sortable table.

Each opens with the few things you need; methods text with references, software checks and the run's
configuration are under **Technical details**.

## Example: simulation report

A simulation report for `sub-ernie` of the example dataset (AF3–PO10 and AF4–Oz, 1 mA per channel,
anisotropic conductivity, with a bilateral-thalamus ROI analysis):

<iframe src="{{ site.baseurl }}/assets/other/simulation_report_ernie.html"
        width="100%"
        height="800px"
        style="border: 1px solid #ddd; border-radius: 8px;">
</iframe>

## Checks and safety advisories

Every check says what it is for: a **gate** blocks a result, a **software check** tests TI-Toolbox's own
consistency, an **advisory** warns but never blocks, and a **reported** value is shown next to a
published reference. Thresholds are only those with a published source:

- **Electrode current** — each electrode carries its channel's current; the total is the sum over
  channels (1 mA per channel in two channels is 2 mA total). Compared with the < 4 mA range that has
  established tES safety evidence (Antal 2017, Bikson 2016). TI at kHz carriers has higher,
  frequency-dependent limits (Cassarà 2025); whether those apply per channel or to the total current is
  not verified.
- **Brain current density** — an estimate from the grey-matter field, against 6.3 A/m², the lowest
  injury level seen in animals (Bikson 2016).
- **Target field** — the ROI mean next to the range published for optimised TI, 0.24–0.57 V/m at 2 mA
  total (Rampersad 2019), scaled to your total current. Shown for context, not as pass or fail.

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

A report can be rebuilt from a run's outputs without re-running it, for example to add an ROI analysis
to a simulation report. In the container:

```bash
simnibs_python -m tit.reporting.generators.simulation  /mnt/project ernie AF3_PO10_and_AF4_Oz
simnibs_python -m tit.reporting.generators.flex_search /mnt/project ernie <flex-search run folder>
simnibs_python -m tit.reporting.generators.ex_search   /mnt/project ernie <ex-search run name>
simnibs_python -m tit.reporting.generators.dti_qc      /mnt/project ernie
```

Add `--out DIR` to write the report somewhere else.

---

_Last Updated: September 2026_

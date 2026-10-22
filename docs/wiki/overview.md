---
layout: wiki
title: Overview
permalink: /wiki/overview/
---

<img src="{{ site.baseurl }}/assets/imgs/v3/overview-welcome.png" alt="The welcome Overview: a project directory field with Browse and Open project, and the five workflow steps below" style="width: 100%; max-width: 1000px;">

The app opens on a welcome Overview. Enter or **Browse…** to your project directory, then
**Open project**. Docker must be running. Project tools stay disabled until a project is open.

<img src="{{ site.baseurl }}/assets/imgs/v3/overview-project.png" alt="Overview with project 000 open: six subjects with the outputs each has, recent analyzer jobs, project storage by kind and a year of job activity" style="width: 100%; max-width: 1000px;">
<em>Once connected, Overview shows what every subject has, the most recent jobs, where the project's disk space goes and its job activity.</em>

**Switch project** loads another project in a fresh session; the current container is stopped
once you confirm. If another TI-Toolbox container is already running you choose whether to
attach to it or recreate it. See [launch options]({{ site.baseurl }}/installation/bash-cli/).

## Add example data

**Add example data** opens **Help ▸ Example data**, where each part of the public example heads has
its own **Download** button; new projects are also offered them once. See
[Example Data]({{ site.baseurl }}/wiki/example-data/).

## Project information

The header shows the project name, host path and storage grouped by workflow (head models,
searches, simulations, leadfields, FreeSurfer/FastSurfer, diffusion, input data, other).
Sizes refresh at most every five minutes. The activity calendar counts retained jobs by
submission date over the past year (UTC); job details live on the **Jobs** page.

## The presence matrix

Each row is a subject. Six columns of dots show the artefacts the rest of the toolbox depends on;
a **Leadfield** column and three counts follow:

| Column               | What it means                                                                             |
| -------------------- | ----------------------------------------------------------------------------------------- |
| **RAW**              | Raw MRI converted into the BIDS tree; data only in `sourcedata/` shows as _partial_       |
| **FAST**             | FastSurfer segmentation (`derivatives/fastsurfer/sub-<id>`)                               |
| **FREE**             | FreeSurfer `recon-all` output from the optional preprocessing stage or an earlier run     |
| **M2M**              | A SimNIBS head model, `derivatives/SimNIBS/sub-<id>/m2m_<id>`                             |
| **DWI** / **CT**     | Diffusion or CT data present                                                              |
| **LEADFIELD**        | The EEG nets the subject has a leadfield for, as chips: the first net, then `+N` for more |
| **SIM / OPT / ANLY** | How many simulations, optimizations and analyses the subject has                          |

A dot has one of five **presence states**, and they are not opinions — what is on disk always wins:

- **present** — the artefact is there
- **partial** — some of it is there (e.g. raw scans staged in `sourcedata/` but not yet converted)
- **running now** — a job is producing it at this moment
- **last run failed** — the most recent job for it failed and it is still absent
- **missing** — nothing on disk and no job

`running now` and `last run failed` come from the job records and only ever describe an artefact
that is _still absent_; they never override a file that exists.

## Subject details

Click a row to open its detail pane (click it again to close it). It lists what the subject has,
including its EEG nets, and its simulation, optimization and analysis counts, each of which opens
**Results**, as does **Open in Results**. Under it are the **Pre-process**, **Simulate**,
**Optimize** and **Analyze** buttons and **Open in viewer** (needs a head model).

## Filtering and the readiness verdict

The **All / Ready / Incomplete** control filters the subject list. **Ready** is one fixed rule: the
subject has a head model and its raw MRI is present. A head model without raw MRI, such as the
example head-model part, therefore counts as Incomplete. Whether a subject can run a given stage is
shown by the detail pane's stage buttons: a disabled button says why in its tooltip — _"no head
model"_, _"no simulations"_ — rather than silently offering a run that will fail.

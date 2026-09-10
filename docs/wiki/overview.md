---
layout: wiki
title: Overview
permalink: /wiki/overview/
---

# Overview

**Overview** (⌘0) is the first page the app opens, and it answers one question for the whole
project at once: *what does each subject already have, and what is it ready for?*

<img src="{{ site.baseurl }}/assets/imgs/v3/overview.png" alt="The Overview page: a presence matrix with one row per subject" style="width: 100%; max-width: 1000px;">
<em>One row per subject; one dot per artefact. The counts on the right are simulations, optimizations and analyses.</em>

## Project information

The header shows the project name and host path. Storage is measured in the background,
with SimNIBS workflow subtotals (head models, Flex/Ex searches, simulations and leadfields),
FreeSurfer/FastSurfer, QSIPrep and QSIRecon groups, and combined raw/source **Input data**.
Diffusion totals include their working directories.
Remaining data is grouped as **Other**, including internal state and viewer scenes.
The list shows a scrollbar when its contents exceed the available height. These are
file sizes (symlinks excluded), refreshed at most every five minutes; System reports
allocated disk usage, which can differ. An incomplete scan is shown as unavailable.

The activity calendar counts retained jobs by submission date over the past year, in UTC.
Select a day to see its count. Job details remain on the **Jobs** page. Deleted job records are not included. Last activity reflects recorded job events;
project creation and opening dates are not inferred from file timestamps.

## The presence matrix

Each row is a subject, each column an artefact the rest of the toolbox depends on:

| Column | What it means |
|---|---|
| **RAW** | A staged/converted anatomical image exists under `sourcedata/` or the BIDS root |
| **FAST** | FastSurfer segmentation (`derivatives/freesurfer/sub-<id>` written by FastSurfer) |
| **FREE** | A legacy FreeSurfer `recon-all` output — still read, never produced by v3 |
| **M2M** | A SimNIBS head model, `derivatives/SimNIBS/sub-<id>/m2m_<id>` |
| **DWI** / **CT** | Diffusion or CT data present |
| **LF** | A leadfield matrix, and which EEG net it was built for |
| **NET** | EEG net files registered for this subject |
| **SIM / OPT / ANLY** | How many simulations, optimizations and analyses the subject has |

A dot has one of five **presence states**, and they are not opinions — what is on disk always wins:

- **present** — the artefact is there
- **partial** — some of it is there (e.g. a leadfield for one net but not the one you selected)
- **running now** — a job is producing it at this moment
- **last run failed** — the most recent job for it failed and it is still absent
- **missing** — nothing on disk and no job

`running now` and `last run failed` come from the job records and only ever describe an artefact
that is *still absent*; they never override a file that exists.

## Filtering and the readiness verdict

The **All / Ready / Incomplete** control filters by whether a subject can be run through the next
stage. "Ready" is per stage, and a subject that is not ready says why in one phrase — *"no head
model"*, *"no simulations"* — rather than silently offering a run that will fail.

## What Overview is not

Overview carries **counts, never trees or previews**. To browse what a subject actually produced,
open [Results]({{ site.baseurl }}/wiki/results/); to watch or cancel work, open
[Jobs]({{ site.baseurl }}/wiki/jobs/).

> **What's new in v3.** There was no project-wide view in 2.x — the PyQt GUI had a per-subject
> "Subject Info" tab, which v3 deletes. Overview replaces it with one server-side aggregate
> (`GET /api/catalog/overview`) so the count it prints is the whole project's, not the first
> 25 subjects'.
>
> Full list: [the v3.0.0 release notes]({{ site.baseurl }}/releases/v3.0.0/).

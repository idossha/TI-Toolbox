---
layout: wiki
title: Example Data
permalink: /wiki/example-data/
---

Two public example heads you can download into any open project, so you can learn TI-Toolbox and
test every page before using your own data. They come from the
[SimNIBS example dataset](https://github.com/simnibs/example-dataset) (**GPL-3.0**) and are re-hosted content-addressed: every file is an
asset named by its own sha256 on the `v1` release of
[`idossha/ti-toolbox-example-data`](https://github.com/idossha/ti-toolbox-example-data) — the data's
own repository — and nothing is written into your project until the downloaded bytes hash to the
catalogue entry.

## Datasets and parts

Each **dataset** is one head. Each of its **parts** is downloaded, and detected, on its own: taking
the head model does not oblige you to take the raw MRIs, and deleting the raw MRIs later does not
make the head model report itself as missing.

| Dataset                         | Part       | Id                 | Size   | What lands                                           | Meaning                                  |
| ------------------------------- | ---------- | ------------------ | ------ | ---------------------------------------------------- | ---------------------------------------- |
| Ernie — SimNIBS example subject | Raw MRI    | `ernie/nifti`      | 35 MB  | `sub-ernie/anat/sub-ernie_T1w.nii.gz`, `_T2w.nii.gz` | needs pre-processing                     |
|                                 | Head model | `ernie/headmodel`  | 592 MB | `derivatives/SimNIBS/sub-ernie/m2m_ernie/`           | ready for optimizer, simulator, analyzer |
| MNI152 template                 | Raw MRI    | `mni152/nifti`     | 15 MB  | `sub-MNI152/anat/sub-MNI152_T1w.nii.gz`              | needs pre-processing                     |
|                                 | Head model | `mni152/headmodel` | 462 MB | `derivatives/SimNIBS/sub-MNI152/m2m_MNI152/`         | ready for optimizer, simulator, analyzer |

A _Raw MRI_ part is what a real study starts from: you build its head model yourself on the
[Pre-processing]({{ site.baseurl }}/wiki/pre-processing/) page (charm takes 1–2 h). A _Head model_
part is a finished charm run, so the [Optimizer]({{ site.baseurl }}/wiki/flex-search/),
[Simulator]({{ site.baseurl }}/wiki/simulator/), [Analyzer]({{ site.baseurl }}/wiki/analyzer/) and the
[example notebook]({{ site.baseurl }}/wiki/notebooks/#the-example-notebook) work the moment it lands — you do not
need that subject's raw MRIs for any of them.

## Where to get it

- **First time you open a new project** the app asks _Add example data?_ and lists the parts under
  their dataset, with `ernie/headmodel` pre-ticked. **Download selected** queues the ticked parts
  one after another. The answer (either way) is recorded in the project's `project_status.json`, so
  you are asked once per project, not once per machine.
- **Help ▸ Example data** has the same grouping at any time, with a **Download** button per part,
  a slim progress bar while one runs, and _Installed ✓_ (plus a quiet re-download) for what this
  project already holds. Overview's **Add example data** button opens that tab.
- **From a shell or a notebook:**

  ```bash
  python -m tit.examples --project /path/to/project --list
  python -m tit.examples --project /path/to/project ernie/headmodel mni152/nifti
  python -m tit.examples --project /path/to/project ernie          # a bare dataset: all its parts
  ```

  ```python
  from tit.examples import fetch, fetch_ernie
  fetch("mni152", "headmodel", PROJECT)   # or fetch("mni152/headmodel", PROJECT)
  fetch_ernie(PROJECT)                    # both ernie parts, the shorthand the notebook uses
  ```

Every route runs the same `tit.examples.fetch` and is idempotent: a part already in place is
skipped unless you pass `--force`. Downloading example data is **not** a job — it does not appear
in the jobs rail — and it needs nothing from project initialization: any project directory, new or
long-established, takes a part. In the app one download runs at a time and the page polls its
progress; a part you start while one is running is queued behind it rather than competing.

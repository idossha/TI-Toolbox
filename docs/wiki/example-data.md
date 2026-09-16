---
layout: wiki
title: Example Data
permalink: /wiki/example-data/
---

Four public datasets you can download into any open project, so you can learn TI-Toolbox and test
every page before using your own data. They come from the
[SimNIBS example dataset](https://github.com/simnibs/example-dataset) (**GPL-3.0**; the licence
check is in `tit/scene/guide/PROVENANCE.md`) and are re-hosted content-addressed: every file is an
asset named by its own sha256 on the `example-data` release of `idossha/TI-Toolbox`, and nothing is
written into your project until the downloaded bytes hash to the catalogue entry.

## The catalogue

| Sample | Size | What you get | State |
|---|---|---|---|
| `mni152-t1` | 15 MB | The MNI152 template's T1 | needs pre-processing |
| `ernie-t1` | 35 MB | Ernie's raw T1 + T2 | needs pre-processing |
| `ernie-headmodel` | 627 MB | Ernie's T1 + T2 **and** the finished `m2m_ernie` head model | ready to simulate |
| `mni152-headmodel` | 477 MB | The MNI152 T1 **and** the finished `m2m_MNI152` head model | ready to simulate |

A *needs pre-processing* sample lands in `sub-<id>/anat/` and you build its head model yourself on
the [Pre-processing]({{ site.baseurl }}/wiki/pre-processing/) page (charm takes 1–2 h). A *ready to
simulate* sample also unpacks `derivatives/SimNIBS/sub-<id>/m2m_<id>/`, so the
[Optimizer]({{ site.baseurl }}/wiki/flex-search/), [Simulator]({{ site.baseurl }}/wiki/gui/),
[Analyzer]({{ site.baseurl }}/wiki/analyzer/) and the
[Example Notebook]({{ site.baseurl }}/wiki/example-notebook/) work at once.

## Where to get it

- **First time you open a new project** the app asks *Add example data?* and offers the four
  samples as tick boxes, with `ernie-headmodel` pre-ticked. The answer (either way) is recorded in
  the project's `project_status.json`, so you are asked once per project, not once per machine.
- **Help ▸ Example data** has the same list at any time, with a **Download** button per sample,
  live job progress and an *Installed ✓* marker for what this project already holds. Overview's
  **Add example data** button opens that tab.
- **From a shell or a notebook:**

  ```bash
  python -m tit.examples --project /path/to/project --list
  python -m tit.examples --project /path/to/project ernie-headmodel mni152-t1
  ```

  ```python
  from tit.examples import fetch, fetch_ernie
  fetch("ernie-t1", PROJECT)   # any catalogue id
  fetch_ernie(PROJECT)         # the ernie-headmodel shorthand the notebook uses
  ```

Every route runs the same code and is idempotent: a sample already in place is skipped unless you
pass `--force`. In the app the download is a job, so it shows in the jobs rail and survives you
navigating away.

## Behind a proxy?

Downloads verify the store's TLS certificate against `certifi`, falling back to your system CA
bundle. If your network inspects TLS, point `SSL_CERT_FILE` (or `REQUESTS_CA_BUNDLE`) at your
organisation's CA bundle before starting the toolbox; certificate verification is never disabled.

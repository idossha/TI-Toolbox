# Examples

| File | What it is |
|---|---|
| `notebooks/example_workflow.ipynb` | The `tit` Python API in eight cells: project, example subject, pre-processing, optimizer, simulator, analyzer, results. Mirrored cell for cell on the wiki's [Example Notebook](https://idossha.github.io/TI-Toolbox/wiki/example-notebook/) page. |

## Running the notebook

You do not need your own data. The notebook's first cell calls
`tit.examples.fetch_ernie(PROJECT)`, which downloads the SimNIBS example subject
(`ernie`, with a finished `m2m_ernie` head model, GPL-3.0) into the project once.
The same download is behind the app's **Add example subject** button on the Overview
page and `python -m tit.examples --project DIR`.

Set the project root either with the `TIT_PROJECT_DIR` environment variable or by
editing the marked `PROJECT = "..."` line in cell 1.

Two ways to open it:

* **App:** open a project, go to the *Notebooks* page, choose **Import .ipynb**, pick
  this file and the *SimNIBS + TI-Toolbox* kernel.
* **Container shell:** `docker exec -it simnibs_container bash`, then `NOTEBOOK` to
  start JupyterLab and upload the file.

The optimizer and simulator cells run FEM solves and take minutes each.

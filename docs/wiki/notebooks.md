---
layout: wiki
title: Notebooks
permalink: /wiki/notebooks/
---

# Notebooks

**Notebooks** (⌘8) is a Jupyter environment inside the app, running on **the container's SimNIBS
Python** — the same interpreter every job runs in. `import simnibs`, `from tit import
get_path_manager`, `from tit.sim import SimulationConfig` all work in a cell with nothing to
install and nothing to configure.

<img src="{{ site.baseurl }}/assets/imgs/v3/notebooks.png" alt="A notebook with real output: a matplotlib figure and DataFrame tables" style="width: 100%; max-width: 1000px;">
<em>The seeded worked example, run against a real project: a field summarised, plotted and tabulated.</em>

## The page

Two panes, no right pane:

- **Left (260 px)** — the notebook list with modification times, **+ New**, **Import .ipynb**, and
  a delete on hover.
- **Right** — a toolbar (insert cell, Run all, Interrupt, Restart, Clear outputs, Save, and the
  **kernel pill**) above the cells in one scroller.

Notebooks are ordinary `.ipynb` files in your project, under
`<project>/code/ti-toolbox/notebooks/`. Saving round-trips the document, so a notebook edited here
and a notebook edited in Jupyter Lab produce the same file.

## Editing

Editing is modal, the way Jupyter is: **↵** enters a cell, **Esc** leaves it, **⇧↵** runs the cell
and moves to the next, **⌘↵ / Ctrl+↵** runs it in place, and **⌥↵ / Alt+↵** runs it and inserts a
new cell below. Code cells are CodeMirror 6 with Python highlighting.

**Completion (⇥ or ⌃Space) and signature help (⇧⇥, or typing `(`) are answered by the kernel**, not
by a language server — so they know what your variables actually are, and they are only available
once a kernel is up. A keystroke never *starts* a kernel.

## The kernel

The pill on the toolbar is both the status and the recovery: `off · starting · idle · busy ·
dead`, and clicking it starts or restarts. A full SimNIBS interpreter takes a few seconds to come
up the first time.

- **At most two kernels** run at once, and an idle kernel is reaped after 30 minutes.
- A kernel **outlives leaving the page** — go and watch a job, come back, your variables are still
  there — but not closing the window.
- Leaving the page flushes unsaved work.

> **There is no sandbox.** A cell runs arbitrary Python as the container's user, with your project
> mounted — exactly the trust boundary the job runners already have. Treat a notebook someone sent
> you the way you would treat a script they sent you.

## The worked example

Every project gets one seeded notebook the first time you open the page:
`examples/getting-started.ipynb`. It is not a static tutorial — it resolves **your** project's
subjects, loads the first real TI field it finds, and plots and tabulates it. Deleting it is
permanent; there is no "restore example".

A written-out version of the same walkthrough, with its outputs, is the
[Example Notebook]({{ site.baseurl }}/wiki/example-notebook/) page.

> **What's new in v3.** 2.x shipped a Jupyter server in the container that you reached through a
> browser on port 8888, separately from the GUI. v3 puts the notebook in the application, on the
> same connection, with the same authentication, and with the project already resolved.
>
> Full list: [the v3.0.0 release notes]({{ site.baseurl }}/releases/v3.0.0/).

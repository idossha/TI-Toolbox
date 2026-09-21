---
layout: wiki
title: Notebooks
permalink: /wiki/notebooks/
---

**Notebooks** (⌘8) is a Jupyter environment inside the app, running on \*\*the container's unique interpreter.

Notebooks are ordinary `.ipynb` files in your project, under
`<project>/code/ti-toolbox/notebooks/`. Saving round-trips the document, so a notebook edited here
and a notebook edited in Jupyter Lab produce the same file.

<img src="{{ site.baseurl }}/assets/imgs/v3/notebooks.png" alt="A notebook with real output: a matplotlib figure and DataFrame tables" style="width: 100%; max-width: 1000px;">
<em>The seeded worked example, run against a real project: a field summarised, plotted and tabulated.</em>

## Editing

Editing is modal, the way Jupyter is: **↵** enters a cell, **Esc** leaves it, **⇧↵** runs the cell
and moves to the next, **⌘↵ / Ctrl+↵** runs it in place, and **⌥↵ / Alt+↵** runs it and inserts a
new cell below. Code cells are CodeMirror 6 with Python highlighting.

**Completion (⇥ or ⌃Space) and signature help (⇧⇥, or typing `(`) are answered by the kernel**, not
by a language server — so they know what your variables actually are, and they are only available
once a kernel is up. A keystroke never _starts_ a kernel.

## The kernel

`off · starting · idle · busy · dead`, and clicking it starts or restarts. The interpreter takes a few seconds to come
up the first time.

## The worked example

Every project gets one seeded notebook the first time you open the page:
`examples/example_workflow.ipynb` — the same notebook as the
[Example Notebook]({{ site.baseurl }}/wiki/example-notebook/) page, which walks some of the app features.
(Pre-processing, Optimizer, Simulator, Analyzer) one cell per page against the SimNIBS example
subject. When a TI-Toolbox update ships a newer version of it, your copy is refreshed only if you
never edited it; an edited copy is yours. Deleting it is permanent; there is no "restore example".

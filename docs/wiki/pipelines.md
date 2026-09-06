---
layout: wiki
title: Pipelines
permalink: /wiki/pipelines/
---

# Pipelines

The **Pipeline** page (⌘6) is a canvas: you place the steps you already run — pre-processing, an
optimizer, the simulator, the analyzer — wire one step's output into the next step's input, and press
Run once. The whole graph is submitted as **one job group**, so it appears in Jobs as one thing you
can watch and cancel as one thing. The same graph exports to a Jupyter notebook that runs the same
work from Python.

Two rules explain everything else on the page:

1. **A node is one existing job kind carrying exactly the config that page already builds.** There is
   no new kind of run, no new runner, and nothing a pipeline can do that the Simulator or Analyzer
   page cannot. A `sim` node *is* a Simulator run.
2. **A pipeline run is one job group.** The edges you draw become the `after` dependencies the job
   scheduler already understands. The scheduler stays the only thing that decides what runs when;
   the canvas never sequences jobs itself.

---

## Nodes and ports

Each node kind has typed **inputs** on its left and **outputs** on its right. An edge may only join
two ports of the same type — the canvas refuses anything else while you are dragging, and says why.

| Node | Takes | Produces |
|---|---|---|
| Pre-processing (`pre`) | — | subjects |
| Leadfield (`leadfield`) | subjects | subjects, leadfield |
| Flex-search (`flex`) | subjects, ROI | subjects, montage names, ROI |
| Ex-search (`ex`) / mEx-search (`mex`) | subjects, ROI, leadfield | subjects, montage names, ROI |
| Simulator (`sim`) | subjects, montage names | subjects, simulation name |
| Analyzer (`analyzer`) | subjects, simulation name, ROI | subjects |
| Source model (`source`) | subjects | subjects |
| Group statistics (`stats`) | subjects | — |

The five port types:

- **Subjects** — the subject set flows down the graph. Wire `pre → flex → sim → analyzer` on
  subjects and you set the cohort once; every downstream node runs on exactly those subjects.
- **Montage names** — an optimizer's result. "Optimizer → Simulator" means *simulate the montage the
  optimizer found*, not "simulate something, separately".
- **Simulation name** — a Simulator's output. "Simulator → Analyzer" fans out to one analysis per
  simulation the Simulator writes.
- **ROI** — the target an optimizer aimed at, carried into a downstream node so the analysis and the
  optimization are talking about the same region.
- **Leadfield** — the `.hdf5` an ex/mEx search needs.

An input that is not wired is not an error: it just has to be filled in on the node's own form. A
Simulator whose montages you picked by hand is a perfectly good one-node pipeline. A step that is
wired to nothing at all is not an error either — it simply runs on its own, and the receipt says so
once, at the bottom ("3 steps run independently"), rather than warning you about each one.

A **required** input that is neither wired nor filled in *is* an error, and the card says which:
a red **needs: subjects** chip on the card itself. Click the chip and the node's form opens with
that field focused; wire the port and the chip goes away.

## Working on the canvas

| To… | Do |
|---|---|
| add a step | click it in the palette (it lands in the middle of the view), or drag it onto the canvas |
| wire two steps | drag from an output handle on the right of one card to the same-coloured input handle on the left of another |
| see what a handle is | hover the card — every port prints its name |
| move a step | drag the card; it snaps to a 16 px grid |
| select several | ⌘-click, shift-click, or drag a marquee on empty canvas; **⌘A** takes everything, **Esc** clears |
| delete | select and press **Delete**, use the toolbar's trash, or right-click ▸ **Delete step / Delete wire** |
| undo / redo | **⌘Z** / **⇧⌘Z**, or the toolbar arrows |
| pan / zoom | trackpad scroll and pinch, the zoom buttons, or the minimap |
| fit everything on screen | the fit button, bottom-left |

An illegal wire is refused *while you drag it*: the target handle will not take the drop, and the
canvas states the reason ("Subjects is already wired from Head model", "that would make a cycle").
Nothing is ever dropped silently.

## Editing a node

Double-click a card. The form that opens is the *same form* its page uses — the Optimizer's
objective and electrode sections, the shared ROI picker, the Analyzer's target fields. A field whose
value arrives over a wire is shown disabled, with a line saying where it comes from.

Kinds whose page form cannot be lifted out of its page yet (`ex`, `mex`, `leadfield`, `source`,
`stats`) are edited as JSON. The server validates that JSON against the same dataclass the runner
reads, so a mistake comes back as a sentence rather than a failed job twenty minutes later.

## The receipt, and the Terminal under it

The right pane always shows what Run *would* submit: how many jobs, in one group, and each job's
label, kind, subjects and the jobs it waits for (the first 15, then a count).

When something *would* stop the run, the receipt becomes the list of those things instead —
**grouped by the step they are about**, each with a **Fix** button that selects and centres that
step on the canvas. Only real blockers appear: a cycle, an incompatible wire, a required input that
is neither wired nor filled in. Facts that are not faults — a step wired to nothing, a step still at
its defaults — are one sentence at the bottom.

Below the receipt is the live **Terminal**. It follows the step you last clicked when that step has
a job in the running group, and otherwise whatever is running, so watching a particular step's log
is one click on its card.

## Running

Run posts the document once. The server:

1. validates the graph;
2. turns it into a list of jobs whose `after` labels are your edges;
3. submits that list under one `group_id`.

Values that only exist *after* an upstream job has run — the name an optimizer gives its own run
directory, a leadfield file, a simulation name whose montages were themselves optimized — get one
extra small step planned between the producer and its consumer. It shows up in Jobs as a `tools` job
tagged `resolve`, and it records what it found under
`code/ti-toolbox/pipelines/runs/<pipeline>/<node>.<port>.json`. The consumer reads that file back
the moment it starts, so an optimized montage reaches the Simulator without you retyping it.

Bindings whose value is knowable up front — subjects, ROI, and a simulation name coming from a
Simulator whose montages you named yourself — never need the extra step: they are resolved when the
pipeline is submitted.

> **If the resolve step finds nothing** — the optimizer wrote no run for that subject — the
> consumer keeps whatever the canvas set, which for an unbound field is empty. The job then fails
> the way it would if you had left the field blank on the page, with the same message. It does not
> guess.

## Saving, loading and exporting

Pipelines are saved in your project, at `code/ti-toolbox/pipelines/<name>.json`, and appear in the
palette's **Saved** list. **Import JSON…** reads the same file from anywhere.

**Save** asks for a name and writes the file; **Export notebook** opens a save dialog and writes an
`.ipynb` with:

- a title cell carrying the graph as a Mermaid diagram;
- one markdown + code cell pair per node, in dependency order, written against the public
  [`tit` scripting API]({{ site.baseurl }}/wiki/scripting/) — `run_pipeline`, `FlexConfig`/`run_flex_search`,
  `SimulationConfig`/`run_simulation`, `Analyzer`;
- bindings as plain Python variables passed from one cell to the next
  (`sim1_subjects = pre1_subjects`, `montage_names=flex1_montages`);
- the pipeline document itself in `metadata.ti_toolbox.pipeline`, so the canvas can be restored from
  the notebook without parsing Python.

The exported notebook is a real script: run it with **Run All Cells**, or

```bash
jupyter nbconvert --to notebook --execute my-pipeline.ipynb
```

Notebook export needs `nbformat`. Both container images bake it in; a bare `pip install tit` needs
`pip install "tit[pipeline]"`.

## From Python

Nothing on the page is exclusive to it — the same document drives the same API:

```python
import json, requests

doc = json.load(open("code/ti-toolbox/pipelines/my-pipeline.json"))
headers = {"Authorization": f"Bearer {TOKEN}"}

# What would run, and why it might not
print(requests.post(f"{BASE}/api/pipelines/validate", json=doc, headers=headers).json())

# Run it: one group id back
result = requests.post(
    f"{BASE}/api/pipelines/run",
    json={"pipeline": doc, "parallel_subjects": 2},
    headers=headers,
).json()
print(result["group_id"], len(result["jobs"]), "jobs")
```

Or build the document in Python without the server at all:

```python
from tit.pipeline import PipelineDocument, export_notebook, plan_pipeline, validate

doc = PipelineDocument.from_dict(json.load(open("my-pipeline.json")))
print(validate(doc).ok)
for job in plan_pipeline(doc):
    print(job.label, job.kind, job.subject_ids, "after", job.after_labels)
open("my-pipeline.ipynb", "w").write(export_notebook(doc))
```

## Non-goals

- **A workflow engine.** No retries-with-backoff, no conditionals, no loops, no per-node scheduling
  policy. If a pipeline could do something a job group cannot, it would be a second executor.
- **Importing an arbitrary notebook.** Export is round-trippable through the document in the
  notebook's metadata; parsing hand-edited Python back into a canvas is not a goal.
- **Drag-to-reorder.** The order is the graph.

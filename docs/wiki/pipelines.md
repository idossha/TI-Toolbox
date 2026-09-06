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

Four rules explain everything else on the page:

1. **The cohort is a node.** A **Subjects** node names who the graph is about, once. It runs
   nothing. Every other node is handed those subjects over a wire — no node carries its own copy of
   the subject list, so two steps in one graph can never disagree about who is in the study.
2. **A node is one existing job kind carrying exactly the config that page already builds — its
   own.** There is no new kind of run, no new runner, and nothing a pipeline can do that the
   Simulator or Analyzer page cannot. A `sim` node *is* a Simulator run. **A node is never
   configured from the node upstream of it**: an edge carries one named value and nothing else.
3. **A wire is refused when the subjects on it are not ready for what it feeds.** Port types say
   what a wire carries; readiness says whether these particular subjects can be run through the
   target. Both are checked, and the second one names the subjects that fail.
4. **A pipeline run is one job group.** The edges you draw become the `after` dependencies the job
   scheduler already understands. The scheduler stays the only thing that decides what runs when;
   the canvas never sequences jobs itself.

---

## Nodes and ports

Each node kind has typed **inputs** on its left and **outputs** on its right. An edge may only join
two ports of the same type — the canvas refuses anything else while you are dragging, and says why.

| Node | Takes | Produces |
|---|---|---|
| **Subjects** (`subjects`) | — | subjects |
| Pre-processing (`pre`) | subjects | subjects |
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
Simulator whose montages you picked by hand is fine. A step that is wired to nothing at all is not
an error either — it simply runs on its own, and the receipt says so once, at the bottom
("3 steps run independently"), rather than warning you about each one.

A step with **no cohort wired to it** *is* an error, and the card says so with a red
**needs: subjects** chip. Wire a Subjects node to it and the chip goes away.

## What a subject has, and what that lets you wire

Drawing a wire asks two questions. The first is the port type — a Simulator produces a *simulation
name*, so it can feed an Analyzer. The second is about the **subjects on the wire**: an Analyzer
runs on a simulation that already exists, so a cohort with no simulations has nothing for it to
analyse, and the wire is refused while you are still dragging it:

> `102, test have no simulations`

Four facts are tracked, all of them read from the same **Overview** you already look at:

| Capability | What it means |
|---|---|
| raw MRI | the subject has converted structural data |
| head model | `m2m_<subject>` exists (`charm` has run) |
| leadfield | at least one EEG net has a leadfield |
| simulations | the subject has at least one finished simulation |

| Step | Needs of every subject | Leaves behind |
|---|---|---|
| **Subjects** | — | — |
| Pre-processing | raw MRI | **head model** |
| Leadfield | head model | **leadfield** |
| Flex-search | head model | — |
| Ex-search / mEx-search | head model + leadfield | — |
| Simulator | head model | **simulations** |
| Analyzer | simulations | — |
| Source model | head model | — |
| Group statistics | simulations | — |

The "leaves behind" column is what makes a chain work. Subjects with nothing but raw data cannot be
wired to the Simulator — but wire them through **Pre-processing** first and they can, because
Pre-processing is what makes the head model the Simulator needs:

```
Subjects(raw only) ─▶ Simulator                      refused: "102, test have no head model"
Subjects(raw only) ─▶ Pre-processing ─▶ Simulator    fine
Subjects(with simulations) ─▶ Analyzer               fine — no Simulator needed
```

A **multi-subject** cohort is wired only if **every** subject satisfies the requirement; the refusal
names the ones that do not, and never blames the ones that do. If part of a cohort is ready and
part is not, split it into two Subjects nodes.

The cohort node's own editor shows each subject's presence columns and what it is ready for, so the
reason arrives before the refusal does. The same table is served at `GET /api/pipelines/kinds` and
applied again by `POST /api/pipelines/validate`, so the refusal you see mid-drag and the one in the
receipt are the same sentence.

## Working on the canvas

| To… | Do |
|---|---|
| start a graph | add a **Subjects** node and choose who takes part |
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

Double-click a card. A **Subjects** node opens the project's subject list with the Overview's own
readiness columns. Every other node opens the *same form* its page uses — the Optimizer's
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

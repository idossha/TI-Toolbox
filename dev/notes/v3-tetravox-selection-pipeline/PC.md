# PC — pipeline canvas and notebook export (D1–D6)

Lane brief: `dev/notes/v3-tetravox-selection-pipeline-plan.md` §1-D. Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. **Nothing committed.**

---

## 1. What the lane built, in one paragraph

A pipeline is a DAG whose nodes are **existing job kinds** carrying **exactly the config the
matching v3 page already builds**, and whose edges are **typed bindings** between one node's named
output and another's same-named input. Running one is exactly one
`tit.jobs.manager.JobManager.submit_plan` call — the same call the `pre` G1–G6 DAG already makes —
so a pipeline run is **one `group_id`**, one row-group in Jobs, cancellable as one thing. There is
no pipeline executor, no new job kind and no runtime graph engine: the scheduler stays the only
thing that decides what runs when. Export is a pure function of the document into an `nbformat` v4
notebook written against the public `tit` scripting API, with the document itself riding along in
`metadata.ti_toolbox.pipeline`.

---

## 2. Files

### New — Python

| File | What it is |
|---|---|
| `tit/pipeline/__init__.py` | Package façade; four pure modules, no SimNIBS, no `tit.server`. |
| `tit/pipeline/document.py` | `PipelineDocument`/`Node`/`Edge`, the `PORTS` table (typed ports per kind), parsing with reasons. |
| `tit/pipeline/validate.py` | `validate()` (acyclicity, port compatibility, unbound required inputs, isolated-node warnings) and `can_connect()` — the refusal reason the canvas shows mid-drag. |
| `tit/pipeline/plan.py` | Document → `list[PlannedJob]` whose `after_labels` **are** the edges; static vs dynamic binding rules; per-subject and per-simulation fan-out; config round-trip through each kind's dataclass. |
| `tit/pipeline/notebook.py` | Document → `nbformat` v4 notebook (Mermaid title cell, markdown+code per node in topological order, bindings as Python variables, final run-all cell, document in metadata). |
| `tit/tools/pipeline_resolve.py` | The `resolve` step: an ordinary `tools` job that reads a producer's output directory and records the dynamic binding. |
| `tit/server/routes/pipelines.py` | `GET /api/pipelines{,/kinds,/{name}}`, `PUT`/`DELETE /api/pipelines/{name}`, `POST /api/pipelines/{validate,run,export}`. |

### New — contracts / docs

- `contracts/pipeline.schema.json` (JSON Schema 2020-12, `version: 1`).
- `contracts/openapi.v1.yaml`: six new paths under tag `pipelines`, eleven new component schemas
  (`Pipeline`, `PipelineNode`, `PipelineEdge`, `PipelineRequest`, `PipelineRunRequest`,
  `PipelineRunResult`, `PipelineValidation`, `PipelineIssue`, `PipelineJobPreview`,
  `PipelineListEntry`, `PipelineKinds`). Regenerated `contracts/openapi.v1.json`
  (`dev/build_contract.py`) and `desktop/src/renderer/api/schema.d.ts` (`pnpm run gen:api`).
- `contracts/SCHEMA-CHANGES.md`: one dated entry (2026-09-05, `feat:pipeline-canvas`).
- `docs/wiki/pipelines.md` + one nav row in `docs/_data/nav.yml`.

### New — desktop

| File | What it is |
|---|---|
| `pages/pipeline/index.tsx` | `PageDef` (id `pipeline`, `Workflow` icon). |
| `pages/pipeline/graph.ts` | Client mirror of the port table, `canConnect`, `topologicalOrder`, `subjectsOf`, card summaries. |
| `pages/pipeline/api.ts` | The seven `/api/pipelines*` calls, through generated contract types. |
| `pages/pipeline/editors.ts` | Node editor state → node config, **by calling the pages' own builders** (`buildFlexConfig`, `buildSimulationConfig`, the Analyzer's `buildConfig`). |
| `pages/pipeline/NodeInspector.tsx` | Double-click form; reuses `optimizer/FlexSections`' `ObjectiveSection`/`ElectrodesSection` and the shared `RoiPicker` by import. |
| `pages/pipeline/PipelinePage.tsx` | Palette + React Flow canvas + right pane (receipt over `JobConsole`). |
| `pages/pipeline/pipeline.css` | Tokens only; one hue per port type shared by handle and wire. |

### Edited — small, and why

| File | Change |
|---|---|
| `desktop/src/renderer/app/registry.ts` | `"pipeline"` into `NAV_ORDER` after `analyzer` (⌘6 falls out of the index). **Plus**: `shortcutForSlot` no longer hard-codes Settings to `"9"` — a ninth rail row would have put two pages on ⌘9. It now takes the first digit the rail does not (`"0"` today). |
| `desktop/src/renderer/app/keyboard.ts` | Digit regex `[1-9,]` → `[0-9,]` and its comment, so ⌘0 reaches Settings. |
| `desktop/src/renderer/app/KeyboardSheet.tsx` | "same as ⌘9" → "same as ⌘0". |
| `desktop/tests/unit/shell-registry.test.ts` | The three assertions that encoded "eight rows, ⌘9 Settings". Rewritten to follow `NAV_ORDER` rather than a hand-typed list, so the next rail row needs no edit here. **Called out because it is another lane's file in spirit** — it is the direct consequence of my one-line `NAV_ORDER` edit and nothing else in it changed. |
| `desktop/tests/mock-server/server.mjs` | A JS mirror of the pipeline document/validate/plan plus the seven routes. |
| `desktop/tests/mock-server/contract.test.ts` | Exercises the six new paths (that test asserts *every* declared path is exercised, so adding paths without this fails it). |
| `desktop/package.json` | `+ "@xyflow/react": "12.11.6"` (exact pin). `pnpm install` run. |
| `pyproject.toml` | New `[project.optional-dependencies] pipeline = ["nbformat>=5.1.4"]`. `dependencies` stays `[]` — see DECISIONS below. |
| `container/blueprint/Dockerfile.ti-toolbox`, `.layered` | `nbformat` added to both pip lines, with a comment naming why. |

### New — tests

`tests/test_pipeline_graph.py` (23), `tests/test_pipeline_plan.py` (11),
`tests/test_pipeline_notebook.py` (7), `tests/test_pipeline_routes.py` (13),
`desktop/tests/unit/pipeline-graph.test.ts` (16), `desktop/tests/e2e/pipeline.spec.ts` (8),
`desktop/tests/e2e/real/pipeline.spec.ts` (3).

---

## 3. The design, decision by decision

### D1 — nodes are job kinds, edges are typed outputs

Node kinds: `pre`, `leadfield`, `flex`, `ex`, `mex`, `sim`, `analyzer`, `source`, `stats`. Every one
is an existing `tit.jobs.spec.JOB_KINDS` entry — asserted, not assumed
(`test_pipeline_graph.py::test_every_node_kind_is_a_real_job_kind`).

`leadfield` is in the list although the plan's §1-D prose named eight kinds: the plan also names
`leadfield` as a **port type**, and without a node that produces one the port could never be wired.
It is an existing job kind, so this adds nothing new to the system.

Port table (`tit/pipeline/document.py::PORTS`):

| kind | inputs | outputs | required |
|---|---|---|---|
| `pre` | — | subjects | — |
| `leadfield` | subjects | subjects, leadfield | — |
| `flex` | subjects, roi | subjects, montages, roi | — |
| `ex` / `mex` | subjects, roi, leadfield | subjects, montages, roi | — |
| `sim` | subjects, montages | subjects, simulation | subjects |
| `analyzer` | subjects, simulation, roi | subjects | subjects, simulation |
| `source` | subjects | subjects | subjects |
| `stats` | subjects | — | subjects |

A *required* input must be wired **or** satisfied by the node's own config, which is what keeps a
hand-configured one-node Simulator a legal pipeline.

### D2 — run = one job group

`POST /api/pipelines/run` → `plan_pipeline(doc)` → `submit_plan(planned, group_cap=parallel_subjects)`.
One `group_id` on every job; `after` on each job is the document's edges resolved to real job ids by
the same label-resolution `plan_preprocessing` uses. The scheduler's group cap applies unchanged.

### D3 — bindings resolved server-side

Two flavours:

- **Static** — `subjects` and `roi` always, and `simulation` when the producing `sim` node names its
  own montages. Resolved at submit time, written straight into the downstream config. `sim → analyzer`
  fans the analyzer out to one job per `(subject, simulation)`.
- **Dynamic** — `montages`, `leadfield`, and a `simulation` whose upstream montages are themselves an
  optimizer's output. These cannot be known from any config: a flex run directory is *named at run
  time* (`PathManager.flex_search_run`, and `FlexResult.output_folder`'s basename is the montage
  name). Each gets one `tools` job `tit.tools.pipeline_resolve` planned between producer and
  consumer, inheriting the producer's `after` and becoming the consumer's.

A dynamic edge deliberately does **not** also name its producer in the consumer's `after`: the
resolve step already waits for it, and a second edge would put a dependency in the submitted DAG that
the document does not have.

### D4 — notebook export

`nbformat` v4. Title cell with a Mermaid `graph LR`; a markdown + code cell per node in topological
order; setup cell binding the project and declaring `SUBJECTS`/`EEG_NET`; a final run-all cell.
Bindings are Python variables (`flex1_subjects = pre1_subjects`,
`load_montages(montage_names=flex1_montages, …)`, `for simulation in sim1_simulations:`). The
document is in `metadata.ti_toolbox.pipeline`. Cell ids are deterministic (`cell-<n>`), which makes
export byte-stable — asserted.

### D5 — the canvas

React Flow (`@xyflow/react` 12.11.6, MIT). Palette left, canvas centre, receipt + `JobConsole`
right. Cards carry kind, name, a one-line summary and a live state chip; ports are coloured by type
and the wire takes the same hue. An illegal drag is refused with `canConnect`'s reason in a transient
line over the canvas. Save/Load under `code/ti-toolbox/pipelines/<name>.json`, plus Import JSON.

### D6 — gate

§4 below.

---

## 4. Gate evidence — every command and its real output

### 4.1 Python

```
$ python3 -m pytest tests/ -q
3734 passed, 47 skipped, 21 deselected, 13 warnings in 67.14s (0:01:07)
```

```
$ python3 dev/route_import_guard.py
  tit.server.routes.pipelines                 31.7 ms  ok
  …
route_import_guard: 21 route module(s) clean
```
(budget 400 ms; `pipelines` is the fourth-slowest of 21 and well inside it.)

`dev/contracts_check.py contracts/openapi.v1.yaml <dump>` reports the eleven new `Pipeline*`
component schemas as "missing from dump components" — **as it already does for `JobSpec`,
`JobDetail`, `JobGroupRequest`, `JobGroupResult`, `Event`, `Settings` and 40-odd others** (52 in
total on this tree, before and after this lane). Every one of them is a route whose body/response is
a plain `dict`/`list`, so FastAPI declares no component for it; the pipeline routes are written the
same way as the job routes deliberately. Not a regression this lane introduced, and not something
it should fix unilaterally — flagged for CX2.

The notebook half of D6 — *"exports a notebook that `nbformat.validate`s and whose code cells
execute against a stub `tit`"* — is `tests/test_pipeline_notebook.py::test_every_code_cell_executes_against_a_stub_tit`:
it writes a stub package defining only the names `docs/wiki/scripting.md` documents, concatenates
the notebook's code cells and runs them in a subprocess. Its stdout assertions:

```
run_pipeline ['ernie', '101'] ['create_m2m']
run_flex_search ernie
run_flex_search 101
load_montages ['L_Insula_mean', 'L_Insula_mean'] GSN-HydroCel-185.csv
run_simulation ernie ['L_Insula_mean', 'L_Insula_mean']
…
analyze_sphere ernie L_Insula_mean [-35.0, 5.0, 5.0] 10.0
four node demo finished: ['ernie', '101'] …
```

### 4.2 Desktop

```
$ pnpm run typecheck      # tsc -p tsconfig.node.json && -p tsconfig.web.json
(clean)

$ pnpm run lint
✖ 3 problems (0 errors, 3 warnings)
# all three warnings pre-exist this lane (ui/DataTable.tsx, ui/VirtualList.tsx: TanStack
# "incompatible library" compiler notes)

$ pnpm run test
Test Files  84 passed (84)
     Tests  949 passed (949)
```

### 4.3 Mock e2e (offscreen)

```
$ pnpm run pree2e && npx playwright test tests/e2e/pipeline.spec.ts
  ✓ 1 the Pipeline page is the sixth rail row and reaches an empty canvas
  ✓ 2 adding a step from the palette puts a card on the canvas
  ✓ 3 the four-node pipeline validates and its receipt is the DAG
  ✓ 4 running it creates exactly one job group, and Jobs shows one group
  ✓ 5 export returns a notebook that carries the pipeline back in its metadata
  ✓ 6 an illegal wire is refused, not silently dropped
  ✓ 7 the canvas renders the four-node graph (screenshot evidence)
  ✓ 8 save and load round-trip a document
  8 passed (5.7s)
```

Test 3 pins the DAG the receipt shows for `pre → flex → sim → analyzer`:

```
pre1:0                 after []
flex1:0                after [pre1:0]
sim1:resolve:montages  after [flex1:0]
sim1:0                 after [pre1:0, sim1:resolve:montages]
an1:resolve:simulation after [sim1:0]
an1:0                  after [an1:resolve:simulation, sim1:0]
```

Test 4 asserts the same chain on the **submitted jobs' real ids**, that all six carry one
`group_id`, and that `GET /api/jobs` shows exactly that one group.

Screenshot (offscreen, Electron, 1440×900):
`desktop/tests/e2e/artifacts/76319/pipeline-canvas.png` — palette, the four-node graph with
port-coloured labelled wires, and the right pane reading "**6** jobs in **one** group — 4 steps"
above the six labelled rows and the Terminal.

### 4.4 Real container

Shared dev container `ti-toolbox-fad740e5-tit-1` (port 8765, project `/Users/idohaber/datasets/000`)
picked up the new route module live:

```
$ curl -s -H "Authorization: Bearer $T" http://127.0.0.1:8765/api/pipelines/kinds
{"port_types":["subjects","montages","simulation","roi","leadfield"],"kinds":[{"kind":"pre",…
```

Two-node `sim → analyzer` pipeline on `sub-ernie`, montage inlined as `pc-real-224625`
(the `tests/smoke/payloads/sim.json` convention — nothing in the shared project's
`montage_list.json` is touched). Checked first that no other FEM simulation was running
(`/api/jobs?state=running` → `[]`, queued 0).

`POST /api/pipelines/validate`:

```
ok: true          order: ["sim1", "an1"]
sim1:0  sim       ernie   after []          tags [pipeline:pc-real-224625, node:sim1]
an1:0   analyzer  ernie   after [sim1:0]    tags [pipeline:pc-real-224625, node:an1]
```
Two jobs and **no** resolve step, which is the static-binding path: this Simulator names its own
montage, so the Analyzer's simulation name is knowable at submit time.

`POST /api/pipelines/run`:

```
group_id 25e8e66b1cbe48a7   pipeline pc-real-224625
81f8e1579f39451c sim      queued 25e8e66b1cbe48a7
a6124aefa80d44e6 analyzer queued 25e8e66b1cbe48a7
```

The binding, read back off the persisted specs on disk
(`/Users/idohaber/datasets/000/code/ti-toolbox/jobs/<id>/spec.json`):

```
81f8e1579f39451c  kind sim       after []                  montages ['pc-real-224625']
a6124aefa80d44e6  kind analyzer  after ['81f8e1579f39451c'] simulation 'pc-real-224625'
```

**Both jobs ran and succeeded, in order.** Poll of `GET /api/jobs` every 30 s
(`sim` is a real FEM run under emulation, ~14 min):

```
23:29:39  a4fc7eba:analyzer:queued  3dc337a1:sim:running
   …
23:43:09  a4fc7eba:analyzer:queued  3dc337a1:sim:running
23:43:39  a4fc7eba:analyzer:succeeded  3dc337a1:sim:succeeded
```

Final states and artifacts (`GET /api/jobs/{id}`):

```
3dc337a1 sim       succeeded  group 68dec04448eb47b4  exit 0
  artifacts: pc-real-232931/TI/mesh/pc-real-232931_TI.msh
a4fc7eba analyzer  succeeded  group 68dec04448eb47b4  exit 0
  artifacts: pc-real-232931/Analyses/Mesh/sphere_x-10.00_y-18.00_z9.00_r10.0_subject/{analysis.json,
             histogram_histogram.pdf, results.csv, roi_overlay.msh}
```

The analyzer wrote into the simulation the pipeline's own edge named — the binding is not merely
recorded, it decided which simulation was analysed:

```
$ ls derivatives/SimNIBS/sub-ernie/Simulations/pc-real-232931/
Analyses  documentation  fsaverage  high_Frequency  TI
$ head -3 …/Analyses/Mesh/sphere_x-10.00_y-18.00_z9.00_r10.0_subject/results.csv
Metric,Value
field_name,TI_max
region_name,sphere_x-10.00_y-18.00_z9.00_r10
```

Cleaned up afterwards: `rm -rf …/Simulations/pc-real-232931`; the subject's `Simulations/` is back
to its six pre-existing entries and no pipeline document was saved on the shared project.

*(An earlier attempt at this same run, group `25e8e66b1cbe48a7` / `pc-real-224625`, produced a
complete simulation but its job record stuck at `running`/`stalled` with `pid: None`. Cause was
mine and not the feature's: I ran `git stash` in this worktree while checking `dev/contracts_check.py`
(popped seconds later, nothing lost), which reverted tracked files under `tit/` long enough for the
container's `uvicorn --reload` to restart the worker and orphan the running job's process handle.
Both jobs were forced to a terminal state, the output directory removed, and the gate re-run clean
from a fresh submission — which is the run reported above. Recorded here because it is exactly the
failure `dev/route_import_guard.py`'s docstring warns about, from a different direction: **any**
write under `tit/` on the shared container restarts the server, and a git operation counts.)*

`desktop/tests/e2e/real/pipeline.spec.ts` encodes exactly this run (offscreen, `--project=real`,
`TIT_E2E_SERVER_URL`/`TIT_E2E_TOKEN`) and cleans up its own `Simulations/pc-real-<runid>` directory
in `afterAll`.

---

## 5. Proposed ARCHITECTURE contract section

> ### Pipelines
>
> A **pipeline** is a directed acyclic graph whose nodes are existing job kinds and whose edges are
> typed bindings between one node's named output and another node's same-named input. Its wire form
> is `contracts/pipeline.schema.json` (`version: 1`); it is stored in the project at
> `code/ti-toolbox/pipelines/<name>.json`.
>
> **Frozen properties.**
> 1. *A pipeline introduces no job kind.* Every `PipelineNode.kind` is a member of
>    `tit.jobs.spec.JOB_KINDS`, and its `config` is validated by the same
>    `tit.config_io.deserialize_config` call `POST /api/jobs` makes.
> 2. *A pipeline run is one job group.* `POST /api/pipelines/run` performs exactly one
>    `JobManager.submit_plan`; every job carries the one returned `group_id`, and every job's
>    `after` is the document's edges resolved to real job ids. There is no second executor and no
>    client-side sequencing.
> 3. *Port types are a closed set*: `subjects | montages | simulation | roi | leadfield`. An edge
>    joins two ports of the same type or it is refused with a reason.
> 4. *Validation answers, it does not throw.* `POST /api/pipelines/validate` returns 200 with
>    `ok: false` and one `PipelineIssue` per problem; 422 means the body is not a pipeline document.
> 5. *Export is a pure function of the document.* `POST /api/pipelines/export` reads no project
>    state beyond the project directory it prints into the setup cell, and round-trips the document
>    through `metadata.ti_toolbox.pipeline`.
>
> **Non-goals.** A workflow engine (retries, conditionals, loops, per-node scheduling policy);
> importing arbitrary hand-edited notebooks; drag-to-reorder.

## 6. Proposed DECISIONS entries

**D-nn — React Flow (`@xyflow/react`) is the pipeline canvas.**
*Context.* The canvas needs node/edge rendering, pan/zoom, typed connection handles and a
connection-validation hook. *Decision.* Take `@xyflow/react` 12.11.6 (MIT), pinned exactly, as the
only new renderer dependency of this feature. *Alternatives.* Hand-rolled SVG (weeks of pan/zoom,
hit-testing and handle geometry for no domain value); `dagre`+static SVG (no interaction).
*Consequences.* One dependency, ~50 kB gzipped, no transitive runtime deps of note. It is used as a
*controlled* component, which means the page must apply **every** `NodeChange` React Flow emits —
applying only position changes throws away its measurements and it keeps unmeasured nodes at
`visibility: hidden` (this bit us; see §8).

**D-nn — `nbformat` is an optional extra, not a hard dependency.**
*Context.* Notebook export needs `nbformat`; `pyproject.toml`'s `dependencies` is deliberately empty
because `tit` is installed into SimNIBS's own interpreter, where an unpinned resolve fights SimNIBS's
pins. *Decision.* `[project.optional-dependencies] pipeline = ["nbformat>=5.1.4"]`, with both
container recipes' pip lines installing it, so the desktop app always has it.
`POST /api/pipelines/export` returns an honest 501 naming the missing module when it is absent.

**D-nn — A pipeline run is one job group.**
*Context.* "Run it as a single job" was the maintainer's ask. *Decision.* Reuse the existing
`PlannedJob`/`after_labels`/`submit_plan` DAG machinery — the same one `plan_preprocessing` uses —
rather than adding a pipeline runtime. *Consequences.* Cancel, the scheduler's group cap, the jobs
rail, the events stream and the log tail all work on a pipeline for free. The price is that a
pipeline can never do anything a job group cannot: no conditionals, no retries, no loops. That is a
feature, not a gap.

**D-nn — Bindings are static where possible, and a `resolve` job where not.**
*Context.* Some edge values are knowable from the upstream config (`subjects`, `roi`, a `simulation`
name from a Simulator that names its own montages); others only exist after the producer ran (an
optimizer names its run directory at run time). *Decision.* Resolve the first kind at submit time;
plan a small `tools` job (`tit.tools.pipeline_resolve`) between producer and consumer for the second.
*Consequences.* The dynamic path's job DAG is correct today and its binding is *recorded*; feeding
the recorded value back into the consumer's config needs one hook this lane did not own (§7).

**D-nn — Settings' ⌘-number is derived, not hard-coded.**
*Context.* `shortcutForSlot` returned `"9"` for Settings because the rail was exactly eight rows;
Pipeline makes it nine. *Decision.* Settings takes the first digit the rail does not (`"0"` today);
⌘, remains its alias. *Consequences.* The rail can grow again without silently binding two pages to
one key.

## 7. The one change this lane needed and did not own

`tit/jobs/manager.py::_runner_config_path` writes the runner's `config.json` from `spec.config` at
admission time. For a **dynamic** binding to reach its consumer, the value the resolve step found
has to be merged into that config *after* the resolve job ran and *before* the consumer is admitted.
The whole change is three lines, additive and inert when the file is absent:

```python
        payload: dict[str, Any] = dict(spec.config or {})
        payload["project_dir"] = self.project_dir
+       # A pipeline's `resolve` step (tit.tools.pipeline_resolve) writes the values a dynamic
+       # binding produced next to the consumer's job record; merge them in at admission, when
+       # they finally exist.
+       bindings_file = os.path.join(job_dir(self.project_dir, spec.id), "bindings.json")
+       if os.path.isfile(bindings_file):
+           with open(bindings_file, encoding="utf-8") as fh:
+               payload.update(json.load(fh))
```

…together with a `--consumer-job <id>` argument on `tit.tools.pipeline_resolve` so it can address
that file (the resolve job's config would carry the consumer's job id, which `submit_plan` knows).
I stopped at the boundary as the lane rules require. Until it lands, the honest statement — the one
in `docs/wiki/pipelines.md` and in the module docstring — is: **static bindings work end to end;
a dynamic binding queues the right jobs in the right order and records what it resolved, but the
consumer still needs that field set on its own form.** The D6 mock gate asserts the DAG (which is
complete) and the D6 real gate uses the static path (which is complete).

## 8. Open items

1. **Dynamic binding write-back** — §7. The single highest-value follow-up.
2. **A saved pipeline's node forms open at their defaults.** The document stores each node's *built
   config* (which is what validates, runs and exports); the editor state that produced it is page
   session state. No v3 page has a config → form-state reader, so Load restores the configs but not
   the form. The page says so in a toast when loading. Fix: give each page's builder an inverse, or
   persist the editor state in a sidecar next to the document.
3. **`ex` / `mex` / `leadfield` / `source` / `stats` nodes are edited as JSON.** `buildExConfig` /
   `buildMExConfig` take a resolved leadfield path, an `ExTarget` and a run name that only the
   Optimizer page computes; the other three have no v3 form at all. The JSON is still validated
   server-side against the real dataclass, so the failure mode is a sentence, not a broken job.
4. **Node status chips depend on the receipt's label order.** `JobStatus` carries no `tags` on the
   wire, so the page maps job id → node by zipping the validation preview's labels with the run
   response's jobs (`submit_plan` creates them in plan order, one for one). Adding `tags` to
   `JobStatus` would make this direct — a contract change I did not want to make in this lane.
5. **`Receipt` from `pages/_shared/run` was not reused.** It renders a `PlanModel`
   (subject × stage cells); a pipeline's receipt is job-labels-and-`after` shaped. The pipeline pane
   renders a local list following the same "first 15 + … and K more" rule. If SG's `PlanModel`
   grows a non-subject-grid form, this should switch to it.
6. **Screenshot is the mock's canvas, not the real one.** The real-server spec asserts behaviour
   over the API; a real-data screenshot of the page would need a completed run in the shot.
7. **A `--reload` restart orphans a running job.** Not this lane's code, but this lane tripped it
   (§4.4): the manager keeps the child pid in memory only, so a worker restart leaves a finished
   process's job at `running`/`stalled` with `pid: None` forever, and every dependant sits queued
   behind it. `POST /api/jobs/{id}/force` is the escape hatch and it works, but it lands the job in
   `lost` — a `FAILED_LIKE` state — so the rest of the group is skipped. Worth a look: re-adopt a
   job's process on manager start-up from the persisted `status.json` `pid`/`create_time` pair,
   which is already written for exactly this purpose.

## 9. Proposed ROADMAP lines

- **Notebook import.** `POST /api/pipelines/import` reading `metadata.ti_toolbox.pipeline` out of an
  uploaded `.ipynb` and returning the document, closing the round trip export already encodes.
  (Parsing hand-edited Python stays a non-goal.)
- **More port types.** `mesh` (a specific field mesh into a visualiser or a `blender` node),
  `atlas`, and `report` — each needs a producer and a consumer that genuinely take it, or it is a
  wire with nothing on either end.
- **Pipeline templates.** Ship the two or three graphs the wiki teaches (`pre → flex → sim →
  analyzer`; `sim → analyzer → stats`) as starting points in the palette.
- **Per-node scheduling hints.** Today `parallel_subjects` is one number for the whole group. A node
  that is cheap (analyzer) and one that is not (sim) could carry different caps.

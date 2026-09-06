To-Do List:

### Opportunities for Early Contributors

- [ ] continue to write unit tests and potentially integration tests
- [ ] docs maintenance - wiki, gallery, API (via MkDocs), etc.

### UI - Frontend

- [ ] Ex-search viewer - graphical UI for electrode visualization and selection.
- [ ] Convert to fully-based Electron frontend → in progress (**v3.0.0**, plan below; Phase 0 started 2026-08-27).

### Other

- [ ] Integrate with openssf best practices

---

## v3.0.0 — Electron/TypeScript GUI over an (almost) unchanged Python backend

**Status:** IN PROGRESS — Phase 0 started 2026-08-27. §9 answers are recorded as an ADR in
`tracks/active/v3-electron-gui.md`. **Decision 2026-08-27:** the GUI moves to Electron now; Freeview and
Gmsh stay *in the container on X11* for 3.0 and are launched by `tit.server` from a ViewSpec; an internal
web renderer (spike (c) in `dev/notes/v3-spikes.md`) is a separate later track that retires them step by
step. Everything below that said "X11 goes away" is amended accordingly (§0, §1, §2.6, §2.7, §2.8, §3.C,
§4, §5, §9, §10).
**Branch:** `feature/v3-electron-gui` (long-lived integration branch; phase PRs target *it*, never
`main`; periodic `main → feature/v3-electron-gui` merges).
**Written:** 2026-08-26 against `main @ 0c0ef614`, after a read-only audit of the repo (9 agents)
and an adversarial review of this text (5 lenses; every accepted finding is folded in).
**Supersedes:** the "Convert to fully-based Electron frontend?" item above, the Electron half of
`tracks/active/launcher-parity.md`, and the unmerged `feature/launcher-redesign` branch.

### 0. Scope in one paragraph

Replace the PyQt5 GUI (`tit/gui/`, 28,255 LOC, runs *inside* `simnibs_container`, displayed via
X11/XQuartz/VcXsrv) with a native Electron + TypeScript desktop app on the host. The Python package
`tit` stays the only place scientific logic lives and keeps working from Jupyter/scripts exactly as
today. The UI talks to the container through one new Python service (`tit.server`) that owns a
**job model** (queue, dependencies, locks, budget, live events, cancellation). Two hard
requirements: **live monitoring** of every running job, and **parallel processing** (pre-process
subject A while a simulation runs on subject B) with guards so parallel jobs cannot corrupt each
other. Ship as **v3.0.0** with a new `idossha/simnibs:v3.0.0` image.

Non-goals for 3.0: two projects open in one app instance, a third-party UI plugin API, GPU work,
HPC job submission through SLURM (architecture leaves the door open, §2.7), and any change to
numerical code (SimNIBS calls, envelope math, optimizers, stats). **Also out of 3.0 (decision
2026-08-27):** replacing Freeview/Gmsh with an embedded renderer and removing X11 — tracked separately
as the "internal viewer" track (`dev/notes/v3-spikes.md` holds the evidence).

### 1. Why (what the current setup costs)

- **X11 is the biggest install/support burden** and exists today because the GUI process lives in
  the container (in 3.0 it remains, but only for the Freeview/Gmsh windows — §2.6): `loader.py:125-219` (xhost/XQuartz), `package/src/backend/env.js:69-436` (~250
  LOC DISPLAY/XQuartz/VcXsrv), three compose files mounting `/tmp/.X11-unix` + `~/.Xauthority`,
  `xhost +` never reverted (`env.js:342-346`). All of it disappears when the UI runs on the host.
- **~3,000 LOC of scientific/orchestration logic is trapped in Qt files** (gross ≈3.8k incl. ~350
  dead and ~400 UI-ish lines) and unreachable from scripting: flex adaptive-focality/Pareto
  *driver* (~300 LOC in `flex_search_tab.py:1428-1846`; the grid/plot/manifest parts already live
  in `tit/opt/flex/pareto.py`), ex-search multi-ROI pipeline + shadow log files
  (`ex_search_tab.py:533-965, 2304-2957`, ~1,000 LOC incl. a dead chain `2958-3123` referencing a
  non-existent `tit/opt/ex/ex_analyzer.py`), flex-run→Montage electrode mapping and freehand
  `stim_configs` parsing (`simulator_tab.py:958-1300`), the **simulation HTML report** (only the Qt
  tab generates it, `simulator_tab.py:1644-1800`; scripted runs get none), ROI→annot/label
  resolution + FreeSurfer LUT parsing (`components/roi_picker.py:814-1529`, ~450 LOC), NIfTI group
  averaging and nilearn group figures computed inside QThreads (`extensions/nifti_group_average.py`,
  `extensions/nilearn_viz.py`), leadfield FEM generation **inside the GUI process**
  (`ex_search_tab.py:246-377`), custom tissue conductivities reaching the solver only via
  `TISSUE_COND_<n>` env vars (`conductivity_dialog.py:185-209` → `tit/sim/base.py:263-268`).
- **No job model.** Each tab owns one `QThread` + `subprocess.Popen(["simnibs_python","-m","tit.<module>",cfg])`
  (`components/base_thread.py`); success = exit code; "progress" = keyword colouring of free text
  (`base_thread.py:62-91`). Nothing prevents two jobs on the same subject/stage; every done-check
  is check-then-act on output dirs (`charm.py:95-99`, `recon_all.py:155-162`, `qsiprep.py:155-163`).
  Stop does not reach the tools: `tit.pre` starts each child in its own session
  (`tit/pre/utils.py:461`), so `killpg` orphans recon-all/charm. Closing the GUI tears the stack
  down (`docker-manager.js:404-416`), killing hour-long jobs.
- **Security posture would get worse if extended as-is:** container runs as root with
  `/var/run/docker.sock` mounted, token-less JupyterLab published on `0.0.0.0:8888`
  (`entrypoint.sh:109,120`, `docker-compose.yml:37-38`); Electron 28 (EOL) with
  `nodeIntegration:true, contextIsolation:false` (`package/src/main.js:140-141`).
- **Duplicated launcher logic:** project scaffolding in JS (`project-service.js`, `main.js:370-548`,
  hard-coded `'2.4.0'`, `.initialized` marker Python does not know) vs `tit/project_init/`; user
  config dir resolved in 5 places, FreeSurfer volume naming in 4, compose env in 3 (loader.py,
  env.js, loader_dev.py).

### 2. Target architecture

```
 HOST                                                      CONTAINER (simnibs_container, headless, no X11)
 ┌─────────────────────────────────────────────┐            ┌─────────────────────────────────────────────────┐
 │ Electron shell (TypeScript)                 │            │ PID 1: docker-init → entrypoint.sh →            │
 │  main:    docker CLI lifecycle (compose up/ │  HTTP/WS   │   simnibs_python -m tit.server --supervise        │
 │           attach), project picker,          │◄──────────►│   ├─ REST /api/…  catalog · configs · files ·   │
 │           shell.openPath, notifications     │ host       │   │      settings · validate/plan · jobs · caps  │
 │  preload: contextBridge (≤10 methods)       │ 127.0.0.1  │   ├─ WS  /ws/jobs  /ws/jobs/{id}  /ws/system     │
 │  window:  loadURL(http://127.0.0.1:<port>)  │ :<port>    │   ├─ JobManager: DAG · locks · budget ·          │
 │           (UI served by tit.server —        │            │   │     start_new_session · events · cancel      │
 │            same origin, no CORS)            │            │   └─ serves /  (UI bundle) and /docs (offline)  │
 │           NiiVue · three.js · uPlot         │            │            │ spawns UNCHANGED runners            │
 └─────────────────────────────────────────────┘            │            ▼                                    │
   python loader.py  (developer/HPC tooling)                │  simnibs_python -m tit.sim|pre|opt.flex|opt.ex  │
     --serve → prints http://127.0.0.1:<port>/?token=…      │     |opt.mex|analyzer|stats|source|blender|…    │
     (browser mode: same UI, experimental)                  │     spec.json → events.jsonl + stdout.log       │
                                                            └─────────────────────────────────────────────────┘
```

**Principles**
1. `tit` is the single source of truth. Anything the UI needs to *know* (subjects, montages,
   atlases, regions, existing outputs, output-dir conventions, lock conflicts) is a Python function
   behind the server; TypeScript never re-implements BIDS/PathManager rules (macOS
   case-insensitivity hides whole bug classes — see memory).
2. The server never runs *jobs* in-process. It does import `tit` subpackages (and therefore
   SimNIBS — `tit/sim/__init__.py:45 → sim/base.py:33`, `tit/opt/__init__.py:53-55 →
   opt/ex/engine.py:15`) once at startup; catalog/validate/plan routes are plain `def` handlers
   (Starlette threadpool) with `(path, mtime)`-keyed caches; the few routes that load volumes/meshes
   (nibabel label scans, view-spec percentiles, skin-surface export, `ExSearchEngine` ROI ops) run
   in a 1–2 worker `ProcessPoolExecutor` so a native crash cannot take the server down. Every job
   is still a separate OS process running the **same** `simnibs_python -m tit.<module> spec.json`.
3. Decisions flow front→back as **typed JSON that round-trips through the existing config
   dataclasses**; the schema is generated from them, never hand-written in TS (§2.2).
4. Scripting parity: everything the UI can do is one Python call or one JSON runner away.
   Extracted logic goes into `tit/<module>` first, the UI second.

#### 2.1 Bridge decision: a Python job server, not docker-exec-per-job from Electron

| | A. Electron main orchestrates `docker exec` per job | **B. `tit.server` inside the container (chosen)** |
|---|---|---|
| Backend change | none for runners; every *query* (regions, montage resolution, existing outputs…) is a fresh `simnibs_python -c` exec | one additive package `tit/server/` + `tit/jobs/` + a handful of small runner edits (§3) |
| Query latency | PathManager-only listings are cheap either way; anything touching `tit.sim`/`tit.opt`/`tit.analyzer` pays the SimNIBS + nibabel import (seconds) per exec | in-process, milliseconds after startup |
| Job model / DAG / locks / budget | in TypeScript; invisible to CLI/notebook users | in Python; runners hold the same locks (§2.4), notebooks can submit into the same queue |
| Cancellation | `docker exec kill` hacks, no process-group control | server is the parent: process-tree snapshot + signals (§2.3) |
| Live monitoring | parse exec stdout in TS | server tails per-job `events.jsonl` + psutil process trees |
| Works without Electron | no | yes: browser mode (`loader.py --serve`), later JupyterHub/HPC (§2.7) |
| New container deps | none | `fastapi`, `uvicorn[standard]` (pure Python; pydantic v2 comes with fastapi) |

B wins on both hard requirements and on scripting parity. Cost: ~2–3k LOC of Python *plumbing*
(not science) and two pip packages in `Dockerfile.simnibs`.

#### 2.2 Decision-passing contract (front → back)

- **Schema source = the existing stdlib dataclasses** (`SimulationConfig`/`Montage`, `FlexConfig`
  + ROI/electrode classes, `ExConfig`/`MExConfig`, `GroupComparisonConfig`/`CorrelationConfig`,
  `QSIPrepConfig`/`QSIReconConfig`, blender `MontageConfig`/`VectorConfig`/`RegionConfig`, source
  `ForwardConfig`/`FsavgMapConfig`) — plain types, so `pydantic.TypeAdapter(cls).json_schema()`
  works without modifying them.
- **`tit/config_io.json_schema(cls)`** = TypeAdapter schema + a post-pass that (a) adds
  `"_type": {"const": <name>}` to `properties` and `required` for every class in
  `_TYPE_DISCRIMINATED`/`_BY_NAME` (`_type` is injected by `_serialize` only, `config_io.py:43-62`,
  it is not a field), (b) rewrites unions of discriminated members from `anyOf` to `oneOf` +
  `discriminator: {propertyName: "_type"}` (without this, `FlexConfig.AtlasROI` vs
  `SubcorticalROI` are structurally overlapping and a TS form cannot tell them apart), (c) names
  `$defs` `<Outer><Inner>` (three `AtlasROI`, two `PoolElectrodes`, two `Subject` collide by name).
  Two *type-only* annotation tightenings: `Montage.electrode_pairs: list[tuple[str | list[float],
  str | list[float]]]`, `Montage.channels: list[tuple[list[int], list[int]]] | None`
  (`tit/sim/config.py:114,117` are `list[tuple]` → `unknown[][]` in TS).
- **FastAPI routes accept `dict[str, Any]` bodies and call `deserialize_config(cls, data)`**; the
  dataclasses are never FastAPI body/response types (pydantic smart-union would silently pick the
  wrong ROI class on structural ties).
- **One symmetric deserialiser**: `deserialize_config(cls, dict)` driven by `dataclasses.fields` +
  `_type`. Today flex/ex/mex already round-trip via `**data` (`opt/flex/__main__.py:27-29`,
  `opt/ex/__main__.py:32`, `opt/mex/__main__.py:54`); **sim, stats, pre, analyzer, source
  hand-roll a key subset** (`sim/__main__.py:54-78`; `stats/__main__.py:48-82` drops
  `alpha/cluster_threshold/n_jobs/nifti_file_pattern/atlas_files`). Those five change behaviour;
  round-trip test per class.
- **Three pipelines have no dataclass today** (`tit.analyzer` dict, `tit.pre` 15-flag dict + nested
  QSI dicts, `tit.source` dict). Add `AnalyzerConfig`, `PreprocessConfig`, `SourceConfig`,
  `LeadfieldConfig` as thin dataclasses wrapping existing kwargs (runners accept both during the
  transition).
- **Env-var side channels become explicit config fields** (additive): `TISSUE_COND_<n>` →
  `SimulationConfig.tissue_conductivities: dict[int, float]` (env still honoured for one release
  with a deprecation warning); `FLEX_MONTAGES_FILE` → montage sources resolved server-side;
  ex-search `SELECTED_EEG_NET`/`ROI_DIR` → `ExConfig` fields; `TI_LOG_FILE` (GUI-only shadow log,
  never read by `tit/opt`) removed. `SimulationConfig.open_in_gmsh` keeps its field and default;
  the server sets it `False` on jobs it submits and the UI never exposes it.
- **Validate / plan endpoints** so the UI never recomputes path conventions:
  `POST /api/validate/{kind}` (same errors `__post_init__`/`run_pipeline` raise);
  `POST /api/plan/{kind}` → resolved output dirs, existing-output conflicts
  (`tit.pre.preflight`, `pm.simulations()`, `analysis_output_dir`), the resolved `Montage` for a
  flex/freehand source, ex-search search-space counts, the job's `cost`, **and `lock_conflicts:
  [{key, held_by, kind, subject, started_at}]`** so the Run button can say "will queue behind #12
  (charm sub-101, running 1h42m) — Queue anyway / Cancel" *before* submission.
- **Contract-first, from Phase 1:** `contracts/openapi.v0.yaml` + `contracts/events.schema.json`
  + sub-ernie fixtures (`tests/fixtures/api/`: subjects, montages, atlases, one job's
  `events.jsonl`) are hand-authored in Phase 1 so the frontend can start in Phase 4 against a mock;
  the real server's generated OpenAPI must diff clean against v0 (CI gate). TS types via
  `openapi-typescript`, client via `openapi-fetch`; CI fails if `contracts/openapi.json` is stale.
- **Version handshake:** `GET /api/version` returns `tit.__version__` + `schema_hash`. Refuse only
  on schema-hash mismatch; on version-only mismatch allow read-only screens (Viewer, Results, Jobs)
  with a banner. Projects may pin an image tag in `code/ti-toolbox/config/project.json`
  (`image_tag`), honoured by both launchers, so labs that freeze an image for a study are never
  locked out.
- **`GET /api/capabilities`** (docker socket present? FreeSurfer present? bpy?) so the UI greys out
  job kinds a runtime cannot execute (QSIPrep on Apptainer, Blender exports without bpy).

#### 2.3 Job model (`tit/jobs/`)

- **JobSpec** `{id, kind, config, subject_ids, after: [job_id], locks: [key], cost: {cpus, mem_gb},
  env: {}, created_by: gui|browser|api|notebook, created_at, group_id, tags}`;
  `kind ∈ {pre, sim, flex, flex_adaptive, flex_pareto, ex, mex, leadfield, analyzer, stats, source,
  blender, nifti_average, nilearn, report, tools}` (`tools` = short utilities such as electrode
  overlay creation).
- **Groups / DAG.** `POST /api/jobs/groups` takes a `PreprocessConfig` + subject list and calls
  `tit/jobs/plans.py::plan_preprocessing(config, subject_ids) -> list[JobSpec]` (Python, reusable
  from notebooks). Stage groups, in dependency order per subject:
  `G1={dicom}` · `G2a={charm+subject_atlas}` after G1 · `G2b={recon-all, incl. subcortical}` after
  G1 · `G3={tissue}` after G2a · `G4={qsiprep}` after G1 · `G5={qsirecon}` after G4 ·
  `G6={dti}` after G5 and G2a · `report` after all of the subject's stage jobs. Admission requires
  all `after` jobs `succeeded`; if any failed/cancelled the dependant becomes `skipped(reason)`.
  The Jobs panel renders a group as a tree (subject → stages). A per-batch "subjects in parallel
  (N)" cap travels with the submission (replaces today's `parallel_recon/parallel_cores`).
- **States** `queued → running → succeeded | failed | cancelled | skipped`, plus `lost` (server
  restarted, pid gone, no final event). `status.json` carries `waiting_on: [{key, job_id}]` and
  `budget_wait` reasons while queued; `{pid, create_time}` while running.
- **Persistence on disk, inside the project** (visible to notebook users, survives server/UI
  restarts): `<project>/code/ti-toolbox/jobs/<job_id>/{spec.json, status.json, events.jsonl,
  stdout.log}`; `PathManager.jobs_dir()`; `code/ti-toolbox/jobs/` added to `.bidsignore`.
  Retention: keep last 200 jobs or 30 days (configurable), prune on server start; `stdout.log`
  size-capped; `events.jsonl` keeps a rolling tail of `log` events (last 2,000) — full output stays
  in `stdout.log`. Runner logs stay where they are (`derivatives/ti-toolbox/logs/sub-<id>/…`).
- **Process topology.** Compose: `init: true` (docker-init reaps orphans), `command:
  ["simnibs_python","-m","tit.server","--supervise"]` executed through `entrypoint.sh` (so runners
  inherit `SetUpFreeSurfer.sh` and `PYTHONPATH=/ti-toolbox` — today's `docker exec` path gets
  neither and only works because of `WorkingDir`). `--supervise` is a tiny restart loop: a crashed
  server restarts inside the same container while runners keep going. A *container* restart loses
  running jobs (marked `lost` on next boot). HEALTHCHECK on `/api/health`.
- **Runner launch** = today's command with a safe spawn: `asyncio.create_subprocess_exec(...,
  start_new_session=True, stdin=DEVNULL, stdout=<jobs/<id>/stdout.log>, stderr=STDOUT,
  close_fds=True)` — never `preexec_fn` (unsafe with threads) and never a pipe (a dead server
  would `BrokenPipe` the runner). Env: `PYTHONUNBUFFERED=1`, `PYTHONFAULTHANDLER=1`, `TIT_JOB_ID`,
  `TIT_EVENTS_FILE`, `TIT_INTERFACE`, thread knobs from the budget (`OMP_NUM_THREADS`,
  `MKL_NUM_THREADS`, `NUMBA_NUM_THREADS`, `TI_NIFTI_WORKERS`), `cwd=/ti-toolbox`. Live and
  re-attached jobs use the same file-tail path (no second code path).
- **Re-attach on boot:** scan `jobs/*/status.json`; a pid is alive only if
  `psutil.Process(pid).create_time()` matches **and** `status() != ZOMBIE`; otherwise finalise from
  the last `result`/`exit` event or mark `lost`. A `lost` job offers "re-run from spec.json".
- **Events** (`events.jsonl`, written by the runner through `tit/logger.py`, tailed by the server
  by polling `st_size` every 250 ms with partial-line handling — inotify is unreliable on Docker
  Desktop mounts): `{"seq","ts","type":"log|stage|progress|marker|artifact|result|exit","level",
  "logger","msg","stage","i","n","pct","outputs":[…]}`. `seq` = line index; `GET
  /api/jobs/{id}/events?since=<seq>` and the WS `{"subscribe": {job_id: last_seq}}` replay the gap
  on reconnect. Sink: opened `O_APPEND`, one object per line ≤ 4 KB, flushed per record, attached
  to both the `tit` and `simnibs` loggers (flex/ex/mex/sim attach file handlers to `simnibs`
  today — that is where FEM progress goes); process-pool children inherit only `log` events.
  Human `%(message)s` stdout stays the default for terminals/Jupyter; the sink is opt-in via
  `TIT_EVENTS_FILE`. The runner's `finally` writes an `exit` event so `lost` vs `failed` is
  decidable.
- **Progress, three tiers** (nothing in SimNIBS/FreeSurfer is modified): (1) `stage`/`progress`
  from existing loops (`_run_step`, montage loop, ex combination loop, flex multistart loop,
  `run_simulation(progress_callback)` already exists); (2) `marker` events parsed from tool stdout
  by a per-tool regex table in the server's tailer (recon-all `#@# <step>` lines against the fixed
  `-all` step list → pct; charm step banners; nipype `[Node]` lines); (3) `liveness` computed
  server-side (seconds since last line + CPU% of the tree → active/stalled badge). Single-FEM jobs
  show elapsed + liveness, never a fake percentage.
- **Scheduler** (single-process asyncio; in-memory table authoritative while running): admission
  = `after` satisfied ∧ lock keys free ∧ Σ`cost` ≤ budget. Budget = container cgroup CPU/RAM
  (`get_inherited_dood_resources` already reads it) and `psutil.virtual_memory().available`;
  DooD siblings run *outside* the cgroup, so their `--cpus/--memory` are counted while the job
  runs and sampled via `docker stats --no-stream` for the Jobs panel. Per-kind default costs live
  in `tit/jobs/costs.py` (data, user-overridable; placeholders until spike (e): recon-all 4 cpu/8
  GB, charm 2/6, sim 1/4 per montage, leadfield 2/8, flex `cpus`/6, qsiprep = its own
  `cpus/memory_gb`). `plan_preprocessing` writes the QSI job's cost into
  `qsiprep_config.cpus/memory_gb` so siblings are bounded by the scheduler, not by the whole
  cgroup. `max_concurrent_jobs` is a ceiling derived from the budget, **not a flat 2** (a 20-subject
  recon-all batch on a 32-core box must still fan out). Runner exit −9 with no `result` event is
  reported as "likely out-of-memory"; the launcher warns when the Docker Desktop VM has < 12 GB.
- **Cancellation:** snapshot `psutil.Process(pid).children(recursive=True)` → SIGTERM the runner
  (graceful path: `run_pipeline` installs the handler because it owns the `CommandRunner`; ex/mex
  engines already have handlers, grace raised from 2 s to 10 s) → 10 s → SIGKILL runner **and every
  snapshotted descendant still alive** (tit.pre children are in their own sessions) → `docker stop`
  any sibling container labelled `tit.job_id=<id>` (both `docker run` builders gain `--label`,
  one line each; idempotent, on every cancel path) → release locks only after the tree is gone.
  flex/ex/mex/sim write their manifest/`run_config.json` **last**, and the catalog ignores run
  dirs without one, so cancelled runs never appear as results.
- **Force start:** `POST /api/jobs/{id}/force` skips lock waits; gated by a Settings toggle
  "Allow unsafe overrides".

#### 2.4 Concurrency policy (what may run in parallel)

Safe in parallel (disjoint writes, after the hygiene items below): `pre(A) ∥ sim/flex/ex/analyzer(B)`;
`recon-all(A) ∥ charm(A)` (FreeSurfer vs SimNIBS derivatives, T1 read-only); `tissue(A) ∥ sim(A)`;
`sim(A, m1) ∥ sim(A, m2)`; `flex(A) ∥ sim(A)`; `ex(A, run1) ∥ ex(A, run2)`; anything read-only
on A ∥ anything on B.

Lock keys (exclusive unless noted). Keys are **held by the runner process itself** (`with
tit.jobs.locks.hold(keys_for(config))`, ≈5 lines per `__main__`; default warn-and-continue,
`TIT_LOCKS=strict` refuses) and *predicted* by the scheduler from the same `keys_for()` function —
so a `simnibs_python -m tit.sim cfg.json` from a second shell and server jobs share one policy and
one lock directory. Direct Python calls (`run_simulation()` in a notebook) remain **advisory**;
`scripting.md` lists the unsafe combinations.

| key | held by | notes |
|---|---|---|
| `subject:<id>:stage:<dicom\|charm\|subject_atlas\|recon\|tissue\|qsiprep\|qsirecon\|dti\|subcortical>` | that stage | recon-all owns `subcortical` (it runs it itself, `recon_all.py:183-185`) |
| `subject:<id>:m2m:write` / `m2m:read` (shared) | write: charm, subject_atlas, DTI extraction, leadfield gen; read: sim/flex/ex/tissue/analyzer | anisotropic sim must not start while DTI writes `m2m/DTI_coregT1_tensor.nii.gz` |
| `subject:<id>:m2m:t1mni` | sim (until hygiene item 1 lands) | `start_t1_to_mni` writes `m2m/T1_<sid>_MNI.nii.gz` on **every** run (`sim/utils.py:770-777`) |
| `subject:<id>:bids:write` / `bids:read` | write: DICOM conversion, QSIPrep sidecar rewrite; read: charm/recon/QSIPrep | |
| `subject:<id>:leadfields` | exclusive: leadfield gen (all nets — `_cleanup` globs the shared `leadfields/` dir and `m2m/leadfield`, `opt/leadfield.py:77-83,105-110`); shared: ex/mex | per-net subdirs are a 3.1 item |
| `subject:<id>:sim:<montage>` | sim | same output tree |
| `subject:<id>:ex:<run_name>` / `mex:<run_name>` | ex/mex | `/api/plan` resolves `run_name` before admission; reuse rejected unless overwrite requested |
| `subject:<id>:analysis:<output_dir>` | analyzer | |
| `subject:<id>:rois` | short exclusive around ROI CRUD in the server (`m2m/ROIs/*.csv`, `roi_list.txt`); shared-read by ex/mex | |
| `subject:<id>:forward` | source | |
| `project:group_analysis:<output_dir>`, `project:stats:<type>/<name>` | analyzer group, stats | two group runs clobber each other today |
| `project:montage_list`, `project:project_status` | short exclusive around read-modify-write | |
| `project:qsi_work` | QSIPrep/QSIRecon | *or* per-subject work dir (`-w` one-liner in `docker_builder.py:198,299`; preferred — docs + the rerun-semantics error text in `qsiprep.py:157-165` change) |
| `daemon:image_pull:<image>` | first QSI job per image | |

Lock directory = `jobs/.locks/<sha1(key)[:16]>/` holding `{key, job_id, pid, create_time, ts}`
(`os.mkdir` is atomic on bind mounts; no `:` or user text in path components — NTFS; `fcntl` is
not trusted on virtiofs/gRPC-FUSE). On boot the server reconciles lock dirs against `status.json`
+ live pids and removes stale ones. Notebooks can inspect holders via `tit.jobs.locks.holders()`.

Backend hygiene that makes the table true (all small, all in §3.B): (1) `start_t1_to_mni` skips
when the MNI T1 exists and writes temp + `os.replace`; (2) `LeadfieldGenerator.generate()` resolves
its HDF5 by the known name `<net>_leadfield.hdf5` instead of `next(glob('*.hdf5'))`
(`leadfield.py:151`); (3) `generate_run_dirname` (flex) and ex-search log names gain a short uuid
suffix (second-resolution collisions); (4) `_create_dataset_description` (reports) and
`save_montage_data` write temp + `os.replace`; (5) the adaptive driver reads *its own* run's
manifest instead of "newest goal=mean manifest"; (6) `tit.sim` partial-output cleanup moves into
the runner scoped to *its* montage dir (today the tab `rmtree`s `Simulations/tmp` and every
montage dir of the run, `simulator_tab.py:1905-1925`); (7) `tit/pre/utils.py:461` switches to
`start_new_session=True`.

#### 2.5 Live monitoring (what the user sees)

- Global **Jobs panel** (persistent across screens; `Cmd/Ctrl+J`): state, kind, subject(s), stage
  progress or liveness badge, elapsed, CPU% / RSS of the process tree (psutil every 2 s; `docker
  stats` for DooD siblings), `waiting_on` with a link to the blocking job, Stop, and on completion
  the artifact list (reports, NIfTIs, CSVs) with "Open" (host path via Electron) / "View" (in-app).
  Group jobs render as subject → stage trees. `lost` jobs offer re-run from `spec.json`.
- Per-job **console**: levelled lines from `events.jsonl` in a virtualised list
  (`@tanstack/react-virtual`, Zustand ring buffer ≤ 50k lines, `requestAnimationFrame` batching,
  ANSI stripped server-side), raw `stdout.log` tab with "load earlier", "reveal log file".
- **System screen**: container CPU/RAM/disk from `/ws/system` (uPlot), running jobs, DooD
  siblings, **and unmanaged processes** (`simnibs_python -m tit.*`, charm, recon-all, `mri_*`, with
  argv-derived subject) as external rows with a confirm-guarded Terminate — the one thing power
  users use today's System Monitor for.
- **Error taxonomy** shown to users: `preflight` (structured problems from `/api/validate`),
  `lock_wait`, `budget_wait`, `runner_failed` (exit code + last 20 output lines —
  `CommandRunner.last_output_lines` exists), `oom_suspected`, `cancelled`, `skipped`, `lost`,
  `docker_unavailable`.
- Desktop notifications on completion; app close with running jobs asks "keep containers running
  in the background?" (decouples UI from job lifetime).

#### 2.6 Viewers (decision 2026-08-27: Freeview + Gmsh stay in 3.0, launched by the server)

| today (X11 subprocess spawned by a Qt tab) | v3.0 |
|---|---|
| `freeview` from the NIfTI Viewer tab (`nifti_viewer_tab.py:1101-1180`), ROI picker, ex AddROIDialog, analyzer | **Freeview, unchanged binary, launched by `tit.server`** (`POST /api/viewers/freeview` with a ViewSpec). The layer-spec builder (`nifti_viewer_tab.py:1272-1290`, `:961-1087`, `:832-959`) moves to `tit/viewspec.py` — `build_view(kind, ...)` + `to_freeview_args(spec)` (same grammar as `launch_freeview_with_files`, with the six audit bugs fixed: HF glob never matching `_scalar_subject_magnE`, `labeling_LUT.txt` ignored, `*_LUT.txt` not found in group mode, MNI template paths outside `resources/atlas`, thresholds dropped when percentile mode is off, single-subject MNI unreachable). The process inherits the container's `DISPLAY` (X11 mounts stay in compose) and is tracked as a job of kind `viewer` (no locks, no budget) so it shows in the Jobs panel and Stop works; the previous instance is terminated first, as today. The Viewer screen is the layer/threshold form + "Open in Freeview". Coordinate lookup for spherical ROIs stays manual (read Freeview's status bar, type it) until the internal viewer lands. |
| `gmsh` for `.msh` results (`analyzer_tab.py:2758-2782`; the SimNIBS-standard way to inspect field-on-mesh) | **Gmsh, unchanged, launched by `tit.server`** (`POST /api/viewers/gmsh {path}`), `.opt` sidecars written as today (`tit/tools/gmsh_opt.py`, `tit/analyzer/visualizer.py`, `tit/sim/TI.py`). Results screen: "Open in Gmsh" per mesh artifact. |
| *(later track: internal viewer)* | NiiVue was verified on sub-ernie for volumes + server-exported surfaces (`dev/notes/v3-spikes.md`, spike (c)); a three.js tet/surface renderer is the candidate for the Gmsh side. Both consume the same ViewSpec; nothing in 3.0 depends on them, and they retire Freeview → Gmsh → X11 in that order when they are good enough. |
| PyOpenGL electrode placement (`extensions/electrode_placement.py`, 358 LOC GL + ray casting) | three.js + Raycaster; skin surface exported by the server (`tit/blender/electrode_placement.py` already extracts the scalp from `.msh`); `stim_configs` writer moves to `tit/electrodes/placement.py`. **Default 3.1.** Because that extension is the *only* writer of `m2m/stim_configs/*.json` (`electrode_placement.py:1010-1036`) and the Simulator's Free-hand source reads them, the Simulator screen ships a **free-hand table editor** (label, x, y, z, type → same JSON via `tit/electrodes/placement.py`, "add from picked NiiVue coordinate") so the source keeps working without the 3D picker. |
| HTML reports opened with `xdg-open` inside the container | `<iframe sandbox="allow-scripts">` (no `allow-same-origin` → opaque origin, no cookie access) whose `src` is `/api/files/report/<id>` served with its own CSP (`default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:`) — reports embed inline `<script>` (`reporting/core/templates.py:866-868`) and are derived from run data, so they never run in the app's origin. "Open in browser" = `shell.openPath`. |
| matplotlib/nilearn PDFs & PNGs | produced by jobs as today; shown as artifacts (PDF viewer / img). |

#### 2.7 Launch paths after v3 (one user-facing path)

- **Desktop app (the documented path):** Launcher screen (Docker check, project dir, pull
  progress) → `docker compose -p ti-toolbox-<hash8(project path)> up -d` → wait for `/api/health`
  → `loadURL(http://127.0.0.1:<port>/?token=…)`. X11 is needed only for the viewer windows: the app
  carries the XQuartz/VcXsrv/`xhost` setup from `package/src/backend/env.js` (ported to
  `desktop/src/main/x11.ts`, `xhost` scoped to localhost and reverted on exit); a missing X server
  disables "Open in Freeview/Gmsh" with a message and nothing else. Windows stays supported via VcXsrv
  for viewers only.
  **Attach, don't kill:** if a stack for the same project is already up (CLI user, previous
  session) the app attaches to it; today `cleanupExistingContainers` force-removes any running
  `simnibs_container` (`docker-manager.js:184-198`). **Switch project:** the app queries
  `/api/jobs?state=running|queued` first and offers wait / cancel / keep-running-and-open-new; the
  per-project compose name means a second project is a second stack (image layers shared).
- **`loader.py` (developer / server / HPC tooling, not a user-facing path):** shrinks to a wrapper
  that shares the **same compose-environment computation** as Electron main (a tiny
  `tit_launch_env.py` bundled by both, or Electron gains `--headless up|shell|serve` and loader.py
  is deleted — decision §9.5). `python loader.py` = stack + shell; on shell exit it asks
  "N jobs running — keep containers running? [Y/n]" (today it runs `compose down`
  unconditionally, `loader.py:407-415`); `--detach`, `--down`, `--serve` (prints the tokenized URL
  and opens the host browser), `--jupyter` (JupyterLab with a token; published on `127.0.0.1:8888`),
  `--bind 0.0.0.0` opt-in for remote servers (token mandatory, LAN warning, always prints the
  `ssh -L <port>:127.0.0.1:<port> user@host` hint — replaces today's `ssh -X` advice in
  `troubleshooting.md:116`). `dev/loader/loader_dev.py` folds into `--dev`.
- In-container aliases: `GUI` → `simnibs_python -m tit.server` (prints URL + token; there is no
  browser inside the container), `NOTEBOOK` → tokenized JupyterLab.
- **Browser mode** (same bundle served by `tit.server`, `experimental` in 3.0 release notes):
  works because every renderer request is origin-relative. Electron-only features degrade via
  `window.tit?.isElectron`: "Open"/"Reveal" → show container path + copy; host file picker → text
  input of a container path; launcher/docker lifecycle/notifications → not available; viewer
  launches need an X display on the server side (documented: `ssh -X`).
- **JupyterHub (`deploy/jupyterhub`, untracked WIP) / HPC (Apptainer):** 3.1. Requires adding
  `jupyter-server-proxy` to the single-user image (not present today) and, for SLURM, a second
  runner backend (`tit/jobs/runner.py` is an interface: `LocalPopenRunner` in 3.0, `SbatchRunner`
  later — `sbatch --wrap`, status via `squeue`, same `events.jsonl` on the shared FS).
  `apptainer.def` gains fastapi/uvicorn in Phase 3; `/api/capabilities` reports no docker socket →
  QSI kinds unavailable with a reason.

#### 2.8 Security posture (must not regress while adding a server)

- **Bind/exposure:** inside the container the server (and Jupyter) listen on `0.0.0.0` — a
  `127.0.0.1` bind is unreachable through Docker port publishing on the bridge network (that is
  why today's `NOTEBOOK` alias uses `--ip=0.0.0.0`). Host exposure is restricted by the compose
  publish spec `127.0.0.1:${TIT_SERVER_PORT}:${TIT_SERVER_PORT}` (free port probed by the launcher).
  Under Apptainer (no network namespace) `--host` defaults to `127.0.0.1`.
- **Token provisioning:** the launcher generates a 32-byte token and passes it as compose env
  `TIT_SERVER_TOKEN` (same mechanism as `LOCAL_PROJECT_DIR`); Electron keeps it in memory. The
  server generates one only when the env is unset (HPC/JupyterHub) and prints it once. No
  root-written token file in the user's config dir (root-owned on Linux-native Docker: 0600 is
  unreadable by the desktop user, 0644 is world-readable).
- **Origin model (recommended, §9.1):** the main UI is *always* served by `tit.server`; Electron
  does `loadURL` after `/api/health`. Consequences: same-origin `fetch`/WS everywhere (Electron,
  browser mode, later JupyterHub proxy) → no CORS, no bearer plumbing in the renderer (`?token=` is
  accepted exactly once to set an `HttpOnly; SameSite=Strict; Path=/` cookie; thereafter cookie
  or `Authorization`), one bundle location, no UI↔image skew. Only the launcher screen is a local
  page on a registered `app://` scheme. Renderer code uses relative URLs and Vite `base: './'`.
  (Alternative if the bundle must ship in Electron: privileged `app://ti-toolbox` scheme +
  `CORSMiddleware(allow_origins=['app://ti-toolbox'])` + WS token via `?token=`/subprotocol.)
- **Server hardening:** `TrustedHostMiddleware(['127.0.0.1','localhost','127.0.0.1:*','localhost:*'])`;
  WS handshakes reject foreign `Origin`; file routes check `Sec-Fetch-Site ∈ {same-origin, none}`
  and are jailed to the project dir + `resources/` (path-traversal tests); CSP response header
  `default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; style-src 'self'
  'unsafe-inline'; worker-src 'self' blob:; frame-src 'self'; object-src 'none'`; reports in a
  sandboxed iframe with their own CSP (§2.6).
- **Electron:** `contextIsolation:true`, `sandbox:true`, dependency-free preload exposing ≤10
  methods (`selectDirectory`, `openPath`, `showItemInFolder`, `notify`, `getSettings/setSettings`,
  `stack.start/stop/status`, `onStackEvent`, `platform`, `appVersion`); latest stable Electron
  major at Phase-4 start, **pinned exactly** and bumped at the start of Phase 5 and in Phase 6
  (Electron has no LTS; 28 is EOL); pinned `electron-builder`/`@electron/notarize` (delete the
  `@latest` installs in `release-build.yml:86-89` now).
- **Jupyter:** off by default, started on demand with a token, published on `127.0.0.1:8888`.
- **X11 (3.0):** the socket + `.Xauthority` mounts and `DISPLAY` stay for Freeview/Gmsh; `xhost` is
  scoped (`+localhost` / `+SI:localuser:$USER`) and reverted when the app exits (today's `xhost +` is
  never reverted, `env.js:342-346`).
- **Docker socket:** unchanged for 3.0 (DooD for QSIPrep), documented; compose profile in 3.1.

#### 2.9 App behaviour (first run, Docker discovery, updates)

- **First launch:** welcome (writes the same marker `first_time_user.py` uses today) → project
  picker → telemetry consent modal (telemetry disabled until answered; same `telemetry.json`
  schema; `TIT_INTERFACE ∈ {electron, browser, api, notebook, cli}`, default `cli`).
- **Docker discovery** is CLI-only via `execa` (`docker context inspect --format
  '{{.Endpoints.docker.Host}}'`, `docker compose … up -d`, `docker inspect`, `docker compose logs`)
  — dockerode is dropped (its only Engine-API-only use was the GUI exec/hijack). Supported
  runtimes documented per OS (Docker Desktop, Linux Engine incl. rootless, OrbStack/Colima/Rancher
  Desktop with their socket paths; `ensurePathEnv`/`findDockerCommand` kept, `/opt/homebrew/bin`
  added) with the exact user-facing error per failure (daemon not running, socket permission,
  wrong context, image missing + offline).
- **Paths:** `src/shared/paths.ts` `hostToContainerPath`/`containerToHostPath` used *only* for
  `shell.openPath`; unit tests for `C:\`, `\\wsl.localhost\…`, macOS case-insensitive roots. Docs
  recommend keeping projects inside the WSL2 filesystem on Windows (9P bind mounts are slow for
  FEM I/O). Container paths embedded in existing artifacts (reports, `run_config.json`,
  `analysis.json`) are shown as project-relative with a prefix map.
- **Updates:** no `electron-updater` in 3.0 (science + UI ship in the image via `docker compose
  pull`; Windows installers are unsigned — §9.7). Launcher shows a "new release available" banner
  from the GitHub Releases API (offline-tolerant); `tit/tools/check_for_update.py` stays for CLI.
  Main-process crash log at `<user_config>/logs/`; renderer error boundary.
- **Help:** bundled offline docs (`release-build.yml` renders `docs/` into
  `desktop/resources/docs/`; the image copies it next to the UI bundle so `tit.server` serves
  `/docs`; links resolve local-first) + About (app/image versions, update check), Cite (DOI),
  Acknowledgments, Contact/Discussions. The 105 `setToolTip` strings and 8 `HelpIcon` popups in
  the tabs are harvested by script into each screen's parity checklist before a Qt file is deleted.
- **Accessibility/shortcuts minimum:** Radix primitives, focus order, `Esc` closes dialogs,
  `Cmd/Ctrl+1-9` screens, `Cmd/Ctrl+J` Jobs panel.

### 3. Backend change budget (the whole list — everything else in `tit/` is untouched)

**A. Additive modules (new files only)**
- `tit/server/` — FastAPI app: `app.py`, `routes/{jobs,catalog,files,settings,system,validate,
  capabilities}.py`, `ws.py`, `auth.py`, `static.py` (`--static-dir`, default
  `/opt/ti-toolbox/ui`), `__main__.py` (`--project`, `--host`, `--port`, `--supervise`,
  `--reload`, `--dump-openapi`).
- `tit/jobs/` — `spec.py`, `registry.py` (on-disk), `scheduler.py`, `plans.py`
  (`plan_preprocessing`), `runner.py` (interface + `LocalPopenRunner`), `locks.py`
  (`hold`, `keys_for`, `holders`), `costs.py` (data), `events.py`, `client.py` (small; `submit`,
  `watch`, `run_from_json(spec.json)` for notebooks).
- `tit/catalog.py` — every discovery routine the UI needs, returning JSON-able dicts (subjects with
  raw/freesurfer/m2m flags; simulations + `documentation/config.json`; analyses per simulation;
  flex runs + manifest labels; ex/mex runs + `final_output.csv`; leadfields; ROIs; custom masks;
  atlases/regions via nibabel + `FreeSurferColorLUT` (no `mri_segstats`); EEG nets + electrode
  names; reports; view specs; freehand configs; notes; subject-info scan). Run dirs without a
  manifest/`run_config.json` are ignored.
- `tit/sim/montage_sources.py` — flex-run→`Montage` (with `tit.tools.map_electrodes`), freehand
  `stim_configs`→`Montage`, `delete_montage`, existing-output skip/replace policy.
- `tit/opt/roi_spec.py` — `get_roi_spec()` + LUT/label resolution extracted from `roi_picker.py`.
- `tit/opt/flex/drivers.py` — `run_adaptive_focality()`, `run_pareto_sweep()` composing the
  existing `tit/opt/flex/pareto.py` (grid/plot/manifest already there); scriptable for the first
  time; fixes the two audit bugs (Stop does not terminate adaptive/pareto subprocesses; multi-subject
  Pareto runs only the first subject).
- `tit/opt/leadfield_runner.py` + `LeadfieldConfig` (`tit/opt/leadfield.py` is a module, so no
  `leadfield/__main__.py` without a package conversion; generation is already scriptable via
  `LeadfieldGenerator` — only the JSON runner is new).
- `tit/stats/nifti_average.py` (+ runner mode), `tit/plotting/nilearn/__main__.py`,
  `tit/pre/qsi/catalog.py` (recon-spec/atlas metadata + resource defaults from
  `qsi_config_dialogs.py`), `tit/electrodes/placement.py` (skin surface via
  `tit/blender/electrode_placement.py`, `stim_configs` reader/writer), `tit/notes.py`.
- `tit/config_io.py`: `deserialize_config`, `json_schema()`; new dataclasses `AnalyzerConfig`,
  `PreprocessConfig`, `SourceConfig`, `LeadfieldConfig`; `PathManager.jobs_dir()`.
- `contracts/` (`openapi.v0.yaml`, `events.schema.json`, generated `openapi.json`,
  `schema.json`) + `tests/fixtures/api/`.

**B. Small behavioural changes inside existing code (each a few lines, each tested)**
- `tit/logger.py::setup_logging()` attaches `JsonEventHandler(TIT_EVENTS_FILE)` to the `tit` and
  `simnibs` loggers when the env var is set (so `log` events need no runner edits); `emit_progress
  /emit_stage/emit_artifact` helpers; `stage`/`progress` calls added in **all nine** runners (sim,
  pre, flex, ex, mex, analyzer, stats, source, blender) at existing loop boundaries; `add_file_handler`
  de-duplicates handlers (leak in long-lived processes).
- Runners: use `deserialize_config`; `with locks.hold(...)`; `finally: emit exit`. Exit codes:
  `tit.analyzer.__main__` gains `sys.exit(0/1)` (has none); `tit.stats.__main__` replaces the
  tautology `n_significant_clusters >= 0` with `result.success` (`stats/__main__.py:64,85`);
  `tit.pre.__main__` catches `PreprocessError` → clean message + exit 2 (today: traceback, exit 1);
  sim already exits 1 on any failed montage (`sim/__main__.py:49-51`) — keep.
- `tit.sim`: simulation report generated by the runner (moves `simulator_tab.py:1644-1800` into
  `tit.reporting`/`tit.sim`); scoped partial-output cleanup; `tissue_conductivities` field (env
  honoured one release with a warning); `start_t1_to_mni` skip-if-exists + atomic write.
- `tit/pre/structural.py::run_pipeline`: takes `runner=` (constructed by `__main__`), installs the
  SIGTERM handler → `CommandRunner.terminate_all()`; the two GUI-only validations ("parallel
  requires recon-all", "tissue requires m2m unless create_m2m") move here; `write_project_metadata`
  / `report` flags so per-stage jobs do not rewrite `dataset_description.json`/`.bidsignore` and
  emit N reports (`ensure_subject_dirs` still runs); `PreprocessingReportGenerator.from_job_results()`
  so the group's `report` job builds one consolidated report from the stage jobs' durations/status.
  `tit/pre/utils.py:461` → `start_new_session=True`. `recon_all.py` passes `-openmp N` from the
  job's cpu budget (2 lines). The per-step modules (`charm.py`, `recon_all.py` otherwise,
  `dicom2nifti.py`, `tissue_analyzer.py` — plus `matplotlib.use('Agg')` there, `qsi/*`) are
  untouched except: `docker_builder.py` adds `--label tit.job_id=$TIT_JOB_ID` to both `docker run`
  commands and (preferred) a per-subject work dir.
- `tit.opt.ex`: batch mode as `ExConfig.targets: list[TargetSpec] | None` (each with
  `roi_name/roi_names/roi_atlas/run_name`) — **not** by overloading `roi_names`, whose meaning is
  *union into one target* (PR #130); sequential, one run dir per target (engine's naming — the GUI
  checks `<roi>_<net>` while the engine writes `ex-search/<eeg_net>/`: settle with a real run in
  Phase 2), one `stage` event per target; owns the pipeline-log sections; combined-ROI naming and
  atlas-only labels move here.
- `tit.opt.flex`: uuid suffix in `generate_run_dirname`; manifest written last.
  `tit/opt/leadfield.py`: HDF5 resolved by `<net>_leadfield.hdf5`.
- `tit.analyzer`: multi-sphere in one config. `tit/sim/utils.py`: `save_montage_data` atomic;
  `delete_montage` helper. `tit/reporting/generators/base_generator.py`: atomic
  `_create_dataset_description`.
- `tit/project_init/first_time_user.py`: drop the PyQt5 dialog (keep the two Qt-free functions);
  `tit.project_init` gets a `-m` entry (`initialize_project`, example data) used by
  `POST /api/project/init`.
- `tit/atlas/constants.py:26`, `tit/tools/montage_visualizer.py:26`,
  `tit/blender/montage_publication.py:365`: paths become `TIT_RESOURCES_DIR`-overridable
  (default `/ti-toolbox/resources`).
- `tit/telemetry.py`: `track_event(_blocking=True)` joins up to 6 s — the server calls it from a
  thread executor, never on the event loop; `gui_launch`/`gui_close` (names kept, dashboards
  unchanged) emitted on first authenticated UI connection / last disconnect with an `interface`
  param.

**C. Removals at cutover (Phase 6)**
- `tit/gui/` entirely (28k LOC), `tests/test_gui_imports.py`, `tit/gui/components/qt_log_handler.py`
  (no callers), the legacy launcher `package/` (replaced by `desktop/`), `package/docker/loader.sh`,
  `package/start-ti-toolbox.sh`, `package/tests/test-docker-integration.sh`; Qt5/GTK apt packages in
  `Dockerfile.simnibs:81-92` only if Freeview (bundles its own Qt) and Gmsh keep working — spike (g).
  **X11 stays** (mounts/env in compose, X11 client libs + Mesa `:55-79`, the XQuartz/VcXsrv logic —
  ported to TypeScript).

**Which copy of `tit` runs:** keep the `/ti-toolbox` checkout (pinned to the build commit) as the
**only** copy — drop `pip install .` (`Dockerfile.simnibs:190`) and set `ENV PYTHONPATH=/ti-toolbox`
in the Dockerfile (not `.bashrc`). Reason: the wheel contains only `tit*` (`pyproject.toml:18-21`);
`resources/` (atlases, ElectrodeCaps, amv) and `tit/blender/Electrode.blend` are not packaged, and
today everything works only because every launch path runs with `cwd=/ti-toolbox`. Phase-3
acceptance: a runner spawned by the server resolves `MNI_ATLAS_DIR` and `Electrode.blend`.
`PathManager` stays a process-wide singleton; the server sets it once from `--project` — which is
why one-project-per-server-instance is a stated non-goal.

**What explicitly does NOT change:** `tit/sim/base.py` solver calls, `tit/opt/*/engine.py` and
the optimizers, `tit/analyzer/analyzer.py`, `tit/stats/permutation.py`, the per-step modules under
`tit/pre/` named above, `tit/reporting/` generators (except the atomic write + `from_job_results`),
`tit/plotting/`, PathManager layout rules, the `montage_list.json` / ROI CSV / flex manifest
formats, the scripting API in `tit/__init__.py` and subpackage `__init__`s (a PEP 562 lazy
`__getattr__` in `tit/sim/__init__.py` and `tit/opt/__init__.py` is an *optional* Phase-0 decision
that keeps the documented import pattern working), the example notebook and `scripts/`.

### 4. Frontend stack & repo layout

- **Electron** (latest stable major at Phase-4 start, pinned; bump schedule in §2.8) +
  **electron-vite**, **TypeScript strict**, **React 18 + Vite**, **TanStack Query** for catalog/
  list state (invalidated only on job state transitions and `artifact` events — never per log
  line) + **Zustand** for UI state and the log ring buffer, **shadcn/ui** (Radix copy-in, Tailwind
  density tokens), **react-hook-form + ajv (draft 2020-12 build) via `@hookform/resolvers/ajv`**
  compiled once from `schema.json` — the PyQt GUI has ~260 input controls in 64 group boxes, so
  form state/validation is where the weeks go and must not drift from the schema; core screens
  1–6 are hand-laid-out RHF forms typed from `components["schemas"]["FlexConfig"]` etc., optional
  panels may use `@rjsf/core` + a shadcn theme to reach parity fast; **@tanstack/react-table**
  (subject/run/CSV tables); **@tanstack/react-virtual** (console); **NiiVue**
  (`@niivue/niivue`); **three.js**; **uPlot** (`useUPlot` hook, ~40 lines); **openapi-typescript +
  openapi-fetch**. Tests: **vitest**, **Playwright** (`_electron` against the built
  `out/main/index.js`, mock server via `TIT_MOCK_SERVER_URL`).
- **Layout:** the v3 app lives in a new `desktop/` directory; the legacy launcher `package/` stays
  untouched until Phase 6 (decision 2026-08-27: no `git mv`, so the 2.x launcher keeps working during
  the transition; `dev/update/update_version.py:68-89`, the 8 `working-directory` lines in
  `release-build.yml`, `docs/wiki/desktop-app.md` and `AGENTS.md` switch to `desktop/` in Phase 6). `desktop/{electron.vite.config.ts, src/main, src/preload,
  src/renderer, src/shared, tests, build, docker}`; electron-builder `files: ['out/**','build/**']`,
  `main: ./out/main/index.js`, `extraResources: docker/` (+ the tmpdir compose copy pattern from
  `main.js:24-60`), `mac.notarize: true` replacing the custom `afterSign` hook. The renderer bundle
  reaches the image through a **multi-stage Dockerfile** (`node:20` builder → `COPY --from=ui
  /src/out/renderer /opt/ti-toolbox/ui`; build context = repo root — today's Dockerfile `git
  clone`s and has no Node).
- **Dev loop:** `npm run dev` (electron-vite HMR) with Vite `server.proxy` for `/api` and `/ws`
  (renderer code stays origin-relative in dev/prod/browser); container side
  `simnibs_python -m tit.server --reload` (`WATCHFILES_FORCE_POLLING=1` documented for Docker
  Desktop); `docker-compose.dev.yml` sets `PYTHONPATH=/ti-toolbox` and
  `TIT_STATIC_DIR=/ti-toolbox/desktop/out/renderer`.
- **Screens** (one per PyQt tab, same names so docs map 1:1): Pre-processing, Optimizer (Flex /
  Ex / mEx), Simulator, Analyzer, Viewer, Results, Jobs (global), System, Settings (project,
  telemetry, feature panels replacing `extensions.json`, Jupyter, image tag pin), Help (offline
  docs, About, Cite, Contact). Optional panels: Source, Cluster Permutation, NIfTI Group Average,
  Nilearn Visuals, Quick Notes, Subject Info; 3D Visual Exporter and Electrode Placement default
  to 3.1 (§9.2).

### 5. Phases

Each phase = one or more PRs into `feature/v3-electron-gui`, each with tests, `black`, and the
gates in §6. The PyQt GUI keeps working on the branch until Phase 6 (feature-frozen: bug fixes
only; where a Phase-2 extraction is a mechanical import swap, the Qt tab is re-pointed to the
extracted function so the legacy GUI exercises the new code until cutover).

**Phase 0 — Decisions & spikes (≈1–2 wks)**
- Create `feature/v3-electron-gui` from `main`; record §9 answers as an ADR in
  `tracks/active/v3-electron-gui.md` (this section moves there when work starts).
- In-flight work: `alba/ex-search-extension` is 45 files, +4,822/−147 — its backend files
  (`tit/plotting/ti_metrics.py` +487, `tit/opt/flex/simulation_export.py` +211,
  `tit/tools/thalamus_rois.py` +353, `tit/pre/structural.py` +68, `tit/sim/utils.py`,
  `tit/pre/preflight.py`) must land on `main` **before** Phase 1 touches the same functions; its
  6 Qt files (+537/−104) are throwaway. Freeze `tracks/active/{gui-roi-cleanups,ex-search-streamlining}.md`
  / PR #146; abandon `feature/launcher-redesign`; `mp-leadfield-search.md` is backend-only.
  `deploy/jupyterhub/` (untracked WIP with a local `.env`) is committed or dropped before Phase 0
  ends; `.env` never.
- Spikes (½–1 day each, notes in `dev/notes/v3-spikes.md`): (a) `simnibs_python -m pip install
  fastapi "uvicorn[standard]"` inside `idossha/simnibs:v2.4.0`, serve REST + WS on `0.0.0.0`
  behind `127.0.0.1:<port>` publishing and **assert reachability with `curl` from the HOST** on
  macOS, Windows (Docker Desktop/WSL2) and Linux Engine; (b) time `import tit.sim; import tit.opt;
  import tit.analyzer` and record RSS in the container (the server will hold SimNIBS); (c) **done
  2026-08-27** (`dev/notes/v3-spikes.md`): NiiVue loads ernie T1 + tissue LUT + TI_max + electrode
  overlay and server-exported GIfTI surfaces; kept as the seed of the internal-viewer track;
  (d) electron-vite + `contextIsolation`/`sandbox` skeleton doing `loadURL` against (a) with a
  token→cookie exchange and a WS round-trip, plus the Vite proxy dev loop; (e) **threads**: time
  charm, one FEM solve, `recon-all -parallel` and one QSIPrep run with `OMP_NUM_THREADS` = 1/4/8
  exported (the image pins `OMP_NUM_THREADS=1`, `Dockerfile.simnibs:133`; FreeSurfer only defaults
  to 4 threads when it is unset) → seeds `tit/jobs/costs.py`; (f) directory-lock creation and
  `os.replace` on Docker Desktop bind mounts **incl. a Windows-hosted project**; (g) which apt
  packages in `Dockerfile.simnibs:55-93` are needed without Qt (gmsh `-nopopup` offscreen, bpy);
  (h) headless Electron + WebGL in CI (`use-angle=swiftshader` under `xvfb-run`).
- Acceptance: ADR merged; spike notes; go/no-go on §2.1 and §2.8 origin model.

**Phase 1 — Contract hardening (Python only, ≈2–3 wks)**
- `deserialize_config` + `json_schema()` post-processor + the four new dataclasses; the five
  hand-rolled runners switched (flex/ex/mex verified unchanged); round-trip test per config class
  (instance → `serialize_config` → validate against `json_schema()` with `jsonschema` 2020-12 →
  `deserialize_config` → equality); `contracts/schema.json` snapshot; `contracts/openapi.v0.yaml`,
  `contracts/events.schema.json`, `tests/fixtures/api/` (sub-ernie).
- `setup_logging` JSON sink; `stage`/`progress` in all nine runners; `exit` event; exit-code fixes
  (analyzer, stats, pre); SIGTERM handler via `run_pipeline(runner=)`; grace 10 s in ex/mex;
  `start_new_session` in `tit/pre/utils.py`; lock `hold()` scaffolding (no-op keys until Phase 3
  defines them).
- `tissue_conductivities`; env side channels → fields (deprecation warnings); `docker run --label`.
- Acceptance: host `pytest` green + container CI green; a runner started with `TIT_EVENTS_FILE`
  produces a valid `events.jsonl` on Dataset 000 (`sub-ernie`) in the test container;
  `scripts/*.py` + `tests/test_scripts.py` unchanged in behaviour.

**Phase 2 — Extraction of GUI-embedded logic into `tit/` (Python only, ≈5–6 wks)**
- `tit/catalog.py`, `tit/sim/montage_sources.py`, `tit/opt/roi_spec.py`,
  `tit/opt/flex/drivers.py`, `ExConfig.targets`, `tit/opt/leadfield_runner.py`,
  `tit/stats/nifti_average.py`, `tit/plotting/nilearn/__main__.py`, `tit/pre/qsi/catalog.py`,
  `tit/electrodes/placement.py`, `tit/notes.py`, simulation report in the backend, analyzer
  multi-sphere, `delete_montage`, Qt-free `first_time_user.py`, `TIT_RESOURCES_DIR`,
  `PreprocessingReportGenerator.from_job_results`, `start_t1_to_mni` skip, leadfield HDF5 naming,
  atomic writes, run-dir uuid suffixes. Settle the ex-search run-dir convention with a real run.
- Each extraction: unit tests (conftest mocks `simnibs/nibabel/nilearn`, numpy real); a
  `scripts/` example where it adds scripting capability (adaptive/pareto, group average, leadfield
  JSON runner); a `docs/wiki/scripting.md` snippet.
- Delete dead code instead of moving it (verified callers): `ex_search_tab.py:2958-3123` (keep
  `current_roi_completed` at 3124 — it is the live completion path), analyzer `browse_atlas`
  (1168-1212) + `toggle_region_input` (1499-1503) + the unread `analysis_kwargs` string
  (`_extract_output_dir_from_cmd` is *called* at 1840/1920 — leave it), `simulator_tab.py:2153-2216`
  **plus its caller at 1624**, `system_monitor_tab.get_processes_fallback`,
  `components/subject_row.py` **plus** its two exports in `components/__init__.py:35-36` and the
  two lines in `tests/test_gui_imports.py:104-105`.
- Acceptance: every routine in the audit's "backend logic living in GUI" lists has a home in
  `tit/` with a test, or a recorded "dropped" decision.

**Phase 3 — `tit.server` + `tit.jobs` + container (≈4–6 wks)**
- Registry/DAG scheduler/locks/costs/runner/events/tailer (§2.3–2.4), `plan_preprocessing`, REST
  + WS routes (`seq`/`since`), static UI + `/docs`, auth (env token → cookie), `TrustedHost`, WS
  origin check, file jail, CSP headers, `/api/capabilities`, `--dump-openapi` (must diff clean
  against `openapi.v0.yaml`). FastAPI `TestClient` + `pytest-asyncio` tests; `tests/fake_runner.py`
  (emits events, honours SIGTERM) for scheduler tests; lock table tested as data; path-traversal
  and CSP-header tests for file/report routes.
- `container/blueprint/Dockerfile.simnibs`: multi-stage (Node builder → `/opt/ti-toolbox/ui`),
  `fastapi uvicorn[standard]`, `ENV PYTHONPATH=/ti-toolbox`, no `pip install .`, pinned clone,
  HEALTHCHECK; compose: `init: true`, server as `command`, drop X11 mounts/`DISPLAY`, publish
  `127.0.0.1:${TIT_SERVER_PORT}`, Jupyter off by default, `name:` per project; `apptainer.def`
  gains fastapi/uvicorn. `loader.py` behaviour changes (§2.7). `.bidsignore` + `PathManager.jobs_dir`.
- `.circleci`: server integration job on `idossha/ti-toolbox-test` with Dataset 000 — submit a
  real short job (analyzer on the shipped `sub-ernie` simulation), assert the WS event stream +
  artifacts; parallel tests: `pre(tissue, A) ∥ analyzer(A)` admitted, `sim(A,m) ∥ sim(A,m)` blocked
  with `waiting_on` in the stream, 4 fake recon-all jobs on an 8-cpu budget run concurrently,
  cancel kills the whole tree, server restart re-attaches a running fake job.
- Acceptance: `curl` walkthrough documented; server survives runner crashes; restart re-attaches;
  a spawned runner resolves `MNI_ATLAS_DIR` and `Electrode.blend`.

**Phase 4 — Desktop foundation (TypeScript, ≈4 wks; starts after Phase 1 against the v0
contract + fixtures, not after Phase 3)**
- new `desktop/` (legacy `package/` untouched); electron-vite skeleton; security settings; preload bridge; Docker
  lifecycle via CLI (`execa`), per-project compose name, **attach-or-start**, project switch
  semantics, launcher screen with pull progress (reuse `renderer.js:133-249` parsing); project
  init sequencing: Electron only `mkdir`s the chosen empty dir → compose up with it mounted →
  `POST /api/project/init {example_data}` (deletes the JS scaffolding); first-run flow (welcome +
  consent); app shell + navigation; typed client from v0; **Jobs panel + per-job console + System
  screen** (live monitoring is proven here, before any feature screen); Settings (telemetry
  writes `telemetry.json` via `PUT /api/settings/telemetry`); notifications;
  close-with-running-jobs dialog. Mock server (`desktop/tests/mock-server/`) from the fixtures.
- Acceptance: the **packaged** app (not the dev server) completes a REST + WS round-trip against
  a real Phase-3 server on Linux CI: starts the stack, shows the Jobs panel, streams a real
  `analyzer` job with progress + logs, stops it, exits leaving containers running by choice;
  Playwright E2E green against the mock server on ubuntu/macos/windows; macOS/Windows real-stack
  checks are a written manual QA matrix (GitHub macOS runners have no Docker; Windows runners
  cannot run Linux images).

**Phase 5 — Feature screens to parity (≈12–18 wks; order = user value / risk)**
1. Pre-processing: subject table with flags; step toggles; QSIPrep/QSIRecon forms from
   `tit/pre/qsi/catalog.py`; preflight via `/api/plan/pre`; Run submits **one group** via
   `/api/jobs/groups` with a "subjects in parallel (N)" cap; consolidated per-subject report.
2. Simulator: montage CRUD, EEG nets, flex/freehand sources via `/api/plan/sim`, **free-hand table
   editor**, conductivity overrides, output fields, one job per (subject, montage), report artifact.
3. Optimizer — Flex (ROI picker on `/api/…/atlases/regions`, spherical picking in NiiVue,
   electrode/solver params, adaptive/pareto as single jobs), Ex/mEx (leadfield as a job, ROI CRUD,
   combine-ROI, `targets` batch), results table from `final_output.csv`.
4. Analyzer: single/group, mesh/voxel, multi-sphere, atlases, output-dir/overwrite via plan.
5. Viewer: NiiVue per §2.6 (T1/MNI, atlas + LUT, TI/mTI overlays, electrode overlay job, analysis
   overlays, group mode, additional NIfTI within the jail); RAS acceptance test on sub-ernie.
6. Results: reports (sandboxed iframe), flex/ex run pages with PNGs, analyses CSVs, **three.js
   `.msh` surface viewer**, "open with host Gmsh".
7. Optional panels: Source, Cluster Permutation (through the fixed `tit.stats` runner), NIfTI
   Group Average, Nilearn Visuals, Quick Notes, Subject Info. 3D Visual Exporter and Electrode
   Placement (three.js picker) are 3.1 unless §9.2 says otherwise.
- Each screen ships with: a parity checklist harvested from the PyQt tab (inputs, tooltips, help
  popups, dialogs), vitest that every form's defaults validate against `schema.json`, a Playwright
  flow, and a wiki page draft. A per-screen LOC/week table is kept in the track file so slips are
  visible.
- Acceptance: parity checklists 100% for screens 1–6; every optional panel either ported or listed
  as deferred in the 3.0 release notes.

**Phase 6 — Cutover, docs, release (≈2–3 wks)**
- Delete `tit/gui/`, `tests/test_gui_imports.py`, `package/` (legacy launcher), Qt apt packages (if
  spike (g) allows); X11 mounts/env stay for the viewers;
  bump to 3.0.0 (`update_version.py`: `desktop/package.json`, compose image tags, Dockerfile ARG;
  drop the `index.html`/`main.js` string patches; fix its stale `dev/bash_dev/…` target);
  `release-build.yml`: `npm ci && npm run typecheck && npm run lint && npm test && npm run build`,
  pinned tooling, notarization, offline docs render; `desktop-ci.yml` from Phase 4 stays.
- **Migration for existing projects:** `.initialized` ignored/deleted; `extensions.json` panels →
  Settings; `project_status.json.version` bump; `montage_list.json`/ROI CSV/flex manifests
  unchanged; `TISSUE_COND_<n>` honoured with a warning for one release; `code/ti-toolbox/jobs/`
  appears (and is `.bidsignore`d); users' `xhost`/XQuartz settings — CHANGELOG cleanup note.
- Docs: rewrite `wiki/gui.md`, `wiki/desktop-app.md` (new architecture SVG), `wiki/extension.md`
  (→ optional panels), `wiki/visualizers.md` (viewers launched from the app; X server still required for them),
  `wiki/scripting.md` (jobs API, events, locks from a notebook, new drivers; lines 40-53 Jupyter
  token), `wiki/example-notebook.md:19-23`, `installation/{windows,macos,linux,dependencies,
  bash-cli}.md` (X-server sections reworded: needed for Freeview/Gmsh only; loader.py semantics; WSL2 note),
  `installation/hpc-apptainer.md` (browser mode, capabilities), `wiki/troubleshooting.md`
  (X11 section → "Remote server" ssh-tunnel section), "User Interface" sections in simulator /
  flex-search / ex-search / cluster-permutation-testing / nilearn-visuals / mti /
  electrode-placement / analyzer (Gmsh) / reports pages, `gallery/UI.md` + 11 `UI_*.png`
  regenerated, `nav.yml`, CHANGELOG with the migration section.
- Agent-facing: `AGENTS.md` (architecture block, critical files, Python 3.11, v3),
  `agent-plugin/` skills + `agent-plugin/mcp/server.py::tool_get_quick_facts`,
  `.claude/skills/{codebase-guide,read-before-coding}`.
- Acceptance: v3.0.0 tag on `main` after the branch merges; `idossha/simnibs:v3.0.0` pushed (built
  by the multi-stage Dockerfile from the tagged commit); desktop artifacts for macOS
  (signed + notarized), Windows, Linux; container CI + desktop CI green; docs deployed.

### 6. Test & CI strategy (quality gates for every phase)

- Python: host `pytest` stays fast (< 30 s) — server/jobs tests use the fake runner; contract
  round-trip tests per config class; `schema.json` + `openapi.json` snapshots; path-traversal and
  CSP-header tests; lock-table-as-data test; **anything touching paths/filesystem is verified in
  the container** (macOS host hides case-sensitivity/EPERM bug classes).
- Container CI (CircleCI, real SimNIBS): existing suite + the Phase-3 server/parallel/cancel/
  re-attach jobs + a scripted "submit sim job → events → report artifact" on `sub-ernie`.
- **Desktop CI** (`.github/workflows/desktop-ci.yml`, new — none exists today): on PRs touching
  `desktop/**`, matrix ubuntu/macos/windows → `npm ci && typecheck && lint && vitest && build &&
  electron-builder --dir` (packaging smoke, unsigned) + Playwright `_electron` E2E against the
  mock server (`xvfb-run`, swiftshader); a second ubuntu-only job (nightly + `e2e` label) pulls
  `idossha/ti-toolbox-test`, starts the stack through the real Electron main, and asserts the WS
  stream. macOS/Windows real-stack = manual QA matrix.
- Gates: `black tit/ tests/`; no new `shell=True`; **no scientific code diff in Phases 1–5** (CI
  diff check on `tit/sim/base.py`, `tit/opt/*/engine.py`, `tit/opt/flex/flex.py`,
  `tit/analyzer/analyzer.py`, `tit/stats/permutation.py`, `tit/pre/{charm,dicom2nifti,
  tissue_analyzer}.py`, `tit/pre/recon_all.py` except the `-openmp` line); no `Co-Authored-By`
  trailers; schema regenerated in the same PR as any dataclass change; `openapi.json` diffs clean
  against v0.

### 7. Risks & mitigations

| risk | mitigation |
|---|---|
| Scope creep / never reaching parity (28k LOC Qt, ~260 inputs) | parity checklists harvested from the audit; optional panels deferrable; Phase 4 proves live monitoring before feature work; per-screen LOC/week table |
| FastAPI/uvicorn vs the SimNIBS-bundled Python 3.11 / numpy 1.26 | spike (a); fallback Starlette + `websockets` |
| Port publishing / origin quirks (Docker Desktop, WSL2, Linux Engine) | spike (a) asserts host-side `curl`; spike (d) proves the packaged-app round-trip; Phase-4 acceptance uses the packaged app |
| RAM per stage unknown; `OMP_NUM_THREADS=1` baked in; DooD siblings outside the cgroup | spike (e) seeds `costs.py`; budget counts sibling `--cpus/--memory`; OOM heuristic; VM-size warning |
| Hidden data races already in the field (memory: docker runs logging writes that never landed) | lock table + runner-held locks + atomic writes + per-job output scoping; artifact existence check in the `result` event |
| Server holds SimNIBS in memory; native crash in a catalog call | sync routes in threadpool; process pool for nibabel/mesh_io work; `--supervise` restart; runners are separate processes |
| UI ↔ image skew | UI served by the server (one bundle); schema-hash handshake; per-project image pin |
| Electron security regressions | `contextIsolation`/`sandbox`/CSP/TrustedHost/Origin checks from day one; preload reviewed with the `security-review` skill |
| Collaborator Qt work orphaned | Phase 0 decision list; backend parts land on `main` first |
| Docs/AI-context drift | Phase 6 checklist includes AGENTS.md + agent-plugin + MCP facts + screenshots |

### 8. Effort & sequencing

Sizes: frontend ≈ 15–22k LOC TS/TSX (screens 9–12k, NiiVue viewer 1.5–2k, three.js viewers
1.5–2k, jobs/system/main process 3–4k, tests ~3k); backend plumbing ≈ 2–3k (`tit/server`,
`tit/jobs`) + ≈ 3k extracted from Qt. Phases: 0 ≈ 1–2 wks · 1 ≈ 2–3 · 2 ≈ 5–6 · 3 ≈ 4–6 · 4 ≈ 4 ·
5 ≈ 12–18 · 6 ≈ 2–3. Backend track (1–3) ≈ 11–15 wks; frontend track (4–5) ≈ 16–22 wks and can
start once Phase 1's v0 contract exists. **One developer ≈ 8–10 months; two ≈ 5–6 months.** First
user-visible milestone = end of Phase 4 (Jobs panel driving real container jobs); first
daily-driver milestone = Phase 5 step 4.

### 9. Decisions (recorded 2026-08-27; ADR in `tracks/active/v3-electron-gui.md`)

1. **Origin model:** UI served by `tit.server`, Electron `loadURL` after `/api/health` (same origin,
   no CORS, one bundle).
2. **Optional panels in 3.0:** Source, Cluster Permutation, NIfTI Group Average, Nilearn Visuals,
   Quick Notes, Subject Info. 3D Visual Exporter and Electrode Placement → 3.1 (free-hand
   simulations keep working through the table editor).
3. **Viewers:** Freeview and Gmsh stay in the container, launched by `tit.server` from a ViewSpec
   (§2.6); X11 stays. No embedded renderer in 3.0. Internal viewer = later track.
4. **`.msh` viewer:** Gmsh (unchanged) in 3.0.
5. **`loader.py` fate:** shrink to a wrapper sharing Electron's env computation.
6. **UI stack:** React + Vite + TypeScript strict + shadcn/Tailwind + react-hook-form/ajv.
7. **Windows:** unsigned NSIS in 3.0; no `electron-updater`.
8. **Per-project stacks** (`ti-toolbox-<hash8>`): yes.
9. **Docker socket:** stays mounted by default in 3.0.
10. **PEP 562 lazy imports:** decide in Phase 1 from spike (b) numbers.
11. **QSIPrep work dir:** per-subject (`-w`).
12. **Repo layout (new):** new `desktop/` directory; `package/` untouched until Phase 6.

### 10. Definition of done for v3.0.0

- [ ] PyQt5 not imported by `tit`; the GUI process runs on the host without X11; X11 is used only
      by Freeview/Gmsh windows launched through `tit.server` (`xhost` scoped and reverted); docs
      describe the X server as required for the viewers only.
- [ ] One documented user entry point (desktop app, macOS/Windows/Linux); `python loader.py`
      works for developers/servers (`--serve`, `--jupyter`, `--detach`, `--down`, `--bind`) and
      never tears down running jobs without asking.
- [ ] Live monitoring: every job kind streams levelled logs + stage/marker progress or a liveness
      badge + CPU/RSS (DooD siblings via `docker stats`); Stop kills the whole tree incl. siblings;
      jobs survive UI restarts and server restarts; `waiting_on` reasons visible before and after
      submission.
- [ ] Parallel processing: pre-processing of A while simulating B from the UI; N-subject
      recon-all fan-out under a budget (not a flat cap); unsafe combinations queue with a reason;
      runner-held locks cover CLI runs; parallel/cancel/re-attach CI tests green.
- [ ] Scripting parity: every UI action maps to a documented `tit` call or JSON runner; example
      notebook + `scripts/` pass; adaptive/pareto, group average scriptable; `tit.jobs.client`
      can submit/re-run a job's `spec.json`; unsafe combinations documented for notebook users.
- [ ] Contract: `schema.json`/`openapi.json` generated + snapshot-tested with `_type`
      discriminators; TS types generated; validate/plan (incl. `lock_conflicts`) used by every
      screen; no hand-written path rules in TypeScript.
- [ ] Security: server + Jupyter reachable only via `127.0.0.1` publishing with tokens/cookies;
      TrustedHost + Origin checks; Electron isolation on; file routes jailed; reports sandboxed.
- [ ] Docs, AGENTS.md, agent-plugin, screenshots, CHANGELOG + migration notes updated; v3.0.0
      image + apps published.

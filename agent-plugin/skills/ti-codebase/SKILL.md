---
name: ti-codebase
description: TI-Toolbox codebase patterns, module graph, conventions and architecture (v3 — Electron desktop app, FastAPI tit.server, shared tit science core). Use when reading or modifying source under tit/ or desktop/ (developers).
user-invocable: false
---

# TI-Toolbox Codebase Guide (v3)

[AGENTS.md](../../../AGENTS.md) owns documentation routing. `docs/dev/` contains
ARCHITECTURE, DECISIONS, TESTING, RELEASING, BENCHMARKS, ROADMAP, CHANGELOG and AUTOMATION.
Read these through `read_dev_doc`; setup is in root CONTRIBUTING.md. Only CHANGELOG is published
from that directory. This skill is an orientation guide; current project documents take precedence.

## The three pieces

| Piece | Where | Owns |
|-------|-------|------|
| Electron desktop app | `desktop/` (main/preload + React + TS strict + Vite) | Host lifecycle only. It starts the container and `loadURL`s the UI from it. |
| FastAPI job server | `tit/server/` inside `idossha/ti-toolbox` | The job model — queue, dependencies, locks, budget, live events, cancellation. Serves the React bundle at `/`. |
| Science core | `tit/` | Every scientific decision. Imports no Qt, no FastAPI-only types. |

Wire contract: `contracts/openapi.yaml`. **The PyQt5 package `tit/gui/` was
deleted in v3.0.0** — do not cite it, do not restore patterns from it.

Frozen interface paths (a change requires the contract edit **and** the
`DECISIONS.md` entry in the same commit): `contracts/`,
`desktop/src/renderer/viewer/protocol.ts`, `desktop/src/shared/tit-bridge.d.ts`.

## Module dependency graph

```
tit/__init__.py       setup_logging, add_file_handler, add_stream_handler,
                      get_path_manager, paths, constants   (__version__ here)
  +-- tit.paths       PathManager singleton (depends on tit.constants)
  +-- tit.constants   pure constants, no internal deps (is_valid_pair_count here)
  +-- tit.logger      no internal deps
  +-- tit.errors      custom exceptions

science core
  tit.calc            the three envelope functions + the mTI direction search
  tit.fields          hf_peak / hf_sar exposure metrics (positional wiring)
  tit._mti_kernel     numba-accelerated sweep kernel

tit.sim
  +-- tit.sim.config           SimulationConfig, Montage, SimulationMode, MontageMode
  +-- tit.sim.base             BaseSimulation
  +-- tit.sim.TI / mTI         the two field pathways (note the capitalisation)
  +-- tit.sim.montage_sources  named / flex-mapped / free-hand montage resolution
  +-- tit.sim.utils            run_simulation, load_montages

tit.opt
  +-- tit.opt.config      FlexConfig, ExConfig, MExConfig, ROIs, electrode pools
  +-- tit.opt.flex.*      run_flex_search (differential evolution)
  +-- tit.opt.ex.*        run_ex_search   (exhaustive over a leadfield)
  +-- tit.opt.mex.*       run_m_ex_search (multipolar)
  +-- tit.opt.leadfield*  leadfield build + the leadfield_runner job module

tit.analyzer   Analyzer, AnalysisResult, GroupResult, run_group_analysis,
               select_field_file;  tit.atlas re-exported
tit.stats      run_group_comparison, run_correlation, engine (permutation), nifti,
               surface, nifti_average
tit.pre        run_pipeline, DICOM->NIfTI, FastSurfer, CHARM, QSIPrep/QSIRecon
tit.source     forward model + project_fields_to_fsaverage
tit.reporting  assembler / generators / reportlets (HTML reports)
tit.plotting, tit.blender, tit.tools, tit.project_init, tit.telemetry

tit.config_io  (de)serialisation with `_type` discriminators; used by tit.server
               job submission and every module's __main__ runner

v3 application layer
  tit.server     FastAPI app; routes/ auto-discovered; kernels.py, notebooks.py,
                 static.py, ws.py, auth.py, settings.py
  tit.jobs       the job engine (see below)
  tit.scene      scene payloads from a subject's real files + the packaged guide
  tit.viewspec   build_view(kind, ...) -> ViewSpec (a pure function)
  tit.catalog    subject/simulation discovery for the UI
  tit.launch     `tit launch` — the run spec reader
  tit.cli        the `tit` CLI (one subcommand: launch)
```

## The job engine (`tit/jobs/`)

`kinds.py` maps a kind to a module; every job is
`simnibs_python -m <module> <spec_path>`.

Kinds: `pre sim flex flex_adaptive flex_pareto ex mex leadfield analyzer stats
source blender nifti_average nilearn tools project_init report`.
States: `queued running succeeded failed cancelled skipped lost`.

- **`scheduler.py` is pure.** `evaluate()` takes a snapshot (the candidate job, all
  known jobs, held locks, running cost totals) and returns one `Decision`. It
  touches no filesystem and no clock. `JobManager` calls it once per queued job per
  tick and acts. A dependency naming an unknown id is a **skip**, never a wait.
- **`registry.py` is the on-disk store**:
  `<project>/code/ti-toolbox/jobs/<id>/{spec.json,status.json,events.jsonl,stdout.log}`,
  written atomically (temp file + `os.replace`). Retention 200 jobs / 30 days.
  Python-only fields (`locks`, `cost`, `pid`, `create_time`, `budget_wait`,
  `group_cap`) are stripped by `to_api()` before a response leaves the server.
- **Batch cap.** `POST /api/jobs/groups` requires `parallel_subjects` (≥ 1); it is
  mirrored onto every job as `JobSpec.group_cap` and enforced as an admission cap.
  **It counts jobs, not distinct subjects.** There is no group registry — the count
  is read off live statuses, so it survives a server restart. The server forces
  each generated config's `subject_id` to its own subject: subject isolation is a
  server guarantee, not a client convention. A `Promise.all` or an awaited POST
  loop is *not* an implementation of parallel or sequential execution.
- **`eta.py`**: `minutes = (fixed + per_unit * units) * mesh_scale * system.factor
  / parallel`. `mesh_scale` uses the `.msh` *file size* as a cheap proxy for
  element count (a `stat()`, not a parse). `EMULATION_FACTOR = 3.0` (amd64 under
  Rosetta). Every number is an estimate and the UI must label it as one.
- **Failure taxonomy** — nine `error.type` values, labelled in
  `desktop/src/renderer/app/jobs-rail/format.ts`: `preflight`, `lock_wait`,
  `budget_wait`, `runner_failed`, `oom_suspected`, `cancelled`, `skipped`,
  **`lost` → "Lost (server restarted mid-run)"**, `docker_unavailable`,
  `kind_error`. `lost` is also what `POST /api/jobs/{id}/force` produces.
- Known open gap (`RELEASE.md` §B): job re-adoption does not survive a server
  restart — the manager holds the child pid in memory only.

## Other v3 subsystems worth knowing before you touch them

- **`tit/server/kernels.py`** — Jupyter kernels driven **in-process** with
  `jupyter_client`, inside the container; the pipe is `WS /ws/kernels/{id}`.
  `MAX_KERNELS = 2`, 30-minute idle timeout, both reported by `GET /api/kernels`
  so no client hard-codes them. A restart must stop and join the pump threads
  before touching a ZMQ socket (libzmq aborts the process, and the process is
  `tit.server`). A keystroke never starts a kernel. **There is no sandbox** — a
  kernel runs arbitrary user code as the container's user; nothing in the product
  may call it one.
- **`tit/server/notebooks.py`** — the `.ipynb` on disk *is* the document; a save is
  validated before it lands and unknown keys survive untouched, so open+save must
  produce an empty git diff.
- **`tit/scene/`** — builds skin (`crop_mesh(tags=[1005])`), grey matter
  (`tags=[1002]`), electrodes (`eeg_positions/<net>.csv`) and region labels
  (`segmentation/*.annot` + `surfaces/*.central.gii`) from the subject's real
  files, plus a packaged subject-free guide served with an ETag of the file's
  SHA-256. A guide coordinate is never written into a configuration.
- **Native TetraVox** — desktop main installs a pinned official release for the host user;
  server scene exports map project paths for its native application. The image has no viewer bundle.

- **`tit/viewspec.py`** — `build_view` is a pure function returning a JSON-able
  `ViewSpec`. The server resolves what to show; the client renders it. **The viewer
  never assembles paths.**
- **`tit/catalog.py`** — built only on `PathManager` plus per-domain helpers, so
  BIDS layout rules are never re-implemented outside `tit`. A run directory without
  its completion manifest (`flex_meta.json`, `run_config.json`, `analysis.json` +
  `results.csv`) is ignored, so a cancelled run never appears as a result.

## Config → JSON → subprocess pattern

1. Build the config dataclass (`SimulationConfig`, `FlexConfig`, `ExConfig`, …).
2. Serialize via `tit.config_io`: `serialize_config` (Enums via `.value`, nested
   dataclasses recursively, union types via a `_type` discriminator);
   `write_config_json(config, prefix="flex")` returns a path.
3. Launch `simnibs_python -m tit.<module> config.json`.

`_type` discriminators: ROIs (`SphericalROI`, `AtlasROI`, `SubcorticalROI`),
electrodes (`PoolElectrodes`, `BucketElectrodes`), montages.

## PathManager singleton

```python
from tit.paths import get_path_manager
pm = get_path_manager("/path/to/project")   # sets project_dir on first call
pm = get_path_manager()                     # returns the existing instance
```
Auto-detection falls back to `PROJECT_DIR`, then `PROJECT_DIR_NAME` + the Docker
mount prefix. Zero-arg: `derivatives() simnibs() config_dir() reports()
jobs_dir()`. One-arg: `m2m(sid) simulations(sid) logs(sid)`. Two-arg:
`simulation(sid, sim) ti_mesh(sid, sim)`. Listing: `list_subjects()` (m2m only)
vs `list_all_subjects()` (all locations). `pm.ensure(path)` creates and returns.
**All paths go through the PathManager — never hand-built.**
Tests: `reset_path_manager()`; the `_reset_path_manager` fixture is `autouse`.

## Testing strategy

- **Host suite** — `python3 -m pytest tests/ -q` from the repo root. `conftest.py`
  installs mocks into `sys.modules` before any `tit` import: `simnibs` (+
  `simulation.sim_struct`, `mesh_tools.mesh_io`, `utils.transformations`), `bpy`,
  `scipy`, `nibabel`, `h5py`, `matplotlib`, `pandas`, `joblib`, `nilearn`.
  **numpy is real** — `tit/calc.py` tests do actual vector math.
- **Numerical suite** — `tests/numerical/`, run **in the container against the real
  libraries**: `docker exec -w /ti-toolbox <c> simnibs_python -m pytest
  tests/numerical -q`. This is where a scientific claim is proved.
- **Frontend** — `cd desktop && npm run typecheck && npm run lint && npx vitest run`.
- **E2E** — Playwright, offscreen by default (`TIT_E2E_OFFSCREEN=1`), **one run at
  a time** under `/tmp/tit-e2e.lock`. Some scene specs need `VITE_SCENE_HOOKS=1`
  and/or `VITE_INCLUDE_GALLERY=1` at build time.
- **Guards** — `python3 dev/route_import_guard.py && python3 dev/contracts_check.py`.
- **Real-container smoke** — `dev/smoke.sh --list | dev/smoke.sh | dev/smoke.sh <row>`.
- pytest markers: `unit integration slow requires_simnibs requires_freesurfer
  requires_data`.

## The gate

Run all of it and **report the numbers, not "green"**:

```bash
cd desktop && npm run typecheck && npm run lint && npx vitest run
python3 -m pytest tests/ -q
docker exec -w /ti-toolbox <container> simnibs_python -m pytest tests/numerical -q
python3 dev/route_import_guard.py && python3 dev/contracts_check.py
cd desktop && TIT_E2E_OFFSCREEN=1 npm run e2e:quiet
actionlint                 # if you touched .github/workflows
npm run verify:package     # if you touched packaging
cd desktop && npm run build   # LAST, always
```

After changing `tit/server/**`, `tit/jobs/**` or `tit/catalog.py`, restart only
once `GET /api/jobs` shows nothing running or queued. **A 200 from `/api/health` is
not evidence the new code loaded** — the pre-reload process can still answer.

## The science-integrity rule

Any change to `tit/stats`, `tit/analyzer`, `tit/calc`, `tit/fields` or `tit/sim`
needs **both**:

1. a test in `tests/numerical/` running against the **real** libraries that asserts
   the claim **independently** — an independent reader or a closed form, never a
   retyping of the implementation; and
2. if any published result moves, an entry in the applicable `docs/releases/` page
   saying what was wrong, which versions, which outputs move and by how much, how a
   user spots an affected result, and whether to **re-run or rescale**.

A number that changes and is not written down there is indistinguishable, to a
user, from a result they can no longer trust.

## Conventions

- `black tit/` before committing. Custom exceptions from `tit/errors.py`.
  `logging.getLogger(__name__)` per module; `setup_logging()` only at entry points.
- Commit titles state the defect or the new truth, e.g.
  `fix(analyzer): voxel focality volumes in cm^3, geometry from the affine`.
  **No AI co-author trailers.**
- `setup_logging()` adds **no handlers** — file-only by design.
  `add_file_handler(log_file, ...)` attaches one and returns it;
  `add_stream_handler()` writes bare `%(message)s` to stdout so the job runner can
  capture a subprocess. Each job writes a log file; the desktop app streams it over
  the server's HTTP API. There is no in-process UI logging handler in `tit/`.
- Shared-worktree rules: stage only your own files; **never `git stash`**; never
  revert another lane's working-tree changes; one Playwright run at a time; plain
  `npm run build` last; never recreate the maintainer's dev container (a plain
  `docker restart` keeps the token; a recreate mints a new one and kills jobs).
- Version lockstep: `dev/update/update_version.py --version X.Y.Z [--dry-run]` owns
  every version site — `tit/__init__.py`, `version.py`, `desktop/package.json`, the
  compose image tag, `CITATION.cff`, the release pages. CI re-checks the
  load-bearing ones and hard-fails on disagreement.

## How to add a new component

**A report generator**: `tit/reporting/generators/my_report.py` inheriting
`BaseReportGenerator`; implement `_get_default_title`, `_get_report_prefix`,
`_build_report`; reuse the reportlets in `tit/reporting/reportlets/`.

**A new UI page or panel**: the interface lives in `desktop/`, not `tit/`. Add the
Python side as a config dataclass plus a `__main__.py` runner plus a job kind in
`tit/jobs/kinds.py`, then the page under `desktop/src/renderer/pages/`. An
eleventh rail row would have no ⌘-number — check `DESIGN.md` §9 first.

**A new server route**: drop a module in `tit/server/routes/`; it is
auto-discovered (`iter_route_modules()`), so no `app.py` edit. Expose `router`
(behind auth) and/or `ws_router`. Routers carry **no prefix** — declare full paths
per endpoint. Only `health` is unauthenticated.

## Gotchas

- The container is Python 3.11 and **case-sensitive**: verify path and filesystem
  behaviour there, never on macOS. Note `tit/sim/TI.py` and `tit/sim/mTI.py`.
- nibabel's gzip save fails on bind mounts — write a plain `.nii` and gzip it with
  the standard library.
- **Never run two FEM simulations in parallel** under emulation; the smoke harness
  enforces it.
- `cpus` does **not** accelerate flex-search: `workers=` is never passed to
  `differential_evolution` and could not be — `goal_fun` holds an unpicklable
  pre-factored `OnlineFEM`. The realistic win is parallelising the multi-start
  restarts.
- `--project=real`, not `--project real`.

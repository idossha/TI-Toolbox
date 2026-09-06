# v3 build plan — all screens, parallel build

**Written:** 2026-08-27 · **Branch:** `feature/v3-electron-gui` (worktree `.claude/worktrees/v3-electron-gui`)
**Inputs:** `TODO.md` §v3.0.0 (architecture, phases), `tracks/active/v3-electron-gui.md` (ADR),
`desktop/DESIGN.md` (visual/interaction contract), `contracts/openapi.v0.yaml` (skeleton contract),
the Phase-0 walking skeleton (`tit/server`, `tit/catalog.py`, `desktop/`).

Goal of this plan: build **every screen of the v3 GUI** with the backend it needs, in parallel,
without agents stepping on each other, and with a real end-to-end run on Dataset 000 at the end.

## 0. How parallelism is made safe

- **Contract first.** `contracts/openapi.v1.yaml` (hand-authored) + `contracts/schema.json`
  (generated from the Python config dataclasses) are written in Stage 0 and are the only shared
  truth. The mock server implements the contract from fixtures; every page is built against the
  mock; the backend implements the same contract; Stage 3 swaps the mock for the real server.
- **File ownership.** Every agent owns a directory (below). Shared files are never edited by two
  agents: routers and pages are *auto-discovered*, dependencies are installed once in Stage 0, and
  the contract is frozen at the Stage-0 gate (later additions go through the orchestrator).
- **No dependency installs by page agents.** `desktop/package.json` is owned by the design-system
  agent; page agents report missing libraries instead of installing them.
- **No commits by agents.** The orchestrator commits at gates.

## 1. Stages and agents

### Stage 0 — Foundations

| id | agent (model) | owns | deliverable |
|---|---|---|---|
| F1a | contract author (sonnet) | `contracts/openapi.v1.yaml`, `contracts/events.schema.json` | the full v1 contract (§3 below), valid OpenAPI 3.1, `$ref`s to config schemas by name |
| F1b | config schema (sonnet) | `tit/config_io.py`, new dataclasses in `tit/analyzer/config.py`, `tit/pre/config.py`, `tit/source/config.py` (`SourceConfig`), `tit/opt/leadfield_config.py`; `contracts/schema.json`; `dev/build_contract.py`; `tests/test_config_schema.py` | `json_schema(cls)` with `_type` discriminators + `deserialize_config(cls, dict)`; round-trip tests for every config class; `dev/build_contract.py` merges `schema.json` `$defs` into the yaml → `contracts/openapi.v1.json` |
| F2 | design system + shell (sonnet) | `desktop/src/renderer/ui/**`, `desktop/src/renderer/app/**` (shell, router, jobs rail, theme, page registry), `desktop/src/renderer/forms/**` (RHF + ajv infra), `desktop/package.json`, `desktop/src/renderer/dev/Gallery.tsx` | everything in `DESIGN.md` §3–§7 as code; page registry via `import.meta.glob('../pages/*/index.tsx')`; all deps installed; gallery route showing every primitive in every state |
| F3 | mock server v1 (sonnet) | `desktop/tests/mock-server/**`, `desktop/tests/fixtures/**` | implements `openapi.v1.json` completely from fixtures, incl. a fake job engine (queued → running with synthetic stage/progress/log events → succeeded/failed/cancelled), validate/plan responses, viewers, files, settings |

Gate 0: `dev/build_contract.py` produces `openapi.v1.json`; `npm run gen:api` types compile;
`pytest` green; F2 gallery renders in light + dark (screenshots); mock passes its own contract test.

### Stage 1 — Backend services (parallel; each owns its modules)

| id | owns | deliverable |
|---|---|---|
| B1 jobs | `tit/jobs/**` (except `events.py`), `tit/server/routes/jobs.py`, `tit/server/routes/ws_jobs.py` (exposes `ws_router`), `tests/test_jobs*.py`, `tests/fake_runner.py` | JobSpec/registry on disk (`code/ti-toolbox/jobs/<id>/…`), scheduler (DAG `after`, lock keys, cost budget), `LocalPopenRunner` (`start_new_session`, stdout to file, env), `events.jsonl` tailer with `seq`/`since`, cancel = tree snapshot → SIGTERM → SIGKILL, re-attach on boot, `POST /api/jobs`, `/groups`, list/get/events/log/cancel/rerun, `WS /ws/jobs` |
| B4 runners | `tit/logger.py`, `tit/jobs/events.py` (sink + `emit_*` helpers only), the nine `__main__.py` runners, `tests/test_runner_events.py` | JSON event sink when `TIT_EVENTS_FILE` is set; `stage/progress/artifact/result/exit` events at existing loop boundaries; `deserialize_config` adoption; exit-code fixes; SIGTERM handler in `tit.pre`; `with locks.hold(keys_for(config))` scaffold |
| B2 catalog+viewers | `tit/catalog.py` (extend), `tit/viewspec.py`, `tit/server/routes/{catalog_v1,viewers,files,schema}.py`, `tit/server/routes/settings.py`, `tests/test_catalog_v1.py`, `tests/test_viewspec.py` | montages CRUD, EEG nets, atlases/regions, ROIs CRUD, leadfields, flex/ex/mex runs, analyses, reports, freehand configs; ViewSpec builder + `to_freeview_args`; `POST /api/viewers/{freeview,gmsh}` as `viewer` jobs (through B1's client API — a documented function `tit.jobs.client.submit(spec)`); jailed file routes; report iframe route with CSP; settings GET/PUT; `GET /api/schema` |
| B3 validate/plan | `tit/server/routes/{validate,plan}.py`, `tit/jobs/plans.py`, `tit/sim/montage_sources.py`, `tit/opt/roi_spec.py`, `tests/test_plan*.py` | `POST /api/validate/{kind}` (dataclass `__post_init__` errors → field paths), `POST /api/plan/{kind}` (resolved outputs, existing-output conflicts, resolved montages for flex/freehand sources, ex search-space counts, cost, `lock_conflicts`), `plan_preprocessing` DAG |

Interfaces between backend agents are fixed by the contract and by two documented stub modules
that already exist: `tit/jobs/api.py` (`submit(spec)`, `lock_conflicts(keys)`, `get_status(id)` —
B1 implements; B2/B3 call) and `tit/jobs/events.py` (`emit_stage/progress/artifact/result/exit` —
B4 implements; B1 only reads the resulting `events.jsonl`). Route modules are auto-discovered from
`tit/server/routes/` (`router` = protected, `ws_router` = self-authorising) — never edit `app.py`.

### Stage 2 — Screens (parallel with Stage 1; built against the mock)

| id | owns `desktop/src/renderer/pages/<name>/**` + `desktop/tests/e2e/<name>.spec.ts` | parity source (PyQt) |
|---|---|---|
| P1 preprocess | `preprocess/` | `tit/gui/pre_process_tab.py` + `qsi_config_dialogs.py` |
| P2 simulator | `simulator/` (montage CRUD dialog, flex/freehand sources, free-hand table editor, conductivity dialog, output fields) | `tit/gui/simulator_tab.py`, `components/conductivity_dialog.py` |
| P3 optimizer-flex | `optimizer-flex/` (ROI picker component shared → lives in `pages/_shared/roi/` owned by P3) | `flex_search_tab.py`, `components/roi_picker.py` |
| P4 optimizer-ex | `optimizer-ex/` (Ex + mEx tabs, leadfield job, ROI CRUD, targets batch) | `ex_search_tab.py` |
| P5 analyzer | `analyzer/` | `analyzer_tab.py` |
| P6 viewer | `viewer/` (Freeview launcher form = today's NIfTI Viewer layers/thresholds; Gmsh launcher) + `results/` (reports iframe, run pages, analyses tables, artifacts) | `nifti_viewer_tab.py`, results parts of analyzer/flex/ex tabs |
| P7 jobs+system | `jobs/` (full jobs table, per-job console, groups tree), `system/` (polish: charts, processes, terminate), rail behaviours in `app/jobs-rail/` (F2 leaves a stub) | `system_monitor_tab.py`, TODO §2.5 |
| P8 settings+help+panels | `settings/` (project, telemetry, appearance, feature panels, image tag, unsafe overrides), `help/` (offline docs iframe, About, Cite, Acknowledgments, Contact), `panels/{source,cluster-permutation,nifti-group-average,nilearn-visuals,quick-notes,subject-info}/` | `settings_menu.py`, `help_tab.py`, `extensions/*.py` |
| P9 main process | `desktop/src/main/**`, `desktop/src/preload/**` | Docker lifecycle via CLI (`compose up -d` per project, attach-or-start, project picker, image pull progress), X11 setup port from `package/src/backend/env.js` (`xhost` scoped + reverted), notifications, close-with-running-jobs dialog, host↔container path mapping, `openPath`/`showItemInFolder` |

Each page agent: (1) harvests a parity checklist from its PyQt source (every input, tooltip, help
popup, dialog, validation) into `pages/<name>/PARITY.md`; (2) builds the screen with the design
system only; (3) vitest: form defaults validate against `schema.json`; (4) Playwright E2E against
the mock incl. light+dark screenshots at 1280; (5) reports contract gaps instead of hacking.

Gate 2: all E2E green against the mock; screenshots reviewed by the design-QA agent.

### Stage 3 — Integration and review

1. Real stack: restart `tit-v3-spike` with the new server; `TIT_E2E_SERVER_URL` E2E per page;
   submit a real analyzer job on `sub-ernie` and a real 2-pair simulation; watch events in the rail.
2. Review agents: security (Electron + server), design QA (every screenshot vs `DESIGN.md`),
   rules R1–R6, test honesty. Fix pass. Orchestrator commits at each gate.

## 2. Ownership map (who may edit what)

| path | owner |
|---|---|
| `contracts/openapi.v1.yaml`, `events.schema.json` | F1a (frozen after Gate 0; changes via orchestrator) |
| `tit/config_io.py`, new `*Config` dataclasses, `contracts/schema.json`, `dev/build_contract.py` | F1b |
| `desktop/package.json`, `desktop/src/renderer/{ui,app,forms,dev}/**`, `desktop/src/renderer/index.css` | F2 |
| `desktop/tests/mock-server/**`, `desktop/tests/fixtures/**` | F3 |
| `tit/jobs/**` except `events.py`; `tit/server/routes/jobs.py`; `tit/server/routes/ws_jobs.py` | B1 |
| `tit/jobs/events.py`, `tit/logger.py`, `tit/*/__main__.py`, `tit/opt/*/__main__.py` | B4 |
| `tit/catalog.py`, `tit/viewspec.py`, `tit/server/routes/{catalog_v1,viewers,files,schema,settings}.py` | B2 |
| `tit/server/routes/{validate,plan}.py`, `tit/jobs/plans.py`, `tit/sim/montage_sources.py`, `tit/opt/roi_spec.py` | B3 |
| `desktop/src/renderer/pages/<name>/**`, `desktop/tests/e2e/<name>.spec.ts` | P<n> |
| `desktop/src/main/**`, `desktop/src/preload/**`, `desktop/src/shared/**` | P9 |
| `tit/server/app.py`, `tit/server/routes/__init__.py` (auto-discovery) | orchestrator only |

## 3. Contract v1 (endpoint inventory — F1a authors the yaml exactly from this)

Auth as v0 (cookie session or Bearer; `/api/health`, `/auth/*` open). All paths origin-relative.
Config bodies are `dict[str, Any]` validated server-side with `deserialize_config`; their schemas
are the `schema.json` `$defs` (`SimulationConfig`, `Montage`, `FlexConfig`, `ExConfig`,
`MExConfig`, `AnalyzerConfig`, `PreprocessConfig`, `QSIPrepConfig`, `QSIReconConfig`,
`GroupComparisonConfig`, `CorrelationConfig`, `SourceConfig`, `LeadfieldConfig`, blender
`MontageConfig`/`VectorConfig`/`RegionConfig`) merged in by `dev/build_contract.py`.

**Catalog (GET unless noted)**
- `/api/catalog/subjects` (v0) · `/api/catalog/subjects/{id}` → detail: flags, `m2m_path`, `eeg_nets: [name]`, `has_leadfields: [net]`, `n_simulations`, `has_dwi`, `has_ct`
- `/api/catalog/simulations?subject=` (v0 + per item: `montages: [name]`, `fields: [name]`, `space: [subject|mni]`, `report_ids`, `niftis: [{path, field, space, tissue}]`, `meshes: [{path, kind}]`)
- `/api/catalog/montages` → `{nets: {<net>: {uni_polar: {<name>: [[e1,e2],[e3,e4]]}, multi_polar: {...}}}}` · `PUT /api/catalog/montages/{net}/{kind}/{name}` body `{pairs}` · `DELETE …`
- `/api/catalog/eeg-nets?subject=` → `[{name, electrodes: [label], n}]`
- `/api/catalog/atlases?subject=&space=subject|mni&kind=cortical|subcortical` → `[{id, name, path, hemispheres?}]` · `/api/catalog/atlases/regions?subject=&atlas=&hemi=` → `[{id, name}]`
- `/api/catalog/rois?subject=` → `[{name, x, y, z, radius?, space}]` · `POST /api/catalog/rois` · `DELETE /api/catalog/rois/{name}`
- `/api/catalog/leadfields?subject=` → `[{net, path, exists, size_bytes}]`
- `/api/catalog/flex-runs?subject=` → `[{name, path, goal, roi, created, manifest}]`
- `/api/catalog/ex-runs?subject=&kind=ex|mex` → `[{run_name, path, eeg_net, created, best: {montage, score}}]` · `/api/catalog/ex-runs/{run}/results?subject=&kind=` → CSV as `{columns, rows}`
- `/api/catalog/analyses?subject=&simulation=` → `[{name, space, field, roi, csv, json, msh?, nifti?, pdf?}]` · `/api/catalog/analyses/{name}/summary?…` → `{columns, rows}`
- `/api/catalog/reports?subject=` → `[{id, kind, title, path, created}]`
- `/api/catalog/freehand?subject=` → `[{name, type, electrode_positions}]` · `PUT /api/catalog/freehand/{name}`
- `/api/catalog/group` → `{stats: [...], nilearn: [...], group_analyses: [...]}`
- `/api/catalog/notes` GET/PUT (Quick Notes), `/api/catalog/subject-info` (presence matrix)

**Schema** — `/api/schema` → `schema.json`; `/api/schema/{name}` → one `$def` resolved.

**Validate / plan** — `POST /api/validate/{kind}` `{config}` → `{ok, errors: [{path, message}]}`;
`POST /api/plan/{kind}` `{config, subject_ids?, overwrite?}` → `{jobs: [{kind, subject, output_dir, exists, will_overwrite}], lock_conflicts: [{key, held_by, kind, subject, started_at}], cost: {cpus, mem_gb}, warnings: [str], resolved: {montages?: [...], search_space?: {...}}}`.
`kind ∈ pre | sim | flex | flex_adaptive | flex_pareto | ex | mex | leadfield | analyzer | stats | source | blender | nifti_average | nilearn`.

**Jobs** — `POST /api/jobs` `{kind, config, subject_ids, after?, tags?, overwrite?}` → `JobStatus`;
`POST /api/jobs/groups` `{kind: "pre", config, subject_ids, parallel_subjects}` → `{group_id, jobs}`;
`GET /api/jobs?state=&subject=&kind=&limit=` → `[JobStatus]`; `GET /api/jobs/{id}` → `{spec, status, artifacts}`;
`GET /api/jobs/{id}/events?since=` → `[Event]`; `GET /api/jobs/{id}/log?tail=` → text;
`POST /api/jobs/{id}/cancel`; `POST /api/jobs/{id}/rerun`; `POST /api/jobs/{id}/force`; `DELETE /api/jobs/{id}`.
`JobStatus = {id, kind, state: queued|running|succeeded|failed|cancelled|skipped|lost, subject_ids, group_id?, created_at, started_at?, finished_at?, progress?: {stage, i, n, pct}, liveness?: active|stalled, waiting_on?: [{key, job_id}], exit_code?, error?: {type, message, last_lines: [str]}, artifacts: [{path, kind, label}], cpu_percent?, rss?}`.
`Event = {seq, ts, type: log|stage|progress|marker|artifact|result|exit, level?, logger?, msg?, stage?, i?, n?, pct?, outputs?}` (`contracts/events.schema.json`).
`WS /ws/jobs` — server → `{type: "job", job: JobStatus}` on every transition; client → `{subscribe: {<job_id>: <since_seq>}}` / `{unsubscribe: [...]}`; server → `{type: "event", job_id, event}`.

**Viewers** — `GET /api/view/{kind}?subject=&simulation=&space=&…` → `ViewSpec {space, layers: [{path, kind: volume|label, colormap, opacity, visible, cal_min?, cal_max?, lut?}], freeview_args: [str]}` (kinds: subject, simulation, analysis, group, custom);
`POST /api/viewers/freeview` `{viewspec}` → `JobStatus` (kind `viewer`); `POST /api/viewers/gmsh` `{path}` → `JobStatus`.

**Files** — `GET /api/files/report/{id}` (HTML, own CSP, for the sandboxed iframe); `GET /api/files/artifact?path=` (pdf/png/csv/json/txt, jailed); `GET /api/files/text?path=&tail=`; `GET /api/files/csv?path=` → `{columns, rows}`.

**Settings / project / system** — `GET|PUT /api/settings` `{telemetry: {consented, enabled}, panels: [name], image_tag?, allow_unsafe_overrides, theme}`; `/api/project` (v0) + `POST /api/project/init` `{example_data}`; `/api/system` (v0) + `POST /api/system/terminate` `{pid}`; `/api/capabilities` (v0 + `jupyter`).

## 4. Gates, artifacts, reporting

Every agent ends with: a file list, exact verification commands + observed output, honest gaps.
The orchestrator runs the full suites at each gate, commits, and updates
`tracks/active/v3-electron-gui.md` "Running state". Screenshots per screen (light + dark) are the
design QA input.

**CI runs the contract gate as a superset check against the real server, not against a fixture.**
The sequence a CI job runs, in order: (1) `docker exec <container> simnibs_python
/ti-toolbox/dev/build_schema.py` regenerates `contracts/schema.json` from the live dataclasses; (2)
`python3 dev/build_contract.py` merges it into `contracts/openapi.v1.yaml` → `openapi.v1.json`; (3)
`cd desktop && npm run gen:api` regenerates `schema.d.ts` and the job fails if that produces an
uncommitted diff (drift between the committed types and what the dataclasses actually describe);
(4) `docker exec <container> simnibs_python -m tit.server --project <fixture-project>
--dump-openapi /tmp/o.json` dumps the real FastAPI app's OpenAPI document (no server process needs
to stay up — `--dump-openapi` builds the app and exits); (5) `python3 dev/contracts_check.py
contracts/openapi.v1.json /tmp/o.json` is the gate: exit 1 fails the job, and its warning count
(dict/list-typed responses the check cannot verify structurally, ra_13 finding 3d) is printed but
never fails the build on its own — only `missing` does. `dev/contracts_check.py` also self-checks
against `openapi.v0.yaml` (step 3's sibling invocation with `openapi.v0.yaml
contracts/openapi.v1.json`, no container needed) so a v0→v1 regression is caught without Docker.
Path normalisation (`{id}`/`{job_id}`/`{report_id}`), the `/ws/*` and 401/403/404 exemptions, and
the `PipelineConfig` exemption are all internal to `contracts_check.py` — CI does not need its own
allowlist or flags for any of them. No workflow file exists yet in this branch; this paragraph is
the spec for whoever adds one.

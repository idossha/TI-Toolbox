# Lane FX2 — jobs + server findings (2026-09-03/04)

Workflow 2, §7 row **FX2**. Five findings from the Workflow-1 runs, all inside `tit/server/**` and
`tit/jobs/**`. Nothing was committed; the shared container was restarted **once** (§ Restarts).

Sources: `dev/notes/v3-pipelines/2026-09-03-smoke.md` open issues 2, 5, 6; `s1-notes.md`
("D0:" request); `s2-notes.md` items 3 and the debugging arc; `f0-notes.md` open issue 1.

## What changed, and why

### 1. `GET /api/project` can now answer `host_path`

`tit/server/host_path.py` (new) + `tit/server/routes/project.py` + `tit/server/schemas.py`
(description only).

The route read exactly one source, `os.environ["LOCAL_PROJECT_DIR"]`. The v3 compose stack
interpolates that variable into the *volumes* entry (`${LOCAL_PROJECT_DIR}:/mnt/${PROJECT_DIR_NAME}`,
`desktop/docker/docker-compose.v3.yml`) and never puts it **inside** the container — verified on the
shared container: `docker inspect --format '{{range .Config.Env}}...'` has `PROJECT_DIR_NAME=000`,
`TIT_SERVER_PORT`, `TIT_SERVER_TOKEN`, `TIT_DEV_ORIGINS`, and no `LOCAL_PROJECT_DIR`. So every v3
server answered `host_path: null` while its own container carried the answer twice: the bind mount
`/Users/idohaber/datasets/000 -> /mnt/000`, and the label `tit.host_project_dir`.

The env var stays authoritative when set. When it is not, the server asks the Engine (over the
socket the stack already mounts for DooD) about **its own** container — id from
`/proc/self/mountinfo`'s `/containers/<64 hex>` path, falling back to `HOSTNAME` — and reads:

1. the `Mounts` bind whose `Destination` is (or contains) the project dir → its `Source`
   (longest-matching destination wins; a project dir nested inside a mount keeps its suffix);
2. else the `tit.host_project_dir` label.

Best-effort by construction: no `/proc`, no socket, an engine error, or a server outside a container
all yield `None` — the same answer as before, never an exception on a request path. Cached per
project dir, so a running server makes at most one Engine call.

*Tests:* `tests/test_server_host_path.py` (12), plus `test_project_shape` in
`tests/test_server_skeleton.py` pinned to "no container" so the shape assertion no longer depends on
where the suite runs.

### 2. `GET /api/openapi.json`

`tit/server/routes/openapi.py` (new) + `tit/server/app.py`.

`create_app` passes `openapi_url=None` (FastAPI's own `/openapi.json` and `/docs` are
unauthenticated by construction, and a route map of a server that can start jobs on the user's
machine should not be). The document itself is worth serving, so it is published at a path under
`/api`, which inherits the app's `require_auth` dependency like every other `/api` route: 401
without a token, 200 with one.

It is the **same document** `--dump-openapi` writes — both call `app.openapi()` → `_custom_openapi`
(pinned by a test that compares them).

`_custom_openapi` now also publishes `JobKind` and `JobState` from `tit.jobs.spec.JOB_KINDS` /
`JOB_STATES`. Without them the generated document names no job enum at all (every job-submitting
route takes `dict[str, Any]`), which is most of the reason to publish it. Taking them from the
runtime tuples means the published enum cannot drift from what the server will accept.

*Contract:* `contracts/openapi.v1.yaml` untouched. `dev/contracts_check.py` against
`contracts/openapi.v0.yaml` (the gated one, and the one `tests/test_server_skeleton.py::
test_openapi_covers_v0_contract` uses) stays **OK**; against `openapi.v1.yaml` the problem count
*drops from 49 to 47* — the two that disappear are `schema JobKind missing from dump components`
and `schema JobState missing from dump components`. No new problem. The dump gains one path
(`/api/openapi.json`) and two schemas; extra paths/schemas in the dump are explicitly fine.

### 3. A cancelled job no longer looks like a crash

`tit/jobs/runner.py` (`runner_env`) + `tit/jobs/manager.py` (`_append_cancel_note`).

**Where the block came from — measured, not guessed.** In the shared container:

```
simnibs_python -c "import simnibs; print('READY'); time.sleep(60)"   → SIGTERM
[0]PETSC ERROR: Caught signal number 15 Terminate: ...
application called MPI_Abort(MPI_COMM_WORLD, 59) - process 0
```

`import simnibs` alone initialises PETSc, which installs a C SIGTERM handler. That is why a
`blender` job that runs no solver ended in solver wreckage (job `169bb37396634a31`), and a `flex`
job cancelled two lines into "Setting up headmodel" did too (`b9632d9056de45c1`).

Two candidate fixes, both measured in the container:

| Probe | Result |
|---|---|
| `PETSC_OPTIONS=-no_signal_handler` + SIGTERM | exit 143, **no block**, no other output |
| Python `signal.signal(SIGTERM, …)` installed *after* `import simnibs` + SIGTERM | exit 143, prints its line, no block |
| `PETSC_OPTIONS=-no_signal_handler`, normal exit | no PETSc "unused options" warning (checked: plain import, and `simnibs.mesh_tools.mesh_io`) |

The second only works if the handler is installed *after* PETSc initialises, which means one edit
per runner package (`tit/sim`, `tit/blender`, … — other lanes' files) and a fragile ordering
contract. The first is one line in `runner_env`, applies to every kind, and cannot be raced.

So: `runner_env` appends `-no_signal_handler` to `PETSC_OPTIONS` (keeping any value the caller
already set, never doubling it), and `JobManager._cancel_running` appends the single line
`cancelled by user` to the job's `stdout.log` **after `terminate_tree` returns** — i.e. after the
process tree is gone, so nothing can write past it. The runner cannot write that line itself:
SIGTERM's default disposition ends it without running any Python.

*Tree-death guarantee:* unchanged. `terminate_tree` still snapshots descendants, SIGTERMs the tree,
waits `DEFAULT_GRACE_S`, SIGKILLs survivors. If anything, cancel is *faster* than it would be with
a Python handler: the default disposition kills immediately even mid-C-call, where a Python-level
handler would have to wait for the interpreter to regain control.

*Trade-off, deliberate:* PETSc no longer prints its own diagnostics for a genuine SIGSEGV/SIGFPE
either. `PYTHONFAULTHANDLER=1` (already set by `runner_env`) still dumps the Python-level traceback
for those, which is the more useful half for this application's users. Recorded in the code comment.

*Tests:* `tests/test_jobs_model.py` (2, `runner_env`), `tests/test_jobs_manager.py` (2, the note is
written exactly once, is the last line, and no `PETSC ERROR`/`MPI_Abort` line survives; plus the
missing-log path).

### 4. The trailing `report` job holds the locks its scan needs

`tit/jobs/locks.py` (`_report_requests`, and a per-subject `report` branch in `keys_for`).

`keys_for("report", …)` returned `[]` for a per-subject report: the only `report` branch was a
top-level `elif kind == "report" and config.get("group")`, and `plan_preprocessing`'s report config
has no `"group"` key (f0-notes open issue 1). The job scanned a subject's rawdata and derivatives
holding nothing.

`tit.pre.report` reads `rawdata/sub-<id>` and the derivatives of each stage the group ran
(`PreprocessingReportGenerator.scan_for_data`), and writes one HTML file for that subject. Its
config is the group's own `PreprocessConfig` narrowed to one subject with the stage flags left as
the caller set them — the same shape `_PRE_STAGE_FLAGS` already reads. So:

- read: `subject:<sid>:stage:<s>` for each stage the group ran, `subject:<sid>:bids`,
  `subject:<sid>:m2m`;
- write: `subject:<sid>:report` — its own output, so two reports for the same subject serialize
  instead of racing on one file.

Read locks, not write ones: two subjects' reports, and a report beside an unrelated subject's `pre`
job, must still run concurrently. The old group-report branch is untouched.

*Tests:* `tests/test_jobs_model.py` (2, including one driven by `plan_preprocessing`'s real output
for two subjects asserting the two reports share no resource).

### 5. `GET /api/jobs/{id}` — who was wrong

Nobody, on the server side. Checked all four consumers of the shape:

| Side | Shape | Verdict |
|---|---|---|
| `tit/jobs/manager.py::get_detail` → route | `{spec, status, artifacts}` | correct |
| `contracts/openapi.v1.yaml` `JobDetail.required` | `[spec, status, artifacts]` | agrees |
| `desktop/src/renderer/api/schema.d.ts` | `JobDetail` | agrees (generated from the contract) |
| `tests/smoke/client.py::job/status` | unwraps `["status"]` | agrees |

The renderer's own client (`app/jobs-rail/api.ts`) never calls this route at all — it uses the list
route plus `/ws/jobs`. The one side that was wrong was Level B's helper `getJobStatus`
(`desktop/tests/e2e/_helpers.ts`), which read `state`/`artifacts` off the top level and therefore
polled forever on jobs that had already succeeded — S2 fixed it in Workflow 1. So the work here is
to make the divergence impossible to reintroduce silently:
`tests/test_jobs_routes.py::test_job_detail_top_level_shape_is_exactly_the_contract` asserts the
live response's top-level key set **equals** the contract's `JobDetail.required`, that `state` is
*not* at the top level, and that `spec`/`status` each carry their own contract-required properties.

## Real runs

All against the shared container `ti-toolbox-fad740e5-tit-1` (`http://127.0.0.1:8765`, project
`/mnt/000` = `/Users/idohaber/datasets/000`), 2026-09-04 UTC. `GET /api/jobs` was checked before
every submit and before the restart; no FEM-class job ever overlapped another.

| # | What ran | Job id | Wall | Outcome |
|---|---|---|---|---|
| P0 | `docker exec` probe: `simnibs_python -c "import simnibs; sleep"` + SIGTERM (before any change) | — | ~40 s | reproduced the PETSc block from a bare import — no solver, no `tit` code |
| P1 | Same probe with `PETSC_OPTIONS=-no_signal_handler` | — | ~40 s | exit **143**, no block, no other output |
| P2 | Same probe with a Python SIGTERM handler installed after `import simnibs` | — | ~40 s | exit 143, printed its own line, no block (the rejected alternative) |
| P3 | In-container, pre-restart: `tit.server.host_path` against the live container | — | 2 s | `own_container_id()` = `f17995acd796…`, `host_project_dir('/mnt/000')` = `/Users/idohaber/datasets/000` |
| P4 | In-container, pre-restart: `TestClient(create_app(...))` for `/api/project` + `/api/openapi.json` | — | 5 s | `host_path` resolved; 401 without token, 200 with; 55 paths |
| R0 | `docker restart ti-toolbox-fad740e5-tit-1` (0 jobs in flight) | — | **3 s** to `/api/health` | the lane's only restart |
| R1 | `GET /api/project` | — | — | `{"container_path":"/mnt/000","host_path":"/Users/idohaber/datasets/000","name":"000"}` — was `host_path: null` |
| R2 | `GET /api/openapi.json` with and without a bearer token | — | — | **401** / **200**; 55 paths, 90 schemas; `JobKind` = the 17 kinds; `JobState` = the 7 states |
| R3 | `simnibs_python -m tit.server --project /mnt/000 --dump-openapi` in the container, compared to R2 | — | 20 s | **identical documents** (`served == dumped: True`) |
| R4 | `pytest tests/smoke -m smoke --smoke-kinds sim_ti` (started → cancel, sub-101) | `934d281da98348d4` | **10.57 s** | **passed**; `cancelled`, exit `-15`; log ends `cancelled by user` — 1 occurrence, last line, **0** PETSc/MPI lines |
| R5 | Real `blender` montage export on `sub-ernie`, started → cancelled (`created_by: fx2-smoke`) | `0d8ad07c76dc4731` | banner at **33.4 s**, cancel → `cancelled` in **0.3 s** | 1 `cancelled by user`, last line, **0** PETSc/MPI lines. Its 51 MB output dir `visual_exports/smoke-fx2-202215` was deleted afterwards (verified gone) |
| R6 | `pytest tests/smoke -m smoke --smoke-kinds pre_report` (real `pre` group: DICOM → report, sub-102) | `684f18bb224d4eaf` (pre) + `20d4d9d21b414942` (report) | **19.39 s** | **passed**, both `succeeded`; the report's spec carries `['subject:102:stage:dicom:read', 'subject:102:bids:read', 'subject:102:m2m:read', 'subject:102:report:write']` — it carried `[]` before. `sub-102` and its derivatives cleaned up (verified gone) |
| R7 | *Another lane's* report job, submitted after the restart (sub-101 tissue group) | `5ea168dea72740d8` | — | `succeeded`, exit 0, 1 artifact, 4 locks; queued on its `after` edge, never on a lock |
| R8 | *Another lane's* cancelled `sim`, after the restart | `a5898be3006e4c94` | — | independent confirmation: 1 `cancelled by user`, last line, **0** PETSc/MPI lines |
| R9 | `find` for leftovers + the advisory lock directory | — | — | no `smoke-fx2*` path anywhere, `sub-102` gone, `m2m_101`/`m2m_ernie` untouched; `jobs/.locks` **empty** right after the runs (it later held 2 entries for another lane's own `source` job -- nothing of this lane's leaked) |

Host and desktop gates:

| Gate | Result |
|---|---|
| `python3 -m pytest -q` (host, smoke deselected) | **3344 passed, 18 skipped, 21 deselected — 36.5 s** (final run) |
| `dev/contracts_check.py contracts/openapi.v0.yaml <dump>` (the gated contract) | **OK** — 10 operations, 9 schemas |
| `dev/contracts_check.py contracts/openapi.v1.yaml <dump>` | problems **49 → 47** (only `JobKind`/`JobState` "missing from dump" disappear); no new problem |
| `desktop npm run typecheck` | clean |
| `desktop npx vitest run` | **713 passed (61 files)** |
| `desktop npm run lint` | 1 error, **pre-existing and not this lane's**: `tests/e2e/real/preprocess.spec.ts:1:35 'rmSync' is defined but never used` (untracked WIP of another lane; FX2 changed no desktop file) |
| `desktop npm run build` | **not run** — no desktop file changed, and the program forbids racing `out/` with other lanes |

## Restarts

**1.** `docker restart ti-toolbox-fad740e5-tit-1` at 01:19:40 UTC, after `GET /api/jobs` showed
nothing running or queued: this lane waited ~12 min for another lane's `source` job
`c8ef9a4a2d454ff0` to finish (polled every 15 s), so the restart killed no one's work.
`/api/health` answered 3 s later.
Every server- and jobs-side change in this lane went in that one restart; the two pre-restart
probes (P3, P4) were run in-process inside the container precisely so the restart only had to
happen once.

## Requests to other lanes

1. **D0 (owner of `desktop/docker/docker-compose.v3.yml` and `desktop/src/shared/compose*.ts`) —
   pass `LOCAL_PROJECT_DIR` into the container's `environment:`.** The compose file interpolates
   `${LOCAL_PROJECT_DIR}` into the volume entry but never sets it inside the container. FX2 made the
   server able to *recover* the value from its own container, which covers containers already
   running and servers started outside the app -- but the variable is the documented source and one
   line makes it authoritative again:

   ```yaml
       environment:
         LOCAL_PROJECT_DIR: ${LOCAL_PROJECT_DIR}
   ```

   It matters beyond `host_path`: `tit/pre/qsi/utils.py::get_host_project_dir()` raises
   `ValueError("LOCAL_PROJECT_DIR environment variable is not set. This is required for spawning
   sibling Docker containers.")`, so **any QSIPrep/QSIRecon run in the v3 stack that gets past the
   DWI preflight cannot spawn its sibling container**. Dataset 000 has no DWI, so the smoke matrix's
   `pre_qsiprep` row (behaviour `refused`) stops at the preflight and no lane has hit this.

2. **HX (owner of `tests/smoke/**`, `dev/smoke.sh`) — the harness no longer needs
   `docker inspect` for the host project directory.** `GET /api/project` now answers `host_path`,
   so `TIT_SMOKE_PROJECT_HOST` can default to `client.get("/api/project")["host_path"]` and
   `dev/smoke.sh` can drop its `tit.host_project_dir` label read (keep the env var as an override
   for a server that genuinely cannot know, e.g. one running outside a container).

3. **FX5 / whoever owns `desktop/tests/e2e/real/preprocess.spec.ts` (currently untracked WIP) —
   `npm run lint` fails on it:** `1:35 error 'rmSync' is defined but never used
   @typescript-eslint/no-unused-vars`. Everything else in the desktop gate is green (typecheck
   clean, vitest 713/713). FX2 changed no desktop file, so this is reported, not fixed.

4. **Whoever next edits `contracts/openapi.v1.yaml` (documentation only, no wire change):**
   `Project.host_path`'s description still reads "from LOCAL_PROJECT_DIR when known". The server's
   own description (`tit/server/schemas.py`) was updated to the two sources it now uses. FX2 left
   the frozen contract alone on purpose -- changing it would drift
   `desktop/src/renderer/api/schema.d.ts` (generated from `contracts/openapi.v1.json`) until someone
   re-ran `npm run gen:api`, for a comment.

## Numbers

| Metric | Before | After |
|---|---|---|
| `GET /api/project.host_path` on the shared container | `null` | `/Users/idohaber/datasets/000` |
| Clients needing `docker inspect` to map `/mnt/000` → host | `dev/smoke.sh`, `desktop/src/main/index.ts` fallback | 0 (the API answers) |
| Live OpenAPI document | none (`openapi_url=None`) | `GET /api/openapi.json`, 401 → 200, 55 paths / 90 schemas |
| Job enums discoverable from a live server | 0 | `JobKind` (17), `JobState` (7), from `tit.jobs.spec` |
| Lines a cancelled job's log ends with | 10 (PETSc block + MPI_Abort + PMIU noise) | 1 (`cancelled by user`) |
| PETSc/MPI lines in a cancelled `sim` (real, sub-101) | 8 | **0** |
| PETSc/MPI lines in a cancelled `blender` (real, ernie — no solver at all) | 8 | **0** |
| Cancel latency, real blender | — | 0.3 s to `cancelled`; process tree death still bounded by `DEFAULT_GRACE_S`=10 s + SIGKILL |
| Locks held by a per-subject `report` job | 0 | 4 (3 read + 1 write) |
| `dev/contracts_check.py` problems, `openapi.v1.yaml` | 49 | 47 |
| Host suite | — | **3344 passed, 18 skipped, 21 deselected / 36.5 s** on the final run (other lanes add tests concurrently -- it read 3339 an hour earlier; smoke stays deselected) |
| Tests added by this lane | — | **26** new, 1 changed |

The 26: `tests/test_server_host_path.py` **14**, `tests/test_server_openapi_route.py` **5**,
`tests/test_jobs_model.py` **+4** (2 `runner_env`, 2 `keys_for("report")`),
`tests/test_jobs_manager.py` **+2** (cancel note, and the missing-log path),
`tests/test_jobs_routes.py` **+1** (JobDetail shape vs the contract). Changed:
`tests/test_server_skeleton.py::test_project_shape`, pinned to "no container" so the assertion is
about the response shape rather than about where the suite happens to run. Every one of the 26
fails without its fix — by construction: a route that did not exist, a field that was `null`, a log
line nothing wrote, a lock list that was empty.

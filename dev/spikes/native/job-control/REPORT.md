# N0.6 — Cross-platform job control and container-path assumptions

Spike report. Repo: `/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui`,
branch `feature/v3-electron-gui`. Machine: Apple M2 Max / macOS 15 (a POSIX host — the "real
Windows interpreter" claims below could not be executed, only reasoned from primary sources and
exercised via monkeypatched seams; see "What this does not prove").

Read in full before starting: `dev/notes/v3-native-desktop-plan.md` (verdict, §1, N0.6 row),
`dev/notes/v3-native-research/r6-native-deps-audit.md`, `dev/notes/v3-native-research/skeptic-3.md`.

## 0. Bugs this fixes (cited by r6 §2a and skeptic-3 claims #3/#4)

1. **`tit/jobs/runner.py:213`** called `proc.send_signal(signal.SIGKILL)` unconditionally on
   the hard-kill escalation path. `signal.SIGKILL` does not exist as an attribute in the
   Windows build of Python's `signal` module at all ("Availability: Unix",
   docs.python.org/3/library/signal.html, quoted verbatim by skeptic-3) — referencing it raises
   `AttributeError` *before* the existing `psutil.NoSuchProcess/AccessDenied` guard
   (`_ignore_gone()`) ever gets a chance to catch it (that guard's exception tuple never
   included `AttributeError`). Every stuck/runaway job's cancel-after-grace-period path hit
   this on Windows.
2. **`tit/jobs/runner.py:86`** passed `start_new_session=True` unconditionally to
   `asyncio.create_subprocess_exec`. `start_new_session` is documented POSIX-only; on Windows
   CPython's `subprocess._execute_child` receives it as `unused_start_new_session` and silently
   ignores it (verified by reading this host's own installed `subprocess.py`, same code path
   3.11-3.14) — so a spawned job on Windows would land in the *server's own* process group,
   with no group `terminate_tree` could target independently.
3. **`tit/pre/qsi/docker_builder.py`** never emitted a `--label` flag on any `docker run`
   command it built. `tit/jobs/runner.py`'s `stop_docker_siblings(job_id)` filters
   `docker ps -q --filter label=tit.job_id=<id>` — with zero labels ever set, this always
   matched zero containers: a cancelled QSIPrep/QSIRecon job's sibling container was never
   found and never stopped (dead code, not merely untested — confirmed via
   `grep -n "label" tit/pre/qsi/docker_builder.py` before this change: only
   `--participant-label`, QSIPrep's own unrelated BIDS arg).
4. **Three hard-coded `/ti-toolbox/...` absolute paths** — real executable code, not
   docstrings/comments — only ever valid inside the Docker image, never on a native host:
   `tit/tools/montage_visualizer.py:26` (`_RESOURCES_DIR`), `tit/atlas/constants.py:26`
   (`MNI_ATLAS_DIR`), `tit/blender/montage_publication.py:365` (`electrode_template`).

## 1. What I did

### 1a. `tit/jobs/processes.py` (new) — the platform split, expressed once

A small module with four functions: `is_windows()` (a named, mockable seam — tests monkeypatch
*this*, not `sys.platform`/`os.name` directly), `spawn_kwargs()` (POSIX
`start_new_session=True`; Windows `creationflags=CREATE_NEW_PROCESS_GROUP`), `send_terminate()`
(POSIX `SIGTERM`; Windows `psutil.Process.terminate()`), `send_kill()` (POSIX `SIGKILL`; Windows
`psutil.Process.kill()`).

Key design point: `CREATE_NEW_PROCESS_GROUP` is **hardcoded as `0x00000200`**
(winbase.h / `_winapi.CREATE_NEW_PROCESS_GROUP`'s real value) rather than read off
`subprocess.CREATE_NEW_PROCESS_GROUP`. CPython's own `subprocess.py` only defines that name
inside its `if _mswindows:` block — referencing it from code that also runs (or is merely
*tested*) on POSIX would itself raise `AttributeError`, the exact mirror-image of the
`signal.SIGKILL` bug this module exists to remove. This is also what makes the Windows branch
of `spawn_kwargs()` genuinely callable and testable on this Mac (see §2).

`tit/jobs/runner.py` changes:
- `LocalPopenRunner.spawn()`: `start_new_session=True` -> `**spawn_kwargs()`.
- `terminate_tree()`: both `proc.send_signal(signal.SIGTERM/SIGKILL)` calls ->
  `send_terminate(proc)` / `send_kill(proc)`.
- `RunRequest.stdout_path` default: hardcoded `"/dev/null"` -> `os.devnull` (found while
  auditing the file; `/dev/null` doesn't exist on Windows either — every real caller,
  `tit/jobs/manager.py`, always passes an explicit `stdout_path`, so this only matters for a
  hypothetical future caller that doesn't).
- Removed the now-unused `import signal`.

**Chose not to touch `tit/pre/utils.py`.** Its own `_terminate_process()`
(`tit/pre/utils.py:364-375`) already branches correctly (`os.name == "nt"` ->
`proc.terminate()`; else `os.killpg(proc.pid, signal.SIGTERM)`) and never calls `SIGKILL` at
all — a different, simpler design (single SIGTERM, no psutil-tracked-tree grace/hard-kill
escalation) that was never actually broken. Unifying it onto `tit/jobs/processes.py` would be a
larger, riskier change (it uses `os.killpg` against a whole process *group* by pid, not a
psutil-snapshotted tree) for no bug-fix benefit — flagged as an N1 nice-to-have, not done here.

### 1b. `tit/pre/qsi/docker_builder.py` — `--label` on every QSI container

Added `DockerCommandBuilder._label_args(kind)`: always emits `--label tit.kind=qsiprep` (or
`qsirecon`); additionally emits `--label tit.job_id=<id>` when `TIT_JOB_ID` is set in the
environment. Wired into both `build_qsiprep_cmd()` and `build_qsirecon_cmd()`, right after
`--name`, before any other option.

`TIT_JOB_ID` is read via `os.environ.get("TIT_JOB_ID")`, a **local string constant**
(`_JOB_ID_ENV_VAR`), not an import of `tit.jobs.runner.ENV_JOB_ID` — `tit/jobs/plans.py`
already imports `tit.pre.config`, so `tit.pre` importing back from `tit.jobs` would create a
cycle between the two packages; `tit.pre` stays the lower layer. Traced the actual data flow to
confirm this is correct, not just plausible: `tit/jobs/kinds.py`'s `MODULE_FOR_KIND["pre"]` is
`"tit.pre"`, run as `simnibs_python -m tit.pre spec_path` — a job process spawned by
`LocalPopenRunner` with `env=runner_env(job_id=..., kind="pre", ...)`
(`tit/jobs/manager.py:668-673`), which sets `TIT_JOB_ID` (`tit/jobs/runner.py:124`) in that
process's own environment. `DockerCommandBuilder` runs *inside* that same "pre" job process
(imported by `tit/pre/qsi/qsiprep.py`/`qsirecon.py`, not a separate subprocess), so
`os.environ["TIT_JOB_ID"]` there is exactly the same top-level job id
`JobManager.cancel()` -> `_cancel_running()` (`tit/jobs/manager.py:452-453`) later passes to
`stop_docker_siblings(job_id)`. Confirmed no other kind value is used for QSI jobs
(`tit/jobs/plans.py` uses `kind="pre"` for every preprocessing step it builds).

### 1c. Hard-coded container paths -> package-relative resolver

New `tit/paths.py` functions `resolve_resources_dir()` / `resolve_resource_path(*parts)`
(placed near `natural_key`, before `PathManager` — a distinct, package-*resources* concern from
`PathManager`'s project-*directory* concern, but colocated since `tit/paths.py` is the module
r6 names as the natural home for path-resolution logic). Resolution order: `TIT_RESOURCES_DIR`
env var (if set and a real directory) -> `/ti-toolbox/resources` (unchanged container behaviour)
-> `<repo_root>/resources` (checkout-relative, `repo_root` two levels above `tit/paths.py`),
returned even if it doesn't exist so callers get an informative path rather than `None`.

Wired in:
- `tit/tools/montage_visualizer.py`: `_RESOURCES_DIR = resolve_resource_path("amv")`.
- `tit/atlas/constants.py`: `MNI_ATLAS_DIR = resolve_resource_path("atlas")`.
- `tit/blender/montage_publication.py`: `electrode_template` resolved package-relatively
  (`os.path.join(os.path.dirname(os.path.abspath(__file__)), "Electrode.blend")`) — *not*
  through `resolve_resource_path`, because `Electrode.blend` ships inside `tit/blender/` itself,
  not the top-level `resources/` tree; a plain sibling-of-this-file lookup is simpler and
  correct for both the checkout and (packaging permitting — see below) a wheel.

**The wheel-install case is not solved, only documented and given an escape hatch.**
`pyproject.toml`'s `[tool.setuptools.packages.find] include = ["tit*"]` and the total absence
of a `MANIFEST.in` or `package_data` entry anywhere in the repo (`find . -iname MANIFEST.in`
-> nothing) mean: (a) the top-level `resources/` tree is not part of a wheel build at all —
`TIT_RESOURCES_DIR` is the only way to point at it once packaged; (b)
`tit/blender/Electrode.blend`, despite living inside the `tit` package tree, would *also* not
be included in a wheel today without an explicit `package_data`/`MANIFEST.in` declaration — a
real gap for N1 packaging, flagged in both the code comment and here, not fixed in this lane
(out of scope: no packaging config file is in N0.6's owned-paths list).

**Bonus fix, same file, same theme:** `tit/tools/montage_visualizer.py`'s template-copy step
called `subprocess.run(["cp", template, out_image], check=True)` — `cp` doesn't exist on
Windows. Replaced both call sites with `shutil.copy2(template, out_image)` (stdlib, identical
semantics — preserves mtime/metadata like `cp`, cross-platform). The ImageMagick `convert`
calls elsewhere in the same file are a separate, still-external-binary dependency, deliberately
left alone (out of this lane's scope; not a job-control or container-path issue).

### 1d. Swept for other posix-only assumptions (brief item 4)

`rg` across `tit/jobs` and `tit/pre` for `os.setsid`, `os.killpg`, `signal.SIG*`, `'/tmp'`,
`shell=True`, `preexec_fn`, `os.fork`, `chmod`/`0o###` perms, hardcoded `/mnt`/`/ti-toolbox`.
Findings, all checked and **none needing a fix**:
- `tit/pre/utils.py:370` `os.killpg(proc.pid, signal.SIGTERM)` — already correctly guarded by
  `os.name == "nt"` one line above (§1a).
- `tit/pre/structural.py:80` `signal.signal(signal.SIGTERM, _handle_sigterm)` — `SIGTERM` *is*
  available on Windows (Python docs, quoted in skeptic-3: "signal() can only be called with
  SIGABRT, SIGFPE, SIGILL, SIGINT, SIGSEGV, SIGTERM, or SIGBREAK" — SIGTERM is in that list);
  already wrapped in `try/except (ValueError, OSError)` and guarded to the main thread only.
  Not owned by this lane; checked, not a bug.
- `tit/pre/qsi/docker_builder.py:132` `container_path = "/tmp/recon_spec.yaml"` — this is a
  path *inside* the QSIPrep/QSIRecon Linux container itself (`docker run --platform
  linux/amd64`), not a host path; that container is always Linux regardless of host OS. Not a
  bug.
- `tit/jobs/bootstrap.py:18/39-42` `DEFAULT_RUNNER_CWD = "/ti-toolbox"` — already falls back to
  the project directory on a host where that path doesn't exist (r6 already verified this;
  independently re-confirmed by reading the file). Not owned by this lane (not in the owned-
  paths list); no change needed.
- `tit/jobs/registry.py`'s `"code/ti-toolbox/jobs/"` string is a project-relative BIDS
  subpath joined via `os.path.join` at every real call site, not a host filesystem path; no
  Windows-separator issue.
- No `os.fork`, no `shell=True`, no raw `chmod`/octal-permission bit-setting anywhere in either
  package.

## 2. Tests added (208 collected across the touched-file test modules; all new/changed tests
pass on both this Mac and the Linux SimNIBS container — see §3)

| File | What's new |
|---|---|
| `tests/test_jobs_processes.py` (new, 9 tests) | `is_windows()`; `spawn_kwargs()` POSIX branch (real) and Windows branch (monkeypatched, asserts the exact `CREATE_NEW_PROCESS_GROUP` value and that `start_new_session` is never in the dict); `send_terminate`/`send_kill` POSIX branch (asserts `send_signal(SIGTERM/SIGKILL)`, real signal values) and Windows branch (asserts `proc.terminate()`/`proc.kill()`, and that `send_signal` is *never* called); a static source-level guard that `send_kill`'s Windows branch never references `SIGKILL` in its own source text. |
| `tests/test_jobs_runner.py` (new, 5 tests) | **Real, unmocked integration test**: spawns an actual child process via `LocalPopenRunner.spawn()` and asserts `os.getpgid(child) != os.getpgid(self)` — proves `spawn_kwargs()`'s POSIX branch is actually wired through, not just unit-tested in isolation. **Real end-to-end hard-kill escalation**: spawns a child that installs `signal.SIG_IGN` for SIGTERM and sleeps 30s, calls `terminate_tree(pid, grace_s=0.3)`, and asserts the child is actually dead afterward — proves the SIGTERM->grace->SIGKILL escalation still works after routing through `tit.jobs.processes` instead of raw `send_signal`. Windows-branch spawn test (mocked `asyncio.create_subprocess_exec`, since passing a real Windows creationflags value to a real POSIX `Popen` raises `ValueError` — documented in the test as the platform boundary this Mac cannot cross). Windows-branch `terminate_tree` test (mocked `psutil.Process`, asserts `terminate()`/`kill()` called, `send_signal` never called). `RunRequest.stdout_path` default `== os.devnull`. |
| `tests/test_pre_qsi_docker.py` (+7 tests, `TestDockerLabels`) | `tit.kind` always present (both builders); no `tit.job_id` label when `TIT_JOB_ID` unset; `tit.job_id` matches the env var exactly (both builders); labels appear before the image name in argv (a `--label` after the image name would be a positional arg to the container's entrypoint, not a docker-run option — this would be a silent, hard-to-notice bug if regressed). |
| `tests/test_paths.py` (+6 tests, `TestResolveResourcesDir`) | Checkout-relative fallback resolves to the *real*, on-disk `resources/` directory of this repo (not just a plausible string); env override wins when set to a real dir; a stale/nonexistent env override is ignored, falling through; container-layout branch wins when `/ti-toolbox/resources` exists (simulated via monkeypatched `os.path.isdir`, since this host isn't root and can't create `/ti-toolbox`); `resolve_resource_path` joins correctly. |
| `tests/test_atlas.py` (+2 tests) | `MNI_ATLAS_DIR` points at a real, existing directory on this host and matches `resolve_resource_path("atlas")` exactly. |
| `tests/test_tools.py` (+2 tests) | `_RESOURCES_DIR` points at a real directory containing the expected files; **real, unmocked** call to `visualize_montage()` with `electrode_pairs=[]` (so only the template-copy path runs, no ImageMagick `convert` needed) asserts `subprocess.run` is never called and a real PNG is written to disk. |
| `tests/test_blender_integration.py` (+2 tests) | `run_montage`'s source no longer contains the literal `"/ti-toolbox"` string; the package-relative `Electrode.blend` path is a real file on this host. |

## 3. Gates

**Host, full suite** (`.venv` built with `uv venv --python 3.11.14`; installed
`psutil fastapi uvicorn pydantic pyyaml numpy scipy jsonschema joblib nibabel matplotlib pandas
pytest black httpx`, matching r6's own working set plus `httpx` so the `httpx`-gated API-client
tests run instead of skipping):

```
python -m pytest -q
=== 1 failed, 3114 passed, 17 skipped, 14 warnings in 29.94s ===
```

The one failure, `tests/test_logger.py::TestSetupLogging::test_clears_existing_handlers`, is
**pre-existing and unrelated to this lane**: reproduces in total isolation
(`pytest -q tests/test_logger.py` alone, before touching any file in this lane), touches
`tit/logger.py` (not in this lane's owned paths, not edited), and is a handler-count assertion
that looks like a pytest-plugin/log-capture-handler interaction, not a `tit` code bug.

**This is a six-lane shared worktree; numbers moved under me mid-session.** While this lane was
running, a concurrent lane's uncommitted edits to `tit/atlas/voxel.py` / `tit/atlas/segstats.py`
(both explicitly *not* owned by N0.6 — the plan's own table assigns them to N0.5) transiently
broke, then fixed, two unrelated tests (`tests/test_atlas_coverage.py`, then a new
`tests/test_atlas_segstats.py`) — confirmed via `git status --short` showing those exact paths
as `M`/`??` at the time, and confirmed by re-running the affected tests in isolation both before
and after this lane touched anything (both passed with an untouched checkout at the very start
of this session). `git status --short` at the end of this lane's work shows exactly the files
below as touched by *this* lane — nothing else:

```
 M tests/test_atlas.py
 M tests/test_blender_integration.py
 M tests/test_paths.py
 M tests/test_pre_qsi_docker.py
 M tests/test_tools.py
 M tit/atlas/constants.py
 M tit/blender/montage_publication.py
 M tit/paths.py            (additive: resolve_resources_dir/resolve_resource_path only --
                              the rest of this file's diff, e.g. list_bids_subjects(), predates
                              this session and belongs to other WIP)
 M tit/pre/qsi/docker_builder.py
 M tit/tools/montage_visualizer.py
?? tests/test_jobs_processes.py
?? tests/test_jobs_runner.py
?? tit/jobs/                (processes.py is new; the rest of tit/jobs/ is pre-existing
                              uncommitted walking-skeleton work, untracked from before this
                              session -- runner.py's edits are inside it)
```

**`black`** on every touched file (`--fast`, since this host's Python 3.11 triggers black's
own safety-check warning against an unrelated newer-syntax auto-target -- not a real issue,
`--fast` skips only the redundant AST-equivalence re-check, not the formatting itself):
```
black --check --fast <14 files>
=== All done! 14 files would be left unchanged. ===
```
(Ran once without `--check` first to apply formatting -- 6 files reformatted, all pre-existing
line-length wraps in my own new test docstrings/asserts; re-ran the full host suite afterward,
same 1-failed/3114-passed result, confirming the reformat changed nothing behavioural.)

**Container, Linux, real `psutil` 7.2.2** (`tit-v3-spike`, `idossha/simnibs:v2.5.0`, worktree
bind-mounted at `/ti-toolbox` -- files created on the host appear immediately, confirmed via
`docker exec tit-v3-spike ls /ti-toolbox/tests/`):
```
docker exec -w /ti-toolbox tit-v3-spike simnibs_python -m pytest -q \
  tests/test_jobs_runner.py tests/test_jobs_processes.py tests/test_jobs_manager.py tests/test_pre_qsi_docker.py
=== 75 passed in 9.96s ===

docker exec -w /ti-toolbox tit-v3-spike simnibs_python -m pytest -q \
  tests/test_paths.py tests/test_atlas.py tests/test_tools.py tests/test_blender_integration.py
=== 158 passed in 0.47s ===
```
Also confirmed, live in the container, that the resource-path resolver picks the *container*
branch (not the checkout-relative fallback) exactly as designed, since `/ti-toolbox/resources`
genuinely exists there:
```
docker exec tit-v3-spike simnibs_python -c "from tit.paths import resolve_resources_dir; from tit.atlas.constants import MNI_ATLAS_DIR; print(resolve_resources_dir()); print(MNI_ATLAS_DIR)"
/ti-toolbox/resources
/ti-toolbox/resources/atlas
```

## 4. What this proves

- The exact Windows crash at `runner.py:213` (`AttributeError` on `signal.SIGKILL`) is fixed:
  the Windows branch of `send_kill()` never evaluates that attribute at all (verified two ways --
  a monkeypatched-`is_windows` test asserting `proc.kill()`/`proc.terminate()` are called and
  `send_signal` never is, and a static source-text check that the Windows branch's source never
  contains the string `SIGKILL`).
- The POSIX behaviour that existed before this refactor is **unchanged and re-verified live**:
  a real spawned child lands in its own process group (real `os.getpgid` check), and the real
  SIGTERM->grace->SIGKILL escalation still kills a SIGTERM-ignoring child within the grace window
  -- on both macOS (host) and Linux (container, real `psutil`).
- QSIPrep/QSIRecon cancel's dead-code gap (skeptic-3 claim #3) is closed at the
  command-construction level: every `docker run` this builder emits now carries
  `--label tit.job_id=<id>` when run inside a real job, with the exact env-var contract traced
  end to end from `runner_env()` through to `stop_docker_siblings()`'s filter.
- The three real hard-coded `/ti-toolbox` path literals are gone; the checkout-relative
  fallback resolves to genuinely-existing directories on this host (not just plausible strings)
  and the container behaviour is provably unchanged (verified live inside `tit-v3-spike`).

## 5. What this does NOT prove (be honest about the gap)

- **No Windows interpreter was available anywhere in this session.** Every Windows-branch claim
  above is exercised via `monkeypatch.setattr(processes, "is_windows", lambda: True)` plus
  mocked `psutil.Process`/`asyncio.create_subprocess_exec` -- this proves the *code path taken*
  is the intended one, and that the primitives used (`psutil.Process.terminate()/.kill()`,
  `subprocess.CREATE_NEW_PROCESS_GROUP`'s real numeric value) are documented-correct per
  psutil's own docs and Python's own signal docs (both cited by skeptic-3 from primary
  sources), but it is not the same as a real Windows box running `python -m tit.jobs...` and
  cancelling a real stuck job. Flagged by skeptic-3 as a general gap across the whole
  six-report set, not resolved here.
- **The wheel-packaging case for `resources/` and `Electrode.blend` is documented, not fixed.**
  `TIT_RESOURCES_DIR` is a real, tested escape hatch, but nothing in this lane adds
  `package_data`/`MANIFEST.in` entries -- a packaged (non-checkout, non-container) install today
  would need that env var set explicitly by whatever launches it (the native Electron
  launcher, per the plan's SS1 architecture) or it silently falls through to a checkout-relative
  path that won't exist. This is squarely `pyproject.toml`/packaging territory, outside this
  lane's owned paths.
- **`tit/pre/utils.py` was deliberately left unmodified** -- its Windows handling was already
  correct (different code shape, not the same bug), so "unify onto processes.py" was scoped
  out as unnecessary risk for this lane's time-box; a future pass could still do it for
  consistency's sake (not correctness).
- Podman/Colima Docker-engine compatibility (skeptic-3 claims #5, #10) is out of this lane's
  scope entirely -- this lane only fixed the *label* half of QSIPrep/QSIRecon cancellation, not
  the underlying Docker Engine/CLI discovery story (that's N0.3's `docker_engine.py`, explicitly
  not touched here per the brief).

## 6. Follow-ups for Stage N1

1. Add `package_data`/`MANIFEST.in` entries (or migrate to `importlib.resources` reading from
   inside the package) so a wheel install ships `resources/` and `tit/blender/Electrode.blend`
   without requiring `TIT_RESOURCES_DIR` to be set externally.
2. Get access to a real Windows box (or a CI Windows runner) at least once before N1 ships, to
   turn every monkeypatched Windows-branch test in this lane into one real end-to-end run:
   spawn a job, cancel it mid-flight, confirm the process tree actually dies.
3. `roi_spec.py:232`'s `_mni_atlas_dir()`, `roi_picker.py:1203`'s `_mni_atlas_dir()`, and
   `opt/ex/buckets.py:49`'s `_RESOURCE_DIR` each independently reimplement a narrower version
   of the same "container path, else checkout-relative" fallback this lane centralized into
   `tit.paths.resolve_resource_path` -- worth converging onto the shared helper once those files'
   owning lanes are free (not touched here: none are in N0.6's owned paths).
4. Decide whether `tit/pre/utils.py`'s single-SIGTERM design and `tit/jobs/processes.py`'s
   snapshot-tree-then-SIGTERM/SIGKILL-escalate design should actually converge, now that both
   are correct independently -- today's split is a source-of-truth risk (two places encode "how
   to stop a process on Windows") even though neither is currently broken.
5. Podman/Colima/OrbStack support for the QSIPrep/QSIRecon Docker path (skeptic-3 claims #5,
   #10) remains completely unspiked -- the `--label` fix in this lane makes cancellation correct
   *for Docker Desktop/Engine*, but nothing here touches engine-compatibility.

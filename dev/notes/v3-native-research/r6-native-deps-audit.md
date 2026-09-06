# R6 — TI-Toolbox native dependency & platform audit

Scope: `tit` Python package + `desktop/` Electron shell in the worktree
`/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui`
(branch `feature/v3-electron-gui`). Question: can TI-Toolbox's own code run
natively (no container) on Linux/Windows/macOS, and what changes would that
take. Every claim below is tagged **VERIFIED** (I ran it / read the exact
line) or **REPORTED** (a comment/doc says it, not independently executed).

---

## 0. Headline finding

**`tit.server` + `tit.jobs` — the entire v3 orchestration layer — already
runs natively today, with no code changes.** I built a bare Python 3.11.14
venv on the macOS host (no simnibs, no Docker), installed only
`psutil fastapi uvicorn pydantic pyyaml numpy scipy jsonschema joblib
nibabel matplotlib pandas` (all of which ship full wheels for
macOS-arm64/win_amd64/manylinux-x86_64+aarch64), and:

- `python -m tit.server --project <dir> --host 127.0.0.1 --port 8799` started
  a working FastAPI/uvicorn server; `GET /api/health` → `{"status":"ok",...}`,
  `GET /api/capabilities` → live host probes. **VERIFIED**
  (`/private/tmp/.../scratchpad/native/tmp`, this session).
- The full `tit.jobs`/`tit.server` pytest suite — `test_jobs_manager.py`,
  `test_jobs_model.py`, `test_jobs_registry.py`, `test_jobs_routes.py`,
  `test_jobs_scheduler.py`, `test_server_skeleton.py`, `test_files_routes.py`,
  `test_plan_routes.py`, `test_runner_events.py`, `test_plan_leadfield_runner.py`,
  `test_runners_deserialize.py` — **277 passed, 0 failed** on this venv.
  **VERIFIED** (ran with `.venv/bin/python -m pytest`, this session).
- `tit.catalog`, `tit.jobs`, `tit.server`, `tit.tools` import with **zero**
  third-party deps beyond the stdlib. **VERIFIED**
  (`python -c "import tit.catalog"` etc., clean exit).
- `tit.analyzer`, `tit.pre`, `tit.pre.structural`, `tit.pre.dicom2nifti`,
  `tit.pre.qsi.utils`, `tit.stats` all import cleanly with only
  `numpy/scipy/nibabel/matplotlib/pandas/joblib` — **no simnibs import at
  module scope**. **VERIFIED**.
- Only `tit.sim`, `tit.opt` (flex/ex/mex), `tit.blender`, `tit.source` fail
  to import without SimNIBS/mne/bpy actually installed — and only because of
  a genuine SimNIBS-FEM dependency (see §1). **VERIFIED**.

This means the "project root is a host path" work and the numpy/scipy-only
config/planning/orchestration code are *already* container-agnostic; the
container boundary the v3 design still needs is narrowly the SimNIBS FEM
math itself (charm, TI field solve, flex/ex optimizers, mesh/EEG-forward
libraries), not the job server.

---

## 1. Native-readiness matrix

| Module | Imports cleanly w/o SimNIBS? | Extra deps needed | Native on Linux/Win/macOS? | Blocker |
|---|---|---|---|---|
| `tit.server` | Yes (verified) | `fastapi`, `uvicorn`, `pydantic`, `psutil`, `pyyaml` | **Yes, today** | `tit/jobs/runner.py:213` `signal.SIGKILL` — Windows-only crash (see §2a) |
| `tit.jobs` | Yes (verified) | `psutil` | **Yes, today** (macOS/Linux); Windows needs §2a/§2b fixes | same as above |
| `tit.catalog` | Yes (verified) | none (stdlib only) | **Yes, today** | none found |
| `tit.tools` (package init + `montage_visualizer`) | Yes (verified) | none for import; `montage_visualizer.py` shells out to ImageMagick `convert` (`tit/tools/montage_visualizer.py:214`) at runtime | Yes for import; `convert` must be on PATH to run | ImageMagick not bundled — needs install or vendored binary |
| `tit.reporting` | Yes (verified) | jinja/stdlib-ish; `base_generator.py:133` shells out to `dcm2niix -v` for a version string (best-effort, wrapped) | **Yes** | `dcm2niix` optional at runtime, not import |
| `tit.telemetry` | Yes (verified) | none for import; lazy `PyQt5` import only inside `_maybe_show_consent_dialog` (`tit/telemetry.py:652`) | **Yes** | none |
| `tit.stats` | Yes (verified, with numpy/scipy/nibabel/pandas/joblib) | `numpy scipy nibabel pandas joblib`; `h5py` referenced only in error strings, not imported at module scope | **Yes** — full wheel coverage all 3 OSes | none |
| `tit.pre` (`__main__`, orchestration) | Yes (verified) | `numpy scipy nibabel` | **Yes for orchestration**; actually *running* `charm`/`recon-all` needs SimNIBS/FreeSurfer binaries on PATH (`tit/pre/charm.py:102`, `tit/pre/recon_all.py:165`) | SimNIBS `charm` binary + FreeSurfer `recon-all` binary — see §3 |
| `tit.pre.structural`, `tit.pre.dicom2nifti` | Yes (verified) | `nibabel`; `dicom2nifti.py:365` shells out to `dcm2niix` | **Yes for orchestration**; `dcm2niix` binary must be on PATH to actually convert | `dcm2niix` is a small (~5 MB), MIT-licensed, native binary with prebuilt releases for linux/mac/win — easy to bundle |
| `tit.pre.qsi.*` | Yes (verified) | `shutil.which("docker")` gate (`tit/pre/qsi/utils.py:182`); silently degrades if docker absent | **Yes for orchestration**; the actual QSIPrep/QSIRecon run still needs Docker (DooD) | stays optional-Docker by design, see §3 |
| `tit.source` | **No** — `tit/source/forward.py:40` `import mne` at module scope | `mne` (pure-Python wheel, `mne-1.5.1-py3-none-any.whl`, 7.7 MB, **no C-extension** — verified via PyPI JSON) | **Yes** — mne itself has zero native-code blockers; only needs to be pip-installed | none real; today's `mne` import is unconditional even for the parts of `tit.source` that don't need it |
| `tit.analyzer` | Yes (verified, with nibabel) | `numpy scipy nibabel matplotlib`; `analyzer.py:1204/1234` shells to `dcm2niix`/related tools for some conversions; `tit/atlas/voxel.py:134` also shells out | **Yes** | same optional-binary pattern as `tit.pre` |
| `tit.sim` | **No** — `tit/sim/base.py:33` `from simnibs import run_simnibs, sim_struct` at module scope | full SimNIBS 4.6 install (compiled FEM solver, C++ core, ~2–3 GB with atlases/templates) | **Blocked** until SimNIBS ships native (non-Docker) desktop installers per platform | SimNIBS itself is the blocker, not `tit` |
| `tit.opt` (`flex`/`ex`/`mex`) | **No** — `tit/opt/ex/engine.py:15` `from simnibs.utils import TI_utils as TI`, imported eagerly by `tit/opt/ex/__init__.py:4`, which `tit/opt/__init__.py:53` imports unconditionally | full SimNIBS | **Blocked**, same reason | *Structural nit*: `tit/opt/config.py`'s `count_combinations`/`generate_current_ratios` (pure combinatorics, no FEM) are only reachable through `tit.opt.ex`, which drags in the full SimNIBS-dependent `ExSearchEngine` at import time — `tit/server/routes/plan.py:351-352` has to import them lazily inside a function body just to dodge this. Splitting the pure-math helpers out of `tit/opt/ex/engine.py` into a simnibs-free module would let `tit.server`'s "plan" endpoints answer without SimNIBS installed at all (today they're saved only by the fact that conftest.py mocks `simnibs` in tests). |
| `tit.blender` | **No** — `tit/blender/utils.py:15` `import simnibs` | full SimNIBS + `bpy` (both) | **Blocked on SimNIBS; bpy itself is native-installable, see §4** | Only reachable via `simnibs_python -m tit.blender config.json` subprocess from `tit/gui/extensions/visual_exporter.py:1158` — already an isolated subprocess boundary, same shape as `tit.jobs`' runner spawn |

**Bottom line for the matrix:** everything that is *not* `tit.sim`,
`tit.opt.*`, or `tit.blender` already runs on bare Python 3.11 with
ordinary PyPI wheels, on all three OSes, verified today. The SimNIBS-bound
third is where the real work is — and that work is bounded by SimNIBS's own
platform story (SimNIBS 4.6 ships native installers for Linux/macOS/Windows
already — https://github.com/simnibs/simnibs/releases — this was not
independently re-verified in this session beyond the Linux tarball URL
baked into `Dockerfile.simnibs:143`, **REPORTED** from that Dockerfile
comment, not fetched).

---

## 2. Code changes needed to drop the container-path model

### a. `tit/jobs/runner.py` — Windows process-tree kill is broken today

- `runner.py:86` `LocalPopenRunner.spawn()` passes `start_new_session=True`
  unconditionally. On Windows, CPython's `subprocess._execute_child`
  (Windows branch) receives this as `unused_start_new_session` and
  **silently ignores it** — verified by reading
  `/opt/homebrew/.../python3.14/subprocess.py:1450-1459` on this host (same
  code path across 3.11–3.14; Windows-only param is POSIX-only per the
  docstring at line 794). Not a crash, but it means the "own process group"
  isolation the code's own comment promises (`runner.py:69`) does not exist
  on Windows — a cancelled job's SIGTERM-equivalent has no group to target.
- `terminate_tree()` (`runner.py:213`) calls `proc.send_signal(signal.SIGKILL)`
  unconditionally. **`signal.SIGKILL` does not exist in the Windows build of
  Python's `signal` module** — this raises `AttributeError` at the point of
  use, before `psutil`/`_ignore_gone()` ever get a chance to catch it (the
  guard only catches `psutil.NoSuchProcess/AccessDenied/ProcessLookupError`,
  not `AttributeError`). Confirmed via WebSearch against multiple upstream
  bug reports (e.g. github.com/invoke-ai/InvokeAI#1288,
  github.com/ClearcodeHQ/mirakuru#215) — **REPORTED but high-confidence**
  (could not run an actual Windows interpreter in this sandbox to reproduce
  first-hand). psutil's own docs (per WebSearch of psutil.readthedocs.io)
  confirm the intended pattern: on Windows, `send_signal(SIGTERM)` is an
  alias for `TerminateProcess` (hard kill, no grace) and there is no
  `SIGKILL` equivalent to send — psutil expects callers to use
  `Process.kill()` instead.
- **Fix shape** (small, contained): mirror what `tit/pre/utils.py` already
  does correctly for the *other* runner (`_terminate_process` at
  `tit/pre/utils.py:364-375`, `start_new_session=(os.name != "nt")` at
  `tit/pre/utils.py:475`) — i.e. `tit/jobs/runner.py` needs the same
  `os.name`/`sys.platform` branch: `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP`
  on Windows instead of `start_new_session`, and replace the unconditional
  `signal.SIGKILL` with `proc.kill()` (psutil's cross-platform hard-kill) or
  an `os.name == "nt"` guard that skips straight to `terminate()`/`kill()`.
  This is a same-file, ~10-line change, not an architecture change — the
  POSIX-safe pattern to copy already exists in the same repo.

### b. Runner cwd / project-root model

- `tit/jobs/bootstrap.py:18` defaults `DEFAULT_RUNNER_CWD = "/ti-toolbox"`
  but **already** falls back to the project directory when that path
  doesn't exist (`bootstrap.py:39-42`, comment: *"Host/dev fallback:
  /ti-toolbox only exists inside the container"*) — **VERIFIED**, no change
  needed, this is already host-safe.
- `tit/server/settings.py:76` `resolve_project_dir` already documents and
  (by extension) implements a resolution order of `--project` →
  `TIT_PROJECT_DIR` → `LOCAL_PROJECT_DIR` (host-side) →
  `/mnt/<PROJECT_DIR_NAME>` (container-side) — **VERIFIED** by reading the
  docstring; this is the "host path vs container path" duality already
  built as a fallback chain, not a single hard assumption.
- `tit/paths.py:83-96` (`PathManager.project_dir` getter) still tries
  `const.DOCKER_MOUNT_PREFIX` (`/mnt`, `tit/constants.py:148`) as a
  fallback after `PROJECT_DIR`/env resolution fails — harmless on a host
  where `/mnt` doesn't exist (the `os.path.isdir` guard just fails closed),
  but it is dead weight in a pure-native deployment. Low-priority cleanup,
  not a blocker.
- Remaining literal `/ti-toolbox` and `/mnt/` path fragments are almost all
  in **docstrings/comments/GUI help text**, not executable path
  construction — e.g. `tit/tools/montage_visualizer.py:26`
  `_RESOURCES_DIR = "/ti-toolbox/resources/amv"` and
  `tit/atlas/constants.py:26` `MNI_ATLAS_DIR = "/ti-toolbox/resources/atlas"`
  **are** real hard-coded absolute paths (not docstrings) that assume the
  container's repo mount point — these two need a native equivalent (e.g.
  resolve relative to the installed package via
  `importlib.resources`/`Path(__file__).parent`, the same pattern
  `tit/config_io.py` already uses elsewhere for lazy resource resolution).
  **VERIFIED** as real code (not comments) at those two exact lines.
- `tit/blender/montage_publication.py:365`
  `electrode_template = "/ti-toolbox/tit/blender/Electrode.blend"` — same
  class of bug, real code, container-path literal. **VERIFIED**.

### c. Windows path-separator / case-sensitivity

- No `os.sep`-hardcoded string concatenation was found in `tit/jobs` or
  `tit/server` (grep for literal `/mnt/`, `/ti-toolbox` inside `tit/jobs`
  and `tit/server` returned only docstrings/comments, verified above) — the
  path-joining code that *is* live (`tit/paths.py`) uses `os.path.join`
  throughout, which is Windows-safe. **VERIFIED** by reading `tit/paths.py`
  in full (first ~120 lines shown above; the rest of the file was not
  fully re-read this session for every one of its ~700+ lines — spot check
  only).
- `tit/pre/qsi/utils.py:59-69` has an explicit `/mnt/` string-parse to
  translate a container-side path back to a host path for the DooD
  sibling-container bind mount — this logic is Docker-QSIPrep-specific
  (§3) and becomes a no-op/dead path in a pure-native deployment, not a bug
  to fix, since native mode never has a `/mnt/<project>` container path to
  translate in the first place.

### d. Config/user-data directories

- `tit/paths.py:221-230` (`get_user_config_dir`, roughly) already branches
  on `APPDATA` (Windows) / `XDG_CONFIG_HOME` (Linux) /
  `os.path.expanduser("~")+"/.config"` (macOS/Linux default) —
  **VERIFIED**, already cross-platform, no change needed.
- `tit/constants.py:872` `USER_CONFIG_CONTAINER_PATH = "/root/.config/ti-toolbox"`
  is explicitly the *container* value the Electron launcher bind-mounts
  onto — `tit/telemetry.py:111` documents it as the Docker-specific path
  and the paths.py logic above is the native fallback. **VERIFIED**, this
  is already a container/native dual-path design, not a single assumption.

---

## 3. What must stay optional-Docker

- **QSIPrep/QSIRecon** (`tit/pre/qsi/**`): DooD pattern —
  `tit/pre/qsi/docker_builder.py` builds `docker run` command lines against
  fixed container paths (`/data`, `/out`, `/work`,
  `/opt/freesurfer/license.txt` at `docker_builder.py:59`), gated at
  runtime by `shutil.which("docker") is None` →
  early-return/no-op (`tit/pre/qsi/utils.py:182`), and `tit/jobs/runner.py`'s
  `stop_docker_siblings()` (labels `tit.job_id=<id>`) is already written to
  degrade silently ("a host without a docker CLI... makes this a silent
  no-op", `runner.py:161-163`, comment **VERIFIED**). This is the pattern
  to keep exactly as-is: Docker becomes an *optional capability*
  (`/api/capabilities.docker_socket`, `tit/server/routes/capabilities.py:41`,
  **VERIFIED live** — this session's `curl` against the running server
  returned `"docker_socket":true"` correctly reflecting `/var/run/docker.sock`
  presence on this Mac), not a hard requirement, exactly mirroring how
  `gmsh`/`freeview`/`bpy`/`freesurfer`/`x11_display`/`jupyter` are already
  probed the same way in the same file. There is no reason to remove
  QSIPrep/QSIRecon from Docker — they are themselves gigabytes-large
  neuroimaging pipelines with their own heavy native dependencies (ANTs,
  FSL, MRtrix); porting *them* off Docker is out of scope for TI-Toolbox's
  own codebase.
- **Legacy FreeSurfer (`recon-all`, `freeview`)**: `tit/pre/recon_all.py:165`
  shells to the `recon-all` binary and `tit/gui/analyzer_tab.py:2585/2620`,
  `tit/gui/ex_search_tab.py:3440`, `tit/gui/components/roi_picker.py:1571/1615`
  all `subprocess.Popen(["freeview", ...])` — a ~1 GB+ compiled
  Linux/macOS-only binary distribution (no first-class Windows native
  build; FreeSurfer on Windows is WSL-only per FreeSurfer's own install
  docs — not independently re-verified this session, **REPORTED** from
  prior general knowledge, flagged for the maintainer to confirm before
  relying on it) with its own MATLAB Runtime dependency
  (`Dockerfile.freesurfer:38` `fs_install_mcr R2019b` — **VERIFIED**, adds
  another few-hundred-MB runtime). This is exactly the FreeSurfer/recon-all
  piece the maintainer's question calls out for a FastSurfer replacement —
  that evaluation is out of this lane's scope (R6 audits TI-Toolbox's own
  surface, not FreeSurfer alternatives) but the audit here confirms *why*
  it matters: `recon-all` and `freeview` are the only two pieces of the
  whole dependency graph that are unconditionally OS-restricted (no native
  Windows binary) and multi-hundred-MB-to-GB in size, everything else in
  this matrix (SimNIBS aside) is pip-installable on all three OSes.
- **`tit.pre.qsi.docker_builder`'s FreeSurfer license path assumption**
  (`docker_builder.py:59`, `/opt/freesurfer/license.txt`) is itself a
  container-path literal that would need resolving relative to wherever a
  native FreeSurfer/FastSurfer license lives — but again, only relevant if
  QSIPrep/QSIRecon (which need FreeSurfer's license for their own
  Docker-internal recon-all invocation) stay Docker-based, which per above
  they should.

---

## 4. Heavy optional deps — platform-wheel verification (PyPI JSON API)

| Package | Pinned/observed version | Wheel platforms (latest available at that pin or nearby) | Size | Verdict |
|---|---|---|---|---|
| `bpy` | 5.0.1 (Dockerfile installs unpinned `bpy`, but only `bpy-5.0.1` ships a `cp311` wheel — later 5.1.x/5.2.x require `cp313`; SimNIBS 4.6's own Python is 3.11, verified `docker exec tit-v3-spike ... Python 3.11.14`, so pip necessarily resolves to 5.0.1 for this stack) | `macosx_11_0_arm64` (228 MB), `manylinux_2_28_x86_64` (374 MB), `win_amd64` (328 MB), `win_arm64` (202 MB) — **no `manylinux_..._aarch64` wheel at any version checked (5.0.1 through 5.2.1)** | 200–400 MB per platform | Installable natively on macOS-arm64/Windows-x64/Windows-arm64/Linux-x64; **no Linux-ARM64 wheel** (irrelevant for typical x86_64 desktop Linux, relevant if targeting Linux ARM). Verified via `pypi.org/pypi/bpy/json`, this session. |
| `mne` | `~=1.5` pinned in `Dockerfile.simnibs` (comment: pinned to stay compatible with numpy 1.26.x) | `mne-1.5.1-py3-none-any.whl` — **pure Python, no compiled extension, `any` platform tag** | 7.7 MB | Zero native-code blocker on any OS. Verified via PyPI JSON. |
| `numba` | not a `tit` dependency — only used by SimNIBS's own bundled `tes_flex_optimization.py` (`resources/map-electrodes/tes_flex_optimization.py:1555/1557`, `from numba import set_num_threads`); zero `import numba` anywhere in `tit/` itself, verified by ripgrep | `numba-0.64.0` ships cp310–cp314 wheels for macosx-arm64, manylinux2014-x86_64, manylinux_2_27-aarch64, win_amd64 | 2.7–3.8 MB | Full cross-platform wheel coverage; not actually a `tit`-package concern, it's inside the vendored/patched SimNIBS optimizer. |
| `torch` | Listed in the maintainer's own container inventory (2.6.0+cpu) but **`rg -n "\btorch\b" tit/ resources/` returned zero matches** — no code in this repo (`tit/` or the patched `resources/`) imports `torch` | n/a (unused by this codebase) | n/a | **Not a TI-Toolbox dependency at all as far as this repo's own source goes.** If it's genuinely needed, it must be pulled in transitively by SimNIBS's own `pip install simnibs` requirements (not independently checked this session — would need `pip show simnibs` inside the container, not run due to time-box) — flag for the maintainer: confirm whether torch can simply be dropped from the image, or is a hard SimNIBS-core dependency. |
| `joblib` | used by `tit/stats/engine.py:21` (`Parallel, delayed`) | pure-Python, no wheel needed | tiny | No blocker. |
| `h5py` | referenced only in **comments/error strings** in `tit/opt/config.py:166/708/722` — no `import h5py` found anywhere in `tit/` via ripgrep | manylinux/macos/win wheels exist (HDF5 C library bundled) | ~3–5 MB | Appears unused at the Python level in this repo today (possibly a leftover reference, or used only inside vendored SimNIBS optimizer code, not verified further this session) — low risk either way, HDF5 has full 3-platform wheel coverage if it ever is needed. |
| `pandas` | used broadly (verified importable) | full 3-platform wheels | tens of MB | No blocker. |
| `PyQt5` | 57 references in `tit/`, but **all real (non-lazy, non-comment) imports are confined to `tit/gui/**`** plus one top-level import in `tit/project_init/first_time_user.py:11`; every reference outside `tit/gui/` that isn't a docstring/comment is a lazy `from PyQt5 import ...` inside a function body (`tit/telemetry.py:652`), never at module scope — **VERIFIED** `tit.server`/`tit.jobs` do not transitively import `tit.gui` or `first_time_user` (grep for both inside `tit/server` and `tit/jobs` returned nothing) | n/a — dropped in v3 per architecture docs | n/a | Confirmed cleanly excisable: v3's server/job layer has zero PyQt5 coupling today. |

---

## 5. Desktop-side (Electron) platform surface

- `desktop/src/main/x11.ts` (200 lines) — X11/XQuartz setup for the
  Freeview/Gmsh viewer windows tunneled through the container. Its own
  header comment says the viewer buttons are already gated server-side via
  `/api/capabilities.x11_display`, "never by anything in this module" —
  i.e. the code already treats X11 as an optional capability, not a hard
  requirement. This file becomes **dead code** once Tetravox replaces
  Freeview/Gmsh as the viewer (no more X11 tunnel needed at all).
  **VERIFIED** by reading the file header and `computeContainerDisplay`.
- `desktop/src/main/stack.ts` (247 lines) — Docker-stack lifecycle: attach
  or `compose up -d` a project-scoped stack, free-port/token/X11 setup,
  streaming pull/compose progress. This is exactly the piece
  `stack.start()` that a native (non-Docker) desktop build would replace
  with a **direct child-process spawn of the native SimNIBS/tit runtime**
  (analogous to what `tit/jobs/runner.py`'s `LocalPopenRunner` already does
  for job subprocesses — the same "spawn, track pid, health-check,
  terminate" shape, just applied to spawning `tit.server` itself instead of
  a `docker compose` stack). **VERIFIED** file exists and its role, exact
  native-replacement design not attempted this session (out of scope: this
  lane audits `tit`'s own dependency surface, not writes new Electron
  code).
- `desktop/src/main/dockerCli.ts` — **the dockerode replacement already
  exists**, and its own top-of-file comment says so explicitly: *"Docker
  discovery + compose lifecycle via the CLI (execa/execFile), never
  dockerode: the only thing the legacy launcher used the Engine API for was
  the GUI exec/hijack, which v3 does not need (TODO §2.9)."* **VERIFIED**
  — `dockerode` does not appear anywhere under `desktop/` (grep across
  `desktop/**/*.ts` and `desktop/package.json`, zero hits); it is only
  still present in the **legacy** `package/` tree
  (`package/src/backend/docker-manager.js`, `package/package.json`,
  `package/package-lock.json`), which is the pre-v3 GUI being replaced.
  This directly answers the maintainer's third question: the "better
  replacement for dockerode" they asked about has already been built in
  this branch, as a thin `execFile`-based CLI wrapper — there is no
  dockerode left to replace in the code path that matters.
- `desktop/package.json` — `"electron": "44.0.0"` in devDependencies; no
  `electron-builder` (or any packager) present yet — **VERIFIED**,
  cross-checked with `python3 -c "import json; ..."` against the file.
  Electron itself has always shipped Linux/Windows/macOS builds by design,
  so nothing here blocks a 3-platform target once a packager
  (electron-builder/electron-forge) is added — that step hasn't happened
  yet in this worktree.
- `@tetravox/engine`, `@tetravox/protocol`, `@tetravox/wasm` are already
  present in `desktop/package.json` as `file:vendor/tetravox/...` local
  package references — **VERIFIED**, Tetravox is already vendored into the
  desktop app's dependency tree, not merely planned.
- No `desktop/src/main/compose.ts` exists (the brief's expected filename);
  the equivalent shared compose-arg-building logic actually lives at
  `desktop/src/shared/compose.ts` (imported by both `dockerCli.ts` and
  `stack.ts`) — **VERIFIED**, corrected file location, same role as
  described (compose args, project naming, `buildStackEnv`, token
  generation).

---

## 6. Method notes / environment

- Host venv: Python 3.11.14 via `uv python install 3.11` (already present
  on this machine — **VERIFIED**, `uv python list` showed
  `cpython-3.11.14-macos-aarch64-none` pre-installed), created at
  `/private/tmp/claude-501/.../scratchpad/native/tmp/.venv` with
  `uv venv --python 3.11.14` (uv venvs ship without `pip`; used
  `uv pip install --python .venv/bin/python ...` throughout — `python -m
  pip` is absent by design in a `uv`-created venv, not a bug).
  System `python3` (Homebrew 3.14.3) was not used for the actual
  install/test run since `tit`/SimNIBS's ecosystem targets 3.11.
- Container checks used the already-running `tit-v3-spike` container
  (`idossha/simnibs:v2.5.0`, `docker ps` verified `Up 11 hours` at the
  start of this session) — only read-only `docker exec` calls were made
  (`which gmsh`, `which freeview`, `simnibs_python --version`,
  `simnibs_python -c "import numpy; print(numpy.__version__)"`); confirmed
  `gmsh` lives at `/root/SimNIBS-4.6/bin/gmsh` (bundled inside the SimNIBS
  installer tarball itself, not an apt/pip package — matches
  `Dockerfile.simnibs` having no `gmsh` apt package and no `gmsh` pip
  install line) and `freeview` is **absent** from the SimNIBS container
  (`which freeview` returned nothing) — it only exists in the separate
  `idossha/ti-toolbox_freesurfer:v7.4.1` image, reachable via the shared
  `freesurfer_data` volume + PATH setup the entrypoint presumably handles
  (entrypoint.sh was not read this session, time-boxed).
- No repository files were modified. All installs happened in the
  throwaway scratchpad venv; no `pip install` was run inside either
  worktree or against the container's own environment.

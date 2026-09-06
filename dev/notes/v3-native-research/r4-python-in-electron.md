# R4 — Bundling a private Python runtime + SimNIBS + tit inside Electron

Scope: how to ship `tit.server` (FastAPI) plus a full SimNIBS 4.6 Python environment as a
native child process inside an Electron app for Linux/Windows/macOS, signed and notarized —
no Docker, no X11. Every claim below is tagged **VERIFIED** (I ran the command / read the
file / fetched the URL myself, in this session) or **REPORTED** (a document says it and I did
not independently confirm it). Evidence is inline.

---

## 0. Bottom line

**Realistic, but not a weekend project, and it has one platform-shaped hole today: macOS
x86_64 (Intel).** Three separate SimNIBS runtime dependencies — `bpy`, `torch`, and SimNIBS's
own `petsc4py` fork — currently ship **zero** Intel-Mac wheels at the versions the container
pins (§4). Windows and Linux x86_64 and macOS arm64 are all solvable with evidence-backed
recipes below. The mechanical Electron-side work (extraResources, hardened runtime,
entitlements, signing every Mach-O in a multi-GB tree) is exactly the kind of thing this
codebase and its sibling project (Tetravox) already do correctly for a *small* signed payload
— it just needs to be pointed at a much bigger `resources/python/` tree, and the signing
script needs to walk that tree instead of trusting `--deep`.

The v3 architecture is not starting from zero: `tit.server` already speaks an HTTP+bearer-
token protocol that the Electron main process already drives through a generic
health-poll/attach contract (`health.ts`, VERIFIED below) — today aimed at a Docker container,
tomorrow aimed at a local child process with the exact same shape. That swap is the *easy*
part. The hard part is the SimNIBS dependency tree's platform coverage, not Electron.

---

## 1. Current baseline (VERIFIED — what exists in the repos today)

### 1.1 The v3 desktop app is 100% Docker today; no bundled-Python code exists yet

- `desktop/src/main/stack.ts` (`StackManager.doStart`) does: check Docker →
  `docker compose up -d` with env built by `buildStackEnv` (port, token, X11 display, project
  dir bind mount) → `waitForHealth(origin)` → save a stack record. There is no
  `child_process.spawn` of a local Python interpreter anywhere in `desktop/src/main/`.
  (VERIFIED: `Read` of
  `/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/desktop/src/main/stack.ts`)
- `desktop/docker/docker-compose.v3.yml` is the actual launch command for `tit.server` today:
  ```
  command: >-
    bash -lc "simnibs_python -m pip install --quiet fastapi 'uvicorn[standard]' pyyaml psutil ... &&
    exec simnibs_python -m tit.server --project /mnt/${PROJECT_DIR_NAME} --host 0.0.0.0
    --port ${TIT_SERVER_PORT} --static-dir ${TIT_STATIC_DIR:-/opt/ti-toolbox/ui}"
  ```
  with `environment: { KMP_AFFINITY: "disabled", TIT_SERVER_TOKEN, TIT_SERVER_PORT, ... }`.
  (VERIFIED, file read in full.) **This is the exact CLI + env-var contract a native spawn
  must reproduce**: `python -m tit.server --project <dir> --port <p> --static-dir <ui>`, token
  via `TIT_SERVER_TOKEN` env or `--token`, `KMP_AFFINITY=disabled` set (the container's own
  Dockerfile comment says why: *"Avoid OpenMP affinity crash during postinstall"* —
  `container/blueprint/Dockerfile.simnibs` line ~118, VERIFIED).
- `tit/server/settings.py` (`ServerSettings`, `resolve_token`, `resolve_project_dir`) already
  resolves `--project`/`TIT_PROJECT_DIR`, `--token`/`TIT_SERVER_TOKEN` (or generates one with
  `secrets.token_urlsafe(32)`), `--static-dir`/`TIT_STATIC_DIR`. (VERIFIED, file read in full.)
  A native launcher only needs to generate a free port + token exactly as `stack.ts` already
  does (`findFreePort`, `generateToken`) and pass them as argv/env to a local process instead
  of into `docker compose`.
- `desktop/src/main/health.ts`: `waitForHealth(origin)` polls `GET /api/health` every 500 ms
  up to 15 s and expects `{status:"ok"}`; `checkToken(origin, token)` does a bearer `GET
  /api/version` and treats HTTP 401 specially. (VERIFIED, file read in full.) This is
  transport-agnostic — it already works identically whether `origin` is a Docker-published
  port or a locally-spawned process's port. **No redesign needed here, only a new "spawn a
  local process" branch parallel to `stack.ts`'s "spawn a docker compose" branch.**
- `desktop/package.json` **already vendors Tetravox** as local file deps: `@tetravox/engine`,
  `@tetravox/protocol`, `@tetravox/wasm` under `file:vendor/tetravox/{engine,protocol,wasm}`,
  with a `vendor/tetravox/VENDORED.md` and `LICENSE`. (VERIFIED:
  `ls /Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/desktop/vendor/tetravox/`)
  This is *ahead* of what `tracks/active/v3-electron-gui.md` row 3 states ("Freeview and Gmsh
  stay in the container on X11 for 3.0 … retire the viewers gradually" — VERIFIED, file read)
  — the Tetravox-replaces-viewers migration the maintainer is asking about here is already
  under way in this worktree, not a future 4.0 idea.
- **No `electron-builder` config exists yet for the v3 `desktop/` app** — no
  `electron-builder.yml`, no `build` key in `desktop/package.json` (VERIFIED:
  `grep -n "electron-builder" desktop/package.json` → only the `electron-vite build` script
  matched; `find desktop -iname "electron-builder*"` found nothing). Packaging is a green
  field for v3; it does not need to be reconciled with an existing broken config.

### 1.2 Two working electron-builder configs already exist in sibling projects to copy from

**Legacy TI-Toolbox launcher** (`/Users/idohaber/01_production/TI-toolbox/package/`, MIT
licensed Electron shell that drives Docker via `dockerode`) — VERIFIED, files read in full:
- `package.json` `build` block: `hardenedRuntime: true`, `entitlements:
  build/entitlements.mac.plist`, `afterSign: build/notarize.js`, `asarUnpack:
  ["docker/**/*"]`, targets `dmg`/`nsis`/`AppImage+deb`.
- `build/entitlements.mac.plist`: exactly the four entitlements a bundled-Python runtime
  needs — `com.apple.security.cs.allow-jit`, `allow-unsigned-executable-memory`,
  `disable-library-validation`, `allow-dyld-environment-variables`. (These match what a
  WebSearch of Apple Developer Forum threads on notarizing bundled Python/conda dylibs
  independently recommends — see §5.3.) This file can be reused verbatim.
- `build/notarize.js`: a 25-line `@electron/notarize` `afterSign` hook reading
  `APPLE_ID`/`APPLE_APP_SPECIFIC_PASSWORD`/`APPLE_TEAM_ID` from env, no-ops if absent.

**Tetravox** (`/Users/idohaber/00_development/tetravox/`) — VERIFIED, files read in full —
is the more complete and more current reference, and is explicitly the template the v3 team
already looks to (it is already vendored into `desktop/`). Its
`packages/app/electron-builder.yml` + `scripts/electron-builder.sh` +
`.github/workflows/release.yml` together are a fully worked, heavily-commented example of:
- **The signed/unsigned split lives in a shell script, not two config files**: `mac:
  hardenedRuntime: true` always in `electron-builder.yml`; `scripts/electron-builder.sh`
  detects `CSC_LINK` at build time and, when absent, passes
  `--config.mac.hardenedRuntime=false --config.mac.notarize=false` on the CLI plus
  `CSC_IDENTITY_AUTO_DISCOVERY=false`, with an explicit comment explaining *why*: an
  ad-hoc-signed arm64 build with `hardenedRuntime:true` is "an app the kernel kills at
  launch" (that line is itself a documented, presumably-hard-won fact worth trusting).
- **Build matrix** (`release.yml`): macOS arm64 *and* x64 dmg+zip built from **one**
  `macos-latest` runner (`electron-builder.yml`'s `mac.target` lists both arches; `wine` is
  not needed because signing never touches Windows and `nsis` uses a downloaded native
  `makensis`); Linux x64 AppImage+deb+tar.gz from `ubuntu-24.04`; Windows nsis x64 from
  `windows-latest`, marked `required: 'no'` / `continue-on-error: true` — Windows is
  explicitly a best-effort leg in this sibling project, worth noting as a precedent if v3
  wants the same posture initially.
- **Verified-then-published release gate**: `create-release` (draft) → per-OS `build` jobs
  attach assets to the still-draft release → `verify` job asserts every required asset
  filename is present, *then* flips `draft:false`. A release is never publicly "latest" with
  a missing platform.
- **Notarization credential pre-flight**: a dedicated step runs `xcrun notarytool history`
  *before* the full build, specifically to fail fast rather than burn a bad password against
  Apple's account-lockout counter — the file's own comment cites a real incident: *"Three of
  those in a row on 2026-08-29 locked the account (`HTTP status code: 401 ... has been
  locked`)"*. Worth carrying into a v3 pipeline verbatim.
- **Post-build verification**: `codesign --verify --deep --strict`, `spctl -a -vv -t install`
  checked for `Notarized Developer ID` in output, `stapler validate` on the dmg — i.e. the
  build fails itself if notarization silently didn't stick, rather than shipping and finding
  out from a user's Gatekeeper block.

None of Tetravox's config bundles a Python runtime (it is pure Rust/WASM + Electron), so it
is a template for the *signing/CI mechanics*, not for `extraResources`/Python-specific
entitlements — that half comes from SimNIBS's own installer (§2) and the legacy launcher's
entitlements file (§1.2 above).

### 1.3 SimNIBS's own official installer (VERIFIED — read in full)

`/Users/idohaber/01_production/simnibs/packing/pack.py` + `install` +
`macOS_installer/{postinstall,Distribution,welcome.html,conclusion.html}` is the *exact*
mechanism that already produces `simnibs_installer_{linux,macos,windows}` today (the same
artifact `container/blueprint/Dockerfile.simnibs` downloads:
`https://github.com/simnibs/simnibs/releases/download/v4.6.0/simnibs_installer_linux.tar.gz`,
VERIFIED in that Dockerfile). It is `conda_pack.pack()`-based, not conda-constructor, not
PyInstaller:

1. `conda_pack.pack(name=env_name, ..., compress_level=0)` tars a pre-built, named conda env
   (or a temporary one created from a `.yml` + a SimNIBS wheel) into `simnibs_env.tar`.
2. Unpacked, then `fix_entrypoints.py` rewrites the shebang embedded in every distlib-style
   `.exe`/console-script launcher (pip's own entrypoint format hardcodes an absolute
   interpreter path at wheel-install time; `conda-pack` moves the tree, so every entrypoint's
   embedded shebang must be binary-patched post-move — this is real, fiddly work already
   solved and available to reuse, not something to reinvent).
3. **Per-OS packaging differs sharply**:
   - **Windows**: NSIS installer via `packing/installer.nsi`, `makensis.exe`. No signing logic
     in `pack.py` for Windows at all (Windows needs no signature to run — SmartScreen just
     warns until enough installs accrue reputation).
   - **macOS**: `pkgbuild` + `productbuild` producing a `.pkg`. **The notable finding**: rather
     than code-signing every binary in a multi-GB conda env, `pack.py` **zips the entire
     `simnibs_env` directory with a password** (`zip -y -q -P password -r simnibs_env.zip
     simnibs_env`) *before* `pkgbuild` runs, and the `postinstall` script unzips it on the
     user's machine after install (`unzip -q -P password -o "$2/simnibs_env.zip" -d "$2"` then
     `conda-unpack` then `fix_entrypoints.py` again). The CLI help text in `pack.py` itself
     admits the reason: `--macos-developer-id` "DOES NOT SUPPORT NOTARIZATION (optional)" —
     i.e. **SimNIBS's own shipped macOS installer is not (fully) notarized**; the password-zip
     is a documented-in-code workaround (`pack.py` comment: *"Workaroud for Notarization /
     Instead of signing all binaries, I zip the enironment with a password / The postinstall
     script will unzip it"*) that hides the payload from Gatekeeper's/notarytool's binary scan
     rather than satisfying it. **This is strong first-party evidence that even SimNIBS's own
     maintainers found "sign every Mach-O in a huge conda env" hard enough to route around it**,
     and it is a trap to avoid copying: an app that ships this way will fail Gatekeeper on a
     clean machine (no stapled ticket) unless Electron's own signed/notarized `.app` wrapper is
     what the user actually double-clicks, with the Python payload inside `Resources/` merely
     *inheriting* trust from the outer bundle rather than being independently gatekept — which
     is exactly the `extraResources` + walk-and-sign-everything-inside approach recommended in
     §5.3, not SimNIBS's zip trick.
   - **Linux**: a `.tar.gz` + a POSIX `install` shell script (no package manager integration,
     no signing).

**Measured size of what this actually produces** (VERIFIED, `docker exec tit-v3-spike`,
`idossha/simnibs:v2.5.0`, which is this exact conda-packed env baked into the container image
per `Dockerfile.simnibs`):

```
4.6G  /root/SimNIBS-4.6                                     (full env root: bin/, lib/, share/, include/…)
3.5G  .../simnibs_env/lib/python3.11/site-packages           (Python packages only)
```
Top offenders inside `site-packages` (`du -sh */ | sort -rh`, VERIFIED):

| Package | Size | Note |
|---|---|---|
| `bpy` | 821M | Blender-as-a-library; used for mesh ops |
| `torch` | 715M | `torch==2.6.0+cpu`, required by `BrainNet`/`BrainSynth`/`pytorch-ignite` (SimNIBS's charm neural-net segmentation — `pip show torch` `Required-by`, VERIFIED) |
| `simnibs` | 393M | core package incl. `external/bin/linux/*` compiled binaries, see §4.3 |
| `PyQt5` (+`PyQt5-Qt5`) | 202M | the legacy GUI toolkit — **droppable in a v3 headless-server build**, `tit.server` doesn't need it |
| `llvmlite` | 162M | numba's LLVM JIT backend |
| `sympy` | 79M | torch transitive dep |
| `pandas` | 76M | |
| `scipy` | 72M | |
| `samseg`/`brainnet`/`brainsynth` | 65M/60M/35M | charm segmentation net weights/code |
| `sklearn` | 49M | |
| `petsc4py`(+`.libs`) | 46+37M | FEM solver bindings, see §4.2 |
| `numpy`(+`.libs`) | 42+37M | |
| `numba` | 34M | |
| `jupyterlab` | 23M | dev tool — droppable |
| `debugpy` | 18M | dev tool — droppable |

Dropping `PyQt5` + `jupyterlab` + `debugpy` (all present only because
`Dockerfile.simnibs`'s `pip install` line explicitly adds `python-lsp-server`/
`jupyterlab-lsp` for the container's interactive dev workflow, and SimNIBS itself pulls in
`PyQt5` for its own GUI — VERIFIED, Dockerfile read in full) saves ~240 MB and is a real,
low-risk trim for a v3 desktop build where `tit.server` is headless and Jupyter/LSP are
out of scope. `bpy` (821M) and `torch` (715M) together are 44% of `site-packages` and are not
safely droppable — `torch` feeds SimNIBS's own charm segmentation (not a `tit`-side choice),
and `bpy` is used by `tit`/SimNIBS mesh tooling; neither is this lane's call to remove.

---

## 2. Runtime bundling strategy: three options, compared with evidence

### 2.1 python-build-standalone (astral-sh/python-build-standalone) + pip wheels

**VERIFIED** (`GET https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest`,
tag `20260901`, 871 assets): ships `cpython-3.11.16+20260901-<triple>-install_only.tar.gz` for
`aarch64-apple-darwin`, `x86_64-apple-darwin`, `x86_64-pc-windows-msvc`,
`aarch64-pc-windows-msvc`, `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu` — i.e. a
**full match** to the four legs this task's build matrix needs (macOS arm64/x64, Windows x64,
Linux x64), at Python 3.11, matching the container's pinned `3.11.14` (VERIFIED:
`docker exec tit-v3-spike simnibs_python -c "import sys;print(sys.version)"` →
`3.11.14 | packaged by conda-forge`). `install_only` builds are relocatable, standard-ABI
CPython — `pip install` of manylinux/macosx/win wheels against them works exactly as against
python.org CPython (this is the mechanism `uv`/`rye` rely on; not independently re-verified
in this session beyond confirming the artifact exists and its naming, but it is a very
widely-relied-on, actively maintained project — the release cadence, `20260901`, is
essentially weekly).

**The catch is not the interpreter, it's the packages** (§4): a plain
"`python-build-standalone` interpreter + `pip install` every wheel from PyPI" pipeline breaks
down for at least `bpy` (no manylinux aarch64, no macOS x86_64 at the pinned version),
`torch` (no macOS x86_64 at 2.6.0), and `petsc4py` (**zero** wheels on PyPI at any version
ever — VERIFIED below). This option is real and light (no conda runtime overhead, ~30 MB
interpreter) but needs a **non-PyPI wheel source** for `petsc4py` specifically (SimNIBS
already solved this — see §4.2) and a version pin strategy for `bpy`/`torch` on Intel Mac
that may not have a clean answer (§4.1).

### 2.2 conda-pack / micromamba-bundled env (SimNIBS's own approach)

This is what SimNIBS itself ships (§1.3), and it is the only approach in this comparison that
has already been proven, end-to-end, against this *exact* dependency set (`bpy`, `torch`,
`petsc4py`, `mumps`, CGAL bindings, etc.) on all three OSes — because it's how the container
image itself was built. Trade-offs, evidence-based:

- **Pro**: conda-forge (or SimNIBS's own channel, §4.2) has working builds of the hard C/
  Fortran-heavy packages (`petsc4py`, `mumps`, CGAL) on platforms where PyPI has none at all.
  `conda-pack`'s shebang-relocation problem is already solved in this codebase
  (`fix_entrypoints.py`) and battle-tested.
- **Con**: `conda-pack` ships every `.so`/dylib the env resolved, including large transitive
  runtime libs (MKL, OpenBLAS, Qt if not pruned) that a curated pip-wheel set would not pull
  in; measured env root (4.6G) vs. `site-packages` alone (3.5G) shows ~1.1G of exactly this
  kind of non-Python payload (VERIFIED, §1.3) — some of it (shared libs actually linked by
  `.so` extensions) is required, some (headers under `include/`, static libs) is pure waste
  that a bundling script should explicitly strip.
- **Con**: a packed conda env is a worse fit for Electron's `asar`+`extraResources` model than
  a pip-installed venv, because conda-pack's own unpack step (`conda-unpack`) rewrites
  prefixes at *install* time, which collides with `asar`'s read-only archive semantics —
  it must land in `asarUnpack`/`extraResources` as a plain directory, never inside `asar`
  itself (true of *any* Python runtime, not conda-specific, but conda-pack's relocation script
  makes the "never touch this after unpacking, treat it as generated output" boundary sharper
  to get right).

**Recommendation**: use conda-forge/micromamba (or SimNIBS's own petsc4py wheels directly
into a `python-build-standalone` interpreter — see §6) specifically *because* it is the only
source that has ever built `petsc4py` for win-64 and macOS, not out of general preference for
conda over pip.

### 2.3 PyInstaller / Nuitka freezing — evidence it is not viable here

The task brief asks this claim be verified, not assumed. Evidence gathered this session,
**against this exact codebase**:

- **SimNIBS spawns its own compiled binaries as subprocesses**, referenced by paths relative
  to the installed package, not embedded via Python import machinery that a freezer's static
  analysis can see: `/root/SimNIBS-4.6/bin/{meshfix,mmg3d_O3,dwi2cond}` are **symlinks into**
  `simnibs_env/.../site-packages/simnibs/external/{bin/linux/*, dwi2cond}` (VERIFIED:
  `ls -la /root/SimNIBS-4.6/bin/` inside `tit-v3-spike`). `external/bin/linux/` itself
  contains `CAT_Surf2Sphere`, `CAT_WarpSurf`, `meshfix`, `mmg3d_O3`, and — tellingly — a
  **vendored `libstdc++.so.6`** (9.5 MB, VERIFIED `ls -la`) shipped *inside the Python
  package* so these binaries don't depend on the host's C++ runtime. A `--onefile`
  PyInstaller/Nuitka freeze extracts bundled *data* files to a temp dir at every launch
  (`_MEIPASS`-style), and package-relative subprocess calls like these need to resolve
  correctly post-extraction — solvable, but exactly the class of bug PyInstaller/napari users
  hit repeatedly (see the Image.sc forum thread on packaging napari via PyInstaller, cited
  §2.4) and the reason `fix_entrypoints.py`/conda-pack's relocation script exists in the first
  place: this problem is already known and already solved for the conda-pack path, not for a
  fresh freezer.
- **Compiled Cython/C extension modules inside the package** (VERIFIED, `find … -name "*.so"`
  inside `simnibs/`, 7 hits): `segmentation/_thickness.cpython-311-x86_64-linux-gnu.so`,
  `_sanlm...so`, `_marching_cubes_lewiner_cy...so`, `mesh_tools/cython_msh...so`,
  `mesh_tools/cgal/{cgal_misc,create_mesh_surf,create_mesh_vol}...so`. Freezers handle single
  `.pyd`/`.so` extension modules fine in the common case, but this combination — Cython
  extensions *and* subprocess-spawned sibling binaries *and* a vendored shared library *and*
  a JIT compiler (`numba`/`llvmlite`, which generates and executes machine code at runtime,
  needing `com.apple.security.cs.allow-unsigned-executable-memory` on hardened-runtime macOS —
  same entitlement already present in the legacy launcher's plist, §1.2) — is precisely the
  profile PyInstaller/Nuitka handle worst, because their whole model is static analysis of
  Python `import` statements plus a hook system for known-tricky packages; `torch`, `scipy`,
  `numba`, `bpy` all need PyInstaller "hooks" that are perpetually chasing upstream releases,
  and a package doing its *own* subprocess/dlopen tricks below Python's import machinery (as
  here) isn't discoverable by static analysis at all.
- **Independent precedent — napari's own packaging history** confirms this pattern generalizes
  beyond SimNIBS: napari (a comparably heavy scientific-Python desktop app: Qt + numpy/scipy +
  GPU rendering) **tried PyInstaller and moved away from it**, to `constructor`
  (conda-based bundling) specifically for bundling robustness — REPORTED via WebSearch,
  https://napari.org/dev/naps/2-conda-based-packaging.html and
  https://labs.quansight.org/blog/napari-conda-constructor-menuinst : *"Conda packages offer
  several advantages when it comes to bundling dependencies, since it makes very few
  assumptions about the underlying system installation"*; a related Image.sc forum thread
  (`forum.image.sc/t/packaging-napari-app-through-pyinstaller/42100`) documents years of
  community struggle with exactly this. This is not proof PyInstaller can never work for a
  SimNIBS-class app, but it is direct precedent from the closest comparable open-source
  project, and its resolution (conda-based bundling, not a freezer) agrees with §2.2's
  recommendation.

**Verdict**: PyInstaller/Nuitka are not recommended. The `python-build-standalone`-interpreter
+ curated-wheels-and-conda-extracted-binaries approach (§6) or full conda-pack (§2.2) are both
viable; a single-file freeze is not, on the specific evidence above (subprocess binaries,
Cython extensions, JIT, vendored shared libs).

### 2.4 Electron + Python sidecar precedent (Tauri, not Electron, but the pattern transfers)

REPORTED via WebSearch (no first-party TI-Toolbox/Tetravox precedent exists — Tetravox has no
Python inside it at all, VERIFIED by reading its `Cargo.toml`/`package.json`/`electron-
builder.yml` in §1.2, none reference a Python runtime). Tauri's documented "sidecar" pattern
(`v2.tauri.app/develop/sidecar/`, `tauri-apps/tauri` discussion #2759) is structurally the
same problem Electron's `extraResources` solves: an `externalBin` array names a binary by
base name, and the bundler appends the *target triple* (`python-x86_64-unknown-linux-gnu`,
`python-aarch64-apple-darwin`, …) — i.e. **per-platform binary directories keyed by Rust-style
target triple**, the same shape `python-build-standalone`'s own release artifacts already use
(§2.1). This is a useful naming convention to copy into `electron-builder`'s
`extraResources[].from` per-platform paths even though Electron itself has no built-in
triple-keying (§5.1 shows how `electron-builder` config does this with per-OS blocks
instead). Community discussion in the same thread confirms the common pattern is exactly
"PyInstaller-compile the Python app, then sidecar the resulting binary" — i.e. even in the
Tauri ecosystem, people reach for PyInstaller for *small* Python helper scripts, not for
SimNIBS-scale scientific stacks; nothing found contradicts §2.3.

---

## 3. Electron packaging mechanics (VERIFIED patterns to reuse)

### 3.1 `extraResources` + `asarUnpack`

Both existing configs already use `extraResources` for large non-JS payloads that must stay
as real files on disk (Docker compose files in the legacy launcher, `resources/` in Tetravox
— VERIFIED, §1.2). The same mechanism is the right one for `resources/python/<triple>/…`: a
multi-GB Python tree must never go through `asar` packing at all (perf and the conda-unpack
prefix-rewrite problem, §2.2) — `extraResources` copies it as a plain directory next to the
app, which is exactly what `asarUnpack` would otherwise be needed to simulate for anything
placed under `files`. Recommendation: put the Python tree under `extraResources`, not
`files`+`asarUnpack`, so it is never asar'd in the first place (simpler than unpacking after
the fact, and avoids `asar`'s path-length and symlink quirks on Windows, which matter for a
tree containing conda's characteristic `Lib/site-packages/*.dist-info` symlink farms).

### 3.2 macOS hardened runtime, entitlements, signing every Mach-O

- Confirmed entitlements set (§1.2, legacy launcher's `entitlements.mac.plist`, reused
  verbatim): `allow-jit`, `allow-unsigned-executable-memory`, `disable-library-validation`,
  `allow-dyld-environment-variables`. WebSearch corroboration (Apple Developer Forum threads,
  `developer.apple.com/forums/thread/{129631,737603,725061,721410}`; a python.org packaging
  blog post `haim.dev/posts/2020-08-08-python-macos-app`): *"Apple recommends not deep-sign,
  but in the case of bundled Python libraries, it's actually required as all the bundled
  Python libraries do need to be signed, not just your main binary"* and *"`--deep`
  Considered Harmful"* (an Apple DTS engineer's own guidance, quoted in the pyinstaller
  mailing list thread found). **Net instruction, consistent across every source found**: do
  not rely on `codesign --deep` (electron-builder does not use it either — it walks the
  bundle itself); write a small pre-notarization script that `find`s every `*.dylib` / `*.so`
  / Mach-O executable under `resources/python/` and `codesign --sign <id> --options runtime
  --timestamp` each one, innermost-first, *before* signing the outer `.app` — this is
  additional work `electron-builder`'s default signing step does not do for you today (it
  signs the app bundle and whatever it walks under `Contents/`, but a `python -m pip install`
  tree with hundreds of `.so`/`.dylib` files across `torch`, `scipy`, `numpy.libs`,
  `petsc4py.libs` etc. is exactly the scale where this needs to be scripted and verified, not
  assumed). `electron-builder`'s `afterSign` hook (already used for `@electron/notarize` in
  both existing configs, §1.2) is the right place to run such a walk-and-sign script *before*
  calling `notarize()`.
- **Real cost**: notarization submits the whole app for Apple's scan; a tree with `bpy`
  (821M) + `torch` (715M) + everything else (§1.3) turns into hundreds to low thousands of
  individual Mach-O binaries to sign and a notarization submission in the multi-GB range —
  slower uploads, more surface area for one missed/expired signature to fail the whole
  submission. Tetravox's own release workflow (§1.2) already treats notarization as slow and
  fragile enough to warrant a credential pre-flight step and account-lockout warning from a
  real incident; that risk compounds with tree size.

### 3.3 Windows — no signing required to run, SmartScreen only

REPORTED/inferred from Tetravox's own comment (`electron-builder.yml`: *"Windows: `nsis` x64
only, and unsigned … Only signing would need wine, and there is none"*) and the legacy
launcher's `nsis` block (no code-signing keys referenced in its `build` config at all,
VERIFIED, §1.2). A native-Python Windows build needs no Mach-O-style per-file signing
concern; the practical issue is purely SmartScreen reputation on first install (cosmetic, not
a build blocker) and file count — Windows Defender / some corporate AV can be slow scanning a
multi-GB `python/` tree on first run, worth flagging as a support-ticket risk, not a build
risk.

### 3.4 Linux AppImage — glibc floor

Not independently re-verified with a version-pinned check this session, but corroborated
structurally: `container/blueprint/Dockerfile.simnibs`'s SimNIBS install downloads
`simnibs_installer_linux.tar.gz` onto `ubuntu:22.04` (glibc 2.35) (VERIFIED, Dockerfile
`FROM ubuntu:22.04` + the wget/tar/install lines), and `python-build-standalone`'s Linux
artifact is tagged `x86_64-unknown-linux-gnu` (glibc-linked, not musl) (VERIFIED, §2.1 asset
listing). An AppImage built from a GitHub Actions `ubuntu-24.04` runner (glibc 2.39) risks
raising the effective glibc floor above what some users' distros ship — the standard AppImage
mitigation is building on the *oldest* supported glibc (traditionally `ubuntu-22.04` or an
even older base image), which the desktop app's own AppImage leg should target explicitly
rather than inheriting whatever `ubuntu-latest` happens to be that month. Tetravox's own CI
already pins `ubuntu-24.04` explicitly rather than `ubuntu-latest` (VERIFIED,
`release.yml`) — the same discipline, applied to an *older* base, is the right lesson to
carry over given the much heavier native-extension payload here (SimNIBS's compiled `.so`s
and vendored `libstdc++.so.6`, §2.3, vs. Tetravox's own Rust binary which is far more
glibc-portable by nature).

---

## 4. Cross-platform package-availability audit (VERIFIED — the centerpiece finding)

Checked via the PyPI JSON API (`GET https://pypi.org/pypi/<pkg>/json`) and the conda.anaconda.org
/ api.anaconda.org APIs, against the exact versions the container has installed today
(`docker exec tit-v3-spike simnibs_python -m pip list`, VERIFIED):
`bpy==5.0.1`, `torch==2.6.0+cpu`, `petsc4py==3.22.2`, `numba==0.64.0`, `llvmlite==0.46.0`.

### 4.1 `bpy` and `torch` both dropped macOS x86_64 (Intel) wheels

- `bpy` PyPI release history (VERIFIED, full release list fetched): every 4.2.x–4.5.x release
  shipped `macosx_11_0_x86_64` *and* `macosx_11_0_arm64`; **starting at `bpy==5.0.0`, the
  `macosx_11_0_x86_64` wheel is gone** — 5.0.0, 5.0.1 (the container's pin), 5.1.x, 5.2.1 all
  ship only `macosx_11_0_arm64`, `manylinux_2_28_x86_64`, `win_amd64`(+`win_arm64` from 4.4.0
  on). **No Linux arm64 wheel at any version checked either**, but that's outside this task's
  matrix (Linux leg is x86_64 only).
- `torch==2.6.0` (VERIFIED, full wheel list for that exact release): `macosx_11_0_arm64`,
  `manylinux1_x86_64`, `manylinux_2_28_aarch64`, `win_amd64`. **No macOS x86_64 wheel.**
  (Consistent with PyTorch's well-known 2.3+ policy of dropping Intel-Mac wheels — not
  independently re-verified against PyTorch's own release notes this session, but the direct
  PyPI JSON evidence stands on its own regardless of the reason.)

### 4.2 `petsc4py`: zero PyPI wheels ever, zero conda-forge win-64 builds — but SimNIBS ships its own fork with wheels for exactly the platforms that need them, **except macOS x86_64**

This was the most consequential single finding, verified end-to-end:

1. PyPI `petsc4py` has **never published a wheel** — every release back to 3.3.1 is
   sdist-only (`petsc4py-X.Y.Z.tar.gz`) (VERIFIED, full release-file listing from PyPI JSON).
   Building PETSc from source needs a Fortran+C toolchain and MPI and is notoriously hard on
   Windows in particular.
2. conda-forge's own `petsc4py` package has **zero win-64 builds**: querying
   `api.anaconda.org/package/conda-forge/petsc4py/files` and filtering `attrs.subdir==win-64`
   returns 0 files, vs. 2849 for `linux-64`, 1667 for `osx-64`, 1062 for `osx-arm64`
   (VERIFIED). Independently corroborated by a real upstream issue found via WebSearch:
   `github.com/conda-forge/petsc4py-feedstock/issues/98`, *"petsc4py not available on
   Windows"*.
3. **SimNIBS solved this by shipping its own fork**: `github.com/simnibs/petsc4py`
   (VERIFIED via `GET api.github.com/repos/simnibs/petsc4py/releases`, all 4 releases listed):
   ```
   v3.24.2:  petsc4py-3.24.2-cp311-cp311-macosx_14_0_arm64.whl                       (only)
   v3.23.2:  macosx_14_0_arm64 + manylinux_2_28_x86_64 + win_amd64
   v3.22.2:  macosx_14_0_arm64 + manylinux_2_28_x86_64 + win_amd64   ← matches the container's exact pin
   v3.21.5:  macosx_14_0_arm64 + manylinux_2_28_x86_64 + win_amd64
   ```
   The container's `petsc4py==3.22.2` (VERIFIED, `pip show petsc4py`) matches
   `simnibs/petsc4py` release `v3.22.2` exactly — this **is** where SimNIBS's own installer
   sources its Windows and Linux petsc4py wheels from (not PyPI, not conda-forge). This is a
   directly reusable, low-risk answer for R4's Windows leg: point `pip install` at
   `https://github.com/simnibs/petsc4py/releases/download/v3.22.2/petsc4py-3.22.2-cp311-cp311-win_amd64.whl`
   (or whatever version is current when this is built) instead of PyPI for this one package.
   **But note it confirms, a third time over, that macOS x86_64 has no wheel here either** —
   `simnibs/petsc4py`'s own releases only ever built `macosx_14_0_arm64`.

### 4.3 Net effect: macOS x86_64 (Intel) is a real, three-deep blocker at current pins

`bpy`, `torch`, and SimNIBS's own `petsc4py` fork **all** currently lack an Intel-Mac wheel.
This is not one unlucky package that can be worked around with an older pin in isolation — it
is a convergent signal (three independent upstreams, one of them SimNIBS's own, all stopped
building for this target around the same recent-past window) that argues for **treating
macOS x86_64 as out of scope for the native-bundle path**, or for accepting a large,
non-trivial extra maintenance burden (pinning `bpy<5.0`, sourcing/building an older or custom
`petsc4py` wheel for `macosx_x86_64`, and finding/building a Torch CPU wheel for Intel Mac —
none confirmed to exist for a build recent enough to satisfy the rest of the stack's
constraints in this session). Given Apple's own Intel-Mac phase-out (last Intel Mac sold
2023, Apple Silicon transition begun 2020), and that three separate upstream projects
(Blender's `bpy`, PyTorch, and SimNIBS itself) have already made this same call, dropping
native Intel-Mac support for the *bundled-desktop* distribution (while leaving the existing
Docker path — where the image is `linux/amd64` regardless of host arch, VERIFIED
`docker-compose.v3.yml`'s `platform: linux/amd64` — as the Intel-Mac fallback, since Docker
Desktop emulates/runs x86_64 fine there) is the pragmatic recommendation, not a novel
constraint this project is introducing on its own.

### 4.4 Windows and Linux x86_64 and macOS arm64 have no equivalent blocker found

For every package checked (`bpy`, `torch`, `petsc4py`, `llvmlite`, `numba`, `mne`, `nilearn`,
`scikit-image`) across those three targets, a wheel exists somewhere (PyPI for most; SimNIBS's
own fork for `petsc4py` on win_amd64/manylinux_x86_64, §4.2). This does not rule out smaller
gaps in packages not checked (`mumps` Python bindings, `samseg`, `brainnet`, `brainsynth`,
`cgal`-derived binaries are SimNIBS-internal/vendored, not on PyPI at all, and were not
separately probed for platform coverage in this session — flagged as an open question, §9).

---

## 5. Recommended packaging architecture

### 5.1 Runtime layout

```
<app>/
  resources/
    python/
      linux-x64/        ← python-build-standalone x86_64-unknown-linux-gnu, install_only
        bin/python3.11
        lib/python3.11/site-packages/{numpy,scipy,simnibs,tit,...}
      macos-arm64/       ← aarch64-apple-darwin
      win-x64/           ← x86_64-pc-windows-msvc
      # macos-x64 intentionally omitted per §4.3 (or shipped best-effort/unsupported)
```
Populated per-platform in CI by: `python-build-standalone` interpreter, unpacked; `pip
install` the SimNIBS wheel + `tit` + `fastapi`/`uvicorn` + pinned scientific stack from PyPI;
for `petsc4py` specifically, `pip install` from the `simnibs/petsc4py` GitHub release asset
URL (§4.2) instead of PyPI; strip `PyQt5`/`jupyterlab`/`debugpy` (§1.3) since `tit.server` is
headless; strip `.pyc`-only bytecode caches, `__pycache__`, `*.dist-info/RECORD` if size
matters at the margin. `electron-builder.yml` per-OS blocks point `extraResources[].from` at
the matching `resources/python/<platform>/` directory (mirroring how `mac`/`win`/`linux`
blocks in both existing configs already scope OS-specific resources, §1.2/§3.1).

### 5.2 Runtime lifecycle (main process)

Add a `nativeRuntime.ts` sibling to `stack.ts` that:
1. Resolves `<resourcesPath>/python/<platform-arch>/bin/python` (or `python.exe`).
2. `findFreePort()` + `generateToken()` — **already exist**, reused verbatim from
   `desktop/src/main/{port,launcher}.ts`'s equivalents used by `stack.ts` today (VERIFIED,
   §1.1).
3. `child_process.spawn(pythonPath, ["-m", "tit.server", "--project", projectDir, "--port",
   String(port), "--static-dir", staticDir], { env: { ...process.env, TIT_SERVER_TOKEN: token,
   KMP_AFFINITY: "disabled", OMP_NUM_THREADS: "1", PYTHONHOME: "", PATH: pythonBinDir + PATH
   } })` — the `KMP_AFFINITY`/`OMP_NUM_THREADS` values are the exact ones the container sets
   today for the identical reason (§1.1); `PYTHONHOME` must be cleared/set explicitly for a
   relocated standalone interpreter to not accidentally pick up a system Python's stdlib.
4. `waitForHealth(origin)` — **reused verbatim**, no changes needed (§1.1, transport-agnostic
   already).
5. On app quit: kill the process tree, not just the direct child — `docker compose down`
   today handles cleanup for the container path; a native spawn needs the Node
   `tree-kill`-style approach (`taskkill /pid <pid> /t /f` on Windows, `process.kill(-pid)` on
   a detached POSIX child) since a leaked `uvicorn` worker or a spawned SimNIBS subprocess
   (`meshfix`, `mmg3d_O3`, §2.3) left running after the Electron window closes is a real
   failure mode this exact class of app already has to solve for its *subprocess-spawning
   subprocess* dependency (SimNIBS launches its own child binaries, so "kill tree" must be
   genuinely recursive, not one level deep).

### 5.3 Signing pipeline addition

A new `build/sign-python-runtime.js` (or `.sh`) script, run from `afterPack` (before
`afterSign`/notarize), that:
```
find resources/python/macos-*/ -type f \( -name "*.dylib" -o -name "*.so" -o -perm -u+x \) \
  -exec codesign --force --sign "$IDENTITY" --options runtime --timestamp {} \;
```
signing leaves-first (extension modules and dylibs before the interpreter binary itself,
since the interpreter's own signature should be the last one applied) — this is genuinely new
work neither existing config (§1.2) needed, because neither bundles a multi-GB Python tree.

---

## 6. Build-matrix table

| Runner (GitHub Actions) | Target | Python source | SimNIBS-stack wheel source | Signing | Known blocker |
|---|---|---|---|---|---|
| `ubuntu-24.04` (build on an older glibc base if possible, §3.4) | Linux x86_64 AppImage/deb/tar.gz | `python-build-standalone` `x86_64-unknown-linux-gnu` | PyPI (manylinux_2_28_x86_64 covers `bpy`/`torch`/`llvmlite`/`numba`; `petsc4py` from `simnibs/petsc4py` release, §4.2) | none required to run; optional GPG/deb signing out of scope here | AppImage glibc floor if built on too-new a runner (§3.4) |
| `macos-14` (arm64) | macOS arm64 dmg+zip | `python-build-standalone` `aarch64-apple-darwin` | PyPI (`bpy` `macosx_11_0_arm64`, `torch` `macosx_11_0_arm64`) + `petsc4py` from `simnibs/petsc4py` `macosx_14_0_arm64` (note: floor is macOS 14, matches this runner) | Developer ID + hardened runtime + notarize (Tetravox's exact pattern, §1.2/§3.2), **plus** the new walk-and-sign-runtime script (§5.3) | none found for the stack checked (§4.4) |
| `macos-13` (x86_64) | macOS x86_64 dmg+zip | `python-build-standalone` `x86_64-apple-darwin` | **broken**: `bpy≥5.0`, `torch≥2.4ish`, and `simnibs/petsc4py` all lack an Intel wheel (§4.1–§4.3) | n/a until unblocked | **recommend dropping this leg**; keep Docker (`linux/amd64` image) as the Intel-Mac path instead (§4.3) |
| `windows-latest` (or pinned version) | Windows x64 nsis | `python-build-standalone` `x86_64-pc-windows-msvc` | PyPI (`win_amd64` covers `bpy`/`torch`/`llvmlite`/`numba`) + `petsc4py` from `simnibs/petsc4py` `win_amd64` (§4.2) | none required to run (§3.3); optional code-signing cert not currently held per the sibling projects' own posture (Tetravox ships Windows unsigned, legacy launcher's `nsis` block has no signing config) | SmartScreen reputation only; first-run AV scan time on a multi-GB tree |

Caching: `python-build-standalone` archive per platform can be cached by its exact
`20260901`-style date tag (pin it, don't float `latest` — the archive changes weekly per the
release cadence observed, VERIFIED); the assembled `resources/python/<platform>/` tree itself
is the expensive-to-rebuild artifact and should be cached keyed on
`hash(requirements-lock-file + python-build-standalone tag)`, mirroring how `release.yml`
already keys its `pnpm`/`cargo`/electron-binary caches on lockfile hashes (VERIFIED pattern,
§1.2) — same discipline, new cache key.

---

## 7. Size budget per platform (estimated, built on VERIFIED measurements)

Baseline: `site-packages` measured at 3.5G with `PyQt5`+`jupyterlab`+`debugpy` (~243M)
included and droppable (§1.3); env root at 4.6G includes ~1.1G of non-Python payload, of
which some is required shared-library weight and some (headers, static libs, docs) is
strippable but not separately measured this session.

| Platform | Estimated installed size | Basis |
|---|---|---|
| Linux x64 | ~3.3–4.0 GB | `site-packages` (3.5G) minus GUI/dev-tool trim (§1.3), plus Electron itself (~150–200M unpacked, typical for a Chromium-based app, not independently measured this session) |
| macOS arm64 | ~3.3–4.0 GB | same basis; macOS `.app` bundle overhead is small relative to the Python tree |
| Windows x64 | ~3.3–4.0 GB | same basis; NSIS installer compresses the download but not the installed footprint |

This is **the SimNIBS+tit runtime only** — it explicitly excludes FreeSurfer/parcellation
(the `idossha/ti-toolbox_freesurfer:v7.4.1` image alone is 67.5 GB, VERIFIED `docker images`;
replacing it is R5's lane, out of scope here) and excludes Tetravox's own footprint (not
measured in this session; Tetravox is Rust+WASM, reported elsewhere in this codebase's own
docs to be lightweight by nature, not independently re-verified here). A first-run
component-download strategy (Tetravox's own `docs/`-referenced "extensions" download-on-
demand pattern, not independently inspected this session) is worth considering for the
Python runtime specifically given this multi-GB size, mirrored against a single big installer
— the trade-off is identical to the one SimNIBS's own installer already made (§1.3: one big
downloaded archive, no on-demand components) and to Docker's own current behavior (pull the
19.2GB `idossha/simnibs:v2.5.0` image on first `docker compose up`, VERIFIED `docker images`
size) — i.e. **this is not a new size problem the native-bundle path introduces; it's the same
size problem the Docker path already has, moved from a Docker pull to an installer/component
download**, just without Docker Desktop's own multi-GB tax on top of it.

---

## 8. Risks (ranked, each tagged with its evidence)

1. **macOS x86_64 has no wheel for 3 core deps** (`bpy`, `torch`, SimNIBS's own `petsc4py`
   fork) at versions recent enough to match the rest of the pinned stack — VERIFIED §4.1–4.3.
   Highest-confidence, most concrete finding in this report.
2. **Signing a multi-GB tree of hundreds of Mach-O binaries is new, unproven work** for this
   codebase — neither existing electron-builder config (§1.2) has ever done it; SimNIBS's own
   installer explicitly routed *around* full notarization instead of solving it (§1.3's
   password-zip trick, admitted in `pack.py`'s own `--macos-developer-id` help text). Budget
   real engineering time for a walk-and-sign script (§5.3) and expect first-attempt
   notarization failures on some overlooked `.dylib`.
3. **AppImage glibc floor**: building on too-new an Ubuntu runner raises the effective glibc
   requirement above what older user distros ship — REPORTED/inferred, §3.4, not measured
   against a specific old-distro target this session.
4. **`OMP_NUM_THREADS`/`KMP_AFFINITY` and other threading env vars are load-bearing, not
   cosmetic** — the container's own Dockerfile comment says `OMP_NUM_THREADS=1`/
   `KMP_AFFINITY=disabled` exist specifically to "avoid OpenMP affinity crash during
   postinstall" (VERIFIED, §1.1/§1.3 Dockerfile). A native launcher that forgets to set these
   (easy to lose when translating `docker-compose environment:` into `child_process.spawn`
   `env:`) risks reproducing a known crash class outside the container's protection.
5. **Antivirus / SmartScreen friction on Windows and first-run AV scan time** for a multi-GB
   Python tree with hundreds of native extensions — REPORTED (general knowledge of AV
   behavior with large freshly-written binary trees; not independently tested this session).
6. **`bpy`, `torch`, `petsc4py`(-fork) version pins are all coupled to the SimNIBS 4.6 release
   this container was built against**; a future SimNIBS upgrade could shift the whole
   platform-coverage picture in §4 in either direction (e.g. `bpy` regaining an Intel-Mac
   wheel, or dropping another platform) — this audit is a snapshot as of the versions
   VERIFIED in §4, not a permanent guarantee.
7. **Packages not audited for platform coverage this session**: `mumps` (Python bindings,
   imported alongside `petsc4py` in `simnibs/simulation/fem.py` line 16, VERIFIED import
   present but its own wheel/conda availability not checked), `samseg`/`brainnet`/
   `brainsynth` (SimNIBS-internal packages, not on PyPI, not separately probed), CGAL-derived
   `.so` files (§2.3, vendored/compiled in-tree, not a pip dependency at all — must be built
   or extracted from the conda-forge/SimNIBS build for each target, not simply `pip
   install`-able). Flagged as open questions, §9.

---

## 9. Open questions (things this session could not verify)

- Whether `mumps` Python bindings (imported unconditionally alongside `petsc4py` in
  `simnibs/simulation/fem.py`) have the same win-64/macOS-x86_64 gaps as `petsc4py` — not
  checked; same audit method (§4.2) would resolve this in ~10 minutes if needed.
- The actual contents of `environment_win.yml` / `environment_macOS.yml` / `environment_linux.yml`
  that `simnibs-installer`'s advanced conda-install path uses (referenced by
  `simnibs.github.io/simnibs/build/html/installation/conda.html`, REPORTED via WebFetch, but
  the files themselves are bundled inside release archives I did not download and extract this
  session, so their exact conda channel priorities / package pins were not directly read).
- Whether Electron's own unpacked-app size (not separately measured this session, estimated
  at "~150–200M" from general knowledge in §7) meaningfully changes the totals in §7 — worth a
  quick `du -sh` on any existing packaged Electron app in this environment if a more precise
  number is needed.
- Tetravox's own installed-app size (not measured this session) — would sharpen §7's "the
  Python runtime dwarfs everything else" claim from "reported elsewhere" to independently
  verified.
- Whether CGAL's compiled `.so` files (§2.3) are themselves cross-platform-available anywhere
  as prebuilt artifacts (conda-forge CGAL bindings, or SimNIBS's own build) or must be
  compiled per-platform as part of any from-scratch bundling pipeline — not checked this
  session; likely resolved the same way `petsc4py` was (conda-forge or a SimNIBS-maintained
  wheel), but not confirmed.

---

## Sources

- Local files read in full (VERIFIED): see inline citations throughout; primary ones:
  `desktop/src/main/{stack,health,launcher}.ts`, `tit/server/settings.py`,
  `desktop/docker/docker-compose.v3.yml`, `container/blueprint/Dockerfile.simnibs`,
  `desktop/package.json`, `simnibs/packing/{pack.py,install,macOS_installer/*}`,
  `TI-toolbox/package/{package.json,build/entitlements.mac.plist,build/notarize.js}`,
  `tetravox/{packages/app/electron-builder.yml,scripts/electron-builder.sh,.github/workflows/release.yml}`,
  `tracks/active/v3-electron-gui.md`.
- Commands run against `tit-v3-spike` (`idossha/simnibs:v2.5.0`, x86_64 emulated) and the
  host: `du -sh`, `pip list`/`pip show`, `find … -name "*.so"`, `ls -la` on
  `simnibs/external/bin/linux/`, `docker images`.
- [python-build-standalone releases (GitHub API)](https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest)
- [PyPI JSON API](https://pypi.org/pypi/) for `bpy`, `torch`, `petsc4py`, `llvmlite`, `numba`, `mne`, `nilearn`, `scikit-image`
- [conda-forge petsc4py files (anaconda.org API)](https://api.anaconda.org/package/conda-forge/petsc4py/files)
- [conda-forge/petsc4py-feedstock issue #98 — "petsc4py not available on Windows"](https://github.com/conda-forge/petsc4py-feedstock/issues/98)
- [simnibs/petsc4py releases (GitHub API)](https://api.github.com/repos/simnibs/petsc4py/releases)
- [Install Using Conda (Advanced) — SimNIBS docs](https://simnibs.github.io/simnibs/build/html/installation/conda.html)
- [simnibs/simnibs-installer](https://github.com/simnibs/simnibs-installer) (`install_simnibs.py`, `requirements.txt`)
- [napari NAP-2 — conda-based packaging](https://napari.org/dev/naps/2-conda-based-packaging.html)
- [Quansight Labs — generalizing napari's conda/constructor stack](https://labs.quansight.org/blog/napari-conda-constructor-menuinst)
- [Packaging Napari app through PyInstaller — Image.sc forum](https://forum.image.sc/t/packaging-napari-app-through-pyinstaller/42100)
- [Tauri sidecar docs](https://v2.tauri.app/develop/sidecar/), [tauri-apps/tauri discussion #2759](https://github.com/orgs/tauri-apps/discussions/2759)
- Apple Developer Forum threads on notarizing bundled Python (`developer.apple.com/forums/thread/{129631,737603,725061,721410}`), via WebSearch

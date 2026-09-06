# N0.4 — Packaging: Electron app with a bundled Python runtime

Stage N0 spike. Proves: an Electron app can bundle a private Python runtime as
`extraResources`, spawn `python -m tit.server` as a native child process (no Docker), connect
the existing shell to it, and clean up the whole process tree on quit — all inside a packaged,
offscreen-launched `.app`. Also measures the ad-hoc code-signing cost r4 flagged as unmeasured,
and finds (empirically, not just from doc research) a real bug in that signing recipe.

Machine: Apple M2 Max, macOS 15.6 (Darwin 24.6.0), Homebrew bash 5.3.9 as default `bash`.
Runtime built independently of lane N0.1's full-SimNIBS runtime spike, per the brief — a
minimal `tit.server`-only stack (fastapi/uvicorn/pydantic/pyyaml/psutil/numpy/nibabel + `tit`),
**not** SimNIBS/bpy/torch. Every number below is measured on that minimal runtime; §6 extrapolates
to the real SimNIBS-scale runtime with explicit caveats.

## 1. What was built (owned files)

| Path | What |
|---|---|
| `desktop/src/main/nativeRuntime.ts` | Native runtime lifecycle: locate the bundled/pointed-at runtime, build argv/env, spawn, wait for health, kill the process tree on stop. Mirrors `stack.ts`'s shape so `index.ts` needs only a thin hook. |
| `desktop/src/main/index.ts` (hook) | `tryNativeAutoStart()` — when `TIT_NATIVE_PROJECT_DIR` is set and a runtime resolves, spawns it and connects, bypassing the launcher form; quit kills it unconditionally (no "keep running" prompt — nothing to reattach to). Every existing path (Docker launcher, manual connect) is untouched. |
| `desktop/electron-builder.yml` | appId `edu.wisc.ti-toolbox.desktop`, productName `TI-Toolbox`, `extraResources` for `runtime/darwin-arm64` and `renderer`, `mac.identity: null` (no signing secrets used), hardened runtime + entitlements declared for when a real identity is added later. |
| `desktop/scripts/stage-runtime.sh` (new, not in the original file list — see §3) | Copies `$TIT_RUNTIME_DIR` to a fixed relative path `electron-builder.yml` can reference. Exists because of a real electron-builder bug, §3. |
| `desktop/scripts/sign-runtime.sh` | Walks a runtime tree, ad-hoc-signs every Mach-O inside-out (dylibs/.so, then executables), **with entitlements** (see §4 — required, not optional), times it. |
| `desktop/tests/e2e/native-launch.spec.ts` | Launches the packaged, unpacked `.app` offscreen, asserts the shell connects to the natively-spawned server, checks `/api/health` independently, and asserts no orphan python process survives quit (`pgrep` before/after). |
| `desktop/tests/unit/nativeRuntime.test.ts` | 20 unit tests over the pure parts of `nativeRuntime.ts`: platform-arch naming, runtime resolution, argv/env building, kill-plan selection. |
| `desktop/build/{entitlements.mac.plist,icon.icns,icon.ico,icon.png}` | Entitlements (same 4 as the legacy launcher / r4 §1.2) + icons copied from `package/assets/` (placeholder — not this lane's asset to design). |
| `dev/spikes/native/packaging/build-runtime.sh` | Builds the minimal runtime this spike measured against (copy of the script run during the spike). |
| `desktop/tsconfig.web.json`, `desktop/eslint.config.mjs`, `desktop/.gitignore`, `desktop/package.json`, `desktop/package-lock.json` | Minimal supporting edits — not on the brief's owned list, done because my own new files needed them to typecheck/lint/build cleanly (details in §7). |

## 2. Runtime build (independent of N0.1)

```
dev/spikes/native/packaging/build-runtime.sh
```
Downloads `cpython-3.11.16+20260901-aarch64-apple-darwin-install_only.tar.gz` (python-build-standalone,
**VERIFIED tag `20260901`**, same as r4 §2.1), `pip install`s `fastapi 'uvicorn[standard]' pydantic
pyyaml psutil numpy nibabel`, then `pip install <this worktree>` (non-editable — self-contained copy,
per the brief). No SimNIBS.

Measured:
```
archive size: 26M (download)
build wall time: 7.9s (4.18s user, 1.52s system)
interpreter: Python 3.11.16 (main, Sep 1 2026, 14:08:22) [Clang 22.1.3]
smoke: import tit.server.app -> OK, tit version 2.4.0
runtime tree size: 165M (6361 files)
```
`tit.server.app` imports cleanly with **no SimNIBS present** — confirms r6's finding (only
`tit.sim`/`tit.opt.*`/`tit.blender` import SimNIBS at module scope) from a completely fresh,
independently-built environment, not the container.

**Real server smoke test** (`python -m tit.server --project <empty temp dir> --host 127.0.0.1
--port 18765 --token spike-test-token`, then curled):
```
GET /api/health  -> 200 {"status":"ok","uptime_s":1.523}
GET /api/version -> 200 {"tit_version":"2.4.0","server_api":"v0","schema_hash":"f928c4...","python":"3.11.16","simnibs":null}
GET /api/project -> 200 {"container_path":"...testproj","host_path":null,"name":"testproj"}
```
`"simnibs":null` — the server reports its own absence gracefully, exactly as designed.

## 3. Packaging (`npm run package:dir`)

```
cd desktop
export TIT_RUNTIME_DIR=<path to the runtime from §2>
npm run package:dir   # stage-runtime.sh && electron-vite build && electron-builder --dir --config electron-builder.yml
```

**Real bug found and worked around**: electron-builder 26.15.3 resolves an `extraResources`
`from:` path with `path.resolve(projectDir, pattern.from)` **before** expanding `${env.X}`
config macros (`app-builder-lib/out/fileMatcher.js`, `getFileMatchers`, line ~244: `path.resolve
(options.defaultSrc, pattern.from)` runs on the still-literal `${env.TIT_RUNTIME_DIR}` token,
which `path.resolve` treats as relative since it doesn't yet start with `/`; the real absolute
value is substituted into the *middle* of that already-wrong path only afterward, inside the
`FileMatcher` constructor). Reproduced exactly as:
```
file source doesn't exist  from=.../desktop//private/tmp/.../packaging/runtime
```
Fix: `desktop/scripts/stage-runtime.sh` copies `$TIT_RUNTIME_DIR` to a fixed relative
`.runtime-staging/darwin-arm64`, which `electron-builder.yml`'s `extraResources.from` references
directly (no macro). The brief's "parametrise by env `TIT_RUNTIME_DIR`" still holds — the
substitution just happens one step earlier, in the staging script, not in the YAML. This is a
genuine electron-builder limitation for absolute-path macros in `extraResources`, worth carrying
into Stage N1's CI runtime-build pipeline design (it will hit the identical bug pointing at a
CI-built runtime path).

**Measured**:
```
stage-runtime.sh: 166M copied in ~2.4s
electron-vite build: 2.1-4.6s (2408 modules)
electron-builder --dir --mac --arm64: 9.5s wall (8.32s user, 5.58s system) — after the first run's
  one-time Electron zip download/cache
```

**Packaged app size** (`release/mac-arm64/TI-Toolbox.app`):
```
Total                                   468M
Contents/Frameworks (Electron itself)   286M  (61%)
Contents/Resources/runtime              175M  (37%)  <- this spike's MINIMAL runtime
Contents/Resources/renderer             4.9M  (1%)
```
For this minimal runtime, Electron's own framework outweighs the Python payload — the inverse of
what r4 §7 projects for the real SimNIBS runtime (~3.3-4.0GB), where the runtime becomes >90% of
the total. This spike's ratio is not representative of the real build; it proves the *mechanics*
(the runtime lands where it should, at the size it actually is), not the real footprint.

`mac.identity: null` in `electron-builder.yml` — confirmed in the build log:
```
skipped macOS code signing  reason=identity explicitly is set to null
```
No signing secrets were looked for or used at any point in this spike.

## 4. End-to-end proof: the packaged app spawns the runtime and connects

`tests/e2e/native-launch.spec.ts`, run through the offscreen quiet-check:
```
$ bash scripts/e2e-quiet-check.sh npx playwright test tests/e2e/native-launch.spec.ts
e2e-quiet-check: frontmost before = <unchanged>
Running 1 test using 1 worker
  ✓  1 tests/e2e/native-launch.spec.ts:72:7 › native launch (packaged app, N0.4 spike) ›
     spawns the bundled runtime, connects, and leaves no python process behind on quit (3.7s)
  1 passed (4.5s)
e2e-quiet-check: frontmost after  = <unchanged>   (7-8 samples)
e2e-quiet-check: command exited 0
e2e-quiet-check: no Electron/Chromium window reached the screen.
e2e-quiet-check: PASS
```
The spec launches `release/mac-arm64/TI-Toolbox.app/Contents/MacOS/TI-Toolbox` directly
(`executablePath`, not the dev tree) with `TIT_NATIVE_RUNTIME_DIR` explicitly unset (forcing the
**packaged** `resourcesPath/runtime/darwin-arm64` resolution branch, not the dev/env-override one)
and `TIT_NATIVE_PROJECT_DIR` pointing at a fresh temp directory. It asserts, independently of the
page itself:
- the window never shows `app://launcher` (the form is genuinely bypassed)
- `shell-content` renders and either `subjects-table` or the empty-project state appears
- `GET <origin>/api/health` and `/api/version` both answer 200 from the **spawned** server
- `pgrep -f "runtime/darwin-arm64/bin/python3.11 -m tit.server"` finds the process while the app
  is open, and finds **nothing** ~2s after `app.close()`

Manual run of the same flow (before the spec existed, used to develop it) showed the actual UI
the shell renders once connected — project name `testproj2`, "No subjects found in this project
yet.", footer "tit 2.4.0 · api v0" — and the same clean-process-tree-kill result via `pgrep`
before/after.

## 5. Signing cost measurement — and a real bug found in the process

`desktop/scripts/sign-runtime.sh`, walking the packaged app's own runtime copy
(`release/mac-arm64/TI-Toolbox.app/Contents/Resources/runtime/darwin-arm64`, 166M, 6361-6364
files):

```
$ time bash scripts/sign-runtime.sh <runtime-dir>
scanning 6361 files for Mach-O binaries…
found 37 dylib/.so + 1 other executable Mach-O binaries (38 total)
signing 37 dylibs/.so extension modules…
signing 1 executables…
signed 38 Mach-O binaries in <1s (batched codesign call, one argv list per group)
real  0m20.9s  (9.82s user, 8.91s system)
```
The **scan phase** (one `file -b` process spawn per file, to detect Mach-O by content rather
than extension — needed because `bin/python3.11` and every future SimNIBS sibling binary
`meshfix`/`mmg3d_O3`/`dwi2cond` have no extension at all) is what actually costs the ~20s, not
the signing: an isolated `find | xargs -n1 file -b` over the same 6364 files took 16.2s (390
files/s under `xargs` batching; the bash `for`-loop in the script itself, one `file` call per
loop iteration, is slightly slower at ~300 files/s). Actual `codesign` throughput, once files are
identified, is fast — 38 files signed in under a second in one batched invocation.

**Real, empirically-reproduced bug in the signing recipe** (this is new evidence beyond what r4
could establish from documentation alone): signing every Mach-O ad-hoc (`-s -`) **without**
`--entitlements` — the version of this script I wrote first — produces a runtime that still
*launches* (Electron spawns it fine, health check passes) but then fails on its own first `import
numpy`:
```
ImportError: dlopen(.../numpy/_core/_multiarray_umath.cpython-311-darwin.so, 0x0002):
  tried: '...' (code signature ... not valid for use in process: mapping process and mapped
  file (non-platform) have different Team IDs)
```
Same failure for `psutil` and, transitively, `tit.server.app` itself. Root cause: `--options
runtime` turns on library validation for the *loading* process (the interpreter); each file was
signed ad hoc with its own distinct, team-less identity, so validation fails for every
extension module loaded after the interpreter itself gets hardened-runtime-signed. **Fix**:
`--entitlements build/entitlements.mac.plist` (specifically
`com.apple.security.cs.disable-library-validation`) on the *interpreter*'s own signature is what
restores dlopen — confirmed by re-signing only `bin/python3.11` with entitlements and re-running
the import, then confirmed end-to-end by re-signing the whole tree with the fixed script and
re-running the e2e spec (§4's PASS above is from the **signed** app). This directly, concretely
substantiates r4 §1.2/§3.2's Apple-Forum-sourced claim ("bundled Python libraries do need to be
signed... `--deep` Considered Harmful") — not just cited from a doc search, but reproduced against
a real interpreter loading its own real extension modules and fixed.

`sign-runtime.sh`'s final form applies `--entitlements` to every file it signs (both groups),
which is what §4's PASS output is signed with.

## 6. Extrapolation to the real SimNIBS runtime (estimate, not measured)

This spike's runtime (166M, 6361 files, 38 Mach-O) is far smaller than what r4 projects for the
real bundle (~3.3-4.0GB after trimming PyQt5/jupyterlab/debugpy, r4 §1.3/§7). Lane N0.1's own
in-progress runtime build (a different lane's own artifact — read-only peek at
`.../native/runtime/runtime-macos-arm64`, **not verified or owned by this report**, cited only for
scale) stood at 2.0GB / 48,197 files at the time of this peek, still incomplete (`bpy`/`torch` not
yet confirmed installed). Applying this spike's measured scan rate (300-390 files/s):
```
48,197 files / ~345 files/s (avg)  ~= 140s  ~= 2.3 min  (scan phase alone, partial-build file count)
```
A fully-built runtime at r4's ~3.3-4.0GB, if its file count scales anywhere near proportionally
with size (uncertain — torch/bpy ship some very large individual `.so`s rather than proportionally
more small files, so file count may grow sub-linearly with size), would put the scan phase
somewhere in the **2-6 minute range**, with actual `codesign` time for however many hundred-to-low-
thousand real Mach-O binaries r4 §8 risk 2 anticipated adding well under a minute on top (this
spike's 38-file batch signed in under a second; even 2,000 files at that throughput is on the
order of a minute). **Net estimate: single-digit minutes for a full walk-and-sign pass**, dominated
by Mach-O detection overhead, not by codesign itself — a real cost, but not the blocking risk r4's
own uncertainty ("nobody has measured this") might have suggested. The detection step could
plausibly be sped up in Stage N1 (parallelizing the `file` calls, or trusting file extensions for
`.so`/`.dylib` and using `otool -h`/a Mach-O magic-byte check only for extensionless files) if it
becomes the bottleneck at real scale — not attempted here, flagged as a N1 follow-up.

## 7. Gates

```
cd desktop
npm run typecheck   # clean
npm run lint         # 0 errors, 3 pre-existing warnings (React Compiler skip notices, unrelated files)
npx vitest run       # 43 files / 418 tests; 42/43 files green.
npm run build        # clean
bash scripts/e2e-quiet-check.sh npx playwright test tests/e2e/native-launch.spec.ts   # PASS (§4)
```

**One flaky, unrelated test file**: `tests/unit/shell-contextBar.test.tsx` (3 tests) failed
intermittently inside the full 43-file `vitest run` (timing-sensitive, 5s async wait) but passed
cleanly every time run in isolation (5/5, 1.28s). Not a file I touched, not in my owned path list,
unrelated to native-runtime code (a renderer shell-component test with no Electron main-process
involvement) — most likely resource contention from six lanes building/testing concurrently on one
machine. `tests/unit/nativeRuntime.test.ts` itself: 20/20 green, every run, isolated and in the
full suite.

**Supporting edits outside the brief's owned-file list**, made because my own new files needed
them and nothing else in this worktree already provided them:
- `desktop/tsconfig.web.json`: added `src/main/{nativeRuntime,health,log,port}.ts` to `include`.
  Composite TS projects require every transitively-imported file to match an include pattern;
  `tests/unit/nativeRuntime.test.ts` imports `nativeRuntime.ts`, which imports `health.ts`/`log.ts`
  (both import `"electron"`, confirmed safe to import under vitest — outside an Electron runtime
  `require("electron")` resolves to a plain string, so `{ app, net }` come back `undefined`,
  never throwing; verified empirically before relying on it) and `port.ts`. (Lane N0.3 hit and
  fixed the identical issue for its own `src/main/docker/**/*.ts` files independently, in this
  same file, while this spike was in progress — confirms the pattern, not a conflict.)
- `desktop/eslint.config.mjs`: added `release/` and `.runtime-staging/` to the ignores array.
  Without it, `npm run lint` walked into the packaged app's own copy of pip's vendored JS
  (`site-packages/pip/_vendor/urllib3/contrib/emscripten/*.js`) and the built renderer's minified
  assets, ballooning to 1553 problems that had nothing to do with this repo's own code.
- `desktop/.gitignore`: added `release/` and `.runtime-staging/` (electron-builder output and the
  staged runtime input — both generated, both machine-specific, both multi-hundred-MB).
- `desktop/package.json` / `package-lock.json`: `electron-builder@26.15.3` added as a devDependency
  (pinned to the exact version Tetravox itself pins, `npm install --save-dev --save-exact`), plus
  the `package`/`package:dir` scripts.

## 8. What this proves

- A native Electron child process spawning a bundled `python -m tit.server` — no Docker, no
  `docker-compose.v3.yml` — works end-to-end: spawn, health check, connect, real UI renders, clean
  process-tree kill on quit. Proven in a **packaged, offscreen-launched app**, not just a dev tree.
- The exact env/argv contract `docker-compose.v3.yml` uses today (`KMP_AFFINITY=disabled`,
  loopback-only bind, token via env) carries over unchanged to a native spawn.
- `electron-builder`'s `extraResources` mechanism does place a multi-hundred-MB runtime tree where
  a native spawn can find and execute it, from inside a packaged `.app` — with one real, documented
  bug in how it resolves macro-expanded absolute paths (§3), worked around cleanly.
- Ad-hoc signing every Mach-O in a bundled Python runtime is necessary but **not sufficient**
  without matching entitlements on the interpreter itself — an empirically-found, empirically-fixed
  gotcha (§5) that goes beyond what documentation research alone (r4) could establish.
- Signing-pass cost for a runtime this size is small (~21s); detection overhead (not signing
  itself) is what will dominate at full-SimNIBS-runtime scale, estimated at single-digit minutes
  (§6, not measured against the real tree).

## 9. What this does NOT prove / follow-ups for Stage N1

- **Not tested against the real SimNIBS runtime.** This spike's runtime has no `bpy`, `torch`,
  `petsc4py`, no SimNIBS at all — proves the packaging *mechanics*, not that the full ~3.3-4.0GB
  tree packages/signs/launches identically. N0.1's runtime is the one to point this exact pipeline
  at next.
- **No real code signing or notarization** — `identity: null`, ad-hoc only. The `--entitlements`
  fix (§5) is necessary groundwork for that, not a substitute for it; a real Developer ID +
  `@electron/notarize` pass (Tetravox's own pattern, already referenced in `electron-builder.yml`'s
  comments) is unexercised here by design (no secrets used in Stage N0).
- **Linux/Windows are declared in `electron-builder.yml` but never built or tested** — only macOS
  arm64 `--dir` was run. `nativePlatformArch()`/`resolveRuntime()` in `nativeRuntime.ts` already
  branch correctly for `linux-x64`/`win32-x64` (unit-tested), but nothing spawns/signs/kills a
  process tree on those platforms in this session.
- **`stage-runtime.sh`'s reliance on Homebrew bash's `mapfile`** (`sign-runtime.sh` too) — this
  Mac's `/usr/bin/env bash` resolves to Homebrew bash 5.3.9; a clean macOS with only Apple's bash
  3.2 on `PATH` would fail on `mapfile`. Worth hardening for Stage N1's CI use (Tetravox's own
  `electron-builder.sh` already documents hitting bash-3.2 quirks on macOS for a different reason).
- **"Attach" is spawn-only, not cross-restart** (documented in `nativeRuntime.ts`'s own module
  doc) — a native server never survives this app quitting; there is no `stackState.ts`-equivalent
  persisted record for it. Fine for this spike; worth a deliberate decision in N1 (probably: keep
  it this way — a local Python process, unlike a Docker container, has no reason to outlive the
  app that owns it).
- **electron-builder's `${env.X}` macro-in-`extraResources.from` bug (§3)** should be filed/known
  before Stage N1's CI pipeline design leans on the same pattern — the workaround
  (`stage-runtime.sh`) generalizes fine (a CI job stages its freshly-built runtime the same way),
  but it is one more moving part a straight YAML macro would not have needed.
- **Detection-phase signing throughput** (§6) not optimized — worth a second pass if the real
  runtime's walk-and-sign time turns out to matter for CI wall-clock budget.
- Icons under `desktop/build/` are copied from the legacy launcher's assets as a placeholder — not
  this lane's call to design final branding.

# Lane TI — the managed Tetravox install (V6)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-06.
Follows lane **VX** (`VX.md`), which made the viewer an external desktop app. This lane removes
the last thing that lane left on the user: *having to install it*.

Maintainer's brief, verbatim: *"make sure we don't require users to have Tetravox installed on
their system."*

Every Playwright run was offscreen (`scripts/e2e-quiet-check.sh`) — no window reached the screen.
One real 131 MB download ran on this Mac, under `TIT_E2E_ALLOW_DOWNLOAD=1`, into a temp directory.
Nothing was stashed, reverted or checked out.

---

## 1. DECISIONS

### V6.1 — the viewer is installed on the **host**, by the desktop app, not baked into the image

The maintainer's own proposal was to install Tetravox inside the `ti-toolbox` Docker image, next
to SimNIBS. **Rejected**, and the reason is a run-time fact rather than a preference:

- The image is headless by construction (blueprint decision **D3**: no X11, no display libraries,
  no `DISPLAY`). Tetravox is an Electron app whose entire purpose is a WebGL2 canvas.
- Since **Chromium 137** there is no software-WebGL fallback: SwiftShader was removed as a WebGL
  backend, so `--use-gl=swiftshader` no longer yields a rendering context. A container launch
  would either fail to open a window or open one with no GL — and the failure would surface as a
  blank canvas, three layers from the cause.
- Forwarding X11 back to the host replaces one install (Tetravox, signed and notarised) with a
  worse one (XQuartz on macOS, an X server on Windows) *and* streams an interactive 3-D viewer
  over a socket, on a machine whose GPU is sitting idle.

So the viewer must run on the host's own GPU. If it must run on the host, something has to put it
there — and the honest choice is between "the user does it" (what V3 shipped) and "the app does
it". This lane makes it the app. Recorded in `container/blueprint/README.md` and in
`docs/wiki/desktop-app.md`, so the next person to have the same good idea finds the answer.

### V6.2 — the publisher's own digest, not our own pin

The asset is verified against the base64 SHA-512 in the release's `latest*.yml`, the manifest
electron-updater already publishes for its own updater. Not a digest checked into this repository:
a pinned hash means a TI-Toolbox release for every Tetravox release, which is exactly the coupling
lane VX spent itself removing. Not "no check at all": this app downloads and executes a binary.

### V6.3 — activate on the next launch, never under a running window

An update lands on disk as `pending` and becomes `current` at the next start of TI-Toolbox. A
viewer swapped underneath an open window is a crash a user cannot explain, and the cost of waiting
is one launch.

### V6.4 — quarantine comes off only after `codesign --verify`

On macOS the order is `ditto` → `codesign --verify --deep --strict` → `xattr -dr
com.apple.quarantine`, and the last step runs **only** if the second passed. Stripping quarantine
unconditionally would mean this app waving a downloaded binary past Gatekeeper on the user's
behalf. A bundle that does not verify keeps the attribute and meets Gatekeeper, which is the right
authority for that question.

## 2. The asset and verification path, per platform

| Platform | Asset resolved | Digest from | Materialise | Managed path |
|---|---|---|---|---|
| macOS arm64 | `Tetravox-<v>-mac-arm64.zip` | `latest-mac.yml` (per-file entry) | `ditto -x -k` → `codesign --verify --deep --strict` → `xattr -dr com.apple.quarantine` **iff** verified | `<userData>/tetravox/<v>/Tetravox.app` |
| macOS x64 | `Tetravox-<v>-mac-x64.zip` | `latest-mac.yml` | same | same |
| Windows x64 | `Tetravox-<v>-win-x64.exe` (NSIS) | `latest.yml` | the release publishes **no portable or zip build**, so the installer is run silently: `<exe> /S /D=<dir>` — `/D` last and unquoted, which is NSIS's own rule | `<userData>/tetravox/<v>/Tetravox.exe` |
| Linux x64 | `Tetravox-<v>-linux-x86_64.AppImage` | `latest-linux.yml` | rename to `Tetravox.AppImage`, `chmod 0755` — an AppImage *is* the install (the `.deb` would need root) | `<userData>/tetravox/<v>/Tetravox.AppImage` |
| anything else | — | — | — | `supported: false`, stated in Settings; the Releases link still works |

`ditto` and not `unzip`: it is the only unpacker on macOS that preserves the symlinks and extended
attributes inside an `.app`, and a bundle unpacked with `unzip` fails its own code signature.

Verified against the real 0.3.11 release: every asset name and every `latest*.yml` above exists,
and `tests/unit/tetravox-install-real.test.ts` re-checks that against GitHub on demand.

## 3. What was built

| File | What |
|---|---|
| `desktop/src/main/tetravoxInstall.ts` | **new, ~560 lines.** The pure half — `detectTarget`, `assetNameFor`, `manifestNameFor`, `executableIn`, `pickRelease`, `versionFromTag`, `compareVersions`, `sha512FromManifest`, `checkIsDue` — and the IO half: `installRelease` (download → hash → verify → materialise → atomic rename → state → prune), `resolveLatestRelease`, `activatePending`, `pruneVersions`, `diskUsage`, and the `createManagedTetravox` orchestrator main holds. `fetch` and `run` are injectable, which is what lets the whole chain be tested over loopback. |
| `desktop/src/main/viewer.ts` | discovery order is now **managed → override → system**, `source` gained `"managed"`, `findTetravox`/`probeTetravox` take the managed location. A managed install that is not on disk falls through rather than disabling the viewer. |
| `desktop/src/main/index.ts` | the orchestrator is created at startup; `activate()` then `maybeCheck()` — neither blocks. Three new IPC handlers (`install`, `checkUpdates`, `remove`), progress pushed on `tit:viewer:event`, and `open` now **installs and then launches** when nothing is there, so a first Open is one click. |
| `desktop/src/preload/index.ts`, `desktop/src/shared/tit-bridge.d.ts` | the `viewer` object grew `install`/`checkUpdates`/`remove`/`onEvent` and `TitViewerInfo.managed`. **The bridge budget is unchanged at 13** — `viewer` is still one top-level entry, like `stack`. |
| `desktop/src/renderer/pages/_shared/viewer/useTetravox.ts` | `progress` (a live push, not a poll), `install`, `checkUpdates`, `remove`. Browser mode answers exactly as before. |
| `desktop/src/renderer/pages/settings/ViewerCard.tsx` | rewritten around the managed install: version, **Installed by TI-Toolbox**, last check, disk usage, a pending-update row, `Check for updates`, `Remove`, `Use a different Tetravox…`, `Releases…`, and one progress line. Still reaches no network on mount. |
| `desktop/tsconfig.web.json` | `src/main/tetravoxInstall.ts` listed, same reason as `viewer.ts`: composite projects need every transitively-imported file. |
| `desktop/tests/unit/tetravox-install.test.ts` | **new, 26 tests**, against a real loopback releases API with real digests. |
| `desktop/tests/unit/tetravox-install-real.test.ts` | **new, 2 tests**, both env-gated (§5). |
| `desktop/tests/unit/viewer-launch.test.ts` | +3 tests for the discovery order. |
| `desktop/tests/e2e/settings.spec.ts` | the viewer card's four states: managed install, pending update, nothing installed, unsupported platform. |
| `docs/wiki/desktop-app.md`, `container/blueprint/README.md` | the managed install, the update policy, and the DECISION above. |

Deliberately *not* built: a progress toast on the Viewer page (that page is another lane's file
this week). Main emits `tit:viewer:event` for it; Settings renders it today.

## 4. Gate

```
desktop$ pnpm run typecheck                              clean
desktop$ npx eslint src tests                            0 errors, 3 pre-existing warnings
                                                         (ui/DataTable.tsx, ui/VirtualList.tsx)
desktop$ npx vitest run                                  90 files, 1071 passed, 2 skipped;
                                                         1 unrelated failure — see below
desktop$ pnpm run build                                  clean
desktop$ pnpm run pree2e && e2e-quiet-check.sh \
           playwright test settings.spec.ts smoke.spec.ts   14 passed (1.1 m), PASS: no window
                                                            reached the screen, focus never moved
```

The one red file, `tests/unit/viewer-page.test.ts` (`ReferenceError: beforeEach is not defined`),
is an **uncommitted work-in-progress edit from the concurrent `pages/viewer/**` lane** — a missing
import in their file, in a file this lane does not touch. Reported, not fixed and not reverted.

## 5. The real tests, and their gates

`tests/unit/tetravox-install-real.test.ts`, both skipped by default so `npx vitest run` stays
offline:

- `TIT_TETRAVOX_REAL=1` — resolves the live release index and reads the real `latest*.yml`. Two
  small HTTPS requests, no download. This is the only test that can catch Tetravox renaming an
  asset; the loopback suite serves the shape this code expects, so it cannot.
- `TIT_TETRAVOX_REAL=1 TIT_E2E_ALLOW_DOWNLOAD=1` — one real install into a temp directory.

Run once on this Mac, both gates on:

```
✓ publishes the asset and the manifest this platform installs
  v0.3.11 → Tetravox-0.3.11-mac-arm64.zip (latest-mac.yml, sha512 Xe2yC01SVdY…)
✓ verifies, unpacks, and produces a bundle that passes codesign     (6.3 s total, 131 MB)
  → <tmp>/tvx-real-XXXX/0.3.11/Tetravox.app
  codesign --verify --deep --strict : PASS
  xattr -p com.apple.quarantine     : absent (stripped, because codesign passed)
```

**Tetravox has no `--version` flag.** Its CLI (`packages/app/src/main/cli.ts`) takes file paths
plus `--job`/`--out`/`--tvx-search`/`--user-data-dir`; every other invocation opens a window. So
the installed copy is asserted by its bundle structure (`Contents/MacOS/Tetravox`,
`Contents/Info.plist`) and by Apple's own verdict on it — never by launching it. A test must not
put another application's window on the screen of the machine running it.

One thing worth knowing before debugging it again: **GitHub's API answers `403` both to a request
with no `User-Agent` and to an unauthenticated IP over 60 requests an hour**, with nothing in the
status to tell them apart. `resolveLatestRelease` sends a User-Agent always and an `authorization`
header when `GITHUB_TOKEN`/`GH_TOKEN` happens to be set — never required, since a once-a-day check
is far under the anonymous limit, but it is what makes a test loop (or a shared office IP) work.

## 6. What a user now experiences

Fresh machine, no Tetravox: open a simulation, press **Open in Tetravox**. A progress line, and
the scene opens. Nothing was installed by hand, no dialog was answered, and no release page was
visited. Offline with a viewer already installed: it opens, immediately, and the app does not
mention the network. Offline with none: one honest sentence and a retry.

## 7. The follow-up bug: "it writes the scene and Tetravox never opens"

Reported from the screenshot of a `cd desktop && pnpm run dev` session: **Open in Tetravox** wrote
`subject.tetravox.json`, the page said *Opened … — /Users/idohaber/datasets/000/code/ti-toolbox/
viewer/subject.tetravox.json*, and no Tetravox window ever appeared. No error anywhere.

### Root cause (measured on this Mac, not inferred)

**A Tetravox left running with no window swallows the scene, and `open` still exits 0.**

At the moment the report arrived, `pgrep` found Tetravox running (pid 24512) and
`System Events` reported it had **zero windows** — the ordinary state of a macOS app whose window
was closed with ⌘W. From that state, every launch is silently inert:

| What was run, from a shell, against the windowless instance | `open` exit | windows after |
|---|---|---|
| `open -a /Applications/Tetravox.app <scene>` (what this app did) | 0 | **0** |
| `open -n -a /Applications/Tetravox.app <scene>` (a *new* instance) | 0 | **0** |
| `open -a /Applications/Tetravox.app` (no document) | 0 | **1**, showing the scene from the call above |

The upstream mechanism, read out of `packages/app/src/main/index.ts` at 0.3.11: `open -a <app>
<doc>` on a running app fires `open-file`; the handler is `if (mainWindow) sendOpened(…) else {
startupScene = scene }` — with the window closed, `mainWindow` is `null` (its `closed` handler
nulls it), so the scene goes into `startupScene` and **nothing creates a window to drain it**.
`-n` does not help either: the single-instance lock quits the new process and the old one takes
the same dead path through `second-instance`. What does work is Tetravox's own `activate` handler,
which *does* call `createWindow()` when `BrowserWindow.getAllWindows().length === 0` — and an
activation is exactly what a document-less `open -a` produces.

Two defects on this side made it invisible rather than merely broken:

1. **The launch was fire-and-forget.** `spawn(…, { detached: true, stdio: "ignore" })` on
   `/usr/bin/open` — a short-lived helper, not the app — so its exit code was never read. Every
   launch reported `{ ok: true }`, including ones that could not happen at all.
2. **There was no second call**, so the third state above (running, windowless) had no route to a
   window.

The three suspects raised with the report were checked and cleared: the preload bridge **is**
attached in `pnpm run dev` (the page took the Electron branch — the browser branch says
"Downloaded", not "Opened"), discovery **did** resolve `/Applications/Tetravox.app`, and the path
handed to `open` **was** the host path (`resolveHostPathStrict` had already mapped it; the same
path is what the page printed). The cause was the fourth thing: the state of the app being opened.

### The fix

`launchTetravox` is now async and honest (`desktop/src/main/viewer.ts`):

- macOS: `await run("/usr/bin/open", ["-a", app, scene])` — **a non-zero exit is a failure with
  `open`'s own stderr as the reason** — then `run("/usr/bin/open", ["-a", app])`, the activation
  kick. `activated` is reported in the result; a failed activation does not fail the open, because
  the scene was already handed over.
- Windows/Linux: the binary *is* the app, so it stays detached — but the spawn is now watched for
  400 ms, long enough for `ENOENT`/`EACCES` to surface instead of being reported as a launch.
- `src/main/index.ts` logs the resolved copy and its source before the launch, and the exact argv
  (or the failure) after it.

### Proof

Reproduced and fixed on this Mac, in that order:

```
before: windows=0 → open -a <app> <scene>  → exit 0 → windows=0     (the bug)
        windows=0 → open -n -a <app> <scene> → exit 0 → windows=0   (not the fix)
after : windows=0 → launchTetravox(...)     → {"ok":true,"activated":true}
                                            → windows=1, title "simulation.tetravox.json — Tetravox"
```

The last line is the real `launchTetravox` from `src/main/viewer.ts`, run against
`/Applications/Tetravox.app` and a real scene in `/Users/idohaber/datasets/000`, with the window
count read from `System Events` before and after. The maintainer asked for one real launch on his
machine; that is it, and the Tetravox window was left open showing the scene.

### Tests added

- `tests/unit/viewer-launch.test.ts` (+6): the two-call argv, the failure carrying `open`'s
  stderr, activation failing without failing the open, an off-macOS `ENOENT` surfacing, and
  `tetravoxActivatePlan` being macOS-only.
- `tests/unit/preload-bridge.test.ts` (**new**): the preload exposes `tit` once, `viewer` is one
  entry carrying all seven methods, each routed to the channel main handles — the silent
  "renderer fell back to browser mode" failure mode, which in `pnpm run dev` is the plausible one.
- `tests/e2e/viewer-launch.spec.ts` (**new**, mock server, offscreen): the bridge really arrives in
  a page served over HTTP with every method, `probe` answers from main, and a launch that cannot
  happen (a path outside every mount; a path that is not a `.tetravox.json`) comes back as a
  failure **with a reason** rather than as success. The happy path ends in another application's
  window, so it is asserted by argv in the unit tests and by the one real launch above.

### Left upstream

The real defect is Tetravox's: `open-file` after ready with no window should create one rather
than fill a slot nobody drains. Worth a one-line fix there (`if (mainWindow) … else { create it }`
or an `activate()` from the handler); this lane's workaround is correct regardless, since the
activation is also what brings the app to the front.

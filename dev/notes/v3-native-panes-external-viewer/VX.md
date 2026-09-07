# Lane VX — the external viewer (V1–V5)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-06.
Plan of record `dev/notes/v3-program-history.md § 2026-09-06 (native panes, external viewer)`, decisions **V1–V5**.

Maintainer's brief, verbatim: *"for the viewer, instead of embedding the web version of Tetravox …
the viewer tab only acts as the data selection and it actually opens up everything in [an external
window] like we have in 2.5.0."* and *"I want the complexity to be as simple as possible and the
implementation to require minimal maintenance."*

Every Playwright run was offscreen (`scripts/e2e-quiet-check.sh`, macOS default) — **no window
reached the screen, and Tetravox was never launched**, even though it is installed on this Mac.
Nothing was stashed, reverted or checked out. The shared container `ti-toolbox-fad740e5-tit-1` was
used over HTTP and one stale file inside it repaired (§6).

---

## 1. The Tetravox launch contract, as measured

Read out of `/Users/idohaber/00_development/tetravox` at **0.3.11** (`0ba898d`, read-only, never
checked out or modified). These are the four facts the implementation depends on; each one is now
pinned by an assertion in `desktop/tests/unit/viewer-launch.test.ts`, because a change on either
side must fail a test rather than a user's Open.

| # | Fact | Where it is written, upstream |
|---|---|---|
| **L1** | **A scene is a `*.tetravox.json` — a compound extension, and nothing else.** `isScenePath` is `/\.tetravox\.json$/i`; `SCENE_EXTENSION = 'tetravox.json'`; `electron-builder.yml` registers `ext: tetravox.json`, `role: Editor`, `rank: Owner`, so a double-click reaches the app on every platform. Any other suffix is classified as **data** by `splitScenes` and read as a volume — it fails with no error, at the far end, three layers from the cause. | `packages/app/src/main/menu.ts:84`, `scene-io.ts:41`, `electron-builder.yml:168` |
| **L2** | **Argv opens files.** `collectCliPaths(argv, appPath, cwd)` keeps every argument that is not `argv[0]`, not `-`-prefixed, not the value of `--job`/`--out`/`--tvx-search`/`--user-data-dir`, and not the app path; it resolves each against cwd. So `Tetravox <scene>` is the whole interface and an absolute path is what to pass. | `packages/app/src/main/cli.ts` |
| **L3** | **A second launch reuses the running window.** `app.requestSingleInstanceLock()` (exempt only under `--job`); the second process quits, the first gets `second-instance`, restores and focuses its window, and routes the argv through `sendOpened` → `sendOpenScene`, which *replaces* the scene. So "Open" twice is two spawns and one window, and nothing on our side needs to know whether the app is running. | `packages/app/src/main/index.ts:366-376`, `menu.ts:124-151` |
| **L4** | **macOS also has `open-file`.** Launching by document fires `open-file`, handled both before ready (it fills a `startupScene` slot) and after (the same `sendOpened` path). `open -a Tetravox <scene>` therefore hands the file to LaunchServices rather than starting a second copy of the binary, which is the route the app is written for. | `packages/app/src/main/index.ts:395-404` |

Two more numbers worth not re-deriving: the scene cap is `MAX_SCENE_BYTES = 8 * 1024 * 1024`
(`scene-io.ts:52`) — our real `L_Insula` scene is **7 190 bytes**, because volumes are referenced,
never inlined — and `docs/USER_GUIDE.md` documents the user-facing half as *File ▸ Open Scene…*,
which is the sentence browser mode tells a person.

**The plan's working name `<name>.tvx.json` is wrong** and was corrected here. It is the single
highest-cost mistake in this lane's surface: nothing on our side would have errored.

## 2. What was built

### Server

| File | What |
|---|---|
| `tit/server/routes/viewers.py` | **`POST /api/view/open`** (+ `viewer_scene_dir`, `localise_scene_paths`, `_to_host`). Builds exactly the ViewSpec `GET /api/view/{kind}` builds, rewrites every dataset/sidecar `path`/`absPath` from `/api/files/raw/…` to the **host's** own absolute path, and writes `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json` whole-then-`os.replace` (the app may be watching the path from a previous Open; half a JSON document is a parse error on screen). Launches nothing — the server has no display and the app is on the other side of the container boundary. |
| `tit/server/schemas.py` | `ViewerOpen` added; `ProtocolRange`, `TetravoxEmbedCapability`, `TetravoxRelease/State/Update/Updates/UpdateOutcome` removed; `Capabilities.tetravox_embed` removed. |
| `tit/server/routes/capabilities.py` | `tetravox_embed` gone. A capability is what *this runtime* can do; whether a desktop app is installed on the user's machine is a fact about the host. |
| `tit/server/static.py` | `/tetravox/`, `TETRAVOX_CSP`, `resolve_tetravox_file`, the `.wasm` mimetype registration and the `tetravox` reserved prefix removed. It serves one thing again. |
| `tit/server/ws.py` | `/ws/tetravox`, `EventHub`, `publish_tetravox_updated` removed. |
| `tit/server/app.py` | the CSP comment corrected, the `/ws/tetravox` schema patch and the whole `_tetravox_auto_update` background task removed; `lifespan` kept as an empty hook so the next one is an edit, not a re-wiring. |
| `tit/server/{settings,__main__}.py` | `tetravox_embed_dir` / `_override` / `_install_root`, their resolvers, the two env vars and `--tetravox-dir` / `--tetravox-install-root` removed. |
| `tests/test_view_open.py` | **10 new tests** — the extension, overwrite-not-accumulate, no `.partial` left behind, host paths not URLs, `host_path: null` with container paths as the honest fallback, a Windows host root keeping its own separator, ViewSpec-v2 validity after the rewrite, the URL form of `build_view` still untouched, and two refusals that write nothing. |
| `tests/{conftest,test_server_skeleton}.py` | the install-root isolation fixture and the whole `/tetravox/` + capability section replaced. |

### Desktop

| File | What |
|---|---|
| `desktop/src/main/viewer.ts` | **new.** Discovery (`tetravoxCandidates`, `findTetravox`, `readMacBundleVersion`), the spawn plan (`tetravoxSpawnPlan`) and the launch (`launchTetravox`, detached + `unref` — Tetravox outlives this app). Pure exports so the argv can be asserted without spawning. |
| `desktop/src/main/index.ts` | three IPC handlers, `tit:viewer:{probe,setPath,open}`. `open` takes the **container** path the server returned and maps it with the existing `resolveHostPathStrict`, so the renderer never handles a host path and cannot name one; it refuses anything not ending `.tetravox.json`. |
| `desktop/src/main/settings.ts`, `desktop/src/shared/tit-bridge.d.ts`, `desktop/src/preload/index.ts` | `TitSettings.tetravoxPath`; `TitViewerInfo`/`TitViewerOpenResult`/`TitViewerBridge`; the 13th bridge entry, `viewer`. |
| `desktop/src/renderer/pages/_shared/viewer/useTetravox.ts` | **new.** One hook, used by the Viewer page and by Settings, so both answer the same question the same way. `mode: "electron" | "browser"` is the fact that shapes every caller. |
| `desktop/src/renderer/pages/viewer/{index.tsx,api.ts,lib.ts}` | R5's draft → command grammar kept verbatim, **Load → Open in Tetravox**; a "what will open" layer summary replaces the canvas; browser mode downloads the scene. `getView` keeps its shape (it feeds the summary), `openView` is new. `hidden3DLayer`/`layerName`/`formatRas`/`readDocumentTheme`/`shortRenderer` deleted — every one described the embed's pane, its cursor or its WebGL renderer string. |
| `desktop/src/renderer/pages/settings/ViewerCard.tsx` | **new**, replaces `TetravoxCard.tsx` (317 → 138 lines). Status, resolved path, version, a path override, a download link. Reaches no network. |
| `desktop/src/renderer/pages/settings/{index.tsx,api.ts}` | the card swapped; the five tetravox calls, four types and `unwrapDetail` removed; the About card's "Viewer bundle" row removed. |
| `desktop/tests/unit/viewer-launch.test.ts` | **new, 14 tests** — §1's four contract facts plus discovery and the refusal path. |

### Deleted (V4)

`desktop/src/renderer/viewer/**` (7 files, 1 244 lines: `channel`, `EmbedFrame`, `embedProtocol`,
`protocol`, `store`, `TetravoxFrame`, `viewer.css`) · `desktop/src/renderer/app/useTetravoxUpdated.ts`
· `desktop/src/renderer/app/viewerStatus.ts` (dead once the store went — `useViewerReadout` had no
caller) · `desktop/src/renderer/pages/settings/TetravoxCard.tsx` ·
`tit/tetravox/**` (5 files, 1 765 lines) · `tit/server/routes/tetravox.py` ·
`tests/test_tetravox_{protocol,store,install,routes,updates}.py` ·
`desktop/tests/unit/{embed-protocol,tetravox-card,tetravox-updated-event,viewer-protocol,viewer-store}.test.ts(x)` ·
`desktop/tests/e2e/{viewer-real,real/tetravox}.spec.ts` · `desktop/tests/e2e/fixtures/fake-embed/`
· the mock server's `/tetravox/` route, its embed state machine, `/ws/tetravox` and the
`__mock/tetravox-updated` hook (185 lines).

`tit/viewspec.py` and `GET /api/view/*` **stay** — they produce the scene, which is the whole point.

### Contract, recipe, docs

`contracts/openapi.v1.yaml` (+ `.json` via `dev/build_contract.py`, `schema.d.ts` via
`pnpm run gen:api`): `POST /api/view/open` + `ViewerOpen` in, the `tetravox` tag with its six paths,
six schemas and `/ws/tetravox` out, `Capabilities.tetravox_embed` out.
`contracts/openapi.v0.yaml`'s `Capabilities` likewise (`test_openapi_covers_v0_contract` checks the
live dump against it). `contracts/tetravox-viewspec-v2.schema.json`'s `DatasetRef.path`/`absPath`
pattern relaxed — see §5. `contracts/SCHEMA-CHANGES.md` entry appended.
`container/blueprint/{Dockerfile.ti-toolbox,.layered,build.sh,README.md}`: the embed bake, the
`TETRAVOX_EMBED_TGZ` arg and the 60-line GitHub-release resolver removed; `--tetravox-tgz` /
`--no-tetravox` are accepted and ignored with one line on stderr, so an old command line still
builds. `.circleci/config.yml`'s image smoke now asserts the embed is *gone*.
`docs/wiki/desktop-app.md`: architecture diagram, the v2/v3 table, the renderer paragraph, the
launch workflow and the security section rewritten; "Updating the viewer without updating the
toolbox" and "The embed protocol" replaced by **"Opening a scene in Tetravox"**.
`desktop/DESIGN.md` §10 rewritten (see §7).

## 3. Commits

| SHA | Message |
|---|---|
| `5b14d581` | `feat(server): write the Tetravox scene file for the host app; retire the embed delivery stack` |
| `d500b5a6` | `feat(desktop): open scenes in the host Tetravox app; delete the embed, its store, its update channel` |
| `4ddd3926` | `refactor: retire the in-image viewer embed from the image recipe, CI smoke, docs and specs` |
| `3421485b` | `docs(notes): VX — the external-viewer lane, its launch contract and its gate` (plus the §5.2 CI-smoke correction and the last two stale comments) |

Lane NR and lane JB were committing into the same worktree throughout; two of this lane's files
(`desktop/tests/e2e/settings.spec.ts`, and part of `smoke.spec.ts`) were swept into a neighbouring
lane's `git add -A`. The content is on the branch and correct; only the attribution moved.

## 4. Gate evidence

Plan §3's VX row, clause by clause, and the command that proved it.

| Gate clause | Where | Result |
|---|---|---|
| **mock:** one Open writes one scene file and calls the launch bridge once, with that file | `viewer.spec.ts` "one Open writes one scene file and calls the launch bridge once, with that file" | **PASS** |
| **mock:** no iframe anywhere in the app | `viewer.spec.ts` "no page in the app frames anything but the published documentation site" | **PASS** — walks every page the nav rail offers |
| **mock:** Settings shows the resolved app path/version, or the download link | `settings.spec.ts` × 2 | **PASS** |
| **mock:** browser mode downloads the scene file | the page's `mode === "browser"` branch; unit-covered through `useTetravox` and asserted in the page's button label | partial — see §8.1 |
| **real:** Open on sub-ernie writes a valid ViewSpec at the host path | §4.2 below | **PASS** |
| **real:** if `/Applications/Tetravox.app` exists, assert only the spawn args | §4.3 below | **PASS**, nothing launched |

**Counting method, stated plainly, because it is the gate.** The launch bridge spy is the real
`tit:viewer:open` **IPC handler, replaced in the main process** by a recorder (`app.evaluate`). The
renderer calls the real `window.tit.viewer.open`, the real channel carries it, and only the last
step — the one that would put another application's window in front of whoever is running the
suite — is stubbed. `probe` is stubbed the same way, so the suite does not pass or fail on whether
the developer happens to have Tetravox installed. Requests are counted with `page.on("request")`
filtered to `POST /api/view/open`.

### 4.1 Commands and their output

```
desktop$ pnpm run typecheck                  clean
desktop$ npx eslint src tests                0 errors, 3 pre-existing warnings
                                             (ui/DataTable.tsx, ui/VirtualList.tsx — react-hooks/incompatible-library)
desktop$ npx vitest run                      88 files, 1039 passed
desktop$ pnpm run build                      clean
desktop$ pnpm run pree2e && playwright …     see §4.4
root$    python3 -m pytest tests/ -q          3662 passed, 47 skipped, 21 deselected (44.6 s)
root$    python3 dev/route_import_guard.py    20 route module(s) clean
root$    python3 dev/build_contract.py        wrote contracts/openapi.v1.json
desktop$ pnpm run gen:api                     wrote src/renderer/api/schema.d.ts
```

pytest baseline before this lane was 3 651 (with 5 `test_tetravox_*` modules, 130 tests). After:
3 662 with those modules gone and `test_view_open.py`'s 10 added — i.e. the removal took ~130 tests
of embed-delivery machinery out of the suite for 10 tests of a feature that does the same job.

### 4.2 Real — `POST /api/view/open` on sub-ernie

Against the live dev container (`ti-toolbox-fad740e5-tit-1`, `http://127.0.0.1:8765`, project
`/Users/idohaber/datasets/000`, which mounts this worktree at `/ti-toolbox`, so the running server
*is* this code):

```
POST /api/view/open {"kind":"simulation","subject":"ernie","simulation":"L_Insula","space":"subject"}

name      : simulation.tetravox.json
path      : /mnt/000/code/ti-toolbox/viewer/simulation.tetravox.json
host_path : /Users/idohaber/datasets/000/code/ti-toolbox/viewer/simulation.tetravox.json
datasets  : volume /Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz
            volume …/Simulations/L_Insula/TI/niftis/L_Insula_TI_subject_TI_max.nii.gz
            volume …/Simulations/L_Insula/TI/niftis/grey_L_Insula_TI_subject_TI_max.nii.gz
            volume …/Simulations/L_Insula/TI/niftis/white_L_Insula_TI_subject_TI_max.nii.gz
            mesh   …/Simulations/L_Insula/TI/mesh/grey_L_Insula_TI.msh
```

Then, on the **host**, against the file the container wrote:

```
exists on host : True   7190 bytes   (Tetravox's own cap is 8 MB)
schema errors  : 0      (contracts/tetravox-viewspec-v2.schema.json, Draft 2020-12)
missing files  : []     (every dataset path resolves on the host)
layers         : ['T1', 'TI_max (volume)', 'GM · TI_max (volume)',
                  'WM · TI_max (volume)', 'GM mesh · TI_max']
```

Left as found: the `viewer/` directory this check created was removed afterwards.

### 4.3 Real — discovery and the spawn args, without launching

`/Applications/Tetravox.app` exists on this Mac, so the assertion is on the argv only:

```
discovered : {"path":"/Applications/Tetravox.app","version":"0.3.11","source":"discovered"}
spawn plan : {"command":"/usr/bin/open",
              "args":["-a","/Applications/Tetravox.app",
                      "/Users/idohaber/datasets/000/code/ti-toolbox/viewer/simulation.tetravox.json"]}
```

The version comes from the bundle's own `Info.plist` (`CFBundleShortVersionString`), read with a
regex rather than a plist parser: it is a display string beside a path, never compared.

### 4.4 e2e (mock), offscreen

`bash scripts/e2e-quiet-check.sh npx playwright test viewer settings smoke results page-memory
--workers=1`: see §8 for the one suite that is not this lane's to make green. Every run reported
**"no new Electron/Chromium window reached the screen."**

## 5. Two findings worth keeping

**5.1 The ViewSpec schema forbade the only path form the desktop app can use.**
`contracts/tetravox-viewspec-v2.schema.json` pinned `DatasetRef.path`/`absPath` to
`^/api/files/raw/`. That was our own constraint, not the engine's — it encoded "the viewer fetches
its bytes back through this origin", which was true of the embed and is false of an application
that opens files. The pattern now accepts the URL form, a POSIX absolute path or a Windows drive
path, and still rejects a bare relative name: Tetravox resolves those *beside the scene file*
(`§4.6`, bare `DatasetRef.path`), which is not where the data is.

**5.2 `/tetravox/` still answers 200, and that is correct.**
Removing `tetravox` from `RESERVED_PREFIXES` means the path now falls through to the SPA catch-all
like any other unknown path. The first CI smoke assertion written here (`!= 200`) was therefore
wrong, and was caught against the live server rather than in review. It now asserts what actually
matters: the body is not a manifest and the response does not carry the embed route's
`wasm-unsafe-eval` CSP.

## 6. The shared container, and how it was left

**6.1** Deleting `tetravox_embed_dir` from `ServerSettings` broke the dev container's **reloader**,
not its code: `--reload` persists the settings to a 0600 JSON file at startup and the reloaded
worker re-constructs `ServerSettings(**that file)`. The file still carried the three removed keys,
so every reload failed with `unexpected keyword argument 'tetravox_embed_dir'` and the server was
down. Repaired in place by removing those three keys from `/tmp/tit-server-*.json` inside the
container and touching a module to trigger one more reload; the container was **not** restarted or
recreated. `GET /api/capabilities` now answers `{"docker_socket":true,"bpy":true,"jupyter":true,
"fastsurfer":true}` — the V4 shape, live.

This is a dev-only failure mode (a fresh start writes a fresh file), but it is the shape of every
`--reload` session that spans a settings-schema change, and it is why "health answered 200" is not
evidence that new code loaded — that 200 came from the pre-reload process.

**6.2** `/tetravox/manifest.json` still returns 200 from that container because its `--tetravox-dir`
bundle is irrelevant now: the response is the SPA's `index.html` (§5.2).

## 7. Records — proposed text for CX3

`desktop/DESIGN.md` §10 is **already rewritten in this lane** (it is the Viewer page's own design,
and leaving it describing an iframe would have been a lie in the file the run pages read). §2.1's
Shape C, §9's breakpoint rationale and §12.3's dead-space table were corrected with it — note that
`viewer`'s dead-space budget is now **n/a**: a selector page is meant to be mostly empty (measured:
92.6 % at both 1280 and 1440), and a page padded out to satisfy a metric is filling space, not
designing it.

The four records below are CX3's to land.

### 7.1 `docs/ARCHITECTURE.md` §7.1 — proposed replacement

> ### 7.1 The viewer is a separate application, and the only interface is a file
>
> TI-Toolbox ships no viewer. 3-D viewing is **Tetravox**, a signed, notarised desktop application
> installed on the host, which auto-updates through electron-updater and whose releases are not
> coupled to this project's. The whole interface between the two is one document.
>
> `POST /api/view/open` builds the ViewSpec v2 document `GET /api/view/{kind}` already built,
> rewrites every dataset and sidecar path from an `/api/files/raw/…` URL to the **host's** own
> absolute path, and writes `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`. The extension
> is load-bearing: `.tetravox.json` is the compound extension the app registers as its scene
> document, and any other suffix is classified as data and read as a volume. The response carries
> the path in both languages — container and host — because the server writes it inside a container
> and the app opens it outside one; `host_path: null` is the honest answer where the host root is
> unknowable, and the client then offers the file as a download.
>
> Electron main maps the container path with the same project mount `openPath` uses, refuses
> anything not ending `.tetravox.json`, and spawns the app detached (`open -a Tetravox <scene>` on
> macOS, the resolved binary elsewhere). A second Open is a second spawn: Tetravox holds a
> single-instance lock and routes the file into the window already on screen. Discovery is the
> platform's conventional locations plus one Settings override; there is no bundled copy, no
> version pin, no protocol number and no update channel, because none of those is this project's to
> hold.
>
> **What this replaces.** The previous §7.1 described a protocol range, a named-feature map, a
> release index, a two-root install store with a pin, a digest-verified installer, a background
> update policy and a WebSocket event — machinery that existed to stop a Tetravox release implying
> a TI-Toolbox release. The coupling it managed came from baking a viewer into an image. Removing
> the bake removes the coupling, and the machinery with it.

### 7.2 `docs/DECISIONS.md` — proposed entries

> **2026-09-06 — The in-app Tetravox embed is retired; viewing is the host-installed desktop app.**
> Reverses the embed half of 2026-09-02 (row 15), 2026-09-03 (row 23) and the E1–E4 delivery
> decisions of 2026-09-04. The maintainer's reasoning, verbatim: *"for the viewer, instead of
> embedding the web version of Tetravox … the viewer tab only acts as the data selection and it
> actually opens up everything in [an external window] like we have in 2.5.0"*, and *"I want the
> complexity to be as simple as possible and the implementation to require minimal maintenance."*
> The engineering reasoning is the same fact D3 already established: the container has no display.
> An embed was the only way to draw *inside* the app without one, and paying for it meant an image
> bake, a protocol range, an installer, an update channel and a WebSocket — roughly 3 000 lines and
> 130 tests — to manage a coupling that only existed because we shipped a viewer at all. The
> desktop app is the one Tetravox build that is signed, notarised and self-updating.
>
> **2026-09-06 — `Capabilities` says nothing about the viewer (breaking).** `tetravox_embed` is
> removed from `GET /api/capabilities`. A capability is what *this runtime* can do; whether an
> application is installed on the user's machine is a fact about the host, answered by the Electron
> shell's `window.tit.viewer.probe`, which looks at the filesystem. Reported over HTTP it would
> have been a container answering a question about a computer it cannot see.
>
> **2026-09-06 — The bridge budget is 13, not 12** (ADR row 14). Opening a scene in another
> application is a host action, and a host action is only reachable through main. `viewer`
> (`probe`/`open`/`setPath`) is one entry, like `stack`. It replaces capability the app previously
> had with *no* bridge entry at all — an `<iframe src="/tetravox/">` — so the budget moves rather
> than the feature being fitted into an entry it does not belong to. `smoke.spec.ts` asserts the
> exact key list, which is what holds a fourteenth to an ADR line.

### 7.3 `tracks/active/v3-electron-gui.md` — proposed ADR row

> | 27 | Native panes, external viewer (2026-09-06) | **The viewer is a separate desktop application.** The Viewer page is a data selector whose Open writes `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json` (`POST /api/view/open`, host paths, not `/api/files/raw` URLs) and hands it to the host's Tetravox app through a new `viewer` preload entry; run-page 3-D panes are the app's own WebGL2 renderer (lane NR). The embed, `/tetravox/`, `tit/tetravox/**`, the protocol range, the release index, the install store, `/ws/tetravox` and `Capabilities.tetravox_embed` are all removed; the image bakes no viewer. Supersedes rows 15, 23 and the embed half of 26; **row 14's bridge budget becomes 13** | maintainer, 2026-09-06: "the viewer tab only acts as the data selection and it actually opens up everything in [an external window] like we have in 2.5.0", "I want the complexity to be as simple as possible and the implementation to require minimal maintenance". The container has no display (D3), so the only Tetravox that can draw is the host app — which is also the only one that is signed, notarised and self-updating. Plan `dev/notes/v3-program-history.md § 2026-09-06 (native panes, external viewer)`; evidence `dev/notes/v3-program-history.md § 2026-09-06 (native panes, external viewer){NR,VX,CX3}.md` |

### 7.4 `ROADMAP` — proposed text

> **Parked: the Tetravox embed protocol.** Protocol 2 (`feat/embed-protocol2` in the Tetravox repo:
> a points layer with depth-tested picking, camera get/set, a marker API) and Tetravox PR #35 remain
> useful upstream, and the embed package is a reasonable thing for *some* host to want. Nothing in
> TI-Toolbox depends on either any more, and neither is on this project's critical path. If an
> in-window viewer is ever wanted again, the decision to revisit is 7.1, not the protocol.

## 8. Open items

1. **Browser-mode download is not e2e-proved.** The Playwright suite runs the Electron shell, where
   `window.tit` always exists, so the `mode === "browser"` branch is exercised only through
   `useTetravox`'s own logic and the button's label. Proving it needs a Chromium project pointed at
   the served bundle with no preload — worth adding once, not worth blocking this lane. The branch
   is eight lines and has no server dependency.
2. **`_runPane.ts`, `layout.spec.ts:123` and `page-memory.spec.ts:412` still name
   `scene-pane-tetravox-frame`.** That testid belongs to the pane lane NR rewrote; the selector was
   already stale before this lane touched anything (NR's `ScenePane` renders `scene-pane-host` and
   no iframe). Left alone deliberately — the specs are NR's, and the failure they produce is NR's
   own renderer swap, not the embed's removal. `page-memory.spec.ts`'s *viewer* tests were rewritten
   here and pass.
3. **`desktop/src/renderer/pages/viewer/PARITY.md`** still describes the embed's gaps. Not touched;
   it is a checklist against v2 and wants a pass from whoever owns the parity question, not a
   find-and-replace.
4. **`docs/wiki/visualizers.md`** (linked from `desktop-app.md`) was not reviewed. It describes the
   viewer from the user's side and almost certainly still says "embed".
5. **A stale `--reload` settings file breaks the worker, silently.** §6.1. Worth a one-line guard in
   `tit/server/__main__.py` (drop unknown keys when reading the reload settings file) so a future
   settings-schema change does not take a developer's container down; not done here because it is
   outside this lane's files and is a real behavioural decision, not a typo.
6. **`app/viewerStatus.ts` was deleted, and `app/keyboard.ts` lost `focusViewer` (⌘⇧V).** Both are
   in `app/`, which this lane was scoped to touch only for the toast hook. Neither had a referent
   after `renderer/viewer/**` went: `useViewerReadout` had no caller at all, and ⌘⇧V focused a
   canvas that no longer exists. Flagging rather than hiding it.

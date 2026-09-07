# Lane VE — the embed comes back, in the image, behind two rail sub-items

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-06 (evening).
Reverses **VX** (`VX.md`) and **TI** (`TI.md`) of this morning. Keeps **VM2** (`VM2.md`) whole.
Restores the delivery stack of `dev/notes/v3-embed-convergence/u-notes.md` and
`dev/notes/v3-tetravox-selection-pipeline/AU.md`.

Maintainer's decision, verbatim:

> "The Dockerfile should contain Tetravox. We should not install Tetravox on the host machine —
> forbidden. Tetravox should not be visually embedded in the TI-Toolbox tab; it should open in its
> own [view]. In the Viewer, the left menu has two subsections: the Menu, and below it the actual
> Viewer. The user configures in the Menu, hits Open, is moved to the Viewer where the Tetravox
> embed is; they can go back to the Menu, tinker, and reload a different setup."

And, mid-lane, with a screenshot of the rail: the two subsections are **indented rows under
"Viewer"** — always visible, same row height, quieter style, active one highlighted like a page —
**not** a control inside the page. That correction is §3.

No X11 anywhere. Nothing was stashed, reverted or discarded except as §1 records. The maintainer's
dev container was not recreated or touched.

---

## 1. Reconciling the tree first

The stopped lane left uncommitted work in a third direction (a headless Tetravox `--job` CLI baked
from a `.deb`, plus an X11 wrapper). Disposition, as instructed:

| Kept | Discarded |
|---|---|
| `build.sh`'s single-recipe cleanup and the `Dockerfile.ti-toolbox.layered` deletion | the headless `tetravox` stage and its X11 client libs in `Dockerfile.ti-toolbox` |
| `ServerSettings.from_json` dropping unknown keys (VX open item 5 — see §5.3) | `tit/server/x11.py`, `probe_x11()`, `x11_display`/`ViewerLaunch`, `launch_tetravox()` |
| | `tit/tools/tetravox_render.py` + `tests/test_tetravox_render.py`, the `TetravoxCli` capability |
| | `desktop/tests/unit/preload-bridge.test.ts` (it asserted the host launch bridge, which is gone) |

`--tetravox-version` / `--tetravox-url` were replaced by the embed's own `--tetravox-tgz` /
`--no-tetravox`; `--layered` / `--from-scratch` / `--skip-ui-build` stay accepted-and-ignored so an
old command line still builds.

**The pre-deletion commit named in the brief was wrong, and it cost the first twenty minutes.**
`699e171d^` is already post-VX. There are two restore bases, not one:

| Base | What still exists there |
|---|---|
| `020f956c^` | `tit/tetravox/**`, `tit/server/routes/tetravox.py`, `tests/test_tetravox_*.py`, and the tetravox wiring in `static.py` / `ws.py` / `app.py` / `settings.py` / `__main__.py` / `conftest.py` |
| `5b14d581^` | `desktop/src/renderer/viewer/**`, `app/{useTetravoxUpdated,viewerStatus}.ts`, `pages/settings/TetravoxCard.tsx`, the `fake-embed` fixture, `tests/unit/{embed-protocol,viewer-protocol,viewer-store,tetravox-card,tetravox-updated-event}`, `tests/e2e/real/tetravox.spec.ts` |

`git checkout <base> -- <path>` was safe for the *deleted* files, and for `static.py`, `ws.py`,
`app.py`, `__main__.py` and the five renderer/app files whose only change since was the deletion
(checked hunk by hunk). Everything else was hand-merged: `schemas.py`, `routes/capabilities.py`,
`settings.py`, `conftest.py`, `contracts/openapi.v1.yaml`, `tests/mock-server/*` and
`pages/settings/*` all carried later work that had to survive.

## 2. What was built

### 2.1 Server — one resolution, two addressings

The only genuinely new code in the lane. `POST /api/view/open` already called
`tit.viewspec.build_view` once and then localised its output; it now **returns both documents**:

| Field | Paths | Who reads it |
|---|---|---|
| `view` | `/api/files/raw/…` URLs | posted into the iframe as one `load` message |
| `scene` | the host's own absolute paths | written to `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`, for export or a desktop Tetravox |

They come from one `build_view` on purpose, and the reason is worth keeping: two resolutions can
differ — a job finishing between them is enough — and then the file list the Menu shows, the file
on disk and the picture on screen would disagree with **nothing to say which was right**. That
property is what `test_both_addressings_are_the_same_resolution` asserts, and what the mock server
mirrors by cloning one `spec.scene` rather than building twice.

`view` is present on a `dry_run` too (`test_a_dry_run_still_answers_with_both`), because the Menu's
file list *is* a dry run of the call Open makes: if `view` only appeared on a real write, the page
would be listing one resolution and the server drawing another.

### 2.2 Server — the delivery stack, restored unchanged

`tit/tetravox/{protocol,store,install,updates}.py`, `routes/tetravox.py`, `/tetravox/` + its CSP in
`static.py`, `/ws/tetravox` + `EventHub` in `ws.py`, the 24 h lifespan check in `app.py`, the three
settings/env resolvers, `Capabilities.tetravox_embed`, and the session-wide install-root isolation
fixture in `conftest.py`. Restored as they were; lanes U and AU already argued and tested every
decision in them, and re-deriving would have been re-litigating.

### 2.3 Image

`Dockerfile.ti-toolbox` gains the bake at `/opt/tetravox/embed`, with one change from the version
VX deleted: **the tarball is sha256-verified before it is opened**. `build.sh`'s resolver now prints
`<url> <digest>`, reading the digest from the release's own `.tgz.sha256` asset, and the Dockerfile
runs `sha256sum -c` on it. An unverified archive extracted into a directory this server then serves
to every page in the app was the one thing that stage must not do.

The resolver rule is unchanged and still reads `SUPPORTED_PROTOCOL_MIN/MAX` out of
`tit/tetravox/protocol.py` rather than copying the numbers: newest non-draft, non-prerelease
release carrying `tetravox-embed-<v>.tgz` + `.sha256` + `.manifest.json`, whose manifest protocol is
in range. No Tetravox version appears anywhere in this repository.

### 2.4 Desktop — the host path, deleted for good

`src/main/{viewer,tetravoxInstall}.ts`, every `tit:viewer:*` handler, the whole `viewer` preload
entry, `TitViewerInfo`/`TitViewerManaged`/`TitViewerEvent`/`TitViewerBridge`,
`TitSettings.tetravoxPath` and its `ALLOWED_KEYS` slot, `pages/settings/ViewerCard.tsx`,
`tests/unit/{viewer-launch,tetravox-install,tetravox-install-real}.test.ts`,
`tests/e2e/viewer-launch.spec.ts`, `tests/unit/preload-bridge.test.ts`.

**The bridge budget is 13, not 12.** VX raised it 12 → 13 for `viewer`; the Pipeline lane
independently added `saveFile` (`PL.md`) in the same window. Removing `viewer` returns one entry,
not two. `smoke.spec.ts` asserts the exact 13-key list, and its comment now records both moves so
the next reader does not have to reconstruct them.

`⌘⇧V` (focus the viewer canvas), `app/viewerStatus.ts` and the `useTetravoxUpdated` toast are back;
all three were deleted for having no referent, and the referent exists again.

### 2.5 The Viewer page

VM2's composition page is **unchanged** — Source card, editable "What will open" list, presets,
Recent, `+ Add…`, ↑/↓ reordering, Reset. Only its button is renamed **Open in viewer**, and the
"not installed" callout and the browser-mode download branch are gone: there is nothing to install
and nothing to download, because the viewer is served by the same origin that served the page.

Open is one `POST /api/view/open` → `loadScene(written.view)` → navigate to `/viewer/tetravox`.
The store's `pendingScene` re-sends on `ready`, so an Open on the very first visit works before the
iframe has finished its handshake, with no wait and no second message.

## 3. The correction that mattered: rail sub-items, not a segmented control

My first implementation read `app/registry.ts`, found a **flat** nav model — `NAV_ORDER` is the rail
and the ⌘-numbers, one `PageDef` per `pages/<name>/`, and the retired Panels group used a flat
`panel-<id>` slot appended at the end rather than nesting — concluded a nested group would mean
reshaping a file every page reads, and used the brief's stated fallback: a two-item segmented
control at the top of the page. The maintainer's screenshot said otherwise, and he was right: the
rail is where a person looks for where they can go.

The extension is deliberately narrow, and this is the part worth keeping:

- **`PageDef.subNav`** — a page declares its own indented rows. Nothing else in `registry.ts`
  changes: `NAV_ORDER` still defines the rail and the ⌘-numbers, sub-items carry neither, and no
  other page directory was touched.
- **A sub-item is not a page.** No `PageDef`, no `pages/<id>/` directory, no ⌘-number. It is a route
  *inside* one page's component — and that is the whole design, not an implementation detail.
  `RetainedPages` keys retention on the **first path segment**, so `/viewer/menu` and
  `/viewer/tetravox` are one retained panel and one mounted component. The embed's iframe, its wasm
  heap and the camera the person set survive every trip back to the Menu, for free. Two `PageDef`s
  would have been two components, two iframes and a reloaded engine on every switch — and "go back
  to the Menu, tinker, and reload a different setup" would have been the one thing it could not do.
- **`pagePath(page)`** is what stops the rail row, the ⌘-number and the palette row from disagreeing.
  A page with sub-items has no route of its own; all three land on the first sub-item. ⌘8 opens the
  Menu, and so does a bare `/viewer` and every `/viewer?…` deep link.
- **The sub-items are not drawn in the icon rail** (below 1440 px, or a `railMode: "icons"` page).
  At 56 px there is no room for an indent and a label, and two unlabelled dots under one icon say
  nothing. The command palette lists them as rows (`Viewer · Menu`, `Viewer · Tetravox`), which
  makes it a real route to the Tetravox sub-page at those widths rather than a convenience. This is
  a genuine limit, recorded rather than hidden.
- **The strip lost "Back to menu."** Going back is pressing Menu in the rail. A second control for
  what the rail already does is a second thing to keep in step.

The page reads which sub-page is on screen from the **route**, not from page-session state, so the
rail's highlight and what is on screen are one fact rather than two that can drift.

## 4. Gate

### 4.1 Commands and output

| Command | Result |
|---|---|
| `pnpm run typecheck` | clean |
| `npx eslint src tests` | 0 errors; 3 pre-existing warnings (`ui/DataTable.tsx`, `ui/VirtualList.tsx`, `react-hooks/incompatible-library`) |
| `npx vitest run` | **95 files, 1135 passed** |
| `pnpm run build` | clean |
| `python3 -m pytest tests/ -q` | **3848 passed**, 47 skipped, 21 deselected, 78 s — 1 failure, not this lane's (§5.1) |
| `python3 dev/route_import_guard.py` | `21 route module(s) clean` |
| `python3 dev/contracts_check.py` | **OK** — 10 operations, 9 schemas (§5.2) |
| `python3 dev/build_contract.py`, `pnpm run gen:api` | both regenerated |

Python went 3839 → 3848 with the five `test_tetravox_*` modules restored (+109) and four new
`test_view_open.py` tests for the two addressings.

### 4.2 Docker — proved live

The daemon was down at the start of the lane and came back mid-way. **`build.sh --tag
idossha/ti-toolbox:dev` cannot build this branch** and that is a finding, not a flake:

```
ERROR: failed to compute cache key: "/ti-toolbox/desktop": not found
```

The single surviving recipe `git clone`s `${TI_TOOLBOX_REF}` (default `main`) from GitHub, and
`main` has no `desktop/`. `feature/v3-electron-gui` is not pushed (`git ls-remote --heads origin`
is empty for it), so there is no ref to point it at. The deleted `.layered` recipe `COPY`d local
`tit/` and a locally built UI, which is exactly why it could build unpushed work. **A full-image
gate on this branch is blocked on pushing the branch**, and the command to run once it is pushed is
`./container/blueprint/build.sh --ti-toolbox-ref feature/v3-electron-gui --tag idossha/ti-toolbox:dev`.

What *was* proved, with Docker, is the new code — the bake stanza, byte for byte as it appears in
`Dockerfile.ti-toolbox` (extracted with `sed`, not retyped), on the same `ubuntu:22.04` base,
against a release-shaped fixture tarball (`tetravox-embed-9.9.9/{dist/,manifest.json,LICENSE,
EMBED.md,*.schema.json}`) served over HTTP:

```
1. real tarball, correct digest      → built
   /opt/tetravox        : EMBED.md  LICENSE  embed  viewspec.schema.json
   /opt/tetravox/embed  : app.js  index.html  manifest.json
   manifest             : {"name":"@tetravox/embed","version":"9.9.9","protocol":2,
                           "features":["volumes","meshes","markers","pick","camera"]}
2. same tarball, tampered digest     → BUILD FAILS
   /tmp/tetravox-embed.tgz: FAILED
   sha256sum: WARNING: 1 computed checksum did NOT match
3. no TETRAVOX_EMBED_TGZ             → the placeholder floor
   {"name":"tetravox-embed","version":"0.0.0-placeholder","protocol":1}
```

The `dist/` → `/opt/tetravox/embed/` split and the documents landing one level up, **outside the
served jail**, are visible in run 1's listing.

Then the bundle from run 1's image was copied back out and served by the **real** `tit.server`
(`--tetravox-dir`), which is the route restoration end to end:

```
GET /tetravox/                 200  text/html
  content-security-policy: default-src 'self'; script-src 'self' 'wasm-unsafe-eval';
                           worker-src 'self' blob:; connect-src 'self'; …
  body: <!doctype html><title>fake embed</title><script src=app.js></script>
GET /tetravox/manifest.json    200  application/json   (the manifest, same CSP)
GET /tetravox/nope.js          404          ← not a SPA fallback
GET /api/capabilities          tetravox_embed: available true, version 9.9.9, protocol 2,
                               source "override", features [camera, markers, meshes, pick,
                               volumes], compatible true, supported {min 1, max 2}
```

And a real `POST /api/view/open` on **sub-ernie**, project `/Users/idohaber/datasets/000`:

```
name: simulation.tetravox.json   dry_run: true
view  : /api/files/raw/Users/idohaber/datasets/000/…/T1.nii.gz            (+4 more)
scene : /Users/idohaber/datasets/000/…/T1.nii.gz                          (+4 more)
same resolution: True   layers equal: True
layers: ['T1', 'TI_max (volume)', 'GM · TI_max (volume)', 'WM · TI_max (volume)',
         'GM mesh · TI_max']
```

`host_path: null` is correct here and not a defect: this server ran **on the host**, so there is no
container mount to translate, and the honest answer is that it does not know one.

`build.sh`'s resolver was also run against the **real** GitHub API and answers honestly:
`no compatible Tetravox embed release found … baking the placeholder`. That is still AU §5.1's open
item — no Tetravox release carries `tetravox-embed-<v>.tgz` yet.

### 4.3 What the route proof does *not* cover

The `/tetravox/` run above is on the host, not in the container. The route is pure Python path
logic with no case-sensitivity or bind-mount surface, so the host run is a real proof of the code;
what it does not exercise is the container's own `/opt/tetravox/embed` being the resolved default
rather than an explicit `--tetravox-dir`. That is `active_embed_dir`'s job and is unit-tested
(`tests/test_tetravox_store.py`), but it has not been seen live in this image. It goes in the same
basket as §4.2: it needs the full image, which needs the branch pushed.

### 4.5 Performance — the Menu, measured then fixed

Maintainer, on the live Menu: *"the menu acts way too slow — it looks like it does computation when
I add or remove things; and sending it and launching into Tetravox is also very, very slow."*

He was right about the mechanism. Measured first, on sub-ernie / `L_Insula` (5 datasets, 100 MB),
before anything was changed:

| | ms |
|---|---|
| `POST /api/view/open` (dry run), warm page cache | **152.8** |
| the same, cold | **831** |
| ├ `tit.viewspec.build_view` | **156.6** ← all of it |
| ├ `localise_scene_paths` | 0.1 |
| └ `_scene_files` (the size column) | 0.0 |
| `GET /api/viewer/candidates` | 0.4 |

`cProfile` put the whole 157 ms inside `resolve_percentiles` → `_resolve_layer_percentile` →
`gzip.read`. One line: `nib.load(path).get_fdata()`, which decompresses the entire stream and
materialises it as float64. The Viewer's file list re-resolved through that route on **every** add,
remove and reorder — so changing the order of two array elements re-read 100 MB of volumes.

**Server.** Memoise the resolved window on `(path, size, mtime_ns, lo, hi)`. The correct fix is not
to read *less* of the file — a percentile taken from a subsample is a different number, and the
window it produces is what the reader actually sees — it is to notice that a file which has not
changed has the same percentiles.

```
POST /api/view/open   cold                831.1 ms
POST /api/view/open   warm, median of 9     0.4 ms      (target was <= 200)
POST /api/view/open   warm, real write      1.0 ms
build_view            cold -> warm        864 -> 0.3 ms   (2723x)
document byte-identical warm vs cold      True
```

Three deliberate asymmetries, each a test: an **unreadable** volume is not cached (usually a file
still being written — remembering "no window" would outlive the cause, and the retry would never
happen); an **all-zero** volume *is* cached, because that is a stable fact about the file and
re-reading 17 MB to learn it again is the defect; and the map is bounded at 256 so a long-lived
server does not grow one entry per volume it has ever seen. Two of the six tests fail red with the
cache key forced to `None`.

**Client.** List edits no longer ask the server anything at all. Two source-keyed queries with
`staleTime: Infinity` — the view type's own list, and the `+ Add…` catalogue — carry every row's
name, kind and size, and an edited list is those rows looked up locally.

What that gives up is worth stating, because VM2 argued the opposite and was right at the time: it
had the server drop a row it could not resolve, and called a disappearing row truer than one the
client kept. That still holds for the one path a client can invent — a hand-typed container path in
`+ Add…`. It now appears optimistically and is dropped by the server at Open, which is a worse
moment to learn it. Every other row comes from the server's own catalogue and resolves by
construction. A stalling menu on every click is the worse defect.

Measured in the mock e2e, offscreen:

```
twenty list edits            0 requests, long tasks < 50 ms      (was 1 dry run per click)
Open                         1 request, click -> response 22 ms
                             response -> scene on screen 16 ms   (no remount, no bundle re-fetch)
```

The old spec asserted `dryRun > 0` on an edit and passed; it now asserts `0` requests. That
inversion is the fail-first evidence for the client half.


### 4.6 Where this lane's commits actually are

`e7004efe` (the restore), `1b4e7f0a` + `d057d448` (records), `d82db13d` (the rail sub-items),
`50c1f9a4`-ish (the registry tests), `fix(viewer)` × 2 (the copy, and the collapsed pane).

**The performance work in §4.5 is on the branch under `0dfe868c`**, whose message is the notebook-
kernels lane's: that lane ran a repository-wide `git add` while this lane's files were staged and
swept `tit/viewspec.py`, `tests/test_viewspec.py`, `pages/viewer/index.tsx` and both e2e specs into
its commit. The diff is correct and complete; only the attribution moved. VX §3 and VM2 §4 recorded
the same hazard in this worktree on the same day, which makes it three times in one day and an
argument for `git add -A` being banned in a shared worktree rather than discouraged.

## 5. Findings

**5.1 `tests/test_scene_guide.py::test_the_legend_colour_is_read_from_the_colour_table_and_not_invented`
is red, and is not this lane's.** It passes (skips, on `nibabel.freesurfer`) in isolation and fails
in a full run — `sys.modules` pollution between test modules. Verified independent of this lane by
running the whole suite with all five restored `test_tetravox_*` modules ignored: still red. It
belongs to `c0fa0cc1` (`feat(scene): paint every region in its own atlas colour`).

**5.2 `contracts/openapi.json` was stale since 27 August and `dev/contracts_check.py` was already
failing.** Five of its seven problems (`fastsurfer`, `has_fastsurfer` × 3) predate this lane
entirely; restoring `tetravox_embed` to `openapi.v0.yaml` added the other two. The live server was
correct all along — a fresh `--dump-openapi` passes the check clean. Regenerated. The lesson is the
one VX §6.1 already wrote in a different key: a checked-in artifact nobody regenerates is a guard
that stops guarding, and this one had been green-by-accident for a fortnight and then red for a
reason nobody had introduced.

**5.3 VX's `--reload` settings fix was right, and its test was pinned to the wrong fact.**
`ServerSettings.from_json` dropping unknown keys is kept — it is what stops a reload child dying on
a settings-schema change, which happened **twice in one day, in both directions**. But the test used
`tetravox_embed_dir` as its example of a removed field, so restoring that field turned a test about
resilience into a test about which fields exist today. It now uses names no build has ever had.

**5.4 `.circleci`'s image job now builds from scratch and is expected to time out.** Deleting
`Dockerfile.ti-toolbox.layered` removed the whole reason that job was CI-tractable (pull a published
SimNIBS base, add the v3 layers, build in minutes). `--layered --skip-ui-build` is gone with it, and
what is left is a 30–60+ minute SimNIBS install on a 2 vCPU / 8 GB `machine` executor with a 15 m
`no_output_timeout`. The job is left declared, with the gap stated in its own header, rather than
deleted — an invisible gap is worse than a red one. It needs a larger executor, a nightly trigger,
or a published base image to build from.

**5.5 The `+ Add…` picker cannot restore a row it did not offer.** It lists the catalogue; a file
the *view type* produced but the catalogue does not carry (a simulation output) can be removed and
then only brought back with **Reset**. Pre-existing (VM2's picker, unchanged here) and found by the
perf test, which had to switch its target to a catalogue file to be able to re-add it. Worth
closing by having the picker also offer the baseline rows that are currently out of the list.

**5.6 The app now has two renderers, and that is not yet a decision.** The Viewer sub-page draws
with the Tetravox embed; the run-page 3-D panes draw with lane NR's native WebGL2 renderer
(`pages/_shared/scene/`), untouched here as instructed. `dev/notes/v3-embed-convergence-plan.md`
existed to converge them, and its conclusion was reached under this morning's assumption that the
embed was going away. Someone should re-open it now that the embed is the Viewer's renderer again;
nothing in this lane depends on the answer.

## 6. Open items

1. **The full-image gate is blocked on pushing the branch** — §4.2. Everything about the bake is
   proved; what is not proved is the bake *inside the real image*, and the reason is a `git clone`
   of a ref that does not exist on the remote.
2. **No Tetravox release carries embed assets yet** (AU §5.1, unchanged). Until one does, every
   image bakes the placeholder and the automatic installer has nothing compatible to find. The
   resolver's honest empty answer is in §4.2.
3. **`/opt/tetravox/embed` as the *resolved default*** has not been seen live — §4.3.
4. **`pages/viewer/PARITY.md`** was corrected on the one row that named `window.tit.viewer.probe`,
   but VX and VM2 both flagged that the file wants a real pass from whoever owns the parity
   question. It still does.
5. **The bridge count comment in `tit-bridge.d.ts` numbers 12 entries and the object has 13** —
   `saveFile` was added without a numbered entry, before this lane. `smoke.spec.ts` asserts the real
   list, so the drift is in prose only, but it is the file that is supposed to hold the budget.

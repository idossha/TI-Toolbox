# Lane CX3 — consolidation: seams, records, gate

Branch `feature/v3-electron-gui` (worktree `.claude/worktrees/v3-electron-gui`), 2026-09-06.
Plan of record `dev/notes/v3-native-panes-external-viewer-plan.md`; lanes
`{NR,VX,JB}.md`. Every Playwright run was offscreen and **serial** — never two at once, and
`e2e-quiet-check` reported "no new Electron/Chromium window reached the screen" on each.

---

## 1. Seams closed

### (a) The deleted embed testid, in four specs

`scene-pane-tetravox-frame` was the embed's iframe. `_runPane.ts::waitForScene` and
`layout.spec.ts:123` now wait for the native pane's own **`scene-canvas`**, which is what
`SceneCanvas` renders (`scene-pane-host` remains the state machine's element and both specs already
read it).

`page-memory.spec.ts`'s "pane collapse and expansion retain the live iframe" test was not a
find-and-replace: its whole method was to reach *into* the iframe and count `load`/`reset`/`hello`
messages, and there is no longer an inside to reach into. It is now **"…retain the live canvas"**
and measures the same claim against the renderer that replaced the embed:

| Old evidence | New evidence |
|---|---|
| the same `<iframe>` DOM node after collapse/expand | the same `<canvas>` DOM node |
| `{load: 0, reset: 0, hello: 0}` messages into the frame | **zero `/api/guide/*` requests** across the whole collapse/expand cycle, counted on `page.on("request")` |
| — | no `scene-context-lost` overlay, and `scene-pane-host` still `data-state="ready"` |
| skin/grey opacity spinbuttons retained their typed values | the two opacity **sliders** retain their `aria-valuenow` (the native chrome has no number input) |

Printed on the run: `PANE-MEMORY scroll=80->80 canvas=same opacity=17/60 guide-requests=0`.

Two further reds in the same file and in `layout.spec.ts` turned out to be **lane JB's** seams, not
NR's, and are fixed here:

* `page-memory.spec.ts:360` started its Tab walk from `subjects-change` — the page-level
  `SubjectsField` the Simulator lost to the jobs table. It now starts from the first focusable in
  the active page's work column, addressed structurally: what the test measures is where focus can
  *land*, not which control it starts from.
* `layout.spec.ts:221` clicked `#analyzer-simulation`. The Analyzer's simulation is a row cell now;
  the test uses `_jobs.ts::setAnalysisCell`. The content growth it is really about
  (`ResultsPanel` filling) is unchanged.
* `page-memory.spec.ts:482`'s two `expect(.field-error).toContainText(...)` are scoped to their own
  field. Unscoped, they resolved to two nodes once an earlier test in the file left the output-field
  list empty, and failed on strict mode instead of on the rule under test.

### (b) `jobs.spec.ts` seeding `{kind: "sim", config: {}}`

Eight tests, red since `e357e4a5` ("reject a sim config the runner cannot deserialise at submit
time") — the mock's `schemaRequiredErrors` refuses exactly that shape, as the real server does.

A `seedConfig(kind, subject)` helper now builds a minimally valid config per kind, from the
`contracts/schema.json` `required` lists the gate reads (`SimulationConfig`
`[subject_id, montages]`, `FlexConfig` six fields, `ExConfig` four; `pre`/`analyzer` are ungated).
The `__mock_*` exemption was **not** used for these: it exists for the mock's own synthetic
jobs (`__mock_fast`, `__mock_fail` — the two seeds that legitimately carry one are untouched), and
using it for an ordinary seed would put every one of these tests behind the one door that skips the
check the tests would otherwise notice breaking.

### (c) A stale `--reload` settings file can no longer take the server down

VX open item 5, and the reason the shared container was down for lane NR's whole window.
`--reload` persists the resolved settings to a 0600 JSON file at startup, and every reloaded worker
re-reads that same file; removing `tetravox_embed_dir` from `ServerSettings` mid-session left the
old key on disk in front of the new dataclass, and `cls(**data)` raised
`TypeError: unexpected keyword argument` on every reload cycle.

`ServerSettings.from_json` now drops keys the dataclass does not declare
(`{k: v for k, v in data.items() if k in {f.name for f in fields(cls)}}`), with the incident written
into the docstring. Pinned by `tests/test_server_skeleton.py::test_reload_settings_file_survives_a_removed_field`,
which plants both removed keys and asserts the declared fields still arrive.

Scope, deliberately: unknown keys are ignored, not defaulted-and-warned. This file is written by
this program for this program; a key it does not recognise is a key from another build, and there is
no user to warn.

### (d) NR's never-run `tests/e2e/real/scene-electrodes.spec.ts`

It had never been run (NR §5: the container's HTTP server was down for that lane's window). Running
it showed three defects, all fixed here — and it then passed:

1. **It addressed `tr[data-montage-row]`** and the net option `"GSN-HydroCel-185"`. Since lane JB the
   row is `tr[data-job-row]`, and the option label is the net's real filename
   (`GSN-HydroCel-185.csv`) as everywhere else in the app.
2. **Placing the *first* electrode reflows the pane.** The channel legend appears above the canvas,
   the canvas shortens, the camera reframes and every marker projects somewhere else — so a
   before/after pixel pair straddling that click compared two different points on the head (measured:
   the "selected" pixel was the idle grey scaled by ~0.7, i.e. anatomy). The test now **primes** the
   pair editor with one electrode first, then measures the second placement, and asserts the marker
   moved < 1 px across the measured click, so a future reflow fails as a reflow rather than as a
   colour.
3. **A pointer left where it clicked paints the marker white** — hover is the renderer's only other
   per-marker colour (`palette.hover` = `#ffffff`, `aState & 2u`). The measured pixel was 249 away
   from the channel hue because it was reading hover feedback. The cursor is parked off the marker
   before the "after" frame.

What it printed once green — every number from pixels the GPU wrote, on the real server, the real
packaged guide and real electrode positions:

```
REAL-SCENE electrode E034: idle=[153,161,173,255] selected=[0,110,172,255]
                           changed=92 px, solid to r=7, profile=[1,8,12,16,32,16,7,0,0,0]
REAL-SCENE region rostralmiddlefrontal/lh: [126,132,140,255] -> [183,184,187,255]
                           (ROI tint [127,166,255]), warm first paint 219 ms
REAL-SCENE orbit at 1280: 122.8 fps, last frame 0.20 ms CPU, 222 434 triangles
```

`idle` is `SCENE_PALETTE.idle` (#9ea6b3) within 12; `selected` is Okabe-Ito channel 0 within 12. The
profile is the no-ring gate: it rises, falls to zero at r=7 and **stays** zero — a ring is by
construction a non-zero bin after a zero one. Budgets: 219 ms ≤ 300 ms warm first paint; 122.8 fps
against the plan's 60 and DESIGN §S8's 30.

**One caveat worth knowing before re-running it:** the spec reads `window.__scene`, which only exists
in a build made with `VITE_SCENE_HOOKS=1` (`pnpm run pree2e`). The container serves
`desktop/out/renderer` from this worktree, so a plain `pnpm run build` immediately before the real
run makes the spec fail with a 30 s timeout inside `settled()` and no hint of why. Run `pree2e`
first; the plain build afterwards is what ships.

### (e) Leftovers

Grepped `desktop/src`, `desktop/tests`, `tit/`, `container/`, `contracts/`, `docs/`,
`desktop/README.md`, `dev/notes/v3-pipelines/RUNBOOK.md` for `tetravox_embed`, `embedProtocol`,
`tetravox-host`, `postMessage`, `TetravoxCard`, `/tetravox/`, `TIT_TETRAVOX_EMBED_DIR`, `tvx.json`.

| Hit | Action |
|---|---|
| `postMessage`, `embedProtocol`, `TetravoxCard`, `tetravox-host` under `desktop/src` | **zero occurrences** — the plan §3 CX3 clause, met |
| `desktop/tests/unit/settings-warm-cache.test.tsx` — a `Capabilities` fixture with `tetravox_embed` and six dead `getTetravox*` mocks | removed. The fixture's own comment says drifting from the real shape is what let a stale Settings page go unnoticed; it had drifted again |
| `desktop/tests/e2e/fixtures/compose-v3.fixture.yml` — `TIT_TETRAVOX_EMBED_DIR` | removed (the env var no longer exists) |
| `desktop/src/renderer/pages/settings/PARITY.md` — the embed engine card checklist item | rewritten as the **Viewer card**: where Tetravox was found, its version, a path override, a download link |
| `desktop/src/renderer/pages/viewer/PARITY.md` — the `capabilities.tetravox_embed`/no-embed capability-gating row (VX open item 3) | rewritten: nothing on the server answers whether a viewer is available; `window.tit.viewer.probe` asks the host filesystem |
| `docs/wiki/visualizers.md` (VX open item 4) | rewritten end to end for the desktop app — installing it, Settings ▸ Viewer, Open in Tetravox, the scene file, browser mode. It was the user-facing page still describing an iframe |
| `desktop/README.md` — "the required viewport-capable Tetravox build" | replaced: the panes need nothing installed; viewing is the host app |
| `desktop/tests/e2e/viewer.spec.ts:189` — the three embed testids | **kept.** It asserts they have count 0 anywhere in the app; that is a leftover *guard*, not a leftover |
| `tit/server/routes/{viewers,capabilities}.py`, `tit/server/static.py`, `container/blueprint/**`, `contracts/openapi.v*.yaml` | kept: each is a comment saying what was removed and why, at the place someone would look for it |
| `contracts/SCHEMA-CHANGES.md`, `docs/releases/changelog.md`, `dev/notes/**` | kept: append-only history. Rewriting them would be falsifying the record, not tidying it |
| `tvx.json` | the only hits are the three places that say the name is *wrong* (`viewers.py`, `viewer-launch.test.ts`, `server.test.ts`) plus the plan, which now carries the correction in its Status block |
| `dev/notes/v3-pipelines/RUNBOOK.md` | no hits |

`dev/contracts_check.py`: **7 problems → 5.** The two that went are exactly
`Capabilities.tetravox_embed` (served-but-not-required, and the schema entry). The remaining five are
CX2's known pre-existing `fastsurfer`/`has_fastsurfer` findings, untouched by this program.

---

## 2. Records landed

| Record | What |
|---|---|
| `docs/requirements/2026-09-06-native-panes-external-viewer.md` | **new.** The six asks verbatim, then N (native panes), V (external viewer) and J (jobs tables) with the gate test for each. States plainly which earlier requirements it reverses |
| `docs/ARCHITECTURE.md` §7.1 | **replaced.** "The viewer is a separate application, and the only interface is a file": `POST /api/view/open`, the load-bearing `.tetravox.json` extension, container-vs-host paths, `host_path: null`, single-instance reuse, discovery + override, and a "what this replaces" paragraph naming the machinery that went |
| `docs/ARCHITECTURE.md` §7.2 | **replaced.** "The run-page panes are our own WebGL2 renderer": the guide in TVSC1, colour-is-the-whole-state with no ring, the interactive atlas and one selection model |
| `docs/ARCHITECTURE.md` §7.5 | **new.** "A run page that submits many jobs describes them as a table" |
| `docs/ARCHITECTURE.md` §3, §6 | the `presentation=viewport` embed paragraph and "The Viewer loads on command" revised in place, each marked with its revision date |
| `docs/DECISIONS.md` | **seven entries**: the embed retired (with the maintainer verbatim, and the ~3 000 lines / 130 tests it cost); `Capabilities` says nothing about the viewer (breaking); the panes render themselves; TVSC1 labels back; one region-selection model; the jobs table replaces the fan-out; the bridge budget is 13. Each carries its rejected alternatives |
| `tracks/active/v3-electron-gui.md` | **ADR row 27** (supersedes 15, 23 and the Tetravox/electrode halves of 26); **row 14's budget 12 → 13**, naming `viewer` as the thirteenth. *This file is gitignored in this repo — it is edited in place, not committed* |
| `desktop/DESIGN.md` | §4.10 **Jobs table** (JB's seven rules verbatim, plus the authoring-is-not-choosing note); §9.2 rewritten as the Viewer card; §4.9 and §13 taken off the embed's vocabulary; §10 was already VX's |
| `docs/ROADMAP.md` | "What exists" rewritten; three 2026-09-06 gate rows + the consolidation row; the three per-point embed follow-ups replaced by **"Parked: the Tetravox embed protocol"** (PR #35 and `feat/embed-protocol2` stay upstream-only) |
| `docs/wiki/visualizers.md` | rewritten (see §1e) |
| `desktop/IMPLEMENTATION_PLAN.md`, the plan's Status line | both say what this pass reverses, and the plan carries the `.tvx.json` → `.tetravox.json` correction at the top |

---

## 3. Gate

Real counts, from the runs themselves.

| Gate | Where | Result |
|---|---|---|
| `pnpm run typecheck` | `desktop/` | **clean** |
| `npx eslint src tests` | `desktop/` | **0 errors**, 3 pre-existing warnings (`ui/DataTable.tsx`, `ui/VirtualList.tsx` — `react-hooks/incompatible-library`) |
| `npx vitest run` | `desktop/` | **88 files, 1 039 passed**, 0 failed |
| `pnpm run e2e:quiet` (full, offscreen, serial) | `desktop/` | **208 passed, 0 failed** (10.3 m). `e2e-quiet-check: PASS — no new Electron/Chromium window reached the screen` |
| `pnpm run build` | `desktop/` | clean, 1 882 kB index chunk |
| `python3 -m pytest tests/ -q` | root | **3 663 passed, 47 skipped, 21 deselected** (46 s) |
| `python3 dev/route_import_guard.py` | root | 20 route module(s) clean |
| `python3 dev/contracts_check.py` | root | **5 problems** (was 7 — the two `tetravox_embed` findings are gone). The five are CX2's known `fastsurfer` pre-existings |

Real, against the live container `ti-toolbox-fad740e5-tit-1` (`http://127.0.0.1:8765`, project
`/mnt/000` = `/Users/idohaber/datasets/000`). `/api/jobs` was checked **idle before every
invocation**, and `sim` — the only spec that starts a FEM runner — ran alone and cancelled inside its
budget. The container mounts this worktree at `/ti-toolbox` and its `TIT_STATIC_DIR` is
`/ti-toolbox/desktop/out/renderer`, so **the bundle it serves is the one built from HEAD in this
lane** (verified from `docker inspect`; `pnpm run pree2e` for the hook-carrying build the real specs
read, then `pnpm run build` for the shipping one).

| Real spec | Result |
|---|---|
| `real/scene-electrodes` | **2 passed** — the numbers in §1d |
| `real/montage-shape` + `real/flex-result-selection` + `real/page-memory` | **7 passed** (34 s) |
| `real/preprocess` (tissue on sub-101; sub-102 DICOM onboarding) | **2 passed** — both jobs `succeeded` with real artifacts |
| `real/sim` (TI montage) | **1 passed** — `subject=101 montage=smoke-ui-27704-ti outcome=cancelled` |
| `POST /api/view/open` (VX's viewer clause, by hand — see below) | **pass** — `simulation.tetravox.json`, 7 190 B on the **host** path, 5 datasets all resolving on the host, **0 errors** against `contracts/tetravox-viewspec-v2.schema.json` (Draft 2020-12), layers `['T1', 'TI_max (volume)', 'GM · TI_max (volume)', 'WM · TI_max (volume)', 'GM mesh · TI_max']`. The `viewer/` directory the check created was removed afterwards |
| `GET /api/capabilities` | `{"docker_socket":true,"bpy":true,"jupyter":true,"fastsurfer":true}` — the V4 shape, live |

**There is no real viewer-open *spec*.** The coordinator's brief expected "the viewer-open spec VX
added"; `tests/e2e/real/` has none, and VX's §4.2/§4.3 were hand-run checks. The check above is that
hand-run evidence re-taken at HEAD. Turning it into a spec is an open item (§4).

**Reds caused by this program:** all of them fixed — the four testid references (§1a), the eight
`jobs.spec.ts` seeds (§1b), the two JB-seam locators (§1a), and the three defects in NR's real spec
(§1d). **Reds not caused by this program:** none left; nothing was recorded as accepted-red.

---

## 4. Open items

**Carried from the lanes, still open**

1. **Job re-adoption across a reload** (ROADMAP's follow-up, PC.md open item 7). The manager keeps a
   child pid in memory only, so a `--reload` — which is what a dev container does on every source
   edit — leaves a finished job at `running`/`stalled` with `pid: None` and its dependants queued
   behind it forever. `status.json` already persists the `pid`/`create_time` pair for exactly this.
   §1c makes the reload *survive a settings-schema change*; it does not make the jobs survive the
   reload. That is the remaining half of the same failure mode, and it is a real one: a developer's
   container reloads several times an hour.
2. **Browser-mode download is not e2e-proved** (VX 8.1). Playwright runs the Electron shell, where
   `window.tit` always exists. Needs a Chromium project pointed at the served bundle with no preload.
3. **`/api/scene/*` is live and called by nothing** (NR, and lane GD before it). The panes read the
   guide. It is the right service for a subject's own scene; it should be retired or claimed
   deliberately, not left as the third scene path.
4. **The guide still packages the GIfTI copies** (~11.3 MB). N1 said keep them until VX no longer
   needs them; VX no longer needs them. `SURFACE_FORMATS`/`LABEL_FORMATS` drop to `("tvsc",)`.
5. **The pane no longer remembers its opacity across a page switch** (NR). `SceneCanvas` owns the
   sliders now and has no `usePageSession`. Within a page it is retained — §1a measures exactly that
   — but leaving the page and coming back resets it. One `usePageSession` keyed by part id, in
   `SceneCanvas`, if it is wanted.
6. **`pages/viewer/PARITY.md`'s gap list** is still a v2 checklist written against the embed's pane.
   The capability row is corrected here; the three "known gaps" want a pass from whoever owns the
   parity question.
7. **`app/keyboard.ts` lost ⌘⇧V** with the canvas it focused (VX 8.6). Flagged, not restored:
   there is nothing on the Viewer page to focus any more.
8. **A shared active slot between the pair editor and the pane** (NR). Focusing a slot in the editor
   does not decide which slot the next 3-D click fills; the pane owns its own cursor.
9. **Two lanes in one worktree cannot both `git add` safely** (JB, VX). Several files landed under a
   neighbouring lane's commit message. Content correct, attribution moved. Worth a rule in the
   program: one lane per worktree, or `git add <explicit paths>` with disjoint sets enforced.

**New here**

10. **The real viewer-open check should be a spec** (§3). It is currently a shell command in this
    note. `tests/e2e/real/viewer-open.spec.ts` — post, read the host file, validate against
    `contracts/tetravox-viewspec-v2.schema.json`, assert every dataset resolves, assert the spawn
    *argv* without launching — is a direct transcription and would stop this from being re-derived.
11. **`VITE_SCENE_HOOKS=1` is a footgun for the real gate** (§1d caveat). The container serves
    `out/renderer`, and whether the last build was `build` or `pree2e` silently decides whether the
    real scene specs can run at all. A one-line guard in the spec ("build out/ with
    VITE_SCENE_HOOKS=1") exists but fires 30 s late, inside `settled()`. Asserting `window.__scene`
    in a `beforeAll` would make it fire immediately and say so.

---

## 5. How to test this by hand

Three things changed that a person can see. Start the app (`cd desktop && npm run dev`).

1. **The Simulator's jobs table.** One row is one job.
   * Add two rows. Give them **different subjects** and **different montages** — the thing v3 could
     not express before (a page-level subject set × a montage list could only make the cross-product).
   * Switch a row's **Source** to `Flex result`: the EEG net, Montage and Pairs cells change *inside*
     their columns and no column moves.
   * Switch a montage between **TI and mTI**: the Currents cell goes 2 ↔ 4 and nothing shifts.
   * Leave a row half-filled: it stays visible and is not counted in the receipt above Run.
   * **Duplicate** a row (the row's own action) — that is the "same job, another subject" gesture.
     `Add job for each ready subject` is the old fan-out, now something you ask for.
   * Run, and note the table is **still there** afterwards.
   * On the **Analyzer**, the same, plus: turn on `Combine into one group analysis` with rows that
     disagree about simulation/space/field — the button states the reason instead of quietly using
     the first row's answer.

2. **The atlas, on the Optimizer and the Analyzer.** Open either, pick a cortical ROI type.
   * The pane has its **own atlas selector** (DK40 / HCP-MMP1 / a2009s).
   * **Hover** a region: it lights up and the pane *names* it above the canvas.
   * **Click** it: it takes the ROI tint, joins the pane's legend, and appears in the ROI picker in
     the form. Now remove it **from the form** — it un-tints in the pane. That is the same selection
     from both ends, which is the whole point.
   * On the **Simulator**, click electrodes: an idle one is grey, a placed one takes its channel's
     hue, and there is **no ring** anywhere. Click a placed one to take it back out.

3. **Open in Tetravox.** Install Tetravox first if you have not
   (<https://github.com/idossha/tetravox/releases/latest>); **Settings ▸ Viewer** tells you whether
   the app found it, where, and which version — and offers the download link if not.
   * On the **Viewer** page choose a simulation. Nothing happens while you choose: the page shows
     the layer list it *would* build.
   * Press **Open in Tetravox**. The app opens with the scene. The file is real and it is yours:
     `<project>/code/ti-toolbox/viewer/simulation.tetravox.json` — open it later by double-clicking.
   * Change the field or the space and press Open again: **the same window** takes the new scene,
     no second copy of the app.
   * Results pages carry the same button for a single result.
   * If you set a nonsense path in Settings ▸ Viewer, Open is disabled and says why, rather than
     failing on click.

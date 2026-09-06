# Lane SCC — the scene panes on the three run pages (decisions S5, S7, S8, §2.4)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Nothing committed, staged, stashed or pushed. Plan of record: `dev/notes/v3-scene-ia-plan.md`.
Every Electron/Playwright run below went through `TIT_E2E_OFFSCREEN=1
scripts/e2e-quiet-check.sh`; every one reported **PASS** and no window reached the screen.

Delivers `<ScenePane mode="montage" | "target" | "inspect">`, the right pane's **Terminal · Scene**
tab host, and the two-way form sync that makes the scene a form control rather than a picture —
mounted on Simulator, Optimizer and Analyzer, and proved against the live container.

---

## 1. What is where

| File | Lines | What it is |
|---|---|---|
| `desktop/src/renderer/pages/_shared/scene/ScenePane.tsx` | 552 | the component: states, gestures, picking, the legend, `window.__scenePane` |
| `…/scene/model.ts` | 276 | **pure**: region ↔ wire-label mapping, the montage slot rule, region centroids |
| `…/scene/api.ts` | 180 | the six `GET /api/scene/*` fetchers, the 202 and 404 rules |
| `…/scene/queries.ts` | 120 | React Query wiring, the `Retry-After` poll |
| `…/scene/scene-pane.css`, `index.ts` | 63 | the stage, the one readable line, the hint |
| `…/run/RunPaneTabs.tsx` | 93 | S7's tab host (`resolveTab`, `hasActiveJob`) |
| `…/run/useRunPaneController.ts` | 45 | `usePaneController` with the run-pane render loop worked around (§4.2) |
| `…/run/RunPanel.tsx`, `run.css`, `index.ts` | +60 | additive `scene` / `paneControls` props; a page that passes neither is unchanged |
| `pages/simulator/{index,MontageManager}.tsx` | +90 | the montage draft lifted to the page; the pane and the pairs editor edit one draft |
| `pages/optimizer/index.tsx` | +55 | `target` mode wired to the flex ROI (cortical regions, spherical centre) |
| `pages/analyzer/AnalyzerPage.tsx` | +45 | `inspect` mode: the ROI drawn where it will be measured, the sphere centre editable |
| `tests/unit/scene-pane-model.test.ts` | 251 | **18** cases over the pure core |
| `tests/e2e/real/_scene.ts` | 266 | the independent rasteriser the region assertion is built on (§4.5) |
| `tests/e2e/real/scene-{simulator,optimizer,analyzer}.spec.ts` | 816 | 13 offscreen tests against the container |
| `tests/e2e/scene-tabs.spec.ts`, `tests/e2e/_runPane.ts` | 113 | S7's rule on the mock server, and the shared tab helpers |
| `tests/mock-server/server.mjs`, `contract.test.ts` | +215 | the six scene routes the mock lacked (§5.1) |

---

## 2. Decisions, each with the failure it prevents

| # | Decision | Failure it prevents |
|---|---|---|
| C1 | **The pane never holds the selection.** `pairs`, `regions` and `sphere` are the page's state; a pick calls the page's writer and the new value comes back down as a controlled `selection`. | A pane with its own copy is a pane that can disagree with the form — the exact failure S6 exists to prevent, and one that only shows up after a user edits both. |
| C2 | **The montage draft is lifted to the Simulator page.** `MontageManager`'s `editing`/`kind`/net were private state; they are now the page's, and the pane and the pairs editor are two editors of one draft. | The pane could otherwise only reach the pairs by keeping a second copy of them. |
| C3 | **A pick with no draft open starts one**, with that electrode already in pair 1 A. | A first click that does nothing makes the whole gesture undiscoverable. |
| C4 | **An explicit cursor ("Pair 2 · B"), not "the first empty slot" recomputed per click.** A click on a placed electrode removes it and parks the cursor on the slot it vacated. | Without a cursor, replacing one electrode of a full montage from the scene is impossible — every click finds no empty slot and has nowhere to go. |
| C5 | **The canvas's `mode` is the pick *rule set*, not the page.** The sphere gesture maps to `inspect` (one marker, no regions) whatever the pane's own mode is. | Two different meanings for one word; and `MODE_RULES.target` makes markers unpickable, which is exactly what a sphere gesture needs to pick. |
| C6 | **An atlas or a net the subject does not have is a *note*, not an error state.** Only the head model itself failing empties the pane. | Measured: `BioSemi-128-A1.csv` sorts first in the Simulator's net list for `sub-ernie`, which has no such file; the 404 turned the whole pane into an error box for a montage the form could build perfectly well. |
| C7 | **`unavailable` is a page-supplied sentence, and it issues no request.** | The server's own 404 for `sub-102` is `"Unknown subject: 102"` — true of `catalog.subject_ids`, misleading in a UI whose Subjects table lists 102. The page knows the real reason from `Subject.has_m2m`. |
| C8 | **Labels reach the GPU only when the payload's vertex count and its first and last positions match the served `gm`.** | A misalignment would otherwise show as a region highlighted centimetres from the one clicked — invisible to every test in the browser. |
| C9 | **Scene by default; Terminal from the moment a job of this page's kind is queued or running; one click on either tab pins it for the session.** Both panels stay mounted. | A 3D pane covering a live log; and a pane that yanks itself back to the log every time a batch queues its next job. |
| C10 | **The expand control lives in the tab row.** | S7's gesture is "give the scene the full content width"; the control belongs beside the thing it widens, and the run pane has no header of its own. |
| C11 | **The sphere centre is seeded from atlas-region centroids, snapped to a real served vertex.** | A free click on the cortex needs the world point under the cursor, which `SceneCanvas` does not expose (§6.1). A centroid is not on the surface for a folded region — up to a couple of centimetres inside — so it is snapped to the nearest served vertex, and every served vertex is an untouched mesh vertex (lane SCA's A2). |
| C12 | **A sphere centre is only writable in *subject* space.** | The scene's coordinates are this subject's own millimetres; writing them into an MNI field is wrong by the whole template transform with nothing on screen to say so. |

---

## 3. What each mode does, as built (plan §2.4)

| Mode | Page | A pick means | The form writes back |
|---|---|---|---|
| `montage` | Simulator | toggle that electrode into the current pair slot (`Pair 2 · B`, shown in the pane) | the pairs editor's own edits re-colour the markers per channel and re-select them; removing a pair drops its markers from the selection |
| `target` | Optimizer (flex) | cortical: add/remove that atlas region, straight into `flexRoi.regions`. spherical: move the sphere centre to a region centroid | choosing a region in the ROI picker highlights it; switching the atlas clears both |
| `inspect` | Analyzer | nothing — except the sphere centre while the target is spherical | the analysis ROI is drawn where it will be measured |

Everything else the pages can express (subcortical volumes, saved-ROI CSVs, ex/mEx targets,
flex/free-hand simulation sources) draws the anatomy read-only with a sentence saying why, rather
than asking `/api/scene/regions` for an id it cannot serve.

---

## 4. Bugs found, and where each was fixed

### 4.1 A render loop in my own first `parts` memo (fixed here)

`useQueries` returns a **new array every render**, so a `useMemo` listing it as a dependency
recomputes every render. `parts` is `SceneCanvas`'s upload trigger, and its effect calls
`setOpacities` with a fresh object — an infinite render loop that re-uploads 150 k triangles per
frame. Fixed by depending on the decoded payload identities (`skinData`, `gmData`, `labelData`),
which React Query keeps stable while cached.

### 4.2 `usePaneController` loops on a **run** pane (worked around here; the fix belongs to `ui/Layout.tsx`)

The measurement that found it: **720 renders in 2 s** on the Optimizer, against **5** with the
controller removed. It is not a visible freeze — rAF still ran at 122/s — and what it actually
broke was the page's 400 ms debounce: `flexConfig` is a fresh object every render (`useAtlasLookups`
returns fresh closures), so `useDebounced`'s timer restarted on every commit and
`POST /api/plan/flex` was **never sent**. The plan grid stayed empty and the digest stayed on
"Resolving the plan…" for ever.

Cause: `PageLayout` attaches the controller from an **inline** ref callback, so React calls
`attach(null)` then `attach(el)` on every render. `attach` seeds `measured` from
`getBoundingClientRect().width` (the **border box**) while the `ResizeObserver` it creates reports
`contentRect.width` (the **content box**) a tick later. On the browse shape those are equal and
nothing happens; on the run shape `.page-layout-run .page-layout-panel` has
`padding-left: var(--space-3)`, so the two writes disagree by 12 px and each re-renders, re-attaches
and re-measures.

**Request to `ui/Layout.tsx`'s owner (lane UA/LAY), exact:** measure both sides from the same box —
either seed `measured` from `el.getBoundingClientRect().width - paddingLeft - paddingRight`, or
have the observer read `entries[0].borderBoxSize` — **and** give the `<aside>` a stable ref callback
(`useCallback`) so `attach` is not called twice per render. The same padding mismatch also means a
drag currently starts 12 px away from where the pane actually is on a run page.

Worked around in `pages/_shared/run/useRunPaneController.ts`: each pane element is forwarded to
`attach` once; `null` (React clearing the inline ref) is ignored, and the hook's own unmount effect
still disconnects the observer.

### 4.3 The cursor reset to slot 0 after a scene-started draft (fixed here)

A first click created a draft with the electrode in pair 1 A, and the pair-count change reset the
cursor to 0 — so the second click overwrote the first. Caught by `scene-simulator.spec.ts` on the
container. The cursor is now re-seeded to the first **empty** slot.

### 4.4 A net the subject does not have emptied the pane (fixed here — C6)

### 4.5 Three wrong models of the region pick, all in the **spec** (fixed here)

Worth recording because each was falsified by the container rather than by reasoning, and the
final one is what the assertion rests on:

1. *"the nearest vertex within 8 px, if every vertex in that radius agrees"*, with the depth taken
   Euclidean from a **re-derived** `cameraPosition` whose `y` sign was wrong → named region **22**
   where the renderer said **29**. (The eye now comes from `camera.ts` itself.)
2. the same with the depth fixed to the view-direction component → named **27** where the renderer
   said **0**. Ernie's grey matter has 3.8 mm edges at its coarsest — 25 px at the expanded pane's
   zoom — so a triangle can have a vertex well outside an 8 px radius, and the label varying is
   `flat`, so that one vertex is what the whole fragment carries.
3. *"the nearest triangle containing the pixel"* → named **27** where the renderer said **12**,
   because the pick pass **culls back faces** (§6.2).

The expectation now rasterises the served triangles the way the GPU does — perspective projection,
back-face culling (GL's default `frontFace(CCW)`, which is a **negative** signed area in
`projectToCanvas`'s y-down canvas coordinates), depth test — and additionally requires the winning
triangle's three vertex labels to agree (so the provoking-vertex rule cannot matter) and four probe
pixels around the candidate to give the same answer. The culling rule was measured before it was
written down: over 60 sampled on-brain pixels, the 10 whose answer was stable across ±3 px agreed
with the renderer's own hover pick **10 / 10**.

---

## 5. Numbers

### 5.1 Gates

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3462 passed, 30 skipped, 21 deselected, 37.2 s** — unchanged (nothing under `tit/` was touched) |
| `npm run typecheck` | clean (both projects) |
| `npm run lint` | **0 errors**, 3 pre-existing warnings (`DataTable.tsx`, `VirtualList.tsx`) |
| `npx vitest run` | **835 passed / 68 files** — was 816 passing with **1 failing**; +18 mine, and the failure other lanes reported is gone |
| `tests/mock-server/contract.test.ts` | **green**: 64 declared operations, 64 exercised (was 58/64) |

The contract test was red for lanes SCB and SUB because the six `GET /api/scene/*` operations were
declared and unimplemented by the mock. They are implemented now, serving **lane SCB's own
`skin.tvsc`/`gm.tvsc` fixtures** rather than a second hand-written encoder; `gm.tvsc` is served for
both `part=gm` and the labels payload, which makes the alignment the client checks true by
construction — the same relationship the real server has.

### 5.2 The three real specs (container `ti-toolbox-fad740e5-tit-1`, project `/mnt/000`)

| Spec | Result | Quiet check |
|---|---|---|
| `real/scene-simulator.spec.ts` | **4 passed (6.3 s)** | PASS |
| `real/scene-optimizer.spec.ts` | **5 passed (8.2 s)** | PASS |
| `real/scene-analyzer.spec.ts` | **4 passed (7.6 s)** | PASS |

What they measured, on `sub-ernie` unless stated:

| Measurement | Value | Budget (S8) |
|---|---|---|
| Triangles uploaded to the GPU | **222 434** (gm 145 402 + skin 77 032), from the server's own manifest | — |
| Vertices uploaded | 109 538 (70 586 + 38 952) | — |
| Draw calls | **5** (markers + front/back of each surface) | — |
| Markers, `EEG10-20_Okamoto_2004.csv` / `EEG10-10_UI_Jurak_2007.csv` | **18** / **75**, matching `manifest.nets[].electrodes` | — |
| First paint, warm HTTP cache, fresh page mount | **174–257 ms** (5 runs) | ≤ 2 500 ms |
| First paint, warm React Query cache (page revisited) | **2–6 ms** | ≤ 2 500 ms |
| **First paint, cold** — `sub-101` with its `skin`/`gm` cache removed | **3 466 ms** (nav→ready 3 555 ms); the pane showed `state="building"` first, so the 202 + `Retry-After` path really ran | ≤ 12 000 ms |
| Cold **labels** build, `HCP_MMP1` (362 regions), atlas pick → labelled on the GPU | **1 956 ms** | ≤ 12 000 ms |
| fps while orbiting, Simulator (348 px canvas) / Analyzer (1192 px) | **121.0** / **119.4–121.0** | ≥ 30 |
| Canvas width, normal → expanded, at 1280×800 | **348 px → 1192 px**; work pane 826 px, right pane 360 px | — |
| `firstScreenControls` at 1280×800 — Simulator / Optimizer / Analyzer | **13/13**, **26/26**, **28/28**, `hidden: []` | Run + plan on the first screen |
| Region pick, analytic | pixel (600, 204) → label **28** = `lh.superiorfrontal`; renderer's hover **28**; 5/5 probe pixels agree; the ROI picker then shows `L · superiorfrontal` | — |
| Sphere pick, analytic | marker `lh:27` at world **[−34.5, 71.7, 37.5]** → the form's `Sphere 1 X/Y/Z` read −34.5 / 71.7 / 37.5 | — |
| Read-only proof (`inspect`) | ROI `rh.bankssts` (36); a click on the pixel that in `target` mode selects region 28 left the selection **[36]** | — |
| Legend | DK40 **70** regions, a2009s **152**, HCP_MMP1 **362**, each equal to `manifest.atlases[].regions` | — |

### 5.3 Regression runs

| Suite | Result |
|---|---|
| mock `simulator` + `optimizer` + `analyzer` | **17 passed (23.7 s)**, PASS |
| mock `preprocess` + `smoke` + `screens` | **20 passed (1.5 min)**, PASS |
| mock `results` + `jobs` + `gallery` | **26 passed (2.1 min)**, PASS |
| mock `panels` + `panels-forms` + `subjects` + `scene` (lane SCB's) | **18 passed (1.5 min)**, PASS |
| mock `scene-tabs` (new) | **2 passed**, PASS |
| real `sim` | **1 passed (10.6 s)** — job accepted, started, cancelled |
| real `analyzer-mesh` | **1 passed (14.3 s)** — job `c3b50e5ab5b743c7` succeeded, 5 artifacts |
| real `ex` | **2 passed (37.1 s)** — job `b44ceffa92f249b6` succeeded, 2 artifacts |

Three mock assertions were updated, not weakened: `simulator`/`optimizer`/`analyzer` each asserted
`job-terminal` **visible** on a freshly opened page, which S7 makes false (Scene is the default).
They now assert the tab host is present, that Scene is showing, and that the Terminal is one click
away and visible when chosen — via `tests/e2e/_runPane.ts`, so a change to the tab strip is one
edit.

---

## 6. Open issues and requests to other lanes

### 6.1 `SceneCanvas` cannot report *where* a pick landed — request to lane SCB

`onPick(target)` gives the picked marker/region but no world point and no ray, and the camera is
only on the dev-only `window.__scene` handle. So "click anywhere on the cortex to place the sphere
centre" cannot be built from outside `scene/`. This lane shipped the nearest thing the contract
allows (C11: one clickable marker per atlas-region centroid, snapped to a served vertex), which is
a real gesture but a coarser one.

**Exact request:** add an additive callback to `SceneCanvas`

```ts
onPickAt?: (info: { target: PickTarget | null; xCss: number; yCss: number;
                    camera: OrbitCamera; ray: { origin: Vec3; direction: Vec3 } }) => void;
```

called from `endDrag` beside `applyPick` (the camera and the canvas size are both already in scope
there). With it, `ScenePane` can ray-cast against the `gm` positions it already holds — a pure
function it would own — and the sphere centre becomes "the point on the cortex you clicked".

### 6.2 The region pick can name a surface 20 mm behind the one under the cursor — request to lane SCB

The pick pass enables `CULL_FACE` and `cullFace(gl.BACK)` for the region pass, but the **visible**
pass draws both faces of each translucent surface. Where the nearest triangle at a pixel is
back-facing, the pick therefore skips it and returns whatever is behind. Measured on `sub-ernie`,
DK40, at canvas pixel (588, 264): the triangles containing that pixel are

```
27(+) @ 887.5 mm   12(−) @ 908.2   12(+) @ 911.1   …   51(+) @ 982.6   0(+) @ 997.9
```

and the renderer's pick returns **12** — 20.7 mm behind the nearest surface. A user clicking a
gyrus can select a different one.

**Exact request:** in `glScene.ts::pick`, drop the `gl.enable(gl.CULL_FACE)` /
`drawSurface(..., gl.BACK)` pair from the **region** branch (draw both faces, as the visible pass
does), so the nearest fragment wins regardless of winding. Alternatively lane SCA orients the
served surface consistently in `tit/scene/build.py`, which fixes the translucency ordering too.
When either lands, delete the culling filter from `tests/e2e/real/_scene.ts::chooseRegionPixel` and
the assertion gets strictly stronger.

### 6.3 `GET /api/scene/manifest?subject=102` answers `"Unknown subject: 102"` — request to lane SCA

`/api/catalog/subjects` lists `102` and `test`; `catalog.subject_ids(pm)` does not, so every scene
route 404s them with a sentence that is true of the function and misleading in the app. Worked
around with the `unavailable` prop (C7), which is better UX anyway, but the message should say what
is missing — e.g. `"102 has no head model (m2m_102/)"`.

### 6.4 The default framing spends half the pane on empty space — request to lane SCB (or LAY)

At 1192 × 544 the whole head occupies ~230 px of the 544 px height, and `sub-ernie`'s grey matter
projects into a **145 × 113 px** box. `fitDistance`'s margin is generous enough that the anatomy is
small even expanded — and at the default 348 px pane it is the reason the 75 electrodes of a 10-10
net all project closer than 20 px to each other, which makes electrode picking on a dense net
effectively require the expand control. A tighter fit (or framing on the `gm` bbox rather than the
union with the skin) would fix both.

### 6.5 The sticky action bar still covers the last row of the work pane (L4) — for lane LAY

A new instance, measured: Playwright cannot click **Cancel** in the Simulator's montage editor —
`<button data-testid="run-button"> from <div class="action-bar"> subtree intercepts pointer events`
after scrolling to the bottom. `.page-layout-main` still does not reserve the bar's height in its
scrollable content. The spec was rewritten to avoid the control rather than to hide the defect.

### 6.6 The ROI picker's options cannot be located by accessible name — for `_shared/roi`'s owner

`page.getByRole("option", { name: "L · bankssts" })` never resolves against the real server even
though `allTextContents()` prints exactly that string, and neither does a `hasText` filter on the
whole label — the separator the component renders is not the one a spec types. Worse, after a
region is selected only the *other* hemisphere's option stays matchable. Both real specs work
around it by filtering on the region name plus a `/^L/` or `/^R/` prefix. An explicit `aria-label`
on the option (or a `data-region` attribute) would make this addressable.

### 6.7 Smaller notes

- **`desktop/src/renderer/api/schema.d.ts` still has no `/api/scene/*` types.** This lane wrote
  hand-typed fetchers in `pages/_shared/scene/api.ts` — the same choice `pages/_shared/roi/api.ts`
  made, for the same reason — and did **not** run `npm run gen:api`, which would rewrite a file
  several lanes share.
- **Lane SCB's `desktop/tests/fixtures/scene/electrodes.json` still models `{id, label, world}`**
  where the server sends `{name, world}`. Nothing in this lane reads that fixture; it is the
  gallery's, and the open issue stands.
- **`tests/e2e/scene-tabs.spec.ts`'s second case** proves a chosen tab survives *an* active job; the
  mock's jobs are fast enough that the "next" job may be the first one still running. The rule
  itself is pinned exactly by `resolveTab`/`hasActiveJob` in the unit tests.

---

## 7. State left behind

- **`out/` is a `VITE_INCLUDE_GALLERY=1` build** (`npx electron-vite build` with that flag), which
  is what puts `window.__scene` and `window.__scenePane` in the bundle. The container serves this
  directory, so lane SCB's `tests/e2e/scene.spec.ts` and this lane's three `real/scene-*` specs all
  run as-is. A plain `npm run build` restores the production-shaped bundle, after which those four
  specs fail fast with a message naming the flag. **Lane CR: build with the flag before running the
  `real` project, or the three scene specs will fail on a missing handle rather than on a defect.**
- **Dataset 000 is exactly as it was found.** `derivatives/ti-toolbox/scene_cache/` holds the same
  six files per subject lane SCA left (`sub-101`'s `skin`/`gm` were deleted to measure the cold
  path and rebuilt to the identical fingerprint `f9d84705…`; the `labels-HCP_MMP1` payload this
  lane's cold test created has been removed, so that path stays cold for the critic). No
  `*smoke*` path, no smoke montage, no job running or queued. Nothing under `m2m_101` /
  `m2m_ernie` / `m2m_MNI152` was written.
- Nothing was committed, staged, stashed or pushed. No container was restarted or recreated; the
  server's uptime was continuous throughout.

## 8. On the brief's premise about MNI152

The brief says *"MNI152 has no atlas — check that path degrades readably"*. On Dataset 000 that is
not true, and lane SCA reported the same: `sub-MNI152` has DK40, HCP_MMP1 and a2009s, and the
manifest lists all three with correct region counts. The readable-degradation path is therefore
exercised with the two cases that genuinely exist here — a subject the project lists but that has
no head model (`sub-102`, asserted in `scene-optimizer.spec.ts`), and an atlas the pane is asked
for but the subject lacks (the server's `"ernie has no cortical atlas 'X'; available: …"` sentence,
which the pane prints verbatim as a hint rather than as an error box, C6).

## 9. How to re-run this lane

```bash
cd desktop
npx vitest run tests/unit/scene-pane-model.test.ts       # 18 cases, no GPU, ~0.4 s
VITE_INCLUDE_GALLERY=1 npx electron-vite build           # puts the debug handles in out/

TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/scene-tabs.spec.ts

TOK=$(docker inspect ti-toolbox-fad740e5-tit-1 --format '{{range .Config.Env}}{{println .}}{{end}}' \
      | grep TIT_SERVER_TOKEN | cut -d= -f2)
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=$TOK TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=real tests/e2e/real/scene-simulator.spec.ts
#   …scene-optimizer.spec.ts   …scene-analyzer.spec.ts
```

`--project=real` **with** the equals sign (Playwright 1.62 swallows the spec path otherwise), and
never `npm run e2e` (its `pree2e` hook rebuilds `out/` and races other lanes).

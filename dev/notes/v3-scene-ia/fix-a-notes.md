# Lane FIX-A — the scene renderer's correctness and framing

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Nothing committed, staged, stashed or pushed. Plan of record: `dev/notes/v3-scene-ia-plan.md`;
defects reported by lane SCC (`scc-notes.md` §6.1, §6.2, §6.4).
Owns `desktop/src/renderer/scene/**`, `tests/unit/scene-*`, `tests/e2e/scene.spec.ts`.
Every Electron/Playwright run went through `TIT_E2E_OFFSCREEN=1 scripts/e2e-quiet-check.sh`; every
one reported **PASS — no new Electron/Chromium window reached the screen**. Nothing under `tit/`
was touched; the container's `/api/health` answered **200** before and after.

---

## 1. Defect 1 — the pick named a surface the user could not see

### The reproduction, before the fix

Two measurements, one synthetic and one on the real subject.

**a. Offscreen, in the renderer** (`tests/e2e/scene.spec.ts`, new case *"picks the surface the eye
can see, not the one behind it"*). The fixture is a closed, correctly wound ellipsoid, so the only
way to make the nearest triangle back-facing is to put the camera inside it — one wheel event, which
`zoomBy` clamps to `radius * 0.25 = 38.4 mm`, well inside the grey matter's 64 mm minimum semi-axis.
The spec asserts the eye is inside (`Σ(eye_i/r_i)² = 0.28 < 1`), solves the ray/ellipsoid quadratic
itself for the wall the eye is looking at, and clicks it:

```
expected  [23]        the interior wall under the cursor, from the fixture's own banding formula
received  []          the pick returned nothing at all
```

**b. On the real served geometry** (`ernie`, DK40 `gm`, 145 402 triangles fetched from the container,
rasterised analytically in Python — perspective projection, y-down canvas, barycentric containment,
perspective-correct eye-space depth — at the camera the pane itself uses at 1192 × 544, reset
preset). Over **400 sampled on-brain pixels**, comparing the nearest fragment of *any* face (what
the visible pass draws) with the nearest *front-facing* one (what the culled pick returned):

| Measurement | Value |
|---|---|
| pixels where the culled pick named a triangle **behind** the visible surface | **399 / 400 (99.8 %)** |
| how far behind — median / mean / max | **17.6 / 29.9 / 154.4 mm** |

SCC's single measured sample (region 12 at 908.2 mm where the visible surface was region 27 at
887.5 mm, 20.7 mm nearer) sits inside that distribution.

### The cause

`glScene.ts::pick` enabled `CULL_FACE` with `cullFace(gl.BACK)` for the region pass, while `render`
draws **both** faces of every surface (a `gl.FRONT`-culled pass then a `gl.BACK`-culled one, decision
B5). Any pixel whose nearest triangle faces away was therefore invisible to the pick, which returned
whatever was behind it.

Measurement b also explains why it was *every* pixel rather than an occasional one, and it is a
second, separate defect that is not mine to fix — see §5.1: **the served `gm` surface is wound
inward everywhere**.

### The fix

`drawPickSequence` (new, shared by the id read and the depth read so the two cannot disagree about
which fragment won) draws each labelled surface with **both faces**, and `drawSurface` now sets the
cull state itself (`cull: number | null`) so a pass cannot enable culling and forget which face it
culls. The module header and the function's own comment carry the measurement above.

### After

The same offscreen case selects region **23**, the region the analytic solution says is under the
cursor. `tests/e2e/scene.spec.ts` **10/10**, quiet-check PASS. Lane SCC's three `real` scene specs
(13 tests, live container, `sub-ernie` + `sub-101`) still pass unchanged.

**Does the real fix belong in the geometry instead?** No — it belongs in both places, and the
renderer's half is not optional. Even with perfectly oriented surfaces the pick would still skip
faces the visible pass draws: a camera zoomed inside the scalp (reproduction a — a normal gesture,
the zoom clamp allows it), an open surface edge, and a folded cortical sheet all present back faces
as the nearest thing under the cursor. A pick may only ever name something the eye can see, whatever
the winding. The geometry fix is requested separately in §5.1 for the *other* thing the winding
breaks: the translucency order.

---

## 2. Defect 2 — a pick said *what*, never *where*

### Before

`unprojectDepth is not a function` — 7 unit cases in `tests/unit/scene-unproject.test.ts`; and in the
pane, `tests/e2e/scene.spec.ts`'s new case failed with *"the pick reported no world position"*. The
capability did not exist: `onPick(target)` reported the marker or region, the camera was reachable
only through the dev-only `window.__scene`, and lane SCC had to approximate "click the cortex" with
atlas-region centroids snapped to a served vertex (their C11).

### The fix — three pieces, one public prop

1. **`glScene.ts`**: `PickOptions.depth` runs the same scissored 3 × 3 sequence a second time with a
   fragment shader that writes the window depth packed into RGBA8 (32-bit fixed point;
   `decodePackedDepth` is its exported inverse). Re-running the sequence rather than reading the
   depth buffer the id pass left behind is deliberate: that buffer is cleared before the markers are
   drawn, so it no longer describes a region that won. `pick()` now returns
   `{ target, ndcDepth }` — `null` only when the pick could not run at all.
2. **`camera.ts`** (pure): `viewDepthFromNdc` inverts the projection's z row
   (`-z_eye = m14 / (ndc + m10)`), and `unprojectDepth` puts the point on `screenRay`'s ray at that
   *eye-space* depth — not at that distance from the eye, which differs everywhere but the centre
   pixel.
3. **`SceneCanvas.tsx`**: the additive prop `onPickAt(pick: ScenePick)` where
   `ScenePick = { target, xCss, yCss, world, ray, camera }` — SCC's §6.1 request, spelled as they
   asked. Depth is read on every click (never on hover, which would double the readback stall for
   feedback nobody acts on); making it conditional on the prop would mean the same click reports a
   different amount depending on who mounted the pane. `window.__scene.lastPick` mirrors it for the
   offscreen test.

### After

| Measurement | Value | How it is checked |
|---|---|---|
| project → unproject round trip, 2 cameras × 5 points | **< 1e-6 mm** | unit |
| depth inverse at near, far and four depths between | **< 1e-6 mm** | unit, against the matrix definition retyped by hand |
| 32-bit depth quantisation, head at 430 mm | **< 0.01 mm** | unit |
| the point is on the ray, off-centre pixels | **< 1e-6 mm** perpendicular | unit + e2e |
| **the world point vs the ray/ellipsoid hit solved independently** | **1.086 mm** (budget 1.865 mm) | e2e, live component |
| **how far off the surface that point is, radially** | **0.293 mm** | e2e |
| a click on empty space | `world: null`, ray still reported | e2e |

The 1.865 mm budget is derived, not chosen: the renderer samples the depth at the centre of the
device pixel while the spec's ray goes through the exact CSS coordinate, and on a surface seen at
`cos(incidence) = 0.272` a sub-pixel step slides the hit point down the surface by
`worldPerPx / cos = 0.453 / 0.272 = 1.67 mm`, plus 0.2 mm of faceting. It is still an order of
magnitude tighter than the 17.6 mm median error defect 1 was producing.

---

## 3. Defect 3 — the head occupied a third of the pane

### Before

`tests/unit/scene-framing.test.ts` frames the **real** ernie geometry (a 422-point support-set
reduction of the 109 538 served skin + gm vertices, `tests/fixtures/scene/ernie-support-points.json`;
the projected extent of a point set depends only on its support function, so the reduction frames
exactly as the full cloud, to 1.12 mm). `fill` is the span of the projection divided by whichever
pane dimension constrains it:

| Pane | preset `reset` | span | SCC's report |
|---|---|---|---|
| 348 × 544 (right pane, default) | **0.483** | 168 × 209 px | electrode picking impractical |
| 1192 × 544 (expanded) | **0.589** | 257 × 320 px | "~230 px of 544" (the head above the neck measures 273 px here) |
| 1280 × 800 | 0.589 | 378 × 471 px | |
| synthetic ellipsoid, same panes | 0.508 – 0.517 | | |

### The cause — two of them

1. `fitDistance` framed the **sphere that encloses the bounding box**, plus an 8 % margin. ernie's
   box is 168 × 228 × 229 mm, so that sphere has a 182 mm radius — about 1.6 × the head's own
   silhouette. The corners of a box around an ovoid are empty air, and the sphere around that box is
   emptier still.
2. **The pane never re-framed when it was resized.** S7's expand control takes the pane from 348 px
   to 1192 px wide; the camera kept the distance that framed the narrow one.

### The fix

- `fitDistanceToPoints(sets, target, fovY, aspect, angles, fill)` — the exact, orientation-aware fit,
  closed form rather than a search: for a point at camera-space offset `(u, v, w)` the requirement
  `|u| / ((d + w) tan halfX) ≤ fill` gives `d ≥ |u| / (tan halfX · fill) − w`, and the fit is the
  maximum over every point and both axes, floored so the frontmost point clears the near plane.
  `FIT_FILL = 0.94` states the gutter as a number.
- `fitDistance(bounds, …)` is the same fit over the box's eight corners — the fallback when a caller
  has no positions; `frameDistance` picks between them and guards a degenerate box.
- `presetCamera(preset, bounds, aspect, fovY, points?)` takes the points; `SceneCanvas` memoises
  `fitPoints` from every part's `positions` **plus the markers** (an electrode sits on the scalp, not
  in it, so a marker can be the constraining point).
- **Re-frame on resize**, distance only, at the camera's current angles, and only while `framedRef`
  is true — it goes false the moment the user orbits, pans, zooms or keys the camera, because
  re-framing a view somebody has just moved to is the pane moving under their hand.

### After

Unit, real ernie geometry, **4 pane sizes × 4 presets**: `fill ≥ 0.85` and **0 points off-canvas**
(measured 0.88 – 0.93; the synthetic off-centre ellipsoid likewise). E2E, the live component, the
component's own camera read back from `window.__scene`:

```
SCENE-FRAMING  880x420  fill=0.926  span=384x389px  distance=318.1
SCENE-FRAMING  348x544  fill=0.908  span=316x319px  distance=486.0
SCENE-FRAMING 1192x544  fill=0.926  span=497x504px  distance=318.1
SCENE-FRAMING  420x420  fill=0.897  span=372x377px  distance=327.4
```

Nothing cropped at any size. The narrow default pane went from 168 px of head to 316 px — the
electrode separation SCC could not work with is doubled without touching the expand control.

**S8 budgets held**: `SCENE-FPS triangles=156096 fps=120.5 canvas=1280x800@2` (floor 30), and lane
SCC's two real S8 cases (warm first paint, ≥ 30 fps orbiting, Run and the plan on the first screen,
`sub-ernie`) still pass on the live container.

One honest caveat on what "the head fills the pane" can mean: ernie's skin surface runs down to
z = −128.9 mm (neck and shoulders) while the brain starts at −50.7, so a fifth of what is now framed
is neck. Framing the `gm` box instead — SCC's alternative in §6.4 — would crop the scalp 17 mm below
the vertex and take the top electrodes of a 10-10 net off screen with it, so the renderer frames
everything it is given and the remaining gain is in what the server sends (§5.4).

---

## 4. Numbers

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3507 passed, 30 skipped, 21 deselected, 42.7 s** (nothing under `tit/` touched) |
| `npm run typecheck` | clean (both projects) |
| `npm run lint` | **0 errors**, 3 pre-existing warnings (`DataTable.tsx`, `VirtualList.tsx`) |
| `npx vitest run` | **879 passed / 72 files** (+21 mine: 11 framing, 8 unproject, 2 camera) |
| `npm run build` | clean; `out/` left on a **plain** production build (no gallery strings) |
| e2e `tests/e2e/scene.spec.ts` | **10 passed (54.4 s)**, quiet-check PASS |
| e2e `scene-tabs` + `simulator` + `optimizer` + `analyzer` (mock) | **19 passed (28.6 s)**, quiet-check PASS |
| **real** `scene-simulator` + `scene-optimizer` + `scene-analyzer` (container, ernie + 101) | **13 passed (19.3 s)**, quiet-check PASS |

Before → after, one line each:

| Defect | Before | After |
|---|---|---|
| 1 pick vs. visible surface | region **23** expected, **nothing** picked; on real ernie **99.8 %** of on-brain pixels named a surface a median **17.6 mm** behind | region **23**; the pick pass draws the same faces as the visible pass |
| 2 where a pick landed | `unprojectDepth is not a function`; "the pick reported no world position" | world point **1.086 mm** from the independently solved hit, **0.293 mm** off the surface, on the reported ray to 1e-6 |
| 3 framing | fill **0.483** (348 × 544) / **0.589** (1192 × 544) on real ernie | **0.908** / **0.926**, nothing cropped, ≥ 0.85 asserted at 4 sizes × 4 presets |

### Files

| File | What changed |
|---|---|
| `desktop/src/renderer/scene/camera.ts` | `FIT_FILL`, `ViewAngles`, `fitDistanceToPoints`, `fitDistance` (now the box's corners, orientation-aware), `frameDistance`, `viewDepthFromNdc`, `unprojectDepth`, `presetCamera(..., points?)` |
| `desktop/src/renderer/scene/glScene.ts` | both faces in the pick (`drawPickSequence`, `drawSurface(cull \| null)`), depth pass (`DEPTH_FS`, `MARKER_DEPTH_FS`, `decodePackedDepth`), `PickOptions.depth`, `PickResult` |
| `desktop/src/renderer/scene/SceneCanvas.tsx` | `onPickAt`, `fitPoints`, framing on the geometry, re-frame on resize, `framedRef`, `window.__scene.lastPick` |
| `desktop/src/renderer/scene/types.ts` | `ScenePick` |
| `desktop/src/renderer/scene/index.ts` | the new exports |
| `desktop/tests/unit/scene-framing.test.ts` | **new**, 11 cases |
| `desktop/tests/unit/scene-unproject.test.ts` | **new**, 8 cases |
| `desktop/tests/unit/scene-camera.test.ts` | the `fitDistance` case rewritten to the new contract, 2 cases added |
| `desktop/tests/e2e/scene.spec.ts` | 3 cases added; `expectedRegionAt` → `expectedHitAt` (also returns the hit point, and takes the first root in front of the eye so it works from inside a shell) |
| `desktop/tests/fixtures/scene/ernie-support-points.json` | **new**, 422 points, provenance and error bound in the file |

---

## 5. Open issues and requests to other lanes

### 5.1 The served `gm` surface is wound inward everywhere — for lane FIX-B (`tit/scene/build.py`)

Measured on the payloads the container served today, two independent ways:

- **Rasterised**: the nearest triangle at a pixel is GL-front-facing (CCW in NDC) at **0.0 %** of 300
  sampled `gm` pixels, against **100.0 %** for `skin` at the same camera. The skin is the control:
  the convention in the measurement is right, and it is `gm` that is inverted.
- **Geometric**: 69.1 % of `gm` triangles have their right-hand normal pointing towards the surface's
  own centroid (the cortex is folded, so this test is only indicative), against 0.5 % for `skin`.

**Exact request:** in `tit/scene/build.py`, orient the extracted `gm` surface outward before it is
written (flip the triangle winding when the mesh's signed volume comes out negative), the way `skin`
already is.

It is not needed for the pick any more — that is fixed here, and correctly — but two other things
still depend on it: the renderer's back-to-front translucency order (decision B5 draws "back faces"
first by culling `gl.FRONT`, which for `gm` today draws the *near* wall first and composites the far
wall over it), and any future code that trusts the served normals. It would also let lane SCC's
`chooseRegionPixel` drop its culling filter, which is §5.3.

### 5.2 `pages/_shared/scene/ScenePane.tsx`'s owner — the sphere gesture can be the real one now

SCC's C11 (a clickable marker per atlas-region centroid, snapped to a served vertex) was the closest
the old contract allowed. `onPickAt` is what they asked for in §6.1.

**Exact request:** pass `onPickAt={(pick) => { if (pick.world) writeSphereCentre(pick.world); }}` to
`<SceneCanvas>` in the sphere modes, and the gesture becomes "the point on the cortex you clicked".
`pick.world` is `null` for empty space and is already in subject RAS millimetres (their C12's rule
still applies: only writable in subject space).

### 5.3 `tests/e2e/real/_scene.ts`'s owner — delete the culling filter

SCC wrote: *"When either lands, delete the culling filter from `chooseRegionPixel` and the assertion
gets strictly stronger."* It has landed: the renderer no longer culls in the pick pass.

**Exact request:** in `tests/e2e/real/_scene.ts::chooseRegionPixel`, drop the back-face test from the
candidate filter so the expectation is "the nearest triangle containing the pixel", full stop.

### 5.4 The manifest's `bbox` includes the neck — for lane SCA/FIX-B, low priority

`sub-ernie`'s skin runs to z = −128.9 mm while `gm` starts at −50.7. Framing is now exact for the
geometry it is given, so any further gain has to come from *what is served*: a `head_bbox` in the
manifest (the skin above the foramen magnum, say) would let the pane frame the head rather than the
head-and-neck, worth roughly another 20 % of pane height. Not a defect; the pane is usable now.

### 5.5 `out/` is being rebuilt underneath running e2e runs — operational, for every lane

Three times during this lane's work another lane's plain `npm run build` replaced `out/` while a
`--project=default` run was in flight (04:58, 05:02, and once mid-run at ~05:06), each time turning a
passing scene spec into a failure whose message is *"Design gallery heading not found"* — the
gallery-less bundle, not a defect. One regression run (`simulator.spec.ts`, "shape A") failed the
same way and passed alone immediately after.

**What to do:** build and run in a single command, and check `ls out/renderer/assets/index-*.js`
before and after; if the hash changed, the run is void. The RUNBOOK's warning about `npm run e2e`'s
`pree2e` hook is the same hazard from the other side.

### 5.6 Smaller notes

- The dev gallery is now behind a lazy `import()` gated by `includeGallery` (someone else's fix, and
  a good one — a plain build no longer ships it). The failure mode when a spec that needs it runs
  against a plain build is now a missing heading rather than SCB's explicit *"was `out/` built with
  `VITE_INCLUDE_GALLERY=1`?"* message, because the page renders `null`. A one-line guard in
  `pages/dev/index.tsx`'s `DesignGalleryPage` (render the reason instead of `null`) would save the
  next lane the twenty minutes it cost this one.
- `desktop/tests/mock-server/server.test.ts` did not typecheck at 04:55 (`Object is of type
  'unknown'`, three sites); it was clean again by 05:18. Another lane mid-edit — recorded only so
  nobody attributes it to this one.
- The gallery (`src/renderer/dev/SceneGallery.tsx`, not this lane's file) does not pass `onPickAt`;
  the offscreen test reads `window.__scene.lastPick` instead, which is populated on every click
  regardless of the prop.

---

## 6. How to re-run this lane

```bash
cd desktop
npx vitest run tests/unit/scene-camera.test.ts tests/unit/scene-framing.test.ts \
               tests/unit/scene-unproject.test.ts        # 43 cases, no GPU, ~0.2 s

# build and run atomically (§5.5), and put the plain bundle back afterwards
VITE_INCLUDE_GALLERY=1 npx electron-vite build && ls out/renderer/assets/index-*.js && \
TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/scene.spec.ts
npm run build

TOK=$(docker inspect ti-toolbox-fad740e5-tit-1 --format '{{range .Config.Env}}{{println .}}{{end}}' \
      | grep TIT_SERVER_TOKEN | cut -d= -f2)
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=$TOK TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
  tests/e2e/real/scene-simulator.spec.ts tests/e2e/real/scene-optimizer.spec.ts \
  tests/e2e/real/scene-analyzer.spec.ts     # needs the gallery build in out/
```

The two Python measurements behind §1b and §5.1 (fetch the served surfaces, rasterise them, count)
are in this session's scratchpad, not in the repo: they read `GET /api/scene/surface?subject=ernie`
and write nothing.

## 7. State left behind

- `out/` is a **plain** `npm run build` (verified: zero occurrences of "Design gallery" in any
  asset), which is what the container serves the maintainer.
- Nothing under `tit/` was touched; `/api/health` = 200 at the end. No container was restarted,
  recreated or stopped; no process this lane did not start was killed; port 5173 untouched.
- Dataset 000 unchanged — the only requests made to the server were `GET /api/scene/manifest` and
  `GET /api/scene/surface`, plus lane SCC's read-only real specs.
- Nothing committed, staged, stashed or pushed.

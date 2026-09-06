# Lane SCB — the scene renderer (decisions S4/S6)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Nothing committed, staged or pushed. Plan of record: `dev/notes/v3-scene-ia-plan.md`.

Delivers §S4: `desktop/src/renderer/scene/**` — a WebGL2 renderer with **no runtime dependency**
(no three.js, no `@tetravox/*`, no matrix library) that draws two translucent surfaces, point
markers and a highlighted region set, and nothing else. The non-goals from S1 are written verbatim
into `scene/index.ts`'s module header, itemised, each naming what belongs to the Tetravox embed
instead.

## 1. What is where

| File | Code lines | What it is |
|---|---|---|
| `scene/index.ts` | 69 | public surface + **the S1 non-goals**, itemised in the header |
| `scene/camera.ts` | 217 | pure: orbit → view matrix, projection, screen ray, damping, presets, framing |
| `scene/tvsc.ts` | 115 | pure: the §2.3 `TVSC1` parser (+ an encoder used only by the fixture generator and the gallery) |
| `scene/normals.ts` | 79 | pure: area-weighted vertex normals, bounds, bounds union |
| `scene/pickId.ts` | 37 | pure: the 24-bit colour-id encode/decode both shaders write |
| `scene/selection.ts` | 85 | pure: the selection reducer and the per-mode rules (`MODE_RULES`) |
| `scene/palette.ts` / `types.ts` | 61 | colours as numbers (shaders cannot read a CSS variable) and the data shapes |
| `scene/glScene.ts` | 651 | the only file that touches WebGL: programs, VAOs, the pick FBO, context restore |
| `scene/SceneCanvas.tsx` | 619 | the React surface, the rAF/damping loop, chrome, fallback, `window.__scene` |
| `scene/scene.css` | 178 lines | the chrome around the canvas |
| **total** | **1 933** code lines (2 852 with comments and CSS) | |

Plus, outside the module: `dev/SceneGallery.tsx` (146) and `dev/sceneFixtures.ts` (137), the
generator `scripts/make-scene-fixtures.ts` (43), five vitest files (`tests/unit/scene-*.test.ts`,
853) and the offscreen spec `tests/e2e/scene.spec.ts` (433).

**Against the plan's "~700 lines": it is 1 933.** Stated rather than hidden. The estimate covers
the four draws (camera 217 + glScene 651 ≈ 870 on its own); what it did not price in is everything
S4/S6 also asked for and that a form control actually needs — damping, camera presets, per-surface
opacity, the legend, hover, the keyboard, the WebGL2-absent fallback, context loss and restore, and
the `window.__scene` handle the offscreen test asserts on. No part of it is a second viewer: there
is no volume, slice, colormap, overlay or layer-tree code anywhere in the module.

## 2. Decisions, each with the failure it prevents

| # | Decision | Failure it prevents |
|---|---|---|
| B1 | **Camera maths is a pure module the e2e spec imports directly.** The spec computes where a marker lands on screen with `camera.ts` and clicks there; the GPU's colour-id pick has to name the same marker. | A camera checked only against its own renderer agrees with itself while both are wrong, and every pick test built on it still passes. |
| B2 | **Colour-ID picking, scissored to 3×3 around the cursor**, into an off-screen RGBA8 FBO, with the *same* matrices as the visible pass. | A CPU ray cast is either a linear scan over 150 k triangles per mouse move or a BVH this module has no business owning — and it cannot answer "which region" at all. The shared matrices are why click and render cannot drift. |
| B3 | **Region ids come from a `flat`-qualified per-vertex label varying.** | An interpolated label averages two regions across a boundary into a third, non-existent region id. This is the WebGL2-only feature that makes it a WebGL2 renderer. |
| B4 | **Markers are instanced quads offset in clip space**, not `gl.POINTS`. | Point sprites carry driver-dependent size clamps and `gl_PointCoord` gaps; a marker that rasterises differently on one GPU is a marker that cannot be clicked there. |
| B5 | **Draw order: markers (depth write on) → all back faces outermost-first → all front faces innermost-first, depth write off.** | A translucent fragment that writes depth rejects everything behind it: the grey matter vanishes inside the head. This ordering is back-to-front for nested shells with no triangle sorting. |
| B6 | **`settled` means "the render loop has stopped", set false the moment a frame is *requested*.** | Measured: a preset click returns before the first rAF fires, so a test waiting on `settled` sampled the previous rest state and read a camera one damping step into the move (yaw −0.858 rad where the goal was −1.571). |
| B7 | **`WEBGL_lose_context` is captured at context creation**, never fetched lazily. | `getExtension` answers `null` on an already-lost context, so a lazily fetched handle can lose a context and then never restore it (measured: `restoreContext()` returned false, the pane stayed dead). |
| B8 | **Wheel is a manual non-passive listener, not React's `onWheel`.** | React attaches wheel handlers passively; `preventDefault` is ignored with a console warning and the page scrolls behind the zoom. |
| B9 | **Damping is `1 − exp(−λ·dt)`, distance interpolated in log space.** | A constant blend factor moves twice as fast on a 120 Hz display as on 60 Hz — a "smooth" camera that feels different on every machine. Asserted: two 8 ms steps land exactly where one 16 ms step does. |
| B10 | **The gallery builds its fixtures, encodes them to `TVSC1` and parses them back** rather than feeding arrays to the GPU directly. | A gallery that shortcuts the wire format leaves the parser untested on the one path that matters. |
| B11 | **One palette, not two.** `--canvas` is the same in both themes; the DOM chrome around the canvas follows the theme, the anatomy does not. | "Is the grey matter light or dark today" is not a theme decision. |
| B12 | **The legend is DOM, not painted.** | A painted legend cannot be read by a test, selected, or translated, and has to be re-implemented per theme. |

## 3. Fixtures

`scripts/make-scene-fixtures.ts` (run by hand: `npx tsx scripts/make-scene-fixtures.ts`) writes

- `desktop/tests/fixtures/scene/skin.tvsc` — 74 924 bytes, 2 145 vertices, 4 096 triangles, no labels
- `desktop/tests/fixtures/scene/gm.tvsc` — 79 216 bytes, same grid + one `uint16` label per vertex, 32 distinct
- `desktop/tests/fixtures/scene/electrodes.json` — 36 markers, 3 rings of 12

They are ellipsoid grids because **every number about them is closed form**, so a test asserts
arithmetic rather than a recorded blob:

```
theta = pi*i/v (i=0..v)      phi = 2pi*j/u (j=0..u)
p = (rx sin(theta) cos(phi), ry sin(theta) sin(phi), rz cos(theta))
vertices = (u+1)(v+1)        triangles = 2uv        bbox = ±(rx, ry, rz) exactly
winding (i,j) -> (i+1,j) -> (i,j+1)  (the +theta and +phi tangents; their cross product is outward)
skin: rx,ry,rz = 78,98,88   u,v = 64,32
gm:   rx,ry,rz = 64,82,70   u,v = 64,32   label = 1 + band_theta(4)*8 + band_phi(8)
```

**Note for lane SCA**: these two files sit in the same directory as your
`tri-surface`/`labels-only`/`labelled-surface` fixtures and are yours to read from the Python side
if you want the reverse direction of §2.3's "one test in each language reads a fixture the other
wrote" on a payload with a realistic vertex count.

`tests/unit/scene-tvsc.test.ts` reads **your** three fixtures with an independent `DataView` walk at
the spec's own offsets and with the authored position formula retyped (`x = i*1.5`,
`y = 40 − i*7.25`, `z = −12 + i²*3`, all exactly representable in float32, so the assertions are
equalities, not tolerances) — the encoder is never used to produce an expected value for the decoder.

## 4. Measurements

Machine: this Mac (120 Hz display), Electron 44, offscreen (`TIT_E2E_OFFSCREEN=1`), mock server.

| Measurement | Value | Note |
|---|---|---|
| Host `python3 -m pytest -q` | **3459 passed, 30 skipped, 21 deselected, 39.4 s** | green |
| `npm run typecheck` | clean | |
| `npm run lint` | 0 errors (3 pre-existing warnings, all in other files) | |
| `npx vitest run` | **816 passed / 817**, 1 failure not mine (§6, SCA's `/api/scene/*`) | my 5 scene files: 76 tests, all pass |
| `npm run build` | 1 354.01 kB renderer chunk | |
| e2e `tests/e2e/scene.spec.ts` | **7 passed (38.4 s)**, quiet-check **PASS**, 57 samples, no new window | |
| Regression `gallery.spec.ts` + `smoke.spec.ts` | **11 passed (53.2 s)**, quiet-check **PASS** | the Gallery.tsx edit breaks nothing |
| Triangles uploaded, small fixture | 8 192 (2 × 4 096), 4 290 vertices, 36 markers, **5 draw calls** | asserted from `GlScene.stats`, not from the props |
| Triangles uploaded, budget fixture | **156 096** (152 000 skin + 4 096 gm) | S3's 150 k-per-surface budget |
| **fps while orbiting, 1280×800 @ dpr 2** (2560×1600 backing store), 156 096 triangles | **118.8–120.2 fps** over three runs, 329–337 frames per 2 s drag | S8's floor is 30; the loop is v-sync-capped at the display's 120 Hz, so every frame was under 8.3 ms |
| CPU submit per frame (`stats.lastFrameMs`) | 0.000–0.100 ms | at or below `performance.now()`'s clamped resolution; the fps figure is the real measure |
| Marker pick agreement | `window.__scene.project()` vs the spec's own `projectToCanvas` agree to 1e-9 px; the click at that pixel selects that marker | the load-bearing cross-check (B1) |
| **Region pick agreement** | the spec solves the ray/ellipsoid quadratic itself, converts the hit to (theta, phi), applies the fixture's own banding formula, and the GPU's colour-id pick returns that label | passed first try — the `flat` varying, the label texture and the kind bits are all right (B3) |
| Orbit | 120 px drag → Δyaw = 0.960 rad, matching `ORBIT_RAD_PER_PX = 0.008` to 1e-6; distance and target unchanged | |
| Context loss | overlay shown, `contextLost` true; after restore `stats.triangles` back to 8 192 and markers to 36 | proves re-upload, not a quiet blank canvas |
| No-WebGL2 | `scene-fallback` visible, canvas absent, legend still lists the parts, handle reports `{webgl2:false, ready:false}` | forced by stubbing `getContext` in an init script |

Two caveats on the fps number, both stated rather than smoothed over:

1. A never-shown Electron window belongs to no display and reports `devicePixelRatio = 1`. The test
   forces 2 (the component's own cap) before resizing, so the backing store really is 2560×1600 —
   a Retina pane's fragment load, not a quarter of it.
2. It is v-sync-capped at 120 Hz, so it is a floor, not a ceiling: the renderer never became the
   bottleneck. The real pane's number is SCC's to re-measure once the scene is in the right pane
   with the plan and the terminal beside it.

## 5. How to run it

```bash
cd desktop
npx vitest run tests/unit/scene-*.test.ts            # 76 tests, no GPU, ~0.2 s
VITE_INCLUDE_GALLERY=1 npx electron-vite build       # the gallery route AND window.__scene
TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/scene.spec.ts
npx tsx scripts/make-scene-fixtures.ts               # regenerate the .tvsc fixtures
```

`out/` was left on a **plain** `npm run build` (no gallery) so other lanes get a production-shaped
bundle; `tests/e2e/scene.spec.ts` fails fast with a message naming the missing flag if run against
one. Builds taken at 00:41, 00:47, 00:52, 00:58, 01:00, 01:05 and 01:07 (the last a plain one) — a
lane building in that window may have raced me (the RUNBOOK's warning); nothing else of mine
touches `out/`.

## 6. Open issues and requests to other lanes

- **SCA (or whoever owns the mock server)** — `desktop/tests/mock-server/contract.test.ts` is RED:
  `contracts/openapi.v1.yaml` now declares `GET /api/scene/{manifest,surface,electrodes,regions,
  labels,volume-legend}` (regenerated 00:49, fixture `desktop/tests/fixtures/openapi.v1.json` 00:57)
  and the mock server implements none of them, so "exercises every declared HTTP operation" fails
  with 58 exercised vs 64 declared. Nothing to do with this lane's files; `npx vitest run` is
  otherwise 816/817.
- **SCC** — the component's contract, so the wiring does not have to be reverse-engineered:
  `<SceneCanvas mode parts markers selection onSelectionChange onPick bounds legend label />`.
  `parts` and `markers` **must be memoised** (they are the upload trigger). Selection is controlled
  when you pass one; `MODE_RULES` already states what each mode picks (montage: ≤2 markers, oldest
  evicted; target: unbounded regions; inspect: one marker). The pane fills its parent, so give it a
  sized box. Test ids: `scene-pane`, `scene-canvas`, `scene-legend`, `scene-opacity`,
  `scene-fallback`, `scene-context-lost`. Please re-measure the S8 fps and first-paint numbers in
  the real right pane — mine are from an 880×420 gallery frame resized to 1280×800.
- **Whoever owns `pages/dev/index.tsx`** — the design gallery ships in production builds. A plain
  `npm run build` contains the strings "Design gallery", "Every primitive" (both pre-existing, not
  mine) and now "Mount scene": `enabled: import.meta.env.DEV || …` is a *runtime* gate, while the
  `import` at the top of `pages/dev/index.tsx` is unconditional, so nothing is tree-shaken —
  contrary to `desktop/README.md`'s "tree-shakes the page and its nav entry out entirely". The fix
  is a dynamic `import()` behind the flag. The `window.__scene` handle *is* correctly stripped
  (`grep -c __scene` over every production chunk: 0), because it is guarded by an inlined constant
  rather than by a runtime property.
- **Shared-file edits made outside `scene/**`**, all minimal and commented in place:
  `src/renderer/dev/Gallery.tsx` (one import + one `<SceneGallery />` at the end),
  `tsconfig.node.json` (two files added to `include` so `scripts/make-scene-fixtures.ts` can import
  the one TVSC1 encoder instead of carrying a second copy).

## 7. Log

- 00:25 read the plan, the RUNBOOK, DESIGN.md, PRINCIPLES.md and `testing-frontend-offscreen`.
  `desktop/tests/fixtures/scene/` did not exist yet, so wrote fixtures from the §2.3 spec; SCA's
  landed at 00:35 while I was working and the parser read them unchanged, first try — the byte
  layouts agreed with no negotiation, including the 2-byte tail padding on the odd-vertex-count
  labels-only payload.
- 00:39 fixtures generated; 00:41 the five unit files green (76 tests).
- 00:47 first offscreen run: 3 of 6 passed. The three failures were three real bugs (B6, B7, and a
  wrong assertion about the debug handle in the fallback), not flakes; each fixed at its cause.
- 00:52 rAF probe first: a never-shown Electron window reports `visibilityState: "visible"` and runs
  **120 rAF callbacks per second**, so the fps measurement is honest offscreen. Worth knowing before
  building anything on it — a hidden page in a browser tab would have run none.
- 00:58 6/6 green, quiet-check PASS; 01:00 plain build, host pytest green.
- 01:05 added the seventh case: **region picking asserted analytically**. The spec solves the
  ray/ellipsoid intersection itself and applies the fixture's banding formula, refusing any pixel
  within two grid cells of a band boundary (a triangle spans one cell, so two cells of clearance
  makes the expectation exact whichever vertex the `flat` qualifier's provoking-vertex rule picks).
  7/7 green, quiet-check PASS. `out/` left on a plain `npm run build`.

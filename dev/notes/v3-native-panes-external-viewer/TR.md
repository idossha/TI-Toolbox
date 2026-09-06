# Lane TR — stacked transparency, and per-label atlas colour (2026-09-06)

Branch: `feature/v3-electron-gui` (worktree `.claude/worktrees/v3-electron-gui`).
Follows lane NR (`NR.md`), which restored `desktop/src/renderer/scene/**`.

Two defects the maintainer reported from a screenshot of the Optimizer pane — a translucent skin
over a translucent grey matter with the selected regions in one flat blue:

1. **broken triangles under stacked transparency** — shards of grey matter showing through the
   scalp and jagged holes where the layers overlap;
2. **one flat ROI colour** — 70 atlas regions rendered in the same accent blue, so neither the
   pane nor the legend could say which patch was which.

Commits: `012080b2` (transparency), `c0fa0cc1` (atlas colour), `2028d407` (the real-data assertion).

---

## 1. The transparency technique, and where it came from

**It is not weighted order-independent transparency.** Tetravox 0.3.10, commit
`829cd08 fix(render): surface opacity preserves smooth sheets (§7.2)`, does something cheaper and
exact for the two nearest layers: **resolve which depth sheet a pixel shows, then blend only that.**

The files that say so, in `/Users/idohaber/00_development/tetravox`:

| File | What it contributes |
|---|---|
| `packages/engine/src/render/surface-depth.ts` | The whole mechanism, 111 lines: a reusable FBO with **two `DEPTH_COMPONENT24` textures** and `drawBuffers([NONE])`. `draw(block, draw, second)` runs the caller's draw depth-only into texture 1, optionally again into texture 2 with the first bound (a one-layer peel), then a third time for colour with the resolved texture bound. |
| `packages/engine/src/shaders/mesh.ts` | Two `#ifdef`s at the end of the fragment shader. `TVX_SURFACE_DEPTH`: `if (abs(gl_FragCoord.z - sheetDepth) > 1.0/16777215.0) discard;`. `TVX_SURFACE_PEEL`: `if (gl_FragCoord.z <= firstDepth + 1.0/16777215.0) discard;`. |
| `packages/engine/src/render/passes/mesh.ts` | Closed outward-wound shells keep the back/front split; **open or `faceMode:'both'` surfaces peel their nearest two sheets with culling disabled**, because their winding does not identify the front of the object. |
| `packages/engine/src/render/passes/derived.ts` | The same for isosurfaces. |
| `docs/ARCHITECTURE.md` §7.2 | *"Resolve sheets before blending (2026-09-04)… A reusable depth24 texture holds the nearest sheet; a second holds the next distinct depth for two-sided surfaces… This remains a bounded two-sheet approximation: deeper folds are omitted."* |
| `packages/engine/test/e2e/surface-opacity{,-real}.spec.ts` | Their golden + real-grey-matter checks. |

So: **a per-sub-draw depth pre-pass, plus a one-layer depth peel, plus depth-gated colour blending.**
No CPU triangle sorting, no accumulation buffer, no OIT weighting.

### What was ported into `glScene.ts`

Re-implemented, not imported — our renderer shares no code with Tetravox. The header of
`desktop/src/renderer/scene/glScene.ts` §"Resolving sheets before blending" carries the reasoning.

* `createSheetTargets()` — one FBO, two immutable `DEPTH_COMPONENT24` textures at drawing-buffer
  size, `drawBuffers([NONE])`, reallocated on resize and after context restore.
* `SHEET_DEPTH_FS` / `SHEET_PEEL_FS` — the depth-only pre-passes. The peel one discards anything at
  or in front of the first sheet.
* `surfaceFs("none" | "near" | "peeled")` — the surface fragment shader as a variant factory. The
  sheet variants compile in the bound; the plain one is unchanged for the pick and opaque paths.
* `drawResolvedSheet(part, level, vp, view)` — steps (a) nearest, (b) peel, (c) colour, with
  culling **disabled throughout**. That is the point: neither of our surfaces is reliably wound.
* The render loop's two phases are unchanged in *ordering* — far sheets outermost first, near
  sheets innermost first — only the sheet each phase draws is now decided by depth.

**One deliberate divergence from Tetravox.** Their test is an *equality* within one depth24 step.
Ours is an **inequality** (`if (gl_FragCoord.z > sheetZ + 1.0e-5) discard;`, plus a lower bound for
the peeled sheet). Our canvas is created with `antialias: true`, so the colour pass writes into a
**multisampled** buffer while the pre-pass writes into a single-sampled depth texture; at a triangle
edge a partially-covered fragment is shaded once at the pixel centre and its `gl_FragCoord.z` does
not match what the single-sampled pre-pass recorded. Measured with the equality test: dropped
fragments at every facet edge of the 64×32 fixture, showing as colour steps of 8–19/255. The bound
admits exactly one sheet and is blind to that sub-pixel disagreement. `1e-5` of the [0,1] window
range is ~170 depth24 steps — three orders of magnitude above quantisation, three below the
millimetres between the walls of a gyrus.

### Cost

| | before | after |
|---|---|---|
| Draw calls per frame (2 surfaces + markers) | 7 | **13** — per surface, far phase 3 (near depth, peel depth, colour) + near phase 2 (depth, colour) = 5, ×2, + 2 marker-occlusion depth + 1 marker |
| GPU memory | — | + 2 screen-sized depth24 textures, reallocated only on resize |
| fps, 152 000-triangle fixture, 1280×800 @dpr 2, orbiting | **120.0** (330 frames) | **120.0** (333 frames) — both vsync-capped; `lastFrameMs` 0.000 → 0.100 CPU |
| fps, real `sub-ernie`, 222 434 triangles, 1280 wide, orbiting | — | **122.5**, last frame 0.10 ms CPU |

No measurable frame cost. The extra work is depth-only rasterisation of geometry already resident.

### Evidence

A new fixture, `sceneFixtures.ts` `foldedFixtureGrid()`, reproduces the defect arithmetically rather
than anatomically: **two concentric ellipsoids concatenated into one part** (four sheets per camera
ray — the 4–6 crossings §7.2 measures for real grey matter) with **the winding of every triangle on
the `x < 0` half reversed** (a folded surface has no globally consistent front face). Unlabelled, so
the only colour variation across it is the shading gradient and any *step* is a compositing defect.
It is the gallery's third "Fixture size" option, `folded`.

`desktop/tests/e2e/scene-transparency.spec.ts` walks a horizontal scanline across the interior of
that sheet — anchored to *projected world points* (±0.55 × the inner radius, which straddles the
seam whatever the camera is doing) rather than to a fraction of the canvas, and kept off the
silhouette where the fresnel term legitimately climbs.

| | worst per-channel step, 3 px apart |
|---|---|
| old winding split, re-applied to the same build to take the reading | **23/255** (further steps of 12, 13, 16, 20 along the same line) |
| sheets resolved by depth | **2/255** (8 at the very edge of the margin) |

The bound is 12, in the middle of that gap. Ten runs of the resolved renderer never exceeded 4.
A second test repeats it at three heights, because one line could cross the seam where the two
orders happen to agree and three cannot.

Screenshots, from the same fixture and the same camera (gitignored — the artifacts directory is):

* `desktop/tests/e2e/artifacts/pane-transparency-before.png`
* `desktop/tests/e2e/artifacts/pane-transparency-after.png`

---

## 2. Per-label atlas colour

**The colour was already on the wire.** `tit/scene/build.py::_load_reference_labels` has read the
`.annot` colour table since the legend existed and emits `legend[].color` as `"#rrggbb"`;
`build.py::volume_legend` does the same from `segmentation/labeling_LUT.txt` for subcortical labels;
`contracts/openapi.v1.{json,yaml}` already **require** `color` on both `GET /api/scene/regions` and
`GET /api/guide/regions`; and all three packaged guide legends carry it —
`DK40.json` 70 rows / 35 distinct colours, `a2009s.json` 152 / 76, `HCP_MMP1.json` 362 / 181 (the
halving is correct: a FreeSurfer ctab is keyed by parcel, so lh and rh share a colour).

So **no route changed, no schema changed, and the guide needed no regeneration** — verified rather
than assumed. `python3 dev/route_import_guard.py` → *20 route module(s) clean*. The whole gap was on
the client: the pane drew one flat `SCENE_PALETTE.selected` for every region.

### The path, end to end

```
m2m_<id>/segmentation/{lh,rh}.<id>_<atlas>.annot   ctab RGB
  -> tit/scene/build.py::_load_reference_labels     legend[].color = "#rrggbb", keyed by wire label
  -> GET /api/{scene,guide}/regions                 (contract already requires `color`)
  -> ScenePane.tsx  buildLabelColors(legend)        Uint8Array, 3 bytes per uint16 label id
  -> SceneCanvas.tsx  labelColors prop -> setLabelColors()
  -> glScene.ts  256x256 RGB8 texture, same index as the label-STATE texture
  -> surfaceFs()  texelFetch(uLabelColor, uv).rgb
```

Indexing is the thing that can silently go wrong — a colour written at the region's `.annot` row
`id` instead of at its wire `label` puts the left hemisphere's colours on the right hemisphere's
regions, plausibly. `buildLabelColors` is pure and `tests/unit/scene-label-colors.test.ts` is about
exactly that.

### How it renders

| State | Draw |
|---|---|
| at rest | the atlas hue **desaturated to 55 % towards its own luma and dimmed to 86 %**, so a parcellated cortex still reads as a cortex rather than as a pie chart |
| hover | the same hue mixed 45 % towards white — brightened, never renamed |
| selected | the hue at **full saturation**, raised opacity, plus a **thin darkened outline** on the rim of the patch |
| no atlas colour (label 0, or a legend without one) | the part's flat tint and the palette blue, exactly as before |

### The outline, and the defect the first version of it caused

Selection is carried by three signals — full saturation, raised opacity and the outline — so hue is
never doing the work on its own.

**The first version was wrong and the maintainer caught it in a screenshot**: every selected DK40
label had a *jagged white border of uncoloured triangles* around it. `SURFACE_VS` writes a non-`flat`
`vSelect` varying (1 at a selected vertex, 0 otherwise), and the shader treated `0 < vSelect < 1` as
"on the rim". That is not the rim — it is **the whole of every triangle that straddles the rim**, and
a decimated cortex has long thin ones. On a 200 000-triangle surface that is a band of shards
several triangles thick, painted 85 % of the way to white.

The fix keeps the varying but reads it as what it is — **a signed field whose 0.5 contour is the
boundary**, not a membership test:

```glsl
float width = fwidth(vSelect);
float edge  = width > 1.0e-5 ? 1.0 - smoothstep(0.0, width * 1.2, abs(vSelect - 0.5)) : 0.0;
shaded = mix(shaded, shaded * 0.12, edge);   // darkened, never whitened
a      = max(a, edge * 0.95);
```

`fwidth` converts "how far am I from the contour, in field units" into "…in pixels", so the line is
**~2.4 px wide on screen whatever the triangle size**, and it cannot swallow a boundary triangle.
The guard handles the constant-field cases (nothing selected, or everything) where `fwidth` is 0.

Two further points, both from the maintainer's note:

* **Darkened, not whitened.** `shaded * 0.12` reads as a border against every atlas colour including
  the light ones, where white was indistinguishable from a specular highlight and, being lighter
  than most of the palette, is what made the shards so loud.
* **A boundary triangle is never a mixed colour.** The *colour* of a fragment has always come from
  `vLabel`, which is `flat` — the provoking vertex's label wins for the whole triangle — so a
  triangle is entirely one region's colour and never a blend of two. Only the discarded rim test
  ever read the interpolated value for colour.

`desktop/tests/e2e/scene-selection-edge.spec.ts` is the regression test, on the gallery's banded
fixture whose legend gives every band a distinct mid-lightness hue:

| | old rim | `fwidth` outline |
|---|---|---|
| white pixels (all channels ≥ 220) in a 100×100 px window round the click | **40 of 441** | **0 of 441** |
| pixels inside the patch not carrying the label's hue | — | **0 of 21** |
| repainted pixels that are outline | — | **4 of 439** (0.9 %) |

Screenshot: `desktop/tests/e2e/artifacts/region-selection-after.png`.

Subcortical volume labels take the same path — `volume_legend` emits `color` from the LUT with the
same parser the optimizer's ROI picker uses.

### Legend and picker

`ScenePane`'s legend rows use the region's own colour instead of one blue (`labelSwatchColor`).
`SelectionItem` gained an optional `swatch?: string`, rendered as a 9 px dot before the label and
`aria-hidden` (the label beside it carries the same information in words). `RoiPicker` fills it from
`useGuideRegions(atlas)` — **the same react-query key the pane on the same page already fetched**,
so the picker issues no request of its own, and `legend[].id` is what `regionKey` keys on, so a
swatch and the patch the pane paints are the same colour by construction. No guide atlas, no colour,
no swatch, and the rows read exactly as before.

The two-way RoiPicker ↔ pane selection model is untouched.

---

## 3. Files

**Renderer** — `desktop/src/renderer/scene/glScene.ts` (the two techniques, `buildLabelColors`,
`labelSwatchColor`, `setLabelColors`), `SceneCanvas.tsx` (`labelColors` prop + upload effect),
`index.ts` (re-exports).
**Fixtures** — `desktop/src/renderer/dev/sceneFixtures.ts` (`FIXTURE_FOLDED`,
`FIXTURE_FOLDED_INNER`, `foldedFixtureGrid`, `concatGrids`, `foldInnerHalf`, `fixtureLegend`,
`hslHex`), `SceneGallery.tsx` (the `folded` option, `labelColors`).
**Pane / picker** — `pages/_shared/scene/ScenePane.tsx`, `pages/_shared/roi/RoiPicker.tsx`,
`ui/SelectionList.tsx`, `ui/selection.css`.
**Tests** — `tests/unit/scene-label-colors.test.ts` (new), `tests/e2e/scene-transparency.spec.ts`
(new), `tests/e2e/scene-selection-edge.spec.ts` (new), `tests/e2e/scene.spec.ts` (draw calls
7 → 13), `tests/e2e/real/scene-electrodes.spec.ts`,
`tests/test_scene_guide.py` (two new colour-table tests).
**Unchanged, and checked rather than assumed** — `tit/scene/build.py`, `tit/scene/guide_build.py`,
`tit/server/routes/{scene,guide}.py`, `contracts/openapi.v1.*`, the packaged guide.

## 4. Gate

| Command | Result |
|---|---|
| `pnpm run typecheck` | clean |
| `npx eslint src tests` | 0 errors (3 pre-existing `react-hooks/incompatible-library` warnings) |
| `npx vitest run` | **1042 passed / 90 files** |
| `npx playwright test` — `scene`, `scene-transparency`, `scene-pane`, `scene-tabs`, `scene-errors`, `guide`, `optimizer`, `analyzer`, `roi-idiom`, offscreen, serial | **12 + 3 + … = all scene specs pass**; one unrelated `analyzer.spec.ts` density number belongs to another lane's in-flight edit in this worktree and passes standalone |
| `npx playwright test --project=real tests/e2e/real/scene-electrodes.spec.ts` | **2 passed** — `rostralmiddlefrontal/lh`, atlas `#4b327d`, cos-to-own-hue **0.997** vs cos-to-flat-blue **0.753**; 122.5 fps at 222 434 triangles; warm first paint 91 ms |
| `python3 -m pytest tests/test_scene_*.py tests/test_guide_routes.py -q` | **187 passed, 30 skipped** |
| `python3 dev/route_import_guard.py` | 20 route modules clean |
| `pnpm run build` | see §5 |

`tests/test_scene_guide.py::test_the_legend_colour_is_read_from_the_colour_table_and_not_invented`
skips on the host (conftest mocks `nibabel`) and runs in the container.

## 5. Notes for whoever is next

* The two-sheet resolution is a **bounded approximation**, exactly as §7.2 says: a third crossing
  deeper inside a sulcus is dropped rather than mis-ordered. That is the right trade for a
  translucent anatomical shell, and it is the same bound Tetravox ships.
* If `antialias` is ever turned off on the scene context, the sheet bound could go back to
  Tetravox's exact equality; the comment on `SHEET_EPS` says why it is not one today.
* Another lane was editing this worktree concurrently (`RunPanel`, `JobTerminal`,
  `logCatalog.ts`, `docs/wiki/pipelines.md`, `pipeline-ux.spec.ts`, `analyzer.spec.ts`). Nothing
  here touches those files and none of them is in these three commits.

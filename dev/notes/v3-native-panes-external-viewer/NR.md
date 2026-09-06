# Lane NR — native run-page panes on our own renderer (2026-09-06)

Plan of record: `dev/notes/v3-native-panes-external-viewer-plan.md`, decisions **N1–N4** and the **NR** gate (§3).
Branch: `feature/v3-electron-gui` (worktree `.claude/worktrees/v3-electron-gui`).

## 1. What changed

### The renderer (N1)

`desktop/src/renderer/scene/**` is restored from `~/.treehouse/ti-v3-firstmate/uiux/desktop/src/renderer/scene/`
(2026-09-04, 5 048 lines): `camera.ts`, `glScene.ts`, `normals.ts`, `palette.ts`, `pickId.ts`, `selection.ts`,
`tvsc.ts`, `types.ts`, `SceneCanvas.tsx`, `scene.css`, `index.ts`. WebGL2, zero runtime dependencies, no iframe and
no protocol. Its nine unit suites came back with it, plus the gallery mount (`src/renderer/dev/SceneGallery.tsx`,
`sceneFixtures.ts`) that `tests/e2e/scene.spec.ts` drives.

Four deliberate changes to the restored code, each for an N2/N3 clause:

| File | Change | Why |
|---|---|---|
| `scene/palette.ts` | `channels` is the **Okabe-Ito** six-hue set (was four house hues); new `idle` (#9ea6b3) and `disabled` (#595959) | The old set put a green next to an orange, which a deuteranope reading a four-pair mTI montage cannot separate. Six hues, not four, because mTI runs to four pairs and the wrap should not repeat before it must. |
| `scene/glScene.ts` | six channel uniforms; `uMarkerColor` is now `palette.idle`; **the white selection rim is deleted**; the 1.5× selected scale is now a 1.25× **hover** scale | N2's "no rings". A selected marker keeps the idle marker's exact footprint, which is what makes "no ring" a pixel test rather than a claim: the changed pixels are one solid disc with the same bounding box. |
| `scene/SceneCanvas.tsx` | new `onHoverChange?: (target) => void` prop, fired from the existing hover pick | N3's "hover names the region". The pane turns it into a word; a highlight with no name still leaves the user guessing which of 70 atlas rows lit up. |

### The pane (N2, N3, N4)

| File | What |
|---|---|
| `pages/_shared/scene/ScenePane.tsx` | Rewritten on the native renderer. Guide-only (no `subject`/`unavailable`/`sphere` prop, no query keyed on a subject), TVSC1 surfaces + labels, electrode dots, an **atlas selector**, hover naming, region toggling through the shared model, the "Showing: montage · net" chip and `ChannelLegend` kept from the embed era. |
| `pages/_shared/scene/api.ts` | Added `getGuideTvsc`, `guideSurfaceUrl`, `guideLabelsUrl`. The decoder is `scene/tvsc.ts`'s `parseTvsc1` — the independent reader the Python encoder is tested against. |
| `pages/_shared/scene/queries.ts` | Added `useGuideSurfaces`, `useGuideLabels`, `useGuideSurfaceRequests`. `staleTime`/`gcTime` `Infinity`, no subject in any key. |
| `pages/_shared/scene/model.ts` | Stopped re-declaring the palette and the marker/selection types: they are **re-exported from `renderer/scene/`**, so there is one palette in the app. New `toggleRegion()` — the one region-selection edit. |
| `pages/_shared/scene/embedScene.ts` | **deleted** (N4). |
| `pages/_shared/scene/scene-pane.css` | `.scene-pane-atlas` / `.scene-pane-hovered`. |
| `pages/_shared/roi/RoiPicker.tsx` | Its private `regionKey` copy is gone; it imports the scene model's. One key function, so a 3D click and a form chip compare regions the same way. |
| `pages/optimizer/index.tsx`, `pages/analyzer/AnalyzerPage.tsx` | **`<ScenePane …>` call-site lines only**: added `onAtlasChange`, and on the Analyzer `onRegionsChange`, so the analysis ROI is editable from the pane (N3). `pages/simulator/index.tsx` needed no change. |

`ScenePane`'s public props are unchanged for the three pages except for the two **additive optional** callbacks above.
`SceneGesture` lost `"sphere"`; nothing under `pages/` produced it.

### The guide (N1)

| File | What |
|---|---|
| `tit/scene/guide_build.py` | `LABEL_FORMATS = ("tvsc", "gii")` (was `("gii",)`), and the summary line prints both. |
| `tit/scene/guide/labels/{DK40,HCP_MMP1,a2009s}.tvsc` | regenerated, +0.99 MB each |
| `tit/scene/guide/manifest.json` | regenerated |
| `tests/test_scene_guide.py` | +1 test: every atlas ships TVSC1 labels **aligned to the `gm` surface** (same vertex count, same first vertex) |

`tit/server/routes/guide.py` needed **no change**: `labels(atlas, format)` already validated `tvsc`/`gii` against the
manifest's own file map, so packaging the payload was the whole fix.

### Tests

| File | What |
|---|---|
| `tests/unit/scene-{camera,framing,normals,orientation,pick,selection,tvsc,unproject}.test.ts` | restored |
| `tests/unit/scene-pane-legend.test.tsx` | now reads `SCENE_PALETTE.channels` (the renderer's palette) instead of the deleted `embedScene.channelColor` |
| `tests/e2e/scene.spec.ts` | restored (gallery, CPU-vs-GPU pick cross-check) |
| `tests/e2e/scene-pane.spec.ts` | rewritten: native canvas, no iframe, aimed electrode click, region ↔ RoiPicker in both directions |
| `tests/e2e/scene-errors.spec.ts` | rewritten for `manifest`/`surface` faults (a `regions` fault is a sentence, not a state) |
| `tests/e2e/guide.spec.ts` | rewritten off the iframe: zero requests / same **canvas** element on a subject change; aimed electrode pick; no `sphere` gesture |
| `tests/e2e/real/scene-electrodes.spec.ts` | **new** — drawing-buffer pixels: idle grey, channel hue, no ring (radial profile), ROI tint, warm first paint, orbit fps |
| deleted | `tests/unit/scene-pane-embed.test.ts`, `tests/e2e/scene-rendering.spec.ts`, `tests/e2e/real/{embed-electrodes,embed-occlusion,scene-preview}.spec.ts` — all embed-protocol specs of pane files this lane replaced |

## 2. Commits

```
95fea0e1 feat(desktop): restore the native WebGL2 scene renderer and its unit suites
020f956c feat(desktop): run-page panes draw the guide with the native renderer; one region-selection model
9290364a feat(guide): package TVSC1 per-vertex labels again so the native pane can highlight regions
e3992968 test(desktop): native-renderer scene specs, region/electrode two-way selection, real pixel gate
```

## 3. Gate evidence

### Guide regeneration (real container, real mesh)

```
$ docker exec ti-toolbox-fad740e5-tit-1 /root/SimNIBS-4.6/bin/simnibs_python \
    -m tit.scene.guide_build --project /mnt/000 --subject ernie --out /ti-toolbox/tit/scene/guide
skin    77032 tris  tvsc 1.39 MB  gii 1.30 MB  within_budget=True
gm     145402 tris  tvsc 2.59 MB  gii 2.44 MB  within_budget=True
DK40         70 regions  tvsc 0.99 MB  gii 2.50 MB
HCP_MMP1    362 regions  tvsc 0.99 MB  gii 2.52 MB
a2009s      152 regions  tvsc 0.99 MB  gii 2.52 MB
8 nets, packaged total 18.44 MB          (was 15.48 MB — +2.96 MB for the three label payloads)
                                          8.4 s wall
```

Served, read back through the route in the container (the HTTP server itself was down at the time — see §5):

```
/api/guide/manifest                        200   2 518 B
/api/guide/labels?atlas=DK40&format=tvsc   200 988 236 B   header ('TVSC', 1, 70586 verts, 0 indices, flags 1)
/api/guide/surface?part=gm&format=tvsc     200 2 591 888 B header ('TVSC', 1, 70586 verts, 436 206 indices, flags 0)
/api/guide/regions?atlas=DK40              200   6 153 B
alignment (labels' first vertex == gm's)   True
```

### Host commands

```
$ python3 dev/route_import_guard.py            → route_import_guard: 20 route module(s) clean
$ python3 -m pytest tests/test_scene_guide.py tests/test_guide_routes.py -q
                                               → 21 passed, 1 warning in 0.80s
$ cd desktop && pnpm run typecheck             → clean in this lane's files
$ npx eslint <this lane's files>               → 0 problems
$ npx vitest run tests/unit/scene-*            → 11 files, 152 passed
$ npx vitest run                               → 89 files / 1064 passed; 3 files / 12 failed, ALL in lane VX's
                                                 in-flight files (viewer-page, embed-protocol, tetravox-card,
                                                 tetravox-updated-event, mock-server contract)
```

<!-- E2E-RESULTS -->

## 4. Proposed record entries

**`docs/ARCHITECTURE.md` — replaces the embed contract for the run pages:**
> The Simulator, Optimizer and Analyzer 3D panes are rendered by `desktop/src/renderer/scene/`, a WebGL2 renderer with
> no runtime dependency that draws two translucent surfaces, screen-space point markers and a labelled region
> highlight, and picks either through a colour-id pass. It consumes the packaged guide over
> `GET /api/guide/{manifest,surface,labels,regions,electrodes}`; surfaces and labels are `TVSC1`
> (`?format=tvsc`), and the labels payload is the `gm` positions plus their `uint16` per-vertex labels. Nothing under
> `pages/` imports the Tetravox embed.

**`docs/DECISIONS.md`:**
> **2026-09-06 — the run-page panes render themselves; the embed is not a pane.** Driving the Tetravox embed from the
> forms cost an iframe, a message protocol, a runtime update channel and a capability negotiation, and still gave a
> worse pane: the electrodes were spheres the engine would not size, selection was a ring the user could not read on a
> dense net, and the atlas was not interactive at all. The 2026-09-04 native renderer is restored and is the only
> renderer on the three run pages. Tetravox remains the *viewer*, as an external application.

> **2026-09-06 — the guide packages TVSC1 labels again.** They were dropped on 2026-09-05 on the premise that nothing
> read them, which was true only while the native renderer was retired; the day it came back the cortex had no regions
> to highlight. They cost 0.99 MB per atlas (2.96 MB on the installation) and are pinned by a test that checks their
> alignment to the `gm` surface, not merely their presence.

> **2026-09-06 — one region-selection model.** `<ScenePane>` and `<RoiPicker>` edit the same list with the same
> `regionKey`/`toggleRegion`, rather than two toggles that agree today. A 3D click and a form chip are one selection,
> in both directions.

**`desktop/DESIGN.md` §9/§10:**
> In the montage pane an electrode's **colour is its whole state** — neutral grey in no channel, 35 % grey when
> unusable, its channel's Okabe-Ito hue when placed. No ring, no outline, no second glyph; the selected marker's
> footprint is byte-identical to the idle one's. In the target/inspect panes the pane carries its **own atlas
> selector**, hover names the region under the cursor, and a click adds or removes it from the ROI the form holds.

**`docs/ROADMAP.md`:** *N1–N4 (native run-page panes, interactive atlas, electrode dots) — done.*

## 5. Open items

* **The shared container's HTTP server was down for this lane's whole window**, on lane VX's in-flight tetravox
  deletions (`ImportError: cannot import name 'ProtocolRange'`, then
  `ServerSettings.__init__() got an unexpected keyword argument 'tetravox_embed_dir'` on every `--reload` cycle). The
  guide routes were therefore verified in-process in the container (§3) rather than over HTTP, and
  **`tests/e2e/real/scene-electrodes.spec.ts` has not been run against the real server**. It is the one gate clause
  with no number yet; re-run it as soon as the container comes back:
  ```
  TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=$(docker inspect ti-toolbox-fad740e5-tit-1 \
    --format '{{range .Config.Env}}{{println .}}{{end}}' | grep TIT_SERVER_TOKEN | cut -d= -f2) \
  TIT_E2E_OFFSCREEN=1 npx playwright test --project=real tests/e2e/real/scene-electrodes.spec.ts --reporter=line
  ```
* **The mock server was also broken mid-lane** (`ReferenceError: route is not defined` — lane VX rewriting
  `tests/mock-server/server.mjs`), which is why the mock e2e results in §3 were taken after waiting it out.
* **`AnalyzerPage.tsx` and `simulator/index.tsx` are being rewritten by lane JB concurrently.** This lane touched only
  the `<ScenePane …>` call-site lines in them (per the coordinator's message) and made no change to
  `MontageManager.tsx`, `FlexTab.tsx`, `RunControls.tsx` or `buildConfig.ts`. At the time of writing both files have
  typecheck errors from JB's in-flight edits, unrelated to these lines.
* **The pane no longer owns the opacity sliders.** `SceneCanvas` has its own per-surface opacity chrome (with the
  legend and the camera presets), so `usePageSession("sceneSkinOpacity"/"sceneGmOpacity")` is gone and the value is
  no longer remembered across a page switch. If that memory is wanted it belongs in `SceneCanvas`, one `usePageSession`
  keyed by part id — a small change, deliberately not made here because it changes a shared component's contract.
* **`/api/scene/*` is still live and now called by nothing.** Same open item lane GD left; the guide routes are what
  the panes use. It is the right service for a subject's own scene and should be retired or claimed deliberately.
* **The guide's GIfTI copies are still packaged** (per N1: "keep the GIfTI copies until VX no longer needs them").
  Once the Viewer no longer reads them, `SURFACE_FORMATS`/`LABEL_FORMATS` drop to `("tvsc",)` and the package loses
  ~11.3 MB.
* **Prop the pages may eventually want** (not made, since `MontageManager.tsx` is JB's): a shared **active slot** —
  `activeSlot?: number` / `onActiveSlotChange?: (slot: number) => void`, the flattened `pair * 2 + col` — so focusing a
  slot in the pair editor decides which slot the next 3D click fills. Today the pane owns its own cursor (moved by the
  channel legend) and the editor owns its focus, and the two do not know about each other.

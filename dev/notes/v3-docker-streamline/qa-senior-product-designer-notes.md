# QA — senior product designer lens (2026-09-03)

Scope: shell + Viewer page + Results/Preprocess as built today, against `desktop/DESIGN.md` v2
(§8.1 "judge numbers and the DOM, not pictures", §10 Viewer) and
`dev/notes/v3-docker-streamline-plan.md` §1. Driven offscreen (`TIT_E2E_OFFSCREEN=1`, verified
quiet by `scripts/e2e-quiet-check.sh` — "no Electron/Chromium window reached the screen", frontmost
app unchanged) against a standalone QA container (`tit-qa-designer`, `idossha/ti-toolbox:dev`,
127.0.0.1:8781, dataset 000), connected via `window.tit.connect()` — never via the maintainer's
`ti-toolbox-fad740e5-tit-1`, which was only read (`GET /api/capabilities`, `/api/health`) and never
stopped/restarted/loaded with jobs. Container removed at the end of this session. Driver script and
raw log/screenshots: `qa-designer.cjs`, `qa-designer-run1.log`, `qa-designer-out/*.png` in the
scratchpad (paths in the summary below).

Also read: `dev/notes/v3-docker-streamline/{w3a-server,w5-viewer,r-reconcile,r2-fixup}-notes.md`,
and the two provided real-embed screenshots (`desktop/tests/e2e/artifacts/phase-c/viewer-real-embed{,-dark}.png`).

## Findings

### 1. [HIGH] The Layout control desyncs from the actual on-screen layout — confirmed live, not just read from code

The embed's own toolbar and TI's inspector both let you pick a pane arrangement, and they can
disagree with no way to reconcile.

**Measured**: with a scene loaded (`ernie` / `L_Insula` / `TI_max`), TI's inspector showed
`LAYOUT: 3D+1` selected (`[aria-label="Layout"] [data-state="on"]` → `"3D+1"`). I clicked the
embed's own toolbar button labelled **"1+3"** (`frame.locator("button", {hasText:"1+3"})`) — a
layout TI's own inspector does not even offer. The canvas visibly rearranged to a real 1-big +
3-small layout (`qa-designer-out/after-embed-1+3-click.png`; embed toolbar now shows "1+3"
pressed). TI's inspector **did not change**: re-querying `[aria-label="Layout"] [data-state]`
gave the identical array, `3D+1` still `"on"`, `1×1/2×2/3D` still `"off"` — visible in the same
screenshot's right-hand LAYOUT block.

**Root cause**: `desktop/src/renderer/viewer/protocol.ts:39` — the real, upstream `LayoutKind` has
7 members: `"1x1" | "1x3" | "1x3-horizontal" | "2x2" | "3d-only" | "1+3" | "3d+1"`. TI's own
`ViewerLayout` (`desktop/src/renderer/viewer/store.ts:56-63`) only maps 4 of them. Worse: the
protocol has **no embed→host message that reports a layout change** — `store.ts:443-449`'s
`layoutOf(scene)` is called exactly once, from `loadScene()` at `store.ts:342`
(`layout: layoutOf(scene) ?? get().layout`), and never from `handleMessage()`'s `layers` / `status`
/ `cursor` / `loaded` cases (`store.ts:265-329`). So the inspector's "selected" layout is a
write-only echo of TI's own last `setLayout()` call, not a readout of what the canvas is actually
showing. The embed's own toolbar is the only thing that is ever accurate.

**Fix**: this cannot be patched app-side without a protocol addition (an embed→host `layout`
event). Until then, apply the rule DESIGN.md §10 already states ("anything registered to the image
... is drawn by the engine") literally: remove TI's Layout inspector block (or make it visibly
read-only / disabled with a note "set from the toolbar above") rather than run two independently
clickable controls for the same state, one of which is provably stale.

### 2. [HIGH] The embed's own toolbar duplicates or shadows nearly everything TI draws — DESIGN.md §10's split is not honored in the build

**Measured** — the full embed toolbar, dumped via `frame.evaluate` (button text + `title` +
pressed state), against a real container-served embed:

```
2×2  1+3  3D+1  3D  NEU  Reset
Crosshair  Bars  Measure  Scale
Cube  Screenshot  ▾(export: target/size/scale/DPI/background/chrome/auto-trim)
?(shortcuts)  ⚙(Settings: "appearance, capture defaults, paths and startup")
›(expand layer panel)  ‹(expand info panel)
```

Direct overlaps with TI's own inspector: **Layout** (2×2/1+3/3D+1/3D vs TI's LAYOUT block, see
finding 1) · **Screenshot** (embed's own `Screenshot`/`▾` export dialog vs TI's EXPORT ▸ Screenshot
▸ Capture, `pages/viewer/index.tsx:283-289`) · the embed's own collapsible **layer panel** (`›`) vs
TI's LAYERS block · the embed's own collapsible **info panel** (`‹`) vs TI's CURSOR block. The
embed's `⚙` opens a wholly separate, TI-unaware **Settings** surface ("appearance, capture
defaults, paths and startup") that nothing in TI's own Settings page links to or knows about.

**Fix**: DESIGN.md §10 already states the intended split in prose ("Engine-drawn chrome ... vs
app-drawn chrome ... Nothing is drawn twice") — the build does not follow it. Given finding 1 shows
the protocol can't keep TI's side honest for Layout, and TI has no read channel for the embed's own
layer-panel/info-panel/settings state either, the two realistic resolutions are: (a) find and use
an embed suppression flag for its own toolbar (check `docs/EMBED.md` for a `chrome`/`ui` option)
and make TI's inspector the single source of truth, or (b) go the other way — drop TI's competing
Layers/Layout/Screenshot blocks and keep only what TI's protocol can reliably surface (Cursor
read-out, Subject/Simulation/Field source bar). Shipping both, live, as today, is the one option
DESIGN.md itself rules out.

### 3. [MEDIUM] The empty 3D pane is a deliberate default with zero on-screen explanation, and the DESIGN.md-promised size-before-fetch never appears

**Measured**: the layer named `grey_L_Insula_TI` (colormap `jet`) loads with `visible:"false"` —
confirmed against `tit/viewspec.py:250-269`'s `_grey_mesh_layer`, whose own docstring says
"Hidden (`visible=False`) because these files run 24-420 MB ... fetched only if the user makes the
layer visible." I toggled it on via TI's own Layers switch; the 3D pane immediately rendered the
mesh (`qa-designer-out/after-mesh-enabled.png`) — **so the empty pane in the provided
`viewer-real-embed.png` screenshot is a layer-visibility default, not the camera rig and not a
bug**, exactly matching the `_grey_mesh_layer` docstring's own framing.

The gap is UX, not data: DESIGN.md §10's "Loading" bullet promises "a large mesh states its size
before it is fetched," but `pages/viewer/index.tsx`'s layer row (~line 246-266) renders only a
`Switch` + name + colormap chip — no byte size, no "renders in 3D" indicator of any kind. A
first-time user who picks the `3D` or `3D+1` layout sees a plain black pane with nothing on screen
explaining why, and no visual cue in the Layers list pointing at the one layer that would fix it.

**Fix**: give the mesh layer a size badge (needs a size source — the scene's `DatasetRef` carries
none today per `tit/viewspec.py`) and/or an inline empty-state message over an unpopulated 3D pane
("No 3D-capable layer visible — enable `<name>` (~N MB)"), the same pattern `TetravoxFrame.tsx`
already uses for its `no-webgl2`/`no-embed`/`error` overlays (`TetravoxFrame.tsx:121-155`).

### 4. [HIGH] Iframe width is under the embed's own 1000px collapse threshold at both 1280 and 1440 — DESIGN.md §8's own acceptance floor also fails on a real form page at 1280×800

Two related, separately measured facts:

**(i) Viewer, real embed, `getBoundingClientRect` on the `<iframe>`** across three widths (height
900 fixed):

| window width | nav rail | inspector | iframe width |
|---|---|---|---|
| 1280 | 216 px | 300 px + 1 px border | **764 px** |
| 1440 | 216 px | 300 px + 1 px border | **924 px** (matches the plan's own "924 px at 1440" note exactly) |
| 1600 | 216 px | 300 px + 1 px border | **1084 px** |

Nav rail is deliberately full-width (216 px) at 1280 by design
(`desktop/src/renderer/app/shell.css:59-61`: "the rail collapses to a 56px icon rail below 1280,
not below 1200 — 1280 is the width every screenshot is taken at, so the full rail must survive
it"). The inspector is fixed and non-collapsible on the Viewer page — `pages/viewer/index.tsx:325`
calls `<PageLayout variant="full-bleed" inspector={inspector} ...>` **without**
`resizableInspector`, so it always takes the plain `width: var(--inspector-w)` branch
(`ui/Layout.tsx:369-378`, `ui/components.css:1766-1768`, 300 px), and does not stack below the
window until 1100 px total (`ui/components.css:1810-1833`). Net: the iframe only crosses W1's
1000 px "panels stay expanded" threshold above roughly 1517 px window width — never at 1280 or
1440, the two sizes DESIGN.md itself treats as standard.

**(ii) Preprocess (a real Tier-1 form page), measured at the exact 1280×800 DESIGN.md §8
prescribes**:
- `.page-layout-main` (`getBoundingClientRect`): `{x:240, y:124, w:700, h:596}` — **700 px**,
  180 px short of §8's stated `≥ 880 px` acceptance floor. Arithmetic: nav (216) + 2×page-pad (48)
  + inspector (300) + gap (16) = 580 px consumed of 1280, leaving 700 for the capped-at-880 work
  pane.
- `.page-header` measures **48 px** tall (`Pre-processing` / "Convert, segment, and prepare
  subjects for simulation."), against §8's own `page header: 0 px` v2 target and §2's "No page
  header ... Settings and Help are the two exceptions." `pages/preprocess/index.tsx:439-445`
  passes an explicit `header={<PageHeader .../>}` — the "v1 escape hatch" documented at
  `ui/Layout.tsx:326-329` ("an explicit node is an explicit decision, and every page written
  against v1 passes one"). Preprocess still passes one.

**Fix**: for (i), either make the Viewer's inspector resizable with a narrower default (the
mechanism already exists — `ResizablePanels`/`resizableInspector`, unused here — wiring it at e.g.
240 px default recovers ~60 px at every width without new code), or treat sub-1000px iframes as
the expected common case and confirm with W1 that the embed's own collapse is graceful rather than
just assumed. For (ii), drop Preprocess's custom header to match every other run screen (move its
purpose sentence to a tooltip or Help entry) to recover the 48 px, and either shrink/collapse the
Plan inspector by default on Preprocess or treat the ≥880 px number as not met by design on pages
with a Plan block and update §8 to say so explicitly instead of leaving a floor the build doesn't
hit.

### 5. [HIGH] The embed's own chrome never receives the app's theme — it stays light regardless of app dark mode

**Measured on the provided real screenshots** (`viewer-real-embed.png` vs `-dark.png`,
pixel-sampled at identical toolbar coordinates): the embed's own toolbar is **byte-identical**
between light and dark — "3D+1" selected button `rgb(109,113,122)` light vs `rgb(107,111,121)`
dark (rounding noise only), "Crosshair" active `rgb(198,204,221)` both, `⚙`/`?` icon wells
`rgb(21,23,27)` both — while the app's **own** chrome correctly inverts over the same pair
(inspector background `rgb(255,255,255)` → `rgb(23,26,32)`, nav rail `rgb(228,235,251)` →
`rgb(28,37,65)`).

**Root cause, confirmed in code**: `store.ts:124` declares `setTheme: (theme) => void` and
`store.ts:374-375` implements it (`channel?.post({type:"setTheme", theme})`); the protocol type is
real (`protocol.ts:132-133`, listed at `:262`). But `rg -n "setTheme" src/renderer/pages/viewer
src/renderer/app` finds no caller anywhere in the app — `pages/viewer/index.tsx` never imports the
action, and nothing wires `app/theme/store.ts`'s `useThemeStore` to it. The mechanism exists and is
tested at the store level (W5's notes list a `setTheme` unit case) but was never connected to a
live theme source.

**Fix**: one missing wire — subscribe to `useThemeStore`'s resolved theme in the Viewer page or
`TetravoxFrame`, and call `useViewerStore.getState().setTheme(theme)` on mount and on every theme
change.

### 6. [LOW] Repeated console errors from the embed's own SVG rendering during ordinary resize/layout use

16 occurrences of `Error: <line> attribute x1/x2: Expected length, "-Infinity"/"Infinity"` in the
renderer console during the 1280→1440→1600 resize pass and the layout-switch click — reproduced
against the real embed, not the fake one. This is inside the vendored Tetravox bundle (not
TI-owned code), so out of this program's fix scope, but it pollutes the one shared devtools console
a TI developer debugs against. Worth a note to W1/upstream Tetravox; if TI ever starts forwarding
explicit resize hints to the embed, debounce them.

### 7. [LOW] Two near-identical "no viewer" messages for two different causes

`TetravoxFrame.tsx:134-146` (`status==="no-embed"`, handshake timeout) says *"This image does not
ship the viewer... Pull or rebuild the image to get it back"*; the page-level state
(`pages/viewer/index.tsx:325-335`, `capabilities.tetravox_embed.available===false`) says *"The
viewer is not bundled in this image... pull or rebuild the image to get the viewer back"* — nearly
identical wording for a slow/broken handshake vs. a capability flag reporting no bundle at all.
Not independently reproduced this pass (the QA container has the embed: `tetravox_embed.available:
true`) — flagged from code read only. A support screenshot cropped to one sentence would not tell
the two apart.

### 8. [LOW, informational] "FastSurfer switch" is a `Checkbox`, consistently with its siblings

The brief calls it a "switch"; the actual control at `pages/preprocess/index.tsx:551-555` is a
`Checkbox`, same as `convert_dicom`, `create_m2m`, `run_tissue_analysis` right above/below it
(`:534-582`) — not a new inconsistency, just noting in case "switch" was itself a request to change
this whole section's control type app-wide (out of this lane's scope either way). Copy/placement
are otherwise correct: help text "Deep-learning cortical and subcortical parcellation from the T1w
image. About 5 minutes per subject on CPU," positioned third in Processing steps (DICOM → charm →
FastSurfer → tissue), matching `run_pipeline`'s real execution order per r2-fixup's notes.

## What's good

- The empty/no-simulation transient state degrades cleanly (skeleton in Layers, blank Cursor
  fields, disabled Simulation/Field selects) — no layout jump, no console error during that
  transition in this run.
- `viewer-real-embed{,-dark}.png` confirm the **app's own** chrome (nav rail, context bar,
  inspector, status bar, source bar) has full, correct light/dark parity — the theme bug is
  entirely scoped to the embed's own unsynced chrome (finding 5), not the shell.
- The 924 px iframe-at-1440 number from the plan's own W1 note reproduced exactly against the real
  embed — the cross-lane contract data is accurate, just not yet designed around.
- Toggling a hidden mesh layer works exactly as documented (`_grey_mesh_layer`'s docstring) and the
  3D pane renders correctly and promptly once a 3D-capable layer is visible — the rendering path
  itself is solid; only the explanatory UI around the default-hidden state is missing.
- Preprocess's FastSurfer step is correctly ordered, worded, and wired to the real
  `run_fastsurfer`/`fastsurfer_threads` contract fields with no lingering `run_recon`/subcortical
  remnants in this page.

## Evidence paths (scratchpad, session-local)

- Driver: `.../scratchpad/qa-designer.cjs`, full run log `.../scratchpad/qa-designer-run1.log`
- Screenshots: `.../scratchpad/qa-designer-out/{after-embed-1+3-click,after-mesh-enabled,
  layout-3d-only,preprocess-fastsurfer,state-no-simulation,viewer-1440-ready,
  viewer-dark-real-toggle}.png`
- Provided evidence re-analyzed: `desktop/tests/e2e/artifacts/phase-c/viewer-real-embed{,-dark}.png`
  (pixel-sampled for finding 5)

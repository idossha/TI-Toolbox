# FX2 — Viewer page, viewer store, pages, presence chips (2026-09-03)

Fix lane after the QA panel. Closes designer findings 1, 2, 3, 5, 7 and the low-severity 7 (copy),
plus researcher finding 1 and the *rendering* half of researcher finding 4. Everything below was
measured offscreen (`TIT_E2E_OFFSCREEN=1`, verified quiet by `scripts/e2e-quiet-check.sh` — "no
Electron/Chromium window reached the screen") against the mock server and against a **standalone**
container I started and removed myself (`tit-fx2`, `idossha/ti-toolbox:dev`, 127.0.0.1:8792, dataset
000, real embed 0.3.4). The maintainer's `ti-toolbox-fad740e5-tit-1` was never touched — not read,
not stopped, no jobs. Connected via the launcher's Connect form (URL + token), never `stack.start`.

To exercise MY renderer against the REAL embed, the container was started with the locally built
bundle bind-mounted: `-v desktop/out/renderer:/ui:ro -e TIT_STATIC_DIR=/ui`. Worth remembering —
without it a real-container run tests the image's baked UI, not the working tree.

## 1 + 2. Layout desync and duplicated image chrome — ownership rule applied

**The rule, now stated in `DESIGN.md` §10 and in a code comment at the removal site
(`pages/viewer/index.tsx`):** the embed's own toolbar owns **image chrome** (layout, screenshot and
export, measure, scale, cube, reset, and everything registered to the image); the inspector owns
**data** (layers, cursor + space, scene serialization). *A control is only app-drawn if the protocol
reports its state back.*

- **Removed** TI's `Layout` block and the whole `Export ▸ Screenshot` sub-block (Capture button, PNG
  preview, Save PNG link, `.viewer-shot` CSS).
- **Kept** Layers (the embed emits `layers`), Cursor (`cursor`), and Scene → Serialize/Save JSON —
  which the embed's toolbar has no equivalent for: it exports pictures, not a ViewSpec. The block is
  renamed `Export` → `Scene` now that it holds one thing.
- `store.ts` keeps `layout` / `setLayout` (a legitimate host action for a future deep link or
  preset) but the `ViewerLayout` doc comment now says in as many words that the mirror is
  **write-only and must not be rendered as a control**, and why.

Measured after the fix, real embed, ernie / Thalamus:
```
embed toolbar: 2×2 1+3 3D+1 3D NEU Reset | Crosshair Bars Measure Scale | Cube Screenshot ▾ | ? ⚙ › ‹
inspector blocks: ["Layers","Cursor","Scene"]
```
One layout control on screen, one screenshot control on screen. Before: two of each, one of them
provably stale.

**Upstream ask for W1 / tetravox (blocking a layout control ever coming back):** protocol v1 has no
embed→host `layout` event. `LayoutKind` has seven members, TI can spell four, and there is no way
for a host to learn that the user clicked `1+3` in the toolbar. If tetravox adds a `layout` event
(same shape as `cursor`: fire-and-forget, on every change including the host's own `setLayout`),
TI can re-render a layout control honestly. Until then it must not.

## 3. iframe under 1000 px — 240 px resizable + collapsible inspector

`PageLayout` gained three **additive** props (`ui/Layout.tsx`, the one file outside my area the
brief allowed): `inspectorWidth` (sets `--inspector-w` inline on `.page-layout`, so the <1099 px
stacking rule still wins), `onInspectorResize` (renders a 6 px `InspectorHandle` between the work
pane and the panel; drag left = wider, ArrowLeft/ArrowRight = ±16 px), and
`inspectorMinWidth`/`inspectorMaxWidth`. Pages that pass none of them are byte-identical to before.

The Viewer owns the number: 240 px default, 200–420 px range, collapse toggle in the source bar
(`data-testid="viewer-inspector-toggle"`, `⌘⇧I` / `Ctrl+Shift+I`), both persisted in
`localStorage["tit-viewer-inspector"]`.

`getBoundingClientRect().width` on the `<iframe>`, height 900, **real embed in the real container**
(identical to the mock-server e2e's numbers, which the spec now asserts):

| window | inspector open | inspector collapsed |
|---|---|---|
| 1280 | **984 px** | **1224 px** |
| 1440 | **984 px** | **1224 px** |

Was 764 px @1280 and 924 px @1440. Both widths are the same now because FX1's rail change landed
(56 px icon rail at 1280, 216 px full rail at 1440) — the two effects cancel: 1280−56−240 =
1440−216−240 = 984. Collapsed is the whole content box at both widths.

Still short of the embed's own 1000 px panel-collapse threshold by 16 px with the inspector open.
That is a deliberate stopping point: dropping the inspector to 224 px would clear it at the cost of
a cramped layer list, and the collapse toggle clears it properly (1224 px) for anyone who wants the
embed's own panels. Worth revisiting with W1 — 984 vs 1000 is the sort of threshold that could
simply be lowered upstream.

## 4 (designer 5). The embed never got the app theme

`pages/viewer/index.tsx` now sends `setTheme` on every `ready` and on every repaint of the app. The
store gained `embedReady: boolean` (true on the `ready` message, false on `disconnect`) because
`status` only leaves `idle` once a scene is loading — a host with something to say to a freshly
booted, scene-less embed had no signal before.

The resolved palette is read off `<html data-theme>` (`readDocumentTheme` in `pages/viewer/lib.ts`)
via a `MutationObserver` plus a `prefers-color-scheme` listener, rather than off
`useThemeStore().theme`. That is not indirection: the store's third setting is `system`, and the
attribute — which `app/theme/store.ts`'s own `stamp()`/`initTheme()` write — is the single place the
*resolved* answer already exists. It also means anything that repaints the app re-themes the embed.

Measured inside the real embed's document (`frame.evaluate`):
```
light: { htmlTheme: "light", bodyBg: "rgb(255, 255, 255)" }
dark:  { htmlTheme: "dark",  bodyBg: "rgb(22, 24, 28)" }
```
Before the fix the two were byte-identical (QA's pixel sample of the toolbar). Screenshots:
`desktop/tests/e2e/artifacts/phase-c-fix/viewer-real-embed{,-dark}.png`.

The e2e asserts it against the fake embed: `fake-embed.js` now records the last `setTheme` on its
own `<body data-theme>`, and the spec checks light → dark → light.

## 5. Empty 3D pane, and layer sizes

- **Inline hint** over the canvas (`data-testid="viewer-3d-hint"`, non-interactive, bottom-centre):
  *"Enable a mesh layer to populate the 3D pane — grey_Thalamus_TI is hidden."* Derived from the
  live layer mirror by `hidden3DLayer()` (`pages/viewer/lib.ts`): fires only when the scene has at
  least one **mesh** layer and every mesh is switched off.

  **Mesh only, deliberately.** My first cut counted any layer the engine draws in 3D
  (`kind === "mesh" || showIn3D === true`) and the hint never fired on the real scene, because
  ernie/Thalamus's `electrode_overlay_subject` is `showIn3D: true` and visible — while the pane
  still reads as empty to a researcher. Verified against the live scene:
  ```
  L0 T1                              volume visible=True  showIn3D=False
  L1 electrode_overlay_subject       volume visible=True  showIn3D=True
  L2 Thalamus_TI_subject_TI_max      volume visible=False showIn3D=False
  L3 grey_Thalamus_TI_subject_TI_max volume visible=True  showIn3D=False
  L4 white_Thalamus_TI_subject_TI_max volume visible=False showIn3D=False
  L5 grey_Thalamus_TI                mesh   visible=False
  ```
  Real-container round trip: hint present → enable the mesh → `"(absent)"` → hide it again → hint
  back.

- **Size badge** per layer row, from the `loaded` message's `bytes` (a ViewSpec carries no file
  size, so a row states nothing until the loader has read the file — `DESIGN.md` §10 now says that
  instead of promising a size "before it is fetched", which the protocol cannot deliver). The store
  gained a `datasets: LoadedDataset[]` mirror seeded from the scene and replaced on `loaded`;
  `datasetFor()` matches a layer to its dataset by `datasetId` first and by position second (ids are
  re-issued by `Engine.load`). Real numbers:
  ```
  T1 105 MB · electrode_overlay_subject 53 MB · Thalamus_TI_subject_TI_max 105 MB ·
  grey_… 105 MB · white_… 105 MB · grey_Thalamus_TI 172 MB (jet)
  ```

- `withPreservedNames` → `withPreservedLayerFields`: `kind` and `datasetId` are now inherited
  alongside `name` when an embed build echoes only ids, because the two derivations above need them.

## 6 (researcher 1). `has_fastsurfer` chip

Added **before** `freesurfer`, matching `tit/catalog.py`'s own column order, in every surface that
renders `has_freesurfer`:

| file | surface |
|---|---|
| `app/subjectContext.ts` (`presenceChips`) | context bar, batch picker, anything using the shared vocabulary |
| `app/SubjectSwitcher.tsx` | the shell's subject switcher rows |
| `pages/subjects/index.tsx` | Project table "Data" column |
| `pages/preprocess/index.tsx` | the picker on the page that RUNS FastSurfer |
| `pages/simulator/index.tsx` | subject picker |
| `pages/optimizer-flex/index.tsx` | subject picker |
| `pages/panels/source/index.tsx` | subject picker |

Real container, Project table row for ernie: `ernie | raw | fastsurfer | freesurfer | m2m | 6` —
`fastsurfer` renders as a *missing* chip for ernie (correct: `has_fastsurfer: false`,
`has_freesurfer: true`), which is exactly the "does this subject still need the step" read the
finding asked for.

**Cross-lane touches, flagged:** `app/subjectContext.ts` and `pages/panels/source/index.tsx` are not
in this lane's file list. Both are one-line chip additions in the same shape as the owned ones, and
leaving them out would have left the context bar and the Source panel as the only surfaces missing
the chip. `tests/unit/shell-subject.test.tsx` (mine) updated to match.

## 7 (designer 4ii). Preprocess page header

Dropped the `header={<PageHeader …/>}` v1 escape hatch. The purpose sentence moved onto the section
it actually describes — an `IconButton` + `Tooltip` in `FormSection title="Processing steps"`'s
`helpSlot`: *"Convert, segment, and prepare subjects for simulation. Steps run in this order; charm
and FastSurfer run in parallel."*

`.page-layout-main` at **1280×800**, icon rail in play:

| | before (QA) | after |
|---|---|---|
| `.page-layout-main` | `{x:240, y:124, w:700, h:596}` | `{x:80, y:64, w:860, h:656}` |
| `.page-header` | 48 px | **absent** |

The width jump to 860 px is FX1's icon rail, not this change; the 60 px of height is. Still 20 px
short of §8's ≥880 px floor because the 300 px Plan inspector is unchanged on this page — that part
of designer finding 4(ii) is **not closed** and is left for whoever owns §8's floor to either meet
or restate (see followups).

`preprocess.spec.ts`'s `beforeEach` no longer waits on a "Pre-processing" heading (there is none) —
it waits on the first section heading and the subject picker.

## 8. Distinct copy for the two "no viewer" states

- `TetravoxFrame` `no-embed` (handshake timeout): **"The viewer did not answer"** — leads with the
  timeout, names the seconds, says a present-but-broken bundle looks the same, tells you to reload
  first.
- Viewer page `not bundled` (`capabilities.tetravox_embed.available === false`): **"This server has
  no viewer bundle"** — leads with the capability answer and says *nothing timed out, because
  nothing was mounted*.

Neither reuses the other's wording; `DESIGN.md` §10 now says why.

## 9 (researcher 4). Raw layer names

Display names stay the server's job (FX3 curates them in `viewspec`). The row renders `name` and,
**when it differs from the file**, a muted mono second line with the basename (`.viewer-layer-file`).
Today the server names a layer after its own file stem (`T1` ← `T1.nii.gz`), so the second line is
correctly absent everywhere; it appears the moment FX3's curated names land, with no further client
change. `layerFile()`'s branches are unit-tested; the e2e asserts today's true negative.
`DESIGN.md` §10 states the rule ("Layer names are the server's… no display-name mapping lives in
the client").

## Files changed

```
desktop/src/renderer/viewer/store.ts            embedReady, datasets mirror, withPreservedLayerFields, layout doc
desktop/src/renderer/viewer/TetravoxFrame.tsx   no-embed copy
desktop/src/renderer/viewer/index.ts            export LoadedDataset
desktop/src/renderer/pages/viewer/index.tsx     theme wire, inspector width/collapse, size badge, 3D hint, block removals
desktop/src/renderer/pages/viewer/lib.ts        NEW — pure helpers (deep link, layer rows, inspector prefs, theme read)
desktop/src/renderer/pages/viewer/viewer-page.css  size/file rows, handle, canvas wrap, hint; .viewer-shot removed
desktop/src/renderer/ui/Layout.tsx              +inspectorWidth/onInspectorResize/min/max, InspectorHandle (additive)
desktop/src/renderer/app/subjectContext.ts      fastsurfer chip (cross-lane, flagged)
desktop/src/renderer/app/SubjectSwitcher.tsx    fastsurfer chip
desktop/src/renderer/pages/{subjects,preprocess,simulator,optimizer-flex}/index.tsx  fastsurfer chip
desktop/src/renderer/pages/panels/source/index.tsx  fastsurfer chip (cross-lane, flagged)
desktop/src/renderer/pages/preprocess/index.tsx page header dropped, purpose → section help
desktop/DESIGN.md                               §10 rewritten (ownership, inspector width, loading, names, two states)
desktop/tests/e2e/fixtures/fake-embed/fake-embed.js  records setTheme; `loaded` sends dataset objects with bytes
desktop/tests/e2e/viewer.spec.ts                +theme, +size/file/3D, +width measurements; screenshot test removed
desktop/tests/e2e/preprocess.spec.ts            +no-header geometry test; beforeEach no longer waits on a heading
desktop/tests/unit/viewer-page.test.ts          NEW — hidden3DLayer, layerFile/datasetFor, inspector prefs, deep link
desktop/tests/unit/viewer-store.test.ts         +datasets mirror, +embedReady/setTheme; layers case updated
desktop/tests/unit/shell-subject.test.tsx       fastsurfer in the chip vocabulary
```

## Gate

```
npm run typecheck   clean
npm run lint        0 errors, 3 warnings (all pre-existing: VirtualList ×2, DataTable — react-compiler)
npx vitest run      46 files, 499 tests passed
npm run build       ok
e2e (quiet)         20 passed — viewer.spec.ts, results.spec.ts, preprocess.spec.ts, smoke.spec.ts
                    "no Electron/Chromium window reached the screen"
real container      status ready (after settle), theme light/dark applied to the embed's own
                    document, iframe 984/1224 px at both 1280 and 1440,
                    screenshots in desktop/tests/e2e/artifacts/phase-c-fix/
```

Mid-lane note: `npm run typecheck` failed twice with `TS6307` on `src/main/{hostInfo,userConfig}.ts`
not being listed in `tsconfig.web.json` — another lane's files mid-edit. Clean on the final run.

## Followups / not closed

1. **Embed→host `layout` event** (W1 / tetravox). Without it no host can render an honest layout
   control. Until it exists, `DESIGN.md` §10 forbids one.
2. **Embed's 1000 px panel threshold vs our 984 px** with the inspector open. Either the embed
   lowers it or TI narrows the inspector further; the collapse toggle is the workaround today.
3. **DESIGN.md §8's ≥880 px work-pane floor is still not met on Preprocess** (860 px at 1280×800)
   because of the 300 px Plan inspector. Not this lane's to decide: either shrink/collapse the Plan
   inspector on plan-bearing pages or restate the floor. Designer finding 4(ii), second half.
4. **`viewer status` flickers to `error` for ~1 s** on a simulation switch against the real embed
   before settling to `ready`, with no error text ever rendered (`viewer-error` never mounts). Looks
   like the embed reporting a failure for the outgoing scene's datasets while the new `load` is in
   flight. Harmless today; a store that ignored an `error` arriving while a newer `load` is pending
   would be tidier. Not touched — it needs the embed's message ids to do properly.
5. **40 `<line> attribute x1/x2: Expected length "±Infinity"` console errors** from inside the real
   embed during resize/layout use — designer finding 6, upstream, unchanged.
6. **`.viewer-layer-file` renders nothing until FX3 lands curated names.** By design; nothing to do
   here, but it means researcher finding 4 is only half-closed from this side.

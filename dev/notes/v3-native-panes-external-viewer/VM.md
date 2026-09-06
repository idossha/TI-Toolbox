# Lane VM — the Viewer as a composition panel

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-06.
Follows lane **VX** (`VX.md`), which made the Viewer a data selector and retired the embed.

Maintainer's screenshot, and the ask, verbatim: the page was *"a thin top bar (`TYPE · SUBJECT ·
ATLAS · Subject|MNI · Open in Tetravox`) over a huge black empty area with a faint ghost 'What will
open / T1.nii.gz grayscale / labeling.nii.gz lut' text"*, and — *"make the menu for the visualizer
much more extensive and centred — since the viewer opens in its own window, the page can be
graceful and let users enjoy an extensive menu experience."*

Every Playwright run was offscreen (`scripts/e2e-quiet-check.sh`); **no window reached the screen
and Tetravox was never launched**. Nothing was stashed, reverted or checked out. The shared
container `ti-toolbox-fad740e5-tit-1` was used over HTTP and left as found (§5.2).

---

## 1. The one rule the design is derived from

**Every knob the panel shows has to land in the scene file.**

A viewer page with no viewer in it is a form, and a form's only failure mode that nobody can see is
a control whose value goes nowhere. So the panel's vocabulary was not designed and then asked of
the server; it was read *out of* what the server can write — `to_tetravox_viewspec`'s own per-layer
fields, and through them the engine's frozen ViewSpec v2 type
(`contracts/tetravox-viewspec-v2.schema.json`).

Two consequences worth stating, because both were tempting and both are wrong:

- **There is no "electrodes as points" checkbox.** The brief asked for one *if the ViewSpec
  supports points*. It does not: v2 has `VolumeLayer` and `MeshLayer` and nothing else. What exists
  is the electrode **overlay volume** (`tit/viewspec.py::_electrode_overlay_layer`, built by the
  `tools` job `tit.tools.electrode_overlay`), so "Also open" offers that and says so.
- **There is no free-text colormap and no arbitrary layout.** Both are validated server-side
  against a closed set and *dropped* when they do not match, so a stale preset from six months ago
  cannot produce a document the app refuses to open.

## 2. What was built

### Server (`b48fa120`, plus the presets in `24566623`)

| File | What |
|---|---|
| `tit/viewspec.py` | **`apply_scene_overrides(scene, overrides)`** — the whole feature, as one pure function on a finished scene. `SCENE_LAYOUTS` (4), `CAMERA_PRESETS` (6 quaternions), `SCENE_BACKGROUNDS` (3), `EXTRA_LAYERS` (4) and `_extra_layers()`. `build_view` gains `extras=` and `overrides=`, both optional; `_apply` is the two-line no-op wrapper each branch returns through. `_DEFAULT_BACKGROUND` moved up the file (it is `SCENE_BACKGROUNDS["dark"]`, and the rig constants come later). |
| `tit/server/routes/viewers.py` | `view_open` takes `extras`, `overrides` and `dry_run`; answers `files` (`_scene_files`: id, kind, name, host-facing path, size or `null`). **`GET/PUT/DELETE /api/viewer/presets[/{name}]`** — plain JSON under `<project>/code/ti-toolbox/viewer/presets/`. |
| `tit/server/schemas.py` | `ViewerSceneFile`; `ViewerOpen.files` / `.dry_run`. |
| `tests/test_viewspec_overrides.py` | **27 new tests.** |
| `contracts/` | `openapi.v1.yaml` (+ `.json`, + `schema.d.ts` via `pnpm run gen:api`, + the mock's `tests/fixtures/openapi.v1.json`): three request fields, two response fields, `ViewerSceneFile`, `ViewerPreset`, three preset paths. `SCHEMA-CHANGES.md` entry. **`tetravox-viewspec-v2.schema.json` is unchanged** — nothing here emits a field it did not already allow, which is the cheapest possible evidence that the panel stayed inside the engine's type. |

### Desktop (`24566623`, `…` css follow-up)

| File | What |
|---|---|
| `pages/viewer/index.tsx` | The panel. `Section` (eyebrow + one-line description) and `Row` (label-left) are local; everything else is `ui/` primitives — `Select`, `SegmentedControl`, `Slider`, `Checkbox`, `NumberInput`, `Popover`, `Button`. Three pieces of session state now: `selection`, `extras`, `composition`. |
| `pages/viewer/lib.ts` | `Composition`, `LayerOverride`, `SceneLayer`, `overridesPayload`, `layerKindLabel`, `formatBytes`, `selectionLabel`, `readRecents`/`pushRecent`, and the option tables (`LAYOUT_/CAMERA_/BACKGROUND_/EXTRA_OPTIONS`, `COLORMAP_OPTIONS`). |
| `pages/viewer/api.ts` | `openView(kind, query, {extras, overrides, dry_run})`, `previewView`, `getPresets`/`savePreset`/`deletePreset`. |
| `pages/viewer/viewer-page.css` | Rewritten. The `--canvas` ground is gone with the canvas; a centred 880 px column on `--bg`, 12 px rhythm, layer cards in a two-column control grid, a sticky footer. |
| `desktop/DESIGN.md` §10 | Rewritten for the panel (diagram, the derivation rule, the four sections, presets-vs-recents, the three states). |
| `tests/mock-server/server.mjs` | A deliberate mirror of `apply_scene_overrides`, plus `files` with deterministic stand-in sizes and an in-memory preset store. |
| `tests/unit/viewer-page.test.ts` | +11 tests (payload shaping, kind labels, byte formatting, recents). |
| `tests/e2e/{viewer,smoke,page-memory}.spec.ts` | see §3. |

### The knobs, exactly

| Where | Knob | Lands as |
|---|---|---|
| Layer row | eye | `layers[].visible` |
| | opacity | `layers[].opacity` (clamped 0…1) |
| | colormap (volumes) | `layers[].colormap` |
| | threshold lo / hi | `layers[].threshold.{lo,hi}` (`null` clears) |
| | in 3D (volumes) | `layers[].showIn3D` |
| | colour by (meshes) | `layers[].colorMode` |
| | clip plane (meshes) | every `layers[].clip.planes[].enabled` |
| Layout & camera | panes | `layout.{kind,cells}` — `1x1 · 1+3 · 2x2 · 3d-only` |
| | camera | `view3d.camera.rotation` — six unit quaternions |
| | background | `background` — dark / black / light, or a vec4 on the wire |
| | convention | `radiological` |
| Also open | T1 · atlas · electrode overlay · GM surface | extra entries in `layers`/`datasets` |

Plus one thing the panel does that no control asked for: after applying overrides, `activeLayerId`
is moved to a *visible* layer if hiding one orphaned it. Otherwise the app opens with its inspector
pointed at something nobody can see, and the cause is three steps away.

## 3. Gate

| Command | Result |
|---|---|
| `pnpm run typecheck` | clean |
| `npx eslint src tests` | 0 errors, 3 pre-existing warnings (`ui/DataTable.tsx`, `ui/VirtualList.tsx`) |
| `npx vitest run` | 92 files, 1082 passed |
| `pnpm run build` | clean |
| `python3 -m pytest tests/test_viewspec*.py tests/test_view_open.py -q` | 98 passed |
| `python3 -m pytest tests/ -q` | 3729 passed, 47 skipped — plus one **unrelated cross-module flake**, §5.1 |
| `python3 dev/route_import_guard.py` | 20 route modules clean |
| `bash scripts/e2e-quiet-check.sh npx playwright test viewer smoke page-memory layout --workers=1` | **41 passed, 1 failed** — the failure is `layout.spec.ts`'s **preprocess** dead-space budget (64.5 % > 62 % at 1440), a page this lane does not touch; §5.1 |

Offscreen every time: *"no new Electron/Chromium window reached the screen."*

### 3.1 The e2e assertions this lane added

The gate's counting method changed shape, and that is worth stating because it is easy to get
wrong: **the preview resolves through the same `POST /api/view/open` with `dry_run: true`**, so
"how many requests did drafting cost" and "how many scenes did drafting write" stopped being the
same question. `opens()` now filters `dry_run` out, and every existing "editing the draft launches
nothing" assertion is unchanged in meaning: no *scene*, no *launch*.

- *the panel shows every section, and the preview strip names the files with their sizes* — the
  four sections, `canvas` count 0, and a size on the first row.
- *drafting the composition still opens nothing, and Open carries it* — dry runs > 0, writes 0,
  launches 0; then an opacity, a layout and a camera, and the one Open's body carries all three.
- *a layer opacity change reaches the scene the server writes* — read off the Open's **response**,
  which is byte-for-byte what went to disk.
- *hiding a layer is written as a hidden layer, not as a missing one.*
- *an 'Also open' tick rides on the Open as an extra.*
- *a preset saves the whole composition and restores it without opening anything.*
- *the Recent list remembers what was opened and restores it* — disabled until something is
  actually opened, because a recent is a footprint and not a draft.
- `page-memory`: a camera preset and an extra survive a tab switch, like the selection always did.
- `smoke`: `viewer-panel` and the four sections are what "the Viewer rendered" means now.
- Screenshot: `desktop/tests/e2e/artifacts/viewer-menu.png`, 1440, full page.

### 3.2 Real — the live container, `sub-ernie`

`http://127.0.0.1:8765`, project `/Users/idohaber/datasets/000`, which mounts this worktree, so the
running server *is* this code.

```
POST /api/view/open  kind=simulation subject=ernie simulation=L_Insula space=subject
  extras   ["t1","electrodes"]
  overrides {layers:{L0:{opacity:.3,colormap:"viridis"},L1:{visible:false}},
             layout:"1+3", camera:"L", radiological:true, background:"black"}

dry_run=true  → files: T1.nii.gz 13 109 495 · L_Insula_TI_subject_TI_max.nii.gz 17 450 987 ·
                       grey_… 3 113 933 · white_… 2 628 530 · grey_L_Insula_TI.msh 63 926 663
                wrote nothing on the host: True
dry_run=false → host_path /Users/idohaber/datasets/000/code/ti-toolbox/viewer/simulation.tetravox.json
                layout   {'kind': '1+3', cells: [view3d, axial, coronal, sagittal]}
                camera   [0.0, -0.70710678…, 0.0, 0.70710678…]        (L)
                radiological True   background [0,0,0,1]
                layers   L0 T1 0.3 viridis visible · L1 TI_max hidden · L2 GM visible · …

schema errors : 0   (contracts/tetravox-viewspec-v2.schema.json, Draft 2020-12)
missing files : []  (every dataset path resolves on the host)
scene on host : 7 190 bytes  (Tetravox's own cap is 8 MB)

no overrides, no extras == the pre-VM document, byte for byte : True
presets       : PUT → GET → DELETE round-trip, live
```

The 64 MB mesh in that list is the argument for the preview strip: it is exactly the fact a person
wants **before** another window opens, not after it has spent thirty seconds loading.

## 4. Two findings

**4.1 The extras had to reuse the *existing* layer builders, not new ones.** The first sketch built
"add the T1" as its own `_layer(...)` call. That is a second, independently-configured description
of the same file — a different opacity here, a different colormap there — and the two would drift
the first time anyone tuned one of them. `_extra_layers` calls `_subject_t1_layer`,
`_subject_atlas_layer`, `_electrode_overlay_layer` and `_grey_mesh_layer`, de-duplicates by path,
and therefore an extra the chosen view type already opens is a **no-op**. That is what makes a tick
safe to leave on across a change of view type, which is the only way the checkbox is usable.

**4.2 `/api/view/presets` would have been shadowed, silently.** `GET /api/view/{kind}` is
registered first, so `GET /api/view/presets` reaches `build_view(kind="presets")`, which returns
`None`, which the route turns into a **404** — indistinguishable, from the client, from "you have
no presets". The path is `/api/viewer/presets`. Written down here because the failure has no error
in it anywhere.

## 5. Open items

1. **`layout.spec.ts`'s preprocess dead-space budget is red on this branch** (64.5 % vs 62 % at
   1440 light; 1280 passes). Pre-processing is not this lane's page and nothing here touches it —
   it is another lane's in-flight work, or a budget that wants re-deriving. Flagged, not fixed.
2. **`tests/test_scene_guide.py::test_the_legend_colour_is_read_from_the_colour_table…` fails only
   in a full-suite run** and passes on its own (14 passed). It is the known sys.modules-mocking
   order hazard `tests/test_stats_config.py` documents, in another lane's module.
3. **Browser-mode download is still not e2e-proved** (VX §8.1, unchanged): the Playwright suite runs
   the Electron shell, where `window.tit` always exists.
4. **`pages/viewer/PARITY.md`** still describes the embed's gaps and was again left alone; several
   of its rows (layer opacity, colormap, threshold, layout, camera) are now *closed by this lane*,
   and a pass over it wants whoever owns the parity question.
5. **Presets are per-project and unversioned.** A preset saved against a simulation that is later
   deleted restores a selection that resolves to nothing; the panel says so through the normal
   empty-preview path rather than pruning presets behind a person's back. If that becomes annoying
   the fix is a "this preset no longer resolves" mark, not a deletion.
6. **The camera presets are rotations of the engine's identity framing**, not a claim about its
   world axes — which this server cannot see. `A` is identity; the other five are quarter- and
   half-turns. If the app's default framing is ever not anterior, the *labels* are wrong and the
   quaternions are still valid; that is a one-line table edit in `CAMERA_PRESETS`.

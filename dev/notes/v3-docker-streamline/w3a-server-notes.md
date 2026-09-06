# W3a — Server: Tetravox serving + scene v2 (2026-09-03)

Lane brief: `dev/notes/v3-docker-streamline-plan.md` row W3a. Read in full before starting: that
plan's D1–D6 + §1/§2/§3, `dev/notes/v3-native-desktop-plan.md` §0 + N0 RESULTS,
`dev/notes/v3-research/r3-server-viewer-side.md` (the F2 work already landed: `/api/files/raw`,
`to_tetravox_scene`, Pydantic `TitScene` — all superseded here), `dev/spikes/native/docker/REPORT.md`,
and the real Tetravox ViewSpec v2 sources at `/Users/idohaber/00_development/tetravox`
(`packages/engine/src/scene/{types,serialize}.ts`, `packages/app/src/shared/scenes/*.tetravox.json`
fixtures). `/Users/idohaber/00_development/tetravox-wt-embed/packages/embed` had only
`package.json`/`vite.config.ts` at read time — no `protocol.ts`, no `docs/EMBED.md` yet (W1 still
in progress) — so the fake embed and the raw-URL design here are built against the plan's §4.5
protocol summary and the frozen engine types, not against W1's actual code.

## What shipped

1. **`tit/viewspec.py::to_tetravox_viewspec(spec)`** replaces `to_tetravox_scene`: emits a real
   Tetravox `ViewSpec` v2 document, not a TI-shaped approximation. Every required field of the
   frozen engine type is present with a concrete value (no percentile-window shortcut — see the
   module's own docstring for the two design consequences that follow from `Engine.load()`
   restoring most of the document verbatim). `_grey_mesh_layer` is new: `build_view`'s
   `kind="simulation"` branch now also emits the hidden grey-matter TI mesh layer (elm `TI_max`
   field, a cursor-following clip plane, 2D contours) when one exists on disk.
2. **`contracts/tetravox-viewspec-v2.schema.json`** — hand-written, host-facing JSON Schema for
   the subset of the engine's type this server actually emits. `tests/test_viewspec_scene.py`
   validates every scene it builds against it (`jsonschema.Draft202012Validator`), including a
   sweep across every `build_view` kind.
3. **`/tetravox/{path}`** (`tit/server/static.py`) — a second static route, distinct from the
   main UI bundle's catch-all, serving `ServerSettings.tetravox_embed_dir` (env
   `TIT_TETRAVOX_EMBED_DIR`, CLI `--tetravox-dir`, default `/opt/tetravox/embed`) with its own
   CSP (`TETRAVOX_CSP`), correct MIME per extension, a jail, `index.html` for the bare/slash/
   `index.html` paths, and a straight 404 (not a SPA fallback) for a missing directory or an
   unknown asset. `tit/server/app.py`'s main `CSP_HEADER` drops `'wasm-unsafe-eval'` — the
   embed's own CSP carries it now, and nothing in the app's own origin needs it.
4. **`Capabilities`** drops `freesurfer`/`x11_display`/`gmsh`/`freeview`; adds
   `tetravox_embed: {available, version, protocol}` (manifest-probed, fails closed) and
   `fastsurfer: bool`. Changed in `tit/server/schemas.py`, `tit/server/routes/capabilities.py`,
   **both** `contracts/openapi.v0.yaml` and `openapi.v1.yaml` (v0's own header commits it to
   tracking the live runtime's actual surface, not a frozen Phase-0 shape — see
   `contracts/SCHEMA-CHANGES.md`'s new entry for the reasoning).
5. **`POST /api/viewers/{freeview,gmsh}` and `_require_x11` deleted** from
   `tit/server/routes/viewers.py` (and their contract paths). `GET /api/view/{kind}` and
   `POST /api/view/args` are unconditional now — no capability check gates them. `tit.jobs`'s
   `"viewer"` kind is unreferenced by this server as of this change but **not deleted** —
   `tit/jobs/kinds.py` is not in this lane's owned paths; see `needs_from_other_lanes` below.
6. **Fake embed** at `desktop/tests/e2e/fixtures/fake-embed/{index.html,manifest.json}` — a
   deterministic, dependency-free implementation of enough of protocol v1 to drive a desktop e2e
   spec without the real WASM/WebGL2 bundle: `ready`/`hello`, `load`→`loaded`+`status`, a visible
   `data-testid="fake-embed-layers"` list, `setCursor`→`cursor`, `probe`→`probe`,
   `screenshot`→a 1×1 PNG data URL, `setLayerVisible`/`setLayerOpacity`→`layers`, `reset`. Origin
   checked against a `?hostOrigin=` query param, mirroring the real protocol's rule. Wired into
   the mock server at `/tetravox/` (env `TIT_MOCK_EMBED_DIR`, default = this fixture dir);
   `desktop/tests/mock-server/server.mjs`'s `sceneFor`/`buildViewSpec` rewritten to the same
   ViewSpec v2 shape as the Python side, and the `/api/viewers/{freeview,gmsh}` mock routes
   replaced with a real `POST /api/view/args` mock (freeview args/command preview + scene,
   matching what `tit/server/routes/viewers.py` now does).

## Design decision: how a `DatasetRef` points at bytes

The plan's §1 line says "absolute same-origin `/api/files/raw/...` refs" — ambiguous between
"absolute path" (leading `/`, no scheme/host) and "absolute URL" (scheme+host). Resolved by
reading the engine's own `scene/serialize.ts`: `Engine.load(spec, resolve)` takes a **host-supplied
resolve callback**, and `candidatePaths`/`joinPath`/`relativePath` treat any string beginning with
`/` as already-absolute, passing it through unchanged regardless of which of `path`/`absPath` a
host prefers. Since the embed is served from this same `tit.server` at `/tetravox/`, an
origin-relative path is directly `fetch()`-able from inside its iframe with zero rewriting. Both
`DatasetRef.path` and `.absPath` (and both `SidecarRef.path`/`.absPath`) are therefore set to the
identical `/api/files/raw/<abs path>` string — robust to whichever field a real host's `resolve`
implementation ends up preferring, and it means the earlier plan-doc language about "the client
prefixes `location.origin`" is unnecessary in the *embed-as-iframe* architecture this program
actually built (it was written for a different, in-process-engine design that Stage 2b retired).

## Design decision: field/window numbers are real, not percentiles

The real `ViewSpec`'s `Scale` type has no `{percentile:{lo,hi}}` shape at all — that was a
Stage-0, TI-only invention this lane's predecessor (`to_tetravox_scene`) carried over from the
Freeview `ViewLayer.percentile` field. A document this server emits has to be valid input to
`Engine.load()`, so `_volume_stats`/`_volume_scale` read one NIfTI (numpy percentiles over its
non-zero voxels, cached by `(mtime, size)`) to produce a concrete triple. A `.msh` field layer's
own value range is *not* read separately (files run 24–420 MB); its scale/threshold are a
documented approximation borrowed from the sibling NIfTI field layer's own resolved window,
justified because both describe the same physical field just voxelised vs. per-element.

## Known limitation (documented, not a bug): no per-file camera fit

`slices`/`view3d`/`annotations`/`background`/`lighting`/`transparency` are one fixed rig
(`_DEFAULT_SLICES` etc. in `tit/viewspec.py`), not a computed "fit to this head" camera — this
server never reads a NIfTI's affine/bounds for that purpose. A freshly loaded scene will not be
perfectly framed; a host may re-fit after `loaded`. Flagged explicitly in the module docstring so
it reads as a decision, not an oversight.

## Gates — commands and results

```
$ python3 -m pytest -q tests/                                          # host, py3.14
3140 passed, 18 skipped, 2 failed (pre-existing, see below)

$ docker exec -w /ti-toolbox tit-v3-spike simnibs_python -m pytest -q \
    tests/test_catalog_v1.py tests/test_server_skeleton.py tests/test_viewspec.py \
    tests/test_viewspec_scene.py tests/test_files_raw.py tests/test_files_routes.py
212 passed, 1 failed (same pre-existing failure, narrower file set)

$ python3 -m black --check <every touched .py file>
All done — clean

$ python3 dev/build_contract.py                          # regenerate openapi.v1.json
$ python3 -m tit.server --dump-openapi /tmp/dump/openapi.json --project /tmp/dump
$ python3 dev/contracts_check.py contracts/openapi.v0.yaml /tmp/dump/openapi.json
contracts_check: OK — 10 operation(s) and 9 schema(s) present
$ python3 dev/contracts_check.py contracts/openapi.v1.yaml /tmp/dump/openapi.json
contracts_check: 49 problem(s)   # pre-existing; see below, none touch this lane's schemas

$ cd desktop && npx vitest run tests/mock-server
Test Files  2 passed (2) / Tests  21 passed (21)

$ cd desktop && npm run gen:api
regenerated src/renderer/api/schema.d.ts

$ cd desktop && npm run typecheck
tsconfig.node.json: clean
tsconfig.web.json:  11 errors, all in desktop/src/renderer/** (not owned by this lane)
```

### The two pre-existing host-pytest failures (not caused by this lane)

- `tests/test_server_skeleton.py::test_process_filter_matches_qt_list` — compares
  `tit/server/routes/system.py::RELEVANT_KEYWORDS` (not owned by this lane) against
  `tit/gui/system_monitor_tab.py`'s list (shows as locally modified, `git status`: `M`) — another
  lane has already renamed a keyword `freesurfer`→`fastsurfer` there but not yet in
  `tit/server/routes/system.py`.
- `tests/test_plan_routes.py::test_plan_pre_builds_full_dag_for_two_subjects` — asserts an exact
  DAG-stage set that is missing `G2b` (`tit/jobs/plans.py`, not owned by this lane and shows as
  untracked/new — matches W3b's brief: "DAG G2b = FastSurfer").

Both reproduced identically inside the container. `tests/test_catalog_v1.py::test_subject_info_matrix`
had the same kind of drift (a new `"fastsurfer"` column from `tit/catalog.py`, also not owned by
this lane) and **was** fixed here, since it lives in a file this lane owns
(`tests/test_catalog_v1.py`) — updated to assert by column name rather than a fixed index/list so
it does not re-break the next time that column set grows.

### The 49 pre-existing `openapi.v1.yaml` contract problems

None reference anything this lane owns — verified by grepping the tool's own output for
`capabilit|viewspec|viewer|scene|tetravox` (6 hits, all `JobKind` enum members inherited
transitively from `PlanJob`/`LockConflict`/`PlanResult`, none from `Capabilities`/`ViewSpec`
directly). The root cause is that most `tit/server/routes/*.py` modules return
`-> dict[str, Any]` rather than a typed Pydantic `response_model`, so FastAPI's dump never
gives their schemas (`JobStatus`, `Settings`, `TableData`, …) a name at all — a structural gap
across the whole v1 contract that predates and is unrelated to this lane's changes (same
88-schema dump count with or without a live-socket `--dump-openapi` subprocess vs. an in-process
`app.openapi()` call).

## contracts_for_other_lanes

- **Scene shape**: `GET /api/view/{kind}` → `{space, layers, freeview_args (deprecated), scene}`.
  `scene` is a Tetravox `ViewSpec` v2 document per `contracts/tetravox-viewspec-v2.schema.json`.
  Every `datasets[].path` **and** `.absPath` is the identical string
  `/api/files/raw/<abs path without leading slash, percent-encoded>` — an origin-relative URL,
  fetchable directly from inside a same-origin `/tetravox/` iframe, never a container filesystem
  path. `fingerprint` is always `""`. Example (real `sub-ernie`, `GET /api/view/subject?subject=ernie`
  shape, abbreviated):
  ```json
  {
    "version": 2,
    "datasets": [
      { "id": "ds0", "kind": "volume", "name": "T1.nii.gz",
        "path": "/api/files/raw/mnt/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz",
        "absPath": "/api/files/raw/mnt/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz",
        "fingerprint": "" }
    ],
    "layers": [
      { "id": "L0", "datasetId": "ds0", "kind": "volume", "name": "T1", "visible": true,
        "opacity": 1.0, "pickable": true, "showColorbar": true, "volumeIndex": 0,
        "colormap": "gray", "scale": { "kind": "linear", "lo": 0.0, "hi": 4000.0 },
        "threshold": { "lo": null, "hi": null, "symmetric": false, "mode": "clamp", "softEdge": 0.0 },
        "interpolation": "linear", "labelMode": "fill", "outlineWidthPx": 1.0,
        "showIn3D": false, "precision": "auto" }
    ],
    "activeLayerId": "L0",
    "slices": ["…3 SliceView entries, a fixed default camera…"],
    "view3d": "…a fixed default camera…",
    "layout": { "kind": "2x2", "cells": ["axial", "coronal", "sagittal", "view3d"] },
    "cursor": [0.0, 0.0, 0.0],
    "radiological": false,
    "background": [0.0588, 0.0667, 0.0863, 1.0],
    "lighting": { "ambient": 0.25, "headlight": true },
    "annotations": { "…7 boolean/const flags…": true },
    "transparency": { "mode": "twoPhase" }
  }
  ```
  A `kind=simulation` scene's mesh layer additionally carries
  `field: {source:"elm", name:"TI_max", component:"mag"}`,
  `clip: {planes:[{plane:{normal:[1,0,0],offset:<cursor.x>}, enabled:true, followCursor:true}], caps:true, capColorMode:"inherit"}`,
  `contoursIn2D: true` for a `grey_*` mesh.
- **Capability fields**: `Capabilities = {docker_socket, bpy, jupyter, tetravox_embed:
  {available, version, protocol}, fastsurfer}`. No more `x11_display`/`freeview`/`gmsh`/
  `freesurfer`.
- **Embed route/CSP**: `GET /tetravox`, `/tetravox/`, `/tetravox/<asset>` — unauthenticated,
  jailed to `ServerSettings.tetravox_embed_dir`, `content-security-policy:
  default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:;
  connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'`
  on every response under the prefix, 404 (not a SPA fallback) for a missing directory or an
  unknown asset. The app's own top-level CSP (served at `/`) no longer includes
  `'wasm-unsafe-eval'`.
- **Fake-embed message set** (`desktop/tests/e2e/fixtures/fake-embed/index.html`, protocol v1
  subset): host→embed `hello`, `load {scene}`, `setCursor {world}`, `probe {id, world}`,
  `screenshot {id}`, `setLayerVisible {layerId, visible}`, `setLayerOpacity {layerId, opacity}`,
  `reset` (accepted but inert: `setTheme`, `setLayout`, `updateLayer`, `setActiveLayer`, `focus`);
  embed→host `ready {version:"fake", caps:{webgl2:true}}`, `loaded {datasets, layers}`,
  `status {phase}`, `cursor {world}`, `probe {id, result:{world, rows}}`,
  `screenshot {id, dataUrl}`, `layers {layers}`. Origin-checked against `?hostOrigin=`.

## needs_from_other_lanes (not edited here — outside this lane's owned paths)

- **`tit/jobs/kinds.py`** (W3b): the `"viewer"` `JobKind` branch and `VIEWER_PROGRAMS` constant
  are now dead code — nothing submits a `"viewer"` job any more. Safe to delete along with
  `"viewer"` from the `JobKind` enum wherever else it's declared.
- **`tit/server/routes/system.py`** (owner unclear — not W3a): `RELEVANT_KEYWORDS` still says
  `"freesurfer"`; `tit/gui/system_monitor_tab.py`'s own list (uncommitted WIP from another lane)
  has already moved to `"fastsurfer"`. `tests/test_server_skeleton.py::test_process_filter_matches_qt_list`
  is correctly failing on this real drift.
- **`desktop/src/renderer/**`** (W4/W5): 5 files reference the now-removed API surface and will
  not typecheck until updated —
  `src/renderer/pages/analyzer/api.ts:200,210`, `src/renderer/pages/optimizer-flex/api.ts:66`,
  `src/renderer/pages/results/api.ts:63,67`, `src/renderer/pages/viewer/api.ts:45,49` (all call
  `POST /api/viewers/{freeview,gmsh}`, which no longer exist in `schema.d.ts`), and
  `src/renderer/pages/viewer/index.tsx:428,429,435,436,509` (read
  `capabilities.{freeview,x11_display,gmsh}`, which no longer exist on `Capabilities`). This is
  Phase B/C's "un-vendor, viewer-on-the-embed" work per the plan's W5 row — the exact shape it
  needs to call instead is `capabilities.tetravox_embed.available` to gate mounting the
  `/tetravox/` iframe, and there is no server-side launch route to call at all any more (the
  client loads the scene into the iframe itself via the postMessage `load` message).

# R3 — Server / viewer side map for the Tetravox internal-viewer integration

Reader R3. Everything below is verified against the worktree
`/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui` (branch
`feature/v3-electron-gui`, uncommitted WIP — **nothing was modified**), the real data at
`/Users/idohaber/datasets/000` (mounted `/mnt/000`), and the **running** container
`tit-v3-spike` (image `idossha/simnibs:v2.5.0`, worktree bind-mounted at `/ti-toolbox`,
dataset at `/mnt/000`). Every prototype below was executed inside that container against
real `sub-ernie` files; the outputs are quoted verbatim.

Container runtime, measured:

```
$ docker exec tit-v3-spike simnibs_python -c "import starlette, fastapi, sys; ..."
starlette 1.6.0
fastapi   0.141.1
python    3.11.14 | packaged by conda-forge
```

---

## 0. Executive summary — the eight server-side deltas

| # | Delta | Where |
|---|---|---|
| 1 | **New `GET`/`HEAD /api/files/raw?path=`** — jailed byte-streaming of `.nii/.nii.gz/.msh/.gii/.msh.opt/*_LUT.txt/.lut/.geo/.annot/.mgz`, *not* subject to `_ALLOWED_ARTIFACT_EXTS`. Starlette 1.6's `FileResponse` already gives Range/206/`Accept-Ranges`/`Content-Length`/ETag; only 304 and HEAD need adding by hand. | `tit/server/routes/files.py` |
| 2 | **`GET /api/view/{kind}` gains an additive `scene` object** (Tetravox-shaped), built by a new `tit/viewspec.py::to_tetravox_scene(spec, ...)`. `freeview_args` stays. Optional thin alias `GET /api/scene/{kind}`. | `tit/viewspec.py`, `tit/server/routes/viewers.py` |
| 3 | **`Capabilities` gains `internal_viewer: bool`** and `x11_display` stops gating anything but the *external* launchers. `_require_x11` stays on `/api/viewers/{freeview,gmsh}` only. | `tit/server/schemas.py`, `tit/server/routes/capabilities.py`, `tit/server/routes/viewers.py` |
| 4 | **CSP: add `script-src 'self' 'wasm-unsafe-eval'`.** Without it the Rust→WASM module cannot be instantiated in the app origin. Everything else the viewer needs is already in `CSP_HEADER`. | `tit/server/app.py:23-27` |
| 5 | **Contract**: 2 new paths (`/api/files/raw` GET+HEAD, optionally `/api/scene/{kind}`), 1 new required `Capabilities` field, `ViewSpec.scene`, and ~6 new `components.schemas` (`TitScene`, `SceneDataset`, `SceneLayer`, …). | `contracts/openapi.v1.yaml` |
| 6 | **Tests**: `tests/test_files_routes.py` (raw route: jail, Range, HEAD, 304, ext policy), `tests/test_viewspec.py` (`to_tetravox_scene` mapping), `tests/test_server_skeleton.py` (`CSP_HEADER` literal + `Capabilities` key set), `tests/test_catalog_v1.py` (x11 gating narrowing). | `tests/` |
| 7 | **Mock server**: `GET/HEAD /api/files/raw` streaming real bytes out of a `TIT_MOCK_DATA_DIR`, plus a `scene` block in `buildViewSpec`. The contract self-test asserts **exact** path coverage, so every new contract path *must* be exercised. | `desktop/tests/mock-server/server.mjs`, `desktop/tests/mock-server/contract.test.ts`, `desktop/playwright.config.ts` |
| 8 | **Do NOT emit a `*.tetravox.json` `ViewSpec` from the server.** Its `DatasetRef.fingerprint` is defined over the *post-gunzip* bytes (`docs/ARCHITECTURE.md:733-757`), which would force the server to inflate every `.nii.gz` per request, and its `path` is *relative to the scene file*, which has no meaning over HTTP. Emit a small TI-Toolbox-owned scene the renderer replays through the `Engine` facade. | design decision, §4.1 |

---

## 1. Inventory — every server-side surface the internal viewer touches

### 1.1 `tit/viewspec.py` — the layer-building domain layer

The whole file is 539 lines and is the *only* place that decides which files a view contains.

* Module docstring, `viewspec.py:1-70`: states this reproduces `tit/gui/nifti_viewer_tab.py`'s
  layer logic as a pure function, and enumerates six audit bugs fixed here.
* `_VIEW_KINDS = ("subject", "simulation", "analysis", "group", "custom")` — `viewspec.py:82`.
* `mni_resources_dir()` — `viewspec.py:85-94`. `/ti-toolbox/resources/atlas` when it exists
  (`tit/atlas/constants.py:26` `MNI_ATLAS_DIR`), else the repo-relative
  `<repo>/resources/atlas` fallback.
* `_mni_atlas_lut(atlas_path)` — `viewspec.py:97-112`. Tries `<stem>_LUT.txt`,
  `<stem>_labels.txt`, `<stem>.txt`, plus `massp2021_labels.txt` for MASSP.
* `_freesurfer_color_lut()` — `viewspec.py:115-117` → `resources/atlas/FreeSurferColorLUT.txt`.
* `_default_mni_atlas_path()` — `viewspec.py:120-127`, via `VoxelAtlasManager.detect_mni_atlases`.
* `_DEFAULT_PERCENTILE = {"lo": 95.0, "hi": 99.9}` — `viewspec.py:130`.
* `_layer(...)` — `viewspec.py:133-157`. **The exact ViewLayer shape**:
  `{path, kind, colormap, opacity, visible, cal_min, cal_max, lut}` plus optional `percentile`.
  `kind` is only ever `"volume"` or `"label"` (`viewspec.py:327`); `colormap` is one of
  `grayscale | lut | heat | jet` in practice.
* `_subject_t1_layer` — `viewspec.py:160-163`. `T1.nii.gz` (subject) or `T1_{sid}_MNI.nii.gz` (MNI).
* `_subject_atlas_layer` — `viewspec.py:166-198`. MNI branch → bundled atlas + `_mni_atlas_lut`;
  subject branch → `segmentation/labeling.nii.gz` + `VoxelAtlasManager.find_labeling_lut()`,
  else the first FreeSurfer atlas + `FreeSurferColorLUT.txt`.
* `_MODE_DIRS = ("mTI", "TI")` — `viewspec.py:201`; `_mode_niftis_dir` — `viewspec.py:204-209`.
* `_ti_max_layers` — `viewspec.py:212-234`. Globs `<sim>/<mode>/niftis/*.nii*`, keeps
  `TI_max` and drops `TDCS`, filters on the `_MNI` substring, `visible` **only** when the
  basename starts with `grey_`, `colormap="heat"`, `opacity=0.85`, default percentile window.
* `_hf_layers` — `viewspec.py:237-257`. `<sim>/high_Frequency/niftis/*_scalar_*magnE.nii.gz`,
  `colormap="heat"`, `opacity=0.7`, `visible=False`.
* `_electrode_overlay_layer` — `viewspec.py:260-277`.
  `<sim>/<mode>/montage_imgs/electrode_overlay_subject.nii.gz` + the `.lut` sidecar from
  `tit/tools/electrode_overlay.py:262-269` (`electrode_overlay_lut_path`, `<stem>.lut`).
  `colormap="lut"`, `opacity=0.85`.
* `_analysis_layer` — `viewspec.py:280-296`. `<sim>/Analyses/{Voxel|Mesh}/<name>/roi_overlay.nii.gz`
  (or the first `*.nii*`), `colormap="jet"`, `opacity=0.6`.
* `build_view(kind, ...)` — `viewspec.py:299-404`. Per-kind branches: `custom` (`:320-328`),
  `subject` (`:330-340`), `simulation` (`:342-363`), `analysis` (`:365-378`), `group` (`:380-402`).
  Returns `None` for anything unresolvable → the route turns that into a 404.
* `_percentiles_from_array` — `viewspec.py:407-418`; `_resolve_layer_percentile` — `:421-442`
  (loads the NIfTI with `nibabel`, `np.percentile` over non-zero voxels, silently gives up on
  any exception); `resolve_percentiles` — `:445-462` (4-thread pool).
* `_finish` — `viewspec.py:465-469`: `{"space", "layers"}` → resolve percentiles → attach
  `freeview_args`. **This is the single place a `scene` key would be attached.**
* `to_freeview_args` — `viewspec.py:472-495`; `freeview_command` — `:498-500`.
* **`jail_roots()` — `viewspec.py:514-521`.** Returns `[Path(pm.project_dir).resolve(),
  Path(mni_resources_dir()).resolve().parent]`. Measured live in the container:
  `['/mnt/000', '/ti-toolbox/resources']`.
* **`resolve_jailed(raw_path)` — `viewspec.py:524-539`.** `Path.resolve()` (follows symlinks),
  `is_relative_to` any jail root, `is_file()`. Pure, returns `None`; no HTTP semantics.

### 1.2 `tit/server/routes/viewers.py` — `/api/view/*`, `/api/viewers/*`

* Module docstring `viewers.py:1-41` documents the electrode-overlay `tools`-job workflow.
* `_require_x11()` — `viewers.py:56-61`. **409** when `probe_capabilities().x11_display` is false.
  Called at `viewers.py:187` (freeview) and `viewers.py:209` (gmsh) — and *not* from
  `GET /api/view/{kind}` or `POST /api/view/args`.
* `_jail_viewspec_layers(spec)` — `viewers.py:64-83`. Re-jails and **rewrites** every
  client-submitted `layer.path` to its resolved absolute form; 403 otherwise.
* `_reject_option_like_args(args)` — `viewers.py:86-101`. Refuses any argv entry starting `-`.
* `_submit_viewer_job(config)` — `viewers.py:104-121`. Lazy `tit.jobs.api.submit`,
  `kind="viewer"`, `created_by="gui"`; `NotImplementedError` → 503.
* `GET /api/view/{kind}` — `viewers.py:124-152`. Query params `subject, simulation, space,
  field, analysis, roi, path`; 404 when `build_view` returns `None`. Return type is
  `dict[str, Any]`, i.e. an **unmodelled** response (see §5.2 for why that matters).
* `POST /api/view/args` — `viewers.py:155-178`. **Present in the server but absent from
  `contracts/openapi.v1.yaml`** (`rg` finds no `view/args` in the contract) — the gate only
  requires contract ⊆ dump, so an extra dump path is legal.
* `POST /api/viewers/freeview` — `viewers.py:181-200`; `POST /api/viewers/gmsh` — `:203-222`;
  `_ensure_gmsh_opt_sidecar` — `:225-241` (writes `<mesh>.msh.opt` via
  `tit.tools.gmsh_opt.create_mesh_opt_file` when missing — note this is a **write** inside the jail).

### 1.3 `tit/server/routes/files.py` — `/api/files/*`

* `REPORT_CSP` — `files.py:36-39`: `default-src 'none'; script-src 'unsafe-inline';
  style-src 'unsafe-inline'; img-src data:; sandbox allow-scripts`.
* `_HTML_ARTIFACT_EXTS = {".html", ".htm"}` — `files.py:47`;
  `ARTIFACT_HTML_CSP = "sandbox allow-scripts"` — `files.py:48`.
* **`_ALLOWED_ARTIFACT_EXTS = {".pdf", ".png", ".csv", ".json", ".txt", ".html"}` — `files.py:50`.**
  This is exactly why the internal viewer needs a new route: `.nii.gz`, `.msh`, `.gii`, `.opt`,
  `.lut` all **403** at `files.py:100-103`.
* `_resolve_jailed(raw_path)` — `files.py:53-69`. HTTP twin of `viewspec.resolve_jailed`:
  403 outside the jail, 404 for a missing file. **The raw route must reuse this.**
* `GET /api/files/report/{report_id:path}` — `files.py:72-90`.
* `GET /api/files/artifact` — `files.py:93-108`. `FileResponse` + `x-content-type-options: nosniff`
  + a sandbox CSP for HTML.
* `GET /api/files/text` — `files.py:111-120`; `GET /api/files/csv` — `files.py:123-133`.

### 1.4 `tit/server/routes/capabilities.py`

* `DOCKER_SOCKET` / `X11_SOCKET_DIR` — `capabilities.py:16-17`.
* `probe_capabilities()` — `capabilities.py:38-55`; **`x11_display=bool(os.environ.get("DISPLAY"))
  and os.path.isdir("/tmp/.X11-unix")` — `capabilities.py:44`**; `gmsh=shutil.which("gmsh")` — `:45`;
  `freeview=` — `:46-47`.
* `GET /api/capabilities` — `capabilities.py:58-64`, `response_model=Capabilities`.
* Model: `tit/server/schemas.py:29-38` (`docker_socket, freesurfer, bpy, x11_display, gmsh,
  freeview, jupyter`).
* Consumers of `x11_display`: `tit/server/routes/viewers.py:57`,
  `desktop/src/renderer/pages/viewer/index.tsx:429,436,509`,
  `desktop/src/main/x11.ts:13` (comment only), `tests/test_catalog_v1.py:863,892,924`,
  `tests/test_server_skeleton.py:439`.

### 1.5 `tit/catalog.py` — what exists per simulation

* Lazy-import note about `tit.opt.ex.roi` — `catalog.py:38-44`.
* `_MODE_DIRS = ("mTI", "TI")` — `catalog.py:216`;
  `_TISSUE_PREFIXES = ("grey_","white_","csf_","bone_","skin_","eyes_")` — `catalog.py:217`;
  `_FIELD_RE = r"_(TI_max|TI_normal|TI_focality|magnE)(?:\.nii)"` — `catalog.py:218`.
* `_mode_niftis` — `catalog.py:234-248` → `{path, field, space, tissue}`; drops `TDCS`.
* `_hf_niftis` — `catalog.py:251-257` → `field: "magnE"`.
* `_dir_meshes(mesh_dir, kind)` — `catalog.py:260-264` → `{path, kind}` for `*.msh`.
* `simulation_detail` — `catalog.py:279-320`. Walks `TI/` and `mTI/`, collecting
  `niftis` (`<mode>/niftis`), `meshes` (`<mode>/mesh` = `kind:"field"`,
  `<mode>/mesh/surfaces` = `kind:"surface"`), then `high_Frequency/niftis` and
  `high_Frequency/mesh` (`kind:"high_frequency"`). Also `montages`, `fields`, `space`,
  `report_ids`.
* `electrode_overlays` — `catalog.py:323-345` → `[{mode, path, exists}]` for both modes.
* `_analysis_entry` — `catalog.py:800-828` → `{name, space, field, roi, csv, json, msh, nifti, pdf}`.
* `analyses` — `catalog.py:831-846` (scans `Analyses/Mesh` then `Analyses/Voxel`).
* `atlases` / `atlas_regions` — `catalog.py:438-540`.
* `group_catalog` — `catalog.py:999-1046`.
* Routes: `tit/server/routes/catalog.py:19-38` (v0 subjects/simulations) and
  `tit/server/routes/catalog_v1.py` — notably
  `/api/catalog/simulations/{name}` (`catalog_v1.py:44-49`),
  `/api/catalog/electrode-overlays` (`catalog_v1.py:52-62`),
  `/api/catalog/atlases` (`:123-133`), `/api/catalog/analyses` (`:223-228`).
  **Every one of these returns absolute container paths** — those are exactly the strings the
  raw route will be handed back.

### 1.6 `tit/server/app.py`, `settings.py`, `static.py`, `auth.py`

* **`CSP_HEADER` — `app.py:23-27`** (see §6 for the diff).
* `CSPMiddleware` — `app.py:32-62`; it only appends CSP when
  `content_type.lower().startswith(b"text/html")` and no CSP is already set (`app.py:51-58`).
  So `/api/files/raw` responses are untouched by it.
* `DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost")` — `app.py:29`; `allowed_hosts` — `:65-71`;
  `TrustedHostMiddleware` added **outermost** at `app.py:147`.
* `_custom_openapi` — `app.py:93-122`: merges `contracts/schema.json` `$defs` into
  `components.schemas` (`app.py:104-113`) and hand-writes `/ws/system` (`:114-120`).
  **This is why a hand-authored contract schema like `ViewSpec` is *missing* from the dump**
  (§5.2).
* `create_app` — `app.py:125-210`. `/auth/session` (`:149-173`) sets the
  `HttpOnly; SameSite=Strict; Path=/` cookie; `/auth/logout` (`:175-190`); route auto-discovery
  (`:192-206`) — **adding a route to an existing module needs no `app.py` edit**
  (`tit/server/routes/__init__.py:22-28`, `OPEN_MODULES = ("health",)` at `:19`);
  `static.router` is included last (`app.py:207`).
* `ServerSettings` — `tit/server/settings.py:26-69`; `resolve_project_dir` — `:72-107`
  (`--project`, `TIT_PROJECT_DIR`, `LOCAL_PROJECT_DIR`, `/mnt/<PROJECT_DIR_NAME>`);
  `resolve_token` — `:110-122`; `resolve_static_dir` — `:125-127`;
  `resolve_dev_origins` / `resolve_allow_hosts` — `:136-143`.
* `static.py:23` `RESERVED_PREFIXES = ("api","ws","auth")` — `/api/*` never falls through to the
  SPA catch-all; `resolve_static_file` jails to the bundle dir (`static.py:46-52`);
  `serve` — `static.py:55-68`.
  **Verified in-container:** `FileResponse` for a `.wasm` file emits
  `content-type: application/wasm` (Python 3.11 `mimetypes.guess_type('a.wasm')` →
  `('application/wasm', None)`), so `WebAssembly.instantiateStreaming` on the bundled
  `@tetravox/wasm` `*_bg.wasm` will **not** trip the "incorrect response MIME type" error.
  No `static.py` change needed for WASM.
* `auth.require_auth` — `tit/server/auth.py:87-108`. Bearer always OK; cookie alone OK for
  `GET/HEAD/OPTIONS` (`_SAFE_METHODS`, `auth.py:58`), otherwise needs `_cookie_csrf_ok`
  (`auth.py:61-84`). **A `GET`/`HEAD /api/files/raw` from the renderer's Worker is a safe
  method, so the `tit_session` cookie alone authenticates it — no token needs to appear in the
  URL a Worker fetches.**

### 1.7 `tit/jobs/kinds.py` — the `viewer` job kind

* `VIEWER_PROGRAMS = frozenset({"freeview", "gmsh"})` — `kinds.py:63`.
* `command_for(...)` `viewer` branch — `kinds.py:92-99`: `[program, *args]`, no interpreter.
* `tools` branch — `kinds.py:101-114`, allow-listed to `tit.tools.*` via
  `_resolve_tool_module_path` (`kinds.py:119-150`).
* **Nothing here changes for the internal viewer**: Tetravox runs *in the renderer*, so it is
  not a job at all. `VIEWER_PROGRAMS` keeps its two entries for the external launchers.

### 1.8 The client side that will consume this

* `desktop/src/renderer/pages/viewer/api.ts:37-50` — `getViewSpec`, `launchFreeview`, `launchGmsh`.
* `desktop/src/renderer/pages/viewer/index.tsx:429,436,509` — the X11 gating callouts.
* `desktop/src/main/index.ts:125` — `win.loadURL(\`${pageOrigin}/auth/session?token=…\`)`:
  **the renderer runs on the tit.server origin**, so `app.py`'s `CSP_HEADER` governs it and
  `connect-src 'self'` already covers `/api/files/raw`.
* `desktop/src/main/index.ts:334-338` — `contextIsolation: true, sandbox: true,
  nodeIntegration: false`.

---

## 2. The real data a scene must reference (`sub-ernie`, Dataset 000)

Host root `/Users/idohaber/datasets/000`, container root `/mnt/000`. Subject root:
`derivatives/SimNIBS/sub-ernie`. Sizes are bytes, from `ls -la`.

### 2.1 `m2m_ernie/`

| File | Bytes | Role in a scene |
|---|---:|---|
| `T1.nii.gz` | 13,109,495 | base volume, subject space |
| `T1_ernie_MNI.nii.gz` | 18,743,325 | base volume, MNI space |
| `T2_reg.nii.gz` | 52,466,662 | (not used by `build_view`) |
| `final_tissues.nii.gz` | 957,678 | label volume |
| `final_tissues_LUT.txt` | 598 | **LUT sidecar** for the above |
| `ernie.msh` | 184,207,351 | head mesh, 847,165 nodes (`$Nodes` header) |
| `ernie.msh.opt` | 2,534 | **`opt` sidecar** — the only source of tissue names/colours (`Physical Volume (" GM",2)` …) |
| `segmentation/labeling.nii.gz` | 940,059 | subject atlas overlay (`build_view` kind=subject) |
| `segmentation/labeling_LUT.txt` | 2,548 | its LUT |
| `segmentation/massp2021_subject.nii.gz` | 378,861 | optional atlas |
| `segmentation/{lh,rh}.ernie_{DK40,a2009s,HCP_MMP1}.annot` | ~1.97 M each | FreeSurfer annots |
| `surfaces/{lh,rh}.central.gii` | 8,052,485 / 8,032,541 | cortical surfaces |
| `surfaces/{lh,rh}.{pial,white}.gii` | ~8.0 M each | |
| `surfaces/{lh,rh}.sphere.reg.gii` | 11,799,156 / 11,799,157 | fsaverage mapping (Tetravox `FsaverageSpec`, `docs/ARCHITECTURE.md:793-799`) |
| `ernie_seeg.msh` | 492,090,201 | **largest file in the tree** — the sEEG head model |

### 2.2 `Simulations/Thalamus/` (mode `TI`; **no `mTI` simulation exists in this dataset**)

`find … -maxdepth 2 -name mTI` returned nothing across all of `Simulations/`.

| File | Bytes |
|---|---:|
| `TI/mesh/Thalamus_TI.msh` | 255,005,467 |
| `TI/mesh/Thalamus_TI.msh.opt` | 1,866 |
| `TI/mesh/grey_Thalamus_TI.msh` | 63,926,663 |
| `TI/mesh/white_Thalamus_TI.msh` | 24,998,961 |
| `TI/mesh/Thalamus_normal.msh` (+`.opt` 1,774) | 43,254,082 |
| `TI/mesh/surfaces/Thalamus_TI_central.msh` (+`.opt` 1,773) | 43,254,079 |
| `TI/mesh/surfaces/{lh,rh}.central` | 8,847,582 each |
| `TI/mesh/surfaces/{lh,rh}.Thalamus_TI.central.TI_max` | 983,063 each |
| `TI/niftis/Thalamus_TI_subject_TI_max.nii.gz` | 17,243,027 |
| `TI/niftis/grey_Thalamus_TI_subject_TI_max.nii.gz` | 3,058,262 |
| `TI/niftis/white_Thalamus_TI_subject_TI_max.nii.gz` | 2,612,404 |
| `TI/niftis/Thalamus_TI_MNI_MNI_TI_max.nii.gz` | 13,452,877 |
| `TI/niftis/grey_…_MNI_MNI_TI_max.nii.gz` | 4,682,355 |
| `TI/niftis/white_…_MNI_MNI_TI_max.nii.gz` | 3,748,275 |
| `TI/montage_imgs/electrode_overlay_subject.nii.gz` | 119,919 |
| `TI/montage_imgs/electrode_overlay_subject.lut` | 79 |
| `TI/montage_imgs/Thalamus_highlighted_visualization.png` | 360,850 |
| `TI/surface_overlays/ernie_TDCS_{1,2}_scalar_central.msh` (+`.opt`) | 60,949,108 each |
| `high_Frequency/mesh/ernie_TDCS_{1,2}_scalar.msh` (+`.opt` ~4.16 k) | 420,249,237 / 420,250,761 |
| `high_Frequency/mesh/ernie_TDCS_{1,2}_el_currents.geo` | ~13.94 M each |
| `high_Frequency/niftis/ernie_TDCS_{1,2}_scalar_subject_magnE.nii.gz` | 17,378,342 / 17,365,841 |
| `high_Frequency/niftis/ernie_TDCS_{1,2}_scalar_MNI_MNI_magnE.nii.gz` | 13,679,348 / 13,669,714 |
| `Analyses/Voxel/cortical_2regions_aparc_DKTatlas_aseg_9423bf31/roi_overlay.nii.gz` | 551,497 |
| `documentation/config.json` | 1,288 |

`electrode_overlay_subject.lut` content (verbatim) — it is a FreeSurfer-shaped LUT with a
comment header, which `tvx_core::lut` accepts (`crates/tvx-core/src/lut.rs:6,33,71-75`,
"blank lines and `#` comments are skipped"):

```
# TI-Toolbox electrode channel LUT
1 Channel_1 0 0 255 0
2 Channel_2 255 0 0 0
```

`documentation/config.json` carries the montage that named the simulation
(`electrode_pairs: [["F7","P7"],["F8","P8"]]`, `eeg_net: "EEG10-10_Cutini_2011.csv"`,
`simulation_mode: "TI"`, `electrode_coordinates` — four RAS triples).
`Analyses/…/analysis.json` carries `{"analysis_type":"cortical","field_name":"TI_max",
"regions":["Left-Thalamus","Right-Thalamus"],"center":null,"radius":null}` — **`center` is
non-null only for `analysis_type: "spherical"`** (`tit/analyzer/config.py:118-124,172-174,191-193`),
which is the one place the server can source an initial cursor from.

### 2.3 What `build_view` actually returns today (live, in the container)

```
$ docker exec tit-v3-spike simnibs_python /tmp/viewdump.py     # build_view("simulation", subject="ernie", simulation="Thalamus", space="subject")
elapsed 0.74
```

5 layers: `m2m_ernie/T1.nii.gz` (grayscale, 1.0, visible);
`…/TI/montage_imgs/electrode_overlay_subject.nii.gz` (lut, 0.85, visible,
`lut=…/electrode_overlay_subject.lut`);
`Thalamus_TI_subject_TI_max.nii.gz` (heat, 0.85, **hidden**, `cal_min 0.30659201741218567`,
`cal_max 1.4342600691318563`); `grey_Thalamus_TI_subject_TI_max.nii.gz` (heat, 0.85, **visible**,
`0.12392265200614928`/`0.19030331176519424`); `white_…` (heat, 0.85, hidden,
`0.15548373907804483`/`0.24795528431237124`). All three heat layers carry
`percentile: {"lo":95.0,"hi":99.9}`. `jail_roots()` = `['/mnt/000', '/ti-toolbox/resources']`.

`build_view("subject", subject="ernie")` returns 2 layers: `T1.nii.gz` +
`segmentation/labeling.nii.gz` (lut, 0.7, `lut=…/labeling_LUT.txt`).

`catalog.simulation_detail(pm,"ernie","Thalamus")` reports `fields: ["TI_max","magnE"]`,
`space: ["mni","subject"]`, and 7 meshes (4 `field`, 1 `surface`, 2 `high_frequency`).

---

## 3. (1) `GET`/`HEAD /api/files/raw?path=…` — full spec

### 3.1 Why a new route rather than widening `/api/files/artifact`

`_ALLOWED_ARTIFACT_EXTS` (`files.py:50`) is a deliberate *document*-safety list: the artifact
route is what the renderer points an `<img>`/`<iframe>`/PDF viewer at, and `files.py:106-107`
attaches a sandbox CSP for HTML. Adding `.nii.gz`/`.msh` there would blur two different
threat models (renderable document vs. opaque byte stream) and would silently give every
existing artifact consumer new file types. A separate route also lets the *response policy*
differ: `Content-Disposition`, no HTML ever, and Range/HEAD semantics the artifact route
does not need.

### 3.2 Interface

```
GET  /api/files/raw?path=<absolute container path>
HEAD /api/files/raw?path=<absolute container path>
```

* **Auth**: behind `require_auth` automatically (the module's `router` is mounted with
  `dependencies=protected`, `app.py:200-202`; `files` is not in `OPEN_MODULES`,
  `routes/__init__.py:19`). `GET`/`HEAD` are `_SAFE_METHODS` (`auth.py:58`) so a same-origin
  Worker `fetch()` authenticates on the `tit_session` cookie alone.
* **Jail**: `files._resolve_jailed(path)` — the *same* `viewspec.jail_roots()` boundary
  (`files.py:53-69`, `viewspec.py:514-539`). 403 outside, 404 missing/not-a-file.
* **Extension policy — an explicit *deny* list, not an allow list.** Refuse only what a
  browser could execute as a document in the app origin:
  `{".html", ".htm", ".xhtml", ".svg", ".xml", ".xsl", ".mhtml"}` → 403 with
  `detail="File type not servable as raw data; use /api/files/artifact"`.
  Everything else is served as opaque bytes. This satisfies "must NOT be limited to the
  artifact extension allow-list" while keeping the origin safe.
* **Media types** (explicit table; never `mimetypes.guess_type` alone — see the gotcha below):

  | Suffix (checked longest-first) | `Content-Type` |
  |---|---|
  | `.nii.gz` | `application/gzip` |
  | `.nii` | `application/octet-stream` |
  | `.mgz`, `.mgh` | `application/octet-stream` |
  | `.msh` | `application/octet-stream` |
  | `.gii` | `application/octet-stream` (GIfTI is XML but must **never** be `text/xml`; see §9.2) |
  | `.geo` | `application/octet-stream` |
  | `.annot`, `.curv`, `.central`, `.pial`, `.white`, `.sphere`, and other extension-less FreeSurfer surfaces | `application/octet-stream` |
  | `.opt`, `.lut`, `.txt`, `.csv`, `.tsv`, `.json` | `text/plain; charset=utf-8` (`.json` → `application/json`) |
  | anything else | `application/octet-stream` |

  **Gotcha, measured in the container:** `mimetypes.guess_type("a.nii.gz")` →
  `(None, 'gzip')`, `("a.msh")` → `('model/mesh', None)`, `("a.mgz")` →
  `('application/vnd.proteus.magazine', None)`, `("a.geo")` → `('application/vnd.dynageo', None)`.
  Guessing would hand a browser three wrong types. Also note `Path("T1.nii.gz").suffix ==
  ".gz"`, so the lookup must match the **compound** suffix.
* **Always-present headers**: `X-Content-Type-Options: nosniff`;
  `Content-Disposition: attachment; filename="<basename>"` (harmless to `fetch()`, kills
  accidental in-origin rendering); `Cache-Control: private, max-age=0, must-revalidate`.
* **Range**: `Accept-Ranges: bytes`, `206` + `Content-Range` for a satisfiable single range,
  `multipart/byteranges` for multi-range, `416` + `Content-Range: bytes */<size>` for an
  unsatisfiable one, and `If-Range` honoured.
* **Caching**: `ETag` = the file's `md5("<st_mtime>-<st_size>")`, `Last-Modified` from
  `st_mtime` — both already produced by Starlette. **Add** `If-None-Match` /
  `If-Modified-Since` → `304 Not Modified` (see §3.4: Starlette does *not* do this).
* **HEAD**: same headers, empty body.

### 3.3 Implementation: Starlette 1.6's `FileResponse` already does most of it — measured

`inspect.getsource(starlette.responses.FileResponse)` in the container, 278 lines, shows:
`self.headers.setdefault("accept-ranges", "bytes")` (line 24 of the class),
`set_stat_headers` computing `etag_base = str(stat_result.st_mtime) + "-" + str(stat_result.st_size)`
then an md5 hex ETag (lines 36-44), `http_if_range = headers.get("if-range")` (line 68),
`status: 206` for a single range (line 112), `multipart/byteranges; boundary=…` (line 138),
and `_parse_range_header` (line 165).

Empirical proof (FastAPI + `FileResponse`, in-container):

```
GET   200 accept-ranges=bytes content-length=25600 etag="efcb3cd3…" last-modified=Wed, 02 Sep 2026 …
RANGE 206 content-range=bytes 0-99/25600 content-length=100 body=100
MULTI 206 content-type=multipart/byteranges; boundary=1947919ff6…
UNSAT 416 content-range=bytes */25600
HEAD  405        <-- @router.get() alone does NOT accept HEAD
```

**Two things Starlette does *not* give you:**

1. **HEAD is 405.** FastAPI's `APIRoute` does **not** add `HEAD` to a `GET` route (unlike
   plain `starlette.routing.Route`, which does — `Route.__init__` has
   `if "GET" in self.methods: self.methods.add("HEAD")`). Fix: stack decorators.
   Verified working:

   ```
   HEAD 200 content-length=25600 accept-ranges=bytes body=0
   openapi methods: ['get']       # with include_in_schema=False on the head registration
   ```

   (`@router.api_route(..., methods=["GET","HEAD"])` also works but emits a
   `UserWarning: Duplicate Operation ID … _head`, so prefer stacked decorators.)

2. **No conditional-request 304.** Measured:

   ```
   etag "0b11794a4abba84b1b446f2ad15741c5"
   If-None-Match       -> 200      <-- NOT 304
   If-Modified-Since   -> 200      <-- NOT 304
   If-Range match+Range-> 206
   If-Range stale+Range-> 200
   ```

   Only `StaticFiles` implements `is_not_modified`. So the raw route must do the check itself.

**Recommended code** (goes into `tit/server/routes/files.py`, after `csv_file`; no `app.py`
change is needed because `routes/__init__.py:22-28` auto-discovers the module and the router
is already mounted):

```python
_RAW_DENY_EXTS = {".html", ".htm", ".xhtml", ".svg", ".xml", ".xsl", ".mhtml"}
_RAW_MEDIA_TYPES = {                       # longest compound suffix wins
    ".nii.gz": "application/gzip",
    ".json": "application/json",
    ".opt": "text/plain; charset=utf-8", ".lut": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",  ".csv": "text/csv; charset=utf-8",
}
_RAW_DEFAULT_MEDIA_TYPE = "application/octet-stream"

def _raw_media_type(name: str) -> str:
    lowered = name.lower()
    for suffix, media_type in _RAW_MEDIA_TYPES.items():
        if lowered.endswith(suffix):
            return media_type
    return _RAW_DEFAULT_MEDIA_TYPE

def _etag(st: os.stat_result) -> str:
    # byte-identical to Starlette's own FileResponse.set_stat_headers
    base = f"{st.st_mtime}-{st.st_size}"
    return f'"{hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()}"'

@router.get(
    "/api/files/raw",
    summary="Raw bytes of one volume/mesh/LUT file for the in-app viewer, jailed to the project",
)
@router.head("/api/files/raw", include_in_schema=False)
def raw(request: Request, path: str = Query(...)) -> Response:
    resolved = _resolve_jailed(path)                       # 403 / 404, files.py:53
    lowered = resolved.name.lower()
    if any(lowered.endswith(ext) for ext in _RAW_DENY_EXTS):
        raise HTTPException(
            status_code=403,
            detail="File type not servable as raw data; use /api/files/artifact",
        )
    st = resolved.stat()
    etag = _etag(st)
    headers = {
        "x-content-type-options": "nosniff",
        "content-disposition": f'attachment; filename="{resolved.name}"',
        "cache-control": "private, max-age=0, must-revalidate",
        "accept-ranges": "bytes",
        "etag": etag,
    }
    if _not_modified(request.headers, etag, st.st_mtime):   # Starlette does NOT do this
        return Response(status_code=304, headers=headers)
    return FileResponse(resolved, media_type=_raw_media_type(resolved.name), headers=headers)
```

`_not_modified` is ~8 lines: `if-none-match` split on `,` and compared (also honouring `*`),
else `if-modified-since` parsed with `email.utils.parsedate_to_datetime` and compared to
`st.st_mtime` truncated to whole seconds.

### 3.4 Prototype run against real `sub-ernie` data (in-container, verbatim)

```
T1.nii.gz                    HEAD=200 len=  13109495 ct=application/gzip          ar=bytes etag="c6e5d6930ead4ce6bb282f95129c2b07" | RANGE=206 cr=bytes 0-1023/13109495 n=1024 21ms
final_tissues.nii.gz         HEAD=200 len=    957678 ct=application/gzip          ar=bytes etag="187778e7dbb7160079339e49f3fe9b47" | RANGE=206 cr=bytes 0-1023/957678   n=1024  5ms
final_tissues_LUT.txt        HEAD=200 len=       598 ct=text/plain; charset=utf-8 ar=bytes etag="4be717ee23755b5bba3f7392b71a6164" | RANGE=206 cr=bytes 0-597/598      n=598   4ms
ernie.msh.opt                HEAD=200 len=      2534 ct=text/plain; charset=utf-8 ar=bytes etag="136e9ee8ee507a4497a85bde44474eec" | RANGE=206 cr=bytes 0-1023/2534    n=1024  4ms
grey_Thalamus_TI.msh         HEAD=200 len=  63926663 ct=application/octet-stream  ar=bytes etag="02284b22f00e57ce1e7ff71957d5edf8" | RANGE=206 cr=bytes 0-1023/63926663 n=1024  4ms
electrode_overlay_subject.lut HEAD=200 len=       79 ct=text/plain; charset=utf-8 ar=bytes etag="dfcc7943ed60596f5a05044c54dc51b6" | RANGE=206 cr=bytes 0-78/79        n=79    3ms
lh.central.gii               HEAD=200 len=   8052485 ct=application/octet-stream  ar=bytes etag="ac3897bb7a600a793cbc524a3a619711" | RANGE=206 cr=bytes 0-1023/8052485 n=1024  3ms
FULL 255MB 200 255005467 0.49 s        # Thalamus_TI.msh streamed end to end
traversal  403     # /etc/passwd
dotdot     403     # <sub-ernie>/../../../../etc/passwd
resources  200     # /ti-toolbox/resources/atlas/MNI152_T1_1mm.nii.gz  (second jail root)
missing    404
```

Source of the prototype (read-only, written to the scratchpad, `docker cp`'d to `/tmp` in the
container, never into the repo):
`/private/tmp/claude-501/-Users-idohaber-01-production-TI-toolbox/2f1d440f-51f9-4340-bb8a-c347107a12b1/scratchpad/rawproto.py`.

---

## 4. (2) The scene document

### 4.1 Design decision: additive `scene` on `GET /api/view/{kind}`, **not** a `*.tetravox.json`

Three candidate wire shapes were considered against `docs/ARCHITECTURE.md`:

* **Tetravox's persisted `ViewSpec` (`*.tetravox.json`, §4.6, `docs/ARCHITECTURE.md:663-694`)** —
  **rejected.** `DatasetRef` requires a `fingerprint` (`ARCHITECTURE.md:674`) whose producer is
  `tvx_core::fingerprint` over **the bytes the loader was handed**, i.e. *after* `.gz` inflation
  (`ARCHITECTURE.md:755-757`). The server would have to gunzip every `.nii.gz` per request.
  `DatasetRef.path` is also "relative to the scene file" (`:672`), a concept with no HTTP
  analogue, and `SidecarRef.path` is relative to the *dataset* (`:667`). Loading via
  `Engine.load(viewspec)` additionally assumes filesystem paths the renderer can open, which
  it cannot (the data lives in a container).
* **A Tetravox *job* document (`docs/AUTOMATION.md`, `python/tetravox/job.py:24-49`)** —
  **rejected for the in-app viewer.** It is the headless screenshot/CLI surface
  (`PRESETS = ("plain","ti-field-on-t1","mesh-tissues-translucent","atlas-outline")`,
  `job.py:26-31`); useful later for a "render a figure" job kind, not for a live canvas.
* **A small TI-Toolbox-owned `TitScene`, replayed through the frozen `Engine` facade** —
  **chosen.** Its dataset sources map 1:1 onto `DatasetSource`/`LoadSource`
  (`ARCHITECTURE.md:774-778`, `:1942-1946`): `{ kind: 'url', url, sidecars?: {lut?, opt?} }`,
  which is exactly what a `/api/files/raw` URL is. Its layer fields are Tetravox's own
  (`VolumeLayer` `ARCHITECTURE.md:352-368`, `MeshLayer` `:413-432`, `Scale`/`Threshold` `:202-212`),
  so the renderer's translation is `engine.addDataset(...)` + `engine.addLayer({...})` with no
  vocabulary of its own.

**Where it is attached:** `viewspec._finish` (`viewspec.py:465-469`) already builds
`{"space","layers"}`, resolves percentiles and attaches `freeview_args`. Add one line:

```python
def _finish(space, layers):
    spec = {"space": space, "layers": layers}
    resolve_percentiles(spec)
    spec["freeview_args"] = to_freeview_args(spec)
    spec["scene"] = to_tetravox_scene(spec)      # NEW, pure, no file IO
    return spec
```

`to_tetravox_scene(spec)` is a **pure** function over the already-resolved ViewSpec — no extra
`nibabel` load, no new discovery, no new jail check. That keeps the "layer rules live in one
place" invariant the module docstring asserts (`viewspec.py:1-9`).

**Optional alias.** If a separate URL is wanted (e.g. for `POST`-ing an edited ViewSpec back and
getting a scene, mirroring `POST /api/view/args`), add
`GET /api/scene/{kind}` returning only the `scene` object, and `POST /api/scene` taking
`{viewspec}` → `{scene}`. Both are 6-line wrappers around the same pure function. **I recommend
starting with the additive field only** — it costs one contract property and no new mock route
or contract-coverage entry (§7, §8), and the client already has the ViewSpec in hand.

### 4.2 The mapping, field by field

| ViewSpec (`viewspec._layer`, `viewspec.py:133-157`) | TitScene / Tetravox |
|---|---|
| `path` | `dataset.url = "/api/files/raw?path=" + quote(path)`, `dataset.path = path` (kept for the "Open in Freeview/Gmsh" buttons and for debugging) |
| `lut` (a sidecar path) | `dataset.sidecars.lut` (same URL form). Presence also sets `dataset.isLabelHint = true`. |
| *(derived)* `<mesh>.msh.opt` next to a `.msh` | `dataset.sidecars.opt`. **Required** — `ernie.msh` has no `$PhysicalNames`, so the `.opt` is the only source of tissue names/colours (`ARCHITECTURE.md:724-728`; `crates/tvx-mesh-io/src/lib.rs:26` tag ladder `$PhysicalNames → <mesh>_LUT.txt → <mesh>.msh.opt`). Verified present for every `.msh` in `Thalamus/TI/mesh/` except `grey_`/`white_`. |
| `kind: "volume" \| "label"` | `layer.kind: "volume"` (Tetravox derives `isLabel` from the file + LUT); `"label"` was only ever set for `.msh` in `custom` kind (`viewspec.py:327`) → map to `layer.kind: "mesh"`. |
| `colormap: "grayscale"` | `colormap: "gray"`, `scale: {kind:"linear", lo:null, hi:null}` (null = the volume's own min/max) |
| `colormap: "heat"` | `colormap: "freesurfer-heat"` (`ColormapName`, `ARCHITECTURE.md:186-189`) |
| `colormap: "jet"` | `colormap: "jet"` |
| `colormap: "lut"` | no colormap; `labelMode: "fill"`, `interpolation: "nearest"` (forced anyway when `dataset.isLabel`, `ARCHITECTURE.md:358`) |
| `opacity` | `opacity` (identical 0..1) |
| `visible` | `visible` |
| `cal_min`/`cal_max` (absolute, already percentile-resolved) | `scale: {kind:"linear", lo:cal_min, hi:cal_max}` **and** `threshold: {lo:cal_min, hi:cal_max, symmetric:false, mode:"hide", softEdge:0}` — the `heat`-colormap semantics Freeview gives `heatscale` (values below `lo` are transparent) is `threshold.mode:"hide"` in Tetravox, not a bare `scale` |
| `percentile: {lo, hi}` | `percentileWindow: {lo, hi}` — carried through so the client can *re-derive* the window from the engine's own `Stats.percentiles` after load. **`95` and `99.9` are both members of Tetravox's `PercentileKey` union** (`ARCHITECTURE.md:214`), so `stats.percentiles['95']` / `['99.9']` reproduce the toolbox default exactly, with no extra server read. |
| `spec.space` | `scene.space` (`"subject"`/`"mni"`); informational, used to label the coordinate read-out |
| *(new)* `analysis.json.center` when `analysis_type == "spherical"` | `scene.cursor: [x,y,z]` (world RAS mm); `null` otherwise |
| *(new)* number of volume layers | `scene.layout: {kind: "2x2"}` (Tetravox `LayoutKind`, `ARCHITECTURE.md:578-581`); `"1+3"` when a mesh layer is present |

`activeLayerId` = the id of the last **visible heat** layer (the field the user came to look at),
falling back to the top-most visible layer.

Layer ids are deterministic and stable across requests: `l{index}_{slug(basename-without-ext)}`.
Dataset ids: `d{index}_{slug(basename-without-ext)}`. Determinism matters because the client
diffs scenes when the user changes `space`/`field` and should not reload unchanged datasets.

### 4.3 Exact JSON — `GET /api/view/simulation?subject=ernie&simulation=Thalamus&space=subject`

The `scene` block below is the mechanical transform of the **live** ViewSpec quoted in §2.3
(same five layers, same resolved thresholds). `…` in a URL is only line-wrapping.

```json
{
  "space": "subject",
  "layers": [ "… unchanged, exactly as today (§2.3) …" ],
  "freeview_args": [ "… unchanged …" ],
  "scene": {
    "version": 1,
    "space": "subject",
    "subject": "ernie",
    "simulation": "Thalamus",
    "cursor": null,
    "layout": { "kind": "2x2" },
    "background": [0, 0, 0, 1],
    "radiological": false,
    "annotations": {
      "orientationLabels": true, "cornerInfo": true, "conventionBadge": true,
      "scaleBar": true, "colorbars": true, "crosshair": true, "orientationCube": true
    },
    "activeLayerId": "l3_grey_thalamus_ti_subject_ti_max",
    "datasets": [
      {
        "id": "d0_t1",
        "kind": "volume",
        "name": "T1",
        "url": "/api/files/raw?path=%2Fmnt%2F000%2Fderivatives%2FSimNIBS%2Fsub-ernie%2Fm2m_ernie%2FT1.nii.gz",
        "path": "/mnt/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz",
        "bytes": 13109495,
        "gzipped": true
      },
      {
        "id": "d1_electrode_overlay_subject",
        "kind": "volume",
        "name": "Electrode overlay",
        "url": "/api/files/raw?path=%2Fmnt%2F000%2F…%2FTI%2Fmontage_imgs%2Felectrode_overlay_subject.nii.gz",
        "path": "/mnt/000/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/TI/montage_imgs/electrode_overlay_subject.nii.gz",
        "bytes": 119919,
        "gzipped": true,
        "isLabelHint": true,
        "sidecars": {
          "lut": {
            "url": "/api/files/raw?path=%2Fmnt%2F000%2F…%2FTI%2Fmontage_imgs%2Felectrode_overlay_subject.lut",
            "path": "/mnt/000/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/TI/montage_imgs/electrode_overlay_subject.lut",
            "bytes": 79
          }
        }
      },
      {
        "id": "d2_thalamus_ti_subject_ti_max",
        "kind": "volume",
        "name": "TI_max (all tissues)",
        "url": "/api/files/raw?path=%2Fmnt%2F000%2F…%2FTI%2Fniftis%2FThalamus_TI_subject_TI_max.nii.gz",
        "path": "/mnt/000/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/TI/niftis/Thalamus_TI_subject_TI_max.nii.gz",
        "bytes": 17243027,
        "gzipped": true
      },
      {
        "id": "d3_grey_thalamus_ti_subject_ti_max",
        "kind": "volume",
        "name": "TI_max (grey)",
        "url": "/api/files/raw?path=%2Fmnt%2F000%2F…%2FTI%2Fniftis%2Fgrey_Thalamus_TI_subject_TI_max.nii.gz",
        "path": "/mnt/000/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/TI/niftis/grey_Thalamus_TI_subject_TI_max.nii.gz",
        "bytes": 3058262,
        "gzipped": true
      },
      {
        "id": "d4_white_thalamus_ti_subject_ti_max",
        "kind": "volume",
        "name": "TI_max (white)",
        "url": "/api/files/raw?path=%2Fmnt%2F000%2F…%2FTI%2Fniftis%2Fwhite_Thalamus_TI_subject_TI_max.nii.gz",
        "path": "/mnt/000/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/TI/niftis/white_Thalamus_TI_subject_TI_max.nii.gz",
        "bytes": 2612404,
        "gzipped": true
      }
    ],
    "layers": [
      {
        "id": "l0_t1", "datasetId": "d0_t1", "kind": "volume", "name": "T1",
        "visible": true, "opacity": 1.0, "pickable": true, "showColorbar": false,
        "volumeIndex": 0, "colormap": "gray",
        "scale": { "kind": "linear", "lo": null, "hi": null },
        "threshold": { "lo": null, "hi": null, "symmetric": false, "mode": "clamp", "softEdge": 0 },
        "interpolation": "linear", "labelMode": "fill", "outlineWidthPx": 1,
        "showIn3D": false, "precision": "auto"
      },
      {
        "id": "l1_electrode_overlay_subject", "datasetId": "d1_electrode_overlay_subject",
        "kind": "volume", "name": "Electrode overlay",
        "visible": true, "opacity": 0.85, "pickable": true, "showColorbar": false,
        "volumeIndex": 0, "colormap": "gray",
        "scale": { "kind": "linear", "lo": null, "hi": null },
        "threshold": { "lo": null, "hi": null, "symmetric": false, "mode": "clamp", "softEdge": 0 },
        "interpolation": "nearest", "labelMode": "fill", "outlineWidthPx": 1,
        "showIn3D": false, "precision": "auto"
      },
      {
        "id": "l2_thalamus_ti_subject_ti_max", "datasetId": "d2_thalamus_ti_subject_ti_max",
        "kind": "volume", "name": "TI_max (all tissues)",
        "visible": false, "opacity": 0.85, "pickable": true, "showColorbar": true,
        "volumeIndex": 0, "colormap": "freesurfer-heat",
        "scale": { "kind": "linear", "lo": 0.30659201741218567, "hi": 1.4342600691318563 },
        "threshold": { "lo": 0.30659201741218567, "hi": 1.4342600691318563,
                       "symmetric": false, "mode": "hide", "softEdge": 0 },
        "percentileWindow": { "lo": 95.0, "hi": 99.9 },
        "interpolation": "linear", "labelMode": "fill", "outlineWidthPx": 1,
        "showIn3D": false, "precision": "auto"
      },
      {
        "id": "l3_grey_thalamus_ti_subject_ti_max", "datasetId": "d3_grey_thalamus_ti_subject_ti_max",
        "kind": "volume", "name": "TI_max (grey)",
        "visible": true, "opacity": 0.85, "pickable": true, "showColorbar": true,
        "volumeIndex": 0, "colormap": "freesurfer-heat",
        "scale": { "kind": "linear", "lo": 0.12392265200614928, "hi": 0.19030331176519424 },
        "threshold": { "lo": 0.12392265200614928, "hi": 0.19030331176519424,
                       "symmetric": false, "mode": "hide", "softEdge": 0 },
        "percentileWindow": { "lo": 95.0, "hi": 99.9 },
        "interpolation": "linear", "labelMode": "fill", "outlineWidthPx": 1,
        "showIn3D": false, "precision": "auto"
      },
      {
        "id": "l4_white_thalamus_ti_subject_ti_max", "datasetId": "d4_white_thalamus_ti_subject_ti_max",
        "kind": "volume", "name": "TI_max (white)",
        "visible": false, "opacity": 0.85, "pickable": true, "showColorbar": true,
        "volumeIndex": 0, "colormap": "freesurfer-heat",
        "scale": { "kind": "linear", "lo": 0.15548373907804483, "hi": 0.24795528431237124 },
        "threshold": { "lo": 0.15548373907804483, "hi": 0.24795528431237124,
                       "symmetric": false, "mode": "hide", "softEdge": 0 },
        "percentileWindow": { "lo": 95.0, "hi": 99.9 },
        "interpolation": "linear", "labelMode": "fill", "outlineWidthPx": 1,
        "showIn3D": false, "precision": "auto"
      }
    ]
  }
}
```

### 4.4 Exact JSON — a **mesh** view

There is no mesh path in `build_view` today: `_ti_max_layers` globs only `*.nii*`
(`viewspec.py:217`) and the only `.msh` a ViewSpec can carry is `kind=custom`
(`viewspec.py:327`). Meshes are currently reached only through
`POST /api/viewers/gmsh` (`viewers.py:203-222`) with a path from
`catalog.simulation_detail`'s `meshes` array (`catalog.py:296-304`).

So a mesh scene comes from `GET /api/view/custom?path=<msh>` (already jailed at
`viewspec.py:320-328`). `to_tetravox_scene` recognises a `.msh`/`.gii` dataset and emits a
`MeshLayer` (`ARCHITECTURE.md:413-432`), attaching the `.msh.opt` sidecar when it exists and
naming the field from the basename (`_FIELD_RE`, `catalog.py:218`):

```json
{
  "space": "subject",
  "layers": [
    { "path": "/mnt/000/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/TI/mesh/grey_Thalamus_TI.msh",
      "kind": "label", "colormap": "grayscale", "opacity": 1.0, "visible": true,
      "cal_min": null, "cal_max": null, "lut": null }
  ],
  "freeview_args": [ "…" ],
  "scene": {
    "version": 1,
    "space": "subject",
    "subject": "ernie",
    "simulation": "Thalamus",
    "cursor": null,
    "layout": { "kind": "1+3" },
    "background": [0, 0, 0, 1],
    "radiological": false,
    "annotations": { "orientationLabels": true, "cornerInfo": true, "conventionBadge": true,
                     "scaleBar": true, "colorbars": true, "crosshair": true, "orientationCube": true },
    "activeLayerId": "l0_grey_thalamus_ti",
    "datasets": [
      {
        "id": "d0_grey_thalamus_ti",
        "kind": "mesh",
        "name": "grey_Thalamus_TI",
        "format": "msh",
        "url": "/api/files/raw?path=%2Fmnt%2F000%2F…%2FTI%2Fmesh%2Fgrey_Thalamus_TI.msh",
        "path": "/mnt/000/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/TI/mesh/grey_Thalamus_TI.msh",
        "bytes": 63926663,
        "gzipped": false,
        "sidecars": {}
      }
    ],
    "layers": [
      {
        "id": "l0_grey_thalamus_ti", "datasetId": "d0_grey_thalamus_ti",
        "kind": "mesh", "name": "grey_Thalamus_TI",
        "visible": true, "opacity": 1.0, "pickable": true, "showColorbar": true,
        "colorMode": "field",
        "field": { "source": "elm", "name": "TI_max", "component": "mag" },
        "colormap": "freesurfer-heat",
        "scale": { "kind": "linear", "lo": null, "hi": null },
        "threshold": { "lo": null, "hi": null, "symmetric": false, "mode": "clamp", "softEdge": 0 },
        "percentileWindow": { "lo": 95.0, "hi": 99.9 },
        "solidColor": [0.8, 0.8, 0.8, 1.0],
        "tagStyle": {},
        "edges": { "surface": false, "caps": true },
        "edgeColor": [0, 0, 0, 1], "edgeWidthPx": 1,
        "flatShading": false, "faceMode": "cull",
        "clip": { "planes": [], "caps": true, "capColorMode": "tag" },
        "contoursIn2D": true, "contourWidthPx": 2, "fillIn2D": false
      }
    ]
  }
}
```

For the *whole-head* mesh (`m2m_ernie/ernie.msh`, 184 MB) the same document takes
`colorMode: "tag"`, `sidecars.opt` pointing at `ernie.msh.opt` (2,534 B) and no `field`;
that is exactly the `mesh-tissues-translucent` preset Tetravox already ships
(`python/tetravox/job.py:26-31`).

**`scale.lo/hi: null` for a mesh is deliberate:** the server never reads a 64–420 MB `.msh`,
so it has no field statistics. Tetravox computes `MeshFieldInfo.stats`
(`ARCHITECTURE.md:271-275`) at load, and `percentileWindow` tells the client which two of the
nine `PercentileKey`s to use. This is the one place where server-side and client-side windowing
must not both be authoritative — the rule is: **`scale.lo/hi` non-null ⇒ use it verbatim;
null ⇒ resolve `percentileWindow` against the engine's own `Stats`.**

---

## 5. (3) Capabilities changes

### 5.1 What changes

`tit/server/schemas.py:29-38` — add one field:

```python
class Capabilities(BaseModel):
    docker_socket: bool
    freesurfer: bool
    bpy: bool
    x11_display: bool = Field(description="DISPLAY set and X socket present")
    gmsh: bool
    freeview: bool
    jupyter: bool = Field(...)
    internal_viewer: bool = Field(                                     # NEW
        description="the in-app Tetravox viewer is usable: the server can stream raw "
                    "volume/mesh bytes (/api/files/raw). Independent of x11_display."
    )
```

`tit/server/routes/capabilities.py:38-55` — add the probe. It is a *server-side* statement of
"raw streaming is available", not a GPU probe (WebGL2 availability is a renderer fact the
renderer discovers itself via `Capabilities` from `packages/engine/src/gl/caps.ts`,
`ARCHITECTURE.md:2070`):

```python
        internal_viewer=True,   # this build serves /api/files/raw
```

A literal `True` is honest and useful: it lets an *older* server (no `/api/files/raw`) be
detected by the client, because `openapi-fetch` will surface the field as `undefined`
and the UI can fall back to Freeview. If a runtime switch is ever wanted, gate it on a
`ServerSettings` flag rather than an environment probe.

### 5.2 What must **not** change

* `_require_x11()` (`viewers.py:56-61`) **stays exactly where it is** — on
  `POST /api/viewers/freeview` (`viewers.py:187`) and `POST /api/viewers/gmsh`
  (`viewers.py:209`). Those still shell out to X11 programs through a `viewer` job
  (`tit/jobs/kinds.py:92-99`).
* `GET /api/view/{kind}` and `POST /api/view/args` never called `_require_x11` and still must not.
* `capabilities.gmsh` / `capabilities.freeview` (`capabilities.py:45-47`) keep their meaning:
  "the external program exists on `PATH`". Together with `x11_display` they gate the two
  *optional external* buttons.

### 5.3 Client-side consequence (for the renderer lane, noted here for completeness)

`desktop/src/renderer/pages/viewer/index.tsx:429,436,509` currently phrase the X11 callout as
if it disabled *viewing*. With the internal viewer, that callout becomes a small note on the
two secondary "Open in Freeview / Open in Gmsh" buttons only.
`desktop/src/renderer/pages/viewer/PARITY.md:30` ("Capability gating (X11) … Done") needs the
same rewording.

---

## 6. (4) Exact CSP diff for `app.py`

**Current** — `tit/server/app.py:23-27`:

```python
CSP_HEADER = (
    "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; frame-src 'self'; "
    "object-src 'none'"
)
```

**Proposed:**

```python
CSP_HEADER = (
    "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; script-src 'self' 'wasm-unsafe-eval'; "
    "worker-src 'self' blob:; child-src 'self' blob:; frame-src 'self'; "
    "object-src 'none'"
)
```

Diff, term by term:

| Term | Change | Why |
|---|---|---|
| `script-src 'self' 'wasm-unsafe-eval'` | **added** | There is no `script-src` today, so it falls back to `default-src 'self'`, which in Chromium **blocks `WebAssembly.compile`/`instantiate`/`instantiateStreaming`**. `@tetravox/wasm` is a Rust→WASM module loaded in a dataset worker (`ARCHITECTURE.md:993-997`), so without this the viewer cannot start. `'wasm-unsafe-eval'` — not `'unsafe-eval'` — is the minimum; Electron 44's Chromium supports it. |
| `child-src 'self' blob:` | **added (belt-and-braces)** | `worker-src` already covers workers in current Chromium; `child-src` is its documented fallback. Harmless, and protects against an Electron/Chromium version where `worker-src` is not honoured for module workers. Drop it if the team prefers the minimal string. |
| `connect-src 'self'` | **unchanged** | The renderer is served from the tit.server origin (`desktop/src/main/index.ts:125`), so `fetch('/api/files/raw?path=…')` from a Worker is same-origin. Tetravox's own `connect-src 'self' tetravox:` (`ARCHITECTURE.md:1045`) is a *standalone-app* requirement; embedded in this app there is no `tetravox://` host. |
| `worker-src 'self' blob:` | **unchanged** | already correct for `new Worker(new URL('./dataset.worker.ts', import.meta.url), {type:'module'})` and for a blob-URL worker. |
| `img-src 'self' data: blob:` | **unchanged** | covers canvas → blob screenshots. |
| `object-src 'none'`, `frame-src 'self'`, `style-src` | **unchanged** | |

**Nothing else in `app.py` needs to change.** `CSPMiddleware` only stamps `text/html` responses
(`app.py:51-58`), so `/api/files/raw` is untouched; `TrustedHostMiddleware` (`app.py:147`)
already admits `127.0.0.1`/`localhost`.

**Test to update:** `tests/test_server_skeleton.py:623-628`
(`test_csp_header_is_exactly_the_todo_string`) asserts the string character for character and
will fail; also `:603` and `:643` compare against the constant (those pass automatically).

**Verified non-issue:** the `*_bg.wasm` file served through the SPA catch-all
(`static.py:55-68`, bare `FileResponse(target)`) gets `content-type: application/wasm`
(measured in-container), so `instantiateStreaming` will not reject it.

---

## 7. (5) Contract entries and tests to add

### 7.1 How the gate works (and its current state)

`dev/contracts_check.py` is a **superset** check: every contract `path+method`
(`contracts_check.py:228-278`), its declared response codes and parameters, and every
`components.schemas` entry **by name** (`contracts_check.py:281-292`) must exist in the
server's `--dump-openapi` output. Extra paths/properties in the dump are fine
(`contracts_check.py:12-14`). Exemptions: path-param aliases `{job_id}/{report_id}→{id}`
(`:60`), `/ws/*` (`:63`), statuses 401/403/404 (`:66`), `PipelineConfig` (`:69`), and
"dump response has no declared `properties`" → *warning* not failure (`:179-191`).

`dev/build_contract.py` merges `contracts/schema.json` `$defs` into the yaml
(`build_contract.py:114-177`), replacing only entries carrying `x-tit-config`
(`:140-144`). **It does nothing to hand-authored schemas** — those pass through verbatim.

The CI sequence is spelled out in `dev/notes/v3-build-plan.md:151-168`.

**Measured current state** (fresh dump from the running container,
`simnibs_python -m tit.server --project /mnt/000 --dump-openapi /tmp/o.json`, then
`python3 dev/contracts_check.py contracts/openapi.v1.json /tmp/o.json`):

```
contracts_check: 136 warning(s) (not gate failures)
contracts_check: 51 problem(s):
  …
  - schema ViewLayer missing from dump components
  - schema ViewSpec missing from dump components
  - schema JobStatus missing from dump components
  …
```

**The v1 gate is already red on this branch** — 51 problems, almost all "schema X missing
from dump components", because routes typed `-> dict[str, Any]` (e.g. `viewers.py:137`) make
FastAPI emit no named model, and `app.py:104-113` only injects `contracts/schema.json` `$defs`.
So adding hand-authored `TitScene`/`SceneDataset`/`SceneLayer` schemas **adds to an existing
backlog rather than newly breaking a green gate** — but it does add. Two ways to keep the
count from growing:

* **(a) Model the scene with Pydantic** in `tit/server/schemas.py` and give
  `GET /api/view/{kind}` a `response_model` — then `ViewSpec`, `ViewLayer`, `TitScene`,
  `SceneDataset` and `SceneLayer` all appear in the dump and **five** of the current 51
  problems disappear. This is the right fix and I recommend it.
* **(b) Declare the scene inline** in the `/api/view/{kind}` 200 response (no named
  `components.schemas` entry) — zero new problems, but `openapi-typescript` then generates an
  anonymous inline type instead of `components["schemas"]["TitScene"]`, which the renderer
  lane will dislike.

### 7.2 `contracts/openapi.v1.yaml` edits

1. **`/api/files/raw`** — new path, next to the other `files (v1)` block at
   `contracts/openapi.v1.yaml:1279-1367`:

   ```yaml
     /api/files/raw:
       get:
         tags: [files]
         summary: Raw bytes of one volume/mesh/LUT file for the in-app viewer, jailed to the project
         description: >-
           Unlike `/api/files/artifact` this is NOT restricted to the document extension
           allow-list: it streams any non-document file inside the project/resources jail
           (`tit.viewspec.jail_roots`) as opaque bytes for the in-app Tetravox viewer —
           `.nii`, `.nii.gz`, `.msh`, `.msh.opt`, `.gii`, `.geo`, `*_LUT.txt`, `.lut`,
           `.annot`, `.mgz`. Extensions a browser could execute as a document
           (`.html`, `.htm`, `.xhtml`, `.svg`, `.xml`, `.xsl`, `.mhtml`) are refused with 403.
           Supports HTTP Range (206 / `Accept-Ranges: bytes` / 416), `If-Range`, and
           `ETag`/`Last-Modified` revalidation (304). `HEAD` returns the same headers with no body.
         security: [{ cookieAuth: [] }, { bearerAuth: [] }]
         parameters:
           - in: query
             name: path
             required: true
             schema: { type: string }
           - in: header
             name: Range
             required: false
             schema: { type: string }
         responses:
           "200":
             description: raw file bytes
             headers:
               Accept-Ranges: { schema: { type: string } }
               ETag:          { schema: { type: string } }
               Content-Length:{ schema: { type: integer } }
             content:
               "*/*":
                 schema: { type: string, format: binary }
           "206":
             description: partial content
             content:
               "*/*":
                 schema: { type: string, format: binary }
           "304": { description: not modified }
           "401": { $ref: "#/components/responses/Unauthorized" }
           "403": { description: path escapes the project jail, or a document-executable extension }
           "404": { $ref: "#/components/responses/NotFound" }
           "416": { description: requested range not satisfiable }
       head:
         tags: [files]
         summary: Size/type/ETag of one raw file without its bytes
         security: [{ cookieAuth: [] }, { bearerAuth: [] }]
         parameters:
           - in: query
             name: path
             required: true
             schema: { type: string }
         responses:
           "200": { description: headers only }
           "401": { $ref: "#/components/responses/Unauthorized" }
           "403": { description: path escapes the project jail }
           "404": { $ref: "#/components/responses/NotFound" }
   ```

   ⚠️ `contracts_check.METHODS` is `("get","post","put","patch","delete")`
   (`contracts_check.py:55`) — **`head` is not checked**, so declaring it is documentation
   only and costs nothing at the gate. But the desktop contract self-test enumerates
   `["get","post","put","delete","patch"]` too (`contract.test.ts:307`), so a declared `head`
   is likewise invisible there. Good: no mock coverage entry needed for HEAD.

2. **`ViewSpec.scene`** — extend `contracts/openapi.v1.yaml:2164-2181`:

   ```yaml
       ViewSpec:
         type: object
         required: [space, layers, freeview_args]
         properties:
           space: { type: string, enum: [subject, mni] }
           layers: { … unchanged … }
           freeview_args: { … unchanged … }
           scene:                                            # NEW, optional
             oneOf:
               - $ref: "#/components/schemas/TitScene"
               - type: "null"
             description: >-
               The same view expressed for the in-app Tetravox viewer: datasets addressed by
               `/api/files/raw` URL, layers in Tetravox's own vocabulary. Derived purely from
               `layers` — the two are always consistent, and `freeview_args` remains the
               authoritative argv for the external launcher.
   ```

   Keep `scene` **optional** so an older server still satisfies the contract.

3. **New named schemas** (`TitScene`, `SceneDataset`, `SceneSidecar`, `SceneLayer`,
   `SceneScale`, `SceneThreshold`) after `ViewSpec` at `contracts/openapi.v1.yaml:2182`.
   Their required fields must match §4.3/§4.4 exactly.

4. **`Capabilities.internal_viewer`** — `contracts/openapi.v1.yaml:1441-1451`: add to
   `required` and to `properties` as `{ type: boolean }`. This one is *load-bearing* at the
   gate: `Capabilities` **is** in the dump (verified: `'Capabilities' in dump.components.schemas
   == True`) because `capabilities.py:59` sets `response_model=Capabilities`, so the new
   required property must really exist on the Pydantic model or the gate fails with
   `schema Capabilities: required property 'internal_viewer' missing`.

5. **`contracts/SCHEMA-CHANGES.md`** — append one dated entry (the file's own rule,
   `SCHEMA-CHANGES.md:1-7`: "Append one entry per change; do not edit past entries").
   Precedent for a route added without a yaml edit: `SCHEMA-CHANGES.md:52-60`.

6. Regenerate `contracts/openapi.v1.json` (`python3 dev/build_contract.py`) and
   `desktop/src/renderer/api/schema.d.ts` (`cd desktop && npm run gen:api`) — CI fails on an
   uncommitted diff (`dev/notes/v3-build-plan.md:155-157`).

### 7.3 Python tests to add

**`tests/test_files_routes.py`** (fixtures already at `:32-56`; `TOKEN`/`BEARER` at `:28-29`):

| Test | Assertion |
|---|---|
| `test_raw_serves_a_nifti_the_artifact_route_refuses` | `GET /api/files/artifact?path=<x.nii.gz>` → 403 (`files.py:100-103`); `GET /api/files/raw?path=<same>` → 200, `content-type: application/gzip`, `content-length` == file size |
| `test_raw_sets_accept_ranges_etag_and_nosniff` | `accept-ranges == "bytes"`, `etag` present and quoted, `x-content-type-options == "nosniff"`, `content-disposition` starts `attachment` |
| `test_raw_range_returns_206_with_content_range` | `Range: bytes=0-9` → 206, `content-range == "bytes 0-9/<size>"`, `len(body) == 10` |
| `test_raw_unsatisfiable_range_is_416` | `Range: bytes=<size+10>-` → 416, `content-range == "bytes */<size>"` |
| `test_raw_head_has_length_and_no_body` | `client.head(...)` → 200, `content-length` == size, `body == b""` — **this is the test that catches the FastAPI 405** |
| `test_raw_if_none_match_is_304` | second GET with `If-None-Match: <etag>` → 304, empty body |
| `test_raw_html_is_403` | the fixture's `misc/report.html` (`test_files_routes.py:45-47`) → 403 |
| `test_raw_traversal_outside_jail_is_403` | mirror `test_text_traversal_outside_jail_is_403` (`:89-107`), both traversal parametrisations |
| `test_raw_outside_project_and_resources_is_403` | mirror `:127-134` |
| `test_raw_missing_file_404` | mirror `:137-145` |
| `test_raw_unauthorized_without_token` | mirror `:72-75` (401) |
| `test_raw_resources_root_is_servable` | a file under `tit.viewspec.mni_resources_dir()` → 200 (proves the second jail root, `viewspec.py:520`) |

**`tests/test_viewspec.py`** (fixture `pm` at `:29-83` already writes real filenames):

| Test | Assertion |
|---|---|
| `test_scene_dataset_urls_are_raw_route_urls` | every `scene.datasets[].url` starts `"/api/files/raw?path="` and its decoded `path` equals the corresponding `layers[].path` |
| `test_scene_maps_colormaps` | `grayscale→gray`, `heat→freesurfer-heat`, `jet→jet`; a `lut` layer gets `labelMode:"fill"` + `interpolation:"nearest"` and no colormap |
| `test_scene_carries_absolute_and_percentile_windows` | a heat layer's `scale.lo/hi == cal_min/cal_max` **and** `percentileWindow == {"lo":95.0,"hi":99.9}` |
| `test_scene_lut_becomes_a_sidecar_not_a_dataset` | the `labeling_LUT.txt` from `_subject_atlas_layer` (`viewspec.py:186`) appears only under `datasets[].sidecars.lut`, never as its own dataset/layer |
| `test_scene_msh_gets_the_opt_sidecar` | write `x.msh` + `x.msh.opt` in the fixture; `kind=custom` scene has `sidecars.opt` and a `kind:"mesh"` layer with `colorMode:"field"` |
| `test_scene_layer_ids_are_stable` | two `build_view` calls give identical `activeLayerId`, `datasets[].id`, `layers[].id` |
| `test_scene_visibility_matches_viewspec` | `grey_` layer visible, the plain and `white_` ones hidden — pins the rule at `viewspec.py:229` |
| `test_to_tetravox_scene_is_pure` | monkeypatch `nibabel` to explode; `to_tetravox_scene` on an already-resolved spec still succeeds (proves no file IO) |

**`tests/test_server_skeleton.py`**:

* update `test_csp_header_is_exactly_the_todo_string` (`:623-628`) to the new literal;
* update `test_capabilities_shape` (`:431-445`) — the `keys` set gains `"internal_viewer"`.

**`tests/test_catalog_v1.py`**: the three `Capabilities(...)` constructions at `:859-867`,
`:888-896`, `:917-929` gain `internal_viewer=True` (keyword-only dataclass-ish model — a
missing required field is a `ValidationError`). Add one new test:
`test_view_spec_does_not_require_x11` — with `x11_display=False`, `GET /api/view/subject`
still 200s **and** carries a non-null `scene` (today `test_viewer_launch_without_x11_is_409`
at `:856-876` only proves the 409).

### 7.4 Where the tests run

Host `pytest` (the whole suite is ~2463 passed / 25 skipped in ~25 s) — the file-routes and
viewspec tests need no container. `tests/test_files_routes.py:19-21`
(`pytest.importorskip("fastapi")`, `"httpx"`) is the existing guard.

---

## 8. (6) Mock-server changes for e2e

### 8.1 The constraint that drives everything

`desktop/tests/mock-server/contract.test.ts:304-314` asserts
`expect([...exercised].sort()).toEqual([...declared].sort())` — the set of exercised
`METHOD path` pairs must **exactly equal** the set declared in `contracts/openapi.v1.yaml`
(minus the two `/ws/*` entries, deleted at `:312-313`). So every new contract path with a
`get`/`post`/`put`/`delete`/`patch` operation must be both implemented in `server.mjs` and
called in `contract.test.ts`. `head` is not enumerated (`:307`), so the HEAD half is free.

### 8.2 A raw route streaming *real* files from a directory env var

`server.mjs` today resolves paths through a fixture registry, not the filesystem:
`resolveJailed` (`server.mjs:303-314`) maps a virtual `/mnt/example/...` path to a fixture file
via `artifactRegistry` (`:260-264`) or `EXT_FALLBACK` (`:252-259`), and `res_stream`
(`:1308-1312`) writes `content-type` + `content-length` with no Range support.

Add, next to `res_stream`:

```js
// Real-bytes mode for the internal viewer: TIT_MOCK_DATA_DIR points at a directory of real
// volumes/meshes (e.g. a copy of sub-ernie). A requested project path is mapped by BASENAME
// into that directory, so the fixtures keep their /mnt/example paths and the e2e run gets
// real NIfTI/msh bytes to feed the in-app viewer. Unset => the extension fallback below.
const DATA_DIR = process.env.TIT_MOCK_DATA_DIR ?? "";
const RAW_MIME = {
  ".nii.gz": "application/gzip", ".nii": "application/octet-stream",
  ".msh": "application/octet-stream", ".gii": "application/octet-stream",
  ".opt": "text/plain; charset=utf-8", ".lut": "text/plain; charset=utf-8",
  ".txt": "text/plain; charset=utf-8", ".geo": "application/octet-stream",
};
const RAW_DENY = [".html", ".htm", ".xhtml", ".svg", ".xml", ".xsl", ".mhtml"];
function rawMime(name) {
  const l = name.toLowerCase();
  for (const [suffix, mime] of Object.entries(RAW_MIME)) if (l.endsWith(suffix)) return mime;
  return "application/octet-stream";
}
function rawLocalFile(virtualPath) {
  if (!DATA_DIR) return null;
  const candidate = join(DATA_DIR, basename(virtualPath));   // basename only: never a traversal
  return existsSync(candidate) && statSync(candidate).isFile() ? candidate : null;
}
function serveRange(req, res, file, mime, headOnly) {
  const st = statSync(file);
  const etag = `"${st.mtimeMs}-${st.size}"`;
  const base = {
    "content-type": mime, "accept-ranges": "bytes", etag,
    "last-modified": new Date(st.mtimeMs).toUTCString(),
    "x-content-type-options": "nosniff",
    "content-disposition": `attachment; filename="${basename(file)}"`,
    "cache-control": "private, max-age=0, must-revalidate",
  };
  if ((req.headers["if-none-match"] ?? "") === etag) { res.writeHead(304, base); return res.end(); }
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
  if (range) {
    let start = range[1] === "" ? st.size - Number(range[2]) : Number(range[1]);
    let end = range[1] === "" || range[2] === "" ? st.size - 1 : Number(range[2]);
    if (!(start >= 0 && start < st.size)) {
      res.writeHead(416, { ...base, "content-range": `bytes */${st.size}` });
      return res.end();
    }
    end = Math.min(end, st.size - 1);
    res.writeHead(206, { ...base, "content-range": `bytes ${start}-${end}/${st.size}`,
                                  "content-length": end - start + 1 });
    return headOnly ? res.end() : createReadStream(file, { start, end }).pipe(res);
  }
  res.writeHead(200, { ...base, "content-length": st.size });
  return headOnly ? res.end() : createReadStream(file).pipe(res);
}
function rawHandler(headOnly) {
  return (ctx) => {
    const requested = ctx.url.searchParams.get("path");
    const resolved = resolveJailed(requested);                    // server.mjs:303, unchanged jail
    if (resolved.jailed) return json(ctx.res, 403, { detail: "path escapes the project jail" });
    if (RAW_DENY.some((e) => (requested ?? "").toLowerCase().endsWith(e)))
      return json(ctx.res, 403, { detail: "File type not servable as raw data" });
    const file = rawLocalFile(requested) ?? (resolved.notFound ? null : resolved.file);
    if (!file || !existsSync(file)) return json(ctx.res, 404, { detail: "not found" });
    serveRange(ctx.req, ctx.res, file, rawMime(requested ?? file), headOnly);
  };
}
route("GET",  "/api/files/raw", rawHandler(false));
route("HEAD", "/api/files/raw", rawHandler(true));
```

Notes on the above, all tied to existing mock behaviour:

* `resolveJailed` (`server.mjs:303-314`) already returns `{jailed:true}` for `..` or anything
  outside `PROJECT_ROOT` (`server.mjs:69`, `"/mnt/example"`), so the 403 path is free.
* `EXT_FALLBACK` (`server.mjs:252-259`) must gain `.nii.gz`/`.msh`/`.gii`/`.lut`/`.opt` entries
  pointing at small fixture files under `desktop/tests/fixtures/artifacts/`, otherwise the
  *no-`TIT_MOCK_DATA_DIR`* path 404s. A 2 MB `T1.nii.gz` slice and a small `.msh` are enough for
  the viewer to render something in CI.
* `basename`/`statSync`/`createReadStream` — `basename` needs adding to the `node:path` import at
  `server.mjs:23`; the others are already imported (`server.mjs:21`).
* Route matching is exact-method (`server.mjs:1370`), hence two `route(...)` registrations.
* Auth: the dispatcher gates all `/api/*` at `server.mjs:1362-1367`; `HEAD` is in
  `SAFE_METHODS` (`server.mjs:132`) so the cookie alone suffices, matching the real server.

### 8.3 `buildViewSpec` gains a `scene`

`server.mjs:560-599` builds the mock ViewSpec. Add a `sceneFor(space, layers)` helper that
applies the §4.2 mapping and returns the §4.3 shape, then
`return { space: …, layers: resolvedLayers, freeview_args, scene: sceneFor(...) }`
(`server.mjs:598`). The mapping is ~30 lines and has no fixtures of its own.

### 8.4 Wiring the data directory into the e2e run

`desktop/playwright.config.ts` `webServer.env` (the block with `TIT_MOCK_PORT`,
`TIT_MOCK_TOKEN`, `TIT_MOCK_WS_INTERVAL_MS`) gains:

```ts
          TIT_MOCK_DATA_DIR: process.env.TIT_MOCK_DATA_DIR ?? "",
```

so a developer can run `TIT_MOCK_DATA_DIR=/Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie/m2m_ernie npm run e2e`
and get the real `T1.nii.gz` in the viewer, while CI (unset) falls back to the small fixtures.
The `contract.test.ts` child spawn (`contract.test.ts:44-47`) needs no change — the
fallback path is what it tests.

### 8.5 `contract.test.ts` additions

In the big coverage `it(...)` after the `files (v1)` block (`contract.test.ts:290-295`):

```ts
    await call("/api/files/raw", "GET", `/api/files/raw?path=${encodeURIComponent(
      "/mnt/example/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz")}`);
```

plus, if `/api/scene/{kind}` is added, `await call("/api/scene/{kind}", "GET",
"/api/scene/simulation?subject=ernie&simulation=Thalamus")`. Without these the
`exercised == declared` assertion at `:314` fails.

Separately, `desktop/tests/mock-server/server.test.ts` is the place for behavioural mock tests
(Range → 206, HEAD → 200 + `content-length`, `..` → 403, `.html` → 403).

### 8.6 E2E spec

`desktop/tests/e2e/viewer.spec.ts` gains a case that the in-app canvas mounts and the
`/api/files/raw` request is issued (Playwright `page.waitForResponse(/\/api\/files\/raw/)`), and
the screenshot set in `desktop/tests/e2e/artifacts/final-mock/` gains
`viewer-internal-{light,dark}.png` alongside the existing `viewer-*.png`.

---

## 9. (7) Risks

### 9.1 Path traversal and symlinks

* The jail is `Path.resolve()` + `is_relative_to` (`files.py:61-68`, `viewspec.py:531-539`).
  `Path.resolve()` **follows symlinks**, so a symlink inside the project pointing at
  `/etc/shadow` resolves *outside* the roots and is refused. Verified live: `/etc/passwd` → 403,
  `<sub-ernie>/../../../../etc/passwd` → 403.
* **TOCTOU remains**: the check `stat`s the resolved path, then `FileResponse` re-opens it by
  path. An attacker who can write inside the project could swap a file for a symlink between
  the two. This is the *same* window `/api/files/artifact` already has, and the threat model
  ("anyone who can write in the project already has the container") makes it acceptable — but
  it should be stated. A stricter version opens the file **once** (`os.open(..., O_NOFOLLOW)` on
  the final component) and streams the fd.
* The **second jail root** is `Path(mni_resources_dir()).resolve().parent` (`viewspec.py:520`)
  = `/ti-toolbox/resources` in the container — i.e. the whole bundled `resources/` tree, which
  in this deployment is *inside the mounted source checkout*. `ls resources/` shows
  `atlas/`, and `resources/` also holds `patches/`, `atlas2subject/` etc. Serving those as raw
  bytes is harmless (they are shipped, public files), but note that `/api/files/raw` will happily
  return `resources/patches/patch_nan_to_num.py` as `application/octet-stream`. If that is
  unwanted, narrow the raw route's second root to `mni_resources_dir()` itself rather than its
  parent.
* Query-string `%2e%2e` never decodes into a traversal because the value arrives as a literal
  path segment — the existing test documents this (`tests/test_files_routes.py:102-107`).

### 9.2 Content type / sniffing

* `mimetypes.guess_type` is wrong or useless for every format the viewer needs (measured:
  `.nii.gz`→`(None,'gzip')`, `.msh`→`model/mesh`, `.mgz`→`application/vnd.proteus.magazine`,
  `.geo`→`application/vnd.dynageo`, `.gii`/`.nii`/`.lut`/`.opt`→`(None,None)`). Use the explicit
  table.
* **`.gii` is XML.** Serving it as `text/xml`/`application/xml` in the app origin plus a
  navigation would let a crafted GIfTI act as a document. `application/octet-stream` +
  `nosniff` + `Content-Disposition: attachment` removes the whole class.
* **Never set `Content-Encoding: gzip` for `.nii.gz`.** Verified: Starlette's `FileResponse`
  does not, and no `GZipMiddleware` is installed (`app.py:146-147` adds only `CSPMiddleware`
  and `TrustedHostMiddleware`). If one were added, the browser would transparently inflate,
  `Content-Length` would stop matching the body, and Range requests would become meaningless —
  and Tetravox's worker already inflates with `DecompressionStream('gzip')`
  (`ARCHITECTURE.md:994,1017-1019`). **Any future compression middleware must exclude
  `/api/files/raw`.**

### 9.3 Huge files

* Worst cases in this dataset: `ernie_seeg.msh` 492 MB, `ernie_TDCS_{1,2}_scalar.msh` 420 MB,
  `Thalamus_TI.msh` 255 MB, `ernie.msh` 184 MB. Measured full stream of the 255 MB mesh through
  `FileResponse`: **0.49 s** in-process; over loopback HTTP it will be bounded by the socket.
* Memory: `FileResponse` streams in chunks; the **client** is the risk. Tetravox's own budget
  (`ARCHITECTURE.md:2795-2869`) plus rule 1 "worker-per-dataset … a worker's high-water mark is
  permanent for its lifetime" (`:1002-1005`) means opening `ernie_TDCS_1_scalar.msh` is a
  several-hundred-MB commitment. **The scene document should therefore carry `bytes` per
  dataset** (§4.3) so the renderer can warn/confirm before loading a 420 MB mesh, and the
  server should never put a `high_frequency` mesh in a default scene.
* Uvicorn has no response-size cap; no change needed, but a `?max_bytes=` guard is *not*
  recommended (it would break legitimate loads).

### 9.4 Container-vs-host paths

* Every path in a ViewSpec, catalog response and scene is a **container** path
  (`/mnt/000/...`), because `ServerSettings.project_dir` is resolved container-side
  (`settings.py:72-107`, `/mnt/<PROJECT_DIR_NAME>` branch at `:88-95`) and
  `catalog.py` composes from `PathManager`. `Project.host_path` (`schemas.py:41-46`, from
  `LOCAL_PROJECT_DIR`) is the only host-side string the API exposes.
* This is *why* the raw route exists: the renderer cannot open `/mnt/000/...` itself. The scene
  keeps both `url` (usable) and `path` (displayable, and what the Freeview/Gmsh buttons post
  back) — but the renderer must never try to `fetch('file:///mnt/000/...')`.
* If the server is ever run **on the host** (`LOCAL_PROJECT_DIR`, `settings.py:86`), the paths
  become host paths and everything still works, because the client only ever uses `url`.

### 9.5 Browser mode

* The launcher can print `http://host:port/?token=…` and the app runs in a plain browser
  (mocked at `desktop/tests/mock-server/server.mjs:1332-1336`). In that mode:
  * `CSP_HEADER` from `app.py` is the *only* CSP — so the `'wasm-unsafe-eval'` addition is
    **required** for browser mode, not just Electron.
  * Cross-origin is impossible by construction (`connect-src 'self'`, `TrustedHostMiddleware`
    at `app.py:147` limited to `127.0.0.1`/`localhost` unless `--allow-host` is given), so a
    remote/HPC deployment using `TIT_ALLOW_HOSTS` (`settings.py:141-143`) will serve the viewer
    over the network — **and then `/api/files/raw` is streaming 250 MB meshes over that
    link**. Worth a UI warning keyed on `Project.host_path == null` + a non-loopback `Host`.
  * WebGL2 may be unavailable (software rendering, remote X). The renderer must degrade to the
    Freeview/Gmsh buttons; that is exactly why `capabilities.x11_display`/`gmsh`/`freeview` must
    **stay** rather than be deleted (§5.2).
* Dev mode: when the renderer is served by Vite (`TIT_DEV_ORIGINS`, `settings.py:136-138`), the
  page origin is `http://127.0.0.1:5173` and `app.py`'s CSP does **not** apply (the middleware
  only stamps responses tit.server itself serves, `app.py:51-58`) — so a CSP bug will be
  invisible in dev and appear only in a packaged run. Add the CSP assertion to
  `tests/test_server_skeleton.py` rather than relying on manual dev testing.

### 9.6 Auth and the Worker fetch

* A **module Worker** created from the app origin inherits the document's origin; its
  `fetch('/api/files/raw?path=…')` defaults to `credentials: 'same-origin'` and therefore sends
  the `HttpOnly; SameSite=Strict` `tit_session` cookie (`app.py:165-172`). `GET`/`HEAD` are safe
  methods (`auth.py:58,102`) so no CSRF proof is needed. **Do not put the bearer token in the
  URL** — it would land in the scene JSON, in logs (`tit/server/access_log.py`) and in any
  screenshot.
* If Tetravox is ever embedded as an `<iframe>` under a *different* origin, none of this holds
  (no cookie, `connect-src` violation, CORS). Keep it same-origin.

### 9.7 Contract / gate

* The v1 gate is **already failing** (51 problems, §7.1). Adding named schemas without
  Pydantic models grows that number; §7.1(a) is the way to shrink it instead.
* `contract.test.ts:314` demands exact path coverage — a contract path added without a mock
  route and a `call(...)` fails the desktop unit suite, not just a lint.
* `Capabilities.internal_viewer` is the one new field the gate *will* enforce, because
  `Capabilities` is a real `response_model` (`capabilities.py:59`).

### 9.8 Scene/ViewSpec drift

* `scene` is derived from `layers` by a pure function called inside `_finish`
  (`viewspec.py:465-469`), so the two cannot drift **for server-built specs**. They *can* drift
  for a client-edited ViewSpec posted to `POST /api/view/args` (`viewers.py:155-178`), which
  does not rebuild `scene`. Either add `spec["scene"] = to_tetravox_scene(spec)` there too, or
  document that the client owns the scene once it starts editing. **Recommend the former** —
  it is one line and keeps one authority.
* `_ensure_gmsh_opt_sidecar` (`viewers.py:225-241`) **writes** `<mesh>.msh.opt` as a side effect
  of launching Gmsh. If the internal viewer stops going through that route, meshes that never
  had a `.opt` will lose their tissue names. Either call `create_mesh_opt_file` from the scene
  builder (a write from a GET — undesirable), or accept `$PhysicalNames`-less meshes rendering
  with numeric tags. Verified: `Thalamus_TI.msh.opt`, `Thalamus_normal.msh.opt`,
  `Thalamus_TI_central.msh.opt`, `ernie.msh.opt` and both `ernie_TDCS_*_scalar.msh.opt` all
  exist already on `sub-ernie`; `grey_Thalamus_TI.msh` and `white_Thalamus_TI.msh` have **no**
  `.opt`.

---

## 10. Open questions for the maintainer

1. **`scene` on `/api/view/{kind}`, or a separate `GET /api/scene/{kind}`?** §4.1 recommends the
   additive field (cheapest at the contract gate and the mock's coverage assertion). A separate
   route is warranted only if a non-viewer consumer (a `report` job, a CLI) wants scenes without
   ViewSpecs.
2. **Pydantic-model the ViewSpec/Scene (§7.1a) in this change, or leave the 51-problem contract
   backlog alone?** Modelling removes 5 of the 51 and makes the generated TS types nominal.
3. **Should the raw route's second jail root be narrowed** from `resources/` to
   `resources/atlas/` (§9.1)? Today it would serve any file in the bundled `resources/` tree.
4. **Default scene contents for `kind=simulation`.** Today `build_view` returns *five* layers
   including two hidden 17 MB / 2.6 MB volumes. Loading all five into Tetravox costs ~36 MB of
   downloads before the user sees anything. Should the scene mark hidden layers as
   `lazy: true` (dataset declared, bytes not fetched until made visible)? That is a scene-schema
   field and a renderer behaviour, but it must be decided before the schema is frozen.
5. **Initial cursor.** The only server-side source is `analysis.json`'s `center` for
   `analysis_type: "spherical"` (`tit/analyzer/config.py:172-174`); `sub-ernie`'s only analysis
   is `cortical` with `center: null`. Is a flex-search target (`flex_meta.json`) worth wiring in
   as a second source?
6. **Who owns the mesh field-name guess?** `catalog._FIELD_RE` (`catalog.py:218`) recognises
   `TI_max|TI_normal|TI_focality|magnE` from *NIfTI* basenames. For a `.msh` the real field
   names live inside the file, which the server will not read. Is guessing from the basename
   acceptable, or should the scene omit `field` and let the renderer pick from
   `MeshDataset.fields` after load?

---

## Appendix — commands run (all read-only; scratchpad scripts only)

```
docker exec tit-v3-spike simnibs_python -c "import starlette, fastapi, sys; ..."
docker exec tit-v3-spike simnibs_python -c "import inspect, starlette.responses as r; ..."   # FileResponse source
docker exec tit-v3-spike simnibs_python /tmp/headtest.py     # GET-only route -> HEAD 405; api_route/stacked -> 200
docker exec tit-v3-spike simnibs_python /tmp/mimetest.py     # mimetypes + gz content-encoding
docker exec tit-v3-spike simnibs_python /tmp/etagtest.py     # If-None-Match/If-Modified-Since -> 200 (no 304)
docker exec tit-v3-spike simnibs_python /tmp/wasmct.py       # .wasm -> application/wasm
docker exec tit-v3-spike simnibs_python /tmp/viewdump.py     # real build_view("simulation", ernie/Thalamus)
docker exec tit-v3-spike simnibs_python /tmp/catdump.py      # build_view("subject") + simulation_detail + analyses
docker exec tit-v3-spike simnibs_python /tmp/rawproto.py     # the raw-route prototype, real ernie files
docker exec tit-v3-spike bash -lc 'cd /ti-toolbox && simnibs_python -m tit.server --project /mnt/000 --dump-openapi /tmp/o.json'
python3 dev/contracts_check.py contracts/openapi.v1.json <dump>   # 136 warnings, 51 problems
```

Scratchpad scripts live under
`/private/tmp/claude-501/-Users-idohaber-01-production-TI-toolbox/2f1d440f-51f9-4340-bb8a-c347107a12b1/scratchpad/`
(`rawproto.py`, `viewdump.py`, `catdump.py`, `headtest.py`, `mimetest.py`, `etagtest.py`,
`wasmct.py`, `o.json`). No repository file was created or modified.

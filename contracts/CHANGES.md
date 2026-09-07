# Schema changes

Dated log of changes to the config dataclasses registered in
`tit.config_io.CONFIG_CLASS_REGISTRY`, and the resulting regeneration of
`contracts/generated/config.schema.json` / `contracts/generated/openapi.json` /
`desktop/src/renderer/api/schema.d.ts`. Append one entry per change; do not
edit past entries — earlier entries name files by the paths they had at the
time (`schema.json`, `openapi.v1.yaml`, `openapi.v0.yaml`), which the
2026-09-07 restructure below renamed.

What each contract file is, which command generates it and the freeze rule:
[`contracts/README.md`](README.md).

## Before v3 — the 2026-08-27 contract build-out (folded summary)

Seven entries dated 2026-08-27 recorded the week the v1 contract was first built out, while the
server routes, the config dataclasses and the contract YAML were being written by parallel lanes.
Everything they describe is already true of `contracts/openapi.v1.yaml` and
`contracts/schema.json` as shipped, so they are summarised here rather than restated at length;
the full text is in git history (`git log -p -- contracts/SCHEMA-CHANGES.md`).

- **fix:backend-catalog** — `tit.catalog.atlas_regions` returns the real FreeSurfer `.annot`
  label index as an integer `id` with the region's own `hemi` (the integer `FlexConfig.AtlasROI.label`
  needs), subcortical regions always carry `hemi: null`; `FlexRun`/`ExRun.artifacts` are populated
  by a bounded-depth walk of the run directory; `ViewLayer.percentile` resolves to concrete
  `cal_min`/`cal_max`; new path `GET /api/catalog/electrode-overlays`.
- **B4 — `QSIPrepSettings` / `QSIReconSettings`** — the diffusion settings dataclasses enter the
  registry and therefore `schema.json`.
- **fix:contract** — reconciles the contract with what the first server stages actually built:
  `Region`, `ViewLayer`, run artifacts and the job shapes.
- **fix:backend-runners** — `NiftiAverageConfig` / `NilearnConfig` land; the events schema is
  aligned with what the runners emit.
- **fix:contract (round 2)** — the `ra_13` finding-3 gate fixes (path-parameter aliases, `/ws/*`
  exemption, implied 401/403/404, untyped-response warnings — all now documented in
  `dev/contracts_check.py`), plus electrode overlays and `log_path`.
- **B2 (catalog-security)** — `Capabilities.jupyter`, `POST /api/project/init`,
  `POST /api/system/terminate`, `GET /api/view/args`; the `ra_14` path- and name-hardening pass.
- **B4 (runners + config, round 2)** — flex driver dispatch, `tissue_conductivities` reaching the
  solver through the config instead of `TISSUE_COND_<n>` env vars, and strict `deserialize_config`.

Every entry from 2026-09-02 on is kept verbatim below.

## 2026-09-02 — F2 (server, v3 in-app viewer) — `/api/files/raw/{path}`, `ViewSpec.scene`, `TitScene`

No dataclass changes, so `contracts/schema.json` is untouched by this entry.
Everything here comes from `docs/dev/HISTORY.md § 2026-09-02 (UX redesign)` §4.1/§4.2 (the
in-app viewer replaces the Freeview/Gmsh round trip for *viewing*; both
launchers stay).

1. **New path `GET|HEAD /api/files/raw/{path}`** (`tit/server/routes/files.py`).
   Streams one project file to the viewer as opaque bytes -- the file types
   `/api/files/artifact` refuses (`.nii.gz`, `.msh`, `.msh.opt`, `.gii`,
   `*_LUT.txt`, `.lut`, `.annot`, `.mgz`), with the opposite response policy:
   `application/octet-stream` + `nosniff` + `attachment`, never a
   `Content-Encoding`, and a 403 for the extensions a browser could execute as
   a document (`.html .htm .xhtml .svg .xml .xsl .mhtml`). Range/206, `If-Range`
   and `ETag`/304 are implemented in the route (Starlette's `FileResponse` does
   Range but not 304, and FastAPI does not add HEAD to a GET route). The URL
   path *is* the absolute container path minus its leading slash, so the last
   segment stays the real file name -- the viewer's loader takes the name, the
   gzip decision and its volume-vs-mesh routing from it, all of which a
   `?path=` URL would mangle. `head` is declared for documentation only
   (`dev/contracts_check.py`'s `METHODS` and the desktop contract self-test
   both enumerate get/post/put/patch/delete).
2. **Jail narrowed for this route only.** `tit.viewspec.raw_jail_roots()` =
   project dir + `resources/atlas`, versus `jail_roots()`'s project dir +
   the whole `resources/` tree. Handing a launcher any bundled reference file
   is fine; handing the *browser* `resources/patches/*.py` from the app's own
   origin is not. Verified in-container: `resources/atlas/MNI152_T1_1mm.nii.gz`
   → 200, `resources/patches/patch_nan_to_num.py` → 403.
3. **`ViewSpec.scene`** (optional) plus six new `components.schemas`:
   `TitScene`, `SceneDataset`, `SceneSidecar`, `SceneLayer`, `SceneWindow`
   (and `SceneSidecars`/`SceneThreshold`/`ViewPercentile` in the dump only).
   Built by the pure `tit.viewspec.to_tetravox_scene(spec)` from the resolved
   layers, attached in `finish_spec` so `GET /api/view/{kind}` and
   `POST /api/view/args` cannot diverge. `POST /api/view/args`'s response
   gains `scene` (that route is not in the contract).
4. **`ViewSpec`/`ViewLayer` are now Pydantic models** (`tit/server/schemas.py`)
   with `response_model=ViewSpec` on `GET /api/view/{kind}`, so both -- and the
   scene schemas -- appear in the dump by name instead of as an anonymous
   `dict[str, Any]`. `build_view` now normalises `space` to `subject`/`mni`
   (the two values the contract has always declared).
5. **CSP**: `script-src 'self' 'wasm-unsafe-eval'` added to
   `tit/server/app.py::CSP_HEADER`; without it Chromium blocks
   `WebAssembly.instantiate` (scripts were falling back to `default-src
   'self'`) and the viewer cannot start, in a browser tab as well as in
   Electron. `mimetypes.add_type("application/wasm", ".wasm")` in
   `tit/server/static.py` so the bundled module streams with the type
   `instantiateStreaming` requires.
6. **`tit/tools/electrode_overlay.py`** writes alpha `255` in the channel LUT
   instead of `0`: a FreeSurfer LUT's fourth colour column is read as opacity
   by every consumer except Freeview (which reads it as transparency and
   treats 255 as opaque), so every electrode marker was invisible in the
   in-app viewer.

Regenerated: `python3 dev/build_contract.py` → `contracts/openapi.v1.json`;
`cd desktop && npm run gen:api` → `desktop/src/renderer/api/schema.d.ts`
(now names `components["schemas"]["TitScene"]`).

### Verified

- `python3 -m pytest -q` (host, full suite): **3024 passed, 17 skipped, 0
  failed** — including the new `tests/test_files_raw.py` (20 cases) and
  `tests/test_viewspec_scene.py` (26 cases).
- `docker restart tit-v3-spike` → `docker exec … --dump-openapi /tmp/o.json`
  → `python3 dev/contracts_check.py contracts/openapi.v1.json <dump>` →
  **133 warnings, 49 problems**, down from the 51 this branch already had;
  none of the 49 mentions the raw route, `ViewSpec`, `ViewLayer` or any
  `Scene*` schema (the remaining ones are the pre-existing backlog other
  lanes own).
- Real data through the running container (`sub-ernie`, Dataset 000):
  `HEAD T1.nii.gz` → 200, 13,109,495 bytes, `etag
  "c6e5d6930ead4ce6bb282f95129c2b07"`, no `content-encoding`;
  `Range: bytes=0-1023` → 206 `bytes 0-1023/13109495` with the gzip magic
  `1f 8b 08 00` intact; full GET → 200 in 0.068 s; `If-None-Match` → 304;
  `grey_Thalamus_TI.msh` HEAD → 200, 63,926,663 bytes; `/etc/passwd` → 403;
  `…/../../etc/passwd` → 403; a symlink to `/etc/passwd` planted inside the
  project (and removed again) → 403; an existing project `report.html` → 403
  on the raw route and still 200 on `/api/files/artifact`.
- `GET /api/view/simulation?subject=ernie&simulation=Thalamus&space=subject`
  → 5 datasets with real byte counts (13.1 MB T1, 17.2 MB and 2.6 MB hidden
  overlays marked `lazy`), electrode LUT as a sidecar, `layout "2x2"`;
  `GET /api/view/custom?path=<Thalamus_TI.msh>` → a mesh dataset with its
  `.msh.opt` sidecar, `field "TI_max"`, `clip "cursor"`, `layout "3d+1"`.
- `cd desktop && npx vitest run tests/mock-server` → **17 passed** (the
  contract self-test's exact path coverage now includes the raw route).

## 2026-09-03 — W3a (server, Docker streamline) — real Tetravox ViewSpec v2 replaces `TitScene`; `/tetravox/` embed route; `Capabilities` drops X11/Freeview/Gmsh/FreeSurfer, adds `tetravox_embed`/`fastsurfer`

`docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)` D1/D3: Freeview/Gmsh/X11/FreeSurfer removed from the
runtime entirely; viewing is the Tetravox embed served client-side from this same server.

1. **`ViewSpec.scene` is now a real Tetravox `ViewSpec` v2 document** (the frozen
   `@tetravox/engine` `scene/types.ts` shape, `SCENE_VERSION = 2`), built by
   `tit.viewspec.to_tetravox_viewspec(spec)` -- replacing the F2-era `TitScene`
   approximation. `TitScene`/`SceneDataset`/`SceneSidecar`/`SceneLayer`/`SceneWindow` are
   **deleted** from both `tit/server/schemas.py` and this contract; `ViewSpec.scene` is now
   `dict[str, Any] | None` server-side (`type: [object, "null"]` in the contract) because the
   full engine scene model is Tetravox-owned and far larger than a Pydantic model is worth
   mirroring here. The subset this server actually emits is hand-schema'd, host-facing, in
   `contracts/tetravox-viewspec-v2.schema.json` and asserted against every scene
   `tests/test_viewspec_scene.py` builds (`jsonschema.Draft202012Validator`).
   `DatasetRef.path`/`.absPath` are both the *same* origin-relative `/api/files/raw/...` URL
   string (never a container filesystem path) -- see `tit/viewspec.py`'s module-level docstring
   on why an absolute-path URL needs no client-side rewriting from inside the same-origin
   `/tetravox/` iframe, and why both fields carry it rather than picking one. `fingerprint` is
   always `""`. Volume layers get a concrete `Scale` (`{kind:'linear',lo,hi}` or
   `{kind:'heat',min,mid,max,...}`) resolved from one `numpy`/`nibabel` read per file
   (`tit.viewspec._volume_stats`, cached by `(mtime, size)`) -- a real `ViewSpec` has no
   percentile-window escape hatch the client resolves after load, unlike the retired
   `TitScene.SceneWindow`. A new grey-matter TI mesh layer (`_grey_mesh_layer`, hidden by
   default) is now built for `kind=simulation`'s default field, with `field: {source:'elm',
   name:'TI_max', component:'mag'}`, a cursor-following clip plane and 2D contours.
   `slices`/`view3d`/`annotations`/`background`/`lighting`/`transparency` are one fixed,
   documented default rig (no per-file camera fit -- documented as a known v1 limitation in the
   module docstring).
2. **`GET|POST /api/viewers/{freeview,gmsh}` and `_require_x11` are deleted**
   (`tit/server/routes/viewers.py`, ~110 lines removed) along with their contract paths; no route
   submits a `"viewer"` job any more (`tit/jobs/kinds.py`'s `"viewer"` kind and
   `VIEWER_PROGRAMS` are now dead code -- **not removed here**, out of this lane's owned paths;
   flagged for whichever lane owns `tit/jobs/kinds.py`). `GET /api/view/{kind}` and
   `POST /api/view/args` (still not declared in the contract, per this file's existing practice)
   are unaffected and need no X11/capability check any more -- the ViewSpec/scene is built
   unconditionally. `ViewSpec.freeview_args` is kept for one release, marked deprecated in both
   the Pydantic field description and this contract.
3. **`Capabilities` drops `freesurfer`/`x11_display`/`gmsh`/`freeview`**, adds
   `tetravox_embed: {available, version, protocol}` (read from
   `<tetravox_embed_dir>/manifest.json`, `available=False` on any failure -- no directory, no
   manifest, malformed JSON) and `fastsurfer: bool` (`FASTSURFER_HOME` or `/opt/fastsurfer` has
   `run_fastsurfer.sh`). Changed identically in `contracts/openapi.v0.yaml` (not just v1) since
   the live runtime genuinely no longer has the fields the walking-skeleton contract used to
   require -- v0's own header commits to tracking "the real server's `--dump-openapi` output",
   not a frozen Phase-0 shape.
4. **New static route `/tetravox/{path}`** (`tit/server/static.py`, not itself in the
   OpenAPI contract, same as `/`): serves `ServerSettings.tetravox_embed_dir` (env
   `TIT_TETRAVOX_EMBED_DIR`, CLI `--tetravox-dir`, default `/opt/tetravox/embed`) with its own
   CSP (`TETRAVOX_CSP`: `script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; ...`) on
   every response under the prefix, correct MIME per extension (`.wasm` already registered
   `application/wasm`), `index.html` for `/tetravox` and `/tetravox/`, a path jail, and a 404
   (not a SPA fallback) for both a missing embed directory and an unknown asset inside an
   installed one. `"tetravox"` added to `RESERVED_PREFIXES` so the path can never fall through to
   the main UI bundle's SPA route even when both are installed. The app's own `CSP_HEADER` in
   `tit/server/app.py` **drops** `'wasm-unsafe-eval'` now that the embed carries its own -- no
   code in the app's own origin needs it any more.
5. **Contract-check status (`dev/contracts_check.py`)**: `openapi.v0.yaml` — clean (10
   operations, 9 schemas). `openapi.v1.yaml` — 49 pre-existing problems against a live
   `--dump-openapi`, **none of which touch anything this lane owns** (verified by grepping the
   output for `capabilit|viewspec|viewer|scene|tetravox`: only 6 hits, all `JobKind` enum
   members inherited from `PlanJob`/`LockConflict`/`PlanResult` schemas that are themselves
   entirely absent from the dump -- a pre-existing gap this repo has flagged before, e.g. this
   file's 2026-08-27 B2 entry). Same 88-schema, same-count dump whether generated in-process
   (`create_app(settings).openapi()`) or via a real `simnibs_python -m tit.server
   --dump-openapi` subprocess -- ruling out an artifact of how the dump was produced.
- **Real data through `sub-ernie`, Dataset 000** (host pytest against real fixtures, not the
  container -- the container run mirrors it): `GET /api/view/simulation?subject=ernie&
  simulation=L_Insula` produces a schema-valid `scene.datasets[].path` of
  `/api/files/raw/<abs path>` for every layer, a hidden grey-matter TI mesh layer with
  `field.name == "TI_max"` and `clip.planes[0].followCursor == true`.
- `python3 -m pytest -q tests/` (host, py3.14): **3140 passed, 18 skipped**; the only 2 failures
  (`test_process_filter_matches_qt_list`, `test_plan_pre_builds_full_dag_for_two_subjects`) are
  pre-existing drift from concurrent lanes' in-progress edits to files this lane does not own
  (`tit/server/routes/system.py`'s `RELEVANT_KEYWORDS` lagging `tit/gui/system_monitor_tab.py`'s
  freesurfer→fastsurfer rename; `tit/jobs/plans.py`'s new `G2b` FastSurfer DAG stage) --
  reproduced identically inside `tit-v3-spike` (212 passed / 1 failed on the narrower file set).
- `python3 -m black --check` on every touched Python file: clean.
- `cd desktop && npx vitest run tests/mock-server`: **21 passed** (4 new: `/tetravox/*`
  index/CSP/manifest/404-not-SPA-fallback, against the new deterministic fake-embed fixture at
  `desktop/tests/e2e/fixtures/fake-embed/`). `npm run gen:api` regenerated
  `src/renderer/api/schema.d.ts` from the rebuilt `contracts/openapi.v1.json`.
  `npm run typecheck`'s `tsconfig.node.json` half is clean; its `tsconfig.web.json` half now
  fails in 5 files this lane does not own
  (`src/renderer/pages/{analyzer,optimizer-flex,results,viewer}/api.ts`,
  `src/renderer/pages/viewer/index.tsx`) that still reference the removed
  `/api/viewers/{freeview,gmsh}` paths and `capabilities.{freeview,gmsh,x11_display}` --
  expected fallout of this contract change, reported to whichever lane owns
  `desktop/src/renderer/**` for Phase C integration rather than fixed here.
- `python3 -m black` on every touched Python file: clean.

## 2026-09-03 — Lane R (reconciliation) — `PreprocessConfig` field rename lands in the contract; `has_fastsurfer`; `JobKind` drops `viewer`

Closes the Phase-A cross-lane needs lists (W3a/W3b/W4 notes) that touch `contracts/**`: the
dataclass side of each of these changes had already landed in `tit/pre/config.py` (W3b) and
`tit/jobs/spec.py`/`kinds.py` (this lane); this entry is the contract catching up.

1. **`PreprocessConfig`** (`contracts/schema.json`, regenerated inside `tit-v3-spike` via
   `dev/build_schema.py`, 62 `$defs`): `run_recon`/`parallel_recon`/`parallel_cores` are gone,
   replaced by `run_fastsurfer: bool` (default `false`) and `fastsurfer_threads: int | null`;
   `run_subcortical_segmentations` is gone with no replacement (D2 -- the MATLAB-runtime
   thalamic/hippocampal subfield stages are not coming back). `openapi.v1.json` picks this up
   automatically through the existing `x-tit-config: PreprocessConfig` merge in
   `dev/build_contract.py` -- no manual edit to `openapi.v1.yaml`'s placeholder entry was needed.
2. **`Subject.has_fastsurfer: boolean`** (required) added to both `openapi.v0.yaml` and
   `openapi.v1.yaml`, and to the Pydantic `Subject` model in `tit/server/schemas.py`. This closes
   a real (not just contract-drift) bug: `tit.catalog.list_subjects()`/`subject_detail()` had
   already started returning a `has_fastsurfer` key (W3b), but `GET /api/catalog/subjects`
   (`tit/server/routes/catalog.py`) builds its response through the `SubjectList`/`Subject`
   Pydantic models, which silently dropped any key the model didn't declare -- so the field
   was present in `subject_detail` (a plain-dict v1 route) but invisible on the v0
   `SubjectList` endpoint until this fix. `SubjectDetail` (`allOf: [Subject, ...]`) inherits the
   field automatically, no separate edit needed there.
3. **`JobKind` drops `"viewer"`** (`PlanJob.kind`/`LockConflict.kind` inherit it via `$ref`, so
   one enum edit covers all three) -- nothing has submitted a `"viewer"` job since W3a deleted
   the `/api/viewers/{freeview,gmsh}` launch routes; `tit/jobs/kinds.py`'s `"viewer"` branch and
   `VIEWER_PROGRAMS` constant, and the matching branch in `tit/server/routes/jobs.py` (a
   403 pointing at those now-deleted routes) are deleted; `tit/jobs/spec.py`'s
   `JOB_KINDS`/`CONTRACT_JOB_KINDS` and `tit/jobs/costs.py`'s `DEFAULT_COSTS` lose the entry.
   `tit/jobs/scheduler.py`'s `job.kind != "viewer"` budget bypass and `tit/jobs/locks.py`'s
   fall-through are both left as-is (unowned by this lane, and already correctly tolerant): a
   `spec.json`/`status.json` written before this change with `kind: "viewer"` still loads and
   costs without raising (`JobSpec.kind`/`JobStatus.kind` are plain, unvalidated `str` fields on
   read) -- exercised directly by
   `tests/test_jobs_registry.py::test_registry_reads_legacy_viewer_kind_job_without_crashing`.
4. `contracts/openapi.v0.yaml`'s `Subject` schema also gained `has_fastsurfer` even though
   nothing in W3a's entry above touched v0's job/viewer schemas -- consistent with this file's
   existing practice (see the 2026-09-03 W3a entry) that v0 tracks the live runtime's actual
   surface rather than a frozen Phase-0 shape.

**Gates**: host `python3 -m pytest -q` -- 3149 passed, 18 skipped, 0 failed. Container
(`tit-v3-spike`) full suite -- 3160 passed, 7 skipped, 0 failed (7 more collected than host: 5
GUI-import tests real PyQt5 makes runnable instead of skipped, `test_docker_engine.py`'s root-only
skip, `test_pre_fastsurfer.py`'s `FASTSURFER_HOME` skip). `dev/contracts_check.py`: v0.yaml clean
(10 operations, 9 schemas); v1.yaml -- 49 problems, byte-identical count to the pre-existing
structural gap the 2026-09-03 W3a entry already documented (most route modules return
`dict[str, Any]` rather than a typed `response_model`), reverified by grepping this run's own
output for `capabilit|viewspec|viewer|scene|tetravox|fastsurfer`: zero hits. `black --check` on
every file this lane touched: clean. `cd desktop && npm run gen:api` regenerated
`schema.d.ts`; `tsconfig.node.json` half of typecheck clean, `tsconfig.web.json` half has 4
pre-existing errors in 2 files this lane does not own (`src/renderer/app/jobs-rail/api.ts:47`
still literals `kind: "viewer"`; `src/renderer/pages/preprocess/index.tsx` still reads/writes
`run_recon`/`parallel_recon`/`parallel_cores`/`run_subcortical_segmentations`) plus their 2 test
files (`tests/unit/preprocess-defaults.test.ts`, `tests/unit/shell-subject.test.tsx`) -- the same
kind of expected, reported-not-fixed fallout the W3a entry above already established the pattern
for. `npx vitest run` -- 465 passed, 4 failed, all four in the same two unowned preprocess-fallout
files. `npm run build` -- clean.


## 2026-09-04 — lane U (dynamic embed delivery, `docs/dev/HISTORY.md § 2026-09-04 (embed convergence)` E1-E4)

Additive only: every change below is a new path or a new optional-in-practice property, and a
client that ignores all of it behaves exactly as before.

1. **`Capabilities.tetravox_embed` gains `source`, `features`, `compatible` and `supported`.**
   It now describes the **active** bundle, resolved the way `/tetravox/` resolves it (dev
   override → pinned/newest installed → baked into the image) rather than always the baked
   directory. This is E1's core: a host asks whether the embed has a *named feature*
   (`markers`, `pick`, `camera`) instead of comparing versions, so an additive Tetravox release
   needs no TI-Toolbox change. `supported` is always present — it is a property of the build, not
   of whatever happens to be installed — and `source` is `null` only when no bundle is available.
2. **Five new paths under `/api/tetravox`** (tag `tetravox`): `GET /api/tetravox` (active +
   installed + baked + supported range), `GET /api/tetravox/updates` (release index; answers 200
   with `available: false` and a sentence when it cannot be reached, because an air-gapped
   install is a supported state), `POST /api/tetravox/install` (`{url, sha256}` or `{version}`),
   `POST /api/tetravox/activate` (`{version}`, or `"baked"` to roll back) and
   `DELETE /api/tetravox/{version}`. Every one answers with the same `TetravoxState`, so a client
   never re-reads to learn what happened.
3. **New schemas**: `ProtocolRange`, `TetravoxRelease`, `TetravoxState`, `TetravoxUpdate`,
   `TetravoxUpdates`. The two request bodies are declared inline rather than as named components,
   because the routes take `dict[str, Any]` like every other body-taking route here and there is
   no server-side model for the dump to name.

**Gates**: host `python3 -m pytest -q` — 3587 passed, 32 skipped, 0 failed (68 new tests:
`tests/test_tetravox_{protocol,store,install,routes}.py`). `dev/contracts_check.py
contracts/openapi.v1.json <dump>` — 187 problems, **byte-identical to the count with the
tetravox paths and properties stripped out of the contract** (measured both ways this session),
i.e. this lane adds zero drift; grepping this run's output for `tetravox` gives zero hits.
`desktop`: `npm run typecheck` clean, `npm run lint` 0 errors (3 pre-existing warnings),
`npx vitest run` — the mock-server contract test drives all five new operations end to end.

## 2026-09-05 — OV (overview) — one bounded `GET /api/catalog/overview` replaces the Subjects fan-out

Additive only: one new path and seven new schemas. Every existing path, schema and property is
unchanged, so a client that ignores all of it behaves exactly as before.

1. **New path `GET /api/catalog/overview`** (tag `catalog`), answering `Overview`. It is the
   project Overview page's *single* read (`docs/dev/HISTORY.md § 2026-09-05` R1): the page it serves
   replaced Subjects, and with it a request fan-out of one `/api/catalog/subjects/{id}` per subject
   plus five output lists per subject plus one `/api/catalog/analyses` per simulation. That
   fan-out was capped in the renderer at 25 subjects, so a larger project silently rendered **no**
   output counts at all. This response owns the display facts instead, and its request count does
   not grow with subjects, simulations or outputs. Detailed output discovery stays lazy and stays
   in Results — the overview carries counts, never trees or previews.
2. **New schemas**: `PresenceState`, `OverviewCounts`, `OverviewReadiness`, `OverviewSubject`,
   `OverviewCoverage`, `OverviewTotals`, `Overview`. `PresenceState` is the point of the change:
   `present` / `absent` / `partial` / `pending` / `failed` are five distinguishable answers where
   the `Subject` booleans had two. `partial` is real (raw staged under `sourcedata/` but never
   converted; some but not all of a subject's EEG nets have a leadfield); `pending` and `failed`
   come from the job scheduler's own records for the job kind that would produce that artefact,
   and only ever apply to an artefact that is still absent — what is on disk always wins.
3. **`GET /api/catalog/subject-info` is untouched** and stays in the contract. The Subject Info
   *page* is deleted in the desktop app, but removing the endpoint is a breaking change and is
   left to the API's next versioned cleanup.

**Gates**: `python3 -m pytest tests/test_server_overview.py -q` — 10 passed.
`python3 dev/route_import_guard.py` — 19 route modules clean, `tit.server.routes.overview` at
18.6 ms against the 400 ms budget. `python3 dev/build_contract.py` regenerated
`contracts/openapi.v1.json` from the YAML; `pnpm run gen:api` regenerated
`desktop/src/renderer/api/schema.d.ts`.

## 2026-09-05 — BX (batch) — `JobGroupRequest` generalized beyond preprocessing

Additive only, in one schema. No dataclass changed, so `contracts/schema.json` is untouched. A
client that keeps sending exactly what it sent before (`kind: "pre"`, `config`, `subject_ids`,
`parallel_subjects`) behaves identically.

1. **`JobGroupRequest.kind`** widens from `enum: [pre]` to
   `[pre, sim, flex, flex_adaptive, flex_pareto, ex, mex]` — every kind that runs one independent
   job per subject (`docs/dev/HISTORY.md § 2026-09-05` R3). `pre` still expands into
   `tit.jobs.plans.plan_preprocessing`'s per-subject G1–G6/report DAG; the new kinds expand into
   one job per `(subject, config)` entry via the new `tit.jobs.plans.plan_per_subject`. Cohort
   kinds are deliberately *not* in the enum: a grouped `analyzer` run is one job over the whole
   selection and has no per-subject concurrency, so it stays on `POST /api/jobs` (the route
   answers 422 for `analyzer`, and a test pins that).
2. **New optional `JobGroupRequest.subject_configs`**: `[{subject_id, config}]`. A workflow whose
   config depends on the subject (an ROI resolved against that subject's own atlas, a
   subject-specific leadfield path) or that runs several jobs for one subject (the Simulator's one
   job per `(subject, montage)`) sends one entry per job instead of one template. Entries are
   matched to `subject_ids` by `subject_id`; a subject with no entry uses `config`; an entry
   naming a subject outside `subject_ids` is a 422. Whatever the caller sends, the server forces
   each generated config's `subject_id` to its own subject, so a generated config can never carry
   another subject's id.
3. **New optional `JobGroupRequest.tags` and `JobGroupRequest.overwrite`**: the two remaining
   fields the pages' previous per-job `POST /api/jobs` loops passed, so a group submission is a
   drop-in replacement for the loop. `overwrite` is ignored for `kind: "pre"`, which carries the
   same policy inside its config's `skip_existing_outputs` / `replace_existing_outputs`.
4. **`parallel_subjects` is unchanged in shape and meaning** and is now the *only* concurrency
   mechanism for these kinds: the whole group is created queued in one request and
   `tit.jobs.scheduler.evaluate` releases it `parallel_subjects`-at-a-time. The renderer no longer
   spaces out POSTs to imitate sequential or parallel execution.

**Gates**: `python3 -m pytest tests/test_jobs_routes.py tests/test_jobs_model.py -q` — 24 + 56
passed, including a cap-1 run that never has two members `running` and a cap-2 run that reaches
two. `python3 dev/build_contract.py` regenerated `contracts/openapi.v1.json` from the YAML;
`pnpm run gen:api` regenerated `desktop/src/renderer/api/schema.d.ts`.

## 2026-09-05 — `/api/guide/*`, the fixed guide scene (additive; lane GD, plan R4)

Five new read-only paths under a new `guide` tag. Nothing existing changed: `/api/scene/*` keeps
its subject parameter, its cache states and its 202s, and is still what a *subject's* pane would
use.

1. **`GET /api/guide/manifest`** — every part, net and atlas of the packaged guide, in the same
   shape `/api/scene/manifest` uses (`parts[]`, `nets[]`, `atlases[]`, `bbox`, `focus_bbox`), so
   one desktop component consumes either. It takes no `subject`, answers with no project bound,
   and never answers 202: the assets ship with the installation.
2. **`GET /api/guide/surface?part=&format=`**, **`GET /api/guide/labels?atlas=&format=`** — the
   packaged TVSC1/GIfTI bytes. `ETag` is the file's SHA-256 and `Cache-Control` is
   `max-age=31536000, immutable`, because these bytes cannot change without the installation
   changing (a subject's surface legitimately changes after a charm re-run, which is why that one
   is `must-revalidate`).
3. **`GET /api/guide/regions?atlas=`**, **`GET /api/guide/electrodes?net=`** — the atlas legend and
   one net's electrode names/positions, the same rows the scene routes answer with.
4. **`space` is `guide-ras`, and it is a frozen enum** — deliberately *not* `subject-ras`. The
   millimetres belong to the guide head; a client that wrote one into a research subject's config
   would produce a coordinate no downstream validation could catch (plan R4). The desktop pane
   keys "click-to-config is disabled here" off this value rather than off a comment.
5. **`volumes` is always empty.** The guide packages no label volume: region picking happens on
   the atlas payloads, on the surface the pane already draws.

**Gates**: `python3 dev/build_contract.py` regenerated `contracts/openapi.v1.json`; `pnpm run
gen:api` regenerated `desktop/src/renderer/api/schema.d.ts`; `python3 dev/route_import_guard.py`
clean on all 20 route modules; `python3 -m pytest tests/test_scene_guide.py tests/test_guide_routes.py -q`.

## 2026-09-05 — VW (viewer) — optional `atlas` on `GET /api/view/{kind}` (plan R5)

One new optional query parameter, on one existing path. Nothing else in the document moves, no
schema gains or loses a property, and a client that never sends it gets byte-for-byte the response
it got before.

1. **`GET /api/view/{kind}` gains `atlas` (query, optional, string).** It names which atlas overlay
   the scene should carry: an id from `GET /api/catalog/atlases` for the same subject and space
   (a display name such as `DK40` or `aparc.DKTatlas+aseg` in subject space), or a bundled MNI
   atlas's basename in MNI/group mode. `tit.viewspec.build_view` honours it in the `subject` and
   `group` branches, which are the two that build an atlas layer at all.

   **Absent preserves the current behaviour exactly** — that is the compatibility claim and it is
   asserted directly (`tests/test_viewspec.py::test_atlas_absent_keeps_the_servers_own_choice`
   compares the whole spec built with `atlas=None` against the spec built without the argument).
   The server's own choice is unchanged: `segmentation/labeling.nii.gz` when the head model has
   one, else the first atlas `VoxelAtlasManager` lists; `DEFAULT_MNI_ATLAS` in MNI.

   **An unknown id falls back to that same server choice rather than 404.** A view request is a
   request for a picture of an anatomy, and an atlas a subject no longer has is a stale bookmark,
   not a reason to answer with no picture at all. The alternative — refusing the whole scene
   because one overlay could not be resolved — turns a project moved between images into a viewer
   that will not open.

**Gates**: `python3 -m pytest tests/test_viewspec.py -q` — 36 passed (5 new).
`python3 -m pytest tests/ -q -k "viewspec or view or catalog_v1"` — 147 passed.
`python3 dev/build_contract.py` + `pnpm run gen:api` regenerated `contracts/openapi.v1.json` and
`desktop/src/renderer/api/schema.d.ts`; the parameter appears in both.

## 2026-09-05 — lane AU — automatic Tetravox embed updates (additive)

No dataclass changes, so `contracts/schema.json` is untouched. Plan of record:
`docs/dev/HISTORY.md § 2026-09-05/06 (Tetravox auto-update, selection, pipeline canvas)` §1-A (A2–A5).

1. **New path `POST /api/tetravox/policy`** — `{auto_update: boolean}` → the same
   `TetravoxState` every other tetravox write answers with. This is the only switch for
   A3's background check; the policy is persisted in `<install root>/policy.json`, not in
   `code/ti-toolbox/config/settings.json`, because it is a property of the *install root*
   (which may be a shared user-config mount) rather than of the project the server is bound to.
2. **New query parameter `refresh` on `GET /api/tetravox/updates`** (default `false`).
   Reading the route now answers from the cache the background check writes; `refresh=true`
   is what "Check now" sends. GitHub allows 60 unauthenticated requests per hour per IP, so
   a page that re-rendered on every mount would spend the budget on nothing.
3. **`TetravoxState.auto_update`** (required, boolean) and **`TetravoxUpdates.auto_update`,
   `.checked_at`, `.from_cache`, `.last_outcome`** (all optional) — what Settings needs to say
   *when* it last looked, *what* happened, and whether the answer is cached.
4. **New component `TetravoxUpdateOutcome`** — `{action, message, version?, protocol?, at?}` with
   `action ∈ {installed, available, current, unsupported, failed}`. `unsupported` is the one
   A1 exists for: a release whose embed protocol is past this build's supported range is
   *reported* as needing a TI-Toolbox update and is never installed.
5. **New WebSocket path `/ws/tetravox`** (hand-added to the dump in `tit/server/app.py`, as
   `/ws/system` and `/ws/jobs` already are): one message type, `{"type": "tetravox.updated",
   version, protocol, message}`, published after the policy has installed and activated a
   bundle. **`contracts/events.schema.json` is deliberately unchanged** — that file describes
   one line of a job's `events.jsonl`, and adding an app-level type to it would have made every
   job-event reader accept a type no job can emit.

Also in this entry, not a contract change: the release index moved from a `releases.json`
committed to the Tetravox repo (which never existed — it answered 404 for the whole of lane U's
live run) to the GitHub Releases API, so `index_url` now reports
`https://api.github.com/repos/idossha/tetravox/releases` unless `TIT_TETRAVOX_RELEASE_INDEX`
overrides it. That env override now accepts either that JSON shape or the flat index.

Regenerated: `contracts/openapi.v1.json` (`python3 dev/build_contract.py`),
`desktop/src/renderer/api/schema.d.ts` (`pnpm run gen:api`).

## 2026-09-05 — feat:pipeline-canvas — `/api/pipelines*` and the pipeline document (lane PC)

No dataclass changes, so `contracts/schema.json` is untouched by this entry. All of it is
**additive**: six new paths and eleven new component schemas; no existing path, schema or enum
was edited, so every v1 client keeps working unchanged.

1. **New standalone schema `contracts/pipeline.schema.json`** (JSON Schema 2020-12,
   `version: 1`) — the pipeline canvas document: `nodes[{id, kind, config, label?, position?}]`
   and `edges[{from, to, port}]`. It is the file saved under
   `<project>/code/ti-toolbox/pipelines/<name>.json` and the object carried in an exported
   notebook's `metadata.ti_toolbox.pipeline`. `kind` is an existing `tit.jobs.spec.JOB_KINDS`
   value (`pre`, `leadfield`, `flex`, `ex`, `mex`, `sim`, `analyzer`, `source`, `stats`) — the
   pipeline introduces **no new job kind**, asserted by
   `tests/test_pipeline_graph.py::test_every_node_kind_is_a_real_job_kind`. `port` is one of
   `subjects | montages | simulation | roi | leadfield`. Implemented by
   `tit/pipeline/document.py`; the same shapes are mirrored into `openapi.v1.yaml` as
   `Pipeline`/`PipelineNode`/`PipelineEdge` (item 3) so the generated TypeScript has them.

2. **New paths** (`openapi.v1.yaml`, tag `pipelines`):
   `GET /api/pipelines` (saved documents), `GET /api/pipelines/kinds` (the palette: each kind's
   typed ports, so the canvas never keeps its own copy), `POST /api/pipelines/validate`,
   `POST /api/pipelines/run`, `POST /api/pipelines/export?format=ipynb`, and
   `GET|PUT|DELETE /api/pipelines/{name}`.

   `POST /api/pipelines/run` returns a `PipelineRunResult` — **one** `group_id` for the whole
   canvas, because running a pipeline is exactly one `tit.jobs.manager.JobManager.submit_plan`
   call with `after_labels` taken from the document's edges (the same mechanism the `pre` G1–G6
   DAG already uses). There is no pipeline executor: the scheduler stays the only one.

3. **New component schemas**: `Pipeline`, `PipelineNode`, `PipelineEdge`, `PipelineRequest`,
   `PipelineRunRequest`, `PipelineRunResult`, `PipelineValidation`, `PipelineIssue`,
   `PipelineJobPreview`, `PipelineListEntry`, `PipelineKinds`. `PipelineNode.config` reuses the
   existing `PipelineConfig` placeholder, so a node's config is validated by exactly the same
   `tit.config_io` machinery `POST /api/jobs` uses (`tit/pipeline/plan.py::_round_trip`).

   `PipelineValidation` is deliberately a 200 with `ok: false` plus one `PipelineIssue` per
   problem (a cycle, an incompatible port, an unbound required input), each a sentence the canvas
   shows next to the node or wire. A 422 means the body is not a pipeline document at all.

4. **Regenerated** `contracts/openapi.v1.json` (`python3 dev/build_contract.py`) and
   `desktop/src/renderer/api/schema.d.ts` (`pnpm run gen:api`).

## 2026-09-06 — feat:external-viewer — `POST /api/view/open` lands; the whole `tetravox` section goes

Plan of record: `docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)`, decisions V1-V4.
No dataclass changes, so `contracts/schema.json` is untouched; `openapi.v1.yaml` was
edited and `openapi.v1.json` / `desktop/src/renderer/api/schema.d.ts` regenerated with
`python3 dev/build_contract.py` and `pnpm run gen:api`.

**This entry is a removal, and a breaking one.** The in-app Tetravox *embed* is retired.
Viewing is now the Tetravox **desktop app**, installed on the host, which signs, notarises
and updates itself. A container with no display could never have run it; an embed baked into
an image tied a viewer release to a toolbox release, which is exactly what the previous
entry's dynamic-delivery machinery existed to undo — by adding five routes, four schemas,
a WebSocket and an installer instead of removing the coupling's cause.

1. **Added: `POST /api/view/open`** → `ViewerOpen` (`{name, path, host_path, scene}`).
   Builds exactly the ViewSpec `GET /api/view/{kind}` would build for the same selection,
   rewrites every dataset and sidecar `path`/`absPath` from an `/api/files/raw/…` URL to the
   **host's** own absolute path, and writes it to
   `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`. `host_path` is `null` when this
   server cannot know its project's host root (`tit/server/host_path.py`), which the client
   renders as "download the file" rather than "launch". One file per view kind, overwritten,
   so the directory does not grow inside the user's project.
2. **Removed: the whole `tetravox` tag** — `GET /api/tetravox`, `GET /api/tetravox/updates`,
   `POST /api/tetravox/{policy,install,activate}`, `DELETE /api/tetravox/{version}` — and the
   schemas `TetravoxRelease`, `TetravoxState`, `TetravoxUpdate`, `TetravoxUpdates`,
   `TetravoxUpdateOutcome`, `ProtocolRange`.
3. **Removed: `/ws/tetravox`** and its one `tetravox.updated` event.
4. **Breaking: `Capabilities.tetravox_embed` is gone**, and with it that key from
   `required`. A capability is what *this runtime* can do; whether a desktop application is
   installed on the user's machine is a fact about the host, answered by the Electron shell
   (`window.tit.viewer.probe`), not by an HTTP route. `contracts/openapi.v0.yaml`'s own
   `Capabilities` was updated in the same commit, since `test_openapi_covers_v0_contract`
   checks the live dump against it.
5. **Relaxed: `contracts/tetravox-viewspec-v2.schema.json`'s `DatasetRef.path`/`absPath`**
   no longer require the `^/api/files/raw/` prefix. That pattern was our own addition, not
   the engine's: a ViewSpec dataset path is a path, and the desktop app opens files rather
   than fetching URLs. The pattern now accepts the URL form, a POSIX absolute path or a
   Windows drive path, and still rejects a bare relative name — the app would resolve one
   beside the scene file, which is not where the data is.

## 2026-09-06 — feat:pipeline-canvas — `PipelineIssue.code` / `.port`

No dataclass changes, so `contracts/schema.json` is untouched.
`contracts/openapi.v1.yaml` / `.json` and `desktop/src/renderer/api/schema.d.ts`
gain two **optional** properties on `PipelineIssue`; every existing reader keeps
working, because `level` and `message` are unchanged and still the only required
fields.

1. **`PipelineIssue.code`** — the stable machine-readable name of the finding,
   one of `empty · duplicate_id · edge_unknown_node · self_edge · bad_output ·
   bad_input · double_bound · cycle · missing_input · unconfigured ·
   unconnected`, defined once in `tit.pipeline.validate.ISSUE_CODES`. The
   Pipeline canvas needs it to tell findings apart *without matching on English*.
   Before it existed the receipt printed every issue as an undifferentiated list,
   so an `unconnected` note ("… is not connected to anything; it will run on its
   own" — which is a legitimate graph, not a fault) read exactly like a blocker,
   and the maintainer's screenshot of the page is a pane of them. With the code,
   the canvas states the independent steps **once** ("3 steps run independently")
   and shows only real errors as errors.
2. **`PipelineIssue.port`** — for the port-shaped findings (`missing_input`,
   `bad_input`, `bad_output`, `double_bound`), which of the five port types the
   finding is about. This is what lets the canvas draw an unbound required input
   as a chip on the node's own card ("needs: subjects") and open that node's
   editor at that field, rather than re-deriving the same fact client-side from
   the config and risking a disagreement with the server that decides Run.

Mirrored in `desktop/tests/mock-server/server.mjs` (its planner is a deliberate
mirror of `tit/pipeline/*`), asserted in `tests/test_pipeline_validate.py` and
`desktop/tests/unit/pipeline-graph.test.ts`.

## 2026-09-06 — feat:viewer-composition — `POST /api/view/open` gains `extras`, `overrides`, `dry_run`; `ViewerOpen` gains `files`, `dry_run`

The Viewer page became a composition panel (VM,
`docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)`), so the request that writes
the scene had to be able to carry what the panel composes. All three request
fields are **optional and additive**, and `tests/test_viewspec_overrides.py`
pins the guarantee that matters: with none of them given, the document this
endpoint returns and writes is *byte-identical* to what it produced before they
existed.

1. **`overrides`** — per-layer `{visible, opacity, colormap, showIn3D,
   showColorbar, contoursIn2D, threshold:{lo,hi}, colorMode, clip}` keyed by
   layer id, plus `layout` (`1x1 · 1+3 · 2x2 · 3d-only`), `camera`
   (`A·P·L·R·S·I`), `radiological` and `background`. Every knob is one the
   engine's own `ViewSpec` v2 type already has — the page exposes exactly what
   the server can write, because a control whose value does not reach the file
   is a lie. Values the type would not accept (an unknown layout, an opacity of
   4, a colour name we do not define) are dropped or clamped rather than
   written: a stale saved preset must not produce a scene the app refuses to
   open. `tit/viewspec.py::apply_scene_overrides`.
2. **`extras`** — `t1 · atlas · electrodes · gm_mesh`, the "Also open"
   checkboxes. Each reuses the layer builder the server already trusted for
   that file, and one the view already opens is a no-op rather than a second,
   differently-configured description of the same volume. There is deliberately
   **no electrode-*points* extra**: ViewSpec v2 has no points layer, so the
   page offers the electrode overlay *volume*, which exists.
3. **`dry_run`** — resolve and answer, write nothing. The preview strip needs
   to say what a selection resolves to without leaving a file behind, and
   reusing the real endpoint means the preview and the Open cannot disagree.
4. **`ViewerOpen.files`** (`ViewerSceneFile[]`) — one row per dataset the scene
   references, with its host-facing path and its size on disk. `bytes: null`
   where the file could not be stat'ed: "unknown" and "empty" are different
   answers and only one is a problem.

`contracts/tetravox-viewspec-v2.schema.json` is **unchanged** — nothing here
emits a field it did not already allow.

## 2026-09-06 — feat:pipeline-subjects-source — the cohort is a node, and a wire is gated on readiness

No dataclass changes, so `contracts/schema.json` is untouched. Three additions to
`contracts/openapi.v1.yaml` / `.json` (and `desktop/src/renderer/api/schema.d.ts`), plus
`contracts/pipeline.schema.json`.

1. **`PipelineNode.kind` gains `subjects`**, and it leads the enum. A `subjects` node names the
   cohort in `config.subject_ids`, runs nothing, and is the graph's only source. What it replaces:
   every processing node used to carry its own copy of the subject list *and* be auto-configured
   from the node upstream of it — so one cohort was typed once per node, two nodes in one graph
   could silently disagree about who was in the study, and an edge meant "and also copy that
   node's settings" rather than one named binding. An edge now carries the named port and nothing
   else.
2. **`PipelineKinds` gains `capabilities` and, per kind, `requires`/`produces`** — the readiness
   table from `tit.pipeline.validate.KIND_READINESS`. A wire is legal when the port types match
   **and** every subject reaching the target already has what that kind requires
   (`raw · m2m · leadfield · simulation`). `produces` is what makes a chain work:
   `pre` produces `m2m`, so `Subjects(raw) → Pre → Simulator` is legal while
   `Subjects(raw) → Simulator` is refused with "102, test have no head model".
   Served from the existing `GET /api/pipelines/kinds` rather than a second `/ports` route,
   because it is the same table and two endpoints for one fact is how they drift. The canvas needs
   it client-side to refuse a *drag* — there is no graph to ask the server about yet — while
   `POST /api/pipelines/validate` applies the same table server-side, so the drag-time refusal and
   the receipt are the same sentence.
3. **`PipelineIssue.code` gains `not_ready`** — the subjects reaching a node lack something it
   requires. Its `message` names them.

`POST /api/pipelines/validate` and `/run` now read subject readiness from the same aggregate the
Overview page shows (`GET /api/catalog/overview`), so the canvas and the board a user just looked
at cannot disagree. A project that cannot be read at all falls back to shape-only checking rather
than refusing every wire.

## 2026-09-06 — NB lane — notebooks and kernels: eleven paths, five schemas, one socket

No dataclass changes, so `contracts/schema.json` is untouched by this entry.
`contracts/openapi.v1.yaml` was hand-edited and `contracts/openapi.v1.json` /
`desktop/src/renderer/api/schema.d.ts` regenerated from it.

1. **`/api/notebooks` (GET, POST) and `/api/notebooks/{name}` (GET, PUT, DELETE)** —
   the `.ipynb` files under `<project>/code/ti-toolbox/notebooks`. New schemas
   `NotebookEntry`, `NotebookList`, `Notebook`. `Notebook.content` is a bare
   `object` with `additionalProperties: true` and stays that way: the `.ipynb`
   *is* the document, and typing its keys here would be this server deciding
   which parts of a format it does not own may survive a save. `POST` doubles as
   the import path — "Import .ipynb" in the UI and the pipeline canvas saving its
   export are the same call, a name and a document — so it declares a `409` for a
   name already taken.
2. **`/api/kernels` (GET, POST), `/api/kernels/{kernel_id}` (DELETE) and
   `/api/kernels/{kernel_id}/{interrupt,restart}` (POST)** — notebook execution
   lifecycle. New schemas `Kernel`, `KernelList`. `KernelList` carries `max` and
   `idleTimeoutSeconds` rather than leaving the client to hard-code them: the
   limits are the server's, and a page that renders "1 of 2 kernels" must be
   reading the server's number. `POST /api/kernels` declares `429`
   (`too-many-kernels`) and `501` (`no-jupyter-client` / `no-kernelspec`) because
   both are states a correctly-built container can be in.
3. **`WS /ws/kernels/{kernel_id}`** — one kernel's traffic; `execute` /
   `interrupt` / `restart` down, `ready` / `status` / `input` / `output` /
   `clear` / `reply` / `fatal` up. Declared in `app.py`'s `_custom_openapi`
   alongside `/ws/system` and `/ws/jobs` (FastAPI cannot describe a WS route) and
   exempt from `contracts_check` like the others. The message shape is SUNA's
   kernel-bridge protocol verbatim, and an `output` payload is an nbformat output
   verbatim — which is precisely why nothing translates between the live kernel
   and the file the `notebooks` paths above read and write.

## 2026-09-07 — merge of `origin/main` @ `b5eb63c3` (v2.5.0) — `channels` leaves two configs, four fields arrive

Generated-schema change only: `contracts/openapi.v1.yaml` is untouched, and every affected
property is under an `x-tit-config` placeholder, so `schema.json` / `openapi.v1.json` /
`schema.d.ts` were regenerated from the dataclasses (`dev/build_schema.py`,
`dev/build_contract.py`, `npm run gen:api`) rather than hand-edited.

**Removed**

1. **`Montage.channels`** and **`MExConfig.channels`** (`list[tuple[list[int], list[int]]] | None`)
   — the Lee-2022 shared-carrier grouping. `main` removed it from the science core in `7a5ee2dd`
   ("Remove Lee-2022 carrier wiring: mTI is always positional (channels->carriers)"), `d4706e5a`
   and `b19a1c26`: mTI is always positional, `electrode_pairs` two at a time, so one FEM field is
   one carrier and the grouping could only ever be the identity. Both were optional and defaulted
   to `null`, so an old config that still carries the key is now rejected by
   `deserialize_config` as an unknown field rather than silently ignored — deliberate, because a
   config that *set* it meant a montage the toolbox will not simulate. The desktop app's
   "Carrier wiring" select is removed in the same series (`f03f9363`).

**Added** (all with server-side defaults, from main's ex/mex work)

2. **`ExConfig.n_jobs`**, **`MExConfig.n_jobs`** (`int`, default `-1`) — worker processes
   evaluating candidates in parallel (`b66a5389`). Results and CSV ordering do not depend on it.
3. **`ExConfig.symmetric_bucket`** (`bool`, default `false`),
   **`ExConfig.symmetry_eeg_csv`** (`str | null`, default `null`),
   **`ExConfig.symmetry_pairing`** (`str`, default `"within_pairs"`) — left/right mirrored bucket
   search for the two-pair Ex path (`230aa10a`); `MExConfig` already declared its equivalents.
   The Optimizer page has no control for the Ex ones yet and sends the defaults —
   `docs/dev/RELEASE.md` §B.

`dev/contracts_check.py`: OK — 10 operations and 9 schemas of `openapi.v0.yaml` present in the
server dump.

## 2026-09-07 — chore:contracts — one hand-written contract, `generated/` outputs, live drift check

No schema changed. This is a **file-layout and gate change**; every path, method and property is
byte-identical to the previous entry's state apart from the `openapi.yaml` `info.description`
rewrite noted below.

### Renamed

| Was | Is |
|---|---|
| `contracts/openapi.v1.yaml` | `contracts/openapi.yaml` |
| `contracts/schema.json` | `contracts/generated/config.schema.json` |
| `contracts/openapi.v1.json` | `contracts/generated/openapi.json` |
| `contracts/SCHEMA-CHANGES.md` | `contracts/CHANGES.md` |

### Deleted

- **`contracts/openapi.json`** — the committed dump of the running server. `dev/contracts_check.py`
  now builds the FastAPI app in-process and takes its OpenAPI document directly, so there is no
  checked-in copy to go stale. Nothing referenced the file except the checker's own default.
- **`contracts/openapi.v0.yaml`** — the Phase-0 walking-skeleton contract, every path of which was
  already carried unchanged into the v1 document. It was the checker's default first argument, so
  the gate had been verifying only the 10-operation skeleton subset; it now verifies the whole
  contract (see below). Its three references were repointed:
  `desktop/src/renderer/api/client.ts`, `dev/contracts_check.py`, `tit/server/schemas.py`.

`contracts/tetravox-viewspec-v2.schema.json` **keeps its name**: it is host-facing and its filename
is its public `$id`.

### The contract's own `info.description`

Rewritten to drop the "every path from `openapi.v0.yaml` is carried unchanged" framing, which no
longer names a file that exists. No behavioural claim changed. Contract `info.version` stays
`1.0.0` — the shape did not change, and the version now lives only there, never in a filename.

### One regeneration command

`npm run gen` (in `desktop/`) = `python3 dev/build_contracts.py` + `openapi-typescript`. The new
`dev/build_contracts.py` runs `build_schema.py` then `build_contract.py` in order, and installs the
test suite's own dependency mocks when SimNIBS/`bpy`/`trimesh` are absent, so it works on a plain
host as well as in the container. `dev/build_contract.py` gained `--check`; its default output is
now `contracts/generated/openapi.json` rather than the input's suffix swapped to `.json`.

### The gate now checks more

`dev/contracts_check.py` regenerates into a temp dir and diffs `contracts/generated/*` and
`desktop/src/renderer/api/schema.d.ts` before it checks anything else, then checks live coverage.

Pointing it at the full contract raised coverage from **10 operations / 9 schemas** to
**104 operations / 115 schemas**, which surfaced pre-existing contract-vs-code differences that
the v0 subset never reached. They are recorded in `_KNOWN_FINDINGS` in `dev/contracts_check.py`,
printed on every run, and the gate fails if one of them stops occurring (so the list cannot rot):

1. **`Overview*.reason`** — the contract declares `string` required; the server returns
   `str | None`. A client trusting the contract can be handed `null`. (4 findings)
2. **`PlanJob.kind`, `LockConflict.kind`** — the contract declares the 17-value `JobKind` enum;
   the server types the field as a bare `str`, so the live document carries no enum there.
   (6 findings)
3. **`POST /api/system/terminate` 204** and **`POST /api/pipelines/export` 501** — declared in the
   contract, not described by the route. (2 findings)

Separately, 232 warnings (not failures) record routes the server types as bare `dict`/`list`, for
which FastAPI registers no model and there is nothing to compare the contract's shape against.
This was already tolerated for inline response schemas; the same tolerance now applies to the
by-name component check, so the 56 named models in that category are warnings rather than
unfixable failures.

### Also

- `tests/conftest.py` gained `scipy.ndimage` and `scipy.stats` to `_MOCK_PACKAGES`. Three test
  modules each carried a private `sys.modules.setdefault` fallback for exactly these two; the
  shared list is now sufficient on its own (the local fallbacks are harmless no-ops).
- `tit/config_io.py` docstrings cited `Montage.channels` and `MExConfig.channels`, both removed in
  the v2.5.0 merge; they now cite `Montage.electrode_pairs` and `ExConfig.roi_names`.

## 2026-09-07 — the twelve known findings, fixed at the cause

`_KNOWN_FINDINGS` in `dev/contracts_check.py` is now **empty**, and the gate's
`contracts_check: 0 known open finding(s)` is a fact rather than a budget. Each of the three
groups the entry above opened turned out to be wrong on a different side:

1. **`Overview*.reason` — the contract was wrong, in a way that said nothing.** It spelled
   nullability as OpenAPI **3.0**'s `nullable: true`, inside a document whose first line is
   `openapi: 3.1.0`. `nullable` is not a keyword in 3.1 — it was replaced by a type union — so the
   contract was silently claiming a non-null `string` while the server correctly returned
   `str | None`. Now `type: [string, "null"]`. No server change; nothing on the wire moved.
   (4 findings)

2. **`PlanJob.kind`, `LockConflict.kind` — the server was wrong.** Both were bare `str`, which
   dumps no enum. `tit/jobs/spec.py` gained `JobKind`, a `Literal` of the contract's 17 values,
   asserted at import to equal `CONTRACT_JOB_KINDS` so the two spellings of one enum cannot drift;
   `tit/server/routes/plan.py` types both fields with it. (6 findings)

3. **`POST /api/system/terminate` — the contract was wrong; `POST /api/pipelines/export` — the
   route was.** Terminate has always answered `200` with `{pid, terminated}` (the desktop's Host
   tab reads only `response.ok`); the contract claimed a bodiless `204`, and now describes the
   body that ships. Export really does raise `501` when `nbformat` is absent, and the route now
   declares that response instead of leaving it undocumented. (2 findings)

**Warnings: 232 → 222.** `GET`/`PUT /api/settings` and `POST /api/system/terminate` — three routes
the desktop calls — now return named Pydantic models (`Settings`, `Telemetry`, `Terminated`)
instead of bare `dict[str, Any]`, so the contract's shape for them is checked rather than assumed.
The rest remain warnings: they are routes whose response is genuinely a pass-through document.

## 2026-09-07 — fix(jobs) — a report is an attachment of its job, never a job of its own

No schema changed. This is a **behaviour change plus one description**, recorded here because it
changes what `POST /api/plan/pre` and `POST /api/jobs/groups` return for the same request.

Maintainer, on a Pre-processing plan with only "Convert DICOM to NIfTI" ticked for one subject
(the card read `JOBS 2 · CPUS 2 · MEM 6 GB`, the grid `DICOM | REPORT`, the footer
"2 jobs in this plan"): *"the report itself should not be counted as a job. A report is attached
to a job, it's not itself a job."*

**Root cause: the server.** `tit.jobs.plans.plan_preprocessing` appended a trailing
`kind="report"` `PlannedJob` per subject, so `POST /api/plan/pre` returned it as a real `PlanJob`
row **and** as a `resolved.stages` entry, and `POST /api/jobs/groups` submitted it as a real job
with its own cost, locks, ETA line and plan column. No other kind ever did this.

### Changed

| Was | Is |
| --- | --- |
| `plan_preprocessing` plans `G1..G6` + one `report` job per subject | plans `G1..G6` only |
| `PlanResult.jobs` for a DICOM-only config: 2 rows (`pre`, `report`) | 1 row (`pre`) |
| `PlanCost` for that config: `cpus 2 · mem_gb 6` (two jobs) | one `pre` job's cost |
| `eta.PRE_STAGE_MIN["report"]`, a per-stage ETA line | `eta.PRE_REPORT_MIN`, folded once per subject into the plan's estimate |
| the consolidated report ran as a scheduled `report` job | `JobManager._attach_pre_report` builds it in-process after the subject's last `pre` job succeeds, and records it as a `report` artifact on that job |
| a report-build failure failed a job | logged as a warning; a `report_failed` artifact on the parent job, which stays `succeeded` |

### Also

- `JobGroupRequest.kind`'s description no longer says "G1-G6/report DAG" (`contracts/openapi.yaml`).
- **`JobKind` still carries `report`.** It is in the frozen v1 enum, so it stays, and
  `tit.jobs.kinds.MODULE_FOR_KIND` still maps it to `tit.pre.report` — nothing *plans or submits*
  one any more. A client may still submit one by hand.
- `tit.pre.report.build_report(config, subject_id)` is the extracted, in-process report builder
  `main()` and the manager hook both call.
- The mock server mirrors all of the above (`desktop/tests/mock-server/server.mjs`): no report
  plan row, no report job, and a `pre` job's artifacts now carry its `report.html`.

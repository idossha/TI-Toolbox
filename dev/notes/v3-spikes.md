# v3 spikes — notes

Spike notes for the v3.0.0 plan in `TODO.md` (§5, Phase 0). Each spike records what was run,
where, and what it means for the design. Nothing here is product code.

## Spike (c) — NiiVue as the embedded NIfTI + mesh engine (2026-08-27)

**Question.** Can one WebGL engine in the Electron renderer replace Freeview (volumes) *and*
Gmsh (SimNIBS meshes) so the container needs no X11 at all, with host Gmsh/Freeview only as an
optional "Open with…"?

**Setup.** NiiVue `@niivue/niivue` 0.69.0 (same version vendored in `docs/assets/js/niivue.min.js`),
plain ESM page served by `python -m http.server`, Chromium via Playwright, Apple M2 Max (ANGLE
Metal). Data: Dataset 000 `sub-ernie`, simulation `Simulations/Thalamus` (TI, 2 electrode pairs),
`m2m_ernie`. SimNIBS 4.6.0 inside `idossha/simnibs:v2.4.0` did the mesh exports.

### What the SimNIBS outputs actually contain (read with `simnibs.mesh_io.read_msh`)

| file | nodes | elements | element data | notes |
|---|---|---|---|---|
| `m2m_ernie/ernie.msh` | 847,165 | 4.72 M tets + 1.18 M tris | – | tags 1–10 volumes, 1001–1010 + 1099 surfaces |
| `Thalamus/TI/mesh/Thalamus_TI.msh` | 847,165 | same | `TI_max` per **element** | electrodes already removed (no 1100/1500 tags) |
| `Thalamus/TI/mesh/grey_Thalamus_TI.msh` | 368,762 | 1.34 M **tets** (tag 2 only) | `TI_max` | a GM *volume*, not a surface |
| `Thalamus/TI/mesh/Thalamus_normal.msh` | 491,524 | 983,040 tris (tags 5003/7003) | node data `TI_normal` (all ≥ 0) | central surface; **mesh-only field** |
| `high_Frequency/mesh/ernie_TDCS_1_scalar.msh` | 847k | +electrode/gel tags 101/102, 501/502, 1101/1102, 1501/1502, 2101/2102 | `E`, `magnE` | source of electrode geometry |

Read time for the full mesh: 0.4–1.6 s (page cache warm).

### Server-side export recipe (all `simnibs.mesh_io`, measured)

```python
m = mesh_io.read_msh(".../Thalamus_TI.msh")
nd = m.elmdata[0].elm_data2node_data()      # 38 s on the full 847k-node mesh — do ONCE, cache
m.nodedata = [nd]                           # (elm_data2node_data refuses surface-only meshes)
gm = m.crop_mesh(tags=[1002])               # 0.1 s → 168,952 verts / 335,930 tris, nodedata cropped with it
mesh_io.write_gifti_surface(gm, "gm.surf.gii")          # 5.7 MB
# scalars: write a GIfTI func array (nibabel GiftiDataArray float32) — NOT write_curv, see gotchas
skin = m.crop_mesh(tags=[1005])             # 38,952 verts, 1.3 MB gii
el = hf.crop_mesh(tags=[1101,1102,1501,1502])   # 96 verts — electrode + gel surfaces
central = mesh_io.read_msh(".../Thalamus_normal.msh")   # 491k verts, write_gifti_surface 1.3 s, 16 MB gii
```

Per-surface export after the one-time node interpolation: 0.2–0.6 s. Cache the node-interpolated
mesh (or interpolate only the cropped GM tets + triangles) — 38 s per request is not acceptable.

### What NiiVue did (all verified in the browser, screenshots in the design page)

- 4 volumes in one canvas: `T1.nii.gz` (gray) + `final_tissues.nii.gz` with the SimNIBS LUT as a
  label colormap + `TI_max` (hot, cal 0.08–0.22 V/m, `alphaThreshold`) + `electrode_overlay_subject.nii.gz`
  — 256×256×208 each — loaded in **1.1–1.5 s**; multiplanar + 3D render quadrant; colorbars.
- Click on a slice → `onLocationChange` gives scanner-RAS mm, voxel index and the value of **every
  layer** at that point (`{mm:[-3.7,61.2,25.4], vox:[96,162,169], TI_max: 0.135, final_tissues: 1}`).
  This is the ROI-centre / free-hand-electrode pick-back Freeview never gave us programmatically.
- GM surface (169k verts) with `TI_max` per vertex + translucent skin + electrode surfaces from the
  TDCS mesh: **144–272 ms**. Central surface (491k verts) with `TI_normal`: **379 ms**. JS heap
  after everything: ~190 MB. 15 built-in mesh shaders (Phong, Matcap, Outline, …).
- GM mesh drawn as a contour on the 2D slices (`meshThicknessOn2D`).
- Volume 3D render honours `setClipPlane` (Gmsh-style cutaway of the *volumetric* field).

### Gotchas (each cost real time; keep them)

1. **NiiVue does not read Gmsh `.msh`** (0.69.0: loaders are GII/MZ3/OBJ/STL/PLY/VTK/ASC/…; the
   "Gmsh" strings in the bundle are inside a WASM blob). The server converts with `mesh_io`.
2. **A `name:` load option without a file extension throws** (`getFileExt(imageItem.name || url)`
   → `toUpperCase` of undefined). Either omit `name` or give it an extension.
3. **`.curv` scalars load but do not colour the mesh** (layer registered, colorbar drawn, surface
   stays grey; `isTransparentBelowCalMin=false` path). GIfTI `.func.gii` (or MZ3) scalars colour
   correctly. Export scalars as GIfTI.
4. **Clip planes do not cut meshes.** `clipPlane` is a uniform of the volume ray-cast shaders only.
   Options: a custom mesh fragment shader (`setCustomMeshShader`) with a plane `discard`, or a
   server-side `crop_mesh(nodes=<half-space>)` (sub-second). The 2D slice views already show the
   "field on a cut plane" that Gmsh clipping is used for, via the NIfTI exports.
5. Label maps: `setColormapLabel()` after load + `alphaThreshold = true` (already known from the
   docs-site atlas browser); index 0 must be transparent.
6. Volume-wide `TI_max` percentiles are dominated by scalp (p99 = 0.81 V/m vs GM p99 = 0.17 V/m):
   the ViewSpec must compute thresholds on the GM-masked NIfTI (`grey_*_TI_max.nii.gz`) or the GM
   mesh, not the whole volume.
7. `isDepthPickMesh` (click a mesh in 3D → crosshair) could not be exercised with synthetic events;
   verify with a real pointer in Phase 0 before relying on it. Picking on 2D slices works.
8. `Thalamus_normal.msh` stores `TI_normal` as non-negative — no signed colormap needed for it.

### Verdict

NiiVue covers every Freeview use in `tit/gui` and the "field on GM/WM/central surface + skin +
electrodes" Gmsh use, from one engine, with data the server can produce in < 1 s per surface.
Not covered natively: raw tetrahedral inspection and arbitrary clip planes through surfaces —
both go to "Open with host Gmsh" (the `.opt` sidecar is already written by `tit/tools/gmsh_opt.py`)
or the server-side crop. No X11 library needs to stay in the image for viewing.

### Coordinate-space check (added after review)

`write_gifti_surface(msh, fn)` builds a `cortech.Surface(vertices, faces, "scanner", geometry=None)`
and calls `to_surface_ras()`; with `geometry=None` that is a no-op. Verified on the exports above:
the skin GIfTI bbox is `[-84.4 -92.4 -128.9]..[83.4 136.2 100.0]`, identical to the raw
`m.nodes.node_coord` bbox, and inside the T1 sform world box `[-99.7 -100.8 -143.6]..[107.3 154.2 111.4]`.
So SimNIBS mesh millimetres are T1 scanner RAS and NiiVue's `onLocationChange.mm` (sform of
volume 0) is directly comparable. Never pass a volume `geometry` to `write_gifti_surface` for
viewer exports, or the surface is shifted by c_ras into FreeSurfer surface RAS.

### Design follow-ups raised in review (not spike results)

- `elm_data2node_data()` is SPR smoothing; it hides discontinuities across tissue boundaries. The
  mesh export needs `mode=flat` (split vertices, one value per triangle) next to `mode=smooth`.
- Hidden ViewSpec layers must be URLs only, fetched on toggle: each 256³ float volume is ~64 MB of
  R32F texture in NiiVue; Freeview's "load everything with visible=0" pattern does not transfer.
- Compacted label LUTs must return an `id_map`; the readout shows original FreeSurfer ids
  (`SubcorticalROI.label` and the analyzer take original ids).
- Volumetric (GM+WM) mesh ROI analyses have no surface: export boundary faces
  (`Elements.get_outside_faces`) or use `roi_overlay.nii.gz`.
- `saveScene` is canvas resolution; publication figures need an offscreen-scaled render (spike)
  or host `freeview -ss` / Gmsh `Print`.
- The Linux `gmsh` wheel links libX11: removing X11 client libs and `pip uninstall gmsh` go together.

## Spike (a) — fastapi/uvicorn in the image + host reachability (2026-08-27)

**Question.** Do `fastapi` + `uvicorn[standard]` install cleanly into `idossha/simnibs:v2.4.0`
(Python 3.11, numpy 1.26.4 pinned), and is a server bound to `0.0.0.0` inside the container
reachable from the host through `-p 127.0.0.1:8765:8765` for REST *and* WebSocket?

**Setup.** Throwaway container `tit-v3-spike` (image `idossha/simnibs:v2.4.0`, linux/amd64 run
under emulation on an Apple-silicon host), worktree mounted at `/ti-toolbox` with
`PYTHONPATH=/ti-toolbox` (the image's site-packages holds a stale `tit`; verified
`tit.__file__ == /ti-toolbox/tit/__init__.py`), Dataset 000 at `/mnt/000`,
`simnibs_python -m tit.server --project /mnt/000 --host 0.0.0.0 --port 8765`.

**pip resolution** (`simnibs_python -m pip install fastapi 'uvicorn[standard]' pyyaml psutil`):
`fastapi 0.141.1`, `starlette 1.6.0`, `pydantic 2.13.4`, `pydantic-core 2.46.4` (cp311 wheel),
`uvicorn 0.52.4`, `uvloop 0.22.1`, `httptools 0.8.0`, `websockets 17.1`, `watchfiles 1.2.0`,
`anyio 4.12.1` (already present), `h11 0.16.0`. `pyyaml 6.0.3` and `psutil 7.2.2` were already
in the image. **No conflict with numpy 1.26.4 / Python 3.11** — none of these depend on numpy.
`pip check` only reports the image's pre-existing state (`simnibs 4.6.0 requires numpy>=2`,
`samseg`, `python-mumps`, missing `tbb`, `bpy 5.0.1 not supported on this platform`); nothing new.

**Host-side results** (all from macOS, `curl`/Node 25 against `127.0.0.1:8765`):

| call | result |
|---|---|
| `GET /api/health` (no auth) | 200 `{"status":"ok","uptime_s":17.192}` |
| `GET /api/version` w/o token | 401 `{"detail":"Unauthorized"}` |
| `GET /api/version` Bearer | 200 `{"tit_version":"2.4.0","server_api":"v0","schema_hash":"","python":"3.11.14","simnibs":"4.6.0"}` |
| `GET /api/capabilities` | `{"docker_socket":false,"freesurfer":false,"bpy":true,"x11_display":false,"gmsh":true,"freeview":false}` (spike container has no socket/X11 mounts) |
| `GET /api/project` | `{"container_path":"/mnt/000","host_path":null,"name":"000"}` |
| `GET /api/catalog/subjects` | 3 subjects (`101`, `ernie`, `MNI152`) with raw/freesurfer/m2m flags + `n_simulations` (6 for ernie) |
| `GET /api/catalog/simulations?subject=ernie` | 6 simulations, all `has_ti:true, has_mti:false`, container paths |
| `GET /api/system` | cpu/mem/disk + 1 relevant process (the server itself, RSS 80 MB) |
| `GET /auth/session?token=spike` | 303 → `/`, `set-cookie: tit_session=spike; HttpOnly; Path=/; SameSite=strict` |
| `Host: evil.example` | 400 `Invalid host header` (TrustedHost) |
| `GET /` (no bundle yet) | 200 built-in status page with the CSP header |
| WS `?token=` (Node global `WebSocket`) | open 52 ms, msg 1 @54 ms, msg 2 @2055 ms |
| WS with `Cookie: tit_session=` | open 8 ms, two messages 2 s apart |
| WS without auth / with `Origin: http://evil.example` | handshake refused (close 1006 on the client; server closes 4401 / 4403 before accept) |
| `--dump-openapi` → `contracts/openapi.json` | `dev/contracts_check.py`: OK — 9 operations, 9 schemas of `openapi.v0.yaml` present |

**Verdict.** The chosen bridge (§2.1) and origin model (§2.8) work as designed on macOS Docker
Desktop: `0.0.0.0` bind inside + `127.0.0.1` publish outside, cookie *and* bearer auth, WS
through the publish. Windows (Docker Desktop/WSL2) and Linux Engine reachability still to be
asserted (same command; expected identical). The server process idles at ~80 MB RSS before any
`tit.sim`/`tit.opt` import (see spike (b)).

## Spike (b) — import timings (2026-08-27)

Fresh `simnibs_python` process per module inside `tit-v3-spike` (same emulated-amd64 container
as above, so absolute numbers are pessimistic — native Linux will be faster; the *ratios* are what
matter). Wall time of the `import`, `VmRSS` from `/proc/self/status` right after it, number of
entries in `sys.modules`. Bare interpreter: 14 MB RSS. Two runs each (warm page cache).

| import | wall (s) | RSS (MB) | sys.modules |
|---|---|---|---|
| `tit` | 0.05 | 25 | 92 |
| `tit.sim` | 3.1–3.3 | 388 | 2361 |
| `tit.opt` | 3.2–3.3 | 388 | 2376 |
| `tit.analyzer` | 0.7 | 127 | 896 |
| `tit.stats` | 0.9 | 128 | 1025 |
| `tit.pre` | 0.4 | 75 | 522 |
| all five in one process | 3.1 | 390 | 2418 |
| `import simnibs` alone | 3.4 | 387 | – |

**Reading.** Essentially the whole cost of `tit.sim` / `tit.opt` *is* `import simnibs`
(3.4 s, ~370 MB); `tit.analyzer` / `tit.stats` / `tit.pre` do not pull SimNIBS today. Holding all
subpackages in the server costs one SimNIBS import (~3 s once at startup, ~390 MB resident) —
acceptable for a long-lived process, and it is exactly the per-exec cost the docker-exec-per-query
alternative (§2.1 column A) would pay on every catalog call. For ADR #13 (PEP 562 lazy imports):
the Phase-0 skeleton imports only `tit.paths` (25 MB, 50 ms) and starts in well under a second;
Phase 1 should keep SimNIBS out of the request path (import `tit.sim`/`tit.opt` lazily or in
the worker `ProcessPoolExecutor`) rather than at server import time, so `/api/health` is up
immediately after `compose up`.

## Note — host pytest suite speed regression: unrelated-thread joins, not test count (2026-08-27)

**Symptom.** The host suite (`python3 -m pytest -q`, macOS, 2840 tests) crept from ~30 s to ~87 s
as `tit/jobs/**` and `tit/telemetry.py` landed, with no proportional growth in test count.

**Root cause.** `tests/test_telemetry.py` waited for "fire-and-forget telemetry threads" by
joining *every alive daemon thread in the process* (`for t in threading.enumerate(): if
t.daemon: t.join(timeout=2)`), at six call sites. Once other test modules started a real
`JobManager` (via `tit.jobs.bootstrap.get_manager()`) without tearing it down, its long-lived
poll thread — plus AnyIO worker threads — stayed alive for the rest of the process. Every one of
those six join loops then burned a full 2 s timeout per unrelated thread it found, on every test
in the file: ~48 s of dead waiting, all of it joining threads `tit.telemetry` never created.

**Compounding bug, same file.** `tit.constants.GA4_MEASUREMENT_ID`/`GA4_API_SECRET` are real,
live GA4 credentials, not placeholders, so several tests that call `set_enabled(True)` without
first patching `tit.telemetry._send_ga4` were making real HTTPS POSTs to production Google
Analytics on every host run.

**Fix (in `tests/conftest.py`, `tests/test_telemetry.py`, `tit/telemetry.py`).**
1. `tit.telemetry.track_event`'s sender thread is now named `"tit-telemetry"`, so tests can
   join *only* telemetry threads instead of every daemon thread.
2. `tests/conftest.py` sets `TIT_NO_TELEMETRY=1` by default and, as a second independent layer,
   patches `tit.telemetry._send_ga4` to a no-op for the whole session — no test can reach the
   real GA4 endpoint regardless of what it does to the config or the env var.
3. `tests/conftest.py` adds module- and session-scoped fixtures that shut down any
   `tit.jobs.bootstrap` `JobManager` a test created, so its poll thread never leaks into later
   modules.

**Result.** `python3 -m pytest -q --durations=10`: **~26 s** (was ~87 s), same 2840 passed /
17 skipped, identical assertions. A `urllib.request.urlopen` interceptor run across the full
suite confirms **zero** calls to `google-analytics.com`.

# v3 scene panes + one subject grammar + a layout pass (plan of record, 2026-09-04)

Maintainer's brief, verbatim: *"for the 3d panes, can you just create a slim scene management? to load exactly what
we need? it should be available for the simulator, optimizer, analyzer. also, 1. try to come up with a consistent
schema/UI for the subject selection in the tabs so users are familiar with a consistent approach. then, position all
UI elements in a way that makes sense in terms of UI/UX."*

Supersedes `dev/notes/v3-3d-panes-plan.md`, whose answer was "wait for Tetravox protocol 2". The upstream ask stays
valid for the **Viewer** (results, volumes, colormaps, slices); it is no longer on the critical path for these three
pages. House rules as always (`/Users/idohaber/00_development/agentic-rules/docs/PRINCIPLES.md`): every rule names the
failure it prevents; an agent judges numbers, not pictures; GUI tests run hidden; nothing is committed unless asked.

## 0. Measurements this plan is built on (taken 2026-09-04 on Dataset 000, sub-ernie)

| Fact | Value | Consequence |
|---|---|---|
| `m2m_ernie/ernie.msh` | 184 MB, 847 165 nodes, 5 899 838 elements, 1.7 s to read in the container | Never sent to the browser; the server extracts. |
| Skin surface (tag 1005) | 77 032 triangles | Fits a browser as-is; decimation optional. |
| Grey matter (tag 1002) | 335 930 triangles | Above the pane's budget; needs a target of ≤ 150 k. |
| EEG nets | `m2m/eeg_positions/*.csv`, `Electrode,x,y,z,name` rows; catalog already lists nets + electrode names | Electrode positions are cheap and exact. |
| Atlases | `GET /api/catalog/atlases` gives per-hemisphere `.annot` paths (DK40, HCP_MMP1, a2009s) | Region picking works off the annot + a surface. |
| Label volume | `m2m/segmentation/labeling.nii.gz` + `labeling_LUT.txt` | NIfTI-side region picking without new science. |

## 1. Decisions — the slim scene

| # | Decision | Failure it prevents |
|---|---|---|
| S1 | **The scene is a form control, not a viewer.** It exists so a user can *choose*: electrodes (Simulator), a target (Optimizer), a verified ROI (Analyzer). Non-goals, written into the module header: no volume slicing, no colormaps, no field overlays, no publication screenshots, no layer tree. Those are Tetravox's, on the Viewer page and in the Results preview. | Rebuilding Tetravox inside TI-Toolbox, which the microservice rule exists to prevent. |
| S2 | **The server builds exactly what a pane needs, and caches it.** New `tit/scene/` + `GET /api/scene/*` (§2) extract skin/GM surfaces, electrode positions, per-vertex atlas labels and the label volume's legend, cached under `derivatives/ti-toolbox/scene_cache/sub-<id>/` keyed by a fingerprint of the source files. First request builds (measured, reported in a response header); later requests are a file read. | A 184 MB mesh crossing the wire, or the browser doing neuroanatomy. |
| S3 | **One wire format, documented, no new dependency** (§2.3, `TVSC1`): a 32-byte header then `float32` positions, `uint32` indices, optional `uint16` per-vertex label. Budgets: any single surface ≤ 3 MB and ≤ 150 k triangles after simplification; the manifest carries the true counts. | glTF/three.js pulled in for four primitives. |
| S4 | **One small renderer**, `desktop/src/renderer/scene/`, WebGL2, no runtime dependency, ~700 lines: orbit/zoom/pan, two translucent surfaces, point markers, region highlight, colour-ID picking. Pure modules (camera math, pick mapping, selection reducer) are unit-tested; the canvas exposes a state hook so e2e asserts state, never pixels. | An untestable blob, and a second general-purpose viewer. |
| S5 | **One component, three modes.** `<ScenePane mode="montage" | "target" | "inspect">` serves Simulator, Optimizer and Analyzer; the mode decides what is pickable and what a pick means. Same camera presets, same legend, same keyboard on all three. | Three divergent 3D panes. |
| S6 | **The pane is never the only way.** Every selection it makes is also reachable in the form, both directions stay in sync, and with no WebGL2 (or no head model yet) the pane shows one readable line and the page still works. | A page that becomes unusable on a machine with a blocklisted driver. |
| S7 | **Placement**: the right pane keeps **Plan** on top; its lower half is tabbed **Terminal · Scene** — Scene by default while configuring, Terminal from the moment a job of that page's kind is running. The pane's existing expand control (U13) gives the scene the full content width for real inspection. | A 3D view squeezed into 360 px, or a terminal that disappears when a run starts. |
| S8 | **Budget, measured per page**: first paint of the pane ≤ 2.5 s on a warm cache, ≤ 12 s cold (build included), interaction ≥ 30 fps at 1280×800 while orbiting, and the pane never pushes Run or the plan off the first screen. | "It looks smooth" as a gate. |

## 2. The scene contract (frozen here so lanes build against it in parallel)

### 2.1 Routes (`tit/server/routes/scene.py`, auth like every other route)
```
GET /api/scene/manifest?subject=<id>
    → { subject, space:"subject-ras", bbox:[x0,y0,z0,x1,y1,z1],
        parts:[ {id:"skin"|"gm", kind:"surface", triangles, vertices, bytes, fingerprint, url} ],
        nets:[ {name:"EEG10-10_UI_Jurak_2007.csv", electrodes:75, url} ],
        atlases:[ {id:"DK40", hemispheres:["lh","rh"], regions:N, url} ],
        volumes:[ {id:"labeling", url, legend_url} ],
        cache:{ state:"ready"|"building", built_ms } }
GET /api/scene/surface?subject=<id>&part=skin|gm        → TVSC1 binary (ETag, Cache-Control)
GET /api/scene/electrodes?subject=<id>&net=<file.csv>   → { net, electrodes:[{name, world:[x,y,z]}] }
GET /api/scene/regions?subject=<id>&atlas=DK40          → { atlas, legend:[{id,name,color}], url }  + TVSC1 labels aligned to part "gm"
GET /api/scene/volume-legend?subject=<id>&id=labeling   → { entries:[{id,name,color}] }
```
Every response is jailed to the project, like `routes/files.py`. A build takes a per-subject lock; two requests never
build the same asset twice. `X-Scene-Build-Ms` reports the build cost; `cache.state:"building"` is answered with 202
and a `Retry-After` rather than a held connection over ~10 s.

### 2.2 Cache
`derivatives/ti-toolbox/scene_cache/sub-<id>/<part>.<fingerprint>.tvsc` (+ `.json` sidecars), fingerprint = size+mtime
of every source file that fed it. Stale entries are deleted on write. The directory is listed in `.bidsignore` the way
`code/ti-toolbox/jobs/` is.

### 2.3 `TVSC1` binary
```
offset size  field
0      4     magic "TVSC"
4      4     u32 version = 1
8      4     u32 vertexCount
12     4     u32 indexCount          (0 for a labels-only payload)
16     4     u32 flags               bit0 = per-vertex u16 labels follow
20     12    reserved (zero)
32     12*V  float32 positions, world-RAS mm, x y z
…      4*I   uint32 indices          (triangles)
…      2*V   uint16 labels           when flags bit0; padded to a 4-byte boundary
```
Normals are computed in the browser. One test in each language reads a fixture the other wrote.

### 2.4 What each mode does
| Mode | Page | Shows | A pick means |
|---|---|---|---|
| `montage` | Simulator | skin (translucent) + GM, electrodes of the selected net, selected pairs coloured per channel | toggle that electrode into the current pair slot |
| `target` | Optimizer | skin + GM, atlas regions (or the label volume) shaded, current ROI highlighted, non-ROI in a second colour | add/remove that region, or set a sphere centre |
| `inspect` | Analyzer | skin + GM, the analysis ROI (sphere / atlas region / cortical) drawn where it will be measured | nothing (read-only), except the sphere centre when the form is in sphere mode |

## 3. Decisions — one subject grammar

Today four pages solve the same problem four ways: Pre-processing has a readiness table with checkboxes, Simulator a
collapsed summary opening a multi-select, Optimizer a `Field`+MultiSelect with its own blocked reasons, Analyzer a
third variant. A user learns the control three times.

| # | Decision | Failure it prevents |
|---|---|---|
| J1 | **One component**, `pages/_shared/subjects/SubjectsField.tsx`, with one grammar: a one-line summary (`ernie` / `3 subjects · 101, ernie, MNI152`), a `Change subjects…` disclosure, then a compact table — filter, select-all, one row per subject, readiness columns supplied by the page, a per-row reason when a subject cannot be used. | Three vocabularies for one idea. |
| J2 | **Always the first Tier-1 section**, titled `Subjects`, on Pre-processing, Simulator, Optimizer, Analyzer and every panel that takes subjects. Same keyboard, same empty state, same "why is this disabled" copy. | A control that moves between pages. |
| J3 | **Readiness is a prop, not a fork**: `columns` (Pre-processing's RAW/FS/M2M/DWI is the general case) and `eligibility(subject) → {ok, reason}` (Optimizer's missing leadfield, Analyzer's missing simulation, Simulator's missing m2m). The reason text is what the Run button shows when it is disabled. | Each page inventing its own blocked-state wording. |
| J4 | **Selection semantics are stated once per page** in the summary line: "one job per subject" (Simulator, Optimizer, Pre-processing) or "one job over all subjects" (group analyses, stats). | A user guessing whether three subjects means three runs or one. |

Measured acceptance: choosing two subjects yields two plan rows and a payload carrying both ids on every page that
says "one job per subject"; the component renders identically (same DOM shape, same testids) on all five pages; the
existing `real` specs still pass.

## 4. Decisions — the layout pass

| # | Decision | Failure it prevents |
|---|---|---|
| L1 | **One skeleton for every run page**: Subjects → the page's Tier-1 decisions (what will run) → collapsible detail sections (how) → action bar; right pane Plan over tabbed Terminal · Scene. A page may add sections, never reorder the skeleton. | Four pages with four reading orders. |
| L2 | **Tier-1 is what changes the science**: subject set, method/mode, target/montage, net, output name. Everything else (electrode geometry, conductivity, solver knobs, existing-output policy) is a collapsed section with a summary line. | A first screen full of defaults. |
| L3 | **The action bar is the only place a run starts**, and it always shows: the digest of what will run, the blocked reason when disabled, the Run control. | Two Run buttons, or a disabled button with no explanation. |
| L4 | **Nothing overlaps.** The sticky action bar reserves its own height in the scrollable pane (the defect lane UC found and could not fix from its own files). Every interactive element is reachable at 1280×800. | A control permanently under the action bar. |
| L5 | **Numbers**: dead-space ratio ≤ 45 % on each run page's populated state at 1280×800 and 1440×900 in both themes; every Tier-1 control on the first screen; no horizontal scrolling anywhere but a table's own container. | A layout pass judged by feel. |

## 5. Lanes

Phase 1 — parallel:
| Lane | Model | Owns | Delivers |
|---|---|---|---|
| **SCA scene service** | Opus | `tit/scene/**`, `tit/server/routes/scene.py`, `contracts/openapi.v1.yaml` (additive), `tests/test_scene*.py`, `.bidsignore` handling | §2 in full, cache, budgets met or the shortfall recorded, measured build times for ernie + 101 + MNI152 |
| **SCB scene renderer** | Opus | `desktop/src/renderer/scene/**`, `desktop/tests/unit/scene-*.test.ts`, a gallery entry under `src/renderer/dev/` | §S4: the module, its pure cores, fixtures written from §2.3, an offscreen harness proving it renders and picks |
| **SUB subject grammar** | Opus | `desktop/src/renderer/pages/_shared/subjects/**` and the subject sections of `pages/{preprocess,simulator,optimizer,analyzer}/**` and `pages/panels/**`, their unit/e2e specs | §3, adopted everywhere, existing specs green |

Phase 2 — **SCC panes** (Opus): `pages/simulator/MontagePane.tsx`, `pages/optimizer/TargetPane.tsx`,
`pages/analyzer/TargetPane.tsx`, the right-pane tab host in `pages/_shared/run/**`, two-way form sync, real
verification against the dev container (ernie + 101), `tests/e2e/real/scene-*.spec.ts`.

Phase 3 — **LAY layout pass** (Opus): §4 across the four run pages and the panels, `desktop/DESIGN.md`, the metrics,
and L4's action-bar defect in `ui/Layout.tsx`.

Phase 4 — **CR critic** (Sonnet): re-runs `dev/smoke.sh`, the `real` Playwright project and the gates from
`dev/notes/v3-pipelines/RUNBOOK.md` only, plus the scene budgets; reports, fixes nothing.

Environment note for every lane: the dev container `ti-toolbox-fad740e5-tit-1` now mounts this worktree at
`/ti-toolbox`, runs the server with `--reload --reload-dir /ti-toolbox/tit` (a change under `tit/` is live in ~2 s —
no restart), serves the UI from `/ti-toolbox/desktop/out/renderer` (so `npm run build` is what a `--project=real` run
tests), and its token is generated per container: read it with
`docker inspect ti-toolbox-fad740e5-tit-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep TIT_SERVER_TOKEN`.

## 6. Orchestrator findings during the build (2026-09-04)

**F1 — `pnpm dev` failed because the server was DOWN, not busy (diagnosis corrected 2026-09-04).** The first
reading here blamed GIL starvation by a cold scene build. Measured afterwards, that is wrong and the note is kept so
nobody re-derives it: with sub-101's `gm`/`skin` cache removed, the cold build finished in ~4 s and 60 consecutive
`/api/health` probes during it all answered in under 14 ms (the 202 + `Retry-After` reply returned in 18 ms), and a
reload cycle showed no failed or slow probe either. The actual cause is in lane SCA's own notes: an import-time
assert in an auto-discovered route module **took the shared container down for about four minutes**, and the
maintainer's `pnpm dev` landed in that window. This is inherent to `--reload`: uvicorn restarts the worker on every
save under `/ti-toolbox/tit`, and when the new process cannot import, the server stays down until the file is fixed —
so any lane writing a broken Python file anywhere under `tit/` takes the maintainer's backend with it. Two rules
follow, and lane SCA wrote them up: a route module must do no work at import time, and a lane editing `tit/**` on
the shared container owes a health check after each save. No product change is required; F2 covers the symptom.

**F2 — the attach probe called a busy stack a dead one (fixed by the orchestrator).**
`desktop/src/main/stack.ts` gave an already-running container 10 s to answer `/api/health`, on the premise that a
live stack answers instantly. A container whose server is restarting (or has just crashed on a bad import, F1) needs
longer than that, and giving up costs the developer their whole dev loop. It is now 45 s, overridable with
`TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS`, and the failure text says the container is running and probably busy, names it,
and gives the `docker logs` command. Verified: attach in 70 ms on a warm server.

## 7. Final state (2026-09-04, after the fix and cleanup rounds)

Delivered: the scene panes (§1, §2), one subject grammar (§3), the layout pass (§4), then two rounds closing what
those rounds found. Combined gate on the merged tree, run by the orchestrator: host pytest **3519 passed**, desktop
typecheck clean, lint **0 errors** (3 pre-existing warnings), vitest **909 passed**, plain `npm run build` with
**0** test-hook and **0** gallery strings in the bundle, container serving that exact bundle, health 200, and a real
end-to-end subset (preprocess, ex, analyzer) **5 passed** offscreen with no window on screen. Earlier in the same
sequence CR2 re-verified all eleven fix-round claims independently and ran Level A 21/21, Level B 27/27 and the
default suite 129 passed twice; CL1/CL2 then took the default suite to 135 passed.

Corrections worth keeping, because each was a plausible wrong answer someone would re-derive:
- The `pnpm dev` failure was a lane's broken import under `--reload`, not GIL starvation (§6, F1).
- The pick bug was not a 20 mm edge case: on real anatomy the culled pick named a surface behind the visible one at
  **399/400** sampled pixels (median 17.6 mm, max 154.4 mm), because the served `gm` was wound inward everywhere
  (**−1 316 329 mm³**). Both halves are fixed — the renderer draws both faces in the pick pass, and
  `tit/scene/build.py` orients every surface outward (**+1 316 329 mm³**) with a `BUILDER_VERSION` salt so a code
  change invalidates a cache an unchanged mesh would otherwise keep.
- A pick now reports where it landed (world point within **1.086 mm** of an independently solved intersection), so
  the sphere gesture places a real centre (**0.093 mm** / **0.164 mm** error) instead of snapping to a centroid.
- `focus_bbox` (the box above the lowest grey-matter vertex) keeps the neck out of the framing: **34.2 %** of the
  framed height was neck on ernie; head area gains 13–96 % depending on the preset at an expanded pane.

Open, none blocking: `panel-source` sits 0.2 points inside the 45 % dead-space limit (treat 45 % as reached, not as
headroom); `RunWork`'s fill controller and a `fill` subject table both claim the same slack, arbitrated today by
ordering; the mock server still shares its settings store and job registry across spec files (four lanes have now
flagged it, though FIX-C's per-file reset stopped the failures it caused); `dev/contracts_check.py`'s 47 problems are
all "no declared schema" for dict-returning routes and predate this program; the sphere gesture is inert on a subject
with no cortical atlas; `focus_bbox` also trims 7.2 mm of jaw on MNI152.

# TI-Toolbox ↔ Tetravox: integration options

Date: 2026-09-17. Status: research note, not a decision. Nothing here is committed or implemented.
Scope: (a) automatic "smart screenshots" of operations and outputs, (b) other integrations the two
codebases already make cheap. Every claim below was read off the two checkouts
(`/Users/idohaber/01_production/TI-toolbox`, `/Users/idohaber/00_development/tetravox`).

---

## 1. What exists today

1. **TI-Toolbox builds scenes, Tetravox draws them.** `tit/viewspec.py::build_view` →
   `to_tetravox_viewspec` (validated against `contracts/tetravox-viewspec-v2.schema.json`) produces
   layers with colormaps, thresholds, camera and cursor; `finish_spec` resolves percentiles off the
   data (`_resolve_layer_percentile`, `_volume_stats` sidecars).
2. **The scene reaches disk as a real file.** `tit/server/routes/viewers.py::export_scene`
   (`POST /api/view/export`) localises container paths to host paths (`native_scene`,
   `localise_scene_paths`) and atomically writes `<project>/…/<name>.tetravox.json`;
   `viewer_library.py` is the saved-scene catalogue with reference-health checks.
3. **The renderer's only launch path** is `desktop/src/renderer/viewer/native.ts`
   (`exportNativeScene` then `openNativeScene` → `window.tit.openNativeTetravox`), used from the
   Viewer page, `app/openInViewer.ts`, and artifact rows (`app/jobs-rail/artifacts.ts::viewableKind`).
4. **Main owns discovery, install and launch**: `desktop/src/main/tetravoxNative.ts` —
   `TETRAVOX_VERSION = "0.4.0"`, resolution order configured → managed → system → PATH
   (`selectViewer`), SHA512/256-verified download (`downloadViewer`, `feedChecksum`),
   `checkViewerScene` (the `.tetravox.json` must be inside the project), `openNativeViewer` (spawn,
   detached, `--user-data-dir` for the managed copy). IPC in `desktop/src/main/index.ts:666-770`.
5. **Main already knows when a job ends**: `desktop/src/main/jobsNotifier.ts` listens on `/ws/jobs`
   and fires on the first `succeeded`/`failed` per job id. That is the natural snapshot trigger.
6. **Jobs already publish pictures**: `tit/jobs/events.py::emit_artifact(path, kind=…"png")`, and
   `desktop/src/renderer/pages/results/preview/views.tsx` inlines `IMAGE_PREVIEW_KINDS`
   (`png/image/jpg/jpeg`) — a PNG dropped in a job folder shows up with no UI work.
7. **The one automatic picture today is matplotlib**: `tit/roi_confirmation.py`
   (`confirm_roi`/`confirm_rois`, `roi_confirmation.{png,json}`, `TIT_NO_ROI_CONFIRMATION`), called
   from `tit/opt/flex/flex.py:140`, `tit/opt/ex/roi.py:131`, `tit/analyzer/analyzer.py:459`.
8. **Tetravox has a complete headless job runner**: `Tetravox --job job.json --out dir`, actions
   `set | screenshot | sweep | orbit | tween | save-scene | module`, presets `plain`,
   `ti-field-on-t1`, `mesh-tissues-translucent`, `atlas-outline`; `view: "figure"` renders a
   labelled multi-panel plate; `job-result.json` reports files, timings, warnings. Validator:
   `packages/app/src/main/job.ts` (1271 lines, pure); client: `python/tetravox/{job,runner}.py`.
9. **A job never takes focus and never shows a window** (`--job` forces offscreen; `isJobRun()` in
   `packages/app/src/main/index.ts` also exempts it from the single-instance lock, so jobs run in
   parallel with the user's open window). Scene input may be `{path: "study.tetravox.json"}` — i.e.
   exactly what `export_scene` already writes.
10. **The embed is gone.** `packages/embed` has no `src` left (only `node_modules/`,
    `test-results/`); `packages/protocol` survives but is the *dataset-worker* protocol
    (`ARCHITECTURE §6.5`), not an embed API. TI-Toolbox retired it in `docs/dev/DECISIONS.md`
    2026-09-13 ("replace browser embedding with managed native TetraVox") and 2026-09-15 (one
    resolution order, detect-or-download).

**The hard constraint:** Tetravox is a host GPU application. The container that runs `tit` cannot
run it. Anything rendered by Tetravox must be driven from the Electron main process (or by the user
on the host).

---

## 2. Screenshot triggers worth doing

| Trigger | The picture | Actions/presets that produce it today | Missing | TI-Toolbox hook (file::function) | Who runs it |
|---|---|---|---|---|---|
| MNI ROI confirmation (job start) | Subject T1 + subject-space mask, 3 orthogonal slices at the mask centroid | `scene{files:[T1.nii.gz, roi_mask.nii.gz], preset:"plain"}` + `set{cursor}` + one `screenshot{view:"figure", figure:{panels:["axial","coronal","sagittal"], labels:"upper"}}` | Nothing in the schema. But the mask must exist **as a file on the host**; today `_subject_mask` works in a scratch dir (`tit/roi_confirmation.py:63`) | `tit/roi_confirmation.py::confirm_roi` writes the mask + a `*.snapshot-request.json`; `tit/opt/flex/flex.py::_confirm_rois`, `tit/opt/ex/roi.py`, `tit/analyzer/analyzer.py:459` unchanged | Electron main (container writes the request + the matplotlib fallback) |
| Simulation done (`kind: "sim"`) | `TI_max` over T1, axial+coronal+sagittal at the field peak, plus one 3D GM-mesh view | `preset: "ti-field-on-t1"` + `set{cursor:[peak]}` + `screenshot{view:"figure"}`; mesh view via `set{camera:"L"}` + `screenshot{view:"view3d"}` | Nothing. "Cursor at field max" needs no new action — TI-Toolbox already computes peaks and passes explicit RAS mm | `desktop/src/main/jobsNotifier.ts` completion → new `snapshots.ts`; scene from `tit/viewspec.py::build_view(kind="simulation")` | Electron main |
| Flex / Ex / mEx / Recip search done | Best montage: electrode overlay on skin (3D) + field on GM | Electrodes exist as a volume: `tit/viewspec.py::_electrode_overlay_layer` (`electrode_overlay_subject.nii.gz` + its LUT) → `preset:"plain"` layers; `.geo`/`.pos` nets load as point layers | An **electrode glyph/point styling knob in a preset** — there is no `electrodes-on-skin` preset, so the job must hand-write layer patches (workable, just verbose) | optimizer runners' end (`tit/opt/flex/flex.py`, `tit/opt/ex/ex.py`) via `emit_result`; main reacts on job completion | Electron main |
| Analyzer done | ROI outline over the field, one slice at the ROI centroid, colour bar on | `preset:"ti-field-on-t1"` + a mask layer patch + `screenshot{include:{colorbar:true, scaleBar:true}}` | A **mask-outline overlay**: `atlas-outline` outlines a *label volume*; a binary ROI mask works but styling is manual (`set{layer:…, patch:{…outline…}}`) | `tit/analyzer/analyzer.py` end of run | Electron main |
| Leadfield / preprocessing done (`kind: "pre"`) | `final_tissues.nii.gz` / `labeling.nii.gz` over T1 as an atlas outline; optionally a 36-frame orbit of the head mesh | `preset:"atlas-outline"`, `preset:"mesh-tissues-translucent"`, `orbit` | Nothing | `tit/pre` pipeline end; `jobsNotifier` | Electron main |
| Batch / group comparison done | A figure-ready plate per subject, same camera and same scale across subjects | `view:"figure"` + explicit `mmPerPx`/`distance`/`cursor` in `set` | A **shared colour scale across jobs**: every preset reads its window off *its own* data, so N subjects get N different scales. Needs `preset` overrides or an explicit `patch:{scale:{min,mid,max}}` (expressible today — TI-Toolbox must compute the common window; `tit/viewspec.py::_volume_stats` already can) | `tit/stats/`, Results page batch action | Electron main |

Rules that fall straight out of the code and should be kept:

* **A picture never fails a job** — already the rule in `tit/roi_confirmation.py`; extend it to
  "Tetravox absent → one log line, job succeeds."
* The **RAD/NEU badge is never optional** in a Tetravox screenshot (AUTOMATION §2.3), so laterality
  is safe by construction — which a matplotlib panel does not guarantee.
* Container paths ≠ host paths. Every snapshot request must go through
  `tit/server/routes/viewers.py::native_scene`/`_to_host` before main sees it.

---

## 3. Options

### O1 — Headless snapshot pipeline from Electron main (`--job`)
A new `desktop/src/main/snapshots.ts`: on a `/ws/jobs` completion event
(`jobsNotifier.ts`), fetch the job's artifacts, ask the server for the matching ViewSpec
(`GET /api/view` / `POST /api/view/export`), write a job document into the job's derivative
directory, resolve the executable with the existing `nativeViewerStatus()`/`selectViewer()`, spawn
it with `--job job.json --out <jobdir> --quiet` (detached, no focus, offscreen by construction),
read `job-result.json`, and POST the resulting PNG paths back so they land in the job's artifact
list and appear inline on Results. A single Settings toggle "Snapshots" (default on), and the whole
thing is skipped with one log line when no Tetravox is resolved.
*Value:* every run leaves a picture the user did not have to ask for; this is the enabling layer for
O2/O5/O7. *Effort:* M, ~3–4 days (main-process module + server endpoint to register an artifact
after the job ended + tests). *Risk:* an extra GPU process per job (mitigate with a serial queue and
`TETRAVOX_JOB_TIMEOUT_MS`); a stale artifact list after the job record closed. *Tetravox deps:* none.

### O2 — Replace `roi_confirmation.png` with a Tetravox render, keeping matplotlib as the fallback
`tit/roi_confirmation.py` already writes the subject-space mask and the JSON; make it also write
`roi_confirmation.snapshot-request.json` (mask path, T1 path, centroid RAS, title) and keep rendering
the matplotlib PNG exactly as today. When O1's main-process watcher sees the request *and* Tetravox
resolves, it renders `roi_confirmation.png` with a three-panel `view:"figure"` capture and overwrites
the matplotlib one (or writes `roi_confirmation_tetravox.png` and lets Results prefer it). Browser
mode, headless CI and a machine without Tetravox keep the matplotlib picture, so the contract
"the artefact exists in every mode" survives.
*Value:* the confirmation picture becomes the same renderer the user inspects with — same LUT, same
RAD/NEU badge, same conventions; no more "the PNG and the viewer disagree". *Effort:* S, ~1–1.5 days
on top of O1. *Risk:* the mask is currently a scratch image, not a durable host file — it must be
persisted beside the PNG. *Tetravox deps:* none.

### O3 — "Open in Tetravox" deep links carrying full state
Today `openInViewer`/`native.ts` export a ViewSpec and launch; the scene already carries layers,
colormaps, thresholds, cursor and camera (`to_tetravox_viewspec`, `_fit_camera`, `_analysis_cursor`).
What is **not** expressible in the `.tetravox.json` TI-Toolbox writes today: (a) the electrode
*channel colours* the desktop shows in `ui/ChannelLegend.tsx` — electrodes ride along only as a
label volume + LUT (`_electrode_overlay_layer`) or a `.geo` point layer, so per-channel colouring is
a LUT the toolbox would have to synthesise; (b) the ROI **region selection** from the scene pane
(`pages/_shared/scene/model.ts`) — Tetravox has a region panel for label volumes, but the toolbox
sends no "these regions visible, those hidden" block; (c) the measurement tool and any extension
state. Each is a layer-patch problem on the TI-Toolbox side, not a Tetravox gap, except the channel
colours, which want a generated LUT file.
*Value:* one click goes from a run page to exactly the view the user was looking at. *Effort:* M,
~2–3 days. *Risk:* scene size and path localisation for multi-subject scenes (already guarded by
`_refuse_a_scene_that_spans_two_subjects`). *Tetravox deps:* none.

### O4 — "Live link" / watch mode (verdict: not available today)
The wish is: the server rewrites `<job>.tetravox.json` as a job progresses and an open Tetravox
window reloads it. **The code does not support it.** Tetravox's only external control surface is
argv: `app.on('second-instance')` in `packages/app/src/main/index.ts:370` hands argv paths to the
running window, and a `*.tetravox.json` in argv sets `startupScene`. There is no file watcher on a
loaded scene, no IPC/HTTP control port, and `--job` deliberately *bypasses* the single-instance lock
(so a job can never talk to the user's window). TI-Toolbox's own `DECISIONS.md` 2026-09-13 states
"no new live external control channel is introduced", and 2026-09-13 notes Tetravox exposes no query
for unsaved scene state — which is why every open today asks "Replace the open TetraVox scene?".
A *poor-man's* version exists now: re-spawning the executable with the rewritten scene path hands it
over to the running window. That is a re-open, not a live link, and it steals focus and can discard
unsaved work. A real live link is a Tetravox feature (§5.1 below): a scene-file watcher plus a
"reload if unmodified" rule, ~2–3 days in the Tetravox repo plus an architecture decision, because
it crosses the "no live-control bridge" line both projects drew on purpose.
*Verdict:* defer; do O1+O5 instead, which give most of the value with none of the new surface.

### O5 — Figure-ready panels straight from Results
A "Export figure…" action on the Results page (and on a job row) that builds a Tetravox job with
`screenshot{view:"figure", width: 1004, dpi: 300, background:"white", autoTrim:true,
figure:{columns:2, gutterMm:3, labels:"upper"}, include:{crosshair:false, cornerInfo:false,
scaleBar:true}}` — a publication plate with per-panel colour bars, scale bar, letters and the
RAD/NEU badge, at a stated DPI, in one action. The existing `pages/panels/visual-exporter/` is where
this belongs (it already has a preview model). Add a small form: panels, columns, DPI, background,
and whether to also write the `.tetravox.json` (`save-scene` action) so the figure is re-derivable.
*Value:* this is the thing users currently do by hand in a viewer and a graphics editor; it is also
the most visible "our toolbox produces publication output" win. *Effort:* M, ~3 days (needs O1's
spawn plumbing). *Risk:* low; worst case an ugly plate. *Tetravox deps:* none — `view:"figure"` and
`dpi` exist.

### O6 — Revive a limited embed? (verdict: no)
The reasons the embed was retired, from `docs/dev/DECISIONS.md`: 2026-09-13 — the maintainer asked
for native-only viewing and the **removal of a duplicate integration surface**; embedding code was
retired in *both* repos; rendering, scene loading, CLI and batch interfaces are Tetravox's
responsibility. ADR rows 27–29 record the earlier flip-flop (embed restored 2026-09-06, superseded
2026-09-13). On the Tetravox side `packages/embed` now has **no source at all**, and
`packages/protocol` is the worker protocol, not an embed API. So reviving it means re-authoring the
embed bundle, its protocol range and its update policy from scratch — the exact duplicate surface
that was deleted — and TI-Toolbox has since built native WebGL2 panes (`desktop/src/renderer/scene/
glScene.ts`, `pages/_shared/scene/ScenePane.tsx`) that cover the in-app picking job.
**Verdict: do not revive.** The only unmet need the embed served — an inline picture without leaving
the app — is better served by O1's rendered PNGs shown inline on Results.

### O7 — A per-project `.tetravox.json` catalogue that snapshots keep current
`tit/server/routes/viewer_library.py` is already a saved-scene library with reference-health checks.
Make every automatic snapshot also emit its `save-scene` sibling into that library, named after the
job (`sub-101_flex-…_best.tetravox.json`). The result: every PNG on Results has a "open exactly this"
twin, and the project accumulates a browsable set of reproducible views rather than a pile of images.
*Value:* reproducibility — a figure a year later is re-derivable from the scene beside it.
*Effort:* S, ~1 day on top of O1 (one extra action in the job document + a library registration).
*Risk:* library clutter; needs a retention rule. *Tetravox deps:* none (`save-scene` exists).

### O8 — Turntable GIFs for the wiki / docs, generated in batch
`orbit` (36 frames, GIF always written, MP4 when ffmpeg is present, `colors: 32` for a small file)
plus `sweep` make the wiki's static figures animated at essentially zero authoring cost. A script
under `dev/` (host-side, not the container) walks `sub-ernie`'s derivatives and regenerates the
docs assets — the same pattern as the existing "regen example assets from sub-ernie" workflow, and
the same shape as Tetravox's own `examples/capture/showcase.py`.
*Value:* documentation that shows the 3D relationships a slice cannot. *Effort:* S, ~1 day.
*Risk:* asset size in the repo (GIF at 256 colours is ~2 MB; use `colors: 32` + MP4).
*Tetravox deps:* none.

### O9 — Tetravox's extension surface as the home for a TI-Toolbox panel (speculative, listed for completeness)
Tetravox §13 has a real extension API with a manifest-as-schema, a job action
(`{"type":"module", …}`), typed Python wrappers (`python/tetravox/modules/`), and a downloadable
install store — the sEEG contact editor is the worked example. A `tit.montage` extension could let a
user place/nudge electrodes in Tetravox and write the montage CSV back into the project, driven
headlessly from a job too. *Value:* high for electrode work; *Effort:* L, 8–10 days across both
repos; *Risk:* a second place where montages are authored. Park it — mention only so it is not
rediscovered as new.

---

## 4. Recommended first slice

Start with **O1 + O2 as one slice**: the main-process snapshot runner, with the MNI ROI confirmation
as its first and only trigger. It is the smallest change that proves the whole mechanism end to end —
request file, host-path translation, executable resolution, `--job` spawn, `job-result.json`,
artifact registration, inline display on Results — against a picture that already exists, so the
fallback is written and the user-visible behaviour cannot regress. The ROI confirmation is also the
trigger with the highest scientific value per pixel, because it is the one error no later number can
reveal (`tit/roi_confirmation.py`'s own preamble). It needs **zero** Tetravox changes, so it cannot
be blocked by a release in the other repo. Once it is green on Dataset 000 sub-ernie, adding the
simulation, search and analyzer triggers is a table of scene builders, and O5/O7 are one extra action
each in a document that is already being written.

---

## 5. Tetravox changes needed

Only three options need anything at all. In order of how much they need:

**O1/O2/O5/O7/O8 — nothing.** `screenshot` (including `view:"figure"`, `dpi`, `background`,
`autoTrim`, `include`), `set` (`cursor`, `camera`, `mmPerPx`, `annotations`), `sweep`, `orbit` and
`save-scene` are all shipped and validated in `packages/app/src/main/job.ts`. Worth pinning:
TI-Toolbox's `TETRAVOX_VERSION` in `desktop/src/main/tetravoxNative.ts` is **0.4.0**, while the
Tetravox `CHANGELOG.md` is at **0.5.2** — the `--job` surface described here should be re-verified
against 0.4.0 or the baseline bumped before O1 is built.

**Gaps found while building the ROI plate (2026-09-17), against 0.5.2:**

1. **`figure` gives every panel one cursor.** A per-region plate is one A/B/C row per region, each
   row at its own cursor and zoom; `screenshot{view:"figure"}` captures one scene state, so the
   rows cannot be one capture. Worked around by leaving multi-row plates to matplotlib and marking
   the request `"tetravox": false` with the reason in it. *Wanted:* `figure: { rows: [{cursor,
   views:{…}}, …] }`, or a `compose` action that stacks earlier captures.
2. **A label volume cannot mask a volume field** (GAPS C5 again). `tit/figures/roi_plate.py` writes
   `<stem>_field-in-roi.nii` — the field already masked — so the two renderers agree about what
   "in the ROI" means. *Wanted:* `patch: { maskBy: { layer: …, labels: [...] } }` on a volume layer.
3. **A 40 % fill under an opaque outline is still two layers** (GAPS A3). The plate lists its region
   map twice in `scene.files` and patches by index. *Wanted:* `fillOpacity` / `outlineOpacity`.
4. **The colour bar cannot be told its unit** (GAPS A2). The field plate's bar reads
   `ROI FIELD PLATE FIELD-IN-ROI.NII (MM)`; matplotlib's reads `V/m`. *Wanted:* `colorbarUnit`.
5. **`labelColors` and `visibleLabels` do work from a job** and are what make a multi-region plate
   show green and orange rather than the file LUT's blue — worth documenting in AUTOMATION §2.3,
   which today only says `patch` is "a `Partial<Layer>` passed untouched".

**Nice-to-have presets (optional, each ~0.5 day):**
1. `electrodes-on-skin` preset — `packages/app/src/renderer/src/automation/presets.ts` (+ the
   `PRESETS` list and `PresetName` union in `packages/app/src/main/job.ts:29-38`, +
   `docs/AUTOMATION.md` §2.2 table, + `presets.test.ts`): translucent scalp with an electrode point
   /label layer opaque on top, so a montage picture is one preset rather than five layer patches.
2. `mask-on-anatomy` preset — same four files: a binary mask as a coloured outline over grey
   anatomy, which is what every ROI-confirmation and analyzer picture wants. Today it is expressible
   with explicit `set{patch}` calls; a preset just removes the copy-paste.

**O4 (live link) — a real feature, ~2–3 days plus a decision:**
3. A `--watch` / scene-file watcher: `packages/app/src/main/index.ts` (the `startupScene` path and
   the `second-instance` handler) plus a renderer-side reload that refuses when the scene has
   unsaved edits, `docs/ARCHITECTURE.md` §4.6 and a `docs/DECISIONS.md` entry, because it creates
   the external control channel both projects explicitly decided not to have. Recommend against
   until O1 has shipped and the need survives.

**Process note (from the lane plan):** if anything above is implemented in the Tetravox repo, it
goes on a branch (`feat/ti-toolbox-snapshots`) with `docs/AUTOMATION.md`, `docs/ROADMAP.md` and the
validator (`packages/app/src/main/job.ts`) updated in the same commit, and the TI-Toolbox pinned
version bumped afterwards.

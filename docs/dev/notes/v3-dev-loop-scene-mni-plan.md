# v3 auxiliary program: dev loop, Ex scene, labeling islands, MNI switch, Tetravox snapshots

Date: 2026-09-17. Owner: idossha. Executor: Opus sub-agent. Base branch: `main`.
Working branch: `feat/v3-dev-loop-scene-mni` (create from `main`; open one PR per lane or one PR
with lane-sized commits; never `git stash`; never touch `examples/studies/` or the untracked
Glasser labels file).

Read first: `AGENTS.md`, `docs/dev/ARCHITECTURE.md` (§ launch model, § run pages / native panes),
`docs/dev/DECISIONS.md` (2026-09-06 native panes, 2026-09-15 entrypoint model), `docs/dev/TESTING.md`,
`loader.sh`, `dev/loader/loader_dev.sh`, `dev/launch-electron.sh`, `desktop/scripts/dev.ts`,
`desktop/src/renderer/pages/_shared/scene/{ScenePane,TargetPreview}.tsx`,
`tit/server/routes/{scene,target_preview}.py`, `tit/scene/{volume_surfaces,target_preview}.py`,
`tit/opt/ex/roi.py`, `tit/opt/roi_spec.py`, and Tetravox `~/00_development/tetravox/docs/AUTOMATION.md`
plus `python/tetravox/{job,runner}.py`.

Every lane ends with: unit tests (host pytest + `desktop` vitest), the offscreen Playwright e2e lane
touched by the change (never two Playwright runs at once, headless only), a DECISIONS.md entry when a
default or frozen interface changes, and a CHANGELOG entry. Report failures verbatim; do not
narrow scope silently.

## Lane A — one dev loop, desktop by default, GPU/Tetravox preserved

Problem. In v2, `loader_dev.sh` mounted the checkout into the running container and every UI/
functional change was visible immediately, on macOS, Linux and WSL. In v3, `bash loader.sh --dev`
(and the `loader_dev.sh` shim) **silently switches `ui=browser`** (`loader.sh` ~line 71:
`|| [ -n "$repo" ]`), so developers land on `http://127.0.0.1:<port>` in a browser tab, losing the
Electron-only surface: native Tetravox open (`window.tit.openNativeTetravox`), Apple GPU
preprocessing, container GPU probe, file dialogs. Users and developers therefore see different apps.

Target behaviour (the user's requirement): *one experience*. `--dev` changes only where the server
and renderer code comes from; it never changes the UI. Browser is used only when `--browser` is
explicit.

Deliverables.
1. `loader.sh` + `loader.py`/`tit/cli.py`: `--dev` no longer implies browser. Default `ui=desktop`
   unless `--browser`/`--no-open`. `--print-config` stays byte-identical between the two loaders
   (extend the parity test). When `--dev` + desktop: run `dev/launch-electron.sh`; if Electron from
   `desktop/node_modules` is missing, print the exact `npm ci && npm run build` line and **fall
   back to the installed desktop app with `TIT_DEV_REPO_DIR` set** (the app already accepts
   `TIT_STATIC_DIR=/ti-toolbox/desktop/out/renderer` + server reload), rather than the browser.
2. Hot reload in dev-desktop: verify the server `--reload` path picks up `tit/` edits inside the
   container and that renderer edits reach the window. If `desktop/out/renderer` must be rebuilt by
   hand today, wire `desktop/scripts/dev.ts` (`npm run dev`) so a source checkout gets Vite HMR
   inside Electron (ELECTRON_RENDERER_URL) **and** the containerised server with reload. One
   command for developers: `npm run dev` (already the documented entry) and `bash loader.sh --dev`
   must converge on the same window; document which one to use in `docs/dev/ARCHITECTURE.md` and
   `CONTRIBUTING.md`, and delete or reduce any third path.
3. Cross-platform: `loader.sh` must work on macOS (bash 3.2), Linux, and WSL2 (Docker Desktop
   Windows backend; path translation for `--project` under `/mnt/c`; `xdg-open`/`open`/`wslview`
   for browser fallback only). `loader.py` covers Windows-native PowerShell. Add a
   `dev/loader/check_loader_parity.sh` (or extend the existing parity test) that runs
   `--print-config` on all three shells in CI via matrix (bash on ubuntu + macos; WSL cannot run in
   CI, so add a shellcheck + `bash -n` gate and a documented manual WSL checklist in
   `docs/dev/TESTING.md`).
4. `loader_dev.sh`: keep as shim, but its `--desktop` flag must not error out demanding
   `--project` (memory: the desktop app has its own project page). Reproduce
   `bash dev/loader/loader_dev.sh --desktop` today and fix.
5. GPU: the desktop app must still run the container GPU probe in dev mode (`stack.ts`
   `probeContainerGpu`); confirm by `--print-config` and a log line in dev mode.

Gate: `bash loader.sh --dev --print-config` shows `ui desktop`; `bash dev/loader/loader_dev.sh`
(no args) opens the Electron window on the packaged Overview; editing a `.tsx` and a `tit/server`
route is visible without restarting the container; `--browser` still works.

## Lane B — Ex/mEx/Recip live scene pane (parity with Flex and Analyzer)

Problem (screenshot 2026-09-17 13:19): on the Optimizer page with method **Ex** the right pane shows
only "Open target in TetraVox". Cause: `desktop/src/renderer/pages/optimizer/index.tsx` passes
`allowAtlas={activeRow?.method === "flex"}` to `TargetPreview`, which then skips `ScenePane`.
Flex and Analyzer already render the live `ScenePane mode="target"|"inspect"`.

Deliverables.
1. Ex, mEx and Recip rows render `ScenePane` exactly like Flex: atlas pick, region toggle, ROI
   write-back through `patchActiveRoi`. Ex's ROI model (`tit/opt/ex/roi.py`, `roi_spec.py`) already
   accepts cortical/subcortical atlas targets and MNI masks, so the pane is a pure UI omission.
   If Ex's `RoiValue` shape differs (e.g. spherical CSV targets), keep the "Open target in TetraVox"
   button for the spherical/mask modes only, as today's fallback branch, and show the pane for
   atlas modes.
2. When the row's method changes, the pane must not remount the guide (rule: pane is keyed on
   nothing subject-specific).
3. Playwright: extend the optimizer e2e to assert the scene canvas is present for `ex` and `mex`
   rows, offscreen.

## Lane C — `labeling.nii.gz` islands: diagnosis, then fix

Problem (screenshot 2026-09-17 13:18): Left-Putamen from `labeling.nii.gz` renders with small
detached fragments far from the putamen (a second blob inferior-anterior, plus grey debris).

Diagnose first, in the container (`idossha/ti-toolbox-test`, Dataset 000 / sub-ernie and the
user's `sub-101` if reachable), with a throwaway script under the scratchpad:
- Load `m2m_<id>/segmentation/labeling.nii.gz`, for each label run `scipy.ndimage.label` on the
  binary mask and report: number of components, voxel count of each, distance of each minor
  component's centroid from the main one. Do this for all 17 regions and for the 3 subcortical
  regions people target most (putamen, caudate, thalamus, hippocampus).
- Compare against `final_tissues.nii.gz` (GM mask) and against the `charm` MNI atlas warped by
  `mni2subject` (`tit/scene/target_preview.py::preview_deformation`) to decide whether the
  islands come from **charm's labeling** (upstream SimNIBS, plausible: it is a warped atlas
  intersected with tissue labels, and small far islands are a known artefact) or from **our
  pipeline** (e.g. `volume_surfaces.py` marching cubes on `np.pad(cropped,1)` with a wrong crop
  bbox, a label-value collision, or nearest-label transfer in `build.py::labels_from_nearest`).
- Write the finding into the PR description and `docs/dev/DECISIONS.md` with the numbers.

Then fix at the right layer:
- If upstream: in `tit/atlas/voxel.py`/ROI mask creation (`prepare_mask` and the subcortical
  ROI path used by flex/ex/analyzer), add a documented `keep_largest_component: bool = True`
  cleanup (scipy `ndimage.label`, keep components ≥ max(5% of largest, 50 voxels) — record the
  threshold and why), applied identically for search, analysis and the scene surface so the
  pane shows exactly what will be optimised/measured. Log removed voxel counts. Expose nothing
  new in the GUI unless the numbers show it matters; keep an env/config escape hatch.
- If ours: fix the bug; add a regression test with a synthetic two-blob volume.
- Either way, the scene surface for a region must match the mask used downstream.

## Lane D — Subject / MNI switch above the scene (Optimizer + Analyzer)

Requirement. Above the scene pane on all targeting/analyzer run pages, a two-state switch
**Subject | MNI**, bound to the *active job row* (not page-global). With MNI selected:
- The pane lists the MNI atlases we ship (`tit/atlas/constants.py::MNI_ATLAS_FILES`,
  `resources/atlas/`), draws them on the packaged MNI guide anatomy (extend `tit/scene/guide*`:
  a second guide, `guide-mni`, built from the MNI152 template we already ship for
  `mni_resources_dir()`), and selection semantics are unchanged (regions ⇄ chips).
- The job config gets `atlas_space: "mni"` (already supported by `roi_spec.py`, `ex/roi.py`,
  analyzer). At the **start of every such job**, the runner always calls `mni2subject`
  (`prepare_mask(path, "mni", m2m, out)` / `mni2subject_coords`) before anything else, and
  writes a **visual confirmation artefact**: the subject-space mask overlaid on the subject T1,
  three orthogonal slices at the mask centroid, saved as
  `derivatives/.../<job>/roi_confirmation.png` + a JSON with centroid (subject RAS), voxel count,
  GM overlap fraction. The desktop job page shows this image in the job's row/results and the
  terminal prints one line ("ROI Left-Putamen (MNI→subject): 1 234 voxels, centroid (−24, 2, −1),
  GM overlap 91 %"). Use the Tetravox job API when the desktop is native (Lane E); fall back to a
  matplotlib/nilearn PNG inside the container otherwise, so the artefact exists in every mode.
- Switching back to Subject clears MNI atlas selections that have no subject equivalent and says
  so in one sentence.

Files: `desktop/src/renderer/pages/_shared/scene/{ScenePane,TargetPreview}.tsx` (+ a small
`SpaceSwitch` in `_shared`), `pages/_shared/roi.ts` (RoiValue gains `space`), optimizer + analyzer
`buildConfig`/`rows`, `tit/server/routes/scene.py` (guide id parameter), `tit/scene/guide_build.py`,
`tit/opt/{flex,ex,recip}` + `tit/analyzer/analyzer.py` entry points (confirmation artefact),
`tit/config_io.py` if the JSON shape changes. Keep PARITY.md files in each page current.

## Lane E — Smart Tetravox snapshots via its job API

Tetravox already has a headless, focus-free job runner: `Tetravox --job job.json --out dir`
with `screenshot`, `sweep`, `orbit`, presets, `set(cursor=…)`, and a stdlib-only Python client
(`~/00_development/tetravox/python/tetravox`, `Job(...).screenshot(...).run(out)`). Screenshots
never contain panels; the RAD/NEU badge is always present.

Deliverables.
1. `tit/snapshots.py` (or `tit/scene/snapshots.py`): a thin wrapper that builds a Tetravox job
   for a given output kind and runs it **from the desktop main process** (Tetravox is a host
   app; the container cannot run it). Server writes a `*.snapshot-request.json` next to the
   output; the Electron main process watches the job's event stream, resolves the Tetravox
   executable (`find_app` equivalent in TS, reuse the existing native-open resolution in
   `desktop/src/main`), runs the job with `--out` inside the derivative directory, and reports
   the PNG paths back through the existing job events so the Results page can list them.
2. Trigger points (only where it logically helps, one screenshot each unless noted):
   - ROI confirmation (Lane D): mask on T1, axial+coronal+sagittal at centroid.
   - Simulation done: TI_max on T1 axial at the field peak, and on GM mesh (preset
     `ti-field-on-t1`).
   - Flex/Ex/Recip search done: best montage electrodes on skin + field on GM (`orbit` 8 frames
     optional, off by default).
   - Analyzer done: ROI on field, one slice.
3. If the job schema lacks something we need (e.g. "cursor at field max", electrode glyph layer,
   a mask-outline overlay), do **not** hack around it: write the exact missing action/preset into
   `~/00_development/tetravox/docs/ROADMAP.md` under a dated heading and implement it in the
   Tetravox repo on a branch (`feat/ti-toolbox-snapshots`), with its AUTOMATION.md and validator
   (`packages/app/src/main/job.ts`) updated together, then bump the pinned Tetravox version the
   desktop auto-update expects. Keep TI-Toolbox working when Tetravox is absent (skip with one
   log line; never fail a job because a picture failed).
4. Settings: a single "Snapshots" toggle in Settings (default on) and a per-page checkbox is not
   needed.

Gate: on Dataset 000 sub-ernie, run one TI simulation and one flex search from the desktop in dev
mode; both derivative folders contain the PNGs; the Results page shows them; the terminal shows
one line per snapshot; with Tetravox uninstalled the jobs still succeed.

## Order and parallelism

A first (everything else is verified through the dev desktop loop). Then B and C in parallel
(independent files). Then D (depends on B's pane refactor and C's mask cleanup). Then E (depends on
D's confirmation hook). Commit after each lane; run the full gate (`docs/dev/TESTING.md`) at the end.

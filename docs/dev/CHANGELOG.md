---
layout: releases
title: Changelog
permalink: /releases/changelog/
---

Complete changelog for all versions of the Temporal Interference Toolbox.

---
### v3.0.0 (Unreleased)

- **Jobs columns fit their content.** Status and resource columns stay compact while Stage uses the remaining space.
- **Overview shows project context.** Project name/path, background storage totals by derivative,
  a yearly activity calendar accompany the subject matrix. Storage groups derivative totals with indented workflow subtotals, with a visible scrollbar for longer lists. The activity calendar fills its column.

- **Saved montages can be removed.** Simulator’s **Manage montages** lists net-based montages
  and subject-specific freehand placements in a fixed-height scrolling list with confirmed
  individual or multi-selection deletion. Existing results are kept; failed deletions stay selected for retry.
- **Extension pages share one navigation group.** Expand **Extensions** to access Source,
  Cluster permutation, NIfTI group averaging, Nilearn visuals and 3D visual exporter.
- **Ex-search electrode pairs align.** Search-space controls occupy their own row, keeping
  positive and negative electrode selectors paired in TI and mTI modes.

- **Navigation follows the working order.** Optimizer precedes Simulator; Viewer and Results
  precede Pipeline, Notebooks and Jobs. Extensions follow those pages. Number shortcuts follow the new order.
- **Inputs need fewer clicks.** NIfTI masks accept file drops and editable server paths;
  multi-select picker rows toggle their selection when clicked. Simulator job settings expose
  tensor ratio and conductivity limits for anisotropic models.

- **Analyzer accepts NIfTI masks.** Import Subject/MNI masks using the same picker as Optimizer;
  group masks are registered separately for each subject.
- **Target previews follow the form.** Optimizer and Analyzer display non-surface targets as
  read-only volumetric previews; cortical atlas picking remains interactive. Lightweight anatomy,
  cached registration and a retained viewer accelerate repeated previews without changing calculation inputs.

- **Tetravox opens immediately.** The Viewer displays its full UI before a scene is selected,
  allowing local files to be dragged directly into it.

- **FastSurfer uses available hardware.** Automatic device selection supports CUDA, native
  Apple MPS, or CPU in the selected Python environment. The bundled Docker image remains CPU-only.

- **Custom NIfTI targets in Flex and Ex searches.** Import `.nii` or `.nii.gz` files (including through the macOS picker) and choose Subject/MNI space;
  MNI masks use the selected subject’s registration. Target and electrode settings are visually
  separated, and stacked scene/terminal panes use the available width on portrait screens.

- **Bash launchers no longer require Python.** Both CLI entry points open the Docker-hosted UI;
  their dev variants mount the current checkout. `pnpm dev --host` runs a local API and UI for
  development without Docker.

- **Scene selection works from the first click.** Simulator previews load the selected subject's
  available EEG nets, including BioSemi nets when tissue labels are present. Analyzer atlas clicks
  can create a new cortical target directly. Mixed mesh/volume selections no longer crash when
  a mesh without a selected field loads first; duplicate viewer handshakes do not restart loading.

- **Confirmed simulation replacement reaches SimNIBS.** Reruns no longer fail merely because
  the previous session marker exists. Existing-output replacement requires the project's
  **Allow unsafe overrides** setting and a fresh confirmation; Skip and Cancel remain available.

- **Extension inputs, plans and logs stay together.** Computational tools use inputs on the
  left and a plan/live terminal on the right. The 3D exporter previews the selected subject's
  atlas, segmentation labels, recorded montage or field context.
- **Viewer layers appear as they load.** Adding files reuses the datasets already in memory;
  failed files leave successful layers visible. Reload explicitly refreshes changed files.

- **Launch without memorizing flags.** Running either Python or Bash loader with no arguments
  asks only for the project folder and remembers it for next time, including the development
  loaders. Existing arguments remain supported; advanced settings do not require prompts.

TI-Toolbox v3 replaces the PyQt5 GUI with an **Electron desktop application**, and the two-image
Docker stack with a single streamlined image. There is no X11 anywhere, FastSurfer replaces
`recon-all`, and viewing is [Tetravox]({{ site.baseurl }}/wiki/visualizers/) inside the app window
instead of Freeview and Gmsh as separate X11 programs.

The desktop app and scripts use the same scientific core. For affected earlier workflows,
see the [targeted correction table]({{ site.baseurl }}/releases/v3.0.0/#scientific-corrections).

See the [installation guide]({{ site.baseurl }}/installation/) for source and artifact availability.

See [Desktop Application]({{ site.baseurl }}/wiki/desktop-app/) for how the pieces fit together,
and the [Wiki]({{ site.baseurl }}/wiki/) for a page per workflow.

#### The application

- **[Overview]({{ site.baseurl }}/wiki/overview/)** — a new landing page: one row per subject, one dot per artefact, and a per-stage readiness verdict, aggregated server-side across the whole project.
- **[Jobs]({{ site.baseurl }}/wiki/jobs/)** — every long-running thing is now a job with a record: state, stage, elapsed time, CPU and memory, live console, artifacts, and a named failure category. There was no job registry in 2.x.
- **[Notebooks]({{ site.baseurl }}/wiki/notebooks/)** — Jupyter inside the app, on the container's SimNIBS Python, with a seeded worked example that resolves *your* project.
- **[Pipeline]({{ site.baseurl }}/wiki/pipelines/)** — a canvas: wire pre-processing, an optimizer, the simulator and the analyzer into one graph, run it as one job group, or export it as a notebook.
- **[Results]({{ site.baseurl }}/wiki/results/)** — one subject-first outputs browser, with simulation reports rendered inline instead of in your OS browser.
- **Per-job tables on Simulator, Optimizer and Analyzer** — one row is one job, with its own subject, montage/method and target; **Duplicate** is the gesture for "same job, another subject". A run page submits its whole table as one request, and says how many groups it made.
- **Free-hand electrode placement, folded into the [Simulator]({{ site.baseurl }}/wiki/simulator/)** — select a row, click the subject's own scalp in the 3-D pane, and the row takes that point in subject millimetres. This is the only pane that draws the selected subject; the others draw a packaged guide head.
- **Optimizer is one page** — Flex and Ex are two *methods* in a column, not two screens; `flex_adaptive`, `flex_pareto` and `mex` are derived from the focality mode and the electrode count. New: a search-cost read-out, and a leadfield precondition strip with an ETA on **Generate**.
- **Settings ▸ Optional tools** — Source, Cluster permutation, NIfTI group averaging, Nilearn visuals and Quick Notes are switched on per project; each then appears in the rail and runs as a real job rather than on the UI thread.
- **Settings ▸ Viewer engine** — the viewer can be updated without updating the toolbox: version, protocol, source, sha256-verified installs, and one-click rollback to the bundle the image shipped.

#### Additions (container and platform)

- **Montage rendering preserves the scientific Python environment** — upcoming/internal
  builds run pinned Blender 4.4.3 as a separate background process, keeping the scientific
  NumPy 2.3.5 environment intact. Canonical PathManager mesh lookup replaces the incorrect
  montage mesh lookup. Full-net montage jobs now reserve 16 GiB as conservative headroom,
  not a measured uncapped peak; other export modes retain 2 GiB reservations. See
  [memory guidance]({{ site.baseurl }}/wiki/blender/#full-net-montage-memory).
  Final baked-image acceptance remains pending.
- **mEx planning no longer reads the removed `channels` field** — preview planning can count
  the positional montage combinations without crashing on the obsolete configuration field.
- **Starting with a different image leaves active jobs alone** — the loader refuses to attach
  when a running project's configured image reference differs from the requested image.
  Wait for its jobs to finish, explicitly stop that project's container, then start with the
  intended image; the loader does not kill jobs or replace a running container automatically.

- **Both standalone loaders can open the upcoming interface without a PyPI release** —
  `loader.py` and `loader.sh` refresh the `main` source archive into a shared isolated cached
  environment on each startup, so starting requires network access and the main integration.
  Management commands `--stop`, `--status` and `--logs` use a working cached launcher offline
  without refreshing source. A checkout loader uses its local source. Internal testing supplies the explicit
  `idossha/ti-toolbox:internal-20260908.1` image; its publication and immutable digest remain
  pending in the [handoff]({{ site.baseurl }}/installation/#internal-colleague-testing).
  This route creates no public release or update notification; 2.5.0 remains the public release.
- **Restarted servers settle interrupted jobs** — queued and interrupted running jobs become
  failed instead of remaining indefinitely active; a recorded completed exit retains its
  actual outcome. Jobs are not resumed or automatically resubmitted. See
  [Jobs]({{ site.baseurl }}/wiki/jobs/#server-restart).
- **mEx symmetry resolves standard leadfield filenames** — it now uses the shared symmetry
  helper, removing the old parsing failure for `<subject>_leadfield_<net>.hdf5`.

- **Single image, `idossha/ti-toolbox:<ver>`** — SimNIBS 4.6, FastSurfer (`--seg_only`, checkpoints pre-downloaded), the desktop UI, and the Tetravox Embed viewer are all baked into one image, with no `pip install` at container start.
- **Image size is being remeasured** — the September 7 development image measured 2.32 GB
  content / 8.93 GB disk. Those historical figures do not describe the current candidate,
  which adds standalone Blender. Final candidate download/disk size is pending.
- **FastSurfer segmentation** — a new, much faster pre-processing stage (`run_fastsurfer`) producing a DKT-atlas parcellation in `derivatives/fastsurfer/`, replacing FreeSurfer `recon-all` for the segmentation this toolbox needs.
- **Tetravox Embed viewer** — the 3D/volume viewer now renders inside the app's own window (WebGL2 + WASM on the host GPU, driven by a `postMessage` protocol), instead of launching Freeview/Gmsh as separate X11 applications.
- **Docker Engine API stack** — the desktop app now drives Docker entirely through its Engine API (image pull with progress, container create/start, health check, log streaming, stop) instead of shelling out to the `docker compose` CLI; `docker context inspect` is the only remaining CLI use, for engine discovery.
- **Three documented ways to run v3**, all landing on the same container-served UI: the **desktop app**; **`tit launch --project <dir>`** from the matching tested source package, or `./loader.sh` in its checkout, for servers and SSH sessions with no Electron; and **`npm run dev`** in `desktop/` to run unreleased code from source. See the [Installation Guide]({{ site.baseurl }}/installation/).
- **Offscreen end-to-end test harness** — Electron e2e tests run headless/offscreen by default, with a quiet-check wrapper that asserts no window reaches the screen, plus a browser-mode leg that drives the UI with no Electron bridge.

#### Removals

- **X11 everywhere** — no `/tmp/.X11-unix`/`.Xauthority` mounts, no `DISPLAY`, no `xhost`, no XQuartz/VcXsrv setup on any platform.
- **The separate FreeSurfer image** — `recon-all`, the thalamic-nuclei and hippocampal-subfield segmentation stages, the `freesurfer` compose service, the `freesurfer_data` volume, and the FreeSurfer license plumbing for the core workflow are all removed. Existing `derivatives/freesurfer/` outputs on disk keep working — readers accept both FastSurfer and legacy FreeSurfer outputs.
- **Freeview and Gmsh launchers** — including the `/api/viewers/{freeview,gmsh}` server routes and their `_require_x11` capability gate. **gmsh is no longer in the image.**
- **`dockerode` and CLI-driven Docker orchestration** in the desktop app, replaced by the dependency-free Engine API client above.
- **The PyQt5 GUI (`tit/gui/`)** — deleted, along with its extension framework, its Qt dialogs and the `GUI` shell command. The container ships no Qt at all: PyQt5, `simnibs_gui` and gmsh are stripped from the image. The [historical page]({{ site.baseurl }}/wiki/gui/) is kept for reference.
- **The legacy 2.x launcher** — replaced by the desktop app and by `tit launch`.
- **The Subject Info panel** — its facts are the [Overview]({{ site.baseurl }}/wiki/overview/) page's; an existing project `settings.json` that still names it still loads.
- **The standalone Electrode Placement extension** — folded into the Simulator (see above).

#### Changes

- **Focused 3D previews** — **Simulator / Optimizer / Analyzer ▸ Scene** use only the visualization viewport and restore separate Skin and Grey matter opacity sliders. The dedicated Viewer keeps its full controls; saved scientific configurations are unchanged.
- **Consistent workflow controls** — subject checkboxes and sliders have keyboard-readable names, long dropdown choices stay inside their pane, and primary actions and blocked-action reasons use the shared layout in both themes.
- **Config field rename:** `PreprocessConfig.run_recon` → `run_fastsurfer` (an incoming `run_recon` is still accepted as a deprecated alias, with a warning); `parallel_recon`, `parallel_cores`, and `run_subcortical_segmentations` are dropped with no replacement (thalamic-nuclei/hippocampal-subfield segmentation has no FastSurfer equivalent — see the Pre-Processing page).
- **Capabilities:** `x11_display`, `freeview`, `gmsh`, and `freesurfer` (as a capability flag; `has_freesurfer` on a subject's info is unaffected) are removed from `GET /api/capabilities`; `tetravox_embed {available, version, protocol}` and `fastsurfer` are added.

#### Fixed

- **Targeted statistics and analyzer fixes** — corrected cluster inference, voxel focality units, grid validation and degenerate-group handling. See the [release notes]({{ site.baseurl }}/releases/v3.0.0/#scientific-corrections) for affected workflows and re-run or rescaling guidance.
- **A group of one no longer makes every voxel degenerate** (`tit.stats.engine.ttest_ind`, SCI-09) — the pooled variance was built as `(n-1) * np.var(x, ddof=1)`, which for a group of one subject is `0 * nan == nan` rather than the `0` the estimator calls for. Every voxel of a one-vs-many group comparison came out `nan`, was caught by the old zero-standard-error guard, and was reported as `t = 0, p = 1`: v2.2.3-v2.5.0 returned a complete, uniformly null result set for those designs, with no error and no warning. The pooled variance now sums each group's squared deviations, a singleton contributes exactly `0`, and a 2-vs-1 design matches `scipy.stats.ttest_ind` exactly. **Re-run** any group comparison with a single-subject group. Note that three subjects still cannot reach significance -- only three relabellings exist, so the smallest possible cluster p-value is about `1/3` -- but the `t` and `p` maps are now the real ones.
- **`channels` must partition `fields`** (`tit.calc`) — a field index that no channel referenced was silently dropped, so the envelope described a different montage from the one passed. It now raises, naming the unused indices.
- **`hf_peak` exactness is queryable** (`tit.fields.hf_peak_is_exact`) — above 8 carriers the direction sweep returns a lower bound on the true worst-case peak, which was documented in the docstring but not exposed to callers that record or display it.
- **Tabs preserve your work** — switching between Pre-processing, Simulator, Optimizer, Analyzer and Viewer retains each tab's draft, subject selection, section state, scroll and live 3D view for the open project session. Returning to a tab no longer rebuilds its viewer or resets its camera. Project switching starts a fresh session.
- **Preview failures stay readable** — a missing or failed 3D renderer no longer loops through silent reloads; retry is explicit and retains your surface-opacity settings.
- **Cortical atlas previews load again** — fixed a mesh-index lookup that prevented the atlas surface from building. Server build errors now remain readable until you explicitly retry, instead of appearing to build indefinitely.
---
### v2.5.0 (Latest Release)

**Release Date**: August 31, 2026

#### Additions

- `TI_normal` for mTI — multipolar simulations now write the normal-component envelope (`{montage}_mTI_normal.msh`) by default, computed by evaluating the multi-carrier envelope along the cortical surface normal; the analyzer's `normal_*` ROI statistics populate for mTI exactly as for standard TI.
- fsaverage projection for mTI — `map_to_fsavg` no longer skips multipolar runs: the modulation depth is read from the mTI central surface and `hf_peak`/`hf_sar` are derived from all N channel volume meshes.
- Multipolar exhaustive search (mex-search) — a multipolar counterpart to ex-search (`tit/opt/mex`), with a TI/mTI toggle, symmetric (bilateral) buckets, atlas-region and MNI-space ROI targeting, and a shared searchable ROI picker across ex-search and mTI.
- Threshold-free focality goal for flex-search — a new opt-in focality objective plus an opt-in current-ratio search, replacing threshold-dependent focality scoring.
- Selectable output fields — the simulator now writes only the fields you choose (TI_max by default) instead of a fixed set, with field definitions documented in the help popup.
- Custom subject masks as ROI targets — label volumes placed under `m2m_<id>/masks/` are auto-discovered and offered as subcortical ROI targets in flex/ex/mex-search and the analyzer.
- Unified TI/mTI field metrics — carrier grouping, hf_peak sign handling, and the TI/mTI metric surface were corrected and unified across calc, sim and the analyzer, closing several description/code mismatches; a literature-grounded field-metrics note documents the math.
- DWI preflight validation — gradient tables and sidecars are validated and QSIPrep node crashfiles are logged before/at container failure, catching bad DWI conversions early.
- Interactive atlas browser and multipolar TI documentation pages on the docs site, including subject-space atlas assets and a redesigned full-width docs theme with per-page subnav and KaTeX equation rendering.
- Claude Code / AI-assistant plugin (`agent-plugin/`) — an MCP server and marketplace listing so AI coding assistants understand the TI-Toolbox codebase, plus a maintainer-verified Troubleshooting Archive.
- Faster ex/mex-search — unit-current channel fields are now computed once per montage and reused across current splits, the TI/mTI envelope is evaluated on ROI∪GM only (not the whole head), and candidates run on a forked worker pool (`n_jobs`). Ex-search: 0.39 s → 0.05 s per evaluation (~8×; a 4,375-evaluation bucket search dropped from 28 min to 3 min). Mex-search: 58 s → ~1.4–2 s per candidate (~30–40×) via a fused numba kernel for the K≥2 mTI direction search.
- Ex/mex-search electrode-map visuals — every ex/mex-search run now writes an electrode participation heatmap and montage strength/focality maps, ported from work by [Larissa Albantakis](https://github.com/Albantakis) on her [ex-search-multipolar branch](https://github.com/Albantakis/TI-Toolbox/tree/ex-search-multipolar).
- Zenodo DOIs added for the archived software release.

#### Changes

- **Breaking:** `tit.calc` consolidated to exactly three envelope functions — `get_TI_vectors(fields, psi=None)` (K ≥ 1 carriers; the K = 1 exact closed form is applied internally), `get_TI_avg(fields, psi=None)`, and `get_TI_dir(fields, directions, psi=None)`. Scripts calling `get_TI_vectors(E1, E2)` positionally must switch to `get_TI_vectors([E1, E2])`; `get_mTI_vectors` is now `get_TI_vectors`, `get_mTI_dir` is `get_TI_dir`, and the deprecated `get_nTI_vectors` shim and the unused `get_magnitude_am` were removed, as was the legacy `channels=` carrier-regrouping parameter.
- Carrier wiring removed — mTI is always positional (each two consecutive electrodes compose a channel, each two consecutive channels compose a carrier): the mex-search "Carrier Wiring" combo, `MTI_CHANNEL_ARCHITECTURES`, and the `channels` JSON config keys are gone (old configs with the key are ignored).
- Documentation vocabulary unified across the simulator, analyzer and ex-search pages: **electrodes → channels (2 electrodes each) → carriers (shared by 2 channels)**; TI = 4 electrodes / 2 channels / 1 carrier, mTI = 8 electrodes / 4 channels / 2 carriers.

#### Fixes

- Analyzer sim-list bug fix, plus analyzer/ex-search layout cleanups (paired Tissue/Space and Field/Type controls, either/or ROI selection, dead vertical space removed).
- Ex-search now rejects empty ROI configs, tolerates header rows in MNI ROI CSVs, and fails cleanly on zero candidates instead of silently returning nothing.
- Flex-search summary.txt no longer prints a raw Python function repr on the Goal line.
- QSIPrep/QSIRecon fixes — the root BIDS dataset description is always created, a missing T1w is reported up front, QSIRecon's log directory is no longer mistaken for existing output, and a converted DWI arriving without its gradient table now warns instead of failing silently.
- DICOM import — a converted DWI missing its gradient table is now caught and reported.
- Atlas resampling in the analyzer — atlases and tissue masks are now matched to the field on shape **and** affine and resampled nearest-neighbour, replacing a shape-only check and an interpolating `mri_convert` call that also required FreeSurfer binaries absent from the simulation container. See the note below.
- Docs — corrected stale ROI, tissue, atlas, CLI and testing-pipeline claims across the wiki, scripting, ex-search and analyzer pages; fixed release download links and a blank atlas viewer for cached scripts.
- Dev loader — `loader_dev.sh` rewritten as a working Python-free bash loader after regressions.

#### Note: atlas resampling in the analyzer

The analyzer's grid check compared shape only, so an atlas with matching dimensions but a different affine could pass through untouched and produce statistics for the wrong tissue, silently. Resampling also used `mri_convert --reslice_like`, whose default trilinear interpolation blends discrete region ids into ids that belong to no region. The check now compares the affine too, resampling is nearest-neighbour, and neither step needs FreeSurfer binaries that the simulation container does not ship.

<a href="{{ site.baseurl }}/assets/imgs/atlas-resampling/atlas_resample_v250_old_vs_new.png">
  <img src="{{ site.baseurl }}/assets/imgs/atlas-resampling/atlas_resample_v250_old_vs_new.png" alt="Old versus new atlas resampling in v2.5.0" style="width: 100%; max-width: 950px;">
</a>

**This is a robustness fix, not a result-changing one.** Interpolation order only matters when the atlas and field lattices do not coincide, which for the 1 mm FreeSurfer parcellations, the thalamic nuclei and every MNI atlas they do — old and new are bit-identical there. The one exception is the 0.333 mm hippocampal and amygdala subfields, shown above: even in that worst case the reported **field changes by ~0.5%** (mean −0.6%, max −1.2%) while the ROI *volume* changes by −42%, because trilinear erodes the region's boundary. Field statistics from earlier versions stand; ROI voxel counts and volumes from a hippocampal or amygdala subfield ROI are worth regenerating. Details on the [Brain Atlases]({{ site.baseurl }}/wiki/atlases/#atlas-resampling) page.

#### Download Links

**Desktop App (v2.5.0):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/TI-Toolbox-2.5.0.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/TI-Toolbox-2.5.0-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/TI-Toolbox.Setup.2.5.0.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/TI-Toolbox-2.5.0.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/ti-toolbox_2.5.0_amd64.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:v2.5.0`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.4.0

**Release Date**: July 20, 2026

#### Additions

- **Combine multiple ROIs in optimization** — flex-search and exhaustive-search can now target the union of several same-type regions (cortical by name including cross-hemisphere, subcortical by label, or multiple spheres) through a searchable region picker with region chips.
- **TI safety metrics (Cassarà et al. 2025)** — peak carrier field and SAR-driver maps are now written as subject- and MNI-space NIfTI volumes alongside TI_max.
- **Surface-based group statistics** — run group comparisons and correlations directly on the fsaverage cortical surface with cluster-based permutation testing and inflated-cortex rendering; TI fields now auto-project to fsaverage after each simulation.
- **CT and NIfTI ingestion** — preprocessing can now import head CT scans and pre-converted NIfTI files (T1w/T2w/CT/DWI), not only DICOMs.
- **3D Visualizer subcortical field export** — export subcortical structures colored by a simulation field (PLY) using a searchable label picker.
- **Simulator skip/replace policy** — choose to skip or overwrite existing simulation outputs instead of aborting with an error.
- **Montage visualizer clarity** — connection arcs now show which channels interfere (TI partners), with a channel color legend.
- **Faster simulations** — mesh-to-NIfTI conversion is parallelized, cutting end-to-end simulation time by roughly 30%.

#### Fixes

- **DICOM import crash** — fixed a crash on projects seeded with macOS junk (AppleDouble) files.
- **QSIPrep preprocessing failures** — the root BIDS dataset description is now always created, and a missing T1w is reported up front instead of failing deep in the workflow.
- **3D exporter file loss** — fixed the exporter deleting cortical region files after export.
- **FreeSurfer data volume versioning** — the volume is now versioned by image tag so image updates correctly re-seed it.

#### Download Links

**Desktop App (v2.4.0):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TI-Toolbox-2.4.0.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TI-Toolbox-2.4.0-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TI-Toolbox-2.4.0.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TI-Toolbox-2.4.0.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TT-Toolbox-2.4.0.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:v2.4.0`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.3.2

**Release Date**: June 11, 2026

#### Additions

- New Source tool (extension): build MNE EEG forward solutions and project TI fields onto the fsaverage template.
- Preprocessing now automatically converts DWI DICOMs to BIDS NIfTI alongside T1w/T2w.

#### Fixes

- FreeSurfer recon-all no longer falsely reports its output as already existing on a fresh project.

#### Download Links

**Desktop App (v2.3.2):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TI-Toolbox-2.3.2.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TI-Toolbox-2.3.2-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TI-Toolbox-2.3.2.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TI-Toolbox-2.3.2.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TT-Toolbox-2.3.2.deb)

**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.3.2`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.3.1

**Release Date**: May 8, 2026

Focused maintenance release for preprocessing robustness, GUI reliability, QSI container compatibility, flex-search validation tools, and NIfTI viewer usability.

#### Fixes & Maintenance

##### Flex-search and Simulation Workflow

- **Flex-search simulation identity and UI naming** — simulator-generated flex-search runs now keep a unique storage key while showing compact, readable run labels and hover metadata in the GUI, following the run-id/run-name split used by tools such as [MLflow](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.html).
- **Flex-search valid skin region controls** — flex-search now exposes `skin_region_margin_mm`, optional landmark guarding, GUI controls, and report imagery so users can inspect and tune the valid scalp placement region used by optimization.

##### Reports and Visualization

- **Report and visualization follow-ups** — simulation reports use clearer missing-visualization states and simulations continue when optional montage visualization cannot be generated.
- **Analyzer discovery improvements** — Analyzer refreshes simulation lists when shown and after simulation completion, with clearer messages when TI/mTI post-processing outputs are missing.

##### NIfTI Viewer

- **Electrode NIfTI overlays** — the NIfTI Viewer can create and auto-load a single label-mask overlay showing saved electrode placements from `documentation/config.json`. Labels are channel-based, use the same color order as montage PNGs, and are saved next to montage images under `TI/montage_imgs/` or `mTI/montage_imgs/` depending on simulation mode.

##### GUI Reliability

- **GUI lifecycle reliability** — preprocessing, simulation, flex-search, ex-search, Analyzer, and NIfTI Viewer tabs now refresh dependent outputs more consistently and avoid reporting success after failed subprocesses.

##### Preprocessing and QSI

- **DICOM preprocessing hardening** — DICOM discovery now searches nested `.dcm`/`.dicom` files and supports basic compressed inputs (`.zip`, `.tar`, `.tar.gz`, `.tgz`) in the documented `sourcedata/sub-{id}/{T1w,T2w}/dicom/` layout.
- **Preprocessing existing-output handling** — the GUI now detects existing outputs before rerunning DICOM conversion, CHARM, FreeSurfer `recon-all`, QSIPrep, QSIRecon, or DTI extraction. Users can cancel, skip existing outputs, or explicitly replace them and rerun. The same policy is available to scripts through `skip_existing_outputs` and `replace_existing_outputs`.
- **QSI Docker preflight** — QSIPrep and QSIRecon now validate Docker/DooD setup early, before starting long-running container work.
- **QSI containers updated** — QSIPrep and QSIRecon now target PennLINC `26.0.0`, with CLI compatibility handling for QSIPrep `concat` and QSIRecon `--input-type qsiprep`.

##### Telemetry and Release Operations

- **Telemetry error grouping** — operation telemetry now emits a per-run `run_id` plus a stable, path-sanitized `error_fingerprint`, making recurring failures easier to group without sending tracebacks or local paths.
- **Telemetry-driven preflight checks** — common user/environment problems are validated before telemetry-tracked work starts for simulation, flex-search, and empty preprocessing subject selections, reducing noisy error reports while preserving real exceptions.
- **Telemetry consent persistence** — GUI telemetry consent is stored in the user-level config mount and should no longer reappear every launch once answered.
- **Launcher telemetry normalization** — host OS and architecture values are canonicalized across the Electron launcher and `loader.py`, keeping telemetry slices consistent across entrypoints.
- **Community link** — README and release help links now point to the active TI-Toolbox Discord server.
- **Release-gate tests** — added Dockerfile.test-based integration checks plus a self-contained comprehensive release-gate entry point using only test-environment fixtures.

#### Download Links

**Desktop App (v2.3.1):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/TI-Toolbox-2.3.1.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/TI-Toolbox-2.3.1-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/TI-Toolbox.Setup.2.3.1.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/TI-Toolbox-2.3.1.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/ti-toolbox_2.3.1_amd64.deb)

**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.3.1`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.3.0

**Release Date**: March 17, 2026

A major release with new analysis capabilities, broader simulation support, diffusion pipeline integration, and a modernized codebase built on SimNIBS 4.6.0.

#### Preprocessing & Segmentation

- **Subcortical sub-nuclei segmentation** — hippocampal and thalamic sub-nuclei are now automatically segmented as part of the FreeSurfer recon-all pipeline.
- **QSIPrep / QSIRecon integration** — diffusion MRI preprocessing and reconstruction are now available through the GUI and CLI, including DTI extraction for anisotropic simulations. This still needs further validation, but works well internally.
- **MASSP2021 nuclei atlas** — added under the MNI resources as a built-in subcortical atlas for targeting thalamic and brainstem nuclei. Can be selected in the group-level visualization step.

#### Simulation & Optimization

- **Upgraded to SimNIBS 4.6.0** — the underlying finite-element engine is now at its latest version, bringing improved meshing and solver accuracy.
- **Anisotropic conductivity in optimization** — flex-search now supports all 4 SimNIBS conductivity models (isotropic, volume-normalized, direct, and mean-conductivity). Select via the GUI dropdown or the `anisotropy_type` config parameter. Fine-tune with `aniso_maxratio` and `aniso_maxcond`.
- **White matter / gray matter tissue targeting** — flex-search lets you choose whether to optimize over gray matter, white matter, or both.
- **Focality Pareto sweep** — new tool to systematically explore the trade-off between field intensity and focality across a grid of threshold combinations, producing a Pareto plot and summary table.
- **Batch simulation** — run multiple simulation configurations in sequence from a single GUI session.

#### Analysis

- **Combined multi-ROI analysis** — select multiple atlas regions and analyze them as a single combined ROI. Outputs use a `+`-joined naming convention (e.g., `precentral+postcentral/`).
- **Tissue-type selection in analysis** — choose GM, WM, or both when running voxel-space analyses.

#### Infrastructure & Usability

- **Singularity / Apptainer support** — run TI-Toolbox on HPC clusters without Docker.
- **HTML report generation** — automated reports for simulation and preprocessing results.
- **Redesigned GUI** — modernized styling, consistent console output, and reusable ROI/electrode/solver widgets across all tabs.
- **Simplified Python scripting API** — cleaner imports and flat configuration dataclasses make scripting simulations, optimizations, and analyses more straightforward. See the updated API documentation for examples.
- **Improved CI/CD and test suite** — comprehensive automated testing with coverage tracking.

#### Breaking Changes (for scripters)

- The Python API has been significantly simplified. If you have scripts that import from `tit`, please refer to the updated [API documentation]({{ site.baseurl }}/wiki/scripting/) for the new import paths and configuration classes. Key changes:

#### Download Links

**Desktop App (v2.3.0):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox-2.3.0.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox-2.3.0-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox.Setup.2.3.0.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox-2.3.0.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/ti-toolbox_2.3.0_amd64.deb)
**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.3.0`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.2.4

**Release Date**: January 16, 2026

#### Additions

- N/A

#### Fixes

- **Loader Program**: Fixed example data and initiliazation of the BIDS files. Also, should be handling X11 more gracefully.

#### Download Links

**Desktop App (v2.2.4):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox-2.2.4.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox-2.2.4-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox.Setup.2.2.4.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox-2.2.4.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/ti-toolbox_2.2.4_amd64.deb)
**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.2.4`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.2.3

**Original Release Date**: January 07, 2026
**Effective Release Date**: January 14, 2026 (re-uploaded tag with preprocessing refactored to deal with recon-all problem without releasing and official new image. Should be updated automatically to all users without breaking behavior).

#### Additions

- **New Blender Tool for Full Blend File Creation**: Complete Blender integration with automated blend file generation, electrode positioning, and visualization setup. Streamlined workflow for creating publication-ready 3D visualizations directly from simulation results.
- **Ex-search**: Added an option to run the a truly exhaustive search option as all selected electrodes are pooled together instead of placed in stationary buckets. Refer to ex-search wiki tab for more information.
- **New Correlation Mode for Cluster-Based Permutation Testing**: Enhanced statistical analysis capabilities with correlation-based cluster permutation testing, providing more robust statistical inference for connectivity and relationship analyses.
- **Unified Command-Line Experience**: All CLI tools now support both interactive mode (run without arguments) and direct mode (with flags). Consistent colored output, clear prompts, and intelligent option discovery across all commands.
- **Multi-Processing Simulator**: Parallel processing capabilities for faster simulation runs, optimized resource utilization, and scalable performance across different hardware configurations.
- **Enhanced Testing Suite Coverage**: Comprehensive test coverage expansion including simulator workflows, statistical analysis pipelines, and integration testing for improved reliability and stability.
- **Improved Security CI/CD Pipeline**: Strengthened GitHub Actions workflows with enhanced security scanning, automated vulnerability detection, and improved code quality gates throughout the development pipeline.
- **Refactored pre-processing tools**: Removed all bash scripts to improved maintainability and reduce complexity. Updated all relevant benchmarks, tests, and docs.

#### Fixes

- **Experimental Movea Tool**: Temporarily removed the experimental movea tool to focus development efforts on core functionality and stability.
- **Bug Fixes & Reliability**: Fixed GUI crashes and timeout issues. Improved path handling and import reliability. Updated electrode templates for better compatibility. Enhanced security scanning and CI/CD workflows.
- **Documentation Updates**: New CLI and GUI documentation pages. Improved Blender integration instructions. Added visualizer documentation. Better organization of documentation images.

#### Download Links

**Desktop App (v2.2.3):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox-2.2.3.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox-2.2.3-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox.Setup.2.2.3.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox-2.2.3.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/ti-toolbox_2.2.3_amd64.deb)
**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.2.3`

---

### v2.2.2

**Release Date**: December 25, 2025

#### Additions

- **Simulator Refactoring**: Complete rewrite from bash to Python with modular architecture including progress callbacks, better error handling, and improved logging.
- **Enhanced Cluster Permutation Testing**: New ACES-like correlation investigation, support for continuous variables, enhanced reporting, and improved GUI integration.
- **Comprehensive Testing Infrastructure**: new test files with code coverage integration, headless operation support, and improved CI/CD pipeline.
- **Improved 3D Visualization**: Enhanced visual exporter with automatic electrode placement, metadata extraction, GLB format export, and Docker-based Blender integration.
- **Pythonic CLI Migration**: New Click-based command-line interfaces for simulator and cluster permutation tools with better argument validation.
- **GUI Enhancements**: Improved threading across all tabs with real-time progress updates, better error handling, and enhanced responsiveness.

#### Fixes

- **Various Bug Fixes**: Fixed silent timeout issues in CI, corrected coverage integration, improved error handling in all major modules, better cleanup of temporary files, and enhanced logging.
- **Windows Electron**: A more robust executable delivery on Windows.

#### Download Links

**Desktop App (v2.2.2):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox-2.2.2.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox-2.2.2-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox.Setup.2.2.2.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox-2.2.2.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/ti-toolbox_2.2.2_amd64.deb)
**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.2.2`

---

### v2.2.1

**Release Date**: December 04, 2025

#### Backward compatibility change to be aware:

- **Electode Mapping**: We changed the mapping functionality from the **flex-seach** to the **simulator**. This to provide a more flexible and dynamic framework. Now, the flex-search outputs the: `electrode_positions.json` file and the mapping functionality happeneds on the simulator side using the new method `ti-toolbox/tools/map_electrodes.py`. Thus, one can use a single flex-search to conveniently map to multiple nets.

#### Additions

- **Desktop App**: Recognizing the importance of Desktop delivery, we redesign our executables with Electron. For more info please see `package`.
- **Benchmarks**: Added benchmarking tool with sensible defaults that users can run on their systems
- **AMV**: Improved automatic montage visualization that now supports all available nets with a higher resolution image.
- **Flex-search**: Added more control over electrode geometry now supporting rectengular and width control.
- **Flex-search**: Exapnded hyper-parameter control. tolerance and mutation rate.
- **Ex-search**: Enhanced the ex-search with current ratio optimization, enabling more robust optimization process. The exhaustive search now evaluates possible electrode montages and current ratios according to the formula:

$$
N_{\text{total}} = N_{\text{elec}}^{4} \cdot N_{\text{current}},
\qquad
N_{\text{current}} = \left\lvert \left\{ (I_1, I_2) \;\middle\vert\; I_1 + I_2 = I_{\text{total}} \;\wedge\; I_{\text{step}} \le I_1, I_2 \le I_{\text{limit}} \right\} \right\rvert
$$

#### Fixes

- **Various Bug Fixes**: protection overwrites, documentation, output formatting, UI improvements, parallel processing, electrode management

#### Download Links

**Desktop App (v2.2.1):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox-2.2.1.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox-2.2.1-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox.Setup.2.2.1.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox-2.2.1.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/ti-toolbox_2.2.1_amd64.deb)

**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.2.1`

---

### v2.2.0

**Release Date**: November 07, 2025

#### Additions

- **Core Infrastructure & Architecture**: The project underwent a complete restructure, removing old launcher directories and consolidating to a unified ti-toolbox structure. A new core module system was introduced in ti-toolbox/core/ with reusable components including paths.py, calc.py, constants.py, errors.py, process.py, utils.py, nifti.py, mesh.py, and viz.py. The project moved away from executable compilation and now focuses exclusively on bash entry point.
- **GUI Extensions System**: A new modular extension system was introduced in ti-toolbox/gui/extensions/ providing several powerful tools. The Cluster-Based Permutation Testing (CBP) extension offers statistical analysis for group comparisons. Nilearn Visuals enables brain visualization using nilearn with glass brain views, surface plots, and slices. The NIfTI Group Averaging tool allows averaging multiple NIfTI files across subjects. The Visual Exporter provides export capabilities to Blender-compatible formats (PLY, STL) with a full tutorial. Additional extensions include Quick Notes for in-app note-taking with persistence, Subject Info Viewer for displaying metadata and processing status, and an Electrode Placement Tool for interactive electrode positioning.
- **3D Visualization & Export**: A 3D Exporter module was added in ti-toolbox/3d_exporter/ containing four specialized tools. TI_quick_volumetric.py provides fast volumetric field exports, cortical_regions_to_ply.py handles region-specific mesh exports, cortical_regions_to_stl.py outputs STL format for 3D printing, and vector_ply.py enables vector field visualization in Blender.
- **MOVEA Optimization**: MOVEA-like integration was implemented for multi-objective optimization of electrode placement. The system now uses a centralized leadfield with unified leadfield target locations across all optimization tools. A complete MOVEA GUI tab provides an interface for optimization workflows.
- **Analysis Tool**: Group Analyzer received significant improvements including enhanced multi-subject analysis capabilities with MNI coordinate support.
- **Statistics Module**: A statistics package was created in ti-toolbox/stats/. The cluster_permutation.py module implements non-parametric cluster-based permutation testing.
- **Simulator Improvements**: The simulator received substantial enhancements including a new free-hand mode that allows direct electrode coordinate input without montage selection. The entire simulator was refactored for a cleaner codebase with better error handling.
- **Optimization Tools**: The flex-search tool was restructured and modularized into ti-toolbox/opt/flex/. A multi-start approach was implemented allowing multiple iterations to find the best solution. The ex-search tool received enhancements for better ROI handling and faster analysis.
- **GUI Enhancements**: Multiple GUI improvements enhance the user experience. A centralized Path Manager handles path operations across all GUI tabs. Console output was standardized for consistent logging and status updates. Confirmation dialogs now appear before long-running processes. A debug mode provides optional verbose output for troubleshooting. An OpenGL fallback system provides automatic compatibility handling for macOS issues.
- **Documentation**: More documentation was added covering new features. New wiki pages document cluster permutation testing, electrode placement, MOVEA optimization, tissue analyzer, visual exporter, nilearn visuals, nifti group averaging, and quick notes. A pipeline flow diagram provides visual representation of the complete workflow. A detailed Blender tutorial offers step-by-step guidance for 3D visualization. Installation documentation was streamlined with updated setup instructions and removal of executable references. The gallery was updated with new screenshots showcasing all GUI features.
- **CI/CD & Testing**: A CI/CD pipeline was implemented with automated testing and Codecov integration for code coverage tracking. The test suite was expanded covering most modules, including new test files for calc, constants, core integration, mesh, errors, ex-analyzer, nifti, paths, process, utils, and MOVEA optimizer with integration tests. CircleCI integration now provides automated testing on every commit with proper permissions and workflows.
- **Development Tools**: Developer experience was improved with enhanced dev environment setup in dev/bash_dev/ for contributors. Version control management was improved for better consistency across all files. The project standardized on the simnibs_python interpreter for all Python operations. Container communication between FreeSurfer and SimNIBS was enhanced for better data sharing.

#### Fixes

- **Bug Fixes & Refinements**: Numerous bug fixes and refinements were implemented including BIDS structure compliance improvements, resolution of deadlock issues in GUI tabs, improved overwrite protection across all tools, fixed electrode naming consistency, better handling of network volumes, X11 and OpenGL fixes for cross-platform compatibility, and reduced console bloat with improved logging throughout the application.
- **Removals & Cleanup**: Significant cleanup was performed removing all executable launcher code (over 7,000 lines), eliminating old MATLAB dependencies, removing outdated documentation and assets, cleaning up redundant development files.

#### Download Links

- Docker Image: `docker pull idossha/simnibs:v2.2.0`
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)** - Main launch script
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)** - Docker configuration

---

### v2.1.3

**Release Date**: October 08, 2025

#### Additions

- - **Executable Launcher**: pre-flight check for existing containers to avoid start conflicts.
- - **Executable Launcher**: validation of path input (for mannual inputs)
- - **Flex-search**: dynamic focality thresholding for better output
- - **Development**: Added a watchdog for easier GUI development
- - **Analyzer**: Added `labeling.nii.gz` as an option for voxel analysis w/o need for recon-all

#### Fixes

- - **General**: Removed env limits for flex-search, cleaned up GUI tabs, fixed Gmsh GUI lauchner with analysis visuals, fixed example data (ernie, MNI152) mounting in executable mode, clean up of executable console output.
- - **Critical**: Batch processing of sub-cortical targets in flex-search mode. Previous, `labeling.nii.gz` was no updating between subjects, causing incorrect optimization targeting.

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.3/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.3/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.3/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.1.2

**Release Date**: September 08, 2025

#### Additions

- Example Dataset: Toolbox now ships with Ernie & MNI152 MRI scans for quick start & learning purposes.
- Tissue Analyzer: Added skin thickness and volume analysis

#### Fixes

- Various bug fixes: charm, ex-search, flex-search

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.1.1

**Release Date**: August 28, 2025

#### Additions

- N/A

#### Fixes

- **ex-search**: fixed final.csv output
- **flex-search**: fixed cleanup of directory if users choose a single start

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.1.0

**Release Date**: August 25, 2025

#### Additions

- **Improved BIDS formatting:** Enhanced Brain Imaging Data Structure (BIDS) compliance and formatting for better data - organization and compatibility
- **Debug mode for console output:** Introduced comprehensive debug mode with detailed console logging for troubleshooting and development
- **Inter-individual variability assessment:** New bone analyzer tool integrated into pre-processing pipeline for assessing anatomical variations between subjects
- **Multi-start approach for flex-search optimization:** Implemented multi-start optimization strategy to counter local maxima issues in electrode placement optimization

#### Fixes

- **Removed MATLAB runtime dependency:** Eliminated MATLAB runtime requirement, making the toolbox fully independent and easier to deploy
- **mTI bug fixes and upstream integration:** Resolved critical bugs in mTI (multi-channel Temporal Interference) functionality and improved integration with upstream SimNIBS components
- **Enhanced X11 handling for macOS:** Improved X11 server integration and display management for better GUI - functionality on macOS systems
- **Official rebranding:** Complete renaming from TI-CSC to TI-Toolbox across all components, documentation, and user interfaces

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.0/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.0/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.0/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.5

**Release Date**: July 10, 2025

#### Additions

- **Group Analysis Features**: Group analysis system with GUI interface, comparison capabilities, and logging
- **Focality Measurement**: New focality analysis tools with histogram generation for cortical analysis
- **Normal Component Analysis**: Added normal component matrics and visualization
- **Enhanced Workflow**: Multiple subject selection for flex-search, new naming conventions

#### Fixes

- **GUI Stability**: Multiple bug fixes for group analysis GUI, element resizing, console widget consistency, and special character handling
- **Analysis Accuracy**: Improved histogram generation, ROI comparison plots
- **Visualization**: Fixed mesh visualization and updated mesh visualizer functionality

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.5/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.5/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.5/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.4

**Release Date**: June 26, 2025

#### Additions

- flex-search -> simulator integration. Simulator now recognizes previous flex-searches and allows for simulation of both optimized and mapped electrodes.
- system monitor -> added a GUI tab that allows users monitor the activity of processes hapenning within the toolbox

#### Fixes

- pre-process -> added missing shell for recon-all step
- pre-process -> fixed parallalization problem
- ex-search redesign -> now is not dependent on MATLAB Runtime, but is fully Python implemented
- ex-search -> users can now creat multiple leadfields for the same subject
- flex-search -> post processing method for TI envelope direction is implemented

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.4/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.4/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.4/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.3

**Release Date**: June 20, 2025

#### Additions

- Modified tes_flex_optimization.py to include eeg_net field in the .json
- toggle between "Montage Simulation" (traditional) and "Flex-Search Simulation" with automatic discovery of optimization results and electrode type selection (mapped/optimized/both)
- Modified TI.py and pipeline scripts to handle direct XYZ electrode coordinates instead of just electrode names, enabling optimized electrode positioning from flex-search results

#### Fixes

- N/A

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.3/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.3/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.3/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.2

**Release Date**: June 19, 2025

#### Additions

- Enhanced X11 support for Windows with automatic host IP detection and VcXsrv/Xming configuration guidance
- Created `windows_x11_setup.sh` helper script for simplified Windows X server setup
- Added comprehensive Windows BIDS path guide (`WINDOWS_BIDS_PATH_GUIDE.md`) with troubleshooting tips
- Improved cross-platform X11 configuration with better error handling and user guidance
- Added OpenGL software rendering flags for better GUI compatibility across all platforms

#### Fixes

- Fixed volume mounting in docker-compose.yml - all required volumes now properly mounted to simnibs container
- Fixed Windows path handling - automatic conversion of backslashes to forward slashes for Docker compatibility
- Fixed paths with spaces on Windows - automatic quoting of paths containing spaces
- Fixed X11 socket mounting for macOS XQuartz and Linux compatibility
- Fixed DISPLAY environment variable configuration for Windows, macOS, and Linux
- Fixed MATLAB Runtime library paths in container environment
- Updated XQuartz version warning to reference memory about v2.7.7 compatibility requirement

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.2/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.2/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.2/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.1

**Release Date**: June 11, 2025

#### Additions

- new logger and report generators under 'projectDIR/derivatives/'
- sub-cortical atlas based targeting for flex-search (example: thalamus targeting)

#### Fixes

- 2 decimal spherical ROIs
- 'TI.py' overwrite protection removed
- intenral 185 EGI net (removed 2 missed electrodes)
- added imagemagick for montage visualizer

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.0

**Release Date**: May 28, 2025

#### Major Changes

- Complete rewrite of the Temporal Interference Toolbox with major enhancements: Cross-platform support for Windows, macOS, and Linux
- Docker-based containerization for consistent environment and reproducibility
- Dual interface with both GUI and CLI support, enabling local and remote server usage
- Key functionalities include DICOM to NIfTI conversion, FreeSurfer segmentation, SimNIBS head modeling, flexible and exhaustive electrode optimization algorithms, FEM-based temporal interference field calculations, and comprehensive analysis tools with atlas-based ROI evaluation

#### Installation

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.0/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.0/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.0/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

## Version Support

We actively support and maintain versions 2.x.x and newer of the Temporal Interference Toolbox. Versions 1.x.x are no longer supported.

## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/installation/troubleshooting/) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)

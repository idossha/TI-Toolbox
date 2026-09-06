# Lane R2 — FreeSurfer touch-point audit vs. charm/SimNIBS replacements

Repo: `/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui` (branch `feature/v3-electron-gui`)
SimNIBS source checkout: `/Users/idohaber/01_production/simnibs` (installed in container as 4.6.0)
Real dataset probed: `/Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie/m2m_ernie` (charm output, on disk, VERIFIED)
Container used for live checks: `tit-v3-spike` (`idossha/simnibs:v2.5.0`, x86_64 emulated), dataset bind-mounted at `/mnt/000`.

All claims below are tagged **VERIFIED** (I read the file / ran the command myself, cited) or **REPORTED** (a comment/doc says so, not independently confirmed).

---

## 1. Headline finding

The v3 codebase has **already done most of the FreeSurfer-removal work at the Python-API level**. Cortical ROI picking (mesh atlases), coarse subcortical ROI picking (whole-structure aseg-style labels), MNI registration, fsaverage projection for group stats, and EEG-forward source modeling are **all already charm/SimNIBS-native with zero FreeSurfer dependency** — verified by reading the code *and* by finding the charm-only artifacts already present on disk for `sub-ernie`, and by running SimNIBS's atlas function against that real m2m directory with no FreeSurfer installed in the calling process.

What's left that genuinely needs FreeSurfer falls into three buckets:
1. **True gaps** — thalamic-nuclei / hippocampal-subfield segmentation, and a combined volumetric cortex+aseg parcellation. No charm equivalent exists (SAMSEG's label set stops at whole-structure aseg granularity).
2. **Incidental binary calls** — `mri_segstats` (atlas region listing) and `mri_convert --reslice_like` (atlas resampling) are called even for charm's own `labeling.nii.gz`, purely as generic NIfTI-label utilities. These are FreeSurfer touch points that carry **no genuine FreeSurfer-specific data dependency** — they could be replaced by a few dozen lines of numpy/nibabel/scipy.
3. **Viewer/version-report cosmetics** — `freeview` binary, `$FREESURFER_HOME/VERSION` sniffing for the PDF report, dataset scaffolding. None block simulate/optimize/analyze.

---

## 2. Consumer-by-consumer table

| # | Consumer (file:line) | FreeSurfer artifact/binary consumed | charm/SimNIBS replacement (exact file) | Critical path? | Gap | Effort to drop FreeSurfer here |
|---|---|---|---|---|---|---|
| 1 | `tit/pre/recon_all.py:102` `run_recon_all()` | runs `recon-all -all` → `derivatives/freesurfer/sub-<id>/{mri,surf,label,...}` | n/a — whole step is optional (`run_recon` flag, unchecked by default; `tit/gui/pre_process_tab.py:179` checkbox "Run FreeSurfer recon-all") | **No** — `tit/pre/structural.py:223-254` runs `create_m2m`(charm)+`subject_atlas` in a block fully independent of `run_recon` (256-277) | — | Trivial: just stop offering the checkbox / stop calling it |
| 2 | `tit/pre/recon_all.py:32-61` `_run_subcortical_segmentations()` | `segmentThalamicNuclei.sh`, `segmentHA_T1.sh` (MATLAB-compiled) → `ThalamicNuclei.v13.T1.mgz`, `lh/rh.hippoAmygLabels-T1.v22.mgz` | **none** | No (optional flag `run_subcortical`) | **Real gap.** charm/SAMSEG (`labeling.nii.gz`, see #3) gives whole-thalamus / whole-hippocampus / whole-amygdala only, not the ~25 thalamic nuclei or hippocampal subfields (CA1-4, subiculum, DG, molecular layer, etc.) these scripts produce | High — would need a from-scratch nuclei/subfield segmentation model (see §4) |
| 3 | `tit/atlas/voxel.py:11-83` `VoxelAtlasManager` (`VOXEL_ATLAS_FILES`, `tit/atlas/constants.py:11-20`) | `aparc.DKTatlas+aseg.mgz`, `aparc.a2009s+aseg.mgz`, `lh/rh.hippoAmygLabels-T1.v22.mgz`, `ThalamicNuclei.v13.T1.mgz` from FreeSurfer `mri/` | **Partial**: `labeling.nii.gz` (m2m/segmentation/, SimNIBS SAMSEG output) is discovered by the same manager (`voxel.py:76-79`) | On the subcortical-ROI path of flex-search/ex-search/analyzer *if the user picks a FreeSurfer atlas*; charm's own `labeling.nii.gz` is always available as an alternative | See row 2 for subfields; `aparc*+aseg.mgz` also gives volumetric **cortical** labels charm doesn't produce (see §4) | Medium — drop the FreeSurfer entries from `VOXEL_ATLASES`, keep `labeling.nii.gz` + MNI atlases |
| 4 | `tit/atlas/voxel.py:108-149` `list_regions()` | shells out to **`mri_segstats --seg <atlas> --excludeid 0 --ctab-default --sum <out>`** for *every* voxel atlas, **including `labeling.nii.gz`** | n/a — this is a generic label-counting utility, not FreeSurfer data | Yes, whenever a user lists regions of any voxel atlas (even charm's own) in analyzer/flex/ex GUI or `GET /api/atlases/{id}/regions` | None — the LUT it needs is already parsed natively elsewhere: `tit/opt/roi_spec.py:494` `_load_freesurfer_lut()` parses a **bundled static** `FreeSurferColorLUT.txt` copy, and `labeling_LUT.txt`/`_parse_lut_line` (roi_spec.py:444-463) already read FreeSurfer-style LUTs without shelling out | **Small** — replace with `np.unique(nib.load(atlas).get_fdata())` + the LUT parser roi_spec.py already has |
| 5 | `tit/analyzer/analyzer.py:1191-1204` `_resample_if_needed()` | shells out to **`mri_convert --reslice_like <template> <atlas> <out>`** whenever a voxel atlas's grid ≠ the simulation field's grid | n/a — generic resampling, used for FreeSurfer atlases *and* charm's `labeling.nii.gz`/custom masks alike | **Yes** — on the Analyzer's voxel-ROI critical path any time atlas and field grids differ (routine, since FreeSurfer-conformed 256³ volumes and SimNIBS-native grids rarely match) | None functionally, but note: container has **no FSL/ANTs** (per project memory `feedback_verify_in_container.md`/`project_v250_e2e_validation.md`), so the replacement must be pure Python | **Small–Medium** — `nibabel` + `scipy.ndimage.affine_transform` (nearest-neighbor for label volumes) reproduces `--reslice_like`; nilearn is already a container dependency (`nilearn.image.resample_img` with `interpolation="nearest"`) is another option |
| 6 | `tit/atlas/mesh.py` `MeshAtlasManager` | reads `.annot` **only from `seg_dir` = `m2m_<id>/segmentation/`** (charm's own output) | Already 100% charm — no FreeSurfer path exists in this class at all | Yes — cortical ROI picking for flex-search/ex-search/analyzer | **None.** VERIFIED on real data: `lh.ernie_DK40.annot`, `lh.ernie_a2009s.annot`, `lh.ernie_HCP_MMP1.annot` (+ rh) already sit in `m2m_ernie/segmentation/` (`ls` output below) | Done already |
| 7 | `tit/pre/charm.py:117-184` `run_subject_atlas()` | calls SimNIBS's own `subject_atlas` CLI (`a2009s`, `DK40`, `HCP_MMP1`) → writes the `.annot` files consumed by row 6 | `simnibs/cli/subject_atlas.py` → `simnibs.utils.transformations.atlas2subject()` — **VERIFIED**: ran `atlas2subject(m2m_ernie, "DK40", split_labels=True, ...)` directly in-container against the real m2m; 36 named regions/hemi (incl. `unknown`), **0.65 s** in-process, no FreeSurfer on `PATH` needed | Yes — runs automatically right after charm in `structural.py:242-251` | None | Done already |
| 8 | `tit/source/fsaverage.py:160-235` `_compute_fields()` | `cross_subject_map(subject_files, "fsaverage", ...)`, `mesh_io.load_subject_surfaces(subject_files, "central")` | Uses charm's own `m2m/surfaces/{lh,rh}.central.gii`, `sphere.reg.gii` (fsaverage registration) **+ SimNIBS's bundled fsaverage templates** — VERIFIED present inside the installed package: `simnibs/resources/templates/{fsaverage_surf,fsaverage_atlases,fsaverage10k_surf,fsaverage10k_atlases,fsaverage40k_surf,fsaverage40k_atlases}` (shipped in the pip wheel, not derived from any FreeSurfer install) | Yes for group-level fsaverage stats (`tit/stats/surface.py`) | None | Done already (matches project memory `project_fsaverage_surface_pipeline.md`) |
| 9 | `tit/source/forward.py`, `tit/source/config.py` | — | EEG-forward leadfield/source-space pipeline; grepped for `freesurfer|SUBJECTS_DIR|bem|watershed` — **zero hits** | Yes for EEG source reconstruction | None found | Done already |
| 10 | `tit/opt/roi_spec.py:235-268` `resolve_volume_atlas_path()` | dispatches `labeling.nii.gz` → `seg_dir` (charm), everything else → `freesurfer_mri_dir` | Same dual-source design as row 3 | Yes — flex-search/ex-search subcortical ROI resolution | Same as row 3 | Same as row 3 |
| 11 | `tit/gui/ex_search_tab.py:2396,2476,2575` | sets `env["SUBJECTS_DIR"] = project_dir` before launching ex/mex-search subprocess pipelines | — | Unclear — **could not find a downstream reader** of this env var in `tit/opt/ex/engine.py` in the time available | **Open question**, flagged not confirmed | Looks like vestigial plumbing; needs a follow-up grep of the ex-search engine's own env reads before deleting |
| 12 | `tit/reporting/generators/base_generator.py:118-124`, `reportlets/text.py:338-343`, `generators/preprocessing.py:242-246,463-464`, `reportlets/references.py:183-444` | reads `$FREESURFER_HOME/build-stamp.txt`/`VERSION` for a "software versions" field; conditionally emits a "Cortical reconstruction was performed using FreeSurfer X" sentence; lists `derivatives/freesurfer/sub-<id>` as an output *only if* a recon step ran; cites Fischl 2012 conditionally | — | **No** — every one of these is gated behind `if self.parameters.get("freesurfer_version")` / `if "freesurfer" in step_names` | Cosmetic — report simply omits the section | Trivial |
| 13 | `tit/gui/nifti_viewer_tab.py:60-75,424-428,1273` `detect_freesurfer_atlases()` | thin wrapper around `VoxelAtlasManager(freesurfer_mri_dir=...)` (row 3) | same as row 3 | No — viewer works without it, just offers fewer overlay atlases | Same as row 3 | Same as row 3 |
| 14 | `tit/server/routes/capabilities.py:20-52` `probe_capabilities()` | checks `$FREESURFER_HOME/bin/recon-all` and `freeview` existence only (no data read) | `Capabilities.freesurfer` / `Capabilities.has_freesurfer` (`tit/server/schemas.py:31,171`) already exists as a **graceful-degradation seam** for the Electron UI to grey out FreeSurfer-only affordances | — | None | **This is the cleanest lever for the maintainer's ask** — the UI-capability contract to hide FreeSurfer already exists; flipping the underlying probe to always return `False` (or removing the freesurfer service) is close to a complete UI-level cutover already |
| 15 | `tit/constants.py:715-716` | `FS_LICENSE_PATH = "/usr/local/freesurfer/license.txt"` hard-coded, comment: "always present in SimNIBS container" | — | check callers | Comment is stale relative to the current 2-container split (see §3) — worth a follow-up grep for actual callers | Small doc fix |
| 16 | `tit/jobs/plans.py:60,140`; `tit/server/routes/plan.py:549`; `tit/jobs/locks.py:285` | pipeline-DAG bookkeeping: step `"G2b"` = recon-all, output path = `pm.freesurfer_subject(sid)`, its own lock domain (deliberately separate from the m2m lock) | — | No — optional DAG node | None | Small — delete the DAG node |
| 17 | `tit/project_init/initializer.py:115,123,307,322-323`; `example_data_manager.py:189,346,355` | scaffolds an empty `derivatives/freesurfer/` BIDS folder + `dataset_description.json` at project-init time | — | No | None | Trivial |
| 18 | `tit/pre/utils.py:37,264-268` | `"freesurfer"` entry in the BIDS dataset-description table | — | No | None | Trivial |

**VERIFIED directory listing** for `m2m_ernie` (charm output only, no recon-all ever run against this m2m per the task's framing — full recursive listing was captured and is summarized in §3):
```
m2m_ernie/segmentation/: labeling.nii.gz, labeling_LUT.txt, lh.ernie_{a2009s,DK40,HCP_MMP1}.annot,
                          rh.ernie_{a2009s,DK40,HCP_MMP1}.annot, massp2021_subject.nii.gz,
                          atlas_level{1,2}.txt.gz, T1/T2_bias_corrected.nii.gz, template_coregistered.mgz
m2m_ernie/surfaces/:     lh/rh.{central,pial,white,sphere,sphere.reg}.gii (+ .sigma files)
m2m_ernie/toMNI/:        Conform2MNI_nonl.nii.gz, MNI2Conform_nonl.nii.gz, final_tissues_MNI.nii.gz
m2m_ernie/label_prep/:   tissue_labeling_upsampled.nii.gz + LUT, T1/T2_upsampled.nii.gz, upper_part.nii.gz
m2m_ernie/ (root):       final_tissues.nii.gz + LUT (FEM tissue types, distinct from labeling.nii.gz — see §3),
                          T1.nii.gz, T2_reg.nii.gz, ernie.msh(.opt), charm_report.html, eeg_positions/
```

---

## 3. What charm already writes into `m2m_<id>`, and what it's for

Directly `ls -R`'d against the real dataset (`/Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie/m2m_ernie`) — VERIFIED, no FreeSurfer artifacts present anywhere in this tree:

| charm output | Purpose | FreeSurfer-provided equivalent it substitutes for |
|---|---|---|
| `surfaces/{lh,rh}.{central,pial,white}.gii` | Cortical surfaces (central used for TI-normal mapping, GM interpolation) | `lh/rh.{white,pial}` |
| `surfaces/{lh,rh}.sphere.gii`, `.sphere.reg.gii` | Native + **fsaverage-registered** sphere, used by `cross_subject_map` for fsaverage projection | `lh/rh.sphere`, `lh/rh.sphere.reg` |
| `segmentation/{lh,rh}.ernie_{DK40,a2009s,HCP_MMP1}.annot` | Cortical ROI picking (surface atlases) | `lh/rh.aparc.annot`, `lh/rh.aparc.a2009s.annot` (+ HCP_MMP1, which FreeSurfer doesn't even ship natively) |
| `segmentation/labeling.nii.gz` + `labeling_LUT.txt` | Whole-head SAMSEG-style anatomical labels — **VERIFIED contains** `Left/Right-Thalamus-Proper`, `-Putamen`, `-Caudate`, `-Pallidum`, `-Hippocampus`, `-Amygdala`, `-Accumbens-area`, `-VentralDC` (same names/IDs as FreeSurfer's aseg LUT) plus head-tissue classes (Bone-Cortical, Skin, Eyes, etc.) | `aseg.mgz` at whole-structure granularity — **not** nuclei/subfield granularity |
| `final_tissues.nii.gz` + `final_tissues_LUT.txt` (m2m root) | FEM tissue conductivity classes (WM/GM/CSF/Bone/Scalp/...) used for the simulation mesh itself — distinct purpose from `labeling.nii.gz` | no FreeSurfer equivalent (this is SimNIBS-native regardless) |
| `toMNI/Conform2MNI_nonl.nii.gz`, `MNI2Conform_nonl.nii.gz` | Nonlinear subject↔MNI warps | FreeSurfer's `talairach.m3z`/`mri_vol2vol -reg` path for MNI transforms |
| `segmentation/massp2021_subject.nii.gz` | A MASSP subcortical atlas **already registered to subject space by charm itself** | n/a — no FreeSurfer role either way; **note**: `tit/atlas/constants.py:30-37` only wires up the MNI-space MASSP file (`MNI_ATLAS_FILES`) for on-the-fly MNI→subject warping; this already-subject-space file sitting in `segmentation/` is not currently discovered by `VoxelAtlasManager` — a small missed-opportunity, not a FreeSurfer question |
| `charm_report.html`, `charm_log.html` | charm's own QC report | FreeSurfer's `recon-all` QC pages |

**`simnibs.atlas2subject()` API — VERIFIED live**:
```
$ docker exec tit-v3-spike simnibs_python -c "
from simnibs import atlas2subject
labels, ctab, names = atlas2subject('/mnt/000/.../m2m_ernie', 'DK40', split_labels=True, return_ctab=True, return_names=True)
"
hemis: ['lh', 'rh']
lh n_regions (split_labels dict): 36
lh region names sample: ['unknown', 'bankssts', 'caudalanteriorcingulate', 'caudalmiddlefrontal', ...]
elapsed: 0.65s (in-process; ~3s wall including simnibs_python interpreter startup)
```
Note for the maintainer: the Python-level entry points in the installed SimNIBS 4.6.0 are `simnibs.atlas2subject` and `simnibs.get_atlas` — **not** `simnibs.subject_atlas` (that name only exists as the CLI script `subject_atlas`, `simnibs/cli/subject_atlas.py`, which wraps `atlas2subject`). Source: `simnibs/utils/transformations.py:2047` (checkout) and live `inspect.signature` in-container.

The three atlas names are hard-capped by SimNIBS itself: `choices=["a2009s", "DK40", "HCP_MMP1"]` (`simnibs/cli/subject_atlas.py:79`) — confirms project memory `project_calc_api_botzanowski.md`-adjacent fact that this list is fixed upstream, not a TI-Toolbox choice.

A known SimNIBS 4.6 bug in `atlas2subject`'s `split_labels=True` path (mismatched `np.unique`/`names` ordering for DK40) is already patched at Docker build time by `resources/atlas2subject/patch_atlas2subject.py` — VERIFIED file content, consistent with project memory.

---

## 4. The real, unreplaceable gap

Everything charm/SimNIBS does NOT provide, confirmed by absence in the `m2m_ernie` listing and by reading `recon_all.py`:

1. **Thalamic-nuclei parcellation** (`segmentThalamicNuclei.sh`, Iglesias et al. probabilistic atlas) — ~25 named nuclei vs. charm's single `Thalamus-Proper` label. No SimNIBS equivalent.
2. **Hippocampal-subfield / amygdala-nuclei parcellation** (`segmentHA_T1.sh`) — CA1-4, subiculum, dentate gyrus, molecular layer, fimbria, hippocampal fissure, HATA, etc., vs. charm's single `Hippocampus`/`Amygdala` labels. No SimNIBS equivalent.
3. **A single volumetric parcellation combining cortical-ribbon atlas labels with subcortical aseg** (FreeSurfer's `aparc.DKTatlas+aseg.mgz` / `aparc.a2009s+aseg.mgz`, produced by `mri_aparc2aseg`) — charm gives cortical labels only as **surface** `.annot` and subcortical labels only as **undifferentiated** `Cerebral-Cortex` in `labeling.nii.gz`. Voxelizing the surface `.annot` onto the volume to reconstruct this combined product is not something SimNIBS ships; it would be custom code (surface-to-volume label rasterization — moderate effort, well-understood problem, e.g. nearest-vertex projection per voxel within a cortical-ribbon mask).
4. **QSIPrep/QSIRecon's own internal FreeSurfer use for anatomically-constrained tractography** (`mrtrix_*_ACT-hsvs`/`ACT-fast` recon specs, `tit/gui/components/qsi_config_dialogs.py:196-216`) — this is FreeSurfer running *inside the third-party `pennlinc/qsiprep`/`pennlinc/qsirecon` containers*, orthogonal to TI-Toolbox's own `freesurfer_container`. REPORTED only (I did not audit qsiprep's own source in this pass) that `ACT-fast` genuinely needs FreeSurfer despite its "FSL FAST" name — flag as an open question. The toolbox's actual DWI use case for SimNIBS anisotropic conductivity (`dsi_studio_gqi`, `tit/gui/components/qsi_config_dialogs.py:183-187`) does **not** need FreeSurfer, and `mrtrix_*_noACT` variants exist as fallbacks.

None of these four gaps sit on the simulate/optimize/analyze/view critical path for a typical TI-Toolbox run — they are opt-in extras (subcortical-subfield ROI targeting, or DWI tractography quality options).

---

## 5. What the FreeSurfer container is used for beyond recon-all (VERIFIED)

`container/blueprint/Dockerfile.freesurfer` (read in full):
- Ubuntu 22.04 + the **official FreeSurfer 7.4.1 `.deb`** from `surfer.nmr.mgh.harvard.edu`.
- `RUN /usr/local/freesurfer/bin/fs_install_mcr R2019b` — installs the **MATLAB Runtime R2019b**, needed *only* so `segmentThalamicNuclei.sh`/`segmentHA_T1.sh` (MATLAB-compiled binaries) can run. `recon-all` itself does not need it. This MCR install is very likely the single biggest contributor to the reported 67 GB image size, and it exists solely to support the "real gap" items in §4 #1-2.
- Sets `FREESURFER_HOME`, `SUBJECTS_DIR`, `FS_LICENSE`, prepends `$FREESURFER_HOME/bin` to `PATH`.
- No X11/GUI packages beyond the minimal X11 client libs (`libx11-6`, `libxt6`, `libxext6`) needed for `freeview` to render — this container does not itself run `freeview`; it just *hosts the binary*.

**Architecture (VERIFIED from `docker-compose.yml:1-58`, mirrored in `desktop/docker/docker-compose.v3.yml`, `dev/loader/docker-compose.dev.yml`, `package/docker/docker-compose.yml`):**
- `freesurfer` service (image `idossha/ti-toolbox_freesurfer:v7.4.1`) mounts a **named Docker volume** `freesurfer_data` at `/usr/local/freesurfer/` and just idles (`restart: unless-stopped`) — its only job is to seed that volume with the FreeSurfer install (and MATLAB Runtime) on first boot.
- `simnibs`/`tit` service **mounts the same volume** (`docker-compose.yml:17`) plus `FREESURFER_HOME`/`SUBJECTS_DIR`/`FS_LICENSE` env vars (lines 26-28) and `depends_on: freesurfer`.
- `container/blueprint/entrypoint.sh:10`: `[ -f "$FREESURFER_HOME/SetUpFreeSurfer.sh" ] && source "$FREESURFER_HOME/SetUpFreeSurfer.sh"` — this is what actually puts FreeSurfer's `bin/` (and MCR paths) onto `PATH` **inside the `tit` container itself**. So every FreeSurfer binary call from Python (`recon-all`, `mri_convert`, `mri_segstats`, `segmentThalamicNuclei.sh`, `freeview`) runs as an ordinary subprocess **in the same container process** that runs `tit` — there is no cross-container `docker exec`/RPC to replace, just a shared bind volume + a sourced setup script. That does mean the `tit` container has a **hard runtime dependency on the freesurfer volume having been populated at least once**.

Beyond recon-all + subcortical segmentation, the `freesurfer_data` volume/container is used for:
- **`freeview`** (`$FREESURFER_HOME/bin/freeview`) — TI-Toolbox's NIfTI/surface/mesh viewer, launched over X11 (`tit/server/routes/viewers.py`, `tit/viewspec.py:753-781`, `desktop/src/main/x11.ts`). This is the piece the maintainer's broader Tetravox-replacement plan is already targeting (see `tracks/active/v3-electron-gui.md` per repo context) — orthogonal to recon-all, but shares the same container/volume today.
- **`mri_convert`** and **`mri_segstats`** as generic NIfTI utilities (rows 4-5 above), called even on charm-only data.
- **`FS_LICENSE`** staging (`.freesurfer_license.txt`) is *also* copied into the project directory for QSIPrep/QSIRecon's own sibling containers (`tit/pre/qsi/docker_builder.py:53-113`) — a second, independent consumer of the FreeSurfer license file beyond TI-Toolbox's own container.

`tit/server/routes/capabilities.py:20-52` already probes `$FREESURFER_HOME/bin/recon-all` and `freeview` presence and surfaces `Capabilities.freesurfer`/`has_freesurfer` to the Electron UI (`tit/server/schemas.py:31,171`) — i.e., **the codebase already has a capability-gated seam for a FreeSurfer-less runtime**; removing the freesurfer container/volume would make these probes return `False` and (per the existing schema contract) the UI is already designed to grey out the affected controls rather than crash.

---

## 6. Answering the maintainer's framing directly

> "find a replacement for the freesurfer recon-all step that parcellates the brain"

Two separate things are bundled in that sentence, and they have very different answers:
- **Cortical parcellation** (DK40/Destrieux/HCP_MMP1 atlases) — **already solved**, no replacement needed. `subject_atlas`/`atlas2subject` does this from charm's m2m alone (§3), verified working and fast (<1s) against the real dataset.
- **Subcortical *subfield* parcellation** (thalamic nuclei, hippocampal subfields) — **genuinely unsolved**, and it's the one piece FastSurfer (raised in the maintainer's question) doesn't solve either: FastSurfer's own subfield modules (`FastSurferVINN`+ optional `HypVINN`/`recon_surf`-adjacent extensions) still wrap FreeSurfer's own `segmentThalamicNuclei.sh`/`segmentHA_T1.sh` scripts for anything below whole-structure aseg granularity in most published configurations (REPORTED — not verified in this pass, since it's outside this lane's file set; flag for whichever lane evaluates FastSurfer specifically). If subfield-level ROI targeting is a hard requirement for the product, replacing recon-all does not remove the FreeSurfer/MATLAB-Runtime dependency for that specific feature; it only removes it for everything else (cortical/whole-structure work), which — per this audit — is already removed at the code level.

---

## 7. Effort summary

| Item | Effort | Blocking? |
|---|---|---|
| Drop `run_recon_all` step + GUI checkbox + DAG node + report sentences | Trivial | No |
| Drop `aparc*+aseg.mgz` from `VOXEL_ATLASES`, keep `labeling.nii.gz`+MNI | Small | No |
| Replace `mri_segstats` region-listing call with numpy+existing LUT parser | Small | No |
| Replace `mri_convert --reslice_like` with nibabel/scipy or nilearn resampling | Small–Medium | Yes, if FreeSurfer container is fully removed (currently used for **every** voxel atlas resample, not just FreeSurfer ones) |
| Drop `freeview` (separate from this lane; Tetravox already the planned replacement) | — | — |
| Replace thalamic-nuclei / hippocampal-subfield segmentation | High / open research question | Only if the product commits to subfield-level ROI targeting as a feature |
| Volumetric cortex+aseg combined parcellation (if ever needed) | Medium (surface→volume rasterization, no upstream tool) | Only if a user-facing feature needs it |
| Untangle vestigial `SUBJECTS_DIR=project_dir` in `ex_search_tab.py` | Small investigation | Should be checked before deleting FreeSurfer env plumbing |

---

## 8. Commands run (for reproducibility)

```
rg -n -i "recon.?all|freesurfer|FREESURFER_HOME|SUBJECTS_DIR|FS_LICENSE|\.annot|aparc|aseg|mri_convert|mri_[a-z]+|mris_[a-z]+|fsaverage" tit --type py -l
docker inspect tit-v3-spike --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
ls -R /Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie/m2m_ernie
docker exec tit-v3-spike simnibs_python -c "from simnibs import atlas2subject; ..."  # DK40, 0.65s, 36 regions/hemi
docker exec tit-v3-spike simnibs_python -c "import simnibs; print(simnibs.__version__)"  # 4.6.0
docker exec tit-v3-spike simnibs_python -c "... glob simnibs/resources/templates/fsaverage*"  # bundled templates
```

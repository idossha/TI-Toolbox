# W3b — Preprocessing: FastSurfer in, FreeSurfer out

Lane W3b of `dev/notes/v3-docker-streamline-plan.md` (decision D2). Phase A, 2026-09-03.

Evidence base: `dev/notes/v3-native-research/r2-freesurfer-audit.md` (touch-point table),
`dev/spikes/native/fastsurfer/REPORT.md` (invocation, `--no_cc`, Dice, timing),
`dev/spikes/native/fs-binaries/REPORT.md` (`segstats.py` already replaces `mri_segstats`).

---

## 1. What changed

### New stage: `tit/pre/fastsurfer.py`

```
run_fastsurfer.sh --seg_only --no_cereb --no_hypothal --no_cc \
  --sid sub-<id> --sd <project>/derivatives/fastsurfer \
  --t1 <project>/sub-<id>/anat/sub-<id>_T1w.nii.gz \
  --device cpu --threads <n> --py simnibs_python
```

Public surface: `fastsurfer_available()`, `fastsurfer_home()`, `fastsurfer_script()`,
`fastsurfer_python()`, `resolve_threads()`, `run_fastsurfer()`, `write_derived_outputs()`.

Outputs, all under `derivatives/fastsurfer/sub-<id>/mri/`:

| File | Written by | Why |
|---|---|---|
| `aparc.DKTatlas+aseg.deep.mgz` | FastSurfer | the parcellation itself |
| `aparc.DKTatlas+aseg.deep.nii.gz` | this module | readers that cannot open MGH (the viewer, `/api/files/raw`) |
| `aparc.DKTatlas+aseg.deep_labels.txt` | this module, via `tit.atlas.segstats` | the `mri_segstats --sum` sidecar `VoxelAtlasManager.list_regions` caches on |

Both atlas filenames derive the *same* sidecar name through `list_regions`'s own
stem rule, so one file serves both.

**Decisions, with the reasoning:**

- **Input = raw BIDS T1w, not `m2m_<id>/T1.nii.gz`.** Two load-bearing reasons.
  (a) It keeps this stage independent of charm, which is what lets G2a and G2b run
  in parallel after G1 in `tit/jobs/plans.py`. (b) The raw T1w is what `recon-all`
  was given and what the N0.2 spike measured its Dice numbers on; charm's copy is
  bias-corrected and re-conformed, a different input with unmeasured effect on the
  network.
- **`--no_cc` is passed unconditionally.** The N0.2 spike showed the corpus-callosum
  module downloads 81 MB of checkpoints the toolbox never uses and then crashed
  (`OSError: ... callosum.CC.orig.mgz`) *after* the segmentation was already saved.
- **`--py simnibs_python`** by default, overridable with `$TIT_FASTSURFER_PYTHON`.
  In the image, torch is already a charm dependency (`brainnet` requires
  `torch>=2.1`, FastSurfer pins `torch==2.7.*` — compatible per the spike), so
  there is no second venv to point at.
- **Threads.** `run_fastsurfer(..., threads=)` → `$TIT_FASTSURFER_THREADS` →
  `DEFAULT_THREADS = 2`. Two, not `cpu_count()`, because the `pre` job kind's
  budget in `tit/jobs/costs.py` is `Cost(cpus=2, mem_gb=6)` and FastSurfer's peak
  RSS is 4.84 GiB — it fits that budget as it stands, and a caller with a larger
  budget passes it explicitly. The GUI's spin box defaults to 2 as well.
- **Idempotent.** An existing `.mgz` short-circuits the run; the derived NIfTI and
  labels are still backfilled so an older run is brought up to the current layout.
- **NIfTI writing goes through a tempdir + stdlib `gzip`**, the same workaround
  `tit/pre/qsi/dti_extractor._save_nifti_gz` uses — nibabel's gzip writer is
  unreliable on Docker bind mounts.

### `PreprocessConfig` (exact diff for W3a's schema regeneration)

```diff
     convert_dicom: bool = False
-    run_recon: bool = False
-    parallel_recon: bool = False
-    parallel_cores: int | None = None
+    run_fastsurfer: bool = False
+    fastsurfer_threads: int | None = None
     create_m2m: bool = False
     run_tissue_analysis: bool = False
     run_qsiprep: bool = False
     run_qsirecon: bool = False
     qsiprep_config: QSIPrepSettings | None = None
     qsi_recon_config: QSIReconSettings | None = None
     extract_dti: bool = False
-    run_subcortical_segmentations: bool = False
     skip_existing_outputs: bool = False
     replace_existing_outputs: bool = False
```

`run_pipeline` mirrors it: `run_fastsurfer` / `fastsurfer_threads` in, `run_recon` /
`parallel_recon` / `parallel_cores` / `run_subcortical_segmentations` out.

**Deviation from the brief, deliberate:** the brief asked for `run_fastsurfer:
bool` "default True when a T1 exists". A dataclass default cannot look at the
filesystem, and every other step flag in this config is opt-in `False` — flipping
one to `True` would make `PreprocessConfig(subject_ids=[...])` silently start a
5-minute GPU-less inference. So the *field* defaults to `False`, the *GUI
checkbox* defaults to checked, and preflight refuses the step without a BIDS T1w
(`STEP_FASTSURFER` reuses the existing `_has_bids_t1` gate).

**Deprecated aliases.** `tit/pre/config.py` gains `LEGACY_KEYS` and
`migrate_legacy_keys(data, *, logger=None)`, called by `tit/pre/__main__._build_config`
before deserialization: `run_recon` → `run_fastsurfer` with a warning;
`parallel_recon`, `parallel_cores`, `run_subcortical_segmentations` dropped with a
warning. An explicit `run_fastsurfer` wins over an old `run_recon`.

### DAG (`tit/jobs/plans.py`)

`G2b` is now FastSurfer: `after_labels=[G1]` (unchanged — it only needs the raw
T1w), `tags=["G2b", "fastsurfer"]`, gated on `config.run_fastsurfer`. `G2a` (charm)
and `G2b` still have no edge between them, so the scheduler runs them in parallel.
`_STAGE_FLAGS` lost `run_recon` and `run_subcortical_segmentations`, gained
`run_fastsurfer`.

**Cost:** unchanged. Costs are per *kind*, not per stage, and `pre` is already
`Cost(cpus=2, mem_gb=6)` — which is the right size for FastSurfer's measured
4.84 GiB / 2-thread default, and smaller than the multi-hour recon-all it replaces
in wall clock (~5 min native / to be measured emulated, vs. 6–10 h).

**Locks:** `tit/jobs/locks.py::_PRE_STAGE_FLAGS` maps `run_fastsurfer` →
stage `fastsurfer` (was `run_recon`/`run_subcortical_segmentations` → `recon`).
`fastsurfer` stays out of `_WRITES_M2M`, so G2a and G2b hold disjoint lock domains.
**This file is outside W3b's stated grant** — see §5.

### Discovery

| Layer | Change |
|---|---|
| `tit/paths.py` | `fastsurfer()`, `fastsurfer_subject()`, `fastsurfer_mri()`, `list_fastsurfer_subjects()`. `freesurfer*` kept and documented as legacy read-only. |
| `tit/atlas/constants.py` | `FASTSURFER_ATLASES` (`aparc.DKTatlas+aseg.deep.mgz`, `.nii.gz`) + `LEGACY_FREESURFER_ATLASES` (the five recon-all names, unchanged); `VOXEL_ATLASES` is their merge, FastSurfer first. Also now hosts `mni_resources_dir()` — see §5. |
| `tit/atlas/voxel.py` | `VoxelAtlasManager(fastsurfer_mri_dir=...)`; `list_atlases()` searches FastSurfer → legacy FreeSurfer → `segmentation/labeling.nii.gz` → `masks/`, first match per name. `segstats.py`'s API untouched. |
| `tit/catalog.py` | `subject_ids()` unions FastSurfer subjects; `list_subjects()`/`subject()` gain `has_fastsurfer` (additive, `has_freesurfer` kept); `subject_info_matrix()` gains a `fastsurfer` column before `freesurfer`; both `VoxelAtlasManager` constructions pass `fastsurfer_mri_dir`. |
| `tit/opt/roi_spec.py` | `resolve_volume_atlas_path(..., fastsurfer_mri_dir="")` searched first (falls back to the legacy dir if the file is not there); threaded through `get_roi_spec`. |
| `tit/gui/**` | `analyzer_tab`, `nifti_viewer_tab`, `components/roi_picker` pass `fastsurfer_mri_dir`; `roi_picker._selected_volume_atlas_path` now delegates to `resolve_volume_atlas_path` instead of hard-coding `pm.freesurfer_mri`. |

Subcortical ROI defaults are unchanged — they come from charm's
`segmentation/labeling.nii.gz`, which was already FreeSurfer-free.

### Removals

- `tit/pre/recon_all.py` (deleted): `run_recon_all`, `run_subcortical_segmentations`,
  `_run_subcortical_segmentations` (`segmentThalamicNuclei.sh` / `segmentHA_T1.sh`,
  the only reason the FreeSurfer image carried the MATLAB Runtime).
- `tests/test_pre_recon_all.py` (deleted).
- `tit/pre/structural.py`: the whole `parallel_recon` ThreadPoolExecutor branch
  (phases 1/2/3). Subjects now run one at a time; parallelism across subjects is
  the scheduler's memory-budgeted decision, not a thread pool inside the loop —
  FastSurfer peaks at 4.84 GiB per subject.
- `tit/gui/pre_process_tab.py`: the "Run FreeSurfer recon-all" checkbox, the
  "Run recon-all in parallel" checkbox + cores spin box and its validation dialog;
  replaced by one "Run FastSurfer segmentation" checkbox + a threads spin box.
- `tit/gui/ex_search_tab.py`: three `env["SUBJECTS_DIR"] = project_dir` assignments
  and the matching debug-log entry. r2 row 11 flagged these as possibly vestigial;
  confirmed — `rg SUBJECTS_DIR tit/opt` returns nothing, no reader exists.
- `tit/constants.py`: `TELEMETRY_OP_PRE_RECON_ALL` → `TELEMETRY_OP_PRE_FASTSURFER`.

### FS license

Only QSIPrep/QSIRecon still need one (their own ACT recon specs run FreeSurfer
*inside the pennlinc images*). New single helper
`tit/pre/qsi/docker_builder.resolve_fs_license_path()`: `$FS_LICENSE` →
`tit.constants.FS_LICENSE_PATH` → `None`. A missing file is not an error — the
license mount is simply omitted and only ACT specs fail, with QSIPrep's own
message. `_stage_fs_license` now calls it.

### Verification of the brief's grep

```
$ rg -n "recon-all|recon_all|segmentThalamic|segmentHA|FREESURFER_HOME|SUBJECTS_DIR" tit
```
19 hits, every one justified:
- 12 are prose in docstrings/comments explaining the legacy reader path
  (`paths.py`, `catalog.py`, `atlas/constants.py`, `atlas/voxel.py`,
  `pre/config.py`, `pre/fastsurfer.py`, `pre/utils.py`, `opt/roi_spec.py`,
  `atlas/segstats.py`'s provenance note).
- 2 in `tit/server/routes/system.py` (`"recon-all"`, `"pre/recon_all.py"` process
  keywords) — W3a's file, diff in §4.
- 1 in `tit/reporting/generators/base_generator.py` (`FREESURFER_HOME` version
  sniff, already gated behind `if freesurfer_version`) — unowned, §4.
- 0 hits for `segmentThalamicNuclei` / `segmentHA` / `SUBJECTS_DIR`.

---

## 2. Measured numbers

Real data, `/Users/idohaber/datasets/000`, host (macOS, py3.14) and container
(`tit-v3-spike`, linux/amd64 emulated, py3.11).

**Derived-output writer on ernie's real `aparc.DKTatlas+aseg.mgz`** (copied to a
scratch project as `aparc.DKTatlas+aseg.deep.mgz`, i.e. exactly the shape
FastSurfer produces):

| Measurement | Value |
|---|---|
| `write_derived_outputs` wall clock | **1.46 s** |
| `.mgz` → `.nii.gz` voxel differences | **0 / 16,777,216** |
| affine max abs difference | **0.0** |
| dtype preserved | `>i4` → `int32` (integer labels, not floats) |
| unique label values preserved | 103 → 103 |
| labels written to the sidecar | **102** — the same 102 the fs-binaries spike matched against live `mri_segstats` |
| output sizes | mgz 436,786 B · nii.gz 397,085 B · labels 5,744 B |

**Discovery on dataset 000** (host and container agree exactly):

```
list_fastsurfer_subjects() -> []
list_freesurfer_subjects() -> ['ernie', 'MNI152']       # legacy, still listed
subject_info_matrix cols   -> [subject, raw, fastsurfer, freesurfer, m2m, dwi, ct, simulations]
  ernie   [True, False, True, True, False, False, 6]
  101     [True, False, False, True, False, False, 2]
  MNI152  [True, False, True, True, False, False, 1]
atlases(ernie) -> aparc.DKTatlas+aseg.mgz, aparc.a2009s+aseg.mgz,
                  lh/rh.hippoAmygLabels-T1.v22.mgz, ThalamicNuclei.v13.T1.mgz,
                  labeling.nii.gz
fastsurfer_available() -> False   (tit-v3-spike has no /opt/fastsurfer; W2's image will)
```

With a FastSurfer tree present, `list_atlases()` returns
`['aparc.DKTatlas+aseg.deep.mgz', 'aparc.DKTatlas+aseg.deep.nii.gz']` first and the
legacy names after — asserted by `test_fastsurfer_dir_searched_before_freesurfer`.

**Gates:**

| Gate | Result |
|---|---|
| Host, full suite | **`1 failed, 3141 passed, 18 skipped in 34.77s`** — the one failure needs a W3a edit, see §3 |
| Container, this lane's modules + the routes that consume them (18 files) | **`539 passed, 1 skipped in 4.15s`** |
| Host, same 18 files | `446 passed, 1 skipped in 0.70s` (subset without the server routes: `446 passed`) |
| `black --check` on 44 touched files | `44 files would be left unchanged` |

The single skip is `test_pre_fastsurfer.py`'s integration test
(`requires a FastSurfer checkout at $FASTSURFER_HOME`) — it stops skipping in W2's
image.

---

## 3. The one remaining host failure

`tests/test_server_skeleton.py::test_process_filter_matches_qt_list`.

It asserts `tit/server/routes/system.py::RELEVANT_KEYWORDS` is byte-equal to the
process-keyword list in `tit/gui/system_monitor_tab.py`, which W3b updated
(`freesurfer` / `recon-all` / `pre/recon_all.py` → `fastsurfer` /
`run_fastsurfer.sh` / `pre/fastsurfer.py` — the last of those named a file that no
longer exists). Both the route module and that test file are W3a's; the exact
diff is in §4. Nothing else in the suite fails.

Mid-lane note, since it shaped the working numbers: for most of this lane's
runtime the host suite showed ~250 errors from a collection-time
`ImportError: cannot import name 'jail_roots' from 'tit.viewspec'` while W3a's
`tit/viewspec.py` + `tit/server/**` rewrite was in flight. That cleared on its own
when W3a landed. One casualty was real and is documented in §5 item 6:
`mni_resources_dir` left `tit/viewspec.py` and `tit/catalog.py` imported it.

`tests/test_plan_routes.py` needed `run_recon` → `run_fastsurfer` in its POST
payload (two lines, test data only); done here — see §5.

---

## 4. Exact diffs needed from other lanes

### W3a — `tit/server/routes/plan.py`
```diff
-        "G2b": pm.freesurfer_subject(sid),
+        "G2b": pm.fastsurfer_subject(sid),
```
(`_pre_stage_output_dir`, ~line 549.) The route itself needs no flag change — it
hands the config dict to `PreprocessConfig`, which now carries `run_fastsurfer`.
Worth considering as a follow-up: call
`tit.pre.config.migrate_legacy_keys(...)` on the incoming `pre` config so an old
HTTP client sending `run_recon` gets the same alias the CLI entry point already
honours. Without it, `POST /api/plan/pre` silently drops the old key and plans no
G2b (that is exactly what made
`tests/test_plan_routes.py::test_plan_pre_builds_full_dag_for_two_subjects` fail).

### W3a — `tit/server/routes/system.py`
```diff
     "charm",
     "simnibs",
-    "freesurfer",
-    "recon-all",
+    "fastsurfer",
+    "run_fastsurfer.sh",
     "dcm2niix",
...
     "pre/charm.py",
-    "pre/recon_all.py",
+    "pre/fastsurfer.py",
```
(`tests/test_server_skeleton.py::test_process_filter_matches_qt_list` asserts this
matches `tit/gui/system_monitor_tab.py`, already updated.)

### W3a — `tit/viewspec.py:190`
```diff
     VoxelAtlasManager(
+        fastsurfer_mri_dir=pm.fastsurfer_mri(sid),
         freesurfer_mri_dir=pm.freesurfer_mri(sid),
```

### W3a — `contracts/**` (schema regeneration)
- `PreprocessConfig`: apply the dataclass diff in §1.
- `Subject` schema: **add** `has_fastsurfer: boolean` to properties and to
  `required` (`contracts/openapi.v1.yaml:1531-1535`). `has_freesurfer` stays —
  legacy `derivatives/freesurfer` is still detected and reported.
- `SubjectInfoMatrix` columns gain `fastsurfer` before `freesurfer`.
- Capabilities: `fastsurfer: boolean` — probe with
  `from tit.pre.fastsurfer import fastsurfer_available; fastsurfer_available()`
  (filesystem-only, no subprocess, safe on any platform).

### Unowned — `tit/analyzer/analyzer.py:1138`
```diff
-        fs_mri = Path(self._pm.freesurfer_mri(self.subject_id))
+        fs_mri = Path(self._pm.fastsurfer_mri(self.subject_id))
+        legacy_mri = Path(self._pm.freesurfer_mri(self.subject_id))
         seg_dir = Path(self._pm.segmentation(self.subject_id))
         candidates = [
             fs_mri / atlas,
+            legacy_mri / atlas,
             seg_dir / atlas,
             fs_mri / f"{atlas}.mgz",
             fs_mri / f"{atlas}.nii.gz",
             fs_mri / f"{atlas}.nii",
+            legacy_mri / f"{atlas}.mgz",
+            legacy_mri / f"{atlas}.nii.gz",
+            legacy_mri / f"{atlas}.nii",
             seg_dir / f"{atlas}.nii.gz",
             seg_dir / f"{atlas}.nii",
         ]
```
Not urgent: the analyzer is normally handed a full path by the ROI picker /
catalog, and both now resolve FastSurfer first. Without this, a *bare atlas name*
naming a FastSurfer atlas would not resolve.

### Unowned — `tit/project_init/initializer.py`, `example_data_manager.py`
They scaffold `derivatives/freesurfer/` at project-init time and write its
`dataset_description.json`. Should become `derivatives/fastsurfer/`;
`resources/dataset_descriptions/fastsurfer.dataset_description.json` already exists
(added by this lane) and `tit/pre/utils.py::DATASET_TEMPLATES` already maps it.

### Unowned — `tit/reporting/**`
`base_generator.py:118-124` sniffs `$FREESURFER_HOME/build-stamp.txt`,
`reportlets/text.py:338-343` emits a "Cortical reconstruction was performed using
FreeSurfer X" sentence, `generators/preprocessing.py:242-246,463-464` lists
`derivatives/freesurfer/sub-<id>`, `reportlets/references.py` cites Fischl 2012 —
all already gated behind `if freesurfer_version` / `if "freesurfer" in step_names`,
so the report simply omits the section today. A FastSurfer equivalent (Henschel
2020 citation, `derivatives/fastsurfer/sub-<id>` output row) is a follow-up, not a
blocker.

---

## 5. Files edited outside W3b's stated grant

Flagged deliberately; each was needed for the lane's own code to be correct, and
none is claimed by another lane in plan §2.

1. **`tit/jobs/locks.py`** (2 lines + a comment). Without it the FastSurfer stage
   falls through to the coarse `stage:pre` lock instead of its own domain, and
   `tests/test_jobs_model.py::test_keys_for_pre_matches_plan_preprocessing_stage_configs`
   fails. The brief's plans.py deliverable says "locks/cost like recon-all had but
   smaller", so the intent was clearly in scope even if the path was not listed.
2. **`tit/constants.py`** (2 lines): renamed `TELEMETRY_OP_PRE_RECON_ALL` →
   `TELEMETRY_OP_PRE_FASTSURFER` (only consumer was the deleted `recon_all.py`) and
   corrected the now-false comment on `FS_LICENSE_PATH`.
3. **`tit/gui/extensions/subject_info_viewer.py`**: `derivatives/freesurfer` →
   `derivatives/fastsurfer`, `freesurfer_complete` → `fastsurfer_complete`. Inside
   `tit/gui/**`, which is granted, but worth naming because the key is read by
   the extension's own template.
4. **`tests/test_jobs_model.py`**: the locks/plans test above; not in the listed
   test globs but it is the test for `plans.py` + `locks.py`.
4b. **`tests/test_plan_routes.py`**: two lines of test data,
   `"run_recon": True` → `"run_fastsurfer": True` and `run_recon=False` →
   `run_fastsurfer=False`. Unowned by any lane; caused directly by this lane's
   field rename.
5. **`resources/dataset_descriptions/fastsurfer.dataset_description.json`** (new):
   the grant named `resources/atlas/**`. `ensure_dataset_descriptions` skips any
   dataset with no template, so a new file was the only way to get a BIDS
   `dataset_description.json` into `derivatives/fastsurfer/`.
6. **`tit/atlas/constants.py::mni_resources_dir()`** (new function). W3a's
   concurrent rewrite of `tit/viewspec.py` removed `mni_resources_dir`, which
   `tit/catalog.py` (mine) imported. Rather than wait on W3a I re-homed the
   four-line helper next to `MNI_ATLAS_DIR`, where it belongs, and pointed
   `catalog.py` at it. **W3a should import it from `tit.atlas.constants` too** if
   `viewspec.py` still needs it.

Not done, deliberately:
- **`tit/jobs/kinds.py`: the `viewer` kind is untouched.** The brief said to remove
  it "if W3a reports its routes are gone". No such report arrived, and
  `tit/server/routes/viewers.py` still exists (250 lines) — removing the kind would
  break `tit/jobs/spec.py::JOB_KINDS`/`CONTRACT_JOB_KINDS` and the frozen contract
  enum, neither of which W3b owns. Follow-up for whoever lands the viewer removal.
- **The freeview launcher in `tit/gui/nifti_viewer_tab.py`** (`launch_freeview_with_files`,
  `terminate_freeview`, ~90 lines) is still there. Deleting it removes that legacy
  PyQt tab's only viewing path, which is a viewer decision (D3 / W5), not a
  preprocessing one; the atlas-discovery half of that tab was updated. Follow-up.

---

## 6. Phase C smoke command (FastSurfer cannot run in `tit-v3-spike`)

`tit-v3-spike` is `idossha/simnibs:v2.5.0` and has no `/opt/fastsurfer`, so the
integration test in `tests/test_pre_fastsurfer.py` skips there
(`requires a FastSurfer checkout at $FASTSURFER_HOME`). Once W2's
`idossha/ti-toolbox:<ver>` image exists, run, inside it:

```bash
# 1. the checkout is present and runnable
docker exec -w /ti-toolbox <container> bash -lc \
  '$FASTSURFER_HOME/run_fastsurfer.sh --help | head -5'

# 2. the integration test stops skipping
docker exec -w /ti-toolbox <container> simnibs_python -m pytest -q \
  tests/test_pre_fastsurfer.py

# 3. a real subject, ~5 min native / measure emulated, 4.8 GiB peak RSS
docker exec -w /ti-toolbox -e PROJECT_DIR=/mnt/000 <container> \
  simnibs_python -c "
import logging; logging.basicConfig(level=logging.INFO)
from tit.pre.fastsurfer import run_fastsurfer
run_fastsurfer('/mnt/000', 'ernie', logger=logging.getLogger('smoke'), threads=4)
"

# 4. the outputs are discovered as an atlas
docker exec -w /ti-toolbox -e PROJECT_DIR=/mnt/000 <container> simnibs_python -c "
from tit.paths import get_path_manager
from tit.atlas.voxel import VoxelAtlasManager
pm = get_path_manager('/mnt/000')
m = VoxelAtlasManager(fastsurfer_mri_dir=pm.fastsurfer_mri('ernie'))
print([n for n, _ in m.list_atlases()])
print(len(m.list_regions(pm.fastsurfer_mri('ernie') + '/aparc.DKTatlas+aseg.deep.mgz')))
"
```

Expected from step 4: the two `aparc.DKTatlas+aseg.deep.*` names, and ~95–102
regions (ernie's real recon-all atlas gave exactly 102 through the same code path).

Worth measuring in Phase C and recording here: **emulated amd64 wall clock**. The
only number anyone has is 5 min native arm64; amd64-under-Rosetta could be several
times that, and the UI's time estimate should quote the measured figure.

---

## 7. Open risks

1. **n = 1 accuracy.** Every Dice number (0.922 subcortical / 0.914 cortical DKT vs.
   real recon-all) is sub-ernie only. Pallidum centroids shift 3–4 mm and one
   cortical region 3.1 mm — material for a 5 mm ROI sphere, negligible at 10–15 mm.
   The UI should say which segmentation source backs an ROI pick; not done here.
2. **Thalamic nuclei and hippocampal subfields are gone with no replacement.**
   `ThalamicNuclei.v13.T1.mgz` and `lh/rh.hippoAmygLabels-T1.v22.mgz` are still
   *discovered* for projects that already hold them, but nothing produces them any
   more. Whole-thalamus / whole-hippocampus / whole-amygdala remain available from
   charm's `labeling.nii.gz`. This is decision D2, recorded, not an oversight.
3. **Checkpoint availability.** The N0.2 spike's primary checkpoint host
   (`b2share.fz-juelich.de`) failed TLS verification; only the Zenodo fallback
   worked. W2 must bake the 67 MB `--vinn` checkpoints into the image rather than
   download at first run.
4. **Bare-atlas-name resolution in the analyzer** still looks only at
   `derivatives/freesurfer` (§4). Low impact — callers normally pass full paths.

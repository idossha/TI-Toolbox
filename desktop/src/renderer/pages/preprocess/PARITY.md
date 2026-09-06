# Pre-processing — parity checklist

Source: `tit/gui/pre_process_tab.py` + `tit/gui/components/qsi_config_dialogs.py`.
Config: `PreprocessConfig` (+ `QSIPrepSettings`/`QSIReconSettings`, the settings-only shapes B4
landed mid-build — see the schema note below) in `contracts/schema.json`.

Legend: [x] built · [~] built, adapted for the v3 job-per-subject model (see note) · [ ] not built.

## Subject selection

- [x] Subject list, multi-select → `SubjectPicker` fed by `/api/catalog/subjects` (+ per-subject
      `/api/catalog/subjects/{id}` for the dwi flag). Presence chips: raw, freesurfer, m2m, dwi.
- [x] "Select All" / "Select None" — `SubjectPicker`'s own checkboxes plus page-level buttons.
- [x] "Refresh" — TanStack Query refetch button.
- [ ] The Qt "No subjects found" / "Project directory not found" `QMessageBox`es → replaced by
      `EmptyState` / `Callout` (DESIGN.md: no native dialogs for informational states).

## Processing options (checkboxes → `Checkbox` rows, tooltips → visible help text)

- [x] "Convert DICOM files to NIfTI" (default **on**, matching Qt) → `convert_dicom`.
- [x] "Run FastSurfer segmentation" (default **on**), tooltip → `run_fastsurfer`. FreeSurfer
      `recon-all` and the thalamic-nuclei/hippocampal-subfield subcortical segmentations were
      removed with the FreeSurfer container (D2, `dev/notes/v3-docker-streamline-plan.md`);
      `tit.pre.config.migrate_legacy_keys` still reads an old config's `run_recon` and maps it onto
      `run_fastsurfer` with a warning, so a saved v2 config keeps working. Existing
      `derivatives/freesurfer` output on disk is unaffected — every atlas reader still discovers
      it (chip label unchanged, see the subject-selection row above).
- [x] "FastSurfer threads" `NumberInput`, nested under the checkbox and disabled when it is off →
      `fastsurfer_threads` (`int | null`). Qt's `pre_process_tab.py` defaults this spinbox to
      `min(DEFAULT_THREADS, multiprocessing.cpu_count())` because it can read the host's core count
      directly; this page has no such reading (no `window.tit` method surfaces it, and no v1
      contract endpoint does either — same gap as gap 2 below), so it defaults to blank/`null` and
      lets the server apply `tit.pre.fastsurfer.DEFAULT_THREADS`.
- [~] "Run recon-all in parallel" + cores spinbox → **removed, not just unexposed.** The v2 Qt-era
      flag (and the `parallel_recon`/`parallel_cores` fields it drove) no longer exist in
      `PreprocessConfig` at all — FastSurfer's `--seg_only` inference is single-process per subject
      with its own `fastsurfer_threads` above, not FreeSurfer's OpenMP-parallel `recon-all`. Cross-
      subject concurrency is still "Subjects running in parallel" below
      (`JobGroupRequest.parallel_subjects`), which is what actually governed this in v3's job-per-
      subject model even before the removal (`len(subject_list) == 1` inside each job's
      `run_pipeline` call, so the Qt-era flag had already stopped doing anything meaningful there).
- [x] "Create SimNIBS m2m folder" (default **on**), tooltip → `create_m2m`. Labelled "charm +
      subject atlas" because `PreprocessConfig` has no separate subject-atlas flag — `create_m2m`
      always runs both (`tit/pre/structural.py`: `run_charm` then `run_subject_atlas`).
- [x] "Run Tissue Analyzer" (default off), tooltip → `run_tissue_analysis`; help text notes it
      needs an m2m folder (create_m2m on, or already present).
- [x] DWI section label ("DWI Processing (Docker)") → `FormSection` "DWI processing (Docker)".
- [x] "Run QSIPrep" + gear button → `run_qsiprep` + "Configure…" opening `QsiPrepDialog`.
- [x] "Run QSIRecon" + gear button → `run_qsirecon` + "Configure…" opening `QsiReconDialog`; help
      text notes it needs QSIPrep output.
- [x] "Extract DTI tensor for SimNIBS" (default off), tooltip → `extract_dti`.
- [~] Existing-output policy: Qt shows a `QMessageBox` *after* Run is clicked with three buttons
      (Cancel / Skip Existing / Replace and Rerun), each subprocess run getting
      `skip_existing_outputs`/`replace_existing_outputs`. v3 moves this earlier and ties it to the
      Plan panel per DESIGN.md §2/§6.2: a `RadioGroup` ("Skip existing outputs" default / "Replace
      and rerun") sets those same two fields, and clicking Run behind a `will_overwrite` conflict
      (from `POST /api/plan/pre`) opens an `AlertDialog` ("Replace existing outputs?") before
      submitting — same two-step confirm as Qt's warning + `ConfirmationDialog.confirm`, adapted to
      the plan-first flow instead of a post-click dialog.
- [ ] "Report" step — **not a config field.** `run_pipeline` always writes an HTML report at the
      end summarizing whichever steps ran; there is no boolean to gate it. Shown as an info
      `Callout`, not a toggle bound to `PreprocessConfig`.
- [x] Debug/info console lines listing every option before running → superseded by the Plan panel
      (DESIGN.md §2: "tells the truth before you click Run") plus the job's own log in the rail.
- [x] Confirmation dialog summarising all options before running → `AlertDialog` (only shown when
      a replace-and-rerun would overwrite existing output; otherwise Run submits directly, per
      DESIGN.md interaction rule 2 — confirmation is for destructive actions, not every run).
- [x] Run/Stop buttons + console → replaced by "Queue N jobs" and the Jobs rail/console (P7); a
      preprocessing run is now N independent jobs, not one subprocess with a Stop button.

## Subjects-in-parallel (new, no Qt equivalent — job-group concept)

- [x] "Subjects running in parallel" `NumberInput`, min 1, max = number of selected subjects,
      default 1 → `JobGroupRequest.parallel_subjects`.

## QSIPrep dialog (`QSIPrepConfigDialog`)

- [x] Output Resolution (mm), 0.5–3.0 step 0.5, default 2.0, tooltip → `output_resolution`.
- [x] Resource Settings group: CPUs (1..cpu_count), Memory (GB, 4..max), OMP Threads
      (1..cpu_count) → `resources.{cpus,memory_gb,omp_threads}`. The Qt dialog pre-fills CPUs/Memory
      from `get_inherited_dood_resources()` (current container limits) — a host/container query with
      no v1 contract endpoint. The page defaults both to "auto" (`null`, `ResourceConfig`'s own
      default) with a placeholder explaining the backend fills the container's inherited limit;
      **gap** noted below.
- [x] Denoise Method select (dwidenoise / patch2self / none), tooltip → `denoise_method`.
- [x] Unringing Method select (mrdegibbs / rpg / none), tooltip → `unringing_method`.
- [x] Skip BIDS Validation checkbox (default on), tooltip → `skip_bids_validation`.
- [x] Image Tag text field (default from `QSI_QSIPREP_IMAGE_TAG`, schema default `"26.0.0"`) →
      `image_tag`.
- [x] "Reset to Defaults" button.
- [x] OK / Cancel → Dialog footer buttons; OK writes into the parent form's `qsiprep_config`.

## QSIRecon dialog (`QSIReconConfigDialog`)

- [x] Reconstruction Specifications — categorised checkbox list (6 categories, 26 specs total),
      each with its tooltip description, ported verbatim from `_SPEC_CATEGORIES` → `qsi.ts`.
- [x] Atlases for Connectivity (optional) — categorised checkbox list (2 categories, 14 atlases),
      hint text, tooltips ported from `_ATLAS_CATEGORIES` → `qsi.ts`.
- [x] Resource Settings: CPUs, Memory (no OMP Threads field in this dialog, matching Qt) →
      `resources.{cpus,memory_gb}`.
- [x] Options: Use GPU (default off, tooltip), Skip ODF Reports (default on, tooltip) → `use_gpu`,
      `skip_odf_reports`.
- [x] Image Tag text field (schema default `"26.0.0"`) → `image_tag`.
- [x] "Reset to Defaults" button (unchecks all specs but the default, clears atlases).
- [x] OK / Cancel.

## Plan panel (no Qt equivalent — DESIGN.md §2)

- [x] `POST /api/plan/pre` on debounce (config + selected subjects + overwrite choice) →
      per-subject output dir, exists/will_overwrite chips, lock conflicts, cost, warnings.
- [x] Client-side stage list per subject (DICOM → charm+atlas → FastSurfer → tissue analysis →
      QSIPrep → QSIRecon → DTI extraction), built from the toggled steps, shown as an ordered
      "Steps per subject" preview.
- [x] **Per-stage existing-output plan**, resolved fix:pages-a 2026-08-27: `tit/server/routes/plan.py`
      (B3, verified in this lane by reading the code) now calls `tit.jobs.plans.plan_preprocessing`
      for `kind=pre` and returns one `PlanJob` per stage (G1-G6/report), not one per subject — the
      `PlanJob` schema itself is unchanged (`{kind, subject, output_dir, exists, will_overwrite}`,
      no `stage` field), so the "Outputs" section now groups `plan.jobs` by `subject` and renders
      every job for it (was: keyed on `job.subject` alone, which silently collapsed >1 stage job
      per subject to one row via a React key collision). A stage label is inferred from
      `output_dir` (`describePreStageDir`, index.tsx) since no explicit stage field exists on the
      wire; falls back to the pre-existing single-row-per-subject look when the plan source (the
      mock server, or an older backend) returns exactly one job per subject. The mock's own
      `planFor("pre", ...)` still returns one row per subject (`server.mjs`, F3-owned, not edited
      here), so this only visibly activates against the real server — noted in the field-help copy
      rather than left silently untested.
- [x] **Queued-jobs toast, fixed alongside the above**: `POST /api/jobs/groups` for `kind=pre` was
      already expanding to one job per stage (+ a report job) per subject in the mock (`server.mjs`,
      pre-existing, F3-owned) — surfaced by this pass's E2E run (`preprocess.spec.ts` failed:
      `result.jobs.length` was 9 for 2 selected subjects, not 2). The success toast now reports
      subjects and jobs separately ("Queued preprocessing for 2 subjects (9 jobs).") instead of
      substituting the raw job count for the subject count the user actually picked.
- [x] Run button label follows the plan: "Run preprocessing" (1 subject) / "Queue N jobs" (N > 1).

## Gaps / requests (see final report)

1. **Resolved mid-build:** B4 landed `QSIPrepSettings`/`QSIReconSettings` (flat, no `subject_id`)
   partway through this lane; the dialogs and `qsi.ts` were updated to the final shape once
   `contracts/schema.json`/`schema.d.ts` were regenerated — nothing outstanding here.
2. No endpoint exposes `get_inherited_dood_resources()` (container CPU/RAM limits) to the
   renderer — CPU/Memory default to "auto" (`null`) instead of the Qt dialog's inherited numbers.
3. **Per-stage grouping RESOLVED** (see the Plan panel item above) — **remaining piece**:
   `PlanJob` still has no explicit `stage`/`label` field on the wire (ra_13 finding 12), so the
   per-stage row label is still `describePreStageDir`'s directory-name guess rather than the
   server's own stage name. Fixed to fall back gracefully: `stageLabelFor()` (`index.tsx`) now
   prefers `job.stage`/`job.label` when a future contract/backend sends them, and only falls back
   to the guess otherwise — no page change needed once B3/F1a add the field.
4. **`forms/ajvResolver.ts` + `forms/schema.ts` (F2) bug, worked around locally:**
   `createAjvResolver(name)` compiles `resolveDef(schema, name)` — the single extracted `$defs`
   entry — in isolation, discarding the document's other `$defs`. Any config whose schema `$ref`s a
   sibling def throws at compile time (`Error: can't resolve reference #/$defs/QSIPrepSettings from
   id #` for `PreprocessConfig`). `pages/preprocess/resolver.ts` works around it locally (compiles
   the def together with the full `$defs` bag) rather than editing `forms/**`; see its file comment
   and `tests/unit/preprocess-defaults.test.ts`'s first `describe` block, which reproduces the
   throw against the real schema. This isn't `PreprocessConfig`-specific — `tests/unit/simulator-
   defaults.test.ts` and `tests/unit/optimizer-ex-defaults.test.ts` hit the identical error
   (`ExConfigBucketElectrodes`, `MExConfigBucketElectrodes`, `Montage`) when run standalone during
   this investigation, though the full suite is green as of this report (another lane may have
   applied its own workaround independently). Worth a real fix in `forms/schema.ts`/`ajvResolver.ts`
   so every page gets it once instead of N local workarounds.

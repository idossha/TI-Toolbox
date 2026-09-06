# Lane F0 — the two known failures (2026-09-03)

Scope: fix the two failures in §0 of `dev/notes/v3-pipelines-program.md` (flex list-form ROI
`TypeError`, and the trailing `report` job's `unknown job kind: 'report'`), prove each with a
real run against the shared dev container, keep host pytest and the flex/report unit suites
green. No desktop files were touched (nothing under `desktop/src/renderer/pages/optimizer/**`
or `desktop/src/renderer/pages/_shared/roi/**` needed changing — see Task 1 below).

## Task 1 — flex list-form ROI

**Root cause.** `tit/opt/flex/flex.py::_validate_roi_input` predates PR #130's ROI-union feature.
`FlexConfig.AtlasROI`/`SubcorticalROI.atlas_path` is `str | list[str]` (one entry per unioned
region, often repeating the same file — the maintainer's own failing config has the same DK40
`.annot` path three times for three labels), and `_validate_roi_input` did
`_require_file(Path(atlas_path), ...)` straight on that field. `Path(list)` raises
`TypeError: expected str, bytes or os.PathLike object, not list` before any real file check runs.

**Everything downstream was already list-aware.** `tit/opt/flex/utils.py` (`_broadcast`,
`_configure_atlas_roi`, `_configure_subcortical_roi`) and `tit/opt/flex/builder.py`
(`_as_list(roi.atlas_path)[0]` for report display) already handle the list form correctly — only
the validation gate was stale. `tit.opt.ex`/`tit.opt.mex` "align" differently: their `AtlasROI` is
always scalar, and a union is expressed as `roi_atlas: list[AtlasROI] | None` (a list of
scalar-ROI objects) instead of parallel list fields on one ROI object — two different shapes for
the same idea, so there was nothing to literally copy from ex/mex's own scalar `_require_file`
call; the fix instead mirrors how `builder.py`/`utils.py` already read this same flex-specific
field (`_as_list` + iterate).

**Fix** (`tit/opt/flex/flex.py`): `_validate_roi_input` now does
`for path in dict.fromkeys(_as_list(atlas_path)): _require_file(Path(path), ...)` — de-duplicated
so three labels sharing one file only stat it once, but a union where one *distinct* file is
missing is still caught (added a test for exactly that: `lh` atlas present, `rh` atlas absent).

**Unit tests** (`tests/test_opt_flex.py`, all new, all passing):
- `test_accepts_list_form_atlas_roi_union` — the maintainer's exact shape (3× same path, 3
  labels) no longer raises.
- `test_list_form_atlas_roi_missing_file_still_reported` — a union with one missing file among
  several distinct ones is still caught (not silently accepted via `[0]`).
- `test_accepts_list_form_subcortical_roi_union` — same fix, `SubcorticalROI` side.

**Real run** (proves it end to end, not just past validation):
- Submitted the maintainer's own failing config (`c45cb53b0e864d02/spec.json`'s `config`
  verbatim, list ROI included) via `POST /api/jobs`, `kind: "flex"`, `subject_ids: ["101"]`,
  `output_folder` overridden to
  `/mnt/000/derivatives/SimNIBS/sub-101/flex-search/smoke-f0-20260903_175617` so the run and its
  output are identifiable, `tags: ["smoke-f0", "smoke-f0-20260903_175617"]`.
- Job `6d3519547ed14bce`: `queued` → `running` (`started_at` 22:56:27 UTC) within the request
  round-trip. Log tail: `Setting up output folders, logging and IO ...` → `Setting up headmodel
  ...` → `Setting up ROI ...` — past `_validate_flex_inputs` entirely and into SimNIBS's own ROI
  setup inside `TesFlexOptimization`, proving the fix, not just that validation didn't crash.
- Cancelled via `POST /api/jobs/6d3519547ed14bce/cancel` at 22:57:18 UTC (`state: cancelled`,
  `exit_code: 15`, ~51 s after start).
- Cleaned up: `rm -rf` on the `smoke-f0-20260903_175617/` output dir inside the container
  (contained only `00/summary.txt` + a SimNIBS log from the one restart before cancel — no real
  results). Verified gone with `find ... -iname '*smoke-f0*'` afterward (empty).
- No other FEM-class job was running/queued before submission (`GET /api/jobs` checked first).

## Task 2 — the trailing `report` job

**What the trailing report job was meant to produce, and why the per-stage report doesn't
already cover it.** Every stage job in a `pre` group (`G1`..`G6`) already writes its own HTML
report as a side effect of `tit.pre.structural.run_pipeline` (`tit/pre/__main__.py`'s
`_logger_callback` matches `"Report generated: "` and emits it as an artifact) — but
`tit/jobs/plans.py::_stage_config` forces every flag except that one stage's own to `False`, and
`run_pipeline`'s report-building loop (`tit/pre/structural.py` lines ~591-666) only adds a
processing step for the flags that are `True` in *that call*. So a group running
`convert_dicom` + `create_m2m` + `run_tissue_analysis` together produces **three separate,
each-incomplete reports** (one covering DICOM Conversion alone, one covering charm+atlas alone,
one covering tissue alone), and whichever stage happens to finish last silently "wins" the
newest-report fallback the UI's job-report pane uses for a `report`-kind job
(`desktop/src/renderer/app/jobs-rail/ReportPane.tsx`'s `resolveReportId`, and
`GroupsView.tsx`'s comment already documents the report job's existence and its own
representative-kind exclusion logic — neither needed changes). This is a real, user-visible gap,
not a redundant no-op — so the decision is **wire the kind**, not remove the plan.

Supporting evidence this was the intended design, not an accident: `CONTRACT_JOB_KINDS`
(`tit/jobs/spec.py`) already froze `"report"` into the wire contract (2026-08-27 schema change,
alongside `tools`); `tit/jobs/costs.py` already had `"report": Cost(cpus=1, mem_gb=2)`; the
docstring on `plan_preprocessing` already spelled out exactly what a consolidated report should
cover. Only `tit/jobs/kinds.py::MODULE_FOR_KIND` was missing the entry, and no runner module
existed.

**Fix:**
1. `tit/pre/report.py` (new) — `simnibs_python -m tit.pre.report config.json`. Reads the *same,
   un-narrowed* `PreprocessConfig` flags the group's plan decided on (not each stage's forced
   config), builds one `PreprocessingReportGenerator` with one `add_processing_step(...,
   status="completed")` per requested flag (`create_m2m` contributes two steps — "SimNIBS charm"
   and "Subject Atlas Segmentation" — mirroring `structural.py`'s own loop exactly, same step
   names/descriptions), then `scan_for_data()` + `generate()`. It does no science of its own: by
   the time this job runs, the scheduler has already gated it on every id in its own `after` list
   reaching a non-`FAILED_LIKE_STATES` terminal state (`tit/jobs/scheduler.py`), so every step it
   lists really did complete — `status="completed"` is not a guess.
2. `tit/jobs/plans.py` — the trailing `PlannedJob`'s `config` changed from the inert
   `{"subject_id": subject_id}` to `serialize_config(replace(config, subject_ids=[subject_id]))`
   — the group's real, un-narrowed flags, narrowed only to one subject (exactly mirrors the same
   `if config.xxx:` checks that decided which of `G1..G6` got planned in the first place, so
   there is no way for the report job's flags to diverge from what actually ran). `project_dir`
   comes along for free via `serialize_config`'s existing PathManager injection, same as every
   other stage job.
3. `tit/jobs/kinds.py` — `MODULE_FOR_KIND["report"] = "tit.pre.report"`.
4. Docstring updates in `tit/jobs/plans.py` and `tit/jobs/spec.py` to stop saying "internal-only,
   not yet wired".

**Unit tests:**
- `tests/test_pre_report.py` (new, 4 tests): reports every requested flag as `"completed"` with
  `create_m2m` correctly expanding to two steps; a flag left `False` is not reported; a
  `generate()` failure exits 1 (caught, not a bare crash); a misuse guard (>1 subject in one
  report job's config) exits via a real `SystemExit`, not a mocked no-op — the test deliberately
  leaves `sys.exit` unpatched here so it actually proves execution stops.
- `tests/test_jobs_model.py`: `test_command_for_report` (kind → argv), and two new
  `plan_preprocessing` tests — `test_plan_preprocessing_report_job_carries_every_requested_flag`
  (the report job's config now has every requested flag, correctly narrowed to one subject, and
  `after_labels` covers exactly the stage jobs planned for that subject) and
  `test_plan_preprocessing_no_jobs_no_report` (a subject with every flag `False` plans nothing,
  report included — `plan_preprocessing`'s own documented contract).

**Real run** (`tit/jobs/kinds.py` + `tit/jobs/plans.py` are server-side; required a container
restart — see below):
- Checked `GET /api/jobs` for running/queued jobs first: none. `docker restart
  ti-toolbox-fad740e5-tit-1`. Polled `/api/health` until `{"status":"ok"}` (came back in ~5 s).
  **Container restarts: 1.**
- Submitted `POST /api/jobs/groups`: `kind: "pre"`, `config: {subject_ids: ["101"],
  convert_dicom: true, skip_existing_outputs: true}`, `subject_ids: ["101"]`,
  `parallel_subjects: 1` — the maintainer's own `d0036f3cad7b4be9` shape (subject 101, only
  `convert_dicom`), with `skip_existing_outputs: true` instead of their original
  `replace_existing_outputs: true` since sub-101's T1w/T2w already exist from that earlier real
  run — skip is strictly safer here (never touches the maintainer's real DICOM-derived NIfTIs)
  and still exercises the exact same group→report DAG.
- Group `5483a740f8e64e6c`: `pre` job `25b2246fee204073` (queued → succeeded, `started_at`
  22:58:27.76 → `finished_at` 22:58:37.00, ~9 s; log: `"DICOM conversion (T1w): skipping because
  output already exists"`) then `report` job `93c76c42ee0845e8` (queued → running → succeeded,
  22:58:37.26 → 22:58:44.56, ~7 s; log: `"Report generated:
  .../pre_processing_report_20260903_225844.html"`). **Both jobs in the group succeeded,
  including the report job.**
- Verified the report artifact on disk inside the container: 29372 bytes, contains the string
  `"DICOM Conversion"` and `"Subject 101"` — the consolidated report picked up exactly the one
  flag that was actually requested for this group.
- Left the two new report HTML files in place (`derivatives/ti-toolbox/reports/sub-101/`) —
  they're small, additive (no filename collision, no overwrite), and sit alongside the
  maintainer's own earlier report from the same directory as ordinary evidence of a real run,
  not smoke-test junk needing a distinct tag.

## Gates

- Host pytest, full suite, after all changes: **3169 passed, 18 skipped, 35.85 s** (baseline per
  project memory was ~2463 passed/~25 s before the other three lanes' concurrent work in this
  shared worktree added their own tests; the ~35 s figure includes their additions, not just
  F0's ~20 new tests, which run in well under 1 s combined).
- Desktop gates: not re-run by this lane. No file under `desktop/` was touched — Task 1 needed no
  UI change because the UI already emits the correct list-shaped ROI (that's the whole bug: the
  backend didn't accept what the UI was already correctly sending), and Task 2 is server-side
  only.

## Files changed

- `tit/opt/flex/flex.py` — `_validate_roi_input` fix (list-form `atlas_path`).
- `tests/test_opt_flex.py` — 3 new regression tests.
- `tit/pre/report.py` — new runner module for the `report` job kind.
- `tests/test_pre_report.py` — new, 4 tests.
- `tit/jobs/kinds.py` — `MODULE_FOR_KIND["report"] = "tit.pre.report"`.
- `tit/jobs/plans.py` — report job's config now carries the group's real flags; docstring update.
- `tit/jobs/spec.py` — docstring update (`report` no longer "internal-only").
- `tests/test_jobs_model.py` — 3 new tests (`command_for("report", ...)`, two `plan_preprocessing`
  tests).

## Open issues / requests to other lanes

1. **Minor, not fixed (out of scope for F0's two named bugs):** `tit/jobs/locks.py::keys_for`
   has no per-subject branch for `kind == "report"` (only a top-level `elif kind == "report" and
   config.get("group"):` for a *different*, apparently never-implemented "group-level report"
   concept — `plan_preprocessing`'s report config has no `"group"` key, so that branch is dead
   for the job this lane wired up). The result: the `report` job I wired holds **zero** locks
   while it reads a subject's derivatives via `scan_for_data()`. This is not a regression (the
   pre-fix `614b6667...` job's spec also had `"locks": []`) and didn't affect the one real group
   run above (nothing else was writing to sub-101 concurrently), but a future report job racing
   a concurrent write to the same subject's derivatives is theoretically possible. Suggested
   owner: whichever lane next touches `tit/jobs/locks.py`'s `report` branch — add
   `LockRequest(f"subject:{sid}:report", mode="read")`-style scaffolding paralleling the other
   per-subject branches, or fold it into `_pre_requests` when `kind == "report"`.
2. **Not a bug, no action needed:** `desktop/src/renderer/app/jobs-rail/GroupsView.tsx`'s comment
   calling `report` "the trailing, incidental stage, never the group's actual work" is now
   slightly narrow in spirit (it does real, useful work — a consolidated report) but its actual
   behavior (excluding `report` from the group's representative-kind label, e.g. "pre · 2
   subjects" rather than "report · 2 subjects") is still exactly correct and needs no change.
   Flagging only so the next reader of that comment isn't confused about why it still says
   "incidental" after F0.

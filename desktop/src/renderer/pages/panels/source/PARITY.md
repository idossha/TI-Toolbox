# Source — parity checklist

Qt source: `tit/gui/extensions/source.py` (362 lines, `EXTENSION_NAME = "Source"`). Two
independent pipelines dispatched to `simnibs_python -m tit.source`, unified in the v1 contract as
`SourceConfig {mode, subject_ids?, pairs?, forward?, fsavg_map?}` (`kind: "source"`).

## Subjects (shared list)

- [x] Multi-select subject list (`QListWidget`, `ExtendedSelection`) → `SubjectPicker`, filtered
      to subjects with `has_m2m` (a forward solution needs the head model).
- [x] "Refresh subjects" button → `useQuery` on `/api/catalog/subjects`, `refetch()`.

## Build forward solution (`ForwardConfig`)

- [x] "EEG net" combo, populated from the first selected subject's caps → `Select` from
      `getEegNets(subject)` for the first selected subject (Qt only looks at the first subject
      too — `_on_subjects_changed` uses `subjects[0]`).
- [x] "fsaverage spacing" combo (5/6/7) → `Select`, default 5 (`ForwardConfig.fsaverage_spacing`).
- [x] `cpus` (SimNIBS FEM workers, hardcoded to 1 in Qt's `_run_forward`) → `NumberInput`, default
      1, with help text.
- [x] `overwrite` (hardcoded `True` in Qt — the confirm-overwrite dialog gates it, not a checkbox)
      → surfaced through the Plan panel's `will_overwrite`/`exists` + `AlertDialog`, not a raw
      toggle (R3/DESIGN.md §2 pattern every other Run screen already uses).
- [x] "Build forward" button → part of the shared Plan panel's Run button (Plan shows which mode
      is about to run).

## Field mapping

Removed from Source by maintainer request (2026-09-09). New simulations opt in through
per-job Simulator settings; existing outputs use `tit.source.fsaverage` from a notebook or
terminal. The SourceConfig mapping mode remains supported by the backend.

## Shared

- [x] Console output (`ConsoleWidget`) / Stop button → replaced by the job model: the Run button
      queues a `source` job, progress/log/cancel live in the Jobs rail and per-job console
      (`ui/Jobs.tsx`), not a page-local console (R3).
- [x] Overwrite confirmation (`confirm_overwrite`) → Plan panel `AlertDialog`, same as every other
      Run screen.

## Honest gap found in Round 2 — not mine to fix (mock-server, F3-owned)

`tests/mock-server/server.mjs`'s `validateConfig()` puts `"source"` in `PER_SUBJECT_KINDS` and
requires `cfg.subject_id` (singular) for every kind in that set. `SourceConfig` has no
`subject_id` field at all — forward mode carries `subject_ids` (plural), fsavg_map mode carries
`pairs: [{subject_id, simulation}]`. The effect: `POST /api/validate/source` against the mock
*always* returns `{ok: false, errors: [{path: "subject_id", message: "subject_id is required"}]}`
for every real `SourceConfig`, so `validateQuery.data.ok` is never `true` and the Plan
(`planSource`, gated on that) never runs — the Source panel's Plan card always shows this one
false-positive error instead of a real plan in E2E/screenshots. Confirmed this is mock-only, not a
real backend bug: `tit/source/config.py`'s `__post_init__`s validate `fsaverage_spacing`/`fields`,
never a `subject_id`. Verified directly: `curl -X POST .../api/validate/source` with a valid
forward `SourceConfig` body returns `{"ok":false,...}` from the mock. Not fixed here — `tests/
mock-server/**` is outside this lane's ownership; flagging for whoever owns the mock server next
(remove `"source"` from `PER_SUBJECT_KINDS`, or check `subject_ids`/`pairs` instead).

## Round 2 (ra_12 #7/#8, ra_13 #10)

- [x] `config.ts`'s builders are now typed against the real `SourceConfig` `$def` instead of
  `Record<string, unknown>`; `api.ts` adds `validateSource()` (`POST /api/validate/source`),
  called before both `planSource()` and submit.
- [x] Both Plan panels ("Build forward" / "Map to fsaverage") now render the shared
  `pages/panels/PlanSummary` component (Jobs · CPUs · Memory · Outputs · Waits — same vocabulary
  as Cluster permutation, NIfTI group averaging, Nilearn visuals) instead of a page-local
  `DefinitionList`, and show `/api/validate` field errors above the plan.
- [x] Run-enabled rule (DESIGN.md §6.3: "Run button stays enabled, Plan shows the errors"): "Build
  forward" / "Map to fsaverage" are no longer `disabled=` — clicking with an incomplete selection
  shows a toast naming what's missing instead of doing nothing.

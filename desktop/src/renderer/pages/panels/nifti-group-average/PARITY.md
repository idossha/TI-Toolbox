# NIfTI Group Averaging — parity checklist

Qt source: `tit/gui/extensions/nifti_group_average.py` (822 lines, `EXTENSION_NAME = "NIfTI Group
Averaging"`). `JobKind` includes `"nifti_average"` (contract §3), and `NiftiAverageConfig` is now
a real `contracts/schema.json` `$def` in the `PipelineConfig` union (ra_13 finding #10) — the
"no config dataclass exists yet" note below was stale by the time this round started. The panel's
`config.ts`/`api.ts` are typed against `NiftiAverageConfig` directly and call
`POST /api/validate/nifti_average` before submit, same as `pages/panels/cluster-permutation`.
Fixed in the same pass: the config this panel built used `analysis_name` and a comma-joined
`diff_pairs` string — the real schema fields are `output_name` and `diff_pairs: string[]`, so the
job submission was silently broken (missing required field) before this round.

- [x] Subject/simulation/group rows (`SubjectRow`: subject combo → filtered simulation combo →
      editable group combo) → the shared `ParticipantsField` (DESIGN.md §4.4.1): the same header
      band, summary line, table and per-row "Why not" reason as `SubjectsField`, over a row list
      rather than a set — the model here is `(subject, simulation, group)` tuples in which one
      subject may legitimately repeat (a diff pair), which a set control cannot express. Columns:
      # / Subject `Select` / Simulation `Select` filtered to that subject / Group `TextInput`;
      "Add subject" in the header band.
- [x] Import/Export CSV → **not ported**: there is no `/api/files` upload route and Electron has
      no file-open dialog wired yet (gotcha #4, `onBrowse`). Reported as a gap rather than faked.
- [x] "Analysis Name" text field → `TextInput`, required, same placeholder text.
- [x] "NIfTI Pattern" text field, default
      `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz`, same tooltip → `TextInput` + help text.
- [x] "Group Differences" text field (comma-separated `GroupA-GroupB` pairs, optional, same
      tooltip) → `TextInput` + help text; empty means "all pairs" like Qt.
- [x] Validation: analysis name required, ≥2 subjects, ≥1 group → same checks before Run, shown
      inline instead of a blocking `QMessageBox`.
- [x] Confirmation dialog listing groups + counts before running → `AlertDialog` with the same
      summary (group → subject count).
- [x] Run → queues a `nifti_average` job instead of an in-process `QThread` (R3: long work is a
      job). Progress/log/cancel move to the Jobs rail.

## Known gaps (reported, not hacked around)

- No CSV import/export (needs a file-open dialog bridge method + an upload route — neither exists
  yet).
- No Space (subject/MNI) selector originally — added in this round since `NiftiAverageConfig.space`
  is a real field with no server-side default worth hiding; the NIfTI pattern default still assumes
  MNI space, same as Qt.

## Round 2 (ra_12 #7/#8)

- [x] Plan card now renders the shared `pages/panels/PlanSummary` (Jobs · CPUs · Memory · Outputs ·
  Waits — same vocabulary as the other three panels this lane owns) instead of a page-local
  `DefinitionList` with only cost.
- [x] Run-enabled rule (DESIGN.md §6.3): "Run analysis" is no longer `disabled={errors.length > 0}`
  — it is always clickable; clicking with an incomplete form shows a toast with the first client
  error instead of doing nothing.

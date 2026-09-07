# Nilearn Visuals — parity checklist

Qt source: `tit/gui/extensions/nilearn_viz.py` (1063 lines, `EXTENSION_NAME = "Nilearn
Visuals"`). `JobKind` has `"nilearn"` and `NilearnConfig` is now a real `contracts/generated/config.schema.json`
`$def` in the `PipelineConfig` union (ra_13 finding #10) — the "no config dataclass exists yet"
note below was stale by the time this round started. The panel's `config.ts`/`api.ts` are typed
against `NilearnConfig` directly and call `POST /api/validate/nilearn` before submit. Fixed in the
same pass: the config this panel built used a `pairs` field — the real schema field is
`subject_simulation_pairs`, so the job submission was silently broken (missing required field)
before this round.

- [x] Subject/simulation pairs table (`+ Add Pair`, `Quick Add`, `Clear All`) → the shared
      `ParticipantsField` (DESIGN.md §4.4.1): the same header band, summary line, table and per-row
      "Why not" reason as `SubjectsField`, over a row list rather than a set (one subject may take
      part twice with two simulations). Columns: # / Subject `Select` / Simulation `Select`
      filtered to that subject; "Add pair" and "Clear all" in the header band. "Quick Add" (same simulation to many subjects at once) → a subject
      multi-picker + one simulation field, "Add" appends one row per picked subject.
- [x] "Sub-directory name" text field, same placeholder/tooltip
      (`derivatives/ti-toolbox/nilearn_visuals/{name}`) → `TextInput` + help text.
- [x] "Use percentile cutoffs" checkbox → `Checkbox`, same tooltip.
- [x] "Minimum Cutoff" / "Maximum Cutoff" (`QDoubleSpinBox`, V/m units, 0.3/5.0 defaults, 0.1/0.5
      steps) → `NumberInput` with `unit="V/m"`, same defaults/steps; label switches to "%" when
      percentile mode is on (same behaviour Qt's `_on_percentile_mode_changed` describes).
- [x] "Atlas Selection" combo (`harvard_oxford_sub` default, `harvard_oxford`, `aal`,
      `schaefer_2018`) → `Select`, same options/default.
- [x] "Region Selection" combo ("All Regions" + atlas-specific regions,
      `self.region_combo.currentData()`) → `Select` seeded with "All regions" only; the
      atlas-region lookup (`atlas_data[config["labels_key"]]`, `nilearn.datasets.fetch_atlas_*`)
      runs in the Python worker at request time in Qt, not exposed by any v1 catalog route —
      reported as a gap rather than hardcoding a region list that would drift from nilearn's.
- [x] Glass-brain visualization — Qt always enables it with the `"hot"` colormap and has no UI
      for it (`create_glass_brain = True`, hardcoded); not surfaced here either, submitted as a
      fixed part of the config for the same reason.
- [x] "Generate Images" / "Stop" → Run button queues a `nilearn` job (R3); Stop lives in the Jobs
      rail like every other job.

## Known gaps (reported, not hacked around)

- No atlas-region catalog route: `atlases/regions` exists for cortical/subcortical *subject*
  atlases (`GET /api/catalog/atlases/regions?subject=&atlas=&hemi=`), not for the
  population-level nilearn atlases (`harvard_oxford`, `aal`, `schaefer_2018`) this panel uses —
  "Region selection" is therefore "All regions" only until that catalog route exists.

## Round 2 (ra_12 #7/#8)

- [x] Plan card now renders the shared `pages/panels/PlanSummary` (Jobs · CPUs · Memory · Outputs ·
  Waits) instead of a page-local `DefinitionList` with only cost.
- [x] Run-enabled rule (DESIGN.md §6.3): "Generate images" is no longer
  `disabled={errors.length > 0}` — it is always clickable; clicking with an incomplete form shows
  a toast with the first client error instead of doing nothing.

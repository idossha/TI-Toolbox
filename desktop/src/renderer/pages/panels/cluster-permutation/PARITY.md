# Cluster Permutation — parity checklist

Qt source: `tit/gui/extensions/cbp.py` (1272 lines, `EXTENSION_NAME = "Permutation Analysis"`).
Unlike NIfTI Group Averaging / Nilearn Visuals, both modes here already have real schema entries
(`GroupComparisonConfig`, `CorrelationConfig` in `contracts/schema.json`) — `kind: "stats"`
accepts either, distinguished structurally (no `_type` discriminator needed: `test_type` only
exists on `GroupComparisonConfig`, `correlation_type` only on `CorrelationConfig`).

## Mode toggle

- [x] "Classification" / "Correlation" radio (`classification_radio`, `correlation_radio`) →
      `SegmentedControl` (DESIGN.md §4.2 rule 9), same two labels, same effect (swaps the subjects-table columns and the
      mode-specific fields below).

## Subjects table

- [x] Subject / Simulation / Response (classification) or Effect Size + weight (correlation) rows
      → the shared `ParticipantsField` (DESIGN.md §4.4.1): the same header band, summary line,
      table and per-row "Why not" reason as `SubjectsField`, over a row list rather than a set —
      `testType: "paired"` is exactly a design in which one subject appears twice, which a set
      control cannot express. Columns: # / Subject `Select` / Simulation `Select` filtered to that
      subject / the mode-specific column(s) (`Select` Responder/Non-responder, or `NumberInput`
      effect size + optional weight).

## Shared config (both `GroupComparisonConfig` and `CorrelationConfig`)

- [x] `analysis_name` → `TextInput`, required.
- [x] `cluster_threshold` (default 0.05), `cluster_stat` (mass/size, default mass),
      `n_permutations` (default 1000), `alpha` (default 0.05), `n_jobs` (default -1, "-1 = all
      CPUs" help text) → `NumberInput`/`Select` under an "Advanced" section, same defaults.
- [x] `tissue_type` (grey/white/all, default grey), `nifti_file_pattern` (nullable — blank means
      "derive automatically from tissue type", same as Qt's `None`) → `Select` + `TextInput`.
- [x] `space` (mni/fsaverage, default mni), `fsaverage_field` (default `TI_max`),
      `fsaverage_spacing` (default 5) → shown only when `space === "fsaverage"`.
- [x] `atlas_files` (multi-select of bundled atlas filenames) → left as free-text tags for now —
      no `/api/catalog/atlases?kind=` variant returns *group-level* MNI atlas filenames (the
      existing route is per-subject); reported as a gap, not hardcoded.

## Classification only (`GroupComparisonConfig`)

- [x] `test_type` (unpaired/paired), `alternative` (two-sided/greater/less),
      `group1_name`/`group2_name` (defaults "Responders"/"Non-Responders"), `value_metric`
      (default "Current intensity" — sentence case per design QA finding #27, was "Current
      Intensity") → same fields, same defaults.

## Correlation only (`CorrelationConfig`)

- [x] `correlation_type` (pearson/spearman), `use_weights` checkbox (default on, same tooltip:
      "Use weights from CSV if available" → reworded since there is no CSV import here — "Apply
      per-subject weights"), `effect_metric` (default "Effect size", was "Effect Size"),
      `field_metric` (default "Electric field magnitude", was "Electric Field Magnitude") — sentence
      case per design QA finding #27 → same fields.

## Run

- [x] Queues a `stats` job (R3) instead of an in-process worker. The Plan panel (`POST
      /api/plan/stats`) shows estimated cost and lock conflicts against the subjects involved.
- [x] Client-side checks before Run mirror the Qt validation (`analysis_name` required, ≥2
      subjects with a simulation, classification needs both response values present) — the
      contract's `/api/validate/stats` is also called and its errors surfaced, since both configs
      are real schema entries.

## Known gaps

- No group-level MNI atlas catalog route — `atlas_files` is manual free text.

## Round 2 (ra_12 #7/#8/#27)

- [x] Plan card now renders the shared `pages/panels/PlanSummary` (Jobs · CPUs · Memory · Outputs ·
  Waits) instead of a page-local `DefinitionList` with only cost.
- [x] Run-enabled rule (DESIGN.md §6.3): "Run analysis" is no longer `disabled={!canRun}` — it is
  always clickable; clicking with an incomplete form shows a toast with the first client error
  instead of doing nothing.
- [x] Default metric labels moved to sentence case per design QA #27: "Current Intensity" →
  "Current intensity", "Effect Size" → "Effect size", "Electric Field Magnitude" → "Electric field
  magnitude".

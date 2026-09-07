# Analyzer — parity checklist

Harvested from `tit/gui/analyzer_tab.py` (2731 lines) and `tit/constants.py`
(`FIELD_REGISTRY`), `tit/analyzer/field_selector.py`. Schema source of truth:
`AnalyzerConfig` in `contracts/generated/config.schema.json`.

Legend: [x] built · [~] built with a deliberate simplification (noted) · [ ] not built (gap, noted)

## 2026-09-06 — the target is a job's, not the page's

Maintainer: *"The TARGET section must become per-job — each row of the jobs table owns its own
analysis target so we can modify our analysis input per job."* Two page sections went away:

- **TARGET** — the ROI is a cell of a job row (`JobRows.tsx`), stated in words and edited in a
  dialog holding the shared `pages/_shared/roi` picker scoped to that row. The page's own
  `SphereRows.tsx` is no longer mounted here (the picker's spherical mode is what a row uses; the
  file survives because `pages/pipeline/editors.ts` imports its `Sphere`/`EMPTY_SPHERE`).
- **OUTPUT** — `pages/results` owns a simulation's existing analyses; `ResultsPanel.tsx` deleted.

What a row expands to is unchanged from 2.5.0's `build_single_analysis_commands`: one config per
row, except that N sphere rows are N separate analyses (`center`/`radius` are a single point, never
a union), and with "Combine regions into one ROI" unchecked each selected region is its own
analysis. A group run needs every row to agree about the target as well as the simulation, space
and field — refused on the Run button, never silently resolved to the first row's answer.

## Mode

- [x] Single / Group radio (`is_group_mode`, default single) → `SegmentedControl` (DESIGN.md §4.2
      rule 9: a small exclusive choice is one idiom everywhere).
- [~] Qt's "Subject-Simulation Pairs" table allows an _arbitrary_ list of
  (subject, simulation) rows in both modes, but only ever submits them as:
  **single mode** = exactly one pair (`run_single_analysis` hard-errors on
  `pairs_table.rowCount() != 1`); **group mode** = N subjects that must all
  share the _same_ simulation name (`build_group_analyzer_command`: "Group
  analysis requires all subjects to use the same simulation/montage"). This
  matches `AnalyzerConfig` exactly (`subject_id: str` vs `subject_ids: list[str]`,
  one `simulation: str` field either way) — built as: single mode = one
  Subject combobox + one Simulation combobox; group mode = a `SubjectPicker`
  (multi) + one shared Simulation combobox (options = the first selected
  subject's simulations; the real pick is validated server-side).

## Subject / simulation selection

- [x] Subject select, populated from `/api/catalog/subjects`.
- [x] Simulation select, populated from `/api/catalog/simulations?subject=`
      (`Simulation` combobox in Qt).
- [x] "Quick Add" pairs dialog — not reproduced; superseded by the
      single-pair / SubjectPicker simplification above (no multi-pair table to
      quick-fill).

## Space / tissue / field row

- [x] Space: Mesh / Voxel radio (`space_mesh`/`space_voxel`, default Mesh).
- [x] Tissue: GM / WM / GM+WM select, enabled only in Voxel space, forced to
      GM when Mesh is selected (`update_atlas_visibility`).
- [x] Field select, built from `FIELD_REGISTRY` (mirrored as a local TS
      constant — no `/api/schema`-reachable field metadata exists yet, tooltip
      text ported verbatim): `TI_max`, `TI_normal`, `TI_avg`, `hf_peak`, `hf_sar`
      (`mTI_max` skipped — same quantity as `TI_max` under the mTI mesh spelling,
      per the Qt tab's comment). Default = "Auto" (`field: null`, resolves
      TI_max/mTI_max automatically), tooltip = each field's registry description.
      Options are further restricted to the selected simulation's
      `SimulationDetail.fields` (whichever of TI_max/mTI_max that simulation
      actually has).
- [x] **TI_normal is mesh-only, and the UI says why**: disabled as a Select
      option in Voxel space, with help text quoting
      `field_selector._select_voxel`'s exact reason — "TI_normal is a surface
      (mesh) field and is not exported to NIfTI; select space='mesh' to analyze
      it." (Qt does not actually enforce this in the widget — the ValueError
      only fires at runtime in `select_field_file` — so this is a UI improvement
      over parity, not a regression.)

## Type / target group

- [x] Type: Spherical / Cortical radio (`type_spherical`/`type_cortical`,
      default Spherical) drives which target group shows, **plus a third
      Subcortical option** per the task brief and `AnalysisType` in
      `contracts/generated/config.schema.json` (`spherical | cortical | subcortical`). The Qt tab
      has no third radio — voxel-space cortical just relabels its button
      "Sub/Cortical" (`update_cortical_button_text`) while still sending
      `analysis_type="cortical"`.
- [ ] **Gap, called out in-page with a `Callout`**: `AnalysisType.subcortical`
      is accepted by the schema/dataclass but
      `tit.analyzer.__main__._run_single` only branches on `"spherical"` /
      `"cortical"` — a submitted `subcortical` job is a silent no-op today (see
      `AnalyzerConfig`'s docstring Notes in `contracts/generated/config.schema.json`). Built
      anyway per the task brief, with an inline warning instead of hiding it.

### Spherical target

- [x] Coordinate Space: Subject / MNI radio (`coord_space_subject`/`mni`,
      default Subject) — one shared choice for every sphere row
      (`_update_coordinate_space_labels` relabels all rows together; there is no
      per-row space).
- [x] Sphere table, one row per sphere (`x, y, z, r`), Add/Remove Selected
      buttons (`_add_sphere_row`/`_remove_selected_sphere_rows`), seeded with one
      row. N rows → N separate analyses (`build_single_analysis_commands`,
      `run_single_analysis` queues `cmds[1:]`) — since `AnalyzerConfig` has no
      list-of-spheres field, this is reproduced client-side as N separate
      `analyzer` job submissions on Run, one `AnalyzerConfig` per row, matching
      the Python multi-command queue exactly.
- [~] **Single mode only.** Group mode's Python path
  (`build_group_analyzer_command`) always calls the _singular_
  `_parse_coords_radius()` — never the multi-sphere path — so group mode is
  built with exactly one sphere row (Add/Remove hidden), matching parity.
- [x] "View in Freeview" button (`view_in_freeview_btn`): loads the subject's
      T1 normally, or the MNI152 template when Coordinate Space = MNI
      (`load_t1_in_freeview`) → `GET /api/view/subject` or
      `GET /api/view/custom?path=.../MNI152_T1_1mm.nii.gz`, then
      `POST /api/viewers/freeview`.

### Cortical / Subcortical target

- [x] Atlas select — mesh space uses the subject's cortical atlases
      (`atlas_name_combo`, `kind=cortical`); voxel space (cortical or
      subcortical) uses `atlas_combo`, `kind=cortical|subcortical` matching the
      selected Type.
- [x] "List Regions" → region multi-select populated from
      `/api/catalog/atlases/regions?subject=&atlas=&hemi=` (`show_regions_btn`
      dialog in Qt; a `MultiSelect` combobox here, filterable, same
      region-count/discoverability goal without a modal).
- [x] "Clear" button clears all selected regions (`clear_regions_btn`).
- [x] Region chips with the atlas region name (`region_chips` in Qt shows
      name + label index; the id here is `"lh-<name>"`/`"rh-<name>"`/numeric
      label id, matching `Region.id` from the contract — shown in the chip via
      `MultiSelect`, not the bespoke chip widget).
- [~] Hemisphere filter (`hemi=lh|rh|both`) is exposed as part of the atlas
  region fetch (cortical atlases return both hemispheres pre-merged, as Qt's
  region dialog does; no separate hemi toggle in the form — this matches
  today's default `AtlasROI`-less analyzer path, which has no hemisphere
  field).

## Actions

- [x] Run — every long action is a job (DESIGN.md rule 1): Plan panel
      (`POST /api/plan/analyzer`, once per config being submitted — N calls for
      N sphere rows, merged into one summary) + `AlertDialog` on
      `will_overwrite` (Qt: `confirm_overwrite()` + a `ConfirmationDialog`
      listing subject/simulation/space/type/metric — reproduced as the
      AlertDialog's description plus the Plan panel's own resolved-output list).
      Run button labelled "Run analysis" / "Queue N jobs" from the plan, per
      DESIGN.md's Run-button-from-plan rule.
- [x] Stop — not reproduced as a page control: v3 stops jobs from the Jobs
      rail/table (`POST /api/jobs/{id}/cancel`), not from the originating page,
      per the job-model design (`stop_analysis`/`RunStopButtons` retired in
      favour of the shared Jobs rail).
- [x] Console output (`ConsoleWidget`, `update_output`) → superseded by the
      Jobs rail's per-job console (`JobConsole`), not duplicated on this page.

## Results

- [x] Gmsh Visualization group (`gmsh_subject_combo`/`gmsh_sim_combo`/
      `gmsh_analysis_combo`/`launch_gmsh_btn`) → a Results section: subject +
      simulation reuse the form's own selection; analyses list from
      `/api/catalog/analyses?subject=&simulation=`; "Open in Gmsh" per row posts
      `path = Analysis.msh` to `POST /api/viewers/gmsh` (disabled with a
      tooltip when `msh` is `null`, which every seeded fixture currently is).
- [x] Analysis summary → `DataTable` from
      `/api/catalog/analyses/{name}/summary` (`TableData`).
- [x] Histogram / report artifact (`Analysis.pdf`) → `ArtifactList` "Open"
      (disabled when `pdf` is `null`).
- [x] "Open in Freeview" for a voxel-space analysis result (not present as a
      dedicated Qt button — the Qt tab only launches Freeview for coordinate
      picking, not for viewing a finished voxel overlay; added per the task
      brief) → `GET /api/view/analysis?subject=&simulation=&field=&roi=` then
      `POST /api/viewers/freeview`, shown only for `space: "mni"|"subject"`
      voxel analyses (mesh analyses have no NIfTI overlay to view this way —
      use Gmsh instead).

## Not reproduced (superseded by shared v3 chrome, not gaps)

- Progress dialog for "Loading Atlas Regions" (`show_available_regions`) →
  `MultiSelect`'s own `loading` state.
- `ConfirmationDialog.confirm` free-text details blob → `AlertDialog`
  description + the Plan panel's resolved output list (same information,
  structured).
- `force_ui_refresh`, `disable_controls`/`enable_controls`,
  `_update_input_widths`, `resizeEvent` — Qt-specific widget plumbing with
  no v3 equivalent needed (React re-renders + CSS handle all of this).

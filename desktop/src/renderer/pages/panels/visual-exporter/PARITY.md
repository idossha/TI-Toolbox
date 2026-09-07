# 3D Visual Exporter — parity checklist

Qt source: `tit/gui/extensions/visual_exporter.py` (1431 lines, `EXTENSION_NAME = "3D Visual
Exporter"`): a `Mode` constant class, a `BlenderExportThread(BaseProcessThread)` running a list of
subprocesses, and `VisualExporterWidget` with four stacked panels behind four radio buttons.

The panel is `PanelId` `visual-exporter`, off by default, toggled in Settings → Panels (server
truth `settings.panels`, `tit/server/routes/settings.py::_VALID_PANELS`).

## The job kind

`blender` already existed (`tit/jobs/kinds.py`, `tit/jobs/costs.py`, `tit/jobs/spec.py`,
`routes/plan.py::_plan_blender`, `routes/validate.py`'s `AMBIGUOUS_KIND_CLASSES`), discriminated by
the config's own `_type` — so three of the four modes needed no backend change at all: they submit
`MontageConfig` / `VectorConfig` / `RegionConfig` to the kind that already runs
`simnibs_python -m tit.blender <spec>`.

The **fourth** did. 2.5.0's sub-cortical mode had no config dataclass and no runner: `_run` called
`extract_labels` / `nifti_to_mesh` / `nifti_to_field_ply` **inline on the Qt main thread**, so the
window froze for the duration and the export left no trace in any job list. Added in this round,
mirroring that branch step for step:

- `tit/blender/config.py::SubcorticalConfig` (registered in `tit.config_io`'s
  `CONFIG_CLASS_REGISTRY` and `_TYPE_DISCRIMINATED_BY_NAME`, hence a `contracts/schema.json` `$def`
  and a `PipelineConfig` union member);
- `tit/blender/subcortical_exporter.py::run_subcortical`;
- the `"SubcorticalConfig"` entry in `tit/blender/__main__.py`'s dispatch and in
  `routes/validate.py`'s `AMBIGUOUS_KIND_CLASSES["blender"]`.

Nothing about the filesystem work changed: the same calls in the same order, `clean_threshold=0.1`,
the same `subcortical_<suffix>.{stl,msh,ply,nii.gz}` names, the same `full`/`labels_10_49` +
`clean`/`raw` suffix rule, the same sorted-glob field-NIfTI lookup, the same temp-file cleanup.

## Selection

- [x] Subject / Simulation combos → two `ui/Select` fields in a "Selection" card. Simulation is
      filtered to the chosen subject and disabled until one is chosen.
- [x] "Refresh" button → dropped. React Query owns the lists; there is no stale combo to refresh.
- [x] Radio tabs (Cortical Regions / Field Vectors / Montage Visualizer / Sub-cortical) →
      `ui/SegmentedControl` (DESIGN.md: one-of-N in one 28 px row), same four modes, same default.

## Cortical regions

- [x] Atlas combo (`DK40`, `a2009s`; DK40 default) → `Select`, same options and default.
- [x] Field line edit (`TI_max`) → `TextInput`, same default.
- [x] Regions `QListWidget` (multi-select) with its own "Select all / Clear / Search…" row →
      `ui/SelectionList`'s `SelectionPicker`, the app's one selection grammar: All · None, an
      always-on filter, an `N of M selected` badge, and a trigger that states the selection. The
      region list comes from `GET /api/catalog/atlases/regions` instead of the widget's own
      in-process `atlas2subject(..., split_labels=True)` call; keys are rebuilt as `lh.<name>` /
      `rh.<name>`, which is what `region_exporter._resolve_selected` matches and what each STL is
      named.
- [x] Nothing selected ⇒ `skip_regions=True` (whole grey matter only) — the Qt rule, stated in the
      field help rather than left implicit.
- [x] One click runs **two** jobs, STL then PLY, with `keep_meshes=True` — exactly `_run`'s two
      `commands.append` calls. Asserted in `tests/unit/visual-exporter-defaults.test.ts` and in the
      e2e spec's submitted-body check.

## Field vectors

- [x] Vector length / width, Anchor (tail|head), Color scale (rgb|magscale) → `NumberInput` /
      `Select`, same ranges, steps and defaults (1.0 / 1.0 / tail / rgb).
- [x] Blue/Green/Red percentiles (50/80/95), shown only for `magscale` → same values, same
      conditional rendering as Qt's `_toggle_magscale`.
- [x] Seed (42), Sample count (10000), "Use maximum (all nodes)" disabling the count → same, with
      the disabled reason in the field help.
- [x] Export CH1/CH2, TI_sum, TI_normal checkboxes → same three, all off by default.
- [x] `vector_scale` / `vector_length` fixed at 1.0 — hardcoded by `_run`, not shown in either UI.
- [ ] **Dropped: the "Enable mTI (4 meshes)" block and its four `Browse…` TDCS-mesh pickers.**
      `VectorConfig` has no mesh-3/mesh-4 fields — `run_vectors` auto-detects mTI from the
      simulation's own TDCS meshes (`config.py`: "mTI mode is auto-detected when TDCS meshes 3 and 4
      exist") and `_run` never passed the four line edits to the config at all. They were dead
      controls in 2.5.0; reproducing them would be reproducing a bug.

## Montage visualizer

- [x] "Show only montage electrodes" checkbox → same, and still the negation of
      `show_full_net`.
- [x] Electrode diameter (10.0 mm) / height (6.0 mm) → `NumberInput` with `unit="mm"`, same
      defaults and ranges.
- [x] The Qt info label listing what the scene contains and where it lands → one help sentence
      naming `visual_exports/sub-<id>/montage_publication/`.

## Sub-cortical

- [x] NIfTI file + `Browse…` → `TextInput`, empty meaning the subject's own
      `<m2m>/segmentation/labeling.nii.gz` (Qt pre-filled the same path; the runner resolves it).
- [x] "Labels to extract" (`10,49`) → same text field; the parse error is the Run button's blocking
      reason instead of a `QMessageBox` after the click.
- [x] "Remove small disconnected components" → `Checkbox`.
- [x] "Field (for PLY)" (`TI_max`) and the note about needing a simulation → same field, same note.
- [x] Simulation optional in this mode only — the Qt validation rule, kept.
- [x] "Search && Select Labels…" (`_show_lut_table` / `AtlasRegionFinderDialog` over a FreeSurfer
      LUT) → the same `SelectionPicker` the regions mode uses, fed by the new
      `GET /api/catalog/nifti/labels?subject=&path=` (`tit/catalog.py::nifti_labels`), which lists
      every integer label present in the volume with its LUT name and voxel count. Names and
      caching come from the toolbox's own segstats path (`compute_segstats` +
      `resolve_lut_for_atlas`, sidecar `<name>_labels.txt`) — the same machinery
      `VoxelAtlasManager.list_regions` uses, so a second visit is a file read. The typed field is
      still there as the fallback for a subject whose volume cannot be read (see below).

## Running

- [x] "Run Export" / "Stop" + an in-panel `ConsoleWidget` → one `blender` job per config, so the
      output is the Jobs rail and the terminal, and Stop is the rail's Stop. The panel has no
      console of its own, by the same rule every other v3 page follows.
- [x] Plan card (`pages/panels/PlanSummary`) — jobs, CPU, memory, resolved outputs — which the Qt
      widget had no equivalent of at all.

## Plan card

`_plan_blender` (`tit/server/routes/plan.py`) now resolves the destination for **every** mode
rather than only for a config that already carries an `output_dir` — which none of the four set,
so the card used to show an empty Outputs column and a "cannot be previewed here" warning for
every export the panel could submit. `_blender_output_dir` restates each exporter's own
`_resolve_paths` formula beside a reference to the file it came from:

| mode | directory |
|---|---|
| `RegionConfig` | `visual_exports/sub-<id>/<sim>/<stl\|ply>` |
| `VectorConfig` | `visual_exports/sub-<id>/<sim>/vectors` |
| `MontageConfig` | `visual_exports/sub-<id>/montage_publication` |
| `SubcorticalConfig` | `visual_exports/sub-<id>/sub-cortical` |

An `output_dir` already on the config still wins. The formulas are restated rather than imported
because the exporters need `bpy`/`trimesh`, which exist only inside the SimNIBS container — which
is also why `tests/test_plan_routes.py::TestPlanBlenderOutputDir` asserts all four against the
route: a drift between the two sides is otherwise invisible until a user reads the wrong path.

## Known gaps (reported, not hacked around)

- **The label browser needs a readable volume.** `GET /api/catalog/nifti/labels` 404s for a
  subject with no segmentation, a path outside the project jail, and an unreadable file alike
  (deliberately one status — the route must not confirm what exists outside the jail). All three
  fall back to the 2.5.0 typed field, which is why `parseLabels` is still here and still tested.
- **`GET /api/catalog/atlases/regions` needs a built subject.** For a subject with no m2m
  segmentation the region picker is empty rather than erroring; the Run button's own blocking
  reason still names the missing subject.

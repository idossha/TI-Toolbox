# Known Issues — 2026-08

Drafted defect reports from a code-reading pass. Not filed as GitHub issues.
Each item was verified by reading the cited code, not inferred from
description alone.

---

## 1. Analyzer GUI "Field" selector is a dead control

**Severity**: Medium (feature does not work — user selection is silently
discarded, single-subject and group analysis always fall back to the
default field)

**Evidence**:
- `tit/gui/analyzer_tab.py:190-202` — `self.field_combo` is built from
  `const.get_field_spec`/the field registry and is a real, populated
  `QComboBox` (not disabled, not decorative — it has a tooltip that updates
  per-selection at `tit/gui/analyzer_tab.py:1216-1219`).
- `tit/gui/analyzer_tab.py:2909` (single-subject config) and
  `tit/gui/analyzer_tab.py:2055` (group config) both write
  `"field": self.field_combo.currentData()` into the JSON config dict that
  gets serialized and passed to `simnibs_python -m tit.analyzer config.json`.
- `tit/analyzer/__main__.py:70-90` — `_run_single()` builds the
  `Analyzer` from the parsed config dict but only reads `subject_id`,
  `simulation`, `space`, `tissue_type`, `output_dir`; it never reads
  `data["field"]` or `data.get("field")`. `_run_group()`
  (`tit/analyzer/__main__.py:43-67`) similarly never reads a `field` key
  before calling `run_group_analysis`.
- `tit/analyzer/analyzer.py:195-217` — `Analyzer.__init__` has no `field`
  parameter at all. It calls
  `select_field_file(subject_id, simulation, space, tissue_type=self.tissue_type)`
  with no `field=` argument, so it always resolves the default field
  (`TI_max`/`mTI_max`).
- `tit/analyzer/group.py:77-90` — `run_group_analysis()` also has no `field`
  parameter.
- By contrast, `tit/analyzer/field_selector.py:25-30` shows
  `select_field_file()` already accepts an optional `field: str | None = None`
  keyword that would resolve a non-default field (e.g. `hf_peak`) from
  `constants.FIELD_REGISTRY` — the plumbing to honor a user's field choice
  already exists, it's just never invoked with the GUI's value.

**Reproduction**: In the Analyzer tab, change the Field dropdown from its
default entry to any other field (e.g. a high-frequency metric), run a
single-subject or group analysis. The resulting analysis is computed on the
default field (`TI_max`/`mTI_max`) regardless of what was selected in the
dropdown — no error, no warning, silently wrong field.

**Suggested fix**: Small plumbing fix.
- Add a `field: str | None = None` parameter to `Analyzer.__init__` (and
  `run_group_analysis`) and pass it through to `select_field_file(..., field=field)`.
- In `tit/gui/analyzer_tab.py`, keep writing `"field": self.field_combo.currentData()`.
- In `tit/analyzer/__main__.py`, read `data.get("field")` in both
  `_run_single()` and `_run_group()` and pass it into `Analyzer(...)` /
  `run_group_analysis(...)`.

---

## 2. Ex-search/mex GUI overwrite check targets a directory the backend never writes to — same-run ROI collisions with no warning

**Severity**: High (silent data loss: results from an earlier ROI in the
same queued run can be overwritten by a later ROI with no prompt, no error)

**Evidence**:
- `tit/gui/ex_search_tab.py:2552-2567` (`_build_ex_config`) and
  `tit/gui/ex_search_tab.py:2617-2632` (`_build_mex_config`) both set
  `run_name=eeg_net` on the `ExConfig`/`MExConfig` dataclass — the run name
  is just the selected EEG net name, with no ROI component.
- `tit/opt/ex/ex.py:46-47` — the backend computes
  `run_name = config.run_name or time.strftime(...)` and
  `output_dir = pm.ex_search_run(config.subject_id, run_name)`. Same pattern
  in `tit/opt/mex/mex.py:45-46` via `pm.m_ex_search_run`.
- `tit/paths.py:447-453` — `ex_search_run(sid, run)` /
  `m_ex_search_run(sid, run)` both resolve to
  `os.path.join(self.ex_search(sid), run)` — i.e. the real, actual output
  directory used by both backends is `<subject>/ex-search/<eeg_net>/` (or
  `m-ex-search/<eeg_net>/`), with no ROI name in the path at all.
- `tit/opt/ex/results.py:33-87` (`save_run_config`) writes a single fixed
  `run_config.json` directly into `output_dir` (line 83), and
  `tit/opt/ex/results.py:156-176` (`save_csv`) writes a single fixed
  `final_output.csv` into the same directory (line 176) — both filenames are
  ROI-independent.
- Meanwhile the GUI's pre-run overwrite guard, at
  `tit/gui/ex_search_tab.py:2809-2811`, checks a *different* path:
  `output_dir_name = f"{roi_name}_{selected_net_name}"` /
  `roi_output_dir = os.path.join(ex_search_dir, output_dir_name)` — a
  directory the backend never creates or writes to.

**Consequence, verified by tracing the call chain**: because the overwrite
check looks at `ex_search_dir/{roi_name}_{net}` (never populated) while the
backend actually writes to `ex_search_dir/{net}`, the check will essentially
never find an existing directory and will never prompt for confirmation.
Concretely, when a user queues multiple ROIs against the same EEG net in one
ex-search/mex run (a supported, normal workflow —
`self.roi_processing_queue` is iterated by `run_roi_pipeline`), each ROI's
run reuses the identical `ex_search_dir/{net}` directory
(`os.makedirs(output_dir, exist_ok=True)` at `tit/opt/ex/ex.py:48`), and each
subsequent ROI's `run_config.json`/`final_output.csv`/mesh outputs silently
overwrite the previous ROI's results in place, with no user-visible warning
at any point.

Two other `f"{roi_name}_{net}"` occurrences in the same file
(`tit/gui/ex_search_tab.py:2905` inside `run_current_roi_analysis`, and
`:3037` inside `run_current_roi_mesh_processing`) reference the same
(non-existent) path convention, but `run_current_roi_analysis` is dead code
(defined, never called anywhere else in the file) and the `:3037` occurrence
is only used in a debug log string, so neither of those two additionally
breaks the pipeline beyond the overwrite-check issue above — though the
`:3037` log message is itself misleading about where output actually landed.

**Reproduction**: In the Ex-Search (or mTI/mex) tab, select an EEG net and
leadfield, queue two or more ROIs for a single run. Run the pipeline. The
second (and any subsequent) ROI's `run_config.json`/`final_output.csv` in
`derivatives/SimNIBS/sub-<id>/ex-search/<net>/` overwrite the first ROI's,
with no overwrite-confirmation dialog shown at any point in the run.

**Suggested fix**: Make the `run_name` passed into `ExConfig`/`MExConfig`
include the ROI, e.g. `run_name=f"{roi_name}_{eeg_net}"` in
`_build_ex_config`/`_build_mex_config`, so the GUI's overwrite check
(already keyed on `f"{roi_name}_{net}"`) matches the backend's real output
directory. Alternatively, change the GUI's overwrite check and log strings
to match the backend's actual `f"{net}"`-only directory. Either way, both
sides need to agree on the same path.

---

## 3. mex "Force left/right symmetry" likely raises `ValueError` for real SimNIBS leadfield filenames

**Severity**: High (checked feature is unusable for realistically-named
leadfields, with no GUI-exposed workaround)

**Evidence**:
- `tit/opt/mex/mex.py:113-123` (`_infer_symmetry_eeg_csv`):
  ```python
  leadfield_name = Path(config.leadfield_hdf).name
  net_name = leadfield_name.removesuffix(".hdf5").removesuffix("_leadfield")
  ```
  `str.removesuffix()` only strips the given suffix if the string *ends with*
  it exactly. For a leadfield file named `<sid>_leadfield_<net>.hdf5` (net
  name comes *after* `_leadfield_`, not before it), the stem after stripping
  `.hdf5` is `<sid>_leadfield_<net>`, which does **not** end with the literal
  string `_leadfield` (it ends with `_leadfield_<net>`), so the second
  `removesuffix("_leadfield")` call is a no-op and `net_name` stays as the
  entire garbled stem `<sid>_leadfield_<net>`.
- That this is the real, expected filename shape (not a hypothetical) is
  confirmed by `tit/opt/leadfield.py:181-199` (`list_leadfields`), which
  parses existing leadfield files and checks the `"_leadfield_" in stem`
  case **first** — splitting on `"_leadfield_"` and taking everything after
  it as the net name — before falling back to a plain `_leadfield` suffix.
  This is also consistent with SimNIBS's own `TDCSLEADFIELD` output-naming
  convention (`tit/opt/leadfield.py:129-153` builds and runs the
  `TDCSLEADFIELD` job, then globs `output_dir.glob("*.hdf5")` for whatever
  SimNIBS wrote).
- With `net_name` left as the garbled full stem, `_infer_symmetry_eeg_csv`
  then calls `canonical_template_coord_path(net_name)`
  (`tit/opt/ex/buckets.py:234-245`), which does an **exact**-match dict
  lookup against `_CANONICAL_TEMPLATE_COORD_FILES`
  (`tit/opt/ex/buckets.py:50-57`, keys like `"GSN-HydroCel-185"`,
  `"GSN-HydroCel-185.csv"`) — no fuzzy/substring matching — so it returns
  `None` for the garbled name.
- The fallback candidate,
  `Path(pm.eeg_positions(subject_id)) / f"{net_name}.csv"`
  (`tit/opt/mex/mex.py:122`), then looks for a file literally named
  `<sid>_leadfield_<net>.csv`, which will not exist (the real file is
  `<net>.csv`). `_infer_symmetry_eeg_csv` returns `None`.
- `tit/opt/mex/mex.py:126-140` (`_build_symmetry_mirror_map`): when
  `config.symmetry_eeg_csv` is `None` (the GUI never sets it — see below)
  and `_infer_symmetry_eeg_csv` returns `None`, it raises:
  ```python
  raise ValueError(
      "symmetric_bucket requires a valid symmetry_eeg_csv or an inferable "
      "EEG-position CSV from the selected leadfield."
  )
  ```
- No GUI workaround exists: `tit/opt/config.py:978` shows
  `MExConfig.symmetry_eeg_csv: str | None = None` is a real, settable field,
  but `grep` for `symmetry_eeg_csv` in `tit/gui/ex_search_tab.py` finds no
  hits — `_build_mex_config`
  (`tit/gui/ex_search_tab.py:2597-2632`) never sets it, and there is no
  widget for it. A user who checks "Force left/right symmetry"
  (`self.mex_symmetric_bucket_cb`, `tit/gui/ex_search_tab.py:1640-1641`) has
  no way to supply the CSV manually through the GUI.

**Reproduction**: Generate a leadfield through the normal SimNIBS
`TDCSLEADFIELD` path (named `<sid>_leadfield_<net>.hdf5`), select it in the
mTI/mex tab, check "Force left/right symmetry", and run. The backend raises
`ValueError` from `_build_symmetry_mirror_map` before the search starts.

**Suggested fix**: Reuse the same split logic already implemented in
`tit/opt/leadfield.py:181-199` (check for `"_leadfield_" in stem` first and
split on it to isolate the trailing net name; fall back to the current
`removesuffix("_leadfield")` only when that substring isn't present) inside
`_infer_symmetry_eeg_csv`, rather than relying on `removesuffix` alone.

---

## Notes on scope

All three issues above were confirmed by reading the current code on this
branch. No additional issues were substituted or added speculatively — if
any of the three had not reproduced on inspection, it would have been noted
here instead of written up as a finding.

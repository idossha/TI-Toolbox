# Lane FX4 — source forward (EEG forward solution)

Workflow 2, `dev/notes/v3-pipelines-program.md` §7. Finding handed to this lane (s2-notes open
issue 2): the `source` pipeline on `sub-101` / net `EEG10-10_UI_Jurak_2007` is accepted, starts,
computes for ~10 minutes and then dies with
`AttributeError: No mne.source_space attribute _complete_source_space_info`
(job `674801945bee46aa`, 2026-09-03).

**Headline: that `AttributeError` was the first of four separate faults on the path from a config
to a forward solution.** Nobody had ever run this pipeline to the end, so each fault was hidden
behind the one in front of it — and every one of them only shows itself *after* the ~11-minute FEM
leadfield. Pinning mne, the fallback the lane brief allowed, would have fixed exactly one of them.

## 1. What the versions actually are

| Where | Value | How measured |
|---|---|---|
| `mne` in `ti-toolbox-fad740e5-tit-1` | **1.12.1** | `docker exec … simnibs_python -c "import mne; print(mne.__version__)"` |
| `numpy` / `scipy` in the same env | 1.26.4 / 1.17.1 | same call |
| `h5io` (mne's HDF5 backend) | **not installed** | `simnibs_python -c "import h5io"` → ModuleNotFoundError |
| `mne` spec in `container/blueprint/Dockerfile.ti-toolbox` | was `"mne~=1.5"` (line 203) | — |
| `Dockerfile.ti-toolbox.layered` | no mne line at all (builds on the base) | `grep -n mne` |

Project memory said "the code was written for mne~=1.5, pin mne". The pin *is already there* — and
it is not doing what its comment says. `~=1.5` is a two-component compatible-release specifier: it
means `>=1.5, ==1.*`, i.e. **any 1.x at or above 1.5**, which is how the image ended up with
1.12.1. Narrowing it to `~=1.5.0` would be a real pin, but it is the wrong fix (§2 fault 2 is not
an mne problem at all), so the Dockerfile now spells the range it always meant — `"mne>=1.5,<2"` —
with a comment recording the measured resolution and saying not to narrow it to work around a
forward failure. The comment's stated fear (a newer mne dragging in numpy 2.x and breaking the
`nan_to_num` patch) did not happen: mne 1.12 asks for `numpy<3,>=1.26`, and the image's numpy
1.26.4 satisfies it.

## 2. Root cause: four faults, in the order a run hits them

### Fault 1 — mne ≥ 1.6's lazy namespace (SimNIBS's code)

`mne` is assembled by `lazy_loader`; `mne.source_space` became a *subpackage* exposing public names
only, and a private submodule is not bound onto its parent until something imports it. Three of
`simnibs/eeg/utils_mne.py`'s lookups therefore raise:

| `utils_mne.py` | Expression | On mne 1.12.1 |
|---|---|---|
| 235 | `mne.source_space._complete_source_space_info` | moved to `mne.source_space._source_space` |
| 283, 344 | `mne.morph._get_src_data`, `._hemi_morph` | exist; `mne.morph` unbound until imported |
| 439, 482 | `mne.forward._make_forward._prepare_for_forward`, `._to_forward_dict` | exist; `_make_forward` unbound until imported |

All five callables still exist with signatures matching what SimNIBS passes — checked with
`inspect.signature`, not assumed: `_prepare_for_forward(src, mri_head_t, info, bem, mindist,
n_jobs, *, bem_extra, trans, info_extra, meg, eeg, ignore_ref, allow_bem_none, on_inside,
verbose)`, `_to_forward_dict(fwd, names, fwd_grad, coord_frame, source_ori)`,
`_hemi_morph(tris, vertices_to, vertices_from, smooth, maps, warn)`, `_get_src_data(src,
mri_resolution)`, and `mne.SourceMorph.__init__` still takes exactly the 17 positionals
`make_source_morph` passes. **Only the path to reach them moved** — a re-attach, not a rewrite.

### Fault 2 — cortech rename (SimNIBS's code, *not* an mne problem)

`AttributeError: 'Sphere' object has no attribute 'morph_mat'`. SimNIBS 4.6 rewrote
`simnibs.utils.transformations.cross_subject_map` on top of `cortech.surface.Sphere` (its own
return annotation says `dict[str, cortech.Sphere]`), but `utils_mne.setup_source_space:103` still
reads the pre-cortech `v.morph_mat`. The matrix is still produced, under cortech's name
`Sphere._mapping_matrix`: a sparse `(target.n_vertices, self.n_vertices)` map filled in by
`Sphere.project`, which for `cross_subject_map(subject, "fsaverage")` is `(n_fsaverage,
n_subject)` — exactly the orientation `mne.morph._hemi_morph` wants for `maps`. Verified
numerically: morph matrix `(20484, 491524)` = 2 × 10242 fsaverage5 vertices × 2 × 245762 subject
vertices.

This is why pinning mne would not have fixed the pipeline: it would have traded one ten-minute
failure for another.

### Fault 3 — the Info's channel order (**our** code, `tit/source/forward.py`)

`AssertionError: Inconsistencies between channels in Info and leadfield` (job
`c8ef9a4a2d454ff0`). `utils_mne.make_forward:430` asserts `info["ch_names"] ==
forward["ch_names"]` — ordered, element-wise. `_build_montage_info` built the Info straight from
the net CSV (`Fp1, Fpz, Fp2, …, Cz@35`), but SimNIBS's `TDCSLEADFIELD` stores the **reference
electrode first** (`electrode_names = Cz, Fpz, Fp2, …, Fp1@35`) and
`simnibs.eeg.forward.prepare_forward` re-inserts the reference at its own index, so
`electrode_names` *is* the final `forward["ch_names"]`. Same 76 names, two orders.

### Fault 4 — `h5io` missing from the image (packaging)

`RuntimeError: For HDF5-based I/O to work, the module h5io is needed`. The last statement of the
pipeline, `_write_src_fwd_morph` → `mne.SourceMorph.save(...h5)`, goes through `h5io`, which
`pip install mne` does **not** pull in. It is a hard dependency of the `source` pipeline, and its
absence costs the entire leadfield before it is reported.

## 3. The fix

| File | Change |
|---|---|
| `tit/source/_simnibs_compat.py` (new) | `ensure_simnibs_eeg_compat()` — idempotent; binds `mne.morph` and `mne.forward._make_forward` onto their parents, re-attaches `_complete_source_space_info` onto `mne.source_space` from wherever the installed mne keeps it (the 1.5 layout is handled too), and restores `cortech.surface.Sphere.morph_mat` as a read-only alias for `_mapping_matrix`. Anything it cannot find raises a `RuntimeError` naming the mne version instead of an `AttributeError` ten minutes into a run. |
| `tit/source/_prepare_forward.py` (new) | The worker replacing SimNIBS's `prepare_eeg_forward mne` console script: same four positional inputs and `--fsaverage`, same call into `simnibs.eeg.forward.make_forward(..., write=True)`, same outputs written next to the leadfield — with the shim applied first. |
| `tit/source/forward.py` | (a) runs `[sys.executable, "-m", "tit.source._prepare_forward", …]` instead of `["prepare_eeg_forward", "mne", …]`; (b) new `_leadfield_channel_order()` + `_in_leadfield_order()`, and the Info is now built **after** the leadfield in the leadfield's own order (fault 3); (c) new `_check_forward_dependencies()` preflight for `h5io`, run before anything expensive (fault 4). |
| `container/blueprint/Dockerfile.ti-toolbox` | mne spec spelled `"mne>=1.5,<2"`, `h5io` added, both with the measured-versions rationale. `Dockerfile.ti-toolbox.layered` needs no change (it has no mne/h5io line — it builds on this image). |
| `tests/test_source.py` | +14 tests: `TestSimnibsEegCompat` (7), `TestPrepareForwardWorker` (2), `TestLeadfieldChannelOrder` (3), `TestForwardDependencyPreflight` (2). 23 → 37 tests in the file. |
| `tests/smoke/matrix.py` | `source` row: real `budget_s` for the `--smoke-full` leg, `expect_files` for the three MNE outputs, `_SOURCE_NET` constant, `notes`. **Not this lane's file** — see §7. |

### Why a child process at all, and why not the console script

`prepare_eeg_forward` is a shell wrapper around `python -E`, which ignores `PYTHONPATH` and every
other `PYTHON*` variable — so **no** environment-based shim can reach that interpreter. Calling
`make_forward` ourselves is what makes the shim possible at all. Keeping it in a *child* process
(rather than importing it into the runner) preserves the existing memory behaviour: the gain
matrix is 76 channels × 491524 sources × 3 orientations, ~0.9 GB in float64 plus mne's own
`_orig_sol` copy, and the child's RSS returns to the OS on exit. Measured runner RSS during the
FEM: 2.06 GB rising to 3.28 GB, back to 1.61 GB.

### Tests that fail without the fix (proved, not asserted)

- `TestPrepareForwardWorker` run against a temporarily reverted `forward.py` (console-script argv
  restored from a backup, then restored): **2 failed** — `assert "prepare_eeg_forward" not in cmd`,
  and the worker's own `_parse_args` rejecting the old argv (`error: the following arguments are
  required: trans`). With the fix: 2 passed.
- `TestSimnibsEegCompat` builds a fake mne that raises lazy_loader's own
  `AttributeError: No mne.source_space attribute _complete_source_space_info`
  (`test_without_the_shim_the_lookup_raises` asserts exactly that pre-fix behaviour) and then
  asserts each of the four bindings SimNIBS makes.
- `TestLeadfieldChannelOrder::test_info_is_built_in_the_leadfields_order` fixes the reproduction of
  job `c8ef9a4a2d454ff0` as a unit: CSV order `[Fp1, Fpz, Fp2, Cz]` vs leadfield order
  `[Cz, Fpz, Fp2, Fp1]`; without `_in_leadfield_order` the Info is built in the CSV order.
- `TestForwardDependencyPreflight::test_runs_before_any_leadfield_work` asserts the h5io check is
  the first thing `prepare_forward` does — the point of the fix is *when* it fails, not that it does.

## 4. Real runs

All against the shared dev container `ti-toolbox-fad740e5-tit-1` (`http://127.0.0.1:8765`),
Dataset 000, `sub-101`, net `EEG10-10_UI_Jurak_2007`, fsaverage5. See §5 for the numbers table.

| # | Command | Job | Wall | Outcome |
|---|---|---|---|---|
| R1 | `docker exec … simnibs_python -c "…utils_mne.make_source_spaces(subject surfaces)"` (repro) | — | 3.7 s | **reproduced** fault 1: `AttributeError: No mne.source_space attribute _complete_source_space_info` |
| R2 | same, with `ensure_simnibs_eeg_compat()` (mne shims only) | — | ~6 s | source spaces built (`nuse=[245762, 245762]`, `tri_area` populated), then **found fault 2**: `'Sphere' object has no attribute 'morph_mat'` |
| R3 | same, with the cortech alias added, through `utils_mne.setup_source_space(m2m, None, 5)` | — | **6.2 s** | src + `SourceMorph` OK: morph `(20484, 491524)`, `101 -> fsaverage5`, `vertices_to=[10242, 10242]` |
| R4 | `TIT_SMOKE_… pytest tests/smoke -m smoke --smoke-kinds source --smoke-full --smoke-keep` | `c8ef9a4a2d454ff0` | **636.1 s** (job 624.9 s) | **FAILED** — shims held, FEM done, then **fault 3**: `AssertionError: Inconsistencies between channels in Info and leadfield` |
| R5 | `docker exec … prepare_forward('101', …, overwrite=False)` (reuses R4's cached leadfield) | — | ~90 s | channel order fixed; **found fault 4**: `RuntimeError: … the module h5io is needed` in `SourceMorph.save` |
| R6 | `simnibs_python -m pip install --no-deps --no-cache-dir h5io` → 0.2.5, then R5 again | — | **22.9 s** | **all three outputs written**: `-fwd.fif`, `-src.fif`, `-morph.h5` |
| R7 | **run of record** — `TIT_SMOKE_SERVER_URL=http://127.0.0.1:8765 TIT_SMOKE_TOKEN=devtoken TIT_SMOKE_PROJECT_HOST=/Users/idohaber/datasets/000 python3 -m pytest tests/smoke -m smoke --smoke-kinds source --smoke-full --smoke-keep -p no:cacheprovider` (from an empty `forward/`) | `300d9dd6f6e94ac5` | **637.5 s** (job 611.1 s, 01:25:35 → 01:35:49 UTC) | **1 passed** — `completed`, 3 artifacts, banner at 4.1 s |

R7 is the proof the brief asked for: the row asserts `completed`, the job succeeded inside its
budget, all three artifacts exist on the host filesystem **and** are served by the server's own
`/api/files/artifact`, and the claimed output directory is non-empty. Its cleanup manifest
(`tests/smoke/artifacts/manifest-20260904T013551Z-fx4b.json`) records `pre_existed: false` for
every claim — nothing pre-existing was touched — and `derivatives/SimNIBS/sub-101/forward/`
(1.3 GB) was removed afterwards, leaving the dataset as it was found. `m2m_101`, `m2m_ernie` and
`m2m_MNI152` were never written.

### The outputs, read back (R6 and R7 independently, byte-identical sizes)

| File | Size | Read back with mne |
|---|---|---|
| `sub-101_net-EEG10-10_UI_Jurak_2007-fwd.fif` | 473 839 911 B | `nchan=76`, `nsource=491524`, gain `(76, 1474572)`, all finite, `max|G|=863.1`, `mean|G|=30.65` |
| `sub-101_net-EEG10-10_UI_Jurak_2007-src.fif` | 25 559 842 B | 2 surface source spaces, `nuse=[245762, 245762]` |
| `sub-101_net-EEG10-10_UI_Jurak_2007-morph.h5` | 8 228 288 B | `SourceMorph` `(20484, 491524)`, `101 -> fsaverage5`, `vertices_to=[10242, 10242]` |
| `101_leadfield_EEG10-10_UI_Jurak_2007.hdf5` (input) | 883 644 542 B | `interpolation='middle gm'`, `tissues=[]`, shape `(75, 491524, 3)`, `reference_electrode='Cz'` |

Two checks that are assertions about correctness, not existence:

* **Channel order** — `fwd['sol']['row_names'][0] == 'Cz'` and `[35] == 'Fp1'`, i.e. the leadfield's
  order, not the net CSV's (`Fp1` first, `Cz` at 35). This is fault 3, verified from the output.
* **Average reference** — `max|mean over channels of G| = 3.56e-06` against `max|G| = 863.1`, i.e.
  the columns sum to zero to ~9 significant figures, so `apply_average_proj` did its job.

## 5. Numbers

| Measurement | Value |
|---|---|
| Faults found on the path from config to forward solution | **4** (2 in SimNIBS 4.6, 1 in `tit/source/forward.py`, 1 packaging) |
| Faults an mne pin would have fixed | **1 of 4** |
| Run of record (R7) | `1 passed, 68 deselected in 637.50 s`; job `300d9dd6f6e94ac5` succeeded in **611.1 s**, **3 artifacts** |
| Point-electrode FEM leadfield | 75 solves, ~6.0 s each steady state, ~10 min wall for this net |
| MNE assembly alone (cached leadfield) | **22.9 s** |
| Source space + fsaverage morph alone | **6.2 s** |
| Runner RSS during the run | 2.06 GB → 3.28 GB peak → 1.61 GB |
| Forward gain matrix | 76 channels × 491 524 sources × 3 orientations = `(76, 1474572)`, 452 MB on disk |
| fsaverage5 morph | `(20484, 491524)`, 10 242 vertices per hemisphere |
| Average-reference residual | `3.56e-06` vs `max|G| = 863.1` |
| mne / numpy / h5io in the container | 1.12.1 / 1.26.4 / **0.2.5 (installed by this lane)** |
| Container restarts | **0** |
| Heavy jobs run | **2** (R4 failed on fault 3, R7 green); never concurrent with another job — the harness's `_wait_no_heavy_job` cleared first, and `GET /api/jobs` was checked before each |
| Dataset paths left behind | **0** (1.3 GB `forward/` removed; manifest shows `pre_existed: false` throughout) |
| New tests in `tests/test_source.py` | **+14** (23 → 37) |

## 6. Container restarts and container state

**Restarts: 0.** Every code change is under `tit/source/**`, which runner subprocesses import from
the bind-mounted worktree, so each was live immediately (program §4). No `tit/server/**`,
`tit/jobs/**` or `tit/catalog.py` change was needed.

**One un-reverted change to the shared container**, deliberately: `simnibs_python -m pip install
--no-deps --no-cache-dir h5io` → **h5io 0.2.5**. `--no-deps` was used so nothing else could move;
its declared requirements (`numpy`, `h5py`) were already present and `numpy` is still 1.26.4 after
the install. It is **not** reverted, because reverting it would put the `source` pipeline back to
failing on this container for every other lane and for the critic pass. The permanent fix is the
`h5io` line now in `container/blueprint/Dockerfile.ti-toolbox`; until the image is rebuilt, this
container's green `source` row depends on that manual install. Flagged in §7.

## 7. Requests to other lanes

1. **Orchestrator / whoever rebuilds the image.** `container/blueprint/Dockerfile.ti-toolbox` now
   installs `h5io` and spells the mne range `>=1.5,<2`. Until that image is rebuilt, the shared
   container's `source` pipeline works only because of the manual `pip install h5io` recorded in
   §6. A rebuilt image with the current Dockerfile needs no manual step; a *fresh* container from
   the **old** image will fail the `source` row again — with a readable one-line refusal now
   (`_check_forward_dependencies`), before the 11-minute FEM, rather than a traceback after it.
2. **HX (owns `tests/smoke/**`).** This lane edited the `source` row of `tests/smoke/matrix.py`
   (the brief asked for a `--smoke-full`/completed path). Three follow-ups it did not take:
   - `tests/smoke/payloads/source.json` sets `forward.overwrite: true`, so every replay recomputes
     the ~11-minute FEM even when a cached leadfield is sitting in `forward/`. The UI's own default
     is `false`; re-recording it that way would make a repeat `--smoke-full` source run ~25 s
     instead of ~11 min.
   - The `source` row's output directory is fixed (`derivatives/SimNIBS/sub-<id>/forward/`, no
     run-name field), so under P6 it is a **once-per-project** row: the second `--smoke-full` run
     skips with "recorded payload targets existing output" unless the directory is removed first.
     Worth stating in the row's `notes` or the runbook rather than being rediscovered.
   - Because a payload exists for this row, `expect_files` is never evaluated (`test_kinds.py`
     sets `expected = []` for payload sources). The three files are still checked, via the job's
     reported artifacts; the `expect_files` entries are there for a builtin-config run.
3. **FX2 (owns `tit/server/**`, `tit/jobs/**`).** Nothing blocking from here. For the record, the
   `source` job reports its three MNE outputs as artifacts correctly (`emit_artifact` in
   `tit/source/__main__.py::_run_forward`), so this kind is not part of FX3's "zero artifacts"
   finding.

## 8. Gates

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3348 passed, 18 skipped, 21 deselected in 36.57 s**, exit 0 (smoke deselected by default) |
| `pytest tests/test_source.py -q` | **37 passed in 0.17 s** (was 23 before this lane) |
| `pytest tests/smoke/test_harness_selftest.py -q` | **68 passed in 0.07 s** (the matrix edit is self-checked) |
| Level A run of record | **1 passed, 68 deselected in 637.50 s** (R7) |

One transient red seen mid-lane and gone by the end: `tests/test_server_skeleton.py::test_catalog_subjects`
failed in a full-suite run at 01:04 UTC but **passed in isolation seconds later**, and passed in the
final full run. Nothing in this lane touches the catalog; recorded here as an observation, and
plausibly FX5's in-flight edits to `tit/catalog.py` in the shared worktree rather than a real
ordering bug.

No desktop gate was run: this lane changed no file under `desktop/`, and `npm run build` there
races other lanes' `desktop/out` (the documented risk in `desktop/README.md`).

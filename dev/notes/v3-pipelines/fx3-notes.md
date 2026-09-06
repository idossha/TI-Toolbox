# Lane FX3 — runner artifacts + catalog — working notes

Program: `dev/notes/v3-pipelines-program.md` §7, row **FX3**. Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Nothing committed,
staged, stashed or pushed.

Shared dev container `ti-toolbox-fad740e5-tit-1`, `http://127.0.0.1:8765`, project
`/Users/idohaber/datasets/000` at `/mnt/000`, this worktree at `/ti-toolbox`.

Findings this lane closes (evidence: `dev/notes/v3-pipelines/2026-09-03-smoke.md`, open issues 1, 3, 4):

1. `stats`, `blender` and `tools` jobs reported `artifacts: []` although they wrote files
   (stats: 9; job `60727ba738144204`).
2. An analyzer run with a custom `output_dir` was invisible to the catalog
   (`tit/catalog.py` scanned only `Analyses/{Mesh,Voxel}`).
3. nilearn's default `min_cutoff = 0.3` V/m is above every real TI field, so a default run
   died inside matplotlib with `minvalue must be less than or equal to maxvalue`
   (job `287e3e0c2eb94134`).

---

## 1. Runner artifacts — three runners onto the analyzer's contract

The contract is `tit/jobs/events.py`: `emit_artifact(path, kind, label)` per file,
`emit_result(outputs)` last, and `emit_new_artifacts(root, since)` for a runner whose output
directory is decided deep inside the pipeline. `tit/analyzer/__main__.py` already used the last
one; the three silent runners now do the same thing for the same reason.

| Runner | File | What it emits now | Why that root |
|---|---|---|---|
| `stats` | `tit/stats/__main__.py` | `emit_new_artifacts(result.output_dir, started)` + `output_dir` in the result outputs | `run_group_comparison` / `run_correlation` return a `GroupComparisonResult` / `CorrelationResult` that already carries `output_dir` — the directory `_resolve_output_dir` chose. Restating the 9 filenames in the runner would duplicate a list `tit/stats/permutation.py` owns. |
| `blender` | `tit/blender/__main__.py` | each handler returns the directory it wrote into; `main()` lists it | montage resolves its own directory when `output_dir` is `None` (`MontageResult.final_blend`'s parent is the truth); `run_vectors`/`run_regions` have `_resolve_paths` fill `config.output_dir` in on the way through. |
| `tools` | `tit/tools/electrode_overlay.py`, `tit/tools/nifti_to_mesh.py` | `emit_artifact` for the overlay NIfTI and its `.lut` (and for the mesh `nifti_to_mesh` writes), then `emit_result` | a `tools` job is argv, not a spec.json (`tit/jobs/kinds.py`), so there is no shared wrapper that could report for it — each tool script reports its own outputs. `electrode_overlay` and `nifti_to_mesh` are the only two modules under `tit/tools/` with a `__main__` guard, i.e. the only two a `tools` job can run today (`tit.jobs.kinds` allowlists `tit.tools.*`); fixing one alone would leave the same "succeeded, artifacts: []" hole open for the other. |

Bookkeeping never fails a finished run: each site guards a non-string / empty output dir and
swallows its own exceptions, the same way `tit/analyzer/__main__._emit_analysis_artifacts`
already did.

**Analyzer, output-dir only** (`tit/analyzer/__main__.py`): `analysis_artifact_root()` now
follows `config.output_dir` when it is set. Listing `Analyses/<Space>/` regardless was the same
bug in a second place — a run with a custom output directory reported *zero* artifacts although
it had written five files. `_warn_if_undiscoverable()` prints one line when the chosen directory
is outside the simulation (see §2 for why that is a note and not a refusal).

A **group** analyzer run reported nothing at all — `main()`'s group branch never called the
artifact helper — although `GroupResult` names the two files the group job itself writes
(`group_summary.csv`, `group_comparison.pdf`; each subject's own analysis belongs to that
subject's directory, not to this job). `_emit_group_artifacts()` reports those two by name rather
than walking, and `_run_group()` now returns its result so it can. Proven by run 7.

## 2. Catalog discovery — decision and why

The finding offered two ways out. **The catalog discovers what the runner wrote.** Reasons, from
the code:

- `output_dir` is a documented argument of the public scripting API
  (`Analyzer(subject_id, simulation, space, output_dir=...)`, `tit-scripting`), and
  `Analyzer._resolve_output_dir` honours it verbatim. Refusing it in the runner would break
  scripts and notebooks that analyse into a scratch directory, and two existing tests
  (`tests/test_analyzer_full.py::test_uses_explicit_output_dir`,
  `tests/test_analyzer_group.py::test_uses_explicit_output_dir`) assert exactly that freedom.
- The analyzer already writes a self-describing pair — `analysis.json` + `results.csv` — into
  whichever directory it used (`tit/analyzer/visualizer.py`). Discovery is therefore a pure read
  of what the runner wrote; no new contract, no new metadata file.
- Cost is not a reason to refuse: a real simulation directory in Dataset 000 holds 68–105
  entries (`find … | wc -l` over every `sub-*/Simulations/*/`), and the walk does not descend
  into a directory it has already identified as an analysis.

`tit/catalog.py`'s `_find_analysis_dirs(sim_dir)` walks the simulation for directories holding
both files. Naming is chosen so nothing existing moves:

- directly under `Analyses/Mesh` or `Analyses/Voxel` → the bare directory name (**unchanged**;
  `GET /api/catalog/analyses/{name}/summary` and every existing client keep working);
- anywhere else under the simulation → the path relative to the simulation directory, with the
  separators flattened to `__` (`Analyses__Custom__smoke-1`, `my_scratch_analysis`) — see §2b for
  why a `/` in a name is unreachable rather than merely ugly;
- standard entries first, in today's Mesh-then-Voxel-then-name order, then the rest by name, so
  adding a custom run never reorders a list a client already knows.

An output directory *outside* the simulation stays undiscoverable — the catalog is keyed by
subject and simulation and there is nothing left to key on — so the runner says so in one line
rather than failing (§1).

### 2b. A name has to survive being a URL path segment (measured, then fixed)

The first cut named a custom run by its relative path verbatim (`Analyses/Custom/smoke-1`). Probed
against the live container, such a name is listed but its summary can never be fetched:

```
GET /api/catalog/analyses/Mesh_smoke/summary?subject=ernie&simulation=L_Insula
  -> 404 {"detail":"Unknown analysis: ernie/L_Insula/Mesh_smoke"}   (the handler answered)
GET /api/catalog/analyses/Analyses%2FCustom%2Ffx3/summary?...
  -> 404 {"detail":"Not found"}                                      (no route matched)
```

The client percent-encodes the path parameter and the ASGI server decodes `%2F` back to `/` before
routing, so `/api/catalog/analyses/{name}/summary` never matches. The fix belongs in the name, not
the route (`tit/catalog.py` is this lane's file; the route is FX2's): a non-standard analysis is
named by its relative path with each separator flattened to `__` (`Analyses__Custom__smoke-1`), and
`analysis_summary()` additionally accepts the run's own slashed relative path, so a script holding
`output_dir` needs no translation. Standard `Analyses/{Mesh,Voxel}` names are untouched.

## 3. nilearn — a data-driven default and a preflight that names the range

`min_cutoff` is now `float | None` with `None` (the default) meaning "take it from the data".
The pair used is `tit.reporting.generators.simulation._compute_field_thresholds`'s **p95 / p99.9**
— the only display range in this codebase already derived from real TI data ("the top 5 % of the
distribution, minus the top 0.1 % of outliers").

`tit/plotting/nilearn/cutoffs.py` (new, pure numpy, no nibabel/nilearn/`tit.stats` import) holds
`resolve_cutoffs()`, `blank_figure_warning()` and `field_summary()`. The runner resolves **both**
cutoffs there, before a figure is drawn — the renderers' own `max_cutoff=None → 99.9th percentile`
rule is applied at the same point, so the `min < max` check sees the real pair rather than `None`.
An impossible range raises a `ValueError` that names the field (verbatim from job
`4db45873f5cb4516`, run 5):

```
display range is empty (min_cutoff 0.3000 V/m, max_cutoff 0.1066 V/m): the averaged field
spans 0.0000-0.1385 V/m over 1163381 non-zero voxels (median 0.0226, p95 0.0616, p99.9 0.1066).
Lower min_cutoff below 0.1066 V/m, set use_percentiles=true to give it as a percentile, or
leave min_cutoff unset for the data-driven default (p95 = 0.0616 V/m).
```

### 3b. The silent half of the same bug

Refusing an *empty* range is not the whole failure. A caller can put the floor above every voxel
and still keep a ceiling above that — which is exactly what the desktop panel sends today
(`min_cutoff` 0.3 with `max_cutoff` 5, `tests/smoke/payloads/nilearn.json`): the job succeeds and
writes PDFs with nothing on them. `blank_figure_warning()` turns that into one WARNING line in the
job log, measured on the replayed UI payload (job `a273230c00664d08`, run 8):

```
min_cutoff 0.3000 V/m is at or above the field's peak 0.1894 V/m, so the figures will be blank:
the averaged field spans 0.0000-0.1894 V/m over 1059014 non-zero voxels (median 0.0308,
p95 0.0799, p99.9 0.1332). Leave min_cutoff unset for the data-driven default (p95 = 0.0799 V/m).
```

A warning and not a refusal, deliberately: refusing it would turn the smoke row that replays the
UI's own recorded body red until the panel's default changes (request 2 below), and this lane does
not own that file. The log now carries the evidence for that request.

Its own module rather than a helper in `__main__.py` for one reason: `tit.plotting.nilearn.__main__`
imports `tit.stats.nifti`, which pulls `tit.stats.engine` and real scipy, so a unit test of the
arithmetic could not import it under the host suite's mocks.

Every run now logs the field range and the display range it resolved, so the numbers are in the
job log whether or not the run succeeds.

---

## Files changed

| File | Change |
|---|---|
| `tit/stats/__main__.py` | `_emit_output_artifacts`; `_run_group_comparison`/`_run_correlation` take `started` and report `output_dir`; the lock request keeps `mode` (it is popped before the config is built, and `locks.keys_for` reads it) |
| `tit/blender/__main__.py` | handlers return their output directory; `main()` lists it and reports it |
| `tit/tools/electrode_overlay.py` | `_report_job_outputs()`; `main()` calls it |
| `tit/tools/nifti_to_mesh.py` | `_report_job_outputs()`; `main()` calls it (the second runnable `tools` module) |
| `tit/analyzer/__main__.py` | `analysis_artifact_root()` follows `output_dir`; `_warn_if_undiscoverable()`; `_emit_group_artifacts()` reports a group run's summary CSV + comparison PDF (`_run_group` now returns its `GroupResult`) |
| `tit/catalog.py` | `_find_analysis_dirs()`; `analyses()` / `analysis_summary()` use it; non-standard names flattened to one URL path segment (§2b) |
| `tit/plotting/nilearn/config.py` | `min_cutoff: float \| None = None` |
| `tit/plotting/nilearn/cutoffs.py` | **new** — `resolve_cutoffs`, `blank_figure_warning`, `field_summary`, the two default percentiles |
| `tit/plotting/nilearn/__main__.py` | resolves both cutoffs up front; logs the field range, the display range and the blank-figure warning; reports the cutoffs in the result |
| `contracts/schema.json` | regenerated (`simnibs_python dev/build_schema.py` in the container) — `NilearnConfig.min_cutoff` is now nullable and its docstring is the schema's description; `--check` is clean |
| `tests/test_runner_artifacts.py` | **new** — blender, tools (`electrode_overlay` + `nifti_to_mesh`) and analyzer (single `output_dir` + group) cases (13) |
| `tests/test_stats_main.py` | + the stats artifact cases and the lock-mode case (5) — this file already performs the real-scipy restore `tit.stats.__main__` needs |
| `tests/test_nilearn_cutoffs.py` | **new** — 18 cases over `resolve_cutoffs` / `blank_figure_warning` / `field_summary` |
| `tests/test_catalog_analyses_discovery.py` | **new** — 13 cases over the walk, naming (incl. "every listed name is one URL path segment"), ordering and summary lookup |

Every one of these ships a test that fails without it; the four added after the first cut were
each run red-then-green in isolation (`nifti_to_mesh` artifacts, the stats lock mode, the group
analyzer artifacts, the URL-safe names).

## Gates

| Gate | Result |
|---|---|
| host `python3 -m pytest -q` | **3354 passed, 18 skipped, 21 deselected in 35.5 s** (3344 before this lane's 10 new cases) |
| `simnibs_python dev/build_schema.py --check` (in the container) | up to date (62 `$defs`) |
| desktop `typecheck/lint/vitest/build` | **not run, deliberately**: this lane changed no file under `desktop/`, and `npm run build` rewrites `desktop/out/`, which other lanes' `--project real` Playwright runs are reading right now. |

## Real runs

All against `ti-toolbox-fad740e5-tit-1` (`http://127.0.0.1:8765`) on Dataset 000. Level A rows:

```bash
TIT_SMOKE_SERVER_URL=http://127.0.0.1:8765 TIT_SMOKE_TOKEN=devtoken \
TIT_SMOKE_PROJECT_HOST=/Users/idohaber/datasets/000 TIT_SMOKE_RUN_ID=fx3a \
python3 -m pytest tests/smoke -m smoke --smoke-kinds stats_group,tools_electrode_overlay,blender \
  -p no:cacheprovider -q
```

(`TIT_SMOKE_PROJECT_HOST` because a second stack carries the `tit.stack` label on this machine,
so `dev/smoke.sh` refuses to guess — the case S1 documented.) The three runs the finding names
are rows 1–3; rows 4–8 are the ones the matrix has no row for.

| # | Run | Job | Outcome | Wall | Numbers |
|---|---|---|---|---|---|
| 1 | Level A `stats_group` (payload `stats.json`, 101+ernie+MNI152) | `99b52baa70ef48ff` | succeeded, **8 artifacts** (was 0) | 4.0 s job / 363.8 s row | `pvalues_map.nii.gz`, `difference_map.nii.gz`, `significant_voxels_mask.nii.gz`, `average_responders.nii.gz`, `average_non_responders.nii.gz`, `analysis_summary.txt`, the run log, `permutation_null_distribution.pdf`. Row wall is P7: it waited on another lane's `source` job. |
| 2 | Level A `blender` (montage, ernie `docs_example`) | `ceaef79222e14512` | succeeded, **5 artifacts** (was 0) | 16.1 s job / 55.8 s row | `..._montage_publication.blend`, `ernie_electrodes_GSN-HydroCel-185.blend`, `.glb`, `gm.stl`, `scalp.stl` |
| 3 | Level A `tools_electrode_overlay` (ernie `L_Insula`) | `70da187fc3c24d4b` | succeeded, **2 artifacts** (was 0) | 0.0 s job / 1.0 s row | `overlay.nii` (nifti), `overlay.lut` (txt) |
| 4 | `nilearn` **at the default** (`min_cutoff` unset), ernie `L_Insula`, direct submit | `3d4a00f573974643` | succeeded, 4 artifacts | 18.1 s | field `0.0000–0.1385 V/m` over 1 163 381 non-zero voxels (median 0.0226, p95 **0.0616**, p99.9 **0.1066**); display range `0.0616–0.1066 V/m (data-driven default)` — the exact configuration that used to die as `287e3e0c2eb94134` |
| 5 | `nilearn` at `min_cutoff = 0.3` (the old default), `max_cutoff` unset | `4db45873f5cb4516` | **failed readably**, 0 artifacts | 6.0 s | `display range is empty (min_cutoff 0.3000 V/m, max_cutoff 0.1066 V/m): the averaged field spans 0.0000-0.1385 V/m … Lower min_cutoff below 0.1066 V/m, set use_percentiles=true …` — no traceback, and it fails *before* any figure is drawn (6.0 s vs the 12 s the old crash took) |
| 6 | `analyzer` with `output_dir = …/Simulations/L_Insula/Analyses/Custom/fx3-fx3b-custom` | `6bdcc66ae13f4097` | succeeded, **4 artifacts** (was 0 for a custom dir) | 9.0 s | `analysis.json`, `results.csv`, `roi_overlay.nii.gz`, `histogram_histogram.pdf`; `GET /api/catalog/analyses?subject=ernie&simulation=L_Insula` → `["Analyses__Custom__fx3-fx3b-custom"]`; `GET /api/catalog/analyses/Analyses__Custom__fx3-fx3b-custom/summary` → **200** with 19 metric rows |
| 7 | `analyzer` **group** run (101+ernie, `L_Insula`, voxel, r 7.3 mm) | `1afda04255454254` | succeeded, **2 artifacts** (was 0) | 9.0 s | `group_summary.csv` (csv, "group summary"), `group_comparison.pdf` (pdf, "group comparison") |
| 8 | Level A `nilearn`, `analyzer_mesh`, `analyzer_voxel` (run id `fx3c`) | `a273230c00664d08`, `63c538ee2bb54754`, `32a35e8ed58b4a01` | 3 passed in 33.6 s; 4 / 5 / 4 artifacts | 16.5 / 9.8 / 7.1 s | the `nilearn` row replays the UI's own body (`min_cutoff` 0.3, `max_cutoff` 5): it still succeeds, and now says why its figures are empty — `min_cutoff 0.3000 V/m is at or above the field's peak 0.1894 V/m, so the figures will be blank …` |
| 9 | Level A `stats_group` again (run id `fx3d`), after the lock-`mode` one-liner landed in the same runner | `5f5840ef114a48f8` | succeeded, 8 artifacts | 2.0 s job / 6.1 s row | re-run so the proven binary is the current code, and with an idle queue it shows the row's real cost: 6.1 s, not the 363.8 s of row 1 (which was all P7 wait) |

Everything these runs created was deleted afterwards (P6): the Level A rows clean themselves up
(`tests/smoke/artifacts/manifest-*-fx3a.json`, `-fx3c`, every claim `removed: true`), and rows 4–7
were removed by hand — `derivatives/ti-toolbox/nilearn_visuals/fx3-fx3b-nilearn-default` (and the
`nilearn_visuals` directory the run created), `…/L_Insula/Analyses/Custom/`,
`derivatives/ti-toolbox/fx3-group-smoke/`, and the two per-subject
`Analyses/Voxel/sphere_x-42.00_y-6.00_z2.00_r7.3_subject` directories the group run wrote (plus
`sub-101/…/Analyses/Voxel`, created by that run — birth time 20:43:08, checked before removing).
`m2m_101`, `m2m_ernie` and `m2m_MNI152` were never written. Verified afterwards: `sub-101`'s
`Analyses/` holds only its pre-existing `Mesh/`, `sub-ernie`'s only its pre-existing
`Voxel/cortical_1035_aparc_DKTatlas_aseg`.

**Container restarts: 1.** `docker restart ti-toolbox-fad740e5-tit-1` at 20:38:03 CDT with
`GET /api/jobs` showing nothing running or queued, healthy again 2 s later (`{"status":"ok",
"uptime_s":0.584}`). Only `tit/catalog.py` needed it; every other file this lane touched is a
runner package the subprocesses import fresh.

## Requests to other lanes

1. **FX2 (`tit/jobs/events.py`) — `_ARTIFACT_KIND_BY_EXT` has no 3D formats.** The blender row's
   five artifacts are all reported `kind: "txt"` (`.blend`, `.glb`, two `.stl` — job
   `ceaef79222e14512`), because the shared extension map only knows
   `csv/json/pdf/png/txt/html/msh/gii/nii/gz/log`. Please add `".stl": "mesh"`, `".glb": "mesh"`
   and `".blend": "mesh"` (or whatever the schema's kind vocabulary should call a scene file).
   Harmless today — `ui/Jobs.tsx`'s `ArtifactList` ignores `kind` — but it is wrong data in the
   events contract, and the first viewer that keys on `kind` will act on it.
2. **Whoever owns `desktop/src/renderer/pages/panels/nilearn-visuals/**` — the panel's default
   `min_cutoff` is still 0.3 V/m.** `index.tsx:52` is `useState<number | undefined>(0.3)` and
   `:85` sends `minCutoff ?? 0`; `config.ts:26` maps it to `min_cutoff`. With the runner's
   data-driven default the panel should leave the field empty and send `null` (or omit the key),
   which is now valid — `NilearnConfig.min_cutoff` is `float | None` in `contracts/schema.json`.
   Evidence that the current default is wrong on real data: job `4db45873f5cb4516` (refused
   readably at 0.3) and job `a273230c00664d08` (0.3 with a ceiling of 5 → blank figures, now
   warned about in the log). `desktop/src/renderer/api/schema.d.ts:4946` still types
   `min_cutoff: number` and wants regenerating from the live OpenAPI.
3. **HX (`tests/smoke/**`) — the `nilearn` row can drop its workaround.** `matrix.py:835` sets
   `use_percentiles: True, min_cutoff: 95.0` with a comment explaining that the 0.3 default was
   above the data; leaving both cutoffs unset now exercises the data-driven default instead, which
   is what the row is really for. And `payloads/nilearn.json` carries the UI's `min_cutoff` 0.3 /
   `max_cutoff` 5, so the replayed row proves the blank-figure warning rather than a good default —
   worth re-recording once request 2 lands.
4. **FX2 (`tit/server/routes/catalog_v1.py`) — for information, no action needed.**
   `/api/catalog/analyses/{name}/summary` cannot take a name containing `/` even
   percent-encoded (measured, §2b). This lane worked around it in the *name*; if you ever want
   nested names to be addressable, the path parameter needs to be `{name:path}`.

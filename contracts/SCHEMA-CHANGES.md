# Schema changes

Dated log of changes to the config dataclasses registered in
`tit.config_io.CONFIG_CLASS_REGISTRY`, and the resulting regeneration of
`contracts/schema.json` / `contracts/openapi.v1.json` /
`desktop/src/renderer/api/schema.d.ts`. Append one entry per change; do not
edit past entries.

## 2026-08-27 — fix:backend-catalog — `atlas_regions`/runs/percentile land; one new path to record

No dataclass changes, so `contracts/schema.json` is untouched by this entry.
Everything below except item 4 required **no** `openapi.v1.yaml` edit — the
fix:contract lane had already declared the target shapes; this lane just
made `tit/catalog.py`/`tit/viewspec.py` conform to them.

1. **`tit.catalog.atlas_regions`'s cortical branch** now returns the real
   FreeSurfer `.annot` label index as `id` (an integer) plus the region's own
   `hemi`, instead of a display string like `"lh.bankssts"` with no `hemi` —
   closing the gap the fix:contract lane's `Region` schema change (item 4,
   entry above) flagged as still open. Verified against a real atlas on
   `sub-ernie` in the `tit-v3-spike` container (Dataset 000):
   `GET /api/catalog/atlases/regions?subject=ernie&atlas=DK40&hemi=lh` now
   returns 35 regions, all `id: int`, all `hemi: "lh"` (e.g.
   `{"id": 1, "name": "bankssts", "hemi": "lh"}`) — this is exactly the
   integer `FlexConfig.AtlasROI.label` needs (see
   `tit.opt.roi_spec.resolve_cortical_region_index_map`, which resolves the
   same annotation the same way). The subcortical branch now also always
   sets `hemi: null` (was previously missing the key entirely) and drops any
   region whose label cannot be parsed as an integer instead of returning a
   non-conforming string id.
2. **`FlexRun`/`ExRun` `artifacts`** are now populated by
   `tit.catalog._dir_artifacts` (a bounded-depth walk of the run directory
   for `.png`/`.csv`/`.json`, classified `image`/`csv`/`json`, with
   `flex_meta.json`/`run_config.json` reclassified `manifest`) — closing the
   fix:contract lane's item 6 follow-up. No schema change: `artifacts:
   [Artifact]` was already declared required on both.
3. **`ViewLayer.percentile` is now resolved.** Heat-colormap layers
   (`TI_max`, high-frequency `magnE`) built by `tit.viewspec.build_view` now
   carry `percentile: {"lo": 95.0, "hi": 99.9}` (the Qt tab's own default),
   resolved to concrete `cal_min`/`cal_max` by
   `tit.viewspec.resolve_percentiles` — `numpy.percentile` over the NIfTI's
   non-zero voxels, run on a small thread pool. Called once by `build_view`
   (`GET /api/view/{kind}`) and again by `POST /api/viewers/freeview` on
   whatever `ViewSpec` the client submits. Verified on a real `TI_max`
   volume on `sub-ernie`: three heat layers resolved to real absolute
   `cal_min`/`cal_max` (e.g. `0.603`/`8.587`) in ~0.6s total, well inside the
   ~2s budget; `to_freeview_args` emits `heatscale=<cal_min>,<cal_max>` with
   those numbers. A layer whose file can't be read or is all-zero simply
   keeps `cal_min`/`cal_max` as `None` (no crash). No schema change: `Region`
   and `ViewLayer.percentile` were already declared by the fix:contract
   lane's items 4/5.
4. **New path, not yet in `openapi.v1.yaml` (this lane may not edit that
   file): `GET /api/catalog/electrode-overlays?subject=&simulation=`** →
   `[{"mode": "TI"|"mTI", "path": string, "exists": boolean}]`, 404 for an
   unknown subject/simulation. Added per the fix:backend-catalog task's item
   (g) as the listing half of `pages/viewer/PARITY.md` gap #1 (electrode
   overlay creation has no v1 job/catalog surface); the *building* half is
   documented as a `tools` job in `tit/server/routes/viewers.py`'s module
   docstring (`{"kind": "tools", "config": {"module":
   "tit.tools.electrode_overlay", "args": [...]}}`, already supported by
   `tit/jobs/kinds.py`'s `tools` branch — no B1 change needed). Verified on
   `sub-ernie`: returns both modes with `exists: false` (no overlay written
   yet in Dataset 000). **Orchestrator/contract-lane action**: add this path
   + a small response schema (or reuse `ElectrodeOverlay: {mode: string,
   path: string, exists: boolean}`) to `openapi.v1.yaml` when it next opens
   for edits.

Regenerated: nothing (no dataclass/contract-yaml change). Verified
`python3 -m pytest -q` (from repo root): 2807 passed, 17 skipped, 2 failed —
both failures are in `tests/test_plan_routes.py`
(`test_validate_no_schema_kind_is_trivially_ok`,
`test_plan_no_schema_kind_returns_empty_with_warning`), pre-existing and
unrelated to this lane (`NiftiAverageConfig`/`NilearnConfig` dataclasses not
yet landed by B4, tracked in this file's item 9 above); every test this lane
touches (`tests/test_catalog_v1.py`, `tests/test_viewspec.py`,
`tests/test_catalog.py`, `tests/test_atlas*.py`) is green.

## 2026-08-27 — B4 — `QSIPrepSettings` / `QSIReconSettings`

Added two new dataclasses to `tit/pre/config.py`: `QSIPrepSettings` and
`QSIReconSettings` — flat, subject-independent settings (no `subject_id`,
resource knobs `cpus`/`memory_gb`/`omp_threads` at the top level, not nested
under a `resources` object). Registered in `CONFIG_CLASS_REGISTRY` as
`"QSIPrepSettings"` / `"QSIReconSettings"`.

`PreprocessConfig.qsiprep_config` / `.qsi_recon_config` now type as
`QSIPrepSettings | None` / `QSIReconSettings | None` instead of the existing
`tit.pre.qsi.config.QSIPrepConfig` / `QSIReconConfig` (which keep their
`subject_id` + nested `resources: ResourceConfig` shape and stay registered
under their own names — they are still used internally by
`tit.pre.qsi.qsiprep.run_qsiprep` / `run_qsirecon` to build the Docker
invocation once a subject is known, and referenced standalone in
`PipelineConfig`'s `oneOf`).

**Why:** `tit.pre.structural.run_pipeline` reads these two fields as flat
dicts (`qsiprep_cfg.get("cpus")`, ...). A `PreprocessConfig` serialized with
the old nested `QSIPrepConfig`/`QSIReconConfig` types wrote
`qsiprep_config.resources.cpus`, which the flat `.get("cpus")` read never
found — the config a form would validate against did not match what the
runner actually consumed. `tit/pre/__main__.py` now builds a
`PreprocessConfig` via `deserialize_config` (falling back to the old flat
dict layout for one release) and converts `qsiprep_config` /
`qsi_recon_config` to plain dicts via `dataclasses.asdict` before calling
`run_pipeline`, so the two shapes are identical end to end.

No `openapi.v1.yaml` edit was needed: `dev/build_contract.py` copies every
`$defs` entry a marked schema transitively references, so `QSIPrepSettings`
and `QSIReconSettings` were picked up automatically as new
`components.schemas` entries once `PreprocessConfig`'s generated schema
started `$ref`-ing them.

Regenerated: `contracts/schema.json` (`docker exec tit-v3-spike simnibs_python
dev/build_schema.py`, 54 `$defs`), `contracts/openapi.v1.json`
(`python3 dev/build_contract.py`), `desktop/src/renderer/api/schema.d.ts`
(`npm run gen:api`). `tests/test_config_schema.py`'s `PreprocessConfig`
sample instance was updated to build `qsiprep_config=QSIPrepSettings(...)`
instead of `QSIPrepConfig(subject_id=...)` (that file is otherwise owned by
F1b — flagged in the B4 verification report as a minimal, unavoidable
touch needed to keep the suite green after this fix).

## 2026-08-27 — fix:contract — reconcile the contract with what Stage 1/2 built

Eleven changes to `contracts/openapi.v1.yaml` + `contracts/events.schema.json`
+ `dev/build_contract.py`, each traced to a lane's own report or code, per
the orchestrator's fix:contract assignment. No dataclass changes, so
`contracts/schema.json` is untouched by this entry.

1. **`JobKind` enum** gains `tools` and `report` (alongside the existing
   `viewer`, `project_init`). `tit/jobs/spec.py::JOB_KINDS` already includes
   both — its own docstring calls them "used only by the internal job model
   and not yet in the frozen v1 contract's enum" and names
   `CONTRACT_JOB_KINDS` as the gap tracker. B1's `tit/jobs/kinds.py` and
   `tit/jobs/plans.py` (the `pre` pipeline's internal `report` stage) already
   emit/consume both kinds.
2. **`GET /api/catalog/simulations/{name}?subject=` → `SimulationDetail`**
   added; the list endpoint (`GET /api/catalog/simulations?subject=`) is
   unchanged. B2's `tit/server/routes/catalog_v1.py::simulation_detail` and
   `tit/catalog.py::simulation_detail` already implement exactly this route
   and return shape — the contract was simply missing the path.
3. **`FreehandConfig.type` enum**: `[xyz, label]` → `[U, M]`. The on-disk
   `stim_configs/*.json` format (`tit/catalog.py::_read_freehand_file`,
   read/written by `tit/gui/extensions/electrode_placement.py`) has always
   used `"U"`/`"M"` (unipolar/multipolar); `xyz`/`label` never matched
   anything real. `tit/catalog.py`'s own docstring already flagged this
   exact mismatch and passed `type` through verbatim rather than force it
   into the wrong enum.
4. **`Region` schema**: `id` narrows from `string | integer` to `integer`,
   and a required `hemi: "lh" | "rh" | null` is added (`name` was already
   required). Documented that for a cortical (annotation) atlas, `id` is the
   FreeSurfer `.annot` label index — the exact integer
   `FlexConfig.AtlasROI.label` / `ExConfig`'s equivalent needs — and `hemi`
   is that region's own hemisphere (an `.annot` file is per-hemisphere, so a
   cortical ROI can union regions from both). For a subcortical/volumetric
   atlas, `id` is the voxel label value and `hemi` is `null`. This is the
   *target* shape flagged by P3's `pages/optimizer-flex/PARITY.md` (item 2)
   and `pages/_shared/roi/RoiPicker.tsx`'s header comment as needed for
   cortical ROIs to work end-to-end — `tit/catalog.py::atlas_regions`'s
   current cortical branch still returns a display string id
   (`"lh.bankssts"`) with no `hemi`, which is a B2-owned gap this contract
   change now makes visible (see this lane's final report).
5. **`ViewLayer`**: added optional `percentile: {lo: number, hi: number} |
   null`, documented as an alternative input to explicit `cal_min`/`cal_max`
   that the server resolves to concrete absolute values at ViewSpec-build
   time (`GET /api/view/{kind}`, `POST /api/viewers/freeview`) — a layer's
   `cal_min`/`cal_max` are always the final resolved numbers a viewer
   applies. `ViewSpec.freeview_args` was already present (verified, no
   change needed). Added a `resolved_layers` note to `ViewSpec.layers`
   documenting that every layer leaving the server already has resolved
   `cal_min`/`cal_max`, whether the caller asked via percentile or directly.
   Addresses `pages/viewer/PARITY.md`'s "No true percentile thresholding"
   gap (percentile math itself is still P6/B2's to implement server-side).
6. **`ExRun`/`FlexRun`**: both gain a required `artifacts:
   [{path, kind, label}]` array (using the existing `Artifact` schema).
   Addresses `pages/results/PARITY.md` ("`FlexRun` has no artifact list,
   only `manifest: Record<string, unknown>`... this page trusts... and
   doesn't [list PNGs]") and `pages/optimizer-ex/PARITY.md` ("the run's PNG
   artifacts... not built. `ExRun` in the v1 contract carries no
   artifact/image list"). Populating these arrays server-side is a B2
   `tit/catalog.py::flex_runs`/`ex_runs` follow-up, not done by this change.
7. **`POST /api/plan/{kind}` request body** gains optional
   `montage_sources: MontageSources` (new schema: `{flex: [{run, subject?,
   electrode_type?, eeg_net?}], freehand: [{name, subject?}]}`), documented
   as resolving into `PlanResult.resolved.montages` for `kind=sim`. This is
   the first-class contract equivalent of the non-schema
   `config["montage_sources"]` key B3's `tit/server/routes/plan.py` already
   reads (see its module docstring and `PlanRequest`) — **note the field
   names differ from B3's actual code**: the code reads `run_name`/
   `subject_id` per source entry, while this schema (matching the task
   brief's literal shape) uses `run`/`subject`. Flagged in this lane's final
   report as a B3 follow-up: either rename the code's keys to match the
   contract, or this schema should be re-aligned to `run_name`/`subject_id`
   — whichever an orchestrator decision picks, one side needs a one-line
   change to agree with the other.
8. **`Event` schema** (`contracts/events.schema.json` and the `Event`
   component in `openapi.v1.yaml`, kept in lockstep): restructured so
   - `exit` events require a new `code: integer` field (the actual exit
     code, no longer stringified into `msg`);
   - `result` events require `outputs: object` (the runner's arbitrary
     structured result payload, previously smuggled into `msg` as a JSON
     string) and may carry `artifacts: [Artifact]` (the job's accumulated
     artifact list, previously misfiled as `result`'s own `outputs`);
   - `artifact` events carry their own flat `path`/`kind`/`label` fields
     (both `path` and `kind` required), not a nested one-item `outputs`
     array.
   This exactly matches the shape `tit/jobs/events.py`'s module docstring
   describes as the target ("the schema's `outputs` field... is an array of
   file objects, but `emit_result`'s signature is fixed to a single
   `outputs: dict[str, Any]`" / "The schema has no dedicated exit-code
   field") — B4's `emit_artifact`/`emit_result`/`emit_exit` still write the
   *old* workaround shape as of this change, which is why
   `tests/test_runner_events.py::TestEmitHelpersWriteSchemaValidEvents`
   (5 tests) now fails schema validation; this is the expected, temporary
   cross-lane break the task brief calls out ("B4/B1 lanes are adapting
   their code to exactly this shape in parallel") — B4 updates
   `tit/jobs/events.py` to the new shape, not this lane.
9. **`NiftiAverageConfig`/`NilearnConfig`** placeholders added to
   `components.schemas` and to `PipelineConfig`'s `oneOf`, for the
   `nifti_average`/`nilearn` `PipelineKind`s that already existed with no
   config schema (`tit/server/routes/plan.py`'s `NO_SCHEMA_KINDS`). **Not**
   marked `x-tit-config` yet — `contracts/schema.json` has no
   `NiftiAverageConfig`/`NilearnConfig` `$defs` entry as of this change (B4
   is adding the dataclasses in parallel), and `dev/build_contract.py`'s
   `merge()` hard-fails on a marker naming a `$defs` entry that doesn't
   exist (by design — see
   `tests/test_config_schema.py::TestBuildContractScript::test_merge_raises_a_clear_error_for_an_unknown_defs_name`,
   F1b-owned, not touched here). The marker is left as a commented-out line
   next to each placeholder; once B4 registers the dataclass and
   `contracts/schema.json` is regenerated, uncomment it and rerun
   `dev/build_contract.py` — no other `openapi.v1.yaml` edit needed (same
   automatic pickup as the `QSIPrepSettings` entry above).
10. **`JobGroupRequest.parallel_subjects`** now documents the intended
    semantics explicitly: a per-group concurrency cap enforced by the
    scheduler, not the number of jobs submitted (every subject's job is
    created immediately as `queued`; the scheduler releases at most this
    many onto runners at once). This is the *target* behavior — B1's
    `tit/server/routes/jobs.py::submit_group` already flags in its own
    comment that the field is currently accepted and ignored (`pre`'s DAG
    shape doesn't depend on it, and nothing yet turns it into a scheduling
    constraint). Flagged in this lane's final report as a B1 follow-up.
11. **`dev/build_contract.py`**: `merge()` now adds a
    `discriminator.mapping` to every copied-in `oneOf` that discriminates on
    `"_type"`, mapping each branch's *real* `_type` const literal (e.g.
    `"PoolElectrodes"`, `"AtlasROI"`) to its `$ref` (e.g.
    `"#/components/schemas/ExConfigPoolElectrodes"`,
    `"#/components/schemas/FlexConfigAtlasROI"`). Without this,
    `openapi-typescript` synthesises a discriminant literal from the
    `$defs`/schema *name* instead of reading the schema's own `_type` const
    — wrong whenever they differ, e.g. `ExConfigPoolElectrodes`'s `_type` is
    `"PoolElectrodes"`, not `"ExConfigPoolElectrodes"` (P4's
    `pages/optimizer-ex/PARITY.md` finding). Verified on the real merge:
    `ExConfig.electrodes`, `MExConfig.electrodes`, and `FlexConfig.roi`/
    `.non_roi` all now carry correct mappings (see this lane's final
    report for the exact values).

Regenerated: `contracts/openapi.v1.json` (`python3 dev/build_contract.py` —
prints one warning-free run; no unmerged placeholders since the two new
config schemas are deliberately left unmarked, see item 9),
`desktop/src/renderer/api/schema.d.ts` (`npm run gen:api`). Verified
`python3 dev/contracts_check.py contracts/openapi.v0.yaml
contracts/openapi.v1.json` reports OK (10 operations, 9 schemas, unchanged
from v0). `python3 -m pytest -q` is green except the 5 pre-flagged
`tests/test_runner_events.py` failures from item 8 above (B4's to fix).
`cd desktop && npx tsc --noEmit -p tsconfig.web.json` surfaces exactly one
new type error caused by this change —
`src/renderer/pages/simulator/FreehandTab.tsx(67,13)`, `"label" | "xyz"` no
longer assignable to the corrected `"U" | "M"` (item 3, P2's to fix); the
`node:fs`/`node:path`/`__dirname` errors in `tests/unit/*.test.ts` are
pre-existing (`tsconfig.web.json`'s `types` array omits `"node"` even though
`@types/node` is a devDependency) and unrelated to this change.

## 2026-08-27 — fix:backend-runners — `NiftiAverageConfig`/`NilearnConfig` land; events schema aligned

Two new config dataclasses registered (closing the fix:contract lane's item
9 gap above), plus `tit/jobs/events.py`'s `emit_artifact`/`emit_result`/
`emit_exit` rewritten to the reconciled `Event` shape from that lane's item
8 (closing the 5 pre-flagged `tests/test_runner_events.py` failures).

1. **`tit.jobs.events`**: `emit_artifact(path, kind, label=None)` now writes
   its own flat `{"type": "artifact", "path", "kind", "label"?}` fields
   instead of a nested one-item `outputs` array; `emit_result(outputs)`
   writes *outputs* verbatim as the event's own `outputs` object (previously
   JSON-stringified into `msg`) plus an `artifacts` array of every
   `emit_artifact` call seen so far (previously misfiled as `result`'s own
   `outputs`); `emit_exit(code)` writes `code` as a real integer field
   (previously stringified into `msg`). No signature changes — every
   `__main__.py` call site is unaffected. `tests/test_runner_events.py` and
   `tests/test_runners_deserialize.py` updated to assert the new shapes (3
   call sites in the latter that read `events[-1]["msg"] == "<code>"` now
   read `events[-1]["code"] == <code>`).
2. **`NiftiAverageConfig`** (`tit/stats/nifti_average_config.py`, new
   module) + its `NiftiAverageSubject` row type: mirrors the "NIfTI Group
   Averaging" GUI extension's fields (`tit/gui/extensions/
   nifti_group_average.py`) — `output_name`, `subjects` (subject_id +
   simulation_name + group, >= 2), a `space` enum (`subject`/`mni`) that
   selects the default `nifti_file_pattern` when one isn't given
   explicitly, and `diff_pairs`. Registered in
   `tit.config_io.CONFIG_CLASS_REGISTRY`. Runner:
   `tit/stats/nifti_average.py` (`simnibs_python -m tit.stats.nifti_average
   config.json`, matching `tit/jobs/kinds.py::MODULE_FOR_KIND["nifti_average"]`
   exactly) — a headless port of the GUI extension's `AnalysisThread.run()`
   using the same `tit.stats.nifti.load_grouped_subjects_ti_toolbox` helper,
   emitting `stage`/`artifact` (one per saved group-average and difference
   NIfTI, plus the summary `config.json`)/`result`/`exit` events.
3. **`NilearnConfig`** (`tit/plotting/nilearn/config.py`, new module) + its
   `NilearnSubjectSimulation` pair type: mirrors the "Nilearn Visuals" GUI
   extension's fields (`tit/gui/extensions/nilearn_viz.py`) —
   `subject_simulation_pairs`, `min_cutoff`/`max_cutoff`, `atlas_name`,
   `selected_regions`, `subdir_name`, `use_percentiles`,
   `create_glass_brain`, `glass_brain_cmap`. Registered in
   `tit.config_io.CONFIG_CLASS_REGISTRY`. Runner:
   `tit/plotting/nilearn/__main__.py` (`simnibs_python -m tit.plotting.nilearn
   config.json`, matching `MODULE_FOR_KIND["nilearn"]` exactly) — a headless
   port of the GUI extension's `PublicationImageWorker.run()` using the
   existing `create_pdf_entry_point_group`/`create_glass_brain_entry_point_group`
   helpers, emitting the same event sequence.
4. **`contracts/openapi.v1.yaml`**: uncommented the `x-tit-config:
   NiftiAverageConfig` / `x-tit-config: NilearnConfig` markers the
   fix:contract lane left staged (item 9 above) now that both `$defs`
   entries exist in the regenerated `contracts/schema.json`. This is an
   F1a-owned file outside this lane's normal ownership; the edit is the
   exact two-line mechanical follow-up that lane's own report and the
   in-file comments named as the next required step once B4 landed the
   dataclasses, so it is made here rather than left blocking a second
   hand-off. Flagged for the orchestrator to spot-check.
5. **`tit/pre/structural.py::_run_step`** now calls `tit.jobs.events.emit_stage(label)`
   before running each pipeline step's function (DICOM conversion, SimNIBS
   charm, subject atlas segmentation, recon-all, tissue analysis, QSIPrep,
   QSIRecon, DTI extraction, subcortical segmentations) — orchestration
   only, no change to the step functions themselves. A no-op unless
   `$TIT_EVENTS_FILE` is set. Covered by a new
   `TestRunStep.test_emits_a_stage_event_per_step` in
   `tests/test_pre_pipeline.py`.
6. **`tests/test_config_schema.py`** (F1b-owned; edited here only because
   this lane's registry addition made `test_sample_instances_cover_the_whole_registry`
   fail): added `NiftiAverageConfig`/`NilearnConfig` sample instances to
   `_sample_instances()` and their imports, so the round-trip /
   discriminated-union / `$defs`-collision suite continues to exercise
   every registered class.
7. Verified `tit.jobs.locks.keys_for` call sites in `tit/opt/ex/__main__.py`
   and `tit/opt/mex/__main__.py` (flagged as 2-arg in this lane's
   assignment) already pass `(kind, subject_ids, config_dict)` — no change
   needed; a prior pass on this branch had already fixed them.

Regenerated in the container: `docker exec tit-v3-spike simnibs_python
/ti-toolbox/dev/build_schema.py` (59 `$defs`, includes `NiftiAverageConfig`/
`NiftiAverageSpace`/`NiftiAverageSubject`/`NilearnConfig`/
`NilearnSubjectSimulation`), then `python3 dev/build_contract.py` (writes
`contracts/openapi.v1.json`, no warnings) and `cd desktop && npm run
gen:api` (writes `src/renderer/api/schema.d.ts`, no errors). Verified
`python3 dev/contracts_check.py contracts/openapi.v0.yaml
contracts/openapi.v1.json` reports OK (10 operations, 9 schemas, unchanged
from v0). `cd desktop && npx tsc --noEmit -p tsconfig.web.json` shows only 3
pre-existing, unrelated errors in `tests/unit/analyzer-defaults.test.ts`
(string/number mismatch, nothing to do with this change's schemas — not
present anywhere near `NiftiAverageConfig`/`NilearnConfig`/`Event`).
`python3 -m pytest -q` (from repo root): full suite green (2827 passed, 17
skipped) on a clean run; two later re-runs each hit exactly one unrelated,
order-dependent failure in a different B1-owned file each time
(`tests/test_jobs_manager.py::test_submit_runs_and_succeeds`,
`tests/test_jobs_model.py::test_keys_for_stats_uses_analysis_name_and_type_discriminator`)
— both pass in isolation and neither imports anything this lane touched;
this looks like pre-existing `sys.modules` / scipy-mock-ordering flakiness
across the many test files that pop and reimport real `scipy.ndimage`/
`scipy.stats` at collection time (several already carry this exact caveat
in their own docstrings), not a regression from this entry.

## 2026-08-27 — fix:contract (round 2) — ra_13 finding 3 gate fixes + electrode-overlays + `log_path`

No dataclass changes in this entry either, so `contracts/schema.json` is
untouched. All work is in `contracts/openapi.v1.yaml` and
`dev/contracts_check.py` (this lane's own files), plus two lines in a
`tit/tests`-adjacent test (`tests/test_server_skeleton.py`) that unit-test
`dev/contracts_check.py` directly and needed updating for its new return
type.

1. **`dev/contracts_check.py` path/param comparison now normalises known
   aliases**: `{id}` (the contract's own spelling) is treated as the same
   parameter as `{job_id}`/`{report_id}` (some server route functions use
   those names internally for readability), both when matching a contract
   path template against the dump's paths and when matching individual
   `in: path` parameters. Documented in `openapi.v1.yaml`'s top-level
   description as the canonical naming (contract always says `id`).
2. **`/ws/*` paths are now required in the contract but exempt from the
   dump-superset check** — FastAPI does not describe WebSocket routes in
   its generated OpenAPI document at all, so `/ws/jobs`/`/ws/system` can
   never "be found" in a dump regardless of correctness.
3. **Response codes 401/403/404 are now skipped by the check** (they are
   implied by the contract's global auth/jail note) instead of being
   required verbatim on every operation. Each tag in `openapi.v1.yaml` now
   carries a one-line pointer back to that note (the "router-level note").
4. **A dump response schema with no declared `properties` at all — FastAPI's
   shape for a route typed `-> dict[str, Any]` / `-> list[dict]` — no longer
   fails the required-property check.** Its gaps are now collected as
   *warnings* (printed separately, counted, never gate the exit code) since
   there is nothing structural left to verify once the dump has erased the
   shape. This is the single largest source of the previously-reported "293
   problems" (ra_13 finding 3d) — see the verification numbers below.
5. **New path: `GET /api/catalog/electrode-overlays?subject=&simulation=`**
   → `[ElectrodeOverlay]` (`{mode: "TI"|"mTI", path: string, exists:
   boolean}`), 404 for an unknown subject/simulation — the contract-side
   half of the gap the 2026-08-27 fix:backend-catalog entry above flagged
   ("this lane may not edit openapi.v1.yaml"); shape copied verbatim from
   `tit.catalog.electrode_overlays` (already implemented and live).
6. **`JobStatus.log_path: string | null`** added — the container path to a
   job's raw stdout/stderr log, so `pages/jobs/JobDetailDrawer.tsx` can stop
   reconstructing `code/ti-toolbox/jobs/<id>/stdout.log` client-side (ra_13
   finding 6). Not yet emitted by `tit.jobs` — a B1 follow-up.
7. **`JobError.type` is now an enum**: the nine-value taxonomy
   `pages/jobs/format.ts::ERROR_LABEL` already labels, plus `kind_error`
   (`tit/jobs/manager.py:628`, an unknown/disallowed job kind rejected
   before a runner starts). Note: `tit/jobs/manager.py:654` also emits
   `spawn_error`, which is in neither the taxonomy nor this enum yet —
   `errorLabel()` degrades it to a title-cased fallback rather than
   crashing, so this is a labelling gap, not a functional one; left out of
   the enum since only `kind_error` was in scope for this entry, flagged
   here for whoever next touches `JobError.type`.
8. **`/api/plan/{kind}` request body gains `parallel_subjects: integer |
   null`**, mirroring `JobGroupRequest.parallel_subjects`, so a `kind=pre`
   plan preview can show the same per-group concurrency cap
   `POST /api/jobs/groups` will enforce.
9. **Renamed three `components.schemas` keys to match `contracts/schema.json`
   and the server's own names**: `BlenderMontageConfig` → `MontageConfig`,
   `BlenderVectorConfig` → `VectorConfig`, `BlenderRegionConfig` →
   `RegionConfig` (no collision with the pre-existing, unrelated `Region`
   catalog schema). Updated the three `$ref`s inside `PipelineConfig.oneOf`
   and the prose list in the top-level description accordingly.
   `dev/contracts_check.py` now also exempts `PipelineConfig` itself from
   the named-schema-by-dump check (it is a contract-only documentation
   union over the `kind`/path parameter, not a model the server names).
10. **Documented, not changed**: `info.version` (this contract's own
    version) is expected to differ from the live server's
    `/api/version.tit_version` (the installed `tit` package version at
    build time) — noted in both the top-level description and
    `Version.tit_version`'s own description; `dev/contracts_check.py` never
    compared `info` in the first place, so nothing to change there.
    `Region` (the atlas-region catalog schema, distinct from the renamed
    `RegionConfig`) is unchanged per this round's instructions.

Verified:

- `python3 dev/build_contract.py` → writes `contracts/openapi.v1.json`
  cleanly (`MontageConfig`/`VectorConfig`/`RegionConfig` merge in with real
  `properties`/`required`, not the `additionalProperties: true` placeholder
  — confirmed by inspecting the output).
- `cd desktop && npm run gen:api` → regenerates
  `src/renderer/api/schema.d.ts` with no errors.
- `python3 dev/contracts_check.py contracts/openapi.v0.yaml
  contracts/openapi.v1.json` → `OK — 10 operation(s) and 9 schema(s) ...
  present` (unchanged; v1 still a clean superset of v0).
- `docker restart tit-v3-spike` then `docker exec tit-v3-spike
  simnibs_python -m tit.server --project /mnt/000 --dump-openapi
  /tmp/o.json` + `docker cp` + `python3 dev/contracts_check.py
  contracts/openapi.v1.json /tmp/o.json` → **130 warnings, 54 problems**
  (down from the 293 problems ra_13 reported against the pre-fix checker;
  the 130 warnings are exactly the dict/list-response required-property
  gaps item 4 above now separates out). The 54 remaining problems are real,
  cross-lane drift for other lanes in this round, not contract-check bugs:
  `GET /api/capabilities`/`schema Capabilities` missing `jupyter` (B2);
  `POST /api/project/init` and `POST /api/system/terminate` not implemented
  by the live server (B1/B2); `PlanJob.kind`/`LockConflict.kind` untyped
  (no enum) in the dump in all four places they appear (B3, ra_13 finding
  3f); and ~40 `schema <Name> missing from dump components` entries for
  names like `JobStatus`/`ViewSpec`/`Settings`/`Roi`/`FlexRun`/etc. that
  exist in the contract but have no distinct named model in the live
  FastAPI dump because their routes are typed `-> dict`/`-> list[dict]`
  rather than a `response_model=` (the structural half of ra_13 finding 3d
  that adding response models, not adjusting the checker, will close).
- `python3 -m pytest -q` (full suite, from repo root): **2840 passed, 17
  skipped**, 0 failed — includes the two `dev/contracts_check.py` unit
  tests in `tests/test_server_skeleton.py`
  (`test_openapi_covers_v0_contract`, `test_contracts_check_reports_type_and_enum_mismatch`),
  updated in this entry only to unpack `check()`'s new `(missing,
  warnings)` return (previously a bare `missing` list).
- `python3 -m black dev/contracts_check.py dev/build_contract.py
  tests/test_server_skeleton.py` → only `dev/contracts_check.py`
  reformatted (whitespace only, no logic change); the other two already
  clean.

## 2026-08-27 — B2 (catalog-security) — `Capabilities.jupyter`, `project/init`, `system/terminate`, `view/args`; ra_14 path/name hardening

No dataclass changes (`contracts/schema.json` untouched); this closes three
of the cross-lane drift items the previous entry listed as open for B2, plus
one already-declared-but-unimplemented contract route, plus a round of
security fixes (`ra_14`) scoped to this lane's own files.

1. **`GET /api/capabilities` now returns `jupyter`** (`tit/server/schemas.py`
   `Capabilities.jupyter: bool`, `tit/server/routes/capabilities.py` probes
   `find_spec("jupyter")` in the server's own interpreter — the container's
   `NOTEBOOK` alias runs `simnibs_python -m jupyter lab`, same interpreter).
   Was already required by `contracts/openapi.v1.yaml`; the live dump now
   matches it (ra_13 finding 3e).
2. **`POST /api/system/terminate {pid}` implemented**
   (`tit/server/routes/system.py`): refuses `pid <= 1`, the server's own
   pid, and any pid whose name/cmdline doesn't match
   `RELEVANT_KEYWORDS` (the same allowlist `GET /api/system`'s process list
   already uses) — SIGTERM, 3s grace, then SIGKILL.
3. **`POST /api/project/init {example_data}` implemented**
   (`tit/server/routes/project.py`): submits a `project_init` job through
   `tit.jobs.api.submit`; degrades to a 503 (catches `ValueError`/
   `NotImplementedError`) if the job kind isn't wired up in
   `tit.jobs.spec.JOB_KINDS`/`tit.jobs.kinds` yet — same pattern
   `tit/server/routes/viewers.py` already used for this situation. (Verified
   live against `tit-v3-spike`: B1 landed `project_init` support mid-round,
   so this now returns a real `201 {kind: "project_init", state: "queued"}`
   rather than the 503 fallback.)
4. **`POST /api/view/args {viewspec}` -> `{freeview_args, freeview_command}`
   added** (`tit/server/routes/viewers.py`): the same jail +
   `to_freeview_args` the launch route uses, with no job submitted and no
   X11 requirement — lets the Viewer page's command-preview panel show the
   real command instead of a hand-rolled TypeScript mirror (ra_13 finding
   9). **Not yet added to `contracts/openapi.v1.yaml`** — that file is
   frozen to the contract lane; flagging here for whoever owns the next
   contract edit to add the path + reuse the existing `ViewSpec`
   request/`{freeview_args: [string], freeview_command: [string]}` response
   shape already documented on `ViewSpec.freeview_args`.
5. **ra_14 finding 1 (path/type injection)**: `tit/catalog.py` gains
   `is_safe_name()` (`^[A-Za-z0-9_-]{1,64}$`) and `as_float()`, enforced in
   `create_roi`, `delete_roi`, `put_montage`, `put_freehand_config` — a ROI
   `name` of `../../../../outside/escaped` used to write a file outside the
   project entirely; `x`/`y`/`z` used to be written to disk with no type
   check at all (verified live: `x: "PWNED"` used to land in the CSV
   verbatim, now 422s before the file is touched).
6. **ra_14 finding 6 (artifact/report CSP)**: `/api/files/artifact` now
   sends `X-Content-Type-Options: nosniff` on every response and
   `Content-Security-Policy: sandbox allow-scripts` on `.html`/`.htm`/
   `text/html` ones; `/api/files/report`'s own CSP gained `sandbox
   allow-scripts` (opaque origin — no cookies, no same-origin fetch back
   into the session) plus `nosniff`, independent of the renderer's iframe
   `sandbox=` attribute.
7. **ra_14 finding 11 (viewer path/arg injection)**: `tit/viewspec.py`
   gains `jail_roots()`/`resolve_jailed()` (project + `resources/`, shared
   by `tit/server/routes/files.py` so there is exactly one definition of
   "inside the project"); `build_view`'s `custom` kind, every layer path in
   a client-submitted `ViewSpec` at launch, the Gmsh mesh path, and its
   `.opt` sidecar write location are all jailed through it, and any
   resulting argv entry starting with `-` is refused outright
   (`tit/server/routes/viewers.py`).
8. **ra_14 finding 14 (settings)**: `tit/server/routes/settings.py`'s
   `_save_project_settings` now uses a unique `.tmp-<pid>-<monotonic_ns>`
   name (matching `tit/jobs/registry.py`'s pattern) instead of a fixed
   `.tmp`; `PUT /api/settings` now validates `theme in
   {system, light, dark}` and `panels` against the known `PanelId` list in
   `pages/panels/_shared.ts`.

Verified:

- `python3 -m pytest -q` (full suite, from repo root): 2932 passed, 17
  skipped, **6 failed** — all six in `tests/test_jobs_routes.py`, none of
  which touch a file in this lane's scope (`tit/jobs/routes.py` mid-edit by
  B1 for ra_13/ra_14 findings on the public job-submit route, confirmed by
  reading the failing assertions and the route's own new inline comments
  citing those findings). Isolated re-run of every file this lane owns
  (`tests/test_catalog_v1.py tests/test_viewspec.py tests/test_files_routes.py
  tests/test_server_skeleton.py tests/test_catalog.py`) is 167/167 green,
  both on the host (py3.14) and inside `tit-v3-spike` (py3.11).
- `docker restart tit-v3-spike` then live curl probes against
  `127.0.0.1:8765` (token `spike`): ROI traversal name → 422, no file
  written outside the project (confirmed via `find` inside the container);
  ROI non-numeric coordinate → 422; artifact `.html` → `nosniff` +
  `sandbox allow-scripts`; artifact `.json` → `nosniff` only, no CSP;
  `POST /api/system/terminate {pid:1}` → 403; `PUT /api/settings` with a
  bad theme/panel → 422; `POST /api/view/args` on a real `ViewSpec` returns
  `freeview_command[0] == "freeview"` and `freeview_args` byte-identical to
  the `GET /api/view/subject` response's own `freeview_args`; the same call
  with an injected `{"path": "/etc/passwd"}` layer → 403; `GET
  /api/capabilities` → `jupyter: true` in this environment.
- `python3 -m black --check` on every file this lane touched: clean after
  `black`-formatting `tit/server/routes/system.py` and
  `tests/test_catalog_v1.py` (both whitespace-only reflow).

## 2026-08-27 — B4 (runners+config, round 2) — flex driver dispatch, `tissue_conductivities`, strict `deserialize_config`

**FlexConfig gains three fields** (`tit/opt/config.py`) so `flex_adaptive`/
`flex_pareto` jobs are real, schema-visible configs instead of two job
kinds that silently ran a plain `flex` search (ra_13/audit finding 1):

1. `mode: FlexConfig.Mode = "flex"` — new `StrEnum` `{"flex", "flex_adaptive",
   "flex_pareto"}`. `tit.opt.flex.__main__` dispatches on it to pick
   `run_flex_search` / `run_adaptive_focality` / `run_pareto_sweep`
   (`tit/opt/flex/drivers.py`, new file). `mode` values are exactly
   `tit.jobs.kinds.JOB_KINDS`' three flex kinds, so a submitter sets
   `config["mode"] = kind` verbatim.
2. `adaptive: FlexConfig.AdaptiveFocalityConfig | None = None` — nested
   dataclass `{roi_percentage: float = 80.0, nonroi_percentage: float =
   20.0}` (exact field names/defaults from
   `tit.gui.flex_search_tab`'s `roi_percentage_input`/
   `nonroi_percentage_input` spin boxes). Validates `0 < nonroi_percentage
   < roi_percentage < 100`. Auto-defaulted when `mode="flex_adaptive"` and
   left `None`.
3. `pareto: FlexConfig.ParetoSweepConfig | None = None` — nested dataclass
   `{roi_pcts: list[float] = [80.0], nonroi_pcts: list[float] = [20.0,
   30.0, 40.0]}` (same field names/defaults as `tit.gui.flex_search_tab`'s
   `roi_pcts_input`/`nonroi_pcts_input` text fields and
   `tit.opt.flex.pareto.compute_sweep_grid`'s parameters). Validates every
   value in `(0, 100)` and every `(roi_pct, nonroi_pct)` pair has
   `nonroi_pct < roi_pct`. Auto-defaulted when `mode="flex_pareto"` and
   left `None`.

`mode in {"flex_adaptive", "flex_pareto"}` requires `goal="focality"`
(`ValueError` otherwise) — both driver workflows exist only to compute the
ROC goal's thresholds; `"focality_tf"` needs none and is rejected too.

**`tit/opt/flex/drivers.py`** (new): `run_adaptive_focality(config)` and
`run_pareto_sweep(config)`, extracted from
`tit.gui.flex_search_tab`'s `_start_mean_optimization` /
`_run_adaptive_focality_step2` / `_run_pareto_sweep_step2` /
`_read_mean_intensity_from_manifest`, composing the existing
`tit.opt.flex.flex.run_flex_search` and `tit.opt.flex.pareto` grid/plot/
manifest helpers. Both emit `stage`/`progress` events per sub-run (mean
calibration, then the focality run or each grid point) via `tit.jobs.events`.
Fixes the two audit bugs in the legacy Qt orchestrator along the way:
(a) achievable ROI intensity is read directly off the mean-optimization
sub-run's own `FlexResult.best_value` — never a filesystem scan for "the
newest manifest with `goal=mean`" (`_read_mean_intensity_from_manifest`'s
bug, which could silently pick up a stale or unrelated run); (b) there is
no multi-subject loop at all — each driver takes one `FlexConfig` (one
`subject_id`) and runs its complete sequence to completion, because the
job system already submits one job per subject for `flex`/`flex_adaptive`/
`flex_pareto` (`tit.jobs.kinds.MODULE_FOR_KIND`), so the legacy GUI's bug
(a multi-subject Pareto sweep silently stopped after subject 1 because
`_finalize_pareto_sweep` never called `_process_next_subject`) cannot
recur structurally.

**`SimulationConfig.tissue_conductivities: dict[int, float] | None = None`**
(`tit/sim/config.py`) — per-tissue conductivity overrides (S/m), keyed by
SimNIBS tissue number. JSON object keys are always strings, so this
round-trips as `{"<tissue number>": <S/m>}`;
`tit.config_io.deserialize_config` now has a generic `dict`-origin branch
that coerces non-`str` key types back (not flex/sim-specific — any future
`dict[int, X]`/`dict[float, X]` field gets this for free), and
`SimulationConfig.__post_init__` does the same for an instance built
directly with string keys. `tit/sim/__main__.py` sets
`TISSUE_COND_<n>` environment variables from it before calling
`run_simulation` — the mechanism
`tit.sim.base.BaseSimulation._apply_tissue_conductivities` already reads
and previously had nothing setting it from the config/job system (ra_13
finding 2: the Conductivity dialog was a no-op). `tit/sim/base.py` is
untouched.

**`tit.config_io.json_schema(cls)` now sets `"additionalProperties": false`**
on every fixed-shape object schema (the top level and every `$defs` entry
with its own `"properties"`) — `_close_object_schemas`, ra_11 finding 3. A
free-form mapping field (only `SimulationConfig.tissue_conductivities` so
far) has no `"properties"` of its own and is left open with pydantic's own
`"additionalProperties": {"type": "number"}`, so this can never turn a
legitimate dynamic-key field into a fixed one.

**`tit.config_io.deserialize_config(cls, data, *, strict: bool = False)`**
— new keyword-only parameter (default `False`, so every existing call site
is unaffected). `strict=True` raises `ValueError` naming every key in
`data` that is not one of `cls`'s own fields, recursively through nested
dataclasses and discriminated unions (`_type` itself is never flagged).
Runners keep calling it with the default (their legacy flat-dict layouts —
e.g. `tit.analyzer.__main__`'s pre-`AnalyzerConfig` fallback — are
unaffected). **`tit/server/routes/validate.py`** (one-line change, not
otherwise owned by this lane) now calls `deserialize_config(cls,
body.config, strict=True)`, so `POST /api/validate/{kind}` reports a
misspelled/renamed config key as a real validation error instead of
silently accepting it (ra_11 finding 3's literal reproduction: a form
field renamed to `condictivity`/`conductivety` used to validate `ok: True`
and just ran with the dataclass default).

### Verified

- `docker exec tit-v3-spike simnibs_python /ti-toolbox/dev/build_schema.py`
  → `Wrote /ti-toolbox/contracts/schema.json (62 $defs)` (was 59; +`Mode`,
  +`AdaptiveFocalityConfig`, +`ParetoSweepConfig`).
- `python3 dev/build_contract.py` → writes `openapi.v1.json` cleanly.
- `cd desktop && npm run gen:api` → regenerates `schema.d.ts`;
  `FlexConfig.mode`/`.adaptive`/`.pareto` and the two new `components.schemas`
  entries present. `npm run typecheck` → clean except the 3 pre-existing
  `tests/unit/analyzer-defaults.test.ts` errors (unrelated `RoiRegion.id`
  mismatch, already flagged in an earlier entry).
- `python3 dev/contracts_check.py contracts/openapi.v0.yaml
  contracts/openapi.v1.json` → OK, unchanged (still a clean v0 superset).
- `docker restart tit-v3-spike` → `docker exec tit-v3-spike simnibs_python -m
  tit.server --project /mnt/000 --dump-openapi /tmp/o.json` → `docker cp` →
  `python3 dev/contracts_check.py contracts/openapi.v1.json /tmp/o.json` →
  **136 warnings, 51 problems** (down from the previous entry's 54 — no new
  drift from this round's fields; the remaining problems are pre-existing
  and owned by other lanes, per that entry).
- `docker exec tit-v3-spike simnibs_python -c '...'` — imports
  `tit.opt.flex.drivers`, builds a `mode="flex_pareto"` `FlexConfig` (gets
  the default `ParetoSweepConfig`), and round-trips
  `SimulationConfig(tissue_conductivities={"1": 0.126, "3": 1.654})` to
  `{1: 0.126, 3: 1.654}` — all against the real SimNIBS/py3.11 environment,
  not just the host's mocked py3.14.
- `python3 -m pytest -q` (host, full suite): **2972 passed, 17 skipped, 0
  failed**. Same files re-run inside `tit-v3-spike`
  (`test_config_schema.py test_opt_config.py test_opt_flex_drivers.py
  test_opt_main.py test_sim_config.py test_runners_deserialize.py
  test_plan_routes.py`): **333 passed**.
- `python3 -m black --check` on every touched file: clean after
  `black`-formatting (whitespace/wrapping only, no logic changes).

## 2026-09-02 — F2 (server, v3 in-app viewer) — `/api/files/raw/{path}`, `ViewSpec.scene`, `TitScene`

No dataclass changes, so `contracts/schema.json` is untouched by this entry.
Everything here comes from `dev/notes/v3-ux-redesign-plan.md` §4.1/§4.2 (the
in-app viewer replaces the Freeview/Gmsh round trip for *viewing*; both
launchers stay).

1. **New path `GET|HEAD /api/files/raw/{path}`** (`tit/server/routes/files.py`).
   Streams one project file to the viewer as opaque bytes -- the file types
   `/api/files/artifact` refuses (`.nii.gz`, `.msh`, `.msh.opt`, `.gii`,
   `*_LUT.txt`, `.lut`, `.annot`, `.mgz`), with the opposite response policy:
   `application/octet-stream` + `nosniff` + `attachment`, never a
   `Content-Encoding`, and a 403 for the extensions a browser could execute as
   a document (`.html .htm .xhtml .svg .xml .xsl .mhtml`). Range/206, `If-Range`
   and `ETag`/304 are implemented in the route (Starlette's `FileResponse` does
   Range but not 304, and FastAPI does not add HEAD to a GET route). The URL
   path *is* the absolute container path minus its leading slash, so the last
   segment stays the real file name -- the viewer's loader takes the name, the
   gzip decision and its volume-vs-mesh routing from it, all of which a
   `?path=` URL would mangle. `head` is declared for documentation only
   (`dev/contracts_check.py`'s `METHODS` and the desktop contract self-test
   both enumerate get/post/put/patch/delete).
2. **Jail narrowed for this route only.** `tit.viewspec.raw_jail_roots()` =
   project dir + `resources/atlas`, versus `jail_roots()`'s project dir +
   the whole `resources/` tree. Handing a launcher any bundled reference file
   is fine; handing the *browser* `resources/patches/*.py` from the app's own
   origin is not. Verified in-container: `resources/atlas/MNI152_T1_1mm.nii.gz`
   → 200, `resources/patches/patch_nan_to_num.py` → 403.
3. **`ViewSpec.scene`** (optional) plus six new `components.schemas`:
   `TitScene`, `SceneDataset`, `SceneSidecar`, `SceneLayer`, `SceneWindow`
   (and `SceneSidecars`/`SceneThreshold`/`ViewPercentile` in the dump only).
   Built by the pure `tit.viewspec.to_tetravox_scene(spec)` from the resolved
   layers, attached in `finish_spec` so `GET /api/view/{kind}` and
   `POST /api/view/args` cannot diverge. `POST /api/view/args`'s response
   gains `scene` (that route is not in the contract).
4. **`ViewSpec`/`ViewLayer` are now Pydantic models** (`tit/server/schemas.py`)
   with `response_model=ViewSpec` on `GET /api/view/{kind}`, so both -- and the
   scene schemas -- appear in the dump by name instead of as an anonymous
   `dict[str, Any]`. `build_view` now normalises `space` to `subject`/`mni`
   (the two values the contract has always declared).
5. **CSP**: `script-src 'self' 'wasm-unsafe-eval'` added to
   `tit/server/app.py::CSP_HEADER`; without it Chromium blocks
   `WebAssembly.instantiate` (scripts were falling back to `default-src
   'self'`) and the viewer cannot start, in a browser tab as well as in
   Electron. `mimetypes.add_type("application/wasm", ".wasm")` in
   `tit/server/static.py` so the bundled module streams with the type
   `instantiateStreaming` requires.
6. **`tit/tools/electrode_overlay.py`** writes alpha `255` in the channel LUT
   instead of `0`: a FreeSurfer LUT's fourth colour column is read as opacity
   by every consumer except Freeview (which reads it as transparency and
   treats 255 as opaque), so every electrode marker was invisible in the
   in-app viewer.

Regenerated: `python3 dev/build_contract.py` → `contracts/openapi.v1.json`;
`cd desktop && npm run gen:api` → `desktop/src/renderer/api/schema.d.ts`
(now names `components["schemas"]["TitScene"]`).

### Verified

- `python3 -m pytest -q` (host, full suite): **3024 passed, 17 skipped, 0
  failed** — including the new `tests/test_files_raw.py` (20 cases) and
  `tests/test_viewspec_scene.py` (26 cases).
- `docker restart tit-v3-spike` → `docker exec … --dump-openapi /tmp/o.json`
  → `python3 dev/contracts_check.py contracts/openapi.v1.json <dump>` →
  **133 warnings, 49 problems**, down from the 51 this branch already had;
  none of the 49 mentions the raw route, `ViewSpec`, `ViewLayer` or any
  `Scene*` schema (the remaining ones are the pre-existing backlog other
  lanes own).
- Real data through the running container (`sub-ernie`, Dataset 000):
  `HEAD T1.nii.gz` → 200, 13,109,495 bytes, `etag
  "c6e5d6930ead4ce6bb282f95129c2b07"`, no `content-encoding`;
  `Range: bytes=0-1023` → 206 `bytes 0-1023/13109495` with the gzip magic
  `1f 8b 08 00` intact; full GET → 200 in 0.068 s; `If-None-Match` → 304;
  `grey_Thalamus_TI.msh` HEAD → 200, 63,926,663 bytes; `/etc/passwd` → 403;
  `…/../../etc/passwd` → 403; a symlink to `/etc/passwd` planted inside the
  project (and removed again) → 403; an existing project `report.html` → 403
  on the raw route and still 200 on `/api/files/artifact`.
- `GET /api/view/simulation?subject=ernie&simulation=Thalamus&space=subject`
  → 5 datasets with real byte counts (13.1 MB T1, 17.2 MB and 2.6 MB hidden
  overlays marked `lazy`), electrode LUT as a sidecar, `layout "2x2"`;
  `GET /api/view/custom?path=<Thalamus_TI.msh>` → a mesh dataset with its
  `.msh.opt` sidecar, `field "TI_max"`, `clip "cursor"`, `layout "3d+1"`.
- `cd desktop && npx vitest run tests/mock-server` → **17 passed** (the
  contract self-test's exact path coverage now includes the raw route).

## 2026-09-03 — W3a (server, Docker streamline) — real Tetravox ViewSpec v2 replaces `TitScene`; `/tetravox/` embed route; `Capabilities` drops X11/Freeview/Gmsh/FreeSurfer, adds `tetravox_embed`/`fastsurfer`

`dev/notes/v3-docker-streamline-plan.md` D1/D3: Freeview/Gmsh/X11/FreeSurfer removed from the
runtime entirely; viewing is the Tetravox embed served client-side from this same server.

1. **`ViewSpec.scene` is now a real Tetravox `ViewSpec` v2 document** (the frozen
   `@tetravox/engine` `scene/types.ts` shape, `SCENE_VERSION = 2`), built by
   `tit.viewspec.to_tetravox_viewspec(spec)` -- replacing the F2-era `TitScene`
   approximation. `TitScene`/`SceneDataset`/`SceneSidecar`/`SceneLayer`/`SceneWindow` are
   **deleted** from both `tit/server/schemas.py` and this contract; `ViewSpec.scene` is now
   `dict[str, Any] | None` server-side (`type: [object, "null"]` in the contract) because the
   full engine scene model is Tetravox-owned and far larger than a Pydantic model is worth
   mirroring here. The subset this server actually emits is hand-schema'd, host-facing, in
   `contracts/tetravox-viewspec-v2.schema.json` and asserted against every scene
   `tests/test_viewspec_scene.py` builds (`jsonschema.Draft202012Validator`).
   `DatasetRef.path`/`.absPath` are both the *same* origin-relative `/api/files/raw/...` URL
   string (never a container filesystem path) -- see `tit/viewspec.py`'s module-level docstring
   on why an absolute-path URL needs no client-side rewriting from inside the same-origin
   `/tetravox/` iframe, and why both fields carry it rather than picking one. `fingerprint` is
   always `""`. Volume layers get a concrete `Scale` (`{kind:'linear',lo,hi}` or
   `{kind:'heat',min,mid,max,...}`) resolved from one `numpy`/`nibabel` read per file
   (`tit.viewspec._volume_stats`, cached by `(mtime, size)`) -- a real `ViewSpec` has no
   percentile-window escape hatch the client resolves after load, unlike the retired
   `TitScene.SceneWindow`. A new grey-matter TI mesh layer (`_grey_mesh_layer`, hidden by
   default) is now built for `kind=simulation`'s default field, with `field: {source:'elm',
   name:'TI_max', component:'mag'}`, a cursor-following clip plane and 2D contours.
   `slices`/`view3d`/`annotations`/`background`/`lighting`/`transparency` are one fixed,
   documented default rig (no per-file camera fit -- documented as a known v1 limitation in the
   module docstring).
2. **`GET|POST /api/viewers/{freeview,gmsh}` and `_require_x11` are deleted**
   (`tit/server/routes/viewers.py`, ~110 lines removed) along with their contract paths; no route
   submits a `"viewer"` job any more (`tit/jobs/kinds.py`'s `"viewer"` kind and
   `VIEWER_PROGRAMS` are now dead code -- **not removed here**, out of this lane's owned paths;
   flagged for whichever lane owns `tit/jobs/kinds.py`). `GET /api/view/{kind}` and
   `POST /api/view/args` (still not declared in the contract, per this file's existing practice)
   are unaffected and need no X11/capability check any more -- the ViewSpec/scene is built
   unconditionally. `ViewSpec.freeview_args` is kept for one release, marked deprecated in both
   the Pydantic field description and this contract.
3. **`Capabilities` drops `freesurfer`/`x11_display`/`gmsh`/`freeview`**, adds
   `tetravox_embed: {available, version, protocol}` (read from
   `<tetravox_embed_dir>/manifest.json`, `available=False` on any failure -- no directory, no
   manifest, malformed JSON) and `fastsurfer: bool` (`FASTSURFER_HOME` or `/opt/fastsurfer` has
   `run_fastsurfer.sh`). Changed identically in `contracts/openapi.v0.yaml` (not just v1) since
   the live runtime genuinely no longer has the fields the walking-skeleton contract used to
   require -- v0's own header commits to tracking "the real server's `--dump-openapi` output",
   not a frozen Phase-0 shape.
4. **New static route `/tetravox/{path}`** (`tit/server/static.py`, not itself in the
   OpenAPI contract, same as `/`): serves `ServerSettings.tetravox_embed_dir` (env
   `TIT_TETRAVOX_EMBED_DIR`, CLI `--tetravox-dir`, default `/opt/tetravox/embed`) with its own
   CSP (`TETRAVOX_CSP`: `script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; ...`) on
   every response under the prefix, correct MIME per extension (`.wasm` already registered
   `application/wasm`), `index.html` for `/tetravox` and `/tetravox/`, a path jail, and a 404
   (not a SPA fallback) for both a missing embed directory and an unknown asset inside an
   installed one. `"tetravox"` added to `RESERVED_PREFIXES` so the path can never fall through to
   the main UI bundle's SPA route even when both are installed. The app's own `CSP_HEADER` in
   `tit/server/app.py` **drops** `'wasm-unsafe-eval'` now that the embed carries its own -- no
   code in the app's own origin needs it any more.
5. **Contract-check status (`dev/contracts_check.py`)**: `openapi.v0.yaml` — clean (10
   operations, 9 schemas). `openapi.v1.yaml` — 49 pre-existing problems against a live
   `--dump-openapi`, **none of which touch anything this lane owns** (verified by grepping the
   output for `capabilit|viewspec|viewer|scene|tetravox`: only 6 hits, all `JobKind` enum
   members inherited from `PlanJob`/`LockConflict`/`PlanResult` schemas that are themselves
   entirely absent from the dump -- a pre-existing gap this repo has flagged before, e.g. this
   file's 2026-08-27 B2 entry). Same 88-schema, same-count dump whether generated in-process
   (`create_app(settings).openapi()`) or via a real `simnibs_python -m tit.server
   --dump-openapi` subprocess -- ruling out an artifact of how the dump was produced.
- **Real data through `sub-ernie`, Dataset 000** (host pytest against real fixtures, not the
  container -- the container run mirrors it): `GET /api/view/simulation?subject=ernie&
  simulation=L_Insula` produces a schema-valid `scene.datasets[].path` of
  `/api/files/raw/<abs path>` for every layer, a hidden grey-matter TI mesh layer with
  `field.name == "TI_max"` and `clip.planes[0].followCursor == true`.
- `python3 -m pytest -q tests/` (host, py3.14): **3140 passed, 18 skipped**; the only 2 failures
  (`test_process_filter_matches_qt_list`, `test_plan_pre_builds_full_dag_for_two_subjects`) are
  pre-existing drift from concurrent lanes' in-progress edits to files this lane does not own
  (`tit/server/routes/system.py`'s `RELEVANT_KEYWORDS` lagging `tit/gui/system_monitor_tab.py`'s
  freesurfer→fastsurfer rename; `tit/jobs/plans.py`'s new `G2b` FastSurfer DAG stage) --
  reproduced identically inside `tit-v3-spike` (212 passed / 1 failed on the narrower file set).
- `python3 -m black --check` on every touched Python file: clean.
- `cd desktop && npx vitest run tests/mock-server`: **21 passed** (4 new: `/tetravox/*`
  index/CSP/manifest/404-not-SPA-fallback, against the new deterministic fake-embed fixture at
  `desktop/tests/e2e/fixtures/fake-embed/`). `npm run gen:api` regenerated
  `src/renderer/api/schema.d.ts` from the rebuilt `contracts/openapi.v1.json`.
  `npm run typecheck`'s `tsconfig.node.json` half is clean; its `tsconfig.web.json` half now
  fails in 5 files this lane does not own
  (`src/renderer/pages/{analyzer,optimizer-flex,results,viewer}/api.ts`,
  `src/renderer/pages/viewer/index.tsx`) that still reference the removed
  `/api/viewers/{freeview,gmsh}` paths and `capabilities.{freeview,gmsh,x11_display}` --
  expected fallout of this contract change, reported to whichever lane owns
  `desktop/src/renderer/**` for Phase C integration rather than fixed here.
- `python3 -m black` on every touched Python file: clean.

## 2026-09-03 — Lane R (reconciliation) — `PreprocessConfig` field rename lands in the contract; `has_fastsurfer`; `JobKind` drops `viewer`

Closes the Phase-A cross-lane needs lists (W3a/W3b/W4 notes) that touch `contracts/**`: the
dataclass side of each of these changes had already landed in `tit/pre/config.py` (W3b) and
`tit/jobs/spec.py`/`kinds.py` (this lane); this entry is the contract catching up.

1. **`PreprocessConfig`** (`contracts/schema.json`, regenerated inside `tit-v3-spike` via
   `dev/build_schema.py`, 62 `$defs`): `run_recon`/`parallel_recon`/`parallel_cores` are gone,
   replaced by `run_fastsurfer: bool` (default `false`) and `fastsurfer_threads: int | null`;
   `run_subcortical_segmentations` is gone with no replacement (D2 -- the MATLAB-runtime
   thalamic/hippocampal subfield stages are not coming back). `openapi.v1.json` picks this up
   automatically through the existing `x-tit-config: PreprocessConfig` merge in
   `dev/build_contract.py` -- no manual edit to `openapi.v1.yaml`'s placeholder entry was needed.
2. **`Subject.has_fastsurfer: boolean`** (required) added to both `openapi.v0.yaml` and
   `openapi.v1.yaml`, and to the Pydantic `Subject` model in `tit/server/schemas.py`. This closes
   a real (not just contract-drift) bug: `tit.catalog.list_subjects()`/`subject_detail()` had
   already started returning a `has_fastsurfer` key (W3b), but `GET /api/catalog/subjects`
   (`tit/server/routes/catalog.py`) builds its response through the `SubjectList`/`Subject`
   Pydantic models, which silently dropped any key the model didn't declare -- so the field
   was present in `subject_detail` (a plain-dict v1 route) but invisible on the v0
   `SubjectList` endpoint until this fix. `SubjectDetail` (`allOf: [Subject, ...]`) inherits the
   field automatically, no separate edit needed there.
3. **`JobKind` drops `"viewer"`** (`PlanJob.kind`/`LockConflict.kind` inherit it via `$ref`, so
   one enum edit covers all three) -- nothing has submitted a `"viewer"` job since W3a deleted
   the `/api/viewers/{freeview,gmsh}` launch routes; `tit/jobs/kinds.py`'s `"viewer"` branch and
   `VIEWER_PROGRAMS` constant, and the matching branch in `tit/server/routes/jobs.py` (a
   403 pointing at those now-deleted routes) are deleted; `tit/jobs/spec.py`'s
   `JOB_KINDS`/`CONTRACT_JOB_KINDS` and `tit/jobs/costs.py`'s `DEFAULT_COSTS` lose the entry.
   `tit/jobs/scheduler.py`'s `job.kind != "viewer"` budget bypass and `tit/jobs/locks.py`'s
   fall-through are both left as-is (unowned by this lane, and already correctly tolerant): a
   `spec.json`/`status.json` written before this change with `kind: "viewer"` still loads and
   costs without raising (`JobSpec.kind`/`JobStatus.kind` are plain, unvalidated `str` fields on
   read) -- exercised directly by
   `tests/test_jobs_registry.py::test_registry_reads_legacy_viewer_kind_job_without_crashing`.
4. `contracts/openapi.v0.yaml`'s `Subject` schema also gained `has_fastsurfer` even though
   nothing in W3a's entry above touched v0's job/viewer schemas -- consistent with this file's
   existing practice (see the 2026-09-03 W3a entry) that v0 tracks the live runtime's actual
   surface rather than a frozen Phase-0 shape.

**Gates**: host `python3 -m pytest -q` -- 3149 passed, 18 skipped, 0 failed. Container
(`tit-v3-spike`) full suite -- 3160 passed, 7 skipped, 0 failed (7 more collected than host: 5
GUI-import tests real PyQt5 makes runnable instead of skipped, `test_docker_engine.py`'s root-only
skip, `test_pre_fastsurfer.py`'s `FASTSURFER_HOME` skip). `dev/contracts_check.py`: v0.yaml clean
(10 operations, 9 schemas); v1.yaml -- 49 problems, byte-identical count to the pre-existing
structural gap the 2026-09-03 W3a entry already documented (most route modules return
`dict[str, Any]` rather than a typed `response_model`), reverified by grepping this run's own
output for `capabilit|viewspec|viewer|scene|tetravox|fastsurfer`: zero hits. `black --check` on
every file this lane touched: clean. `cd desktop && npm run gen:api` regenerated
`schema.d.ts`; `tsconfig.node.json` half of typecheck clean, `tsconfig.web.json` half has 4
pre-existing errors in 2 files this lane does not own (`src/renderer/app/jobs-rail/api.ts:47`
still literals `kind: "viewer"`; `src/renderer/pages/preprocess/index.tsx` still reads/writes
`run_recon`/`parallel_recon`/`parallel_cores`/`run_subcortical_segmentations`) plus their 2 test
files (`tests/unit/preprocess-defaults.test.ts`, `tests/unit/shell-subject.test.tsx`) -- the same
kind of expected, reported-not-fixed fallout the W3a entry above already established the pattern
for. `npx vitest run` -- 465 passed, 4 failed, all four in the same two unowned preprocess-fallout
files. `npm run build` -- clean.


## 2026-09-04 — lane U (dynamic embed delivery, `dev/notes/v3-embed-convergence-plan.md` E1-E4)

Additive only: every change below is a new path or a new optional-in-practice property, and a
client that ignores all of it behaves exactly as before.

1. **`Capabilities.tetravox_embed` gains `source`, `features`, `compatible` and `supported`.**
   It now describes the **active** bundle, resolved the way `/tetravox/` resolves it (dev
   override → pinned/newest installed → baked into the image) rather than always the baked
   directory. This is E1's core: a host asks whether the embed has a *named feature*
   (`markers`, `pick`, `camera`) instead of comparing versions, so an additive Tetravox release
   needs no TI-Toolbox change. `supported` is always present — it is a property of the build, not
   of whatever happens to be installed — and `source` is `null` only when no bundle is available.
2. **Five new paths under `/api/tetravox`** (tag `tetravox`): `GET /api/tetravox` (active +
   installed + baked + supported range), `GET /api/tetravox/updates` (release index; answers 200
   with `available: false` and a sentence when it cannot be reached, because an air-gapped
   install is a supported state), `POST /api/tetravox/install` (`{url, sha256}` or `{version}`),
   `POST /api/tetravox/activate` (`{version}`, or `"baked"` to roll back) and
   `DELETE /api/tetravox/{version}`. Every one answers with the same `TetravoxState`, so a client
   never re-reads to learn what happened.
3. **New schemas**: `ProtocolRange`, `TetravoxRelease`, `TetravoxState`, `TetravoxUpdate`,
   `TetravoxUpdates`. The two request bodies are declared inline rather than as named components,
   because the routes take `dict[str, Any]` like every other body-taking route here and there is
   no server-side model for the dump to name.

**Gates**: host `python3 -m pytest -q` — 3587 passed, 32 skipped, 0 failed (68 new tests:
`tests/test_tetravox_{protocol,store,install,routes}.py`). `dev/contracts_check.py
contracts/openapi.v1.json <dump>` — 187 problems, **byte-identical to the count with the
tetravox paths and properties stripped out of the contract** (measured both ways this session),
i.e. this lane adds zero drift; grepping this run's output for `tetravox` gives zero hits.
`desktop`: `npm run typecheck` clean, `npm run lint` 0 errors (3 pre-existing warnings),
`npx vitest run` — the mock-server contract test drives all five new operations end to end.

## 2026-09-05 — OV (overview) — one bounded `GET /api/catalog/overview` replaces the Subjects fan-out

Additive only: one new path and seven new schemas. Every existing path, schema and property is
unchanged, so a client that ignores all of it behaves exactly as before.

1. **New path `GET /api/catalog/overview`** (tag `catalog`), answering `Overview`. It is the
   project Overview page's *single* read (`desktop/IMPLEMENTATION_PLAN.md` R1): the page it serves
   replaced Subjects, and with it a request fan-out of one `/api/catalog/subjects/{id}` per subject
   plus five output lists per subject plus one `/api/catalog/analyses` per simulation. That
   fan-out was capped in the renderer at 25 subjects, so a larger project silently rendered **no**
   output counts at all. This response owns the display facts instead, and its request count does
   not grow with subjects, simulations or outputs. Detailed output discovery stays lazy and stays
   in Results — the overview carries counts, never trees or previews.
2. **New schemas**: `PresenceState`, `OverviewCounts`, `OverviewReadiness`, `OverviewSubject`,
   `OverviewCoverage`, `OverviewTotals`, `Overview`. `PresenceState` is the point of the change:
   `present` / `absent` / `partial` / `pending` / `failed` are five distinguishable answers where
   the `Subject` booleans had two. `partial` is real (raw staged under `sourcedata/` but never
   converted; some but not all of a subject's EEG nets have a leadfield); `pending` and `failed`
   come from the job scheduler's own records for the job kind that would produce that artefact,
   and only ever apply to an artefact that is still absent — what is on disk always wins.
3. **`GET /api/catalog/subject-info` is untouched** and stays in the contract. The Subject Info
   *page* is deleted in the desktop app, but removing the endpoint is a breaking change and is
   left to the API's next versioned cleanup.

**Gates**: `python3 -m pytest tests/test_server_overview.py -q` — 10 passed.
`python3 dev/route_import_guard.py` — 19 route modules clean, `tit.server.routes.overview` at
18.6 ms against the 400 ms budget. `python3 dev/build_contract.py` regenerated
`contracts/openapi.v1.json` from the YAML; `pnpm run gen:api` regenerated
`desktop/src/renderer/api/schema.d.ts`.

## 2026-09-05 — BX (batch) — `JobGroupRequest` generalized beyond preprocessing

Additive only, in one schema. No dataclass changed, so `contracts/schema.json` is untouched. A
client that keeps sending exactly what it sent before (`kind: "pre"`, `config`, `subject_ids`,
`parallel_subjects`) behaves identically.

1. **`JobGroupRequest.kind`** widens from `enum: [pre]` to
   `[pre, sim, flex, flex_adaptive, flex_pareto, ex, mex]` — every kind that runs one independent
   job per subject (`desktop/IMPLEMENTATION_PLAN.md` R3). `pre` still expands into
   `tit.jobs.plans.plan_preprocessing`'s per-subject G1–G6/report DAG; the new kinds expand into
   one job per `(subject, config)` entry via the new `tit.jobs.plans.plan_per_subject`. Cohort
   kinds are deliberately *not* in the enum: a grouped `analyzer` run is one job over the whole
   selection and has no per-subject concurrency, so it stays on `POST /api/jobs` (the route
   answers 422 for `analyzer`, and a test pins that).
2. **New optional `JobGroupRequest.subject_configs`**: `[{subject_id, config}]`. A workflow whose
   config depends on the subject (an ROI resolved against that subject's own atlas, a
   subject-specific leadfield path) or that runs several jobs for one subject (the Simulator's one
   job per `(subject, montage)`) sends one entry per job instead of one template. Entries are
   matched to `subject_ids` by `subject_id`; a subject with no entry uses `config`; an entry
   naming a subject outside `subject_ids` is a 422. Whatever the caller sends, the server forces
   each generated config's `subject_id` to its own subject, so a generated config can never carry
   another subject's id.
3. **New optional `JobGroupRequest.tags` and `JobGroupRequest.overwrite`**: the two remaining
   fields the pages' previous per-job `POST /api/jobs` loops passed, so a group submission is a
   drop-in replacement for the loop. `overwrite` is ignored for `kind: "pre"`, which carries the
   same policy inside its config's `skip_existing_outputs` / `replace_existing_outputs`.
4. **`parallel_subjects` is unchanged in shape and meaning** and is now the *only* concurrency
   mechanism for these kinds: the whole group is created queued in one request and
   `tit.jobs.scheduler.evaluate` releases it `parallel_subjects`-at-a-time. The renderer no longer
   spaces out POSTs to imitate sequential or parallel execution.

**Gates**: `python3 -m pytest tests/test_jobs_routes.py tests/test_jobs_model.py -q` — 24 + 56
passed, including a cap-1 run that never has two members `running` and a cap-2 run that reaches
two. `python3 dev/build_contract.py` regenerated `contracts/openapi.v1.json` from the YAML;
`pnpm run gen:api` regenerated `desktop/src/renderer/api/schema.d.ts`.

## 2026-09-05 — `/api/guide/*`, the fixed guide scene (additive; lane GD, plan R4)

Five new read-only paths under a new `guide` tag. Nothing existing changed: `/api/scene/*` keeps
its subject parameter, its cache states and its 202s, and is still what a *subject's* pane would
use.

1. **`GET /api/guide/manifest`** — every part, net and atlas of the packaged guide, in the same
   shape `/api/scene/manifest` uses (`parts[]`, `nets[]`, `atlases[]`, `bbox`, `focus_bbox`), so
   one desktop component consumes either. It takes no `subject`, answers with no project bound,
   and never answers 202: the assets ship with the installation.
2. **`GET /api/guide/surface?part=&format=`**, **`GET /api/guide/labels?atlas=&format=`** — the
   packaged TVSC1/GIfTI bytes. `ETag` is the file's SHA-256 and `Cache-Control` is
   `max-age=31536000, immutable`, because these bytes cannot change without the installation
   changing (a subject's surface legitimately changes after a charm re-run, which is why that one
   is `must-revalidate`).
3. **`GET /api/guide/regions?atlas=`**, **`GET /api/guide/electrodes?net=`** — the atlas legend and
   one net's electrode names/positions, the same rows the scene routes answer with.
4. **`space` is `guide-ras`, and it is a frozen enum** — deliberately *not* `subject-ras`. The
   millimetres belong to the guide head; a client that wrote one into a research subject's config
   would produce a coordinate no downstream validation could catch (plan R4). The desktop pane
   keys "click-to-config is disabled here" off this value rather than off a comment.
5. **`volumes` is always empty.** The guide packages no label volume: region picking happens on
   the atlas payloads, on the surface the pane already draws.

**Gates**: `python3 dev/build_contract.py` regenerated `contracts/openapi.v1.json`; `pnpm run
gen:api` regenerated `desktop/src/renderer/api/schema.d.ts`; `python3 dev/route_import_guard.py`
clean on all 20 route modules; `python3 -m pytest tests/test_scene_guide.py tests/test_guide_routes.py -q`.

## 2026-09-05 — VW (viewer) — optional `atlas` on `GET /api/view/{kind}` (plan R5)

One new optional query parameter, on one existing path. Nothing else in the document moves, no
schema gains or loses a property, and a client that never sends it gets byte-for-byte the response
it got before.

1. **`GET /api/view/{kind}` gains `atlas` (query, optional, string).** It names which atlas overlay
   the scene should carry: an id from `GET /api/catalog/atlases` for the same subject and space
   (a display name such as `DK40` or `aparc.DKTatlas+aseg` in subject space), or a bundled MNI
   atlas's basename in MNI/group mode. `tit.viewspec.build_view` honours it in the `subject` and
   `group` branches, which are the two that build an atlas layer at all.

   **Absent preserves the current behaviour exactly** — that is the compatibility claim and it is
   asserted directly (`tests/test_viewspec.py::test_atlas_absent_keeps_the_servers_own_choice`
   compares the whole spec built with `atlas=None` against the spec built without the argument).
   The server's own choice is unchanged: `segmentation/labeling.nii.gz` when the head model has
   one, else the first atlas `VoxelAtlasManager` lists; `DEFAULT_MNI_ATLAS` in MNI.

   **An unknown id falls back to that same server choice rather than 404.** A view request is a
   request for a picture of an anatomy, and an atlas a subject no longer has is a stale bookmark,
   not a reason to answer with no picture at all. The alternative — refusing the whole scene
   because one overlay could not be resolved — turns a project moved between images into a viewer
   that will not open.

**Gates**: `python3 -m pytest tests/test_viewspec.py -q` — 36 passed (5 new).
`python3 -m pytest tests/ -q -k "viewspec or view or catalog_v1"` — 147 passed.
`python3 dev/build_contract.py` + `pnpm run gen:api` regenerated `contracts/openapi.v1.json` and
`desktop/src/renderer/api/schema.d.ts`; the parameter appears in both.

## 2026-09-05 — lane AU — automatic Tetravox embed updates (additive)

No dataclass changes, so `contracts/schema.json` is untouched. Plan of record:
`dev/notes/v3-tetravox-selection-pipeline-plan.md` §1-A (A2–A5).

1. **New path `POST /api/tetravox/policy`** — `{auto_update: boolean}` → the same
   `TetravoxState` every other tetravox write answers with. This is the only switch for
   A3's background check; the policy is persisted in `<install root>/policy.json`, not in
   `code/ti-toolbox/config/settings.json`, because it is a property of the *install root*
   (which may be a shared user-config mount) rather than of the project the server is bound to.
2. **New query parameter `refresh` on `GET /api/tetravox/updates`** (default `false`).
   Reading the route now answers from the cache the background check writes; `refresh=true`
   is what "Check now" sends. GitHub allows 60 unauthenticated requests per hour per IP, so
   a page that re-rendered on every mount would spend the budget on nothing.
3. **`TetravoxState.auto_update`** (required, boolean) and **`TetravoxUpdates.auto_update`,
   `.checked_at`, `.from_cache`, `.last_outcome`** (all optional) — what Settings needs to say
   *when* it last looked, *what* happened, and whether the answer is cached.
4. **New component `TetravoxUpdateOutcome`** — `{action, message, version?, protocol?, at?}` with
   `action ∈ {installed, available, current, unsupported, failed}`. `unsupported` is the one
   A1 exists for: a release whose embed protocol is past this build's supported range is
   *reported* as needing a TI-Toolbox update and is never installed.
5. **New WebSocket path `/ws/tetravox`** (hand-added to the dump in `tit/server/app.py`, as
   `/ws/system` and `/ws/jobs` already are): one message type, `{"type": "tetravox.updated",
   version, protocol, message}`, published after the policy has installed and activated a
   bundle. **`contracts/events.schema.json` is deliberately unchanged** — that file describes
   one line of a job's `events.jsonl`, and adding an app-level type to it would have made every
   job-event reader accept a type no job can emit.

Also in this entry, not a contract change: the release index moved from a `releases.json`
committed to the Tetravox repo (which never existed — it answered 404 for the whole of lane U's
live run) to the GitHub Releases API, so `index_url` now reports
`https://api.github.com/repos/idossha/tetravox/releases` unless `TIT_TETRAVOX_RELEASE_INDEX`
overrides it. That env override now accepts either that JSON shape or the flat index.

Regenerated: `contracts/openapi.v1.json` (`python3 dev/build_contract.py`),
`desktop/src/renderer/api/schema.d.ts` (`pnpm run gen:api`).

## 2026-09-05 — feat:pipeline-canvas — `/api/pipelines*` and the pipeline document (lane PC)

No dataclass changes, so `contracts/schema.json` is untouched by this entry. All of it is
**additive**: six new paths and eleven new component schemas; no existing path, schema or enum
was edited, so every v1 client keeps working unchanged.

1. **New standalone schema `contracts/pipeline.schema.json`** (JSON Schema 2020-12,
   `version: 1`) — the pipeline canvas document: `nodes[{id, kind, config, label?, position?}]`
   and `edges[{from, to, port}]`. It is the file saved under
   `<project>/code/ti-toolbox/pipelines/<name>.json` and the object carried in an exported
   notebook's `metadata.ti_toolbox.pipeline`. `kind` is an existing `tit.jobs.spec.JOB_KINDS`
   value (`pre`, `leadfield`, `flex`, `ex`, `mex`, `sim`, `analyzer`, `source`, `stats`) — the
   pipeline introduces **no new job kind**, asserted by
   `tests/test_pipeline_graph.py::test_every_node_kind_is_a_real_job_kind`. `port` is one of
   `subjects | montages | simulation | roi | leadfield`. Implemented by
   `tit/pipeline/document.py`; the same shapes are mirrored into `openapi.v1.yaml` as
   `Pipeline`/`PipelineNode`/`PipelineEdge` (item 3) so the generated TypeScript has them.

2. **New paths** (`openapi.v1.yaml`, tag `pipelines`):
   `GET /api/pipelines` (saved documents), `GET /api/pipelines/kinds` (the palette: each kind's
   typed ports, so the canvas never keeps its own copy), `POST /api/pipelines/validate`,
   `POST /api/pipelines/run`, `POST /api/pipelines/export?format=ipynb`, and
   `GET|PUT|DELETE /api/pipelines/{name}`.

   `POST /api/pipelines/run` returns a `PipelineRunResult` — **one** `group_id` for the whole
   canvas, because running a pipeline is exactly one `tit.jobs.manager.JobManager.submit_plan`
   call with `after_labels` taken from the document's edges (the same mechanism the `pre` G1–G6
   DAG already uses). There is no pipeline executor: the scheduler stays the only one.

3. **New component schemas**: `Pipeline`, `PipelineNode`, `PipelineEdge`, `PipelineRequest`,
   `PipelineRunRequest`, `PipelineRunResult`, `PipelineValidation`, `PipelineIssue`,
   `PipelineJobPreview`, `PipelineListEntry`, `PipelineKinds`. `PipelineNode.config` reuses the
   existing `PipelineConfig` placeholder, so a node's config is validated by exactly the same
   `tit.config_io` machinery `POST /api/jobs` uses (`tit/pipeline/plan.py::_round_trip`).

   `PipelineValidation` is deliberately a 200 with `ok: false` plus one `PipelineIssue` per
   problem (a cycle, an incompatible port, an unbound required input), each a sentence the canvas
   shows next to the node or wire. A 422 means the body is not a pipeline document at all.

4. **Regenerated** `contracts/openapi.v1.json` (`python3 dev/build_contract.py`) and
   `desktop/src/renderer/api/schema.d.ts` (`pnpm run gen:api`).

## 2026-09-06 — feat:external-viewer — `POST /api/view/open` lands; the whole `tetravox` section goes

Plan of record: `dev/notes/v3-native-panes-external-viewer-plan.md`, decisions V1-V4.
No dataclass changes, so `contracts/schema.json` is untouched; `openapi.v1.yaml` was
edited and `openapi.v1.json` / `desktop/src/renderer/api/schema.d.ts` regenerated with
`python3 dev/build_contract.py` and `pnpm run gen:api`.

**This entry is a removal, and a breaking one.** The in-app Tetravox *embed* is retired.
Viewing is now the Tetravox **desktop app**, installed on the host, which signs, notarises
and updates itself. A container with no display could never have run it; an embed baked into
an image tied a viewer release to a toolbox release, which is exactly what the previous
entry's dynamic-delivery machinery existed to undo — by adding five routes, four schemas,
a WebSocket and an installer instead of removing the coupling's cause.

1. **Added: `POST /api/view/open`** → `ViewerOpen` (`{name, path, host_path, scene}`).
   Builds exactly the ViewSpec `GET /api/view/{kind}` would build for the same selection,
   rewrites every dataset and sidecar `path`/`absPath` from an `/api/files/raw/…` URL to the
   **host's** own absolute path, and writes it to
   `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`. `host_path` is `null` when this
   server cannot know its project's host root (`tit/server/host_path.py`), which the client
   renders as "download the file" rather than "launch". One file per view kind, overwritten,
   so the directory does not grow inside the user's project.
2. **Removed: the whole `tetravox` tag** — `GET /api/tetravox`, `GET /api/tetravox/updates`,
   `POST /api/tetravox/{policy,install,activate}`, `DELETE /api/tetravox/{version}` — and the
   schemas `TetravoxRelease`, `TetravoxState`, `TetravoxUpdate`, `TetravoxUpdates`,
   `TetravoxUpdateOutcome`, `ProtocolRange`.
3. **Removed: `/ws/tetravox`** and its one `tetravox.updated` event.
4. **Breaking: `Capabilities.tetravox_embed` is gone**, and with it that key from
   `required`. A capability is what *this runtime* can do; whether a desktop application is
   installed on the user's machine is a fact about the host, answered by the Electron shell
   (`window.tit.viewer.probe`), not by an HTTP route. `contracts/openapi.v0.yaml`'s own
   `Capabilities` was updated in the same commit, since `test_openapi_covers_v0_contract`
   checks the live dump against it.
5. **Relaxed: `contracts/tetravox-viewspec-v2.schema.json`'s `DatasetRef.path`/`absPath`**
   no longer require the `^/api/files/raw/` prefix. That pattern was our own addition, not
   the engine's: a ViewSpec dataset path is a path, and the desktop app opens files rather
   than fetching URLs. The pattern now accepts the URL form, a POSIX absolute path or a
   Windows drive path, and still rejects a bare relative name — the app would resolve one
   beside the scene file, which is not where the data is.

## 2026-09-06 — feat:pipeline-canvas — `PipelineIssue.code` / `.port`

No dataclass changes, so `contracts/schema.json` is untouched.
`contracts/openapi.v1.yaml` / `.json` and `desktop/src/renderer/api/schema.d.ts`
gain two **optional** properties on `PipelineIssue`; every existing reader keeps
working, because `level` and `message` are unchanged and still the only required
fields.

1. **`PipelineIssue.code`** — the stable machine-readable name of the finding,
   one of `empty · duplicate_id · edge_unknown_node · self_edge · bad_output ·
   bad_input · double_bound · cycle · missing_input · unconfigured ·
   unconnected`, defined once in `tit.pipeline.validate.ISSUE_CODES`. The
   Pipeline canvas needs it to tell findings apart *without matching on English*.
   Before it existed the receipt printed every issue as an undifferentiated list,
   so an `unconnected` note ("… is not connected to anything; it will run on its
   own" — which is a legitimate graph, not a fault) read exactly like a blocker,
   and the maintainer's screenshot of the page is a pane of them. With the code,
   the canvas states the independent steps **once** ("3 steps run independently")
   and shows only real errors as errors.
2. **`PipelineIssue.port`** — for the port-shaped findings (`missing_input`,
   `bad_input`, `bad_output`, `double_bound`), which of the five port types the
   finding is about. This is what lets the canvas draw an unbound required input
   as a chip on the node's own card ("needs: subjects") and open that node's
   editor at that field, rather than re-deriving the same fact client-side from
   the config and risking a disagreement with the server that decides Run.

Mirrored in `desktop/tests/mock-server/server.mjs` (its planner is a deliberate
mirror of `tit/pipeline/*`), asserted in `tests/test_pipeline_validate.py` and
`desktop/tests/unit/pipeline-graph.test.ts`.

## 2026-09-06 — feat:viewer-composition — `POST /api/view/open` gains `extras`, `overrides`, `dry_run`; `ViewerOpen` gains `files`, `dry_run`

The Viewer page became a composition panel (VM,
`dev/notes/v3-native-panes-external-viewer/VM.md`), so the request that writes
the scene had to be able to carry what the panel composes. All three request
fields are **optional and additive**, and `tests/test_viewspec_overrides.py`
pins the guarantee that matters: with none of them given, the document this
endpoint returns and writes is *byte-identical* to what it produced before they
existed.

1. **`overrides`** — per-layer `{visible, opacity, colormap, showIn3D,
   showColorbar, contoursIn2D, threshold:{lo,hi}, colorMode, clip}` keyed by
   layer id, plus `layout` (`1x1 · 1+3 · 2x2 · 3d-only`), `camera`
   (`A·P·L·R·S·I`), `radiological` and `background`. Every knob is one the
   engine's own `ViewSpec` v2 type already has — the page exposes exactly what
   the server can write, because a control whose value does not reach the file
   is a lie. Values the type would not accept (an unknown layout, an opacity of
   4, a colour name we do not define) are dropped or clamped rather than
   written: a stale saved preset must not produce a scene the app refuses to
   open. `tit/viewspec.py::apply_scene_overrides`.
2. **`extras`** — `t1 · atlas · electrodes · gm_mesh`, the "Also open"
   checkboxes. Each reuses the layer builder the server already trusted for
   that file, and one the view already opens is a no-op rather than a second,
   differently-configured description of the same volume. There is deliberately
   **no electrode-*points* extra**: ViewSpec v2 has no points layer, so the
   page offers the electrode overlay *volume*, which exists.
3. **`dry_run`** — resolve and answer, write nothing. The preview strip needs
   to say what a selection resolves to without leaving a file behind, and
   reusing the real endpoint means the preview and the Open cannot disagree.
4. **`ViewerOpen.files`** (`ViewerSceneFile[]`) — one row per dataset the scene
   references, with its host-facing path and its size on disk. `bytes: null`
   where the file could not be stat'ed: "unknown" and "empty" are different
   answers and only one is a problem.

`contracts/tetravox-viewspec-v2.schema.json` is **unchanged** — nothing here
emits a field it did not already allow.

## 2026-09-06 — feat:pipeline-subjects-source — the cohort is a node, and a wire is gated on readiness

No dataclass changes, so `contracts/schema.json` is untouched. Three additions to
`contracts/openapi.v1.yaml` / `.json` (and `desktop/src/renderer/api/schema.d.ts`), plus
`contracts/pipeline.schema.json`.

1. **`PipelineNode.kind` gains `subjects`**, and it leads the enum. A `subjects` node names the
   cohort in `config.subject_ids`, runs nothing, and is the graph's only source. What it replaces:
   every processing node used to carry its own copy of the subject list *and* be auto-configured
   from the node upstream of it — so one cohort was typed once per node, two nodes in one graph
   could silently disagree about who was in the study, and an edge meant "and also copy that
   node's settings" rather than one named binding. An edge now carries the named port and nothing
   else.
2. **`PipelineKinds` gains `capabilities` and, per kind, `requires`/`produces`** — the readiness
   table from `tit.pipeline.validate.KIND_READINESS`. A wire is legal when the port types match
   **and** every subject reaching the target already has what that kind requires
   (`raw · m2m · leadfield · simulation`). `produces` is what makes a chain work:
   `pre` produces `m2m`, so `Subjects(raw) → Pre → Simulator` is legal while
   `Subjects(raw) → Simulator` is refused with "102, test have no head model".
   Served from the existing `GET /api/pipelines/kinds` rather than a second `/ports` route,
   because it is the same table and two endpoints for one fact is how they drift. The canvas needs
   it client-side to refuse a *drag* — there is no graph to ask the server about yet — while
   `POST /api/pipelines/validate` applies the same table server-side, so the drag-time refusal and
   the receipt are the same sentence.
3. **`PipelineIssue.code` gains `not_ready`** — the subjects reaching a node lack something it
   requires. Its `message` names them.

`POST /api/pipelines/validate` and `/run` now read subject readiness from the same aggregate the
Overview page shows (`GET /api/catalog/overview`), so the canvas and the board a user just looked
at cannot disagree. A project that cannot be read at all falls back to shape-only checking rather
than refusing every wire.

## 2026-09-06 — NB lane — notebooks and kernels: eleven paths, five schemas, one socket

No dataclass changes, so `contracts/schema.json` is untouched by this entry.
`contracts/openapi.v1.yaml` was hand-edited and `contracts/openapi.v1.json` /
`desktop/src/renderer/api/schema.d.ts` regenerated from it.

1. **`/api/notebooks` (GET, POST) and `/api/notebooks/{name}` (GET, PUT, DELETE)** —
   the `.ipynb` files under `<project>/code/ti-toolbox/notebooks`. New schemas
   `NotebookEntry`, `NotebookList`, `Notebook`. `Notebook.content` is a bare
   `object` with `additionalProperties: true` and stays that way: the `.ipynb`
   *is* the document, and typing its keys here would be this server deciding
   which parts of a format it does not own may survive a save. `POST` doubles as
   the import path — "Import .ipynb" in the UI and the pipeline canvas saving its
   export are the same call, a name and a document — so it declares a `409` for a
   name already taken.
2. **`/api/kernels` (GET, POST), `/api/kernels/{kernel_id}` (DELETE) and
   `/api/kernels/{kernel_id}/{interrupt,restart}` (POST)** — notebook execution
   lifecycle. New schemas `Kernel`, `KernelList`. `KernelList` carries `max` and
   `idleTimeoutSeconds` rather than leaving the client to hard-code them: the
   limits are the server's, and a page that renders "1 of 2 kernels" must be
   reading the server's number. `POST /api/kernels` declares `429`
   (`too-many-kernels`) and `501` (`no-jupyter-client` / `no-kernelspec`) because
   both are states a correctly-built container can be in.
3. **`WS /ws/kernels/{kernel_id}`** — one kernel's traffic; `execute` /
   `interrupt` / `restart` down, `ready` / `status` / `input` / `output` /
   `clear` / `reply` / `fatal` up. Declared in `app.py`'s `_custom_openapi`
   alongside `/ws/system` and `/ws/jobs` (FastAPI cannot describe a WS route) and
   exempt from `contracts_check` like the others. The message shape is SUNA's
   kernel-bridge protocol verbatim, and an `output` payload is an nbformat output
   verbatim — which is precisely why nothing translates between the live kernel
   and the file the `notebooks` paths above read and write.

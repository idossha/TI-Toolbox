# Lane R — Reconciliation of Phase-A cross-lane needs + full gate (2026-09-03)

Read first: `dev/notes/v3-docker-streamline-plan.md`, and the four Phase-A lane notes
(`w2-image-notes.md`, `w3a-server-notes.md`, `w3b-preprocessing-notes.md`,
`w4-desktop-docker-notes.md`). Every numbered item below is exactly one item from this lane's
brief; the exact diffs came from the originating lane's own notes (cited inline).

## Items closed

1. **`tit/server/routes/system.py::RELEVANT_KEYWORDS`** — `"freesurfer"`/`"recon-all"` →
   `"fastsurfer"`/`"run_fastsurfer.sh"`, `"pre/recon_all.py"` → `"pre/fastsurfer.py"` (exact diff
   from w3b-notes §4). Also fixed the test itself:
   `tests/test_server_skeleton.py::test_process_filter_matches_qt_list` asserted
   `is_relevant_process("", "/usr/local/freesurfer/bin/recon-all -s x")` — updated to the
   FastSurfer-era invocation.
2. **`tit/server/routes/plan.py`** — `_pre_stage_output_dir`'s `"G2b"` entry:
   `pm.freesurfer_subject(sid)` → `pm.fastsurfer_subject(sid)`. `plan()` now calls
   `tit.pre.config.migrate_legacy_keys(config_dict)` on the incoming `pre` config before
   `deserialize_config`, so `POST /api/plan/pre` from an old client sending `run_recon` maps
   onto `run_fastsurfer` (and plans `G2b`) instead of silently dropping the key. New tests:
   `test_plan_pre_g2b_output_dir_is_fastsurfer_not_freesurfer`,
   `test_plan_pre_accepts_legacy_run_recon_key` (`tests/test_plan_routes.py`).
3. **`tit/viewspec.py`** — `_subject_atlas_layer`'s `VoxelAtlasManager(...)` call now also passes
   `fastsurfer_mri_dir=pm.fastsurfer_mri(sid)` (FastSurfer searched before legacy FreeSurfer, per
   `VoxelAtlasManager.list_atlases`'s own order). `mni_resources_dir` is now imported from
   `tit.atlas.constants` (where W3b re-homed it after this module's own rewrite dropped it —
   w3b-notes §5 item 6 asked W3a to make exactly this import) instead of a second local
   definition; the local `Path`/`os.path.isdir` copy is deleted. New test:
   `test_subject_atlas_layer_prefers_fastsurfer_over_freesurfer` — a fresh project with atlas
   files in *both* mri dirs, asserting the FastSurfer one resolves
   (`tests/test_viewspec.py`).
4. **`contracts/**` regeneration** — `contracts/schema.json` rebuilt inside `tit-v3-spike`
   (`simnibs_python dev/build_schema.py`, 62 `$defs`; `PreprocessConfig` now carries
   `run_fastsurfer`/`fastsurfer_threads`, not `run_recon`/`parallel_recon`/`parallel_cores`/
   `run_subcortical_segmentations`); `contracts/openapi.v1.json` rebuilt via
   `python3 dev/build_contract.py` (the `x-tit-config: PreprocessConfig` merge picks the new
   fields up automatically). `Subject.has_fastsurfer: boolean` (required) added by hand to both
   `openapi.v0.yaml` and `openapi.v1.yaml`, **and** to the Pydantic `Subject` model in
   `tit/server/schemas.py` — this closes a real bug, not just contract drift:
   `tit.catalog.list_subjects()` already returned a `has_fastsurfer` key (W3b), but
   `GET /api/catalog/subjects` builds its response through `SubjectList`/`Subject`, which was
   silently dropping any key the Pydantic model didn't declare. `SubjectDetail` (`allOf`) inherits
   the field with no separate edit. `SubjectInfoMatrix`/`subject_info_matrix` columns were
   already correct in `tit/catalog.py` (W3b) and ride through the generic `TableData` schema —
   nothing to change in the contract for that one. `capabilities.fastsurfer` was already present
   (W3a) — verified, not re-added. `desktop/src/renderer/api/schema.d.ts` regenerated via
   `npm run gen:api`. Fixture updates: `desktop/tests/fixtures/subjects.json` gained
   `has_fastsurfer` per subject; `desktop/tests/mock-server/server.mjs`'s
   `PRE_STAGE_FLAGS`/`planPreprocessingStages` now use `run_fastsurfer` instead of
   `run_recon`/`run_subcortical_segmentations`. `desktop/tests/fixtures/openapi.v1.json` needed no
   manual refresh — `contract.test.ts`'s own `beforeAll` regenerates it from
   `contracts/openapi.v1.yaml` on every run. Full diff to `contracts/SCHEMA-CHANGES.md`'s own new
   2026-09-03 "Lane R" entry.
5. **`tit/jobs/kinds.py`** — the `"viewer"` branch and `VIEWER_PROGRAMS` constant deleted. Since
   the enum lives on the wire contract (`JobKind`, referenced by `PlanJob.kind`/
   `LockConflict.kind`), the brief's "remove … from the enum(s)" also meant
   `tit/jobs/spec.py`'s `JOB_KINDS`/`CONTRACT_JOB_KINDS` (both lost the `"viewer"` member) and
   `contracts/openapi.v1.yaml`'s `JobKind` enum — flagged in w3b-notes §5 as "not W3b's grant" and
   explicitly left for whoever lands the viewer removal; that's this lane. Also removed:
   `tit/jobs/costs.py`'s `"viewer": Cost(cpus=0, mem_gb=0)` entry (falls back to `_FALLBACK`, no
   crash — `default_cost` was already a `.get(kind, _FALLBACK)` lookup); the dead
   `if kind == "viewer": raise 403 ...` branch in `tit/server/routes/jobs.py::submit_job` (it
   pointed at `POST /api/viewers/{freeview,gmsh}`, which W3a already deleted, and was unreachable
   anyway once `"viewer"` left `JOB_KINDS` — the generic `if kind not in JOB_KINDS: 422` above it
   catches it first). **Left alone, deliberately**: `tit/jobs/scheduler.py`'s
   `job.kind != "viewer"` budget bypass and `tit/jobs/locks.py`'s fall-through-to-`[]` — both are
   outside this lane's owned paths, and both are already correct legacy tolerance rather than
   something needing a fix. Verified the actual tolerance claim: `JobSpec.kind`/`JobStatus.kind`
   are plain unvalidated `str` fields on `from_dict` (no enum check on load), so a
   `spec.json`/`status.json` written before this change with `kind: "viewer"` still loads,
   costs, and lists without raising — new test
   `tests/test_jobs_registry.py::test_registry_reads_legacy_viewer_kind_job_without_crashing`
   exercises exactly that round trip. Updated tests: `tests/test_jobs_model.py` (renamed/reworked
   `test_command_for_viewer` → `test_command_for_legacy_viewer_kind_raises_clear_error`; added
   `test_default_cost_legacy_viewer_kind_falls_back_without_crashing`),
   `tests/test_jobs_scheduler.py::test_legacy_viewer_kind_never_waits_on_budget` (renamed +
   comment, behavior unchanged since scheduler.py itself wasn't touched),
   `tests/test_jobs_routes.py::test_submit_rejects_legacy_viewer_kind` (renamed; now asserts 422
   not 403, matching the deleted special case).
6. **`tit/analyzer/analyzer.py::_resolve_voxel_atlas`** (~line 1133) — exact diff from w3b-notes
   §4: now searches `pm.fastsurfer_mri(sid)` (and every filename variant) before
   `pm.freesurfer_mri(sid)`'s legacy equivalents, and the seg dir. Error message names all three
   dirs. New tests in `tests/test_analyzer_full.py::TestResolveVoxelAtlas`:
   `test_prefers_fastsurfer_over_legacy_freesurfer` (same-named atlas in both dirs → FastSurfer's
   wins), `test_falls_back_to_legacy_freesurfer_when_fastsurfer_lacks_it` (a legacy-only name like
   `ThalamicNuclei.v13.T1.mgz` still resolves).
7. **`tit/gui/nifti_viewer_tab.py`** — `launch_freeview_with_files`/`terminate_freeview` (and the
   `self.freeview_process` field, the `closeEvent` override that only existed to call
   `terminate_freeview`, the `subprocess` import) are deleted. The three call sites
   (`load_subject_data`, `load_group_data`, `load_custom_nifti`) now call a new
   `_notice_viewing_moved(file_specs, file_paths=None)`, which keeps the same file-discovery/
   validation logic (all of `_load_analysis_overlay`, `_load_electrode_overlay`,
   `create_electrode_overlay`, atlas detection, T1/NIfTI globbing are unchanged — still real,
   still useful independent of Freeview) but ends by logging the file list to the console and the
   message "Viewing has moved to the desktop app — open this subject/simulation there to render
   these files." instead of shelling out to `freeview`. Module + class docstrings rewritten
   accordingly. Verified inside `tit-v3-spike` (real PyQt5): the module imports cleanly, neither
   removed method exists on the class any more, and `tests/test_gui_imports.py`'s full 27-test
   suite (including the source-level `masks_dir` check that inspects this file's
   `VoxelAtlasManager(...)` call) passes unchanged.
8. **`desktop/tests/mock-server/contract.test.ts:32`** — found already changed from
   `@ts-expect-error` to `@ts-ignore` (by whichever concurrent WIP touched this file before this
   lane started) — that dodges `tsc`'s "unused directive" error but trades it for a *new* ESLint
   error (`@typescript-eslint/ban-ts-comment`: "Use @ts-expect-error instead of @ts-ignore"),
   caught by this lane's own `npm run lint` gate run. Fixed properly per the original ask: the
   suppression comment is deleted outright (not swapped to another directive) since `yaml` is a
   real, installed dependency now and the import needs no suppression at all. `tsc` and `lint`
   both clean on this file after.
9. **Freeview/Gmsh launch calls in `pages/analyzer/**`/`pages/optimizer-flex/**`** — deleted
   `openInFreeview`/`openInGmsh` (`pages/analyzer/api.ts`) and `getSubjectViewSpec`/
   `launchFreeview` (`pages/optimizer-flex/api.ts`) — all four called
   `POST /api/viewers/{freeview,gmsh}` or fetched a `ViewSpec` only to feed it to that route,
   neither of which exist in `schema.d.ts` any more. Every caller now deep-links into
   `/viewer` instead, reusing `pages/results/index.tsx`'s already-exported `ViewerLink`/
   `viewerSearch()` helper (read, not edited — `pages/results` is W5's) so the query-key
   convention (`kind`, `subject`, `simulation`, `field` — exactly those, per the brief) is shared
   with the one other place in the app that already builds this URL:
   - `AnalyzerPage.tsx`'s `viewInFreeview` (awaited `getViewSpec` + `openInFreeview`) →
     `openInViewer` (synchronous `navigate({pathname:"/viewer", search: viewerSearch(...)})`,
     `kind="subject"`). One real behavior change, unavoidable and noted in a code comment: the old
     call could request the MNI-space T1 (`space: "mni"`) for an MNI-coordinate spherical target;
     `ViewerLink` has no `space` key (the brief's four keys are exhaustive), so that distinction is
     dropped — the viewer opens the same subject-space scene, switchable from inside the viewer.
   - `ResultsPanel.tsx`'s two mutations (`gmsh`/`freeview`, calling `openInGmsh`/`openInFreeview`
     via `getViewSpec("analysis", ...)`) → one `openInViewer(analysis)` function and one "Open in
     viewer" button (was two buttons, "Open in Gmsh" + "Open in Freeview") gated on
     `selectedAnalysis.msh || selectedAnalysis.nifti` (either used to gate one of the two removed
     buttons).
   - `SphereRows.tsx`'s `onViewInFreeview`/`freeviewLabel` props (analyzer/** owned, so renamed
     for clarity) → `onOpenViewer`/`viewerLabel`; the fallback button label
     `coordinateSpace === "mni" ? "View MNI template" : "Open in Freeview"` → plain
     `"Open in viewer"` (the MNI-vs-subject framing no longer applies, see above).
   - `optimizer-flex/index.tsx`'s `openFreeview` (awaited `getSubjectViewSpec` + `launchFreeview`)
     → `openViewer` (same `navigate`+`viewerSearch` pattern, `kind="subject"`). Still wired through
     the **shared, unowned** `pages/_shared/roi/RoiPicker.tsx`'s `onOpenFreeview` prop — that
     component's prop name and its button's hard-coded label ("Open T1 in Freeview") are stale now
     (the button correctly opens the embedded viewer at runtime; only its name/label still says
     Freeview) — flagged as a cross-lane need below, not fixed here (outside this lane's granted
     paths). `getViewSpec` (`pages/analyzer/api.ts`) is left in place, unused by this page's own
     code as of this change but still a correctly-typed, real wrapper over the still-live
     `GET /api/view/{kind}` endpoint — kept rather than deleted as speculative cleanup.
   Typecheck clean for both owned pages; `pages/viewer`/`pages/results` untouched (not owned,
   currently green anyway — see Gates below).
10. **Comment-only cleanups** — `desktop/src/main/docker/discover.ts` and `engine.ts`'s header
    comments no longer describe `dockerCli.ts` as existing/"unchanged" (it's deleted, D4) or
    imply `discover.ts` shares an override env var with it; `nativeRuntime.ts`'s scope-note
    comment no longer cross-references the deleted `stackState.ts`, instead contrasting against
    `stack.ts`'s current label-based attach. No code changed in any of the four files.

## needs_from_other_lanes (found while closing the items above, not fixed — outside this lane's
owned paths)

- **`pages/_shared/roi/RoiPicker.tsx`** (owner unclear — not listed under any current Phase A/B
  lane; `AnalyzerPage.tsx`'s header comment calls it "the shared … picker (P3)"). Two stale spots,
  both cosmetic (the underlying callback already does the right thing after this lane's fix):
  `onOpenFreeview?: () => void` prop name (both the outer `RoiPickerProps` and the inner
  `SphericalPanel`'s props), and the button's hard-coded text `"Open T1 in Freeview"` inside
  `SphericalPanel` (~line 128). Rename to `onOpenViewer`/`"Open T1 in viewer"` whenever that file
  gets touched next; `optimizer-flex/index.tsx`'s caller already passes a `openViewer` function
  through the existing prop name, so this is a pure rename with no behavior change.
- **`src/renderer/app/jobs-rail/api.ts:47`** — still literals `kind: "viewer"` somewhere in a
  typed call, now a hard typecheck error (`Type '"viewer"' is not assignable to type
  "source" | "ex" | ...`) against the regenerated `JobKind` (item 5 above). Not owned by this
  lane; not `pages/viewer`/`pages/results` either, so not covered by the "expected fallout" carve-
  out in this lane's own gate instructions.
- **`src/renderer/pages/preprocess/index.tsx`** (7 typecheck errors: lines 48, 73, 103, 108, 568,
  569, 575, 577) and its two test files — `tests/unit/preprocess-defaults.test.ts` (1 typecheck
  error + 3 vitest failures) and `tests/unit/shell-subject.test.tsx` (2 typecheck errors, from
  `Subject.has_fastsurfer` becoming required, item 4 above) — all read/write the pre-FastSurfer
  `PreprocessConfig` field names (`run_recon`/`parallel_recon`/`parallel_cores`/
  `run_subcortical_segmentations`) that `tit/pre/config.py`'s dataclass already renamed (W3b) and
  this lane's contract regeneration (item 4) now reflects in `schema.d.ts`/`contracts/schema.json`
  too. `tests/unit/forms-ajvResolver.test.ts` has one more vitest failure of the identical shape
  (a `defaultPreprocessConfig()` fixture built with the old field names, now failing ajv's
  `additionalProperties: false` against the regenerated schema). None of these five files are in
  this lane's granted paths (`pages/preprocess/**`, `tests/unit/**` are outside the grant; `tests/**`
  in the grant means Python tests per the brief's own parenthetical). The fix in every case is
  mechanical — the same rename `tit/pre/__main__.py::migrate_legacy_keys` already performs on the
  Python side — but is left for whoever owns `desktop/src/renderer/pages/preprocess/**` /
  `desktop/tests/unit/**`.

## Gates

```
$ python3 -m black --check <18 touched .py files>
All done — 18 files would be left unchanged

$ python3 -m pytest -q                                        # host, py3.14
3149 passed, 18 skipped in 34.31s                              # 0 failed

$ docker exec -w /ti-toolbox tit-v3-spike simnibs_python -m pytest -q \
    tests/test_plan_routes.py tests/test_server_skeleton.py tests/test_viewspec.py \
    tests/test_viewspec_scene.py tests/test_jobs_model.py tests/test_jobs_scheduler.py \
    tests/test_jobs_routes.py tests/test_jobs_registry.py tests/test_analyzer_full.py \
    tests/test_catalog_v1.py tests/test_catalog.py tests/test_gui_imports.py \
    tests/test_pre_config_migration.py
413 passed in 11.25s

$ docker exec -w /ti-toolbox tit-v3-spike simnibs_python -m pytest -q     # full container suite
3160 passed, 7 skipped in 45.01s                                # 0 failed

$ docker exec -w /ti-toolbox tit-v3-spike simnibs_python dev/build_schema.py --check
/ti-toolbox/contracts/schema.json is up to date (62 $defs)

$ python3 dev/contracts_check.py contracts/openapi.v0.yaml <live --dump-openapi>
contracts_check: OK — 10 operation(s) and 9 schema(s) present

$ python3 dev/contracts_check.py contracts/openapi.v1.yaml <live --dump-openapi>
contracts_check: 49 problem(s)     # byte-identical count to W3a's pre-existing report; zero
                                   # hits for capabilit|viewspec|viewer|scene|tetravox|fastsurfer

$ cd desktop && npm run gen:api
regenerated src/renderer/api/schema.d.ts

$ cd desktop && npx tsc --noEmit -p tsconfig.node.json
(exit 0, no output)

$ cd desktop && npx tsc --noEmit -p tsconfig.web.json
11 errors in 4 files, none owned by this lane, none in pages/viewer or pages/results — see
needs_from_other_lanes above for the full list with line numbers.

$ cd desktop && npm run lint
✖ 3 problems (0 errors, 3 warnings)    # all 3 pre-existing react-hooks/incompatible-library
                                       # warnings in files this lane doesn't own; 0 errors (was
                                       # 1 error before item 8's fix)

$ cd desktop && npx vitest run
Test Files  2 failed | 43 passed (45)
     Tests  4 failed | 465 passed (469)
# both failing files are the same unowned pages/preprocess fallout (see needs_from_other_lanes);
# this lane's own tests/mock-server/** subset: 21 passed, 0 failed

$ cd desktop && npm run build
✓ built in 1.85s (exit 0)
```

Not run: `npm run e2e:quiet` — not listed in this lane's gate (no file this lane touched launches
Electron).

## Files touched this session

`tit/server/routes/{system,plan,jobs}.py`, `tit/server/schemas.py`, `tit/viewspec.py`,
`tit/jobs/{kinds,spec,costs}.py`, `tit/analyzer/analyzer.py`, `tit/gui/nifti_viewer_tab.py`,
`tests/test_{plan_routes,server_skeleton,viewspec,jobs_model,jobs_scheduler,jobs_routes,
jobs_registry,analyzer_full}.py`, `contracts/{openapi.v0.yaml,openapi.v1.yaml,schema.json,
openapi.v1.json,SCHEMA-CHANGES.md}`, `desktop/tests/fixtures/subjects.json`,
`desktop/tests/mock-server/{server.mjs,contract.test.ts}`,
`desktop/src/renderer/api/schema.d.ts`, `desktop/src/renderer/pages/analyzer/{api.ts,
AnalyzerPage.tsx,ResultsPanel.tsx,SphereRows.tsx}`,
`desktop/src/renderer/pages/optimizer-flex/{api.ts,index.tsx}`,
`desktop/src/main/docker/{discover.ts,engine.ts}` (comments only),
`desktop/src/main/nativeRuntime.ts` (comment only).

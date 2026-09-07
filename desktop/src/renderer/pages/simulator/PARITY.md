# Simulator page — parity checklist

Parity source: `tit/gui/simulator_tab.py` (2216 lines) + `tit/gui/components/conductivity_dialog.py`.
Backend: `tit/sim/config.py` (`SimulationConfig`, `Montage`, `MontageMode`), `tit/sim/utils.py`
(`build_simulation_config_for_job`, `run_simulation`), `tit/constants.py` (output field registry).

## Deliberate redesign, not a bug

The PyQt tab is a spreadsheet of **job cards** (`_add_job_row`): each row independently sets
subject, source (Montage/Flex-Search/Freehand), U/M mode, currents, and EEG net, then opens a
shared **selection panel** below to multi-select montages for that one row. The v3 screen matches
`v3-build-plan.md`'s brief instead ("subject picker; montage source tabs; ... one planned job per
(subject, montage)"): one multi-select **subject picker** at the top, three **source tabs**
(Montage / Flex-search / Free-hand) whose checkboxes add a row to a shared "cart" for **every**
currently-selected subject that has the item available (e.g. has that EEG net), and one **Global
parameters** card that applies to every job — exactly like the PyQt tab's own "Global Parameters"
group box, which already applies conductivity/electrode/output-field settings to all cards, not
per-card. Per-row state kept from the PyQt tab: currents (mA), editable per selected job.

## Checklist

| PyQt control | Default | Tooltip / help | v3 | Status |
|---|---|---|---|---|
| Subject combo (per job card) | first subject | — | `SubjectPicker`, multi-select, filtered to `has_m2m` | done (redesigned: one multi-select, not per-row) |
| Source combo: Montage / Flex-Search / Freehand | Montage | — | `Tabs`: Montage / Flex-search / Free-hand | done |
| Mode combo: U / M | U | — | Montage tab: "Polarity" select (uni_polar / multi_polar); rows show 2 vs 4+ pairs | done |
| Currents `mA` line edit | `1.0,1.0` / `1.0,1.0,1.0,1.0` | placeholder only | per-row text input in "Selected jobs" table, seeded from pair count | done |
| Net combo (per job card) | first net | — | Montage tab's "EEG net" select; Flex/Freehand read the net from the run/config itself | done |
| Selection list (montages) | — | flex items show a tooltip (search name / run id / type) | Montage/Flex/Free-hand tabs' own tables; flex shows goal chip + resolved electrode pairs from the run manifest | done |
| "Add Montage" / "Remove Montage" buttons | — | — | Montage tab "New montage" button opens an inline creation panel (see gap #1 below for why it is not a `Dialog`) + row-level edit/delete icons (delete via `AlertDialog`) | done |
| `AddMontageDialog` (uni/multi pair editors) | 2 pairs (U) / 4 pairs (M) | — | `ElectrodePairsEditor` (mode `net`) inside the inline montage panel, net-scoped electrode options | done |
| Anisotropy combo: Isotropic / vn / dir / mc | Isotropic | — | "Conductivity model" select | done |
| "Change Default Cond." button -> `ConductivityEditorDialog` | SimNIBS literature defaults (12 tissues) | info label "double-click to edit" | `ConductivityDialog`: editable table, same 12 tissues/defaults/references, Reset to defaults | done, **with a reported backend gap** (below) |
| Electrode Shape: Rectangle / Ellipse | Ellipse | — | `RadioGroup` | done |
| Dimensions (mm, x,y) line edit | `8,8` | placeholder | two `NumberInput`s (width/height) | done |
| Gel Thickness (mm) line edit | `4` | placeholder | `NumberInput` | done |
| Output Fields checkboxes | `TI_max` only | per-field tooltip (`spec.description`) + `HelpIcon` popup with equations/references | checkboxes with `title` tooltips + `Popover` info button reusing the same field descriptions | done |
| "Some selected simulation outputs already exist" dialog (skip / replace-and-rerun / cancel) | — | — | Plan panel: per-job "exists" / "will overwrite" chips + `AlertDialog` "Overwrite and run" before submitting overwriting jobs | redesigned to the v3 Plan-panel idiom (single `overwrite` flag per job, not a 3-way skip/replace/cancel choice) |
| Run / Stop buttons, console | — | — | Plan panel's "Run simulation" / "Queue N jobs" button; live output now lives in the Jobs rail (`app/jobs-rail/`), not an inline console, per `v3-build-plan.md` (R3: "anything long is a job") | done (console intentionally not rebuilt here — jobs rail owns it) |
| `TI_normal` — always computed for 2-pair TI, not a checkbox | n/a | n/a | not offered as a selectable output field (matches `get_selectable_output_field_specs()`) | done |
| `map_to_mni`, `map_to_fsavg`, `map_to_vol`, `open_in_gmsh`, `rubber_thickness`, `aniso_maxratio`, `aniso_maxcond`, `tissues_in_niftis` | schema defaults | n/a | **not exposed** — the PyQt tab does not expose them either (verified: no matching widgets in `simulator_tab.py`); left at `SimulationConfig` defaults by omission | matches PyQt (no widget), not a v3 gap |

## Free-hand table (new in v3; no direct PyQt equivalent)

The PyQt tab reads free-hand configs from on-disk `stim_configs/*.json` (keys `E1+/E1-/E2+/E2-/...`,
built by other tools) — it has no *editor* for them. `catalog.json`'s `FreehandConfig` contract
(`{name, type: "U"|"M", electrode_positions: [{label?, x,y,z}]}`) is the actual v3.0 writer
surface (per the lane brief: "the ONLY writer of stim_configs in v3.0"), so this page builds a
genuine table editor (label, x, y, z per row, add/remove rows) rather than porting a UI that never
existed. Row count is validated to 4 (2 pairs, TI) or 8+ in steps of 2 (4+ pairs, mTI), matching
`Montage.simulation_mode`. `type` is derived from pair count (`U` for 2 pairs, `M` for 4+) — fixed
fix:pages-a 2026-08-27 after the contract lane's reconciliation narrowed `FreehandConfig.type` from
`"xyz"|"label"` to the real on-disk `"U"|"M"` values (`tit/catalog.py::_read_freehand_file`); the
previous `xyz`/`label` guess (keyed off whether any position had a label) no longer type-checks.

## Electrode Placement extension (`tit/gui/extensions/electrode_placement.py`, 1091 lines)

Migrated **into this page**, not as a panel of its own — maintainer, 2026-09-06: *"For the
electrode placement extension, please just enhance the simulator instead of actually embedding a
complete extension for it. Instead of having our default subject in the simulator, we should just
load the selected subject such that the user can click on the surface of the skin in the simulator
tab when the free hand is selected and by that they can insert the electrode coordinates."*

| PyQt (2.5.0) | v3 | Status |
|---|---|---|
| Its own window with a subject combo, an OpenGL widget and a marker table | The Simulator's own 3-D pane and the free-hand editor's table, which are now two views of one array (`freehandDraft.tsx`) | done |
| `loadSurfaces()` reads `m2m_<id>/<id>.msh` and draws skin + GM | `<ScenePane subject={…}>` → `/api/scene/*` (the server extracts; 1.4 MB of skin crosses the wire, not a 184 MB mesh) | done |
| Double-click ray-casts the skin and appends a marker | **Select a row, then click the scalp** — the row takes the point, and a further click moves it (maintainer, 2026-09-06: *"enforce a selection of the electrode from the table"*). The world point is the depth the renderer's own pick pass rasterised (`ScenePick.world`), read against **every** surface so a faint scalp is still what the click lands on, in the head mesh's own millimetres — the frame `stim_configs/*.json` stores | done |
| `E<n>+ / E<n>-` naming by row index, per-pair marker colours | `freehandPlacement.ts::autoLabel` + `placementMarkers`. The colour is **per electrode**, not per pair (`SCENE_CATEGORICAL`, 12 hues): the question a dot answers here is "which row am I", which a six-hue pair ramp cannot. The same colour is the row's swatch | done |
| `deleteChecked` renumbers the remaining markers | `removeAt` = filter + `renumber`; the dot goes with the row | done |
| Editable X/Y/Z cells | The editor's `NumberInput`s, unchanged — a click and a typed millimetre write the same rows | done |
| "Export Configuration" → name + `U`/`M` prompt → `stim_configs/<name>.json` | "Save placement" → `PUT /api/catalog/freehand/{name}`, `type` derived from the pair count | done |
| EEG-cap overlay (`loadEEGCap`) | The pane's own net electrodes, from the row's EEG net | done |
| Its own trackball camera, mesh loader and normals | `renderer/scene/` | done |

Not carried over: the extension's per-marker **checkbox column** (v3 removes one row at a time from
a table that is four rows long) and its standalone subject combo (the placement's subject is the
editor's own field, and it is what the pane draws).

### Three rules the 2.5.0 widget did not need, and the failures behind them

Each was reported by the maintainer against a screenshot on 2026-09-06.

1. **The dot is never buried in the scalp.** A placement sits exactly on the surface it was picked
   off, so it loses the depth test against that surface — the first build drew a crescent above the
   skin and, with the skin turned down, nothing at all. Placement markers are therefore drawn with
   the depth test off (`markersOccluded={false}`, `depthFunc(ALWAYS)`), one and a half times the
   EEG-net dot's size, with a thin dark contour so a light hue still has an edge.
2. **The click reads the skin, however faint it is.** With a translucent scalp the depth pass
   skipped it and the point landed on the grey matter behind — an electrode inside the head.
   `PickOptions.allSurfaces` (the pane's `pickAnySurface`, on only in `place`) makes every surface
   count and the nearest win. The Optimizer keeps the default, because *its* click is aimed
   **through** the scalp at the cortex.
3. **The selection is shown, not explained.** No instructional copy anywhere: an accent row with a
   ringed swatch in the table, and a white ring plus a size step on that electrode's dot on the
   scalp. Exactly one row at a time; clicking the selected row again clears it.

Known deviation: a placement dot on the **far side** of the head is not hidden. Doing it properly
needs the surface normal at the picked point, which the pick pass does not report; four to eight
dots that never disappear is a better failure than one the user placed and cannot find.

## Reported gaps (not fixable inside `pages/simulator/**`)

1. **RESOLVED, verified fix:pages-a 2026-08-27.** A `Select`/`Popover`/`Combobox` popover used to
   render behind an open `Dialog`'s own overlay. `ui/tokens.css:91-95` now scales
   `--z-overlay:80 / --z-dialog:90 / --z-popover:100 / --z-tooltip:110 / --z-toast:120`, so a
   popover opened inside a dialog sits above its backdrop. The montage editor stays an inline
   `Card` panel (see `MontageManager.tsx`) as a deliberate design choice, not a workaround anymore
   — no follow-up needed.
2. **`SimulationConfig` has no `tissue_conductivities` field.** The legacy dialog applies overrides
   via `os.environ["TISSUE_COND_<n>"]`, read by `tit.sim.base._apply_tissue_conductivities` — a
   process-global side channel that doesn't fit a job server executing many jobs concurrently in
   one process. The v3 conductivity dialog collects overrides and sends them as
   `config.tissue_conductivities: {tissue_number: value}` (forward-compatible JSON; ignored by
   `deserialize_config` today, since unknown keys are dropped). **Needs**: a real
   `tissue_conductivities: dict[str, float] | None` field on `SimulationConfig`, consumed by
   `tit/sim/base.py` instead of (or in addition to) the env-var path. Filed against F1b/B4 per
   `docs/dev/DECISIONS.md`'s own note on this exact legacy pattern.
3. **Plan naming convention for `kind=sim` — SUPERSEDED, fix:pages-a 2026-08-27.** This page used
   to send the montage name as a plan-only top-level `name` field alongside the real
   `SimulationConfig` fields so `outputDirFor`/`existsForFixture` in the mock could compute
   `output_dir`/`exists` the way they do for other kinds — noted at the time as harmless because
   the real `_plan_sim` never read it (it resolves one `PlanJob` per `(subject, montage)` from
   `SimulationConfig.montages[i].name` directly) and the schema had no `additionalProperties`
   restriction to violate. Once `contracts/schema.json`'s `SimulationConfig` gained
   `additionalProperties: false` (ra_11 finding 3, landed mid-build by another lane), that extra
   key started failing schema validation (`tests/unit/simulator-defaults.test.ts` caught it), so
   `buildSimulationConfig` (`buildConfig.ts`) no longer adds it — `config` is now a real,
   schema-conformant `SimulationConfig` with nothing extra. **Trade-off accepted**: against the
   mock only, a `kind=sim` plan preview's `output_dir` now shows the mock's generic "NewRun"
   fallback instead of the real montage name (`tests/mock-server/server.mjs::outputDirFor` reads a
   top-level `cfg.name` that no longer exists — F3-owned, not this lane's file to change); the real
   server is unaffected since it never read that field. No e2e assertion depends on the mock's
   exact `output_dir` string.
4. **Planning half RESOLVED, verified fix:pages-a 2026-08-27** — `tit/server/routes/plan.py:20-28`
   now reads the top-level `PlanRequest.montage_sources` field this page already sends
   (`{flex: [{subject, run, electrode_type, eeg_net}]}` / `{freehand: [{subject, name}]}`, per
   `_montage_sources_for_request`'s own docstring), with the old nested-in-`config` shape kept only
   as a one-release fallback. No client-side change needed for planning any more.
   **Submission gap RESOLVED 2026-09-06** — `flex_meta.json` records no electrodes at all, so the
   old `manifest.electrodes` read here was always empty: every row's checkbox was disabled and the
   whole "Flex result" mode was unclickable (maintainer report, reproduced against Dataset 000).
   `tit/catalog.py::flex_runs` now surfaces the electrodes from the run's own files as `FlexRun`
   fields — `mappings` (one per `electrode_mapping_<net>.json`, i.e. `FLEX_MAPPED`) and `optimized`
   (`electrode_positions.json`, i.e. `FLEX_FREE`, which every flex run writes) — so the tab can tell
   mapped from free and resolve either into the `Montage` a submitted job must embed. The plan no
   longer sends `montage_sources` alongside an already-resolved config either: the server resolved
   the run a *second* time from it, planning one job as two.

5. **Montage CRUD without any subject selected has no electrode-label source.** `GET
   /api/catalog/eeg-nets` is subject-scoped (`?subject=`); creating a montage before picking any
   subject leaves the pair editor's electrode dropdowns empty. Low priority (montages are
   subject-independent by net, so this only blocks the *very first* action in an empty session) —
   noted rather than worked around with a fabricated subject.
6. **A shared v1 API client would remove some duplication.** `desktop/src/renderer/api/client.ts`
   only wraps the v0 endpoints; this page added its own `pages/simulator/api.ts` for every v1
   catalog/plan/jobs call it needs rather than extending the shared file (not in this lane's
   ownership, and multiple lanes need the same v1 endpoints — editing it here would race other
   page agents). **Suggestion for the orchestrator**: a follow-up pass consolidating the v1 catalog
   /plan/jobs helpers that P2–P5 will each have reinvented into `api/client.ts` (or a sibling
   `api/v1.ts`), owned by one lane.
7. **`forms/ajvResolver.ts` + `forms/schema.ts`'s `resolveDef` cannot validate any config with a
   nested dataclass.** `createAjvResolver(name)` compiles a single extracted `$defs` entry in
   isolation; any `$ref` to a sibling `$defs` entry (e.g. `SimulationConfig.montages` ->
   `#/$defs/Montage`) then fails to resolve ("can't resolve reference #/$defs/Montage from id #").
   This is not new: it already fails on `main`'s `optimizer-ex-defaults.test.ts` (5 of 7 cases,
   via `ExConfig`/`MExConfig`'s bucket-electrode sub-types) — reproduced here for `SimulationConfig`
   too. `tests/unit/simulator-defaults.test.ts` works around it by compiling the *whole* schema
   document directly with `ajv/dist/2020` instead of going through the shared resolver; the
   resolver itself needs a fix from F2 (likely: register the full document once via `ajv.addSchema`
   and resolve definitions with `ajv.getSchema('#/$defs/<name>')` instead of extracting and
   recompiling a fragment).

## Verified correctness catch

Building `SimulationConfig.montages[0]` without a `_type: "Montage"` discriminator **fails schema
validation** — `Montage` is a member of the top-level `PipelineConfig` union, so
`dev/build_contract.py`/`config_io.py` mark it `required: [..., "_type"]` even when nested. Caught
by `tests/unit/simulator-defaults.test.ts` before this ever reached a real server; fixed in
`buildConfig.ts`.

# Tetravox currency, electrode dots, one selection grammar, and the pipeline canvas (plan of record, 2026-09-05)

Status: **implemented and gated** (2026-09-05). Lanes TX/AU/EL/SG/PC finished; the consolidation lane
closed the seams, landed the records and ran the full gate — `dev/notes/v3-tetravox-selection-pipeline/CX2.md`.
Records: `docs/requirements/2026-09-05-tetravox-selection-pipeline.md`, `docs/ARCHITECTURE.md` §7,
`docs/DECISIONS.md` (8 entries), `docs/ROADMAP.md`, `tracks/active/v3-electron-gui.md` row 26,
`desktop/DESIGN.md` §§4.8/4.9/9.1/9.2. The Tetravox release itself (PR #35 → `scripts/release.sh 0.3.12`)
is the maintainer's, and is the only thing A3 is still waiting on.
Follows `desktop/IMPLEMENTATION_PLAN.md` (R1–R5, gated today). Lane rules: `dev/notes/v3-overview-batch-viewer/LANES.md`
(same worktree, disjoint ownership, no commits, records land via the consolidation lane). Lane notes go to
`dev/notes/v3-tetravox-selection-pipeline/<LANE>.md`.

## Maintainer asks, verbatim

> "We shipped a new TetraVox that fixed a few visualization bugs, so please make sure that we incorporate that into the TI toolbox."
> "think deeply about how we should implement the TI toolbox in such a way that it automatically gets updated if Tetravox is releasing a new version"
> "I don't want to use the native Tetravox for the EEG electrode visualization. Instead, I want to use dot-like visuals for the electrodes … Instead of creating circles around the electrodes please change their colors and make sure that the selection deselection works properly."
> "you have to create tests to make sure that the selection and visualization of electrodes and channels works properly."
> "I want to come up with a solution for all windows on how we should create the selection logic of elements. In the TI toolbox 2.5.0, we had a great logic for selecting multiple jobs … right now it's too convoluted for the users to choose and to understand the jobs that they're selecting."
> "a canvas-like graphical programming where users create nodes of processing and (1) run it as a pipeline — one flow of complete processing … as a single job — and (2) create Jupyter notebooks out of it … shared, visualized, and modified programmatically."

## 0. What is already true (measured 2026-09-05)

- Tetravox `main` is **0.3.11** (0.3.10 fixed surface opacity on smooth sheets; 0.3.11 fixed view controls / layer
  controls / screenshot layout). `packages/embed` exists **only** on `feat/embed-viewport` (d78e2ef, protocol 2,
  embed version 0.4.0, 11 commits behind main). No release carries an embed asset; `release.yml`'s `embed` job exists
  only on that branch. So **no shipped embed has the 0.3.10/0.3.11 fixes**.
- TI-Toolbox dynamic delivery (plan `v3-embed-convergence-plan.md`, lanes U/M) is complete and live: `tit/tetravox/`
  (protocol range 1–2 + named features, two install roots, sha256-verified atomic install, `active.json` pin, baked
  rollback), routes `/api/tetravox{,/updates,/install,/activate,/{version}}`, Settings `TetravoxCard`. The dev
  container runs a runtime-installed 0.4.0/protocol-2 over a baked 0.3.4/protocol-1 floor. The **only** gap for
  automatic updates: `install.py` reads a `releases.json` index on Tetravox `main` that does not exist; nothing polls.
- Electrodes are already a protocol-2 inline points layer (`pages/_shared/scene/embedScene.ts:200-219`,
  `shape:"sphere"`, `stateColors.selected` amber, no tool ring because `setPointTool` is never sent). The embed's
  `EmbedPointsLayer` has `shape: 'sphere' | 'dot'`, `dotRadiusPx`, `stateColors {idle,selected,disabled}` and
  per-point `color`; unknown fields pass through to the engine.
- v3 has **five** selection idioms (row-checkbox table with filter+all/none; the same table deliberately without
  either; two `Select` combos per electrode pair; `MultiSelect` chips per ex bucket; 3-D click-toggle) and the Jobs
  list has no selection at all. 2.5.0's pattern (see §3) was one idiom everywhere.
- Job groups already form a DAG: `PlannedJob.after` labels resolved in topological order (`tit/jobs/spec.py:221,292`,
  `plans.py::plan_preprocessing` G1–G6+report). Every page has a pure config builder
  (`pages/{simulator,analyzer}/buildConfig.ts`, `optimizer/{flex,ex}Config.ts`, preprocess). The `tit` scripting API
  (`SimulationConfig`, `FlexConfig`, `ExConfig`, `Analyzer`, `run_pipeline`) is documented in the wiki.

## 1. Decisions

**A — Tetravox currency and automatic updates**

- A1 *Where the coupling lives.* TI-Toolbox pins a **protocol range + named features**, never a Tetravox version
  (already E1). A Tetravox release is "incorporable" iff its embed manifest's `protocol` ∈ range; a release whose
  protocol exceeds `SUPPORTED_PROTOCOL_MAX` is reported as *needs a TI-Toolbox update*, never installed.
- A2 *Source of truth for "is there a new one".* The **GitHub Releases API** of `idossha/tetravox`
  (`/repos/idossha/tetravox/releases`, non-draft, non-prerelease, newest first), looking for the asset pair
  `tetravox-embed-<ver>.tgz` + `tetravox-embed-<ver>.tgz.sha256` and reading `protocol` from a third asset
  `tetravox-embed-<ver>.manifest.json` so the check needs no download. Replaces the never-existing `releases.json`
  (the env override `TIT_TETRAVOX_RELEASE_INDEX` remains for air-gapped mirrors, accepting either the GitHub JSON
  shape or a plain index). `api.github.com` joins the host allowlist.
- A3 *Policy.* Setting `tetravox.auto_update` (default **on**): the server checks at startup (non-blocking, after
  `/api/health` is up) and every 24 h; if a newer compatible embed exists it installs into the user root, activates it,
  and emits a `tetravox.updated` event that the desktop shows as one toast ("Tetravox 0.3.12 installed — reload the
  viewer"). Panes already mounted keep their iframe until the user reloads; new mounts get the new bundle. Off →
  check only, show "Update available" in Settings. Failure (offline, 403 rate-limit, bad digest) is one honest line
  in Settings and the log; it never blocks anything and never retries more than once per interval.
- A4 *Rollback stays one click* (`activate baked` / previous version) and the last two installed versions are kept.
- A5 *The image bake follows the same rule.* `container/blueprint/build.sh` resolves the newest compatible release
  automatically when `--tetravox-tgz` is not given (same lookup, in bash+python), so a fresh image never ships the
  placeholder. Documented in `container/blueprint/README.md`.
- A6 *Tetravox side.* Rebase `feat/embed-viewport` onto `main` (picks up 0.3.10/0.3.11 engine fixes), make the embed
  version the release version (one number; `pack.mjs` reads the root version), emit the `.sha256` and
  `.manifest.json` sidecars from `release.yml`'s `embed` job, fix the missing reply ids on `setPoints` /
  `setPointTool` / `setPointSelection` (host hangs when awaiting), add `shape`/`stateColors`/`dotRadiusPx` to
  `viewspec.schema.json`. Push the branch and open a PR; **never** touch `main` or push a tag (Tetravox AGENTS.md).
  The release itself (merge + `scripts/release.sh` + tag push) is the maintainer's.

**B — Electrodes as dots, colour = state, no rings**

- B1 Points layer `shape: 'dot'`, `dotRadiusPx` 5 (7 when hovered/active channel), `offPlaneOpacity` kept.
- B2 Colour is the whole signal: `idle` = neutral grey, `disabled` = 35 % grey, **selected = its channel colour**
  (pair 1 / pair 2 … from `channelColor`), hover = same hue, lighter. `stateColors` carries idle/disabled; selected
  points carry an explicit `color` (per-channel) because one layer-level `selected` colour cannot encode the channel.
  `setPointTool` / `setPointSelection` are never sent, so no ring can appear — asserted, not assumed.
- B3 Select/deselect: click an idle dot → next free slot of the active pair; click a selected dot → removes it and
  parks the cursor on the vacated slot (today's rule, kept); the form is the source of truth and the layer re-derives
  from it (`setPoints` whole replacement). Keyboard: the same via the pair editor. Labels: names shown for selected
  points and on hover only.
- B4 Channels: a legend chip per channel (colour + "E1 → E2") above the pane; clicking a chip makes that pair active.
- B5 Tests (all offscreen): unit — marker→point mapping (state/colour/radius, no `setPointSelection` ever emitted);
  mock e2e — pick idle → form slot filled and the next `setPoints` payload marks exactly that id selected with the
  channel colour; pick selected → removed; two channels → two hues; `real` e2e — with the real embed, screenshot via
  the `screenshot` message and assert the drawing-buffer colour at the projected electrode position (camera set to a
  known preset via `setCamera`) before/after toggle equals the expected state colour within tolerance; and no ring
  pixels (annulus around the dot equals background).

**C — One selection grammar for every window (build on 2.5.0)**

2.5.0's rule, restated: *a flat list of discovered things, native range selection, exactly two bulk buttons, options
that apply to the whole selection (never per item), a plain receipt of what will run, and a Skip/Replace/Cancel decision
on existing outputs.* v3 keeps its stronger pieces (readiness columns, blocked reasons, scheduler cap) and drops the rest.

- C1 One primitive `ui/SelectionList` (rows = any catalog item: subject, montage, ROI/region, electrode, participant,
  job): click selects one, ⇧-click ranges, ⌘/Ctrl-click toggles, ⌘A all, Esc none; a checkbox column is the visible
  state (so touch/mouse-only users toggle rows), always-on filter box, `All · None` as the only bulk buttons, an
  `N of M selected` badge. Virtualised. Replaces the row-click ambiguity in `SubjectsField` (whole-row click *and*
  checkbox today), gives `ParticipantsField` the same filter/All/None, and replaces `MultiSelect` chips for ex/mEx
  buckets and the region checkboxes in `RoiPicker` with the same list.
- C2 Electrode pairs keep the pair editor (two slots per pair) but each slot opens the same `SelectionList` in
  single-select mode, and the 3-D pane is a second input to the same model (B3).
- C3 *Jobs are what the receipt says.* Every run page shows one **receipt** above Run: "This will run **N** jobs:
  S subjects × M montages … Existing outputs: skip/replace" — the same `planModelFrom` rows, rendered as a short
  list (first 15 + "… and K more") exactly as 2.5.0 did, replacing the grid as the primary confirmation; the grid
  stays as the detail view. The existing-output pre-flight (Skip / Replace / Cancel) becomes one shared dialog used by
  all four run pages (Simulator already has a version).
- C4 Jobs page rows become selectable with the same primitive (cancel / retry / pin terminal for the selection).
- C5 Non-goals: no drag-to-reorder anywhere (pipeline order is fixed, as in 2.5.0); no per-item options.

**D — Pipeline canvas and notebook export**

- D1 *A pipeline is a DAG of nodes; each node is exactly one existing job kind with exactly the config that page
  already builds.* Node kinds: `pre`, `sim`, `flex`, `ex`, `mex`, `analyzer`, `source`, `stats`. Edges carry
  **outputs** (subject set, montage names, ROI, leadfield) — a downstream node's inputs are bound to an upstream
  node's outputs by name, so "Optimizer → Simulator" means the simulator's montage list is *the flex result*, and
  "Pre-processing → everything" means the subject set flows through. No new job kinds; no runtime graph engine.
- D2 *Run = one job group.* `POST /api/jobs/groups` with `after` labels derived from the edges (the pre DAG already
  works this way); per-subject fan-out happens inside each node as R3 defines; the scheduler cap applies. A pipeline
  run is one group id, shown in Jobs as one row with its member tree, cancellable as one.
- D3 *Bindings are resolved at run time by the server*, not by the client: a `tit/pipeline/` module validates the
  graph (acyclic, typed ports, every required input bound or set), resolves bindings (e.g. montage names from a
  finished flex job's output dir) via a small `resolve` step that runs as a job before its consumer, and submits the
  group. `POST /api/pipelines/validate` and `POST /api/pipelines/run`; the document is `contracts/pipeline.schema.json`
  (`version: 1`, nodes[id, kind, config, position], edges[from, to, port]).
- D4 *Notebook export is a pure function of the document.* `tit/pipeline/notebook.py` emits an `nbformat` v4
  notebook: a title cell with the graph rendered as a Mermaid block, one markdown+code cell pair per node in
  topological order using the public `tit` scripting API (`SimulationConfig(...)`, `run_simulation(cfg)`,
  `FlexConfig`, `run_flex_search`, `Analyzer`, `run_pipeline`), bindings expressed as Python variables passed between
  cells, and a final "run everything" cell. `GET /api/pipelines/export?format=ipynb` and a Save button; the export is
  round-trippable in the sense that the notebook carries the pipeline JSON in its metadata (`metadata.ti_toolbox.pipeline`)
  so a later "import notebook" can restore the canvas without parsing Python. Importing arbitrary edited notebooks
  is a non-goal.
- D5 *Canvas.* React Flow (`@xyflow/react`, MIT) — one new dependency, recorded in DECISIONS. Page `pipeline`
  (rail after Analyzer, Cmd+6). Node = card with the kind, a one-line summary (subjects, montage/ROI), status chip
  while running; double-click opens the same form that page uses (reuse `pages/<kind>` form sections, not copies);
  right pane = receipt (D2, same as C3) + Terminal. Palette of node kinds on the left; connect by dragging ports;
  invalid connection refused with a reason. Save/Load pipeline JSON under `code/ti-toolbox/pipelines/<name>.json`.
- D6 Gate: a 4-node pipeline (pre→flex→sim→analyzer) on the mock server validates, runs as **one** group whose
  `after` chain matches the edges, shows one Jobs row, exports a notebook that `nbformat.validate`s and whose code
  cells execute against a stub `tit` (import + construct configs) in a subprocess; on the real container a 2-node
  pipeline (sim → analyzer, sub-ernie, an existing montage) completes end to end via the smoke harness.

## 2. Lanes (all Opus, concurrent, disjoint ownership)

| Lane | Owns | Depends on |
|---|---|---|
| **TX** Tetravox repo | new worktree `../tetravox-wt-embed-release` off `feat/embed-viewport`, rebased onto `origin/main`; `packages/embed/**`, `.github/workflows/release.yml` (embed job), `docs/EMBED.md`, `docs/ARCHITECTURE.md` §embed, DECISIONS | — (push branch + PR only) |
| **AU** auto-update | `tit/tetravox/`, `tit/server/routes/tetravox.py`, `tit/server/{settings,app}.py` (startup task), `contracts` tetravox section, `container/blueprint/build.sh` + README, `desktop/src/renderer/pages/settings/TetravoxCard.tsx` + `api.ts`, `app/` toast on `tetravox.updated` event (one small edit in the events model), tests | TX only for the *real* release; verified against a loopback fake GitHub API |
| **EL** electrodes | `pages/_shared/scene/**`, `viewer/protocol.ts` (types only), `ui/` legend chip (new file), tests `scene-pane`, `guide`, `real/embed-*` | current 0.4.0 embed already passes `shape`/`stateColors` |
| **SG** selection grammar | new `ui/SelectionList.tsx` + css, `pages/_shared/subjects/`, `pages/panels/_participants/`, `pages/_shared/roi/RoiPicker.tsx`, `pages/optimizer/ExSections.tsx` (buckets), `ui/ElectrodePairsEditor.tsx`, `pages/_shared/run/` receipt + shared existing-output dialog, the run pages' selection wiring, `pages/jobs/`, `ui/Jobs.tsx` row selection only, tests | coordinates with EL on `ElectrodePairsEditor` (SG owns the file; EL consumes the model) |
| **PC** pipeline canvas | new `tit/pipeline/`, `tit/server/routes/pipelines.py`, `contracts/pipeline.schema.json` + openapi section, `desktop/src/renderer/pages/pipeline/**`, `app/` registration (page id, rail, Cmd+6, palette — small edits), `package.json` (+`@xyflow/react`), `pyproject.toml` (+`nbformat`), docs `docs/wiki/pipelines.md`, tests | reads the other pages' config builders read-only |
| **CX2** consolidation | everything after the five finish: seams, records (intent doc, ARCHITECTURE, DECISIONS ×≥6, ROADMAP, ADR row, DESIGN), full gate | all |

## 3. Risks and fixed decisions

- **Rate limits / offline:** unauthenticated GitHub API = 60 req/h per IP; the check is once per start + 24 h, cached
  (`ETag`), and a 403 is "could not check", not an error dialog.
- **Two Tetravox sessions:** the TX lane never checks out or pushes `main`, never tags; its PR is the handoff.
- **Embed reply ids:** until TX's fix ships, the host must not `await` `setPoints` (EL keeps fire-and-forget).
- **Selection primitive scope creep:** `SelectionList` is a list, not a tree; the Results tree stays as is.
- **Pipeline ≠ workflow engine:** bindings are resolved by small server-side steps, the scheduler stays the only
  executor, and a pipeline run is a normal job group. No new runtime.
- **Notebook honesty:** exported code uses only documented public API calls; the gate executes it against a stub.

## 4. Gate commands

```bash
cd desktop && pnpm run typecheck && pnpm run lint && pnpm run test && pnpm run e2e:quiet && pnpm run build
python3 -m pytest tests/ -q && python3 dev/route_import_guard.py
# real (offscreen): npx playwright test --project=real tests/e2e/real/{embed-*,tetravox,pipeline}.spec.ts
# tetravox worktree: pnpm typecheck && pnpm test && pnpm --filter @tetravox/embed e2e && pack:embed
```

# TI-Toolbox v3 overview, batch, terminal, and viewer plan

Date: 2026-09-05  
Status: R1-R5 implemented and gated per-lane (`dev/notes/v3-overview-batch-viewer/{OV,TM,BX,GD,VW}.md`);
delivery steps 1 and 7 closed by the consolidation lane (`.../CX.md`) — records landed in
`docs/{ARCHITECTURE,DECISIONS,ROADMAP}.md`, `docs/requirements/2026-09-05-overview-batch-viewer.md`,
`tracks/active/v3-electron-gui.md` and `desktop/DESIGN.md`; typecheck, lint, unit, full offscreen
e2e, build, host pytest, the route-import guard and the real-container checks are green. Step 7's
`pnpm run dev` smoke is the maintainer's own, deliberately not run here. Nothing is committed.

A **2026-09-06** pass follows both of the 2026-09-05 ones and **reverses parts of them**: the
run-page 3-D panes are now this app's own WebGL2 renderer, the Viewer page is a data selector that
opens the host-installed Tetravox desktop app with a scene file (the embed, its update channel and
`Capabilities.tetravox_embed` are deleted), and the Simulator and Analyzer describe a run as a jobs
table instead of a page-level subject set fanned across a montage list. Plan of record
`dev/notes/v3-native-panes-external-viewer-plan.md`; requirements
`docs/requirements/2026-09-06-native-panes-external-viewer.md`; contract `docs/ARCHITECTURE.md`
§§7.1, 7.2, 7.5; gate `dev/notes/v3-native-panes-external-viewer/CX3.md`.

A **second** 2026-09-05 pass followed this one — Tetravox currency and automatic updates, electrodes
as coloured dots, one selection grammar with the receipt, and the pipeline canvas. Its plan of record
is `dev/notes/v3-tetravox-selection-pipeline-plan.md` (A-D), its requirements are
`docs/requirements/2026-09-05-tetravox-selection-pipeline.md`, its contract is
`docs/ARCHITECTURE.md` §7, and its gate is `dev/notes/v3-tetravox-selection-pipeline/CX2.md`. It does
not reverse anything here; it adds a ninth rail row (Pipeline, ⌘6), which moves Settings to ⌘0.  
Scope: Electron desktop, catalog/job/scene APIs, tests, and the corresponding architecture records

## Goal

Make the desktop open on a project-level Overview, give every runnable workflow the same subject and
batch grammar, make every interactive terminal scrollable and locally clearable, and decouple guide
visualization from the selected research subject. Keep detailed outputs in Results.

This plan refines `../docs/ARCHITECTURE.md` §§2–5 and reverses the current landing-page and
subject-coupled scene rules in `DESIGN.md` §§9–10. The dated parent-repository intent document,
contract amendment, decision entries, and roadmap lines must land in the same implementation commit.
The maintainer's 2026-09-05 notes outrank earlier plans where they conflict.

## Maintainer asks, verbatim

> "the first tab should not be subjects, it should be overview"

> "We can also delete the subject info page completely and migrate bits and pieces of logic and
> information from that into the overview page."

> "regarding the terminal in all pages, make sure that A it is scrollable, b that it can be cleared.
> Make sure the logic is modular and recyclable between all pages."

> "all pages that require subject selection, they need to behave like the pre-processing does"

> "users should be able to select multiple subjects for either a parallelized or a sequential processing"

> "instead of actually rendering the selected individual, we can be rendering a general individual,
> for example, Ernie"

> "the top [bar] will have more selection, for example the type of atlas and so on, and that it does
> not load information automatically based on subject selection"

## R1 — Replace Subjects with a project Overview

The first rail item, Cmd+1 target, initial route, catch-all destination, palette item, and page id become
`overview`. The current Subjects page is the starting implementation: keep its project coverage,
presence/readiness matrix, filters, workflow links, and high-level output counts. Rename and reshape it
as an eagle-eye project page; do not reproduce the Results tree or output preview.

Overview shows, per subject, raw staged/converted state, FastSurfer, FreeSurfer, m2m, DWI, CT,
leadfields, EEG nets, and high-level totals/readiness for simulations, optimizations, and analyses.
Pending, absent, partial, and failed are distinct states. A row may link to a workflow or open the same
subject in Results.

Replace the current N-subject/N-output request fan-out with one `GET /api/catalog/overview` response
that owns the display facts and counts. Its request count must not grow with the number of subjects or
simulations. Detailed output discovery remains lazy and owned by Results.

Delete the Subject Info discovery shim/page and remove its Settings toggle, panel id, parity assertions,
and test fixtures. Old `/panel-subject-info` navigation falls through to Overview; stale saved panel ids
are ignored. The compatibility catalog endpoint may remain until the API's next versioned cleanup.

* Gate test: in mock projects containing 3 and 30 subjects, opening Overview makes exactly one overview
  catalog request, renders every subject and every defined presence/count column, and Cmd+1, first launch,
  catch-all, rail, and palette all resolve to `/overview`. No Subject Info route or toggle is discoverable.

## R2 — Make the shared terminal scrollable and locally clearable

Keep `ui/Jobs.tsx::JobConsole` as the one interactive log renderer used by all four run pages and the
Jobs rail. Its existing vertical/horizontal overflow and virtualization remain. Add a source-aware Clear
action that hides the lines currently visible without deleting server events or truncating a log file.
New lines arriving after Clear appear normally. Changing from one job/file source to another resets the
clear watermark; Follow state is retained and the text filter resets.

Move duplicated event-to-line conversion and sequence merging from `JobTerminal` and `ConsolePane` into
one pure shared module. Keep Jobs detail `<pre>` excerpts as diagnostic records rather than pretending
they are interactive terminals.

* Gate test: a 100-line console has `scrollHeight > clientHeight`; one long line has
  `scrollWidth > clientWidth`; scrolling changes both offsets. Clear removes all current rendered lines,
  leaves the input array byte-for-byte unchanged, shows the next higher-sequence line, and does not carry
  its watermark to a different source key. The same shared control is present in one run-page integration
  test and the Jobs rail.

## R3 — Standardize subject selection and execution policy

`SubjectsField` remains the only set selector and is open by default on Pre-processing, Simulator,
Optimizer, Analyzer, and Source. It retains filtering, select-all, readiness columns, blocked reasons,
and page-session memory. Analyzer's single-subject scope and grouped analysis remain explicit modes;
statistics that require repeated `(subject, simulation, role)` rows keep `ParticipantsField`.

Every workflow that performs one independent job per selected subject exposes the same
`Subjects in parallel` control. `1` means sequential; `N` allows up to N subjects to run concurrently.
The server, not request timing in React, enforces the cap. Generalize `/api/jobs/groups` and its contract
beyond preprocessing for `sim`, `flex`, `ex`, and `mex`, while preserving per-subject config resolution,
group identity, scheduler budget/lock checks, and one job/result record per subject. Group Analyzer jobs
remain one job over the selected cohort and therefore do not show a per-subject concurrency control.

* Gate test: every subject-taking workflow displays the shared selector on first visit. Selecting two
  subjects produces two plan rows. Submitting with a cap of 1 never has more than one group member in
  `running`; submitting with a cap of 2 allows two when resources and locks permit. Each generated config
  contains exactly its own subject id, and the UI never substitutes client-side parallel POSTs for the
  scheduler cap.

## R4 — Use a fixed Ernie guide in workflow 3D panes

Simulator, Optimizer, and Analyzer scene panes stop querying or rendering the first selected project
subject. Add a project-independent, immutable guide scene advertised by the server and derived from
Ernie. Package lean prebuilt skin/GM surfaces, atlas label payloads, legends, and standard EEG-net channel
positions; do not package a full m2m directory or rebuild the guide at runtime. Every bundled atlas and
net is enumerated in the guide manifest and selectable without depending on project data.

The guide remains an interactive helper for net, channel, atlas, and label selection. Actual run
eligibility and config paths are still validated against every selected research subject. Disable
subject-RAS sphere click-to-config in the fixed guide: Ernie coordinates must never be written into a
different subject's configuration. Typed subject coordinates remain available; a later MNI picking mode
requires an explicit space/transform contract.

* Gate test: changing selected research subjects makes zero guide-manifest requests and causes zero guide
  iframe remounts after the initial load. The manifest's atlas/net ids equal the packaged catalog ids, all
  referenced assets resolve, and each surface payload keeps the existing `TVSC1` limit of at most 3 MB and
  150,000 triangles. Electrode/region choices update form names; a guide click cannot update subject-RAS
  coordinates.

## R5 — Make Viewer selection explicit and load on command

The dedicated Viewer keeps subject-specific results, but separates `draftSelection` from
`loadedSelection`. The top source bar adds a view Type selector and conditional selectors for subject,
simulation, analysis, field, atlas, space, ROI, and custom path as the chosen type requires. Catalog calls
may populate menus; they do not build or load a scene.

Changing any selector only edits the draft and marks it dirty. Load validates the draft, snapshots it as
the loaded selection, performs exactly one matching view request, and then posts the returned scene to
the retained iframe. A failed attempt leaves the last successfully loaded scene visible with an error
attached to the attempted selection. Deep links prefill the draft but do not bypass Load. Reload remains
an explicit iframe/runtime recovery action, distinct from loading a new selection.

Add an optional `atlas` parameter to the frozen view API and make `build_view` honor it; absent preserves
the current server-selected atlas behavior. This contract change, generated client, architecture record,
and decision entry land together.

* Gate test: initial Viewer navigation and each draft edit issue zero view requests and zero scene-load
  messages. One Load click issues exactly one request with the visible draft values and one scene-load
  message. Atlas A and Atlas B produce distinguishable requested ids. Failed Load keeps the previous
  scene identity. A deep link fills controls and still issues zero view requests before Load.

## Delivery sequence

1. **Contracts and fixtures:** record dated intent/decision changes; add overview, generic job-group,
   optional atlas, and guide-scene schemas plus deterministic mock fixtures.
2. **Overview:** migrate Subjects, add the aggregate endpoint, remove Subject Info, and update navigation.
3. **Shared terminal:** add source-aware Clear, consolidate log transforms, and prove scroll behavior.
4. **Batch execution:** default-open selectors, generalize job groups, and wire the shared concurrency
   control into per-subject workflows.
5. **Guide scene:** generate and package Ernie guide artifacts, switch run-page panes, and remove unsafe
   subject-RAS picking.
6. **Explicit Viewer load:** add draft/applied state, richer toolbar, atlas contract support, and failure
   retention.
7. **Consolidation gate:** run typecheck, lint, unit tests, hidden E2E/quiet checks, real embed checks, and
   `pnpm run dev` from this directory with an isolated profile.

The terminal work is independent after step 1. Overview UI can proceed against the mock aggregate
fixture while the real catalog endpoint is built. Batch UI and scheduler work should land together.
Guide assets/API must precede scene-pane conversion; Viewer draft state can proceed before atlas support,
but the Viewer gate closes only after both land.

## Risks and fixed decisions

- **Guide provenance and package size:** record the Ernie asset license/source and generate only derived,
  bounded scene artifacts. If redistribution is not permitted, use another redistributable reference
  anatomy without changing the guide API.
- **Coordinate correctness:** fixed-guide subject-RAS picking is disabled, not approximately transformed.
- **Overview scale:** the aggregate endpoint is required; retaining the current fan-out would silently omit
  counts above the existing 25-subject eager limit.
- **Execution truth:** `Promise.all` or sequential POST loops do not constitute scheduler-enforced parallel
  or sequential processing.
- **Deep links:** they prefill but never auto-load, matching the explicit-load requirement.
- **Clear semantics:** Clear is local/presentational and recoverable by changing source or receiving new
  lines; raw logs remain intact.

## Verification commands

```bash
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run e2e:quiet
pnpm run build
```

Real-data/renderer gates remain environment-gated and must report a skip reason when their Ernie guide or
Tetravox bundle is unavailable. Screenshots support review but do not replace DOM, request-count,
scheduler-state, payload, or drawing-buffer assertions.

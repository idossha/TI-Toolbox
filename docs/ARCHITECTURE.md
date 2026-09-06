# TI-Toolbox v3 architecture contract

This file is the contract for the developing desktop application. Deviations require an edit here
and an appended entry in [DECISIONS.md](DECISIONS.md) in the same commit. Section numbers are stable;
do not renumber them. [ROADMAP.md](ROADMAP.md) records verification and remaining work.

## 1. Boundaries and settled stack

| Concern | Owner | Reason |
|---|---|---|
| Scientific computation and project paths | Python `tit/`, typed configs and job runners | Keeps desktop and scripted results on the same implementation; duplicating numerical or path rules in TypeScript would diverge. |
| Host lifecycle | Electron `desktop/src/main/` | Owns project/server connection and native integration; browser components cannot own host processes. |
| Workflow UI | React, shared primitives, tokens and forms in `desktop/src/renderer/` | Uses the existing stack; introducing another component system would make control behavior inconsistent. |
| Rendering | Tetravox embed through the existing message protocol | Dataset parsing and graphics stay in the viewer; another TI renderer would duplicate the same science-facing view. |
| Verification | Vitest and hidden Playwright/Electron runs | State, geometry and drawing-buffer assertions detect failures that a screenshot impression cannot establish. |

Versions and the dependency roster are authoritative in `desktop/package.json` and its lockfile.
The detailed visual contract is [desktop/DESIGN.md](../desktop/DESIGN.md); this document owns the
lifetime and integration guarantees that cross its sections. Native runtime and container procedures
remain in [the desktop manual](wiki/desktop-app.md) and [desktop/README.md](../desktop/README.md).

Non-goals of this polishing change are numerical algorithm changes, a replacement rendering engine,
restoring yesterday's unfinished jobs into forms, and publishing a release. Preserving tabs within an
open project is required; persistence across application restarts is a separate product decision.

## 2. Project and tab lifetime

**A visited tab retains its component tree and iframe until the project session ends.** Tabs mount
on first visit and become hidden and inert on navigation, preserving form drafts, subject choices,
validation, sections, scrolling, nested tabs, camera, layer visibility and rendered data. Rebuilding a
tab from a selected list of serialized fields is insufficient: it omits renderer and transient state.

Collapsing a preview or expanding it over the work pane also hides and inerts the other pane without
unmounting it. Nested source-editor drafts and open dropdown filters survive navigation. Hidden
portals do not cover or capture focus from the active page.

**Only the active page owns page commands, keyboard shortcuts, status cells and subject selection.**
Each visited page retains its own subject context and route parameters. A new page inherits the current
subject; an explicit destination link can replace the destination's selection. Hidden pages cannot
navigate the app, submit a job from a keyboard shortcut, or overwrite the active page's status.

**Project switching clears page memory and disposes retained frames.** Keeping old project drafts or
dataset workers across that boundary risks applying work to the wrong dataset. Retaining a frame's
workers while its tab is hidden is an intentional cost of preserving the user's view.

## 3. Run-page visualization

**Simulator, Optimizer and Analyzer use a viewport-only embed.** The URL opts into
`presentation=viewport`; the embed uses the existing engine and channel but omits its application
toolbar, side panels and status bar. Without the parameter, the dedicated Viewer retains its full UI.
The host must not reach into the embed DOM to hide implementation-specific controls.

**Skin and grey-matter opacity are two explicit controls below each preview.** Percent values map
directly to the protocol's normalized opacity, including fully transparent and opaque endpoints.
Grey matter controls the cortical atlas surface when present. Changing opacity must not reload
geometry, reset the camera, or alter the form's electrodes and ROI.

Manifest/atlas build failures stop polling and remain visible until explicit retry. A stale HTTP 202
must not hide a later error or trigger endless rebuilds. Transport failures retain bounded retries.
When a preview requires an atlas, its first scene waits for that atlas; temporary anatomy must not
race the final scene load and leave duplicate surfaces.

**The run-page panes draw a fixed guide, not the selected subject** (2026-09-05). Their anatomy,
atlas payloads, legends and EEG-net channel positions are packaged with the installation and served
by `GET /api/guide/*`; no query on these pages is keyed on a subject, so changing the selection
costs zero guide requests and zero iframe remounts. A pick names an electrode, a net channel or an
atlas region — never a coordinate. Click-to-place of a sphere centre is removed here rather than
approximately transformed: the guide's space is `guide-ras`, which is no research subject's space,
and a guide coordinate must never be written into a configuration that runs on a different subject.
Typed subject coordinates remain the way a centre is set; a picking mode in a shared space requires
an explicit space/transform contract first. The dedicated Viewer and `GET /api/scene/*` remain the
places subject-specific anatomy is drawn, and there coordinates and picks remain subject-RAS
millimetres as defined by the scene service.

Orientation cues remain visible in the viewport; hiding application chrome must not remove them.

## 4. Controls and conventions

Use the existing UI tokens and primitives. Subject scope comes before parameters; the shared action
bar keeps the primary action in a predictable position. Labels and blocked-action reasons remain
readable, long selections cannot push controls outside their pane, and dropdowns fit their viewport.
Keyboard names belong on interactive nodes, including checkbox rows and slider thumbs.

Ordinary controls use the 28px token; workflow run actions use 32px, including Source's two in-card
pipelines. The larger primary action must not depend on a page inheriting an accidental button default.

No new dependency is required. A future dependency change requires a decision entry and a regenerated
lockfile. Commit titles state the defect or resulting behavior; no AI co-author trailers.

## 5. Verification and frozen interfaces

The [2026-09-04 requirements](requirements/2026-09-04-maintainer-polish.md) and the
[2026-09-05 requirements](requirements/2026-09-05-overview-batch-viewer.md) define the observable
gate; where they conflict, the later one wins.
`desktop/tests/e2e/page-memory.spec.ts` holds tab continuity;
`desktop/tests/e2e/scene-pane.spec.ts` holds protocol/opacity integration;
`desktop/tests/e2e/overview.spec.ts`, `terminal.spec.ts`, `batch.spec.ts`, `guide.spec.ts` and the
R5 cases in `viewer.spec.ts` hold §6's four seams;
the real-embed rendering check holds viewport and rendering behavior. Shared-control and token tests
hold the visual system. Tests run hidden with a fresh profile and record actual assertions and skips.
The quiet-check script must report its sampling result; an unavailable check is not a pass.

Frozen interface paths are `desktop/src/renderer/viewer/protocol.ts`,
`desktop/src/shared/tit-bridge.d.ts`, and `contracts/`. Changes require this contract and the decision
log in the same commit. For optional additions, absent reproduces the previous behavior. This is a
review requirement until a dedicated CI guard exists; local verification alone does not claim that
all release-platform CI or real scientific workflows have passed.

## 6. Project overview, batch execution, the shared terminal, the guide and the Viewer

*Added 2026-09-05; refines §§2–5 and reverses the landing-page and subject-coupled-scene rules of
desktop/DESIGN.md §§9–10. Rationale in [DECISIONS.md](DECISIONS.md).*

**`GET /api/catalog/overview` → `Overview` is the project Overview page's single read.** It is the
one catalog endpoint that aggregates across subjects; every other catalog route stays per-subject
and lazy. Server-side aggregation is required, not an optimisation: a client-side fan-out cannot
state a project-wide count without a per-subject request budget, and the fan-out it replaced was
capped at 25 subjects in the renderer. `PresenceState` (`present`, `absent`, `partial`, `pending`,
`failed`) is the vocabulary for "does this subject have X"; what is on disk always wins, and
`pending`/`failed` come from the job records and only ever describe an artefact that is still
absent. Overview carries counts, never trees or previews — Results remains the only detailed
outputs browser. `GET /api/catalog/subject-info` stays in the contract until the API's next
versioned cleanup; `_VALID_PANELS` keeps accepting `"subject-info"` so an existing project
`settings.json` still loads, and the registry ignores an id no page claims.

**`/api/jobs/groups` is the batch seam for every per-subject kind** (`pre`, `sim`, `flex`,
`flex_adaptive`, `flex_pareto`, `ex`, `mex`). The request carries one template `config` plus
optional `subject_configs` for workflows whose config depends on the subject, and optional `tags`
and `overwrite`. The server forces each generated config's `subject_id` to its own subject, so
subject isolation is a server guarantee and not a client convention, and
`tit.jobs.scheduler.evaluate` enforces `parallel_subjects` as an admission cap on how many of the
group's jobs are `running`. A `Promise.all` or an awaited POST loop is not an implementation of
sequential or parallel execution. Cohort kinds (grouped `analyzer`, `stats`) stay on
`POST /api/jobs`: one job, no cap. The cap counts *jobs*, not distinct subjects.

**One interactive log renderer, one pure transform.** `app/jobs/logLines.ts` is the single
event→line and sequence-merge module; `ui/Jobs.tsx::JobConsole` is the single interactive log
renderer for the run pages, the Jobs rail and the gallery. Its Clear is a per-source sequence
watermark over the caller's array: local, presentational and recoverable, never a deletion of
server events or a truncation of a log file. Jobs-detail `<pre>` excerpts remain diagnostic
records, not terminals.

**`GET /api/guide/{manifest,surface,labels,regions,electrodes}` serve a fixed, immutable guide
scene** packaged with the installation and derived from one reference head. They take no subject,
require no project and never build; responses are content-addressed (`ETag` = the file's SHA-256,
`Cache-Control: immutable`). Their coordinate space is `guide-ras`, which is not a research
subject's space; a guide coordinate is never written into a configuration. Every bundled atlas and
net is enumerated in the manifest and selectable without project data, and each packaged surface
stays inside the frozen `TVSC1` budget of 3 MB and 150,000 triangles. Run eligibility and config
paths are still validated against every selected research subject. The guide assets are declared in
`pyproject.toml`'s `[tool.setuptools.package-data]` so an installed wheel can serve them.

**`GET /api/view/{kind}` accepts an optional `atlas`** naming which atlas overlay the scene should
carry: an id from `GET /api/catalog/atlases` for the same subject and space, or a bundled MNI
atlas's basename. Omitting it preserves the server-selected atlas exactly, and an id that resolves
to nothing available falls back to that same choice rather than failing the request. The parameter
changes which layer is built and adds nothing to the ViewSpec, so
`contracts/tetravox-viewspec-v2.schema.json` is unchanged.

**The Viewer loads on command.** It keeps a draft selection (what the source bar shows) separate
from a loaded selection (what the embed is drawing). Editing a selector changes only the draft;
Load validates it, snapshots it, issues exactly one view request and posts exactly one scene to the
retained iframe. A failed load keeps the previously loaded scene on screen with the error attached
to the attempted selection. Deep links prefill the draft and never auto-load. Reload remains
iframe/runtime recovery for the *loaded* scene, not the draft.

## 7. The Tetravox update channel, pipelines, the selection grammar and the electrode contract

*Added 2026-09-05 (second batch); refines §§1–6. Requirements:
[2026-09-05 Tetravox/selection/pipeline](requirements/2026-09-05-tetravox-selection-pipeline.md).
Rationale in [DECISIONS.md](DECISIONS.md).*

### 7.1 The embed bundle has two delivery paths and one rule

The image bakes a floor (`/opt/tetravox/embed`), resolved at build time from the newest Tetravox
release whose embed manifest's `protocol` is inside the range `tit/tetravox/protocol.py` declares;
the server may install a newer release into the user-config root at runtime, under the same rule.
**The rule — a protocol range plus named features, never a version — is the only coupling between
the two projects.** A release past the range is reported, never installed: the honest answer is
"update TI-Toolbox to use it", and it is given without downloading the tarball.

The index is the **GitHub Releases API** of `idossha/tetravox`, not a file anyone must remember to
commit. A release is incorporable iff it carries all three assets

```
tetravox-embed-<X.Y.Z>.tgz            tetravox-embed-<X.Y.Z>.tgz.sha256            tetravox-embed-<X.Y.Z>.manifest.json
```

where `<X.Y.Z>` is the release tag without its leading `v`, the `.sha256` is in `sha256sum` format,
and the manifest is a byte-for-byte copy of the one inside the tarball
(`{name, version, protocol, sha}`). `protocol` is read from the manifest **asset**, so compatibility
is answerable for about 2 KB. `TIT_TETRAVOX_RELEASE_INDEX` overrides the index for air-gapped
mirrors and accepts either the GitHub shape or a plain one; `api.github.com` is on the download
allowlist. A release carrying no embed asset is "not incorporable", not an error.

`GET /api/tetravox/updates` answers from a cache the server's own background pass refills — a
rendered Settings card costs no GitHub request, `?refresh=true` is the button. `POST
/api/tetravox/policy` carries `auto_update` (default **on**), stored in `<install root>/policy.json`
because it is a property of the install root, not of the bound project. "Off" stops the installing,
not the knowing. **"Newer" is measured against the newest bundle this updater installed from a
release** (its recorded provenance), never against whatever bundle is active, so a hand-installed
dev bundle numbered ahead of every real release cannot freeze the updater. `/ws/tetravox` carries
the single app-level `tetravox.updated` event; `contracts/events.schema.json` is unchanged, because
it describes one line of a job's `events.jsonl` and no job emits this.

**Compatibility matrix.** This build supports embed protocol **1–2**: 0.3.4 (the baked floor,
protocol 1) and every Tetravox release from 0.3.12 onward (protocol 2), plus the dev container's
hand-installed 0.4.0-dev. Protocol 3+ is listed with `compatible: false` and outcome `unsupported`;
raising `SUPPORTED_PROTOCOL_MAX` is one constant that a cross-language test keeps in step between
Python and `container/blueprint/build.sh`. Named features are unchanged: `volumes, meshes, cursor,
probe, screenshot, layers` at protocol 1; `markers, pick, camera` at protocol 2; a manifest's own
`features` array always wins.

### 7.2 The points layer is the electrode contract

`EmbedPointsLayer` gains `dotRadiusPx` and `labelColorSource`; `EmbedPoint` gains `radiusPx`. All
additive within protocol 2. A point's own `color` takes precedence over `stateColors`, and in the
bundles shipped so far a point whose `state` is `idle` is never state-coloured at all — so a host
that wants per-point colour must write it on **every** point, idle ones included. A point with no
`name` draws no label, which is how "labels for the selection only" is expressed. `dotRadiusPx` is
read from the layer, not the point, and until Tetravox 0.3.12 it reaches the 2-D slice pass only, so
a `3d-only` pane draws millimetre spheres whatever `shape` says. The run-page pane sends neither
`setPointTool` nor `setPointSelection`, which are the only messages that draw a selection ring.

### 7.3 Pipelines

A **pipeline** is a directed acyclic graph whose nodes are existing job kinds and whose edges are
typed bindings between one node's named output and another node's same-named input. Its wire form is
`contracts/pipeline.schema.json` (`version: 1`); it is stored in the project at
`code/ti-toolbox/pipelines/<name>.json`.

1. *A pipeline introduces no job kind.* Every `PipelineNode.kind` is a member of
   `tit.jobs.spec.JOB_KINDS`, and its `config` is the same shape the matching page already builds.
2. *A pipeline run is one job group.* `POST /api/pipelines/run` performs exactly one
   `JobManager.submit_plan`; every job carries the one returned `group_id`, and every job's `after`
   is the document's edges resolved to real job ids. There is no second executor and no client-side
   sequencing, so cancel, the scheduler's group cap, the jobs rail, the events stream and the log
   tail work on a pipeline for free.
3. *Port types are a closed set*: `subjects | montages | simulation | roi | leadfield`. An edge joins
   two ports of the same type or it is refused with a reason.
4. *Validation answers, it does not throw.* `POST /api/pipelines/validate` returns 200 with
   `ok: false` and one issue per problem; 422 means the body is not a pipeline document.
5. *Bindings are static where possible and a `resolve` job where not.* `subjects`, `roi` and a
   `simulation` whose producer names its own montages are written into the downstream config at
   submit time. `montages`, `leadfield` and an optimizer-fed `simulation` only exist once the
   producer has run, so one `tools` job (`tit.tools.pipeline_resolve`) is planned between producer
   and consumer; it writes what it found to
   `code/ti-toolbox/pipelines/runs/<pipeline>/<node>.<port>.json`, and the consumer — which carries
   that project-relative path in its config under `tit.jobs.bindings.BINDINGS_KEY` — has it merged
   into its runner `config.json` by `JobManager._runner_config_path` at **admission**, the first
   moment the file can exist. A resolve step that found nothing leaves the field as the canvas set
   it; the job then fails exactly as it would with the field left blank on the page.
6. *Export is a pure function of the document.* `POST /api/pipelines/export` reads no project state
   beyond the project directory it prints into the setup cell, emits only calls the public `tit`
   scripting API documents, and round-trips the document through `metadata.ti_toolbox.pipeline`.

**Non-goals.** A workflow engine (retries, conditionals, loops, per-node scheduling policy);
importing arbitrary hand-edited notebooks; drag-to-reorder.

### 7.4 One selection grammar

Anything chosen out of a set is `ui/SelectionList` — subjects, montages, ROI regions, electrodes,
participants, jobs. Click selects one, ⇧-click takes the range, ⌘/Ctrl-click toggles, ⌘A takes what
the filter is showing, Esc clears it; a checkbox column is the visible form of the same toggle; the
filter is always on; `All · None` are the only bulk buttons and act on the **visible** rows, so a
row the filter hides keeps its state; one `N of M selected` badge is the only place the count is
stated. Selection order is submission order. A row that cannot be used keeps its checkbox and states
its reason; `bulkExclude` keeps it out of `All` so a bulk convenience cannot create a blocked run.
Where a field has no room for a list, `SelectionPicker` puts the same list behind a trigger that
states the selection in words. There is no second selection idiom, no drag-to-reorder and no
per-item options.

Every run page ends its work column with `pages/_shared/run/Receipt`, rendered through
`PageLayout`'s `receipt` slot — outside the work scroller, between it and the action bar, so a
confirmation can never overlay the form it confirms. It is derived from the same `PlanModel` as the
plan grid and the action bar's digest, so the three cannot disagree: the grid is the detail view,
the receipt is the confirmation, and it is adjacent to the button. Existing outputs are one question
with three answers on every run page — `ExistingOutputsDialog`: Skip (default) / Replace and rerun /
Cancel.

The rail's ⌘-number is the page's index in `registry.ts`'s `NAV_ORDER`, and Settings takes the first
digit the rail does not (`⌘0` since the Pipeline row landed; `⌘,` remains its alias). The `?` sheet
and the Help page both derive their rows from that list rather than restating it.

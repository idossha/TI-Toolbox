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

**Simulator, Optimizer and Analyzer draw their own pane** (revised 2026-09-06, §7.2): the app's
WebGL2 renderer, not an embedded copy of another application. The rule the retired
`presentation=viewport` embed existed to satisfy is now structural — the pane draws only what the
workflow needs, so there is no application chrome to hide and no foreign DOM to reach into.

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

**The Viewer selects on command** (revised 2026-09-06, §7.1). It keeps the draft → command grammar:
editing a selector changes only the draft, and the Menu's **Open in viewer** validates it, snapshots
it and issues exactly one `POST /api/view/open`. That one call resolves the scene once and returns
both addressings of it: the URL form is posted into the embed and the page moves to the Viewer
sub-page, and the host form is written to `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`. A
failed Open leaves the Menu's summary on screen with the error attached to the attempted selection.
Deep links prefill the draft and never auto-open.

## 7. The viewer, the run-page renderer, pipelines and the selection grammar

*Added 2026-09-05 (second batch); refines §§1–6. §§7.1–7.2 were **replaced on 2026-09-06**: §7.2
makes the run-page panes this app's own renderer, and §7.1 was replaced twice that day — the embed
was retired in the morning and restored in the afternoon (ADR row 28). Requirements:
[2026-09-05 Tetravox/selection/pipeline](requirements/2026-09-05-tetravox-selection-pipeline.md),
[2026-09-06 native panes / external viewer](requirements/2026-09-06-native-panes-external-viewer.md).
Rationale in [DECISIONS.md](DECISIONS.md).*

### 7.1 The viewer is the Tetravox embed, and it ships in the image

*Replaced 2026-09-06 (second revision, same day). The morning's text made viewing a
host-installed Tetravox desktop app launched by Electron main; the maintainer reversed it the
same afternoon. See [DECISIONS.md](DECISIONS.md), ADR row 29.*

TI-Toolbox's viewer is **Tetravox Embed** — a browser build of the Tetravox engine, WebGL2 +
WASM, drawn by the Electron renderer on the host GPU inside a same-origin `<iframe>`. It is
part of the image and part of the app; **no Tetravox is installed on the user's machine, and
there is no X11 anywhere** (D3). The container has no display, which is exactly why the embed
is the only Tetravox that can draw inside this app: an application baked into the image would
have nothing to draw on, and one installed on the host would be a second install for the user
to acquire and a second window for them to manage.

**The bake is the floor.** `container/blueprint/Dockerfile.ti-toolbox` writes the bundle to
`/opt/tetravox/embed` (`ServerSettings.tetravox_embed_dir`'s default). What it bakes is resolved
at build time from the newest non-draft, non-prerelease `idossha/tetravox` release carrying
`tetravox-embed-<v>.tgz`, its `.sha256` and its `.manifest.json`, whose manifest `protocol` is
inside the range this checkout supports; the tarball is sha256-verified before it is unpacked.
A build that resolves nothing writes a placeholder and says so — an image with no bundle is a
normal state, not a build failure, because the runtime channel can supply one.

**`tit.server` serves it at `/tetravox/`** (`tit/server/static.py`), with its own
Content-Security-Policy on that route only — `script-src 'self' 'wasm-unsafe-eval'` for the
engine's Rust→WASM module and `worker-src 'self' blob:` for its dataset workers. The app's own
top-level page carries neither. `tetravox` is a reserved prefix, so the SPA catch-all never
answers for it. Resolution is per request: the `--tetravox-dir` override, then the pinned or
newest compatible installed bundle, then the baked one.

**The protocol range is the only coupling between the two projects, and it is never a version.**
`tit/tetravox/protocol.py` declares `SUPPORTED_PROTOCOL_MIN`/`MAX` (1–2 today) and a map of
*named* features (`volumes`, `meshes`, `markers`, `pick`, `camera`, …) to the protocol that
first carried them; `desktop/src/renderer/viewer/embedProtocol.ts` is its renderer twin, and
`tests/test_tetravox_protocol.py` reads both files off disk and fails if they disagree. A pane
asks `embedCan(caps.tetravox_embed, "markers")` — a name, never a number — and a bundle's own
manifest `features` array wins when it has one. An **additive** Tetravox release therefore needs
no TI-Toolbox change at all; a breaking one needs `SUPPORTED_PROTOCOL_MAX` edited in two files
the cross-language test keeps in step.

**Two delivery paths, one rule.** The image bakes a floor so an offline or air-gapped install
works with nothing fetched; bundles installed at runtime live under the user config directory
(`<install root>/<version>/`, `tit/tetravox/store.py`). The rule is the same on both sides —
newest release whose manifest protocol is in range — so "what a fresh image ships" and "what a
running install would update itself to" cannot disagree about which release is incorporable.

**The update channel** is `tit/tetravox/{protocol,store,install,updates}.py` behind
`GET /api/tetravox`, `GET /api/tetravox/updates`, `POST /api/tetravox/{policy,install,activate}`
and `DELETE /api/tetravox/{version}`. The index is the GitHub Releases API. A download is
verified against its sha256 before the archive is opened, extraction refuses absolute paths,
`..` and links (Python 3.11's unfiltered `extractall` writes outside the destination — measured
in this image, `dev/notes/v3-embed-convergence/u-notes.md`), the manifest's protocol must be in
range, and activation is one atomic rename, so a half-extracted bundle is never served. The
policy (`auto_update`, **default on**) is stored at `<install root>/policy.json`; the lifespan
task checks at startup and every 24 h (`CHECK_INTERVAL_S`), never on the path to a render, and
publishes exactly one event, `tetravox.updated`, on `/ws/tetravox`. A pin (`active.json`,
`"baked"` a legal value) makes rollback a click rather than a re-download.
`GET /api/capabilities` carries `tetravox_embed`: the active bundle's version, protocol, source,
resolved features and whether it is compatible — a fact about *this runtime*, which is what a
capability is.

**The Viewer page is two sub-pages behind one rail entry** (Viewer, ⌘8):

- **Menu** — the composition page: a Source card and an editable "What will open" list, plus
  presets and Recents. Its primary button is **Open in viewer**.
- **Viewer** — full-bleed, hosting the embed iframe, with a slim top strip: the scene name,
  `Reload` (re-posts the current scene) and `Back to menu`.

They are a page-level segmented sub-nav, not a rail group: `desktop/src/renderer/app/registry.ts`
derives a **flat** rail from `NAV_ORDER` with one `PageDef` per `pages/<name>/index.tsx` and has
no nested-group model. It also makes §2's retention rule trivially true — the two sub-pages are
one mounted component, so switching between them never unmounts the iframe.

**One request, one message.** Open calls `POST /api/view/open` once. That route resolves the
scene **once** (`tit.viewspec.build_view`) and returns both addressings of it: `view`, with every
dataset an `/api/files/raw/…` URL, which is what is posted into the iframe; and `scene`, the same
document with every path re-rooted onto the host, which is also written to
`<project>/code/ti-toolbox/viewer/<kind>.tetravox.json` so it can be exported or opened by a
desktop Tetravox. They come from one resolution on purpose: two calls could resolve differently
— a job finishing between them is enough — and then the list the page shows, the file on disk and
the scene on screen would disagree, with nothing to say which was right. Returning to the Menu
without pressing Open shows the same scene on the way back; Open again replaces it. Deep links
`/viewer?…` prefill the Menu only.

**What this replaces.** The morning's §7.1 said "the viewer is a separate application, and the
only interface is a file", and deleted the bake, `/tetravox/`, `tit/tetravox/**`, the protocol
range, the release index, the install store, `/ws/tetravox` and `Capabilities.tetravox_embed`.
The maintainer reversed it, verbatim: *"The Dockerfile should contain Tetravox. We should not
install Tetravox on the host machine — forbidden."* The scene file stays: it is a real artefact
in the user's own project, and it is the export path and the desktop-Tetravox path. What is
restored is the renderer that made this app able to show a result without asking the user to
install anything.

### 7.2 The run-page panes are our own WebGL2 renderer

*Replaced 2026-09-06; the previous text was the embed's points-layer contract, and reverses §3's
`presentation=viewport` embed rule and the electrode-dot clauses of the 2026-09-05 batch.*

The Simulator, Optimizer and Analyzer 3-D panes are rendered by `desktop/src/renderer/scene/`, a
WebGL2 renderer with no runtime dependency, no iframe and no message protocol. It draws two
translucent surfaces, screen-space point markers and a labelled region highlight, and picks either
through a colour-id pass cross-checked against its own CPU projection. It consumes the packaged
guide over `GET /api/guide/{manifest,surface,labels,regions,electrodes}`; surfaces and labels are
`TVSC1` (`?format=tvsc`), and the labels payload is the `gm` positions plus their `uint16`
per-vertex labels, pinned by a test to be *aligned* to the `gm` surface rather than merely present.

**An electrode's colour is its whole state.** Neutral grey in no channel, 35 % grey when unusable,
its channel's Okabe-Ito hue when placed. No ring, no outline, no second glyph — a selected marker's
footprint is byte-identical to an idle one's, which is what makes "no ring" a pixel assertion
(a solid disc that reaches zero and stays zero) rather than a claim about which message was not
sent. The palette is six hues, not four, because mTI runs to four pairs and a wrap should not repeat
before it must.

**The atlas is interactive, and there is one selection.** The pane carries its own atlas selector
over the packaged atlases, hover names the region under the cursor, and a click adds or removes it
from the ROI the form holds. `<ScenePane>` and `<RoiPicker>` edit the same list through the same
`regionKey`/`toggleRegion`: a 3-D click and a form chip are one selection, in both directions, not
two toggles that agree today. Sphere targets keep typed coordinates only — §3's rule stands, and the
guide's `guide-ras` is still no research subject's space.

### 7.3 Pipelines

A **pipeline** is a directed acyclic graph whose source is a `subjects` node naming the cohort, whose
other nodes are existing job kinds, and whose edges are typed bindings between one node's named
output and another node's same-named input. Its wire form is `contracts/pipeline.schema.json`
(`version: 1`); it is stored in the project at `code/ti-toolbox/pipelines/<name>.json`.

1. *A pipeline introduces no job kind.* Every `PipelineNode.kind` but `subjects` is a member of
   `tit.jobs.spec.JOB_KINDS`, and its `config` is the same shape the matching page already builds.
   `subjects` is the one node that is not a job: it names who the graph is about and plans nothing.
1a. *The cohort is stated once, and a node is never configured from the node upstream of it.* The
   subject list lives on the `subjects` node and reaches the rest of the graph over the `subjects`
   port; no processing node carries a copy, so two nodes in one graph cannot disagree about who is
   in the study. An edge carries **one named value and nothing else** — `Optimizer -> Simulator` on
   `montages` means "this Simulator's montage list is that flex result" and says nothing about any
   other setting of either node.
2. *A pipeline run is one job group.* `POST /api/pipelines/run` performs exactly one
   `JobManager.submit_plan`; every job carries the one returned `group_id`, and every job's `after`
   is the document's edges resolved to real job ids. There is no second executor and no client-side
   sequencing, so cancel, the scheduler's group cap, the jobs rail, the events stream and the log
   tail work on a pipeline for free.
3. *Port types are a closed set*: `subjects | montages | simulation | roi | leadfield`. An edge joins
   two ports of the same type or it is refused with a reason.
3a. *A `subjects` edge is additionally gated on readiness.* `tit.pipeline.validate.KIND_READINESS` is
   the single table of what each kind **requires** of a subject and what it **produces** for the
   nodes after it, over a closed set of capabilities — `raw | m2m | leadfield | simulation` — read
   from the same aggregate the Overview page shows (`GET /api/catalog/overview`). A wire is legal
   only when **every** subject on it has what the target requires; the refusal names the subjects
   that do not ("102, test have no head model"), never a count. `produces` is what lets a chain
   satisfy a requirement its cohort does not: `Subjects(raw) -> Pre -> Simulator` is legal because
   `pre` produces `m2m`, while `Subjects(raw) -> Simulator` is not. The table is served to the
   canvas at `GET /api/pipelines/kinds` so a **drag** can be refused before any graph exists, and
   applied again inside `POST /api/pipelines/validate` and `/run`, so the drag-time refusal and the
   receipt are the same sentence from the same definition. A project that cannot be read falls back
   to checking shape only rather than refusing every wire.
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

### 7.5 A run page that submits many jobs describes them as a table

*Added 2026-09-06; refines §7.4 and removes the subject-set × montage fan-out from the Simulator and
the Analyzer.*

*Extended 2026-09-06 to the Optimizer, which makes it all three run pages.*

**One row is one job**, and the row owns every input that differs between jobs: the Simulator's row
is `Subject · Source · EEG net · Montage · Pairs · Currents`, the Analyzer's is
`Subject · Simulation · Space · Field`, and the Optimizer's is
`Subject · Method · Net / leadfield · Goal` over a target line. The Optimizer's row carries the four
sections that page used to hold globally — target, objective/electrodes, solver and the subject
table — because every one of them is a property of a *search*, and a search is a row. Two clauses
follow from that page and hold everywhere:

* **A row may be a different KIND of job.** Where a page's rows submit as more than one kind, one
  Run is one submission *per kind* (`POST /api/jobs/groups` takes one `kind`), and the page says so
  rather than implying a single atomic batch.
* **A cell with nothing to decide says so.** A column meaningless for a row's method prints a muted
  `—` with the reason in its title, never a disabled control that reads as a choice the user has
  failed to make. A page with a jobs table therefore has **no page-level
subject control** — §7.4's grammar applies inside the subject cell, where a subject that cannot run
here is listed with its reason and cannot be picked. Properties of the *run* rather than of a job —
electrode geometry, conductivity, output fields, the analysis ROI — stay page-level sections.

The cross-product the page used to be is now something the user asks for: **Duplicate**, the row's
own action, is the one gesture for "the same job, another subject", and the user changes the cell
that differs. (The earlier `Add job for each ready subject` / `Quick add` buttons were specified and
then not built: one explicit gesture proved to be enough, and `analyzer.spec.ts` asserts the Quick
add control is absent so the two do not drift back apart.) A half-filled row is shown and is not
planned — one predicate is the gate between visible and submitted. A group is a **switch over the
same rows**, not a mode with its own selection: the rows name the cohort, and rows that disagree
about what a cohort job can only do once are refused with the reason on the button rather than
silently resolved to the first row's answer. Submitting does not empty the table.

What runs is unchanged: one `POST /api/jobs/groups` with `subject_configs`, one config per row
carrying its own subject, and §7.4's shared existing-outputs question.

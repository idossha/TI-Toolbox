# Desktop architecture decisions

Current rules live in [ARCHITECTURE.md](ARCHITECTURE.md); this append-only log records why.

## 2026-09-04 — Tabs retain their live page and renderer

**Decision.** Architecture §2 retains visited pages for the project session and isolates their subject
and route context. Inactive pages relinquish commands, keyboard actions and status ownership.

**Why.** The production PyQt main window creates each tab once. The v3 route outlet instead removed
the page, destroying its iframe and camera even where a session bag restored some form values.
The maintainer made unchanged state across tab changes a non-negotiable requirement (R1).

**Alternatives rejected.** Serializing a growing list of form fields misses validation and viewer
state. The older embed plan's visible-only lifetime released WASM memory but violated navigation
continuity. Project changes still dispose frames; this decision does not retain past sessions.

## 2026-09-04 — Preview controls belong to the workflow

**Decision.** Architecture §3 uses optional `presentation=viewport` for embedded run-page scenes,
and exposes skin/grey-matter opacity through the existing layer protocol. The full Viewer is the
default when the parameter is absent.

**Why.** Full Tetravox application controls consume the small scene pane and duplicate workflow
decisions. The missing opacity controls made the skin and cortex harder to inspect (R3).

**Alternatives rejected.** Reintroducing a second rendering engine duplicates graphics logic.
Host-injected CSS would couple TI to private viewer DOM. A default-changing embed option would also
strip controls from the dedicated Viewer. The additive presentation option avoids that coupling.

## 2026-09-04 — Existing primitives govern control consistency

**Decision.** Architecture §4 keeps the existing token system and makes shared controls contain long
values, carry accessible names and reserve a consistent primary-action position (R2).

Workflow run actions explicitly use the 32px primary token, including Source's two in-card
pipelines; ordinary controls use 28px. This preserves the same hierarchy with or without an action bar.

**Why.** Separate page variants would repeat the same layout and accessibility defects. No new
dependency or scientific configuration format is introduced by this pass.

Verification results are recorded in [ROADMAP.md](ROADMAP.md) after the commands run.

## 2026-09-04 — Preview build failures require explicit retry

**Decision.** Architecture §3 stops manifest/atlas polling on HTTP failure and offers an explicit retry.
Bounded automatic retries remain for transport failures.

**Why.** The server reports an asynchronous build error once, then consumes it. An automatic retry
starts another build and can return HTTP 202 again; that success resets the retry counter and hides
the underlying failure forever. The real atlas mesh-index bug exposed this loop. Keeping the error
visible prevents repeated work and gives the user the actual reason the preview is unavailable.

The preview also waits for a required atlas before sending its first scene. Loading temporary
anatomy and then the atlas concurrently left duplicate skin/cortex layers in the live renderer;
the atlas-ready gate removes that dependency race without changing the scientific data.

## 2026-09-05 — The app opens on a project Overview, and Subject Info is deleted

**Decision.** Architecture §6: the first rail item, the ⌘1 target, the initial route, the catch-all
destination and the palette's first page are `overview`. The Subjects page is its starting
implementation, reshaped to answer the project question rather than the per-subject one. Its facts
come from one `GET /api/catalog/overview` whose request count does not grow with subjects,
simulations or outputs. Presence is five distinguishable states (`present`, `absent`, `partial`,
`pending`, `failed`). The Subject Info panel, its page id, its Settings toggle and its fixtures are
removed; `/panel-subject-info` falls through to `/overview` and a stale saved panel id is ignored.

**Why.** The maintainer's first ask (R1). The fan-out Overview replaces was capped at 25 subjects in
the renderer, so a larger project silently rendered no counts at all — server-side aggregation is
correctness, not speed. "Staged but not converted", "running right now" and "the last run failed"
are three different answers that one boolean swallowed.

**Alternatives rejected.** Keeping the per-subject fan-out behind a higher cap moves the cliff
without removing it. Removing `GET /api/catalog/subject-info` from the contract is breaking and
belongs to the API's next versioned cleanup; it stays, unused.

## 2026-09-05 — Terminal Clear is presentational, not destructive

**Decision.** Architecture §6: one interactive log renderer (`ui/Jobs.tsx::JobConsole`) over one
pure transform (`app/jobs/logLines.ts`), with a source-aware Clear implemented as a per-source
sequence watermark over the caller's array.

**Why.** The maintainer asked for a scrollable, clearable terminal whose logic is shared between
pages. A Clear that spliced the array would destroy the record the console exists to show, and
would differ from what the log file and the event stream say.

**Alternatives rejected.** Truncating the log file, or dropping server events, makes Clear
irreversible and makes the console disagree with `Reveal log file`. Per-page terminal
implementations were what produced two copies of the event→line conversion in the first place.

## 2026-09-05 — Batch execution is a scheduler cap, not renderer request timing

**Decision.** Architecture §6: every workflow that runs one independent job per subject submits one
`POST /api/jobs/groups` with `parallel_subjects`, and `tit.jobs.scheduler.evaluate` enforces it as
an admission cap. `JobGroupRequest.kind` widens beyond `pre` to `sim`, `flex`, `flex_adaptive`,
`flex_pareto`, `ex`, `mex`, and grows optional `subject_configs`, `tags` and `overwrite`. Cohort
kinds (grouped `analyzer`, `stats`) stay on `POST /api/jobs` — one job, no cap.

**Why.** Simulator, Optimizer and Source submitted a batch as an awaited `for` loop of
`POST /api/jobs`. That loop names a policy and decides nothing: the server admitted whatever its
budget allowed the moment each job landed, so "sequential" described the renderer's `await`, not
what ran. The maintainer asked for parallel *or* sequential processing over a multi-subject
selection, which is a scheduler property.

**Alternatives rejected.** A client-side semaphore around `Promise.all` still cannot see the
scheduler's budget or the directory locks, and dies with the window. Per-subject POSTs with a
`group_id` tag would leave the cap unenforced on the only side that can enforce it.

**Known limit.** The cap counts jobs, not distinct subjects: on the Simulator, one subject with
three montages is three jobs, so a cap of 2 can run two montages of the same subject together.
`tit.jobs.locks` is what keeps that safe, and the control's help says "jobs", not "subjects".
Subject-count semantics would be a scheduler change plus a contract note.

## 2026-09-05 — The workflow 3D panes draw a fixed guide, not the selected subject

**Decision.** Architecture §3 and §6: Simulator, Optimizer and Analyzer panes draw a packaged,
immutable guide served by `GET /api/guide/*`, derived from the SimNIBS example subject `ernie`
(GPL-3.0, redistribution permitted; see `tit/scene/guide/PROVENANCE.md`). The click-to-place sphere
gesture is removed from these panes.

**Why.** The maintainer asked for "a general individual, for example, Ernie". Coupling the pane to
the first selected subject re-keyed three queries on every selection change — a cache-cold 184 MB
mesh extraction and a remount for ticking a second subject — and let one subject's anatomy produce
a subject-RAS coordinate written into a *different* subject's configuration. 15.5 MB of derived,
bounded artifacts replace a per-project 184 MB read.

**Alternatives rejected.** Transforming a guide pick into the target subject's space approximately
is exactly the silent-wrongness this removes; a real picking mode needs an explicit space/transform
contract. Rebuilding the guide at runtime, or packaging a whole `m2m` directory, gives up the
"immutable, no build, no project" property that makes the pane free.

## 2026-09-05 — The Viewer loads on command, not on selection

**Decision.** Architecture §6: the Viewer keeps a `draftSelection` separate from a
`loadedSelection`. Editing a selector changes only the draft; **Load** validates it, snapshots it,
issues exactly one view request and posts exactly one scene to the retained iframe. A failed load
keeps the previously loaded scene with the error attached to the attempted selection; deep links
prefill and never auto-load; Reload remains iframe/runtime recovery for the loaded scene. Also
decided: `GET /api/view/{kind}` takes an optional `atlas`; absent is the previous behaviour and an
unresolvable id falls back to it rather than 404-ing.

**Why.** The maintainer asked for more selectors in the top bar and for the page not to load on
subject selection. Deriving the request from the controls meant every incidental change — a subject
switch in the shell, a space toggle, a half-finished pick — tore down a scene that had cost minutes
to load, and a transient server error replaced the picture with an error card. Explicitness costs
one click and buys back the image you already have and the knowledge of which selection produced it.

**Alternatives rejected.** Debouncing the auto-load keeps every failure mode and adds a race.
404-ing an unknown `atlas` turns a stale bookmark into no picture at all. The atlas menu offers the
voxel atlases only: FreeSurfer `.annot` cortical parcellations are surface data and would silently
resolve back to the default.


## 2026-09-05 — The Tetravox release index is the GitHub Releases API, and the pin is a protocol range

**Decision.** Architecture §7.1: TI-Toolbox never names a Tetravox version. It pins a protocol
range plus named features, and asks the GitHub Releases API of `idossha/tetravox` whether a newer
*compatible* release exists, reading `protocol` out of the published `tetravox-embed-<v>.manifest.json`
asset. A release whose protocol is past the range is reported — "update TI-Toolbox to use it" — and
never downloaded. `TIT_TETRAVOX_RELEASE_INDEX` stays for air-gapped mirrors and accepts either
shape; `api.github.com` joins the download allowlist. The image bake resolves the newest compatible
release by the same lookup, in bash and stdlib Python, so a fresh image never ships a placeholder.

**Why.** The E-series specified a `releases.json` committed to the Tetravox repo; it never existed
and 404'd for the whole of the previous lane's live run. A file someone must remember to commit is
an index that goes stale silently, and the API is written by the release itself. Reading the manifest
*asset* means "can this build host it?" costs about 2 KB instead of a 6 MB tarball, so the protocol
check happens **before** the download and the user reads A1's sentence rather than the installer's.

**Alternatives rejected.** Comparing version numbers couples two release trains that have no reason
to move together. Downloading first and letting the installer refuse spends 6 MB to produce a worse
message. An authenticated request would put a credential this app must then protect into a config
file, for a public repo's public releases; unauthenticated 60 req/h is ample for one check per start
plus one per day, and a 403 is "could not check", not an error dialog.

## 2026-09-05 — Tetravox updates install themselves by default, and "newer" means newer than what we installed

**Decision.** Architecture §7.1: `tetravox.auto_update` defaults **on**. The server checks at
startup (non-blocking, after `/api/health` is up) and every 24 h, installs a compatible release into
the user-config root, activates it and emits one `tetravox.updated` event the desktop shows as one
toast. Off means check and report. Rollback stays one click and the last two installs are kept. The
policy lives in `<install root>/policy.json`. The baseline for "newer" is the newest bundle **this
updater installed from a release** — its recorded provenance — never the active bundle.

**Why.** A viewer bugfix should cost a 5–6 MB download, not a 6.66 GB image pull gated on a
TI-Toolbox release; the alternative is one TI-Toolbox release per Tetravox release, which is the
thing the maintainer asked to remove. The provenance baseline is not fussiness: the dev container
runs a hand-installed bundle calling itself 0.4.0 and the first real release is 0.3.12, so comparing
against the active bundle answers "up to date" forever on the one machine where this matters.

**Alternatives rejected.** Image-only delivery (keeps the release coupling, and users pinned to a
tag never get the fix). Default-off (a check that only ever tells you something exists is a chore
list). A new type on `/ws/jobs` or `/ws/system` — both have consumers that parse exactly one shape,
and `events.schema.json` describes a job's `events.jsonl`, which no app-level event can be; hence
`/ws/tetravox`. The toast is deliberately not a reload: a mounted pane keeps its iframe and its
bundle, and a new mount gets the new one.

## 2026-09-05 — Electrodes are dots whose colour is their whole state, and the host writes every colour

**Decision.** Architecture §7.2: the montage scene pane draws a `shape: "dot"` points layer and says
everything with colour — neutral grey idle, 35 % grey disabled, the channel's hue when placed. No
ring, no outline, no second glyph: the pane never sends `setPointTool` or `setPointSelection`, which
are the messages that draw one, and a real-embed test asserts that the changed pixels form one solid
disc rather than assuming it. Names are shown for placed electrodes only. Every point carries an
explicit `color`, idle ones included. The channel palette is **Okabe-Ito**, and the pair editor, the
channel legend and the 3-D pane all read it from the one `channelCss()` function.

**Why.** The embed's selection ring is unreadable on a 185-electrode net and cannot say *which*
channel a marker belongs to — the maintainer asked for colour instead of circles. The explicit idle
colour is not redundancy: the shipped normaliser returns an `idle` point untouched and never consults
`stateColors.idle`, so an idle point with no colour of its own falls through to the layer colour,
and one layer colour cannot also be the disabled colour. The old four-hue palette put green next to
orange, which is exactly the pair a deuteranope cannot separate — and a four-pair mTI montage uses
all four.

**Alternatives rejected.** A layer-level `selected` colour (it cannot encode the channel).
Radius-as-state for the active channel (the shipped bundle reads the dot radius from the layer, not
the point, so it is inert; the field is still sent, and asserted, so it cannot drift). Waiting for the
upstream 3-D dot pass before shipping: the payload is correct today, the layer keeps `radiusMm: 4`
so nothing regresses, and the defect is pinned by a test that fails when the fix lands.

## 2026-09-05 — One selection grammar, with the receipt as the confirmation

**Decision.** Architecture §7.4: `ui/SelectionList` is the only way anything is chosen out of a set,
with `SelectionPicker` as its dialog form for fields with no room. 2.5.0's rule is restored — a flat
list, native range selection, exactly two bulk buttons, options that apply to the whole selection, a
plain receipt, and one Skip/Replace/Cancel question about existing outputs — and the receipt is
rendered through a `receipt` slot on `PageLayout`, outside the work scroller and immediately above
Run. The plan grid stays as the detail view.

**Why.** v3 had grown five selection idioms that disagreed about what a click did, and the
maintainer reported that choosing and understanding a batch had become "too convoluted". The
confirmation was also in the wrong place: the grid states coverage and the digest states a count,
and neither says *which* jobs, next to the button that runs them. Making the receipt sticky *inside*
the scroller was tried and measured wrong — the layout hit-test caught it answering clicks meant for
12 of the Optimizer's controls — so the slot is the fix, not a z-index.

**Consequences.** A plain click now selects one row instead of adding one (⌘-click adds).
`MultiSelect` chips and the per-slot `Select` combos are gone from the pages (`MultiSelect` survives
for schema-driven forms). `PlanGrid` is no longer the primary confirmation. Four different
existing-output dialogs became one, two of which had offered no Skip at all — finishing a half-done
batch had meant deselecting its finished rows by hand.

## 2026-09-05 — A pipeline is a job group, not a workflow engine

**Decision.** Architecture §7.3: a pipeline is a DAG of existing job kinds whose edges are typed
bindings, and running it is exactly one `submit_plan` — the same machinery `plan_preprocessing`'s
G1–G6 DAG already uses. No new job kind, no second executor, no client-side sequencing. Bindings
knowable from the upstream config are resolved at submit time; the rest get one small `tools` job
between producer and consumer whose result is merged into the consumer's runner config at admission.
Port types are a closed set of five.

**Why.** "Run it as a single job" was the ask, and the DAG the scheduler already runs *is* that.
Reusing it means cancel, the group cap, the jobs rail, the events stream and the log tail all work on
a pipeline for free. The price is that a pipeline can never do what a job group cannot — no
conditionals, no retries, no loops — and that is the feature: the alternative is a second scheduler
whose failure modes nothing else in the app understands. Admission is the right moment for the
write-back because it is by construction after every `after` job has finished, which is the first
moment a run-time-named directory exists.

**Alternatives rejected.** A pipeline runtime (a second executor). Resolving dynamic bindings in the
client (the client would have to poll for a directory name and then submit, which is client-side
sequencing by another name). Failing the consumer when a resolve step found nothing: leaving the
field as the canvas set it makes it fail exactly as an unfilled form field does, with the same
message.

## 2026-09-05 — React Flow is the canvas; `nbformat` is an optional extra

**Decision.** `@xyflow/react` 12.11.6 (MIT), pinned exactly, is the pipeline canvas — the only new
renderer dependency of the feature. `nbformat>=5.1.4` is a `[project.optional-dependencies] pipeline`
extra, not a hard dependency, and both container recipes install it; `POST /api/pipelines/export`
returns an honest 501 naming the missing module when it is absent.

**Why.** The canvas needs node/edge rendering, pan/zoom, typed handles and a connection-validation
hook — weeks of pan/zoom, hit-testing and handle geometry for no domain value if hand-rolled, and
`dagre` plus static SVG has no interaction at all. `pyproject.toml`'s `dependencies` is deliberately
empty because `tit` is installed into SimNIBS's own interpreter, where an unpinned resolve fights
SimNIBS's pins; an extra keeps that property while the desktop app always has the module.

**Consequences.** React Flow is used as a *controlled* component, which means the page must apply
**every** `NodeChange` it emits — applying only position changes throws away its measurements and it
keeps unmeasured nodes at `visibility: hidden`.

## 2026-09-05 — Notebook export is public-API-only, and carries the document in its metadata

**Decision.** `POST /api/pipelines/export` emits an `nbformat` v4 notebook whose code cells call only
what `docs/wiki/scripting.md` documents, in topological order, with bindings expressed as Python
variables; the pipeline document rides along in `metadata.ti_toolbox.pipeline`. Cell ids are
deterministic, so export is byte-stable. **Importing an arbitrary hand-edited notebook is a
non-goal**; a future import reads the metadata, never the Python.

**Why.** A notebook that a user runs is a promise about the API it calls, so the gate executes every
code cell against a stub `tit` that defines only the documented names — a call the wiki does not
teach fails the build. The metadata makes the round trip a lookup rather than a parse: reconstructing
a graph from edited Python is guesswork that would be wrong quietly.

## 2026-09-05 — Settings' ⌘-number is derived, not hard-coded

**Decision.** `shortcutForSlot` gives each rail row its index and gives Settings the first digit the
rail does not use — `⌘0` since the Pipeline row landed, `⌘,` still its alias. The `?` sheet and the
Help page's Keyboard tab both build their rows from `NAV_ORDER` rather than restating it.

**Why.** Settings was hard-coded to `⌘9` because the rail was exactly eight rows; a ninth row put two
pages on one key, and the two places that had typed the list out by hand became wrong the same day.
A rail row must not need an edit in four files.

## 2026-09-06 — The in-app Tetravox embed is retired; viewing is the host-installed desktop app

**Decision.** Architecture §7.1 is replaced. TI-Toolbox ships no viewer. The Viewer page is a data
selector whose Open writes `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json` with host paths
and hands it to the host's Tetravox application. The embed, `/tetravox/`, `tit/tetravox/**`, the
protocol range, the release index, the install store, `/ws/tetravox`, the Settings engine card and
the image bake are all deleted. Reverses the embed halves of 2026-09-02, 2026-09-03 and the E1–E4
delivery decisions of 2026-09-04.

**Why.** The maintainer, verbatim: *"for the viewer, instead of embedding the web version of
Tetravox … the viewer tab only acts as the data selection and it actually opens up everything in
[an external window] like we have in 2.5.0"*, and *"I want the complexity to be as simple as
possible and the implementation to require minimal maintenance."* The engineering reasoning is the
fact D3 already established: the container has no display. An embed was the only way to draw
*inside* the app without one, and paying for it meant an image bake, a protocol range, an installer,
an update channel and a WebSocket — roughly 3,000 lines and 130 tests — to manage a coupling that
existed only because we shipped a viewer at all. The desktop app is the one Tetravox build that is
signed, notarised and self-updating; removing the bake removes the coupling, and the machinery
with it. The removal took ~130 tests of delivery machinery out of the suite and added 10 of the
feature that does the same job.

**Alternatives rejected.** Keeping the embed only for the Viewer page would have kept every piece of
the delivery stack for one page. Shipping a GUI Tetravox *inside* the container needs X11, which v3
removed. Copying Tetravox's engine into this repo is the vendoring the service boundary exists to
prevent — the run-page panes are our own renderer over our own guide format (§7.2), not a copy of
another product.

## 2026-09-06 — `Capabilities` says nothing about the viewer (breaking)

**Decision.** `tetravox_embed` is removed from `GET /api/capabilities`.

**Why.** A capability is what *this runtime* can do. Whether an application is installed on the
user's machine is a fact about the host, answered by the Electron shell's `window.tit.viewer.probe`,
which reads the filesystem. Reported over HTTP it would have been a container answering a question
about a computer it cannot see.

## 2026-09-06 — The run-page panes render themselves; the embed was never a pane

**Decision.** Architecture §7.2 is replaced. `desktop/src/renderer/scene/` — the 2026-09-04 WebGL2
renderer, restored — is the only renderer on the Simulator, Optimizer and Analyzer. It reads the
packaged guide in `TVSC1`, draws electrodes as screen-space dots with no ring, and carries its own
atlas selector with hover naming and click-to-select regions.

**Why.** The maintainer, verbatim: *"I still don't like our implementation … we had a really neat
implementation that worked very well and showed the electrodes in a better fashion and also the
atlas ROIs were interactive"*, and *"write our own little module based on the logic from Tetravox
and embed it exactly how we need it into our tabs."* Driving the embed from the forms cost an
iframe, a message protocol, a runtime update channel and a capability negotiation, and still gave a
worse pane: the electrodes were spheres the engine would not size, selection was a ring the user
could not read on a dense net, and the atlas was not interactive at all. Two of those were
protocol-2 asks upstream — i.e. a pane feature this project could not ship without another
project's release.

**Alternatives rejected.** Waiting on Tetravox protocol 2 (`markers`, `pick`, `camera`) makes a pane
feature depend on another product's release cadence; the parked work is recorded in ROADMAP.md and
remains useful upstream. Rendering only 2-D slices in the pane loses the electrode geometry that is
the whole point of the Simulator's pane.

## 2026-09-06 — The guide packages `TVSC1` labels again

**Decision.** `tit/scene/guide_build.py` packages per-vertex `uint16` label payloads (`LABEL_FORMATS
= ("tvsc", "gii")`), ~0.99 MB per atlas, 2.96 MB on the installation.

**Why.** They were dropped on 2026-09-05 on the premise that nothing read them, which was true only
while the native renderer was retired; the day it came back the cortex had no regions to highlight.
A test pins them by **alignment to the `gm` surface** — same vertex count, same first vertex — not
merely by presence, because a label payload for a different surface is the failure that looks like
a working feature.

## 2026-09-06 — One region-selection model

**Decision.** `<ScenePane>` and `<RoiPicker>` edit the same list through the same `regionKey` and
`toggleRegion`, exported once from the scene model.

**Why.** Two toggles that agree today are two toggles. A 3-D click and a form chip must compare
regions the same way or the pane highlights a region the form does not hold — and that divergence
is invisible until a user notices the ROI they clicked is not the ROI that ran.

## 2026-09-06 — A jobs table replaces the subject-set × montage fan-out

**Decision.** Architecture §7.5. The Simulator and the Analyzer describe a run as a table in which
one row is one job; the page-level subject control, the Simulator's source tabs and the Analyzer's
Scope segment and single Simulation combobox are removed.

**Why.** The maintainer, verbatim: *"it's hard to separate users, montages, modes in different jobs.
In 2.5.0, within a job users could manipulate the subject, the mode, the montage, the current
intensities… We need that capability. This is also true for the Analyzer."* A page-level subject set
fanned across a montage list can only express the cross-product: three subjects × two montages was
six jobs, and there was no way to say "ernie on F3_F4, 101 on the flex result". 2.5.0's job cards
and Subject × Simulation pair table could. The cross-product survives as an explicit button, which
is what it always was — a convenience, not the model.

**Alternatives rejected.** Per-subject overrides layered on the page-level set keeps the fan-out as
the model and adds an exception mechanism on top of it. A separate "advanced" mode makes the page
two pages with two selection idioms, against §7.4.

## 2026-09-06 — The bridge budget is 13, not 12

**Decision.** ADR row 14's preload bridge budget moves from 12 entries to 13. The new entry is
`viewer` (`probe`/`open`/`setPath`).

**Why.** Opening a scene in another application is a host action, and a host action is only
reachable through main. It replaces capability the app previously had with *no* bridge entry at all
— an `<iframe src="/tetravox/">` — so the budget moves rather than the feature being squeezed into
an entry it does not belong to. `smoke.spec.ts` asserts the exact key list, which is what holds a
fourteenth to an ADR line.


## 2026-09-06 — The viewer is installed on the host, not baked into the image

**Decision.** The desktop app downloads, verifies and maintains its own copy of Tetravox on the
user's machine (Settings ▸ Viewer states where it is and which version), keyed to the publisher's
own release digest. It is not added to the container image, and it is never pinned by us.

**Why.** Tetravox is a windowed application on the *user's* desktop; the container has no display
server and never will. Baking it in would also chain a Tetravox release to a TI-Toolbox image
release, which is the coupling this whole program exists to remove — the point of an external
viewer is that it ships on its own clock. The publisher's `latest*.yml` digest is the only
authority on what a given version is; substituting a pin of our own means a hash we have to update
by hand and a "corrupt download" the day they re-cut a release.

**Alternatives rejected.** A bundled copy inside the app bundle doubles our download for every
user who already has one and makes the version un-upgradable without a TI-Toolbox release. A
"please install it yourself" dialog is the state this replaced. Activating a newly downloaded copy
under a running window is refused outright: the new version takes effect on the next launch.

## 2026-09-06 — A cohort is a node, and a wire is refused on what its subjects have

**Decision.** Architecture §7.6. The pipeline canvas gains a **Subjects** node, which is the only
source of subjects in a document, and every edge out of it is validated against a readiness table:
a step declares what it *requires* and what it *produces*, and a wire whose subjects cannot satisfy
the requirement — directly or through an upstream step that produces it — is refused with the
subject and the reason on the edge.

**Why.** Subjects were a property of each node, so the same cohort was retyped per step and could
silently disagree between two of them. And a canvas that accepts any wire and fails an hour later
inside a container is not a canvas: `Subjects(102) → Simulator` is knowably wrong at the moment of
the drag, because 102 has no head model, and `Subjects(102) → Pre → Simulator` is knowably right,
because Pre-processing produces one.

**Alternatives rejected.** Validating only at Run keeps the canvas honest but moves every mistake
past the point where the user still remembers what they meant. A warning rather than a refusal
makes the edge a fact the user must re-derive; §7.6's issues carry a machine-readable `code` and
`port` precisely so the refusal can say which end is wrong.

## 2026-09-06 — All three run pages carry a jobs table

**Decision.** Architecture §7.5 extends to the Optimizer: the Simulator, the Analyzer and the
Optimizer each describe a run as a table in which one row is one job, and the row owns everything
that differs between jobs. Global sections survive only for properties of the *run*.

**Why.** The Optimizer had the same defect as the other two and worse: a target, an objective, an
electrode set and a solver were all page-level, so one page could describe exactly one search. A
row is the unit a user actually thinks in ("this ROI with this goal, and that one with that"), and
making it the unit on all three pages means one grammar to learn rather than three. The
consequence is stated rather than hidden: where a page's rows submit as more than one job *kind*,
one Run is one submission per kind, and the page says so.

**Alternatives rejected.** Leaving the Optimizer page-level because a search is "bigger" than a
simulation is the argument that produced the defect. A cell that is meaningless for a row's method
prints a muted `—` with the reason in its title rather than a disabled control, which would read
as a choice the user has failed to make.

## 2026-09-06 — Translucent surfaces are resolved as two depth sheets

**Decision.** The native scene pane resolves the two nearest depth crossings per pixel and blends
those, rather than depth-sorting geometry or accepting whatever order the draw calls arrive in.
Regions are painted in the colours their `.annot` colour table carries, read from the file, and a
selected region is outlined by a thin edge rather than a border.

**Why.** A translucent skin over a translucent grey matter has no correct single depth, and
back-to-front sorting of a 222k-triangle cortex per frame is not affordable at 120 fps. Two sheets
is a bounded approximation — a third crossing deeper inside a sulcus is dropped rather than
mis-ordered — and it is the same bound Tetravox ships, which matters because the two renderers must
agree about the same subject. The atlas colours are read and not invented because a legend that
names a region in a colour the file does not give it is a lie the user cannot check.

**Alternatives rejected.** Inventing a palette per atlas makes two views of the same subject
disagree. The first outline implementation drew a border and produced "a border of white shards" on
a folded surface; a thin edge computed in the same pass does not.

## 2026-09-06 — The run terminal never auto-pins a finished job

**Decision.** The run page's terminal pins a job only while it is live. A job that has finished is
never pinned by the page on the user's behalf.

**Why.** Auto-pinning a finished job takes the terminal away from whatever the user was reading and
replaces it with a log that has stopped changing — an interruption that costs attention and returns
nothing, since a finished job's log is reachable from the Jobs page whenever it is wanted. The Raw
log tab is now the shared console filling the detail pane, so there is one place that answers "what
did it print", and it is not the run page's terminal deciding for the user.

## 2026-09-06 — The Viewer page is a file list, and Open is the only verb

**Decision.** The Viewer page is an editable list of the files that will open, plus **Open in
Tetravox**. Layer appearance — opacity, colormap, threshold, layout, camera — is not duplicated on
this page; it belongs to Tetravox's own inspector.

**Why.** Two applications offering the same appearance controls over the same file is two sources
of truth, and the one the user tuned is not the one that opened. What this app knows and Tetravox
does not is *which files belong together*, so that is the whole job of the page: derive the list,
let the user edit it, hand it over. The written scene is a real file in the user's own project
(`code/ti-toolbox/viewer/…`) — it opens later by double-clicking, with no app in the middle.

**Alternatives rejected.** A composition panel with layers, layout, camera and presets was built
first and is the version this replaced; it was a better *panel* and a worse *page*, because every
knob on it was a knob Tetravox already had and would win.

## 2026-09-06 (later the same day) — The embed is restored, ships in the image, and is the Viewer's own sub-page

**Decision.** Architecture §7.1 is replaced again, reversing this morning's two entries — *"The
in-app Tetravox embed is retired; viewing is the host-installed desktop app"* and *"`Capabilities`
says nothing about the viewer"* — and the *"The viewer is installed on the host, not baked into the
image"* entry with them. The Tetravox **embed** is the viewer again: baked into the image at
`/opt/tetravox/embed`, served by `tit.server` at `/tetravox/` with its own CSP, delivered and
updated at runtime by `tit/tetravox/{protocol,store,install,updates}.py` behind `GET/POST
/api/tetravox*` and `/ws/tetravox`, and reported by `Capabilities.tetravox_embed`. **Nothing
installs Tetravox on the host, and there is still no X11 anywhere.** The Viewer page becomes two
sub-pages, shown in the rail as indented rows under the Viewer row — **Menu** (the composition page,
VM2's design, its button renamed *Open in viewer*) and **Tetravox** (full-bleed, the embed iframe,
a slim strip with the scene name and `Reload`). ADR row 14's preload budget loses the `viewer` entry
again; the morning's amendment is reversed.

**Why.** The maintainer, verbatim: *"The Dockerfile should contain Tetravox. We should not install
Tetravox on the host machine — forbidden. Tetravox should not be visually embedded in the
TI-Toolbox tab; it should open in its own [view]. In the Viewer, the left menu has two subsections:
the Menu, and below it the actual Viewer. The user configures in the Menu, hits Open, is moved to
the Viewer where the Tetravox embed is; they can go back to the Menu, tinker, and reload a
different setup."*

The engineering reading of D3 was half right and drew the wrong conclusion. The container having no
display is exactly why the *embed* is the only Tetravox that can draw inside this app: a windowed
application baked into the image has nothing to draw on, and one installed on the host is an
acquisition the user has to make, a second window to manage, and a per-platform install path this
project then owns. The embed runs on the host GPU in the app's own renderer, and the user installs
nothing. What the morning got right — that the Viewer should not be a picture squeezed beside a
form — is kept, and answered by the sub-page split rather than by deleting the renderer: the embed
is full-bleed on its own sub-page, and the composition lives on the Menu.

**What the restored machinery buys, stated plainly.** It is roughly 3,000 lines and ~130 tests, and
it is not free. It buys the one property this program was asked for and cannot get any other way:
*a Tetravox release does not imply a TI-Toolbox release.* The coupling is real the moment a viewer
ships inside an image, and the protocol range is what keeps it from becoming a version pin — a pane
asks for a named feature (`markers`, `pick`, `camera`), the supported range lives in two files a
cross-language test keeps in step, an additive Tetravox release needs no change here at all, and a
breaking one costs one constant. The rest of the cost is the delivery honesty the maintainer's own
threat model demands: a digest verified before the archive is opened, an extraction that refuses
`..`, absolute paths and links (Python 3.11's unfiltered `extractall` writes outside the destination
in this image), an atomic activation, a pin so rollback is not a re-download, and a policy stored on
disk rather than a habit compiled in.

**Alternatives rejected.** An in-page segmented control was built first and rejected: the maintainer
specified the rail, precisely — two indented rows under Viewer, always visible, the active one
highlighted like a page, and clicking Viewer itself opens Menu. Making the sub-items *pages* was
rejected too: a `PageDef` each would give them ⌘-numbers, `pages/<id>/` directories and separate
mounts, and separate mounts are exactly what destroys the iframe. What landed instead is one narrow,
page-declared concept — `PageDef.subNav` plus `pagePath()` — over the existing flat model:
`NAV_ORDER` still defines the rail and the ⌘-numbers, sub-items carry none, no other page directory
changed, and `RetainedPages` keys retention on the first path segment, so `/viewer/menu` and
`/viewer/tetravox` remain one mounted component and iframe retention is true by construction. Two calls — one for the file, one for the iframe — were
rejected: a job finishing between them is enough to make the list, the file and the picture
disagree, so `POST /api/view/open` resolves once and returns both addressings.

**Known limit.** Sub-items are not drawn in the icon rail (below 1440 px): at 56 px there is no
room for an indent and a label, and two unlabelled dots under one icon say nothing. The command
palette carries both as rows (`Viewer · Menu`, `Viewer · Tetravox`), which makes it a real
accessibility path at those widths rather than a convenience.

**Known consequence.** The app now has two renderers: the embed on the Viewer sub-page, and the
app's own WebGL2 renderer on the run pages (§7.2, unchanged and untouched by this reversal). That
is a deliberate split — the panes draw packaged reference anatomy and need picking and marker
behaviour this project controls, while the Viewer draws the user's data and wants the whole engine.
Converging them (`dev/notes/v3-embed-convergence-plan.md`) is a future question again, not a settled
one.

## 2026-09-06 (later the same day) — The bridge budget is 13, and `viewer` is not one of them

**Decision.** ADR row 14's preload budget is **13** entries. `viewer` (`probe`/`open`/`setPath`) is
removed — opening the viewer is no longer a host action, so it is not main's to expose — and the
morning's 12 → 13 amendment for it is reversed. The 13 are `appVersion`, `connect`, `getSettings`,
`notify`, `openExternal`, `openPath`, `platform`, `saveFile`, `selectDirectory`, `selectFile`,
`setSettings`, `showItemInFolder`, `stack`, which is the exact list `smoke.spec.ts` asserts.

**Why.** The budget was 12 before the morning. It is 13 rather than 12 now because `saveFile` landed
independently between the two decisions (the Pipeline canvas's notebook export: writing
renderer-produced text to a file the user picks is a host action, and the renderer's `<a download>`
on a `blob:` URL was inert in this shell and reported success anyway). Reversing the viewer
amendment therefore returns one entry, not two. A page that renders the embed needs no bridge entry
at all — it is an `<iframe src="/tetravox/">` on the same origin.

## 2026-09-06 (NB lane) — notebooks: the kernel is the container's, and the UI is SUNA's

**Decision.** A Notebooks page runs `.ipynb` files on a Jupyter kernel owned by `tit.server`
(`tit/server/kernels.py`, kernelspec `simnibs`, cwd the project), driven over
`WS /ws/kernels/{kernel_id}`, with the files under `<project>/code/ti-toolbox/notebooks/` behind
`/api/notebooks`. At most **2** kernels run at once and one idle for **30 minutes** is shut down.
The renderer is ported from SUNA (github.com/idossha/SUNA), GPL-3.0, same author, attributed in
each file's header. ARCHITECTURE §7.6.

**Why.** The ask was that "the TI-Toolbox environment is automatically loaded". The environment is
not something to load — it is the container's SimNIBS Python with `tit` on the path, and it is
already where the server runs. Putting the kernel there means the answer to "which interpreter?" is
never asked: no picker, no `ipykernel` install prompt, no per-project selection. SUNA needs all
three because its kernel is the user's own machine's; §16.2 there is largely the machinery for
degrading honestly when that interpreter has no `jupyter_client`. **That entire branch disappears
here**, which is why this port is shorter than its source rather than longer.

**Why SUNA's code rather than a fresh UI.** Everything hard about a notebook front end is already
solved there and solved for reasons that hold identically here: an iopub content *is* an nbformat
output so nothing translates; a plot beats its own text repr but a DataFrame table beats both;
output with no attributable parent is dropped rather than mispinned; ANSI is parsed because an
uncoloured IPython traceback is unreadable; modal editing is the only way `dd` can be a bare
keystroke. Rewriting that would have reproduced the bugs it already fixed.

**Alternatives rejected.** *Publishing the image's JupyterLab and linking to it* — one HTTP port and
no code, and it is a different application in a different window with its own auth, its own file
tree and no idea what a TI-Toolbox project is; the ask was for notebooks *within* TI-Toolbox.
*Running the kernel on the host under the user's own Python* — SUNA's topology, and it would put
the user back in the business of installing SimNIBS. *Framing the bridge as a child process anyway,
for symmetry with SUNA* — a process and a pipe to reach a library already importable in this
process.

**Known consequence — Jobs loses ⌘9.** Notebooks sits after Pipeline (the maintainer's placement),
making ten workflow rows. There are nine digits and ⌘0 is Settings, so the tenth row has no number:
Jobs is now ⌘K and its route only. `shortcutForSlot` was returning `"10"` for a tenth row — a chord
no keyboard can send, printed in the rail and the `?` sheet as though it worked — and now returns
nothing past the ninth. If ⌘9 Jobs matters more than the rail's workflow order, the fix is to move
Notebooks to the end of `NAV_ORDER`, not to reinstate an untypeable shortcut.

**Known limit — interactive plots fall back to a picture.** SUNA renders plotly/vega by loading the
library from a CDN into an iframe on its own privileged `suna-output:` scheme, because the renderer
CSP rightly forbids kernel-supplied scripts and a `srcdoc` iframe inherits that CSP. TI-Toolbox has
no such scheme, so a live plot here would silently draw nothing. `pickRepresentation` still
*recognises* the interactive mime — that is what lets `Outputs.tsx` fall back to the static PNG the
kernel sends beside it — and matplotlib, the dominant case in this domain, was never affected.

**Known limit — a cell is a textarea.** SUNA puts a CodeMirror in every cell because the rest of
that app already ships one. Five CodeMirror packages for cell text is a dependency nothing else in
this app would use, so cells are auto-sizing textareas in the mono token face and syntax
highlighting is on the ROADMAP. **No new dependency was added for this feature.**

**Proved live, and one defect it caught.** Driving the dev container's `/api/kernels` and
`/ws/kernels/{id}` directly ran a real cell in SimNIBS Python and got a real IPython traceback
back — which is how the starter cell was found to say `pm.project_root` when `PathManager`'s
attribute is `pm.project_dir`. Static reading had it wrong in both the server and the mock; a
driven run said so.

## 2026-09-06 (NB lane, later) — the cell is a CodeMirror, and the kernel is the completer

**Decision.** A code cell is **CodeMirror 6** with `@codemirror/lang-python`, whose highlight
palette is built from the app's own CSS variables rather than a colour list. Completion is answered
by the **running kernel** over the existing `/ws/kernels/{id}` socket (`complete_request`,
`inspect_request`), surfaced through CodeMirror's autocompletion on ⇥ and ⌃Space. A sliders popover
carries autocompletion, signature help, auto-close brackets, line numbers, indent size, font size
and word wrap, persisted in `localStorage` like `app/executionPrefs.ts`. New dependencies: `katex`
(which SUNA also depends on) and six `@codemirror/*` packages. ARCHITECTURE §7.6 rules 4–5.

**Why the editor changed.** The first version shipped a `<textarea>` to avoid the dependency, and
recorded that as a known limit. The maintainer's answer was that the cost was worth paying: a
textarea cannot colour Python, cannot indent a block and has nowhere to put a completion popup, and
"easier for users to develop" is the entire point of the page. A markdown cell is still a textarea
— there is nothing to highlight in prose, and its rendered form is where the reading happens.

**Why the kernel and not `pylsp`.** The image already has `python-lsp-server` and `jupyterlab-lsp`,
and using them was the obvious move. It is the wrong one. A language server reads *files*; a
notebook's meaning lives in an interpreter that has already run `from tit import catalog`, and only
that interpreter can say what `catalog.` holds — it is the thing holding it. IPython answers
`complete_request` from that live namespace using `jedi`, which is already inside `ipykernel`.
So the choice was between a second process to install, configure and keep in sync with a namespace
it cannot see, and one message on a socket that is already open. Verified in the container:
`jedi 0.19.2`, and `from tit import get_pa` completes to `get_path_manager` against the real kernel.

**Why the palette is variables.** `EditorView.theme` is compiled once, so a theme built from hex
values would need a second palette and a rebuilt editor on every theme switch. Every rule resolves
to `var(--…)` instead, so the editor follows light/dark with the rest of the app for free.

**Markdown is KaTeX, bundled.** SUNA depends on `katex` and so does this. It is a real npm package
compiled into the bundle, **not** a CDN script: the renderer's CSP forbids remote scripts and a
`srcdoc` frame inherits that CSP, so a CDN would have drawn nothing and said nothing about it.

**Four defects the driven runs found, none of which static reading would have.**

- *A command-mode guard that tested for a textarea.* `onKeyDown` skipped the notebook's single-letter
  keys when `target.tagName === "TEXTAREA"`. True for a textarea, false for CodeMirror's
  contenteditable — so typing `print(` delivered `r` to command mode, which re-typed the cell as
  **raw** and destroyed the editor under the author's cursor. The test is now "did this come from
  inside an editor", which is what was always meant.
- *Tab closing the popup it should accept.* Typing already opens the completion, so by the time ⇥
  arrives there is one on screen; `startCompletion` returns false when one is open, and ⇥ then fell
  through to `indentWithTab`, which indented **and** dismissed it. ⇥ now accepts, then swallows a
  pending query, then starts one, and only then indents.
- *A completion range that filtered every option away.* The kernel replaces the whole dotted
  expression, so `catalog.subject_ids` replaced `catalog.subj`. CodeMirror filters options by
  matching the label against the replaced text, so a label of `subject_ids` matched nothing and the
  popup never appeared — while keeping the full label fixed the filter and made every option read
  `catalog.…`. The **range** moves instead, past the prefix every match shares.
- *A restart that aborted the server.* See below; it is the sharpest of the four.

**Known consequence — a notebook restart could take the API down, and did.** Restart closed the ZMQ
channels while the iopub and shell pumps were still polling them. ZMQ sockets are not thread-safe;
libzmq's answer was `Assertion failed: pfd.revents & POLLIN (src/signaler.cpp:238)`, aborting the
`tit.server` process — every running job's API, killed by a notebook button. The pumps are now
stopped and joined before anything touches a socket, and the client is rebuilt because
`restart_kernel` makes the old session key stale (which is where the preceding `Invalid Signature`
came from). Three tests pin the ordering. **This was invisible to every unit test and to the mock
e2e**, and only appeared when a real kernel was restarted in the container — D13's argument, again.

**The example notebook, and why it is generated rather than shipped.** `examples/getting-started.ipynb`
is written by the server on a project's first listing, because its cells resolve *this* project's
subjects and plot the first TI field it actually has; a fixture in the image would name a project
that does not exist yet, and a fixture in the repo would drift from the API it calls. Two things it
taught: without `%matplotlib inline` this kernel's formatter offers a Figure only as `text/plain`
(the cell printed `<Figure size 900x340>` and no picture), and *with* the magic a trailing bare
`figure` puts the same picture in the notebook twice — once as `display_data`, once as the
execute_result.

**`GET /api/notebooks/examples/getting-started.ipynb` 404'd.** A plain path parameter stops at a
separator, so the seeded example could not be opened at all. The routes take `{name:path}`. What
keeps it safe is unchanged and was never the router's pattern: `normalise_name` accepts exactly one
known prefix and refuses everything else.

**Alternatives rejected.** *A CDN for KaTeX and for CodeMirror* — blocked by the CSP, silently.
*Client-side static completion from a Python grammar* — it cannot see the namespace, which is the
only thing that makes `tit.` completion worth having. *Settings on the server, per project* — these
follow the person, not the project, so they are `localStorage` and not in the `.ipynb`.

## 2026-09-06 (CX5) — Grey matter is opaque, and only the skin has an opacity slider

**Decision.** The pane's grey-matter surface is drawn fully opaque and its opacity control is gone;
the skin keeps its slider. Translucency remains a property of the outer surface only.

**Why.** A translucent cortex under a translucent scalp was not readable as anatomy. Two sheets of
alpha compose to a colour that belongs to neither, and the fresnel silhouette boost every surface
carries pushes both towards white at the rim — so a region's own atlas hue arrived at the screen
diluted by a factor that depended on where on the head the fragment was, which is precisely what the
atlas-border work then had to measure around (`#4b327d` reaching the buffer as `[150,137,169]`). One
translucent sheet over an opaque one has a single, predictable composition.

**Alternatives rejected.** *Order-independent transparency for both sheets* — real cost for a view
whose depth reading was never the complaint. *Keeping the slider at a fixed default of 1.0* — a
control that exists but must not be moved is worse than no control.

## 2026-09-06 (CX5) — The camera is the user's, not the data's

**Decision.** A pane keeps its camera across a payload change: switching net, montage or subject
reframes nothing. The framing pass runs on the pane's *first* payload and on an explicit reset.

**Why.** Changing a montage to compare two placements threw away the view the comparison was being
made from — the one interaction where the camera matters most was the one that destroyed it. A
camera is a statement about what the user is looking at; a new net is not a statement about that.

## 2026-09-06 (CX5) — Free-hand placement lives in the Simulator, not in a panel

**Decision.** Free-hand electrode placement is reached from the Simulator's montage footer, beside
*New montage*, and edits the montage in place by clicking the subject's skin in the pane. It is not
a Settings-gated panel page and has no rail row.

**Why.** A montage is what free-hand placement produces, so it belongs where montages are made. As a
panel it would have been a second place to build the same object, reachable only by someone who had
already found the Settings toggle — the PyQt tab-strip mistake in a new costume.

**Known consequence — 3-D electrode geometry is not modelled, for now.** A placed electrode is a
dot with a colour, not a disc with a radius and a thickness lying on the scalp. The rejected
alternative was to draw real electrode geometry in the pane: it needs a surface-tangent frame per
electrode and a shape the solver agrees with, and getting either subtly wrong would draw a montage
that is not the one submitted. A dot at a picked skin vertex is exactly as true as the position it
came from.

## 2026-09-06 (CX5) — Subject Info is deleted rather than migrated

**Decision.** The Subject Info Viewer panel, its page and `GET /api/subjects/{id}/info` with the
`SubjectInfo`, `SubjectSimulationInfo` and `FileRef` schemas are removed from the contract.

**Why.** Overview already answers "what does this subject have" for every subject at once, in one
bounded request. Two surfaces for one question means two answers whenever one of them lags — and the
panel's per-subject request was the one that would have had to grow a column each time a data stage
was added.

## 2026-09-06 (CX5) — A plan's ETA is modelled from what drives the job, not from a constant

**Decision.** `POST /api/plan` returns an estimated wall clock derived from the job's own drivers —
the leadfield's presence and size, the electrode count, the search's iteration budget — rather than a
per-kind constant.

**Why.** The number exists to answer "do I start this now or after lunch", and a constant answers
that wrongly in both directions: it makes a flex search on a computed leadfield look like the same
half hour as one that must build it first. The drivers are already in the config the plan validates,
so the estimate reads the same object the run will.

## 2026-09-06 (CX5) — The image carries what the v3 server needs, and nothing the GUI used to

**Decision.** `Dockerfile.ti-toolbox` drops gmsh, PyQt5 and the SimNIBS TMS coil model set.

**Why.** v3 has no Qt GUI and no external mesh viewer to launch: Gmsh and Freeview were the v2
flow, and the run pages now draw their own panes (§7.2). PyQt5 was a dependency of a GUI that no
longer ships. The coil models are for TMS, which this toolbox does not simulate. Each was carried
only because it had always been carried.

**Known consequence.** Anything still importing `tit.gui` fails in the image rather than starting a
window nobody can see, which is the honest failure. The v2 loader path is unaffected — it runs its
own image.

## 2026-09-06 (CX5) — A triangle's region label is transferred, not left to the provoking vertex

**Decision.** Before upload, each grey-matter triangle is rotated so its **last** corner carries the
majority region label, and label shading is `flat`. Winding is preserved: `[a,b,c] -> [c,a,b]` is a
rotation, so normals, culling and the outward orientation the service guarantees are untouched.

**Why.** The shader reads the region id from a `flat` varying, and WebGL 2 fixes the provoking vertex
to the triangle's last index — an arbitrary corner as far as the anatomy is concerned. On the
packaged ernie guide with DK40, 15 289 of 145 402 triangles (10.5 %) straddle a border; 14 965 have a
clear two-to-one majority, and with the last corner deciding, roughly a third of those took the
*minority* label. Each is a triangle-sized spike of the neighbour's colour across the border — the
saw-tooth the maintainer reported. Rotated, the border follows the mesh edges between the regions.

**Alternatives rejected.** *Interpolating labels* — a label is not a quantity and the midpoint of two
region ids is a third region. *Splitting border triangles* — changes the mesh the solver and the
service agree on to fix a shading artefact. A triangle whose three corners are three different
regions is a genuine triple junction (324, 0.22 %): there is no majority to rotate to, and it is
left exactly as it came.

## 2026-09-06 (CX5) — The rail counts from ⌘0

**Decision.** `shortcutForSlot` is the row's index in `NAV_ORDER`, starting at zero: ⌘0 Overview
through ⌘9 Jobs. Settings takes no digit and keeps ⌘, as its only chord; Help stays the `?` sheet.
This supersedes the 2026-09-05 entry above, which gave Settings the first digit the rail did not use.

**Why.** Maintainer, 2026-09-06: *"start from 0 the rail digit and finish at 9."* A keyboard has ten
digits and the rail has ten workflow rows — they match exactly, but only when the count starts at
zero. Counting from one spent ⌘0 on Settings, which is not a rail row at all, and left the tenth row
with no key: the Notebooks insertion had just taken ⌘9 away from Jobs, the row opened by keyboard
many times an hour.

**Alternatives rejected.** *Moving Notebooks to the end of `NAV_ORDER`* — implemented first, and it
buys Jobs its key back by taking one from Notebooks and by putting the rail out of workflow order.
*Printing ⌘10* — a chord no keyboard can send. An eleventh row would again have no number, which is
a limit of ten digits rather than of this function, and `NAV_ORDER`'s job to stay within.

## 2026-09-07 (NB lane) — signature help from the kernel, and nothing left half-built

**Decision.** Signature help is finished and is a kernel round trip like completion:
`inspect_request` on `(` and on ⇧⇥, showing IPython's own signature line and the docstring's first
paragraph in a CodeMirror tooltip, honouring the existing `signatureHelp` preference. Escape
dismisses the tooltip **before** it leaves edit mode. The kernel status pill is now the recovery
too — clicking it restarts, or starts one when none is running. ⌘S saves from anywhere on the page,
leaving the page flushes rather than prompting, and closing the window hands every kernel back.
ARCHITECTURE §7.6 rules 5 and 9.

**Why the tooltip is a summary and not the reply.** `inspect_reply`'s `text/plain` is the whole of
`get_path_manager?` — signature, full numpydoc body, `File:`, `Type:`. Rendered verbatim that is
forty lines hanging over the code it describes. So `parseInspect` reads IPython's *field* format
(labels at line starts, each field ending at the next label — not at the next newline, because
signatures wrap and docstrings certainly do) and `firstParagraph` stops at a blank line **or at a
numpydoc section underline**, which otherwise drags in a `Parameters` heading with no body.

**Why Escape needed the highest precedence.** The notebook's own Escape leaves edit mode. Bound at
equal precedence, one Escape would have done both — dismissed the tooltip *and* thrown the author
out of the cell they were typing in. `Prec.highest` puts the dismissal first, and it returns false
when there is nothing to dismiss, so the second Escape behaves exactly as it always did.

**Why leaving the page flushes instead of prompting.** The brief said "unsaved-changes guard".
A modal would be the literal reading and the wrong product: autosave already writes 1.5 s after the
last keystroke, so the only thing a prompt could ask is whether to do the save the app was about to
do anyway. The guard writes. What was actually broken — navigating inside that 1.5 s window losing
the edit — is fixed, and that is what the e2e asserts.

**Two defects this round found, both from the defaults.**

- *Signature help never fired for anyone with default settings.* The trigger tested whether the
  inserted text *ended* with `(`. Auto-close brackets is on by default, so typing `(` inserts `()`
  in one change — the test saw `)` and the feature did nothing at all. It now tests for a `(`
  anywhere in the insertion.
- *Restart did nothing on a dead kernel.* `restart()` returned early when `kernelId` was null, which
  is precisely the state a user is in when they press it — a kernel reaped for idling, or lost with
  its socket. It now starts a fresh one, and also recovers when the server answers `no-such-kernel`.

**Dead code removed rather than left to look finished.** `makeCompartments`/`EditorCompartments`
(the component builds its own) and `completion.ts`'s `inspectTooltipText`, which `signature.ts`
superseded and whose only remaining caller was its own test — a green test over dead code is worse
than no test. `signatureShown` stopped being exported; it has one caller, in its own file.

**Verified against the real container, not only the mock.** The 30-minute idle cap was checked with
a `KernelRegistry(idle_timeout=3.0)` driving a **real** SimNIBS kernel: not reaped at 1 s, reaped
past the cap, and `manager.is_alive()` false afterwards — a dead interpreter, not a forgotten
registry entry. Closing the app is asserted by the real e2e, which closes the window and polls
`/api/kernels` to zero from Node.

## 2026-09-06 (CX5) — A cap with no electrodes is not an EEG net

**Decision.** `GET /api/catalog/eeg-nets` and the subject detail's `eeg_nets` list only cap files
that carry at least one `Electrode` row. `Fiducials.csv` therefore disappears from every net picker.

**Why.** Every subject's `m2m_<sid>/eeg_positions` holds `Fiducials.csv`, whose rows are all
`Fiducial` (Nz/Iz/LPA/RPA). It was offered wherever a net is chosen — the Simulator's net cell, a
flex row's mapping target, the leadfield pickers — and choosing it left the row unrunnable forever
with nothing said, because there is no electrode in it to place. The endpoint already reported it as
`n: 0`; the listings now filter on that rather than on the file existing.

**How it was found.** The real `flex-result-selection` spec maps a run onto *every* net the subject
has and asserts each resolves to labels. Mapping onto Fiducials resolved to none. The spec was right
and the app was wrong — which is the argument for real-data specs that enumerate rather than pick
one known-good value.

## 2026-09-06 (CX5) — Open: an idle electrode can be invisible against the opaque-GM scalp

**Not a decision — a measurement, recorded so it is not lost.** With the grey matter opaque, the
composed scalp over part of the head lightens to within a few units of the palette's idle marker
grey. Measured on ernie / GSN-HydroCel-185 at 1280 px, over the 24 front-most electrodes: the
**worst** separation between an idle marker and the anatomy behind it is **2/255**, the median 35.
An electrode at the worst pixel is invisible, and the difference is a property of where on the head
it sits, not of the marker.

The real `scene-electrodes` spec now measures its colour claims on a marker whose background is
actually separated, and logs the worst and median so a regression in either direction shows up as a
number. The fix is a design call the maintainer should make — a thin contour on *every* marker
rather than only on the ones carrying a channel colour is the obvious candidate, and it would keep
colour as the whole state signal because the contour is constant — so it is left open rather than
decided here.

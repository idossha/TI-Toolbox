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

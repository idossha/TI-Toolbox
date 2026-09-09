# Architecture decisions

Current rules live in [ARCHITECTURE.md](ARCHITECTURE.md); this append-only log records **why**.
Chronological, oldest first.

Every entry has the same four parts, and a new one must too:

```

## The numbered ADR index

The codebase and the entries below cite decisions as **"ADR row N"**. This is that table, moved here
on 2026-09-07 from `ADR.md` (itself moved from a gitignored track file). A row's full rationale is
the dated entry below it, or `HISTORY.md`'s section for the program that produced it.

| # | Date | Decision | Status |
|---|---|---|---|
| 1 | 2026-08-27 | Bridge is a Python job server (`tit.server`, FastAPI) in the container; Electron is a thin shell | live |
| 2 | 2026-08-27 | UI served by `tit.server`; Electron `loadURL`s `127.0.0.1:<port>`; `?token=` exchanged once for a cookie | live |
| 3 | 2026-08-27 | Freeview and Gmsh stay in the container on X11 for 3.0 | superseded by 15, then 21 |
| 4 | 2026-08-27 | An internal viewer is a separate later track over the same ViewSpec | superseded by 15 |
| 5 | 2026-08-27 | New `desktop/` for v3; legacy `package/` untouched until Phase 6 | Phase 6 done 2026-09-07 |
| 6 | 2026-08-27 | React 18 + Vite + TypeScript strict + Tailwind + react-hook-form/ajv; TanStack Query; Zustand | live |
| 7 | 2026-08-27 | Contract-first: hand-authored OpenAPI, server dump must diff clean, TS types generated | live |
| 8 | 2026-08-27 | Optional panels in 3.0; 3D Visual Exporter and Electrode Placement to 3.1 | Electrode Placement landed in the Simulator instead |
| 9 | 2026-08-27 | `loader.py` shrinks to a wrapper sharing Electron's env computation | live |
| 10 | 2026-08-27 | Windows: unsigned NSIS, no `electron-updater` in 3.0 | live |
| 11 | 2026-08-27 | Per-project compose stacks; docker socket stays mounted; per-subject QSIPrep `-w` | live |
| 12 | 2026-08-27 | X11 hygiene: `xhost` scoped and reverted on exit | moot — X11 removed (21) |
| 13 | 2026-08-27 | Decide PEP 562 lazy imports from the import-timing spike | done: the server imports SimNIBS lazily |
| 14 | 2026-08-27 | Preload bridge budget, **13** top-level entries, no growth without an ADR line | live |
| 15 | 2026-09-02 | Tetravox as a service: a released embed bundle in an iframe, no Tetravox source in this repo | supersedes 3–4; viewer half re-decided by 27 then 29 |
| 16 | 2026-09-02 | Freeview/Gmsh/X11 kept only as the no-WebGL2 fallback | superseded by 21 |
| 17 | 2026-09-02 | Workflow-first IA and the density rules; one subject switcher; Panels group dissolved | live |
| 18 | 2026-09-03 | Native bundled Python runtime as the deployment target | parked by 22 |
| 19 | 2026-09-03 | FreeSurfer not required by default (charm + `subject_atlas` + FastSurfer `--seg_only`) | live |
| 20 | 2026-09-03 | Dependency-free typed Docker Engine API client; no dockerode; CLI only for `docker context inspect` | live |
| 21 | 2026-09-03 | X11 removed from the product with the viewers | live |
| 22 | 2026-09-03 | **Docker stays the single runtime**: one image `idossha/ti-toolbox:<ver>`; native runtime parked, not deleted | live |
| 23 | 2026-09-03 | The embed ships inside the image and is drawn on the host GPU; no X11 anywhere | superseded by 27, restored by 29 |
| 24 | 2026-09-03 | Compose remains the stack definition; the app realises it through the Engine API client | live |
| 25 | 2026-09-05 | Landing page = Overview; batch = a scheduler cap; one shared terminal; run-page panes draw a packaged guide; the Viewer loads on command | live |
| 26 | 2026-09-05 | Tetravox updates itself against a protocol range; electrode dots; one selection grammar; a pipeline is a job group | live, except the electrode/embed halves (27) |
| 27 | 2026-09-06 | Native run-page panes; the viewer is a separate desktop application; jobs tables | pane half live; viewer half superseded by 29 |
| 28 | 2026-09-06 | Managed host install of Tetravox; the pipeline's Subjects node and readiness gating; jobs tables on all three run pages | install half superseded by 29; the rest live |
| 29 | 2026-09-06 | **The embed is restored, baked in the image, on the Viewer's own two sub-pages.** Nothing installs Tetravox on the host | live |
| 30 | 2026-09-07 | External audit response: the six scientific corrections, the server hardening, one release workflow | live |

### <date> — <title>

**Decision.** What is now true.
**Why.** What made it necessary — the ask, the defect, the measurement.
**Cost.** What it costs, what it rules out, what was rejected to get here.
**Revisit if.** The condition under which this should be reopened.
```

A decision that was later reversed keeps its entry and gains a **Superseded by …** banner at the
top; the entry that replaced it says what it reverses. Two entries here are marked as *open*
rather than decided and carry no **Decision** — that is deliberate, and they say so.

### 2026-09-04 — Tabs retain their live page and renderer

**Decision.** Architecture §2 retains visited pages for the project session and isolates their subject
and route context. Inactive pages relinquish commands, keyboard actions and status ownership.

**Why.** The production PyQt main window creates each tab once. The v3 route outlet instead removed
the page, destroying its iframe and camera even where a session bag restored some form values.
The maintainer made unchanged state across tab changes a non-negotiable requirement (R1).

**Cost.** Serializing a growing list of form fields misses validation and viewer
state. The older embed plan's visible-only lifetime released WASM memory but violated navigation
continuity. Project changes still dispose frames; this decision does not retain past sessions.

**Revisit if.** A retained page's memory becomes a problem on a small machine, or a page appears whose live state is cheap enough to serialise.

### 2026-09-04 — Preview controls belong to the workflow

> **Superseded by *2026-09-06 — The run-page panes render themselves; the embed was never a pane*.**

**Decision.** Run-page scenes were an embed mounted with `presentation=viewport`, with skin and
grey-matter opacity driven over the layer protocol. **Why.** Full Tetravox chrome consumed a small
pane and duplicated workflow decisions. **Cost.** Host-injected CSS would have coupled us to private
viewer DOM. **Revisit if.** Never — the panes became our own renderer.

### 2026-09-04 — Existing primitives govern control consistency

**Decision.** Architecture §4 keeps the existing token system and makes shared controls contain long
values, carry accessible names and reserve a consistent primary-action position (R2).

Workflow run actions explicitly use the 32px primary token, including Source's two in-card
pipelines; ordinary controls use 28px. This preserves the same hierarchy with or without an action bar.

**Why.** Separate page variants would repeat the same layout and accessibility defects. No new
dependency or scientific configuration format is introduced by this pass.

Verification results are recorded in [BENCHMARKS.md](BENCHMARKS.md) after the commands run.

**Cost.** One more rule the pages must obey, and two sizes to remember; no new dependency and no new configuration format.

**Revisit if.** A page needs a control size the 28/32 px pair cannot express, or the token system is replaced.

### 2026-09-04 — Preview build failures require explicit retry

**Decision.** Architecture §3 stops manifest/atlas polling on HTTP failure and offers an explicit retry.
Bounded automatic retries remain for transport failures.

**Why.** The server reports an asynchronous build error once, then consumes it. An automatic retry
starts another build and can return HTTP 202 again; that success resets the retry counter and hides
the underlying failure forever. The real atlas mesh-index bug exposed this loop. Keeping the error
visible prevents repeated work and gives the user the actual reason the preview is unavailable.

The preview also waits for a required atlas before sending its first scene. Loading temporary
anatomy and then the atlas concurrently left duplicate skin/cortex layers in the live renderer;
the atlas-ready gate removes that dependency race without changing the scientific data.

**Cost.** One extra click on a real failure, in exchange for never hiding one.

**Revisit if.** The server starts reporting a build error durably, so a retry can tell a new failure from a repeat of the same one.

### 2026-09-05 — The app opens on a project Overview, and Subject Info is deleted

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

**Cost.** Keeping the per-subject fan-out behind a higher cap moves the cliff
without removing it. Removing `GET /api/catalog/subject-info` from the contract is breaking and
belongs to the API's next versioned cleanup; it stays, unused.

**Revisit if.** The aggregate query stops being bounded as projects grow, or a per-subject detail view is asked for again.

### 2026-09-05 — Terminal Clear is presentational, not destructive

**Decision.** Architecture §6: one interactive log renderer (`ui/Jobs.tsx::JobConsole`) over one
pure transform (`app/jobs/logLines.ts`), with a source-aware Clear implemented as a per-source
sequence watermark over the caller's array.

**Why.** The maintainer asked for a scrollable, clearable terminal whose logic is shared between
pages. A Clear that spliced the array would destroy the record the console exists to show, and
would differ from what the log file and the event stream say.

**Cost.** Truncating the log file, or dropping server events, makes Clear
irreversible and makes the console disagree with `Reveal log file`. Per-page terminal
implementations were what produced two copies of the event→line conversion in the first place.

**Revisit if.** Someone genuinely needs to truncate a huge log on disk — a different feature, which must say so in its own words.

### 2026-09-05 — Batch execution is a scheduler cap, not renderer request timing

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

**Cost.** A client-side semaphore around `Promise.all` still cannot see the
scheduler's budget or the directory locks, and dies with the window. Per-subject POSTs with a
`group_id` tag would leave the cap unenforced on the only side that can enforce it.

**Known limit.** The cap counts jobs, not distinct subjects: on the Simulator, one subject with
three montages is three jobs, so a cap of 2 can run two montages of the same subject together.
`tit.jobs.locks` is what keeps that safe, and the control's help says "jobs", not "subjects".
Subject-count semantics would be a scheduler change plus a contract note.

**Revisit if.** Users read the cap as subjects rather than jobs; subject-count semantics are a scheduler change plus a contract note.

### 2026-09-05 — The workflow 3D panes draw a fixed guide, not the selected subject

**Decision.** Architecture §3 and §6: Simulator, Optimizer and Analyzer panes draw a packaged,
immutable guide served by `GET /api/guide/*`, derived from the SimNIBS example subject `ernie`
(GPL-3.0, redistribution permitted; see `tit/scene/guide/PROVENANCE.md`). The click-to-place sphere
gesture is removed from these panes.

**Why.** The maintainer asked for "a general individual, for example, Ernie". Coupling the pane to
the first selected subject re-keyed three queries on every selection change — a cache-cold 184 MB
mesh extraction and a remount for ticking a second subject — and let one subject's anatomy produce
a subject-RAS coordinate written into a *different* subject's configuration. 15.5 MB of derived,
bounded artifacts replace a per-project 184 MB read.

**Cost.** Transforming a guide pick into the target subject's space approximately
is exactly the silent-wrongness this removes; a real picking mode needs an explicit space/transform
contract. Rebuilding the guide at runtime, or packaging a whole `m2m` directory, gives up the
"immutable, no build, no project" property that makes the pane free.

**Revisit if.** A pane needs a pick in the selected subject's own space — that requires an explicit space/transform contract first.

### 2026-09-05 — The Viewer loads on command, not on selection

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

**Cost.** Debouncing the auto-load keeps every failure mode and adds a race.
404-ing an unknown `atlas` turns a stale bookmark into no picture at all. The atlas menu offers the
voxel atlases only: FreeSurfer `.annot` cortical parcellations are surface data and would silently
resolve back to the default.

**Revisit if.** Loading a scene becomes cheap enough that a torn-down picture costs the user nothing.

### 2026-09-05 — The Tetravox release index is the GitHub Releases API, and the pin is a protocol range

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

**Cost.** Comparing version numbers couples two release trains that have no reason
to move together. Downloading first and letting the installer refuse spends 6 MB to produce a worse
message. An authenticated request would put a credential this app must then protect into a config
file, for a public repo's public releases; unauthenticated 60 req/h is ample for one check per start
plus one per day, and a 403 is "could not check", not an error dialog.

**Revisit if.** Unauthenticated rate limiting starts refusing the daily check, or Tetravox publishes an index of its own that a release writes.

### 2026-09-05 — Tetravox updates install themselves by default, and "newer" means newer than what we installed

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

**Cost.** Image-only delivery (keeps the release coupling, and users pinned to a
tag never get the fix). Default-off (a check that only ever tells you something exists is a chore
list). A new type on `/ws/jobs` or `/ws/system` — both have consumers that parse exactly one shape,
and `events.schema.json` describes a job's `events.jsonl`, which no app-level event can be; hence
`/ws/tetravox`. The toast is deliberately not a reload: a mounted pane keeps its iframe and its
bundle, and a new mount gets the new one.

**Revisit if.** An automatic update ever breaks a working project — the rollback pin is the escape hatch that would then have to prove itself.

### 2026-09-05 — Electrodes are dots whose colour is their whole state

> The embed-specific half (never sending `setPointTool`/`setPointSelection`, the explicit idle
> colour that worked around the shipped normaliser) is superseded by *2026-09-06 — The run-page
> panes render themselves*: the pane is our own renderer, so "no ring" is structural. The rule
> itself stands.

**Decision.** An electrode says everything with colour — neutral grey idle, 35 % grey disabled, the
channel's hue when placed. No ring, no outline, no second glyph. Names are shown for placed
electrodes only. The channel palette is **Okabe-Ito**, read by the pair editor, the channel legend
and the 3-D pane from the one `channelCss()`.

**Why.** A selection ring is unreadable on a 185-electrode net and cannot say *which* channel a
marker belongs to — the maintainer asked for colour instead of circles. The old four-hue palette put
green next to orange, exactly the pair a deuteranope cannot separate, and a four-pair mTI montage
uses all four.

**Cost.** A layer-level `selected` colour cannot encode the channel. Radius-as-state was inert in
the shipped embed.

**Revisit if.** A net grows dense enough that dots overlap at usable zoom.

### 2026-09-05 — One selection grammar, with the receipt as the confirmation

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

**Cost.** A plain click now selects one row instead of adding one (⌘-click adds).
`MultiSelect` chips and the per-slot `Select` combos are gone from the pages (`MultiSelect` survives
for schema-driven forms). `PlanGrid` is no longer the primary confirmation. Four different
existing-output dialogs became one, two of which had offered no Skip at all — finishing a half-done
batch had meant deselecting its finished rows by hand.

**Revisit if.** A page needs a selection idiom `SelectionList` cannot express — the answer is to extend it, never to add a sixth.

### 2026-09-05 — A pipeline is a job group, not a workflow engine

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

**Cost.** A pipeline runtime (a second executor). Resolving dynamic bindings in the
client (the client would have to poll for a directory name and then submit, which is client-side
sequencing by another name). Failing the consumer when a resolve step found nothing: leaving the
field as the canvas set it makes it fail exactly as an unfilled form field does, with the same
message.

**Revisit if.** A pipeline genuinely needs a conditional, a retry or a loop. That is a second executor, and a decision of its own.

### 2026-09-05 — React Flow is the canvas; `nbformat` is an optional extra

**Decision.** `@xyflow/react` 12.11.6 (MIT), pinned exactly, is the pipeline canvas — the only new
renderer dependency of the feature. `nbformat>=5.1.4` is a `[project.optional-dependencies] pipeline`
extra, not a hard dependency, and both container recipes install it; `POST /api/pipelines/export`
returns an honest 501 naming the missing module when it is absent.

**Why.** The canvas needs node/edge rendering, pan/zoom, typed handles and a connection-validation
hook — weeks of pan/zoom, hit-testing and handle geometry for no domain value if hand-rolled, and
`dagre` plus static SVG has no interaction at all. `pyproject.toml`'s `dependencies` is deliberately
empty because `tit` is installed into SimNIBS's own interpreter, where an unpinned resolve fights
SimNIBS's pins; an extra keeps that property while the desktop app always has the module.

**Cost.** React Flow is used as a *controlled* component, which means the page must apply
**every** `NodeChange` it emits — applying only position changes throws away its measurements and it
keeps unmeasured nodes at `visibility: hidden`.

**Revisit if.** React Flow's licence or maintenance changes, or `nbformat` becomes needed on a path that is not optional.

### 2026-09-05 — Notebook export is public-API-only, and carries the document in its metadata

**Decision.** `POST /api/pipelines/export` emits an `nbformat` v4 notebook whose code cells call only
what `docs/wiki/scripting.md` documents, in topological order, with bindings expressed as Python
variables; the pipeline document rides along in `metadata.ti_toolbox.pipeline`. Cell ids are
deterministic, so export is byte-stable. **Importing an arbitrary hand-edited notebook is a
non-goal**; a future import reads the metadata, never the Python.

**Why.** A notebook that a user runs is a promise about the API it calls, so the gate executes every
code cell against a stub `tit` that defines only the documented names — a call the wiki does not
teach fails the build. The metadata makes the round trip a lookup rather than a parse: reconstructing
a graph from edited Python is guesswork that would be wrong quietly.

**Revisit if.** Import lands — it reads `metadata.ti_toolbox.pipeline`, never the Python.

### 2026-09-05 — Settings' ⌘-number is derived, not hard-coded

> **Superseded by *2026-09-06 (CX5) — The rail counts from ⌘0*.**

**Decision.** `shortcutForSlot` gave each rail row its index and Settings the first digit the rail
did not use. **Why.** Settings was hard-coded to ⌘9 while the rail was eight rows; a ninth row put
two pages on one key. The derivation survives; only where the count starts changed.

### 2026-09-06 — The in-app Tetravox embed is retired; viewing is the host-installed desktop app

> **Superseded by *2026-09-06 (later the same day) — The embed is restored, ships in the image, and is the Viewer's own sub-page*.**

**Decision.** TI-Toolbox would ship no viewer: the Viewer page a data selector handing a
`*.tetravox.json` to the host's Tetravox app, with the embed, `/tetravox/`, `tit/tetravox/**`, the
protocol range, the install store and `/ws/tetravox` all deleted. **Why.** The maintainer asked for
"minimal maintenance", and D3 says the container has no display. **Reversed the same afternoon**:
the container having no display is exactly why the *embed* is the only Tetravox that can draw
inside this app.

### 2026-09-06 — `Capabilities` says nothing about the viewer (breaking)

> **Superseded by *2026-09-06 (later the same day) — The embed is restored…*, which restores `Capabilities.tetravox_embed`.**

**Decision.** `tetravox_embed` removed from `GET /api/capabilities`, on the reasoning that whether
an app is installed on the user's machine is a fact about the host, not about this runtime.
Reversed with the embed the same day.

### 2026-09-06 — The run-page panes render themselves; the embed was never a pane

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

**Cost.** Waiting on Tetravox protocol 2 (`markers`, `pick`, `camera`) makes a pane
feature depend on another product's release cadence; the parked work is recorded in `RELEASE.md` §B and
remains useful upstream. Rendering only 2-D slices in the pane loses the electrode geometry that is
the whole point of the Simulator's pane.

**Revisit if.** The two renderers are converged — an open question, tracked in `RELEASE.md` §B.

### 2026-09-06 — The guide packages `TVSC1` labels again

**Decision.** `tit/scene/guide_build.py` packages per-vertex `uint16` label payloads (`LABEL_FORMATS
= ("tvsc", "gii")`), ~0.99 MB per atlas, 2.96 MB on the installation.

**Why.** They were dropped on 2026-09-05 on the premise that nothing read them, which was true only
while the native renderer was retired; the day it came back the cortex had no regions to highlight.
A test pins them by **alignment to the `gm` surface** — same vertex count, same first vertex — not
merely by presence, because a label payload for a different surface is the failure that looks like
a working feature.

**Cost.** ~0.99 MB per atlas, 2.96 MB on the installation.

**Revisit if.** The native renderer is retired again; it is the payload's only reader.

### 2026-09-06 — One region-selection model

**Decision.** `<ScenePane>` and `<RoiPicker>` edit the same list through the same `regionKey` and
`toggleRegion`, exported once from the scene model.

**Why.** Two toggles that agree today are two toggles. A 3-D click and a form chip must compare
regions the same way or the pane highlights a region the form does not hold — and that divergence
is invisible until a user notices the ROI they clicked is not the ROI that ran.

**Cost.** One more thing the scene model owns, and two callers that may not fork it.

**Revisit if.** A third editor of the same list appears — it uses the same export, or it is a bug.

### 2026-09-06 — A jobs table replaces the subject-set × montage fan-out

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

**Cost.** Per-subject overrides layered on the page-level set keeps the fan-out as
the model and adds an exception mechanism on top of it. A separate "advanced" mode makes the page
two pages with two selection idioms, against §7.4.

**Revisit if.** A table grows past what a user can scan; the cross-product button is the pressure valve.

### 2026-09-06 — The bridge budget is 13, not 12

> **Superseded by *2026-09-06 (later the same day) — The bridge budget is 13, and `viewer` is not one of them*.**

**Decision.** ADR row 14's preload budget moved 12 → 13 for a `viewer` entry
(`probe`/`open`/`setPath`), because opening a scene in another application is a host action.
Reversed with the host-launch design; the budget is 13 for a different reason (`saveFile`).

### 2026-09-06 — The viewer is installed on the host, not baked into the image

> **Superseded by *2026-09-06 (later the same day) — The embed is restored…*.**

**Decision.** The desktop app would download, verify and maintain its own copy of Tetravox on the
user's machine, keyed to the publisher's own release digest and never pinned by us. **Why.**
Tetravox is a windowed application and the container has no display; baking it in chains a Tetravox
release to a TI-Toolbox image release. **Reversed the same day**: nothing installs Tetravox on the
host, and the protocol range is what breaks the release coupling instead.

### 2026-09-06 — A cohort is a node, and a wire is refused on what its subjects have

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

**Cost.** Validating only at Run keeps the canvas honest but moves every mistake
past the point where the user still remembers what they meant. A warning rather than a refusal
makes the edge a fact the user must re-derive; §7.6's issues carry a machine-readable `code` and
`port` precisely so the refusal can say which end is wrong.

**Revisit if.** `tit.pipeline.validate.KIND_READINESS`'s four artefact types stop covering a new job kind.

### 2026-09-06 — All three run pages carry a jobs table

**Decision.** Architecture §7.5 extends to the Optimizer: the Simulator, the Analyzer and the
Optimizer each describe a run as a table in which one row is one job, and the row owns everything
that differs between jobs. Global sections survive only for properties of the *run*.

**Why.** The Optimizer had the same defect as the other two and worse: a target, an objective, an
electrode set and a solver were all page-level, so one page could describe exactly one search. A
row is the unit a user actually thinks in ("this ROI with this goal, and that one with that"), and
making it the unit on all three pages means one grammar to learn rather than three. The
consequence is stated rather than hidden: where a page's rows submit as more than one job *kind*,
one Run is one submission per kind, and the page says so.

**Cost.** Leaving the Optimizer page-level because a search is "bigger" than a
simulation is the argument that produced the defect. A cell that is meaningless for a row's method
prints a muted `—` with the reason in its title rather than a disabled control, which would read
as a choice the user has failed to make.

**Revisit if.** One Run must be one group across kinds — that needs a mixed-kind group on the server.

### 2026-09-06 — Translucent surfaces are resolved as two depth sheets

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

**Cost.** Inventing a palette per atlas makes two views of the same subject
disagree. The first outline implementation drew a border and produced "a border of white shards" on
a folded surface; a thin edge computed in the same pass does not.

**Revisit if.** A third depth crossing is visibly missing, or Tetravox changes its own bound — the two renderers must agree about the same subject.

### 2026-09-06 — The run terminal never auto-pins a finished job

**Decision.** The run page's terminal pins a job only while it is live. A job that has finished is
never pinned by the page on the user's behalf.

**Why.** Auto-pinning a finished job takes the terminal away from whatever the user was reading and
replaces it with a log that has stopped changing — an interruption that costs attention and returns
nothing, since a finished job's log is reachable from the Jobs page whenever it is wanted. The Raw
log tab is now the shared console filling the detail pane, so there is one place that answers "what
did it print", and it is not the run page's terminal deciding for the user.

**Cost.** A user watching a job finish must click to keep reading it.

**Revisit if.** Users report losing track of the job they were watching.

### 2026-09-06 — The Viewer page is a file list, and Open is the only verb

> Partly superseded by *2026-09-06 (later the same day) — The embed is restored…*: the page is the
> **Menu** sub-page and its button is *Open in viewer*. The rule below is why the Menu looks the way
> it does, and it stands.

**Decision.** The Viewer page is an editable list of the files that will open, plus one Open. Layer
appearance — opacity, colormap, threshold, layout, camera — is not duplicated here; it belongs to
the viewer's own inspector.

**Why.** Two applications offering the same appearance controls over the same file is two sources of
truth, and the one the user tuned is not the one that opened. What this app knows and the viewer does
not is *which files belong together*, so that is the whole job of the page. The written scene is a
real file in the user's own project and opens later by double-clicking, with no app in the middle.

**Cost.** A composition panel with layers, layout, camera and presets was built first and is the
version this replaced; it was a better *panel* and a worse *page*, because every knob on it was a
knob the viewer already had and would win.

**Revisit if.** Layer appearance turns out to be something this app knows better than the viewer does.

### 2026-09-06 (later the same day) — The embed is restored, ships in the image, and is the Viewer's own sub-page

**Decision.** Architecture §7.1 is replaced again, reversing this morning's three entries above. The
Tetravox **embed** is the viewer: baked into the image at `/opt/tetravox/embed`, served by
`tit.server` at `/tetravox/` with its own CSP, delivered and updated at runtime by
`tit/tetravox/{protocol,store,install,updates}.py` behind `GET/POST /api/tetravox*` and
`/ws/tetravox`, and reported by `Capabilities.tetravox_embed`. **Nothing installs Tetravox on the
host, and there is still no X11 anywhere.** The Viewer page becomes two sub-pages shown as indented
rail rows — **Menu** (composition, its button *Open in viewer*) and **Tetravox** (full-bleed iframe,
a slim strip with the scene name and `Reload`). ADR row 14's budget loses the `viewer` entry again.

**Why.** The maintainer, verbatim: *"The Dockerfile should contain Tetravox. We should not install
Tetravox on the host machine — forbidden. Tetravox should not be visually embedded in the TI-Toolbox
tab; it should open in its own [view]. In the Viewer, the left menu has two subsections: the Menu,
and below it the actual Viewer."* The engineering reading of D3 was half right: the container having
no display is exactly why the *embed* is the only Tetravox that can draw inside this app — a windowed
app baked into the image has nothing to draw on, and one installed on the host is an acquisition the
user has to make and a per-platform install path this project would then own. What the morning got
right — that the Viewer should not be a picture squeezed beside a form — is kept, and answered by the
sub-page split rather than by deleting the renderer.

**What the restored machinery buys.** Roughly 3,000 lines and ~130 tests, and it is not free. It
buys the one property this program was asked for and cannot get any other way: *a Tetravox release
does not imply a TI-Toolbox release.* The protocol range is what keeps the coupling from becoming a
version pin — a pane asks for a named feature, the range lives in two files a cross-language test
keeps in step, an additive Tetravox release needs no change here, and a breaking one costs one
constant. The rest is delivery honesty: a digest verified before the archive is opened, an extraction
that refuses `..`, absolute paths and links (Python 3.11's unfiltered `extractall` writes outside the
destination in this image), an atomic activation, a pin so rollback is not a re-download.

**Cost.** An in-page segmented control was built first and rejected — the maintainer specified the
rail precisely. Making the sub-items *pages* was rejected too: separate mounts are exactly what
destroys the iframe. What landed is one narrow concept, `PageDef.subNav` plus `pagePath()`, over the
existing flat model, with `RetainedPages` keying retention on the first path segment so
`/viewer/menu` and `/viewer/tetravox` are one mounted component. Two calls — one for the file, one
for the iframe — were rejected: a job finishing between them is enough to make the list, the file and
the picture disagree, so `POST /api/view/open` resolves once and returns both addressings.

**Known limit.** Sub-items are not drawn in the icon rail below 1440 px; the command palette carries
both as rows, which makes it a real accessibility path there rather than a convenience.

**Known consequence.** Two renderers: the embed on the Viewer sub-page, the app's own WebGL2
renderer on the run pages (§7.2, untouched). Deliberate — the panes draw packaged reference anatomy
and need picking behaviour this project controls; the Viewer draws the user's data and wants the
whole engine.

**Revisit if.** Tetravox ships a protocol past the supported range (one constant), or the two
renderers converge.

### 2026-09-06 (later the same day) — The bridge budget is 13, and `viewer` is not one of them

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

**Cost.** Thirteen host actions to keep reviewed; `smoke.spec.ts` asserts the exact list.

**Revisit if.** A fourteenth host action is genuinely needed — it moves the ADR line, not the assertion.

### 2026-09-06 (NB lane) — notebooks: the kernel is the container's, and the UI is SUNA's

**Decision.** A Notebooks page runs `.ipynb` files on a Jupyter kernel owned by `tit.server`
(`tit/server/kernels.py`, kernelspec `simnibs`, cwd the project), driven over
`WS /ws/kernels/{kernel_id}`, with the files under `<project>/code/ti-toolbox/notebooks/` behind
`/api/notebooks`. At most **2** kernels run at once and one idle for **30 minutes** is shut down.
The renderer is ported from SUNA (github.com/idossha/SUNA), GPL-3.0, same author, attributed in each
file's header. ARCHITECTURE §7.6.

**Why.** The ask was that "the TI-Toolbox environment is automatically loaded". The environment is
not something to load — it is the container's SimNIBS Python with `tit` on the path, and it is
already where the server runs. Putting the kernel there means "which interpreter?" is never asked:
no picker, no `ipykernel` install prompt, no per-project selection. SUNA needs all three because its
kernel is on the user's own machine, and most of its §16.2 is the machinery for degrading honestly
when that interpreter has no `jupyter_client`. **That entire branch disappears here**, which is why
this port is shorter than its source. Everything hard about a notebook front end is already solved
there for reasons that hold identically here: an iopub content *is* an nbformat output; a plot beats
its own text repr but a DataFrame table beats both; output with no attributable parent is dropped
rather than mispinned; ANSI is parsed because an uncoloured traceback is unreadable.

**Cost.** *Publishing the image's JupyterLab and linking to it* — one HTTP port and no code, and a
different application in a different window with its own auth and no idea what a TI-Toolbox project
is. *Running the kernel on the host under the user's own Python* — SUNA's topology, and it puts the
user back in the business of installing SimNIBS. *Framing the bridge as a child process for symmetry
with SUNA* — a process and a pipe to reach a library already importable in this process.

**Known consequence — Jobs loses ⌘9.** Notebooks sits after Pipeline (the maintainer's placement),
making ten workflow rows against nine digits. Resolved by the CX5 entry below (the rail counts from
⌘0), after `shortcutForSlot` was found returning `"10"` — a chord no keyboard can send.

**Known limit — interactive plots fall back to a picture.** SUNA renders plotly/vega through a
privileged `suna-output:` scheme because the renderer CSP forbids kernel-supplied scripts and a
`srcdoc` iframe inherits it. TI-Toolbox has no such scheme. `pickRepresentation` still *recognises*
the interactive mime, which is what lets `Outputs.tsx` fall back to the static PNG beside it;
matplotlib, the dominant case here, was never affected.

**Revisit if.** A user needs a kernel outside the container. That is SUNA's topology, and its whole
honest-degradation branch comes back with it.

### 2026-09-06 (NB lane, later) — the cell is a CodeMirror, and the kernel is the completer

**Decision.** A code cell is **CodeMirror 6** with `@codemirror/lang-python`, whose highlight palette
is built from the app's own CSS variables rather than a colour list. Completion is answered by the
**running kernel** over the existing `/ws/kernels/{id}` socket (`complete_request`,
`inspect_request`), surfaced through CodeMirror's autocompletion on ⇥ and ⌃Space. A sliders popover
carries autocompletion, signature help, auto-close brackets, line numbers, indent size, font size and
word wrap, persisted in `localStorage`. New dependencies: `katex` (which SUNA also depends on) and
six `@codemirror/*` packages. ARCHITECTURE §7.6 rules 4–5.

**Why the editor changed.** The first version shipped a `<textarea>` to avoid the dependency and
recorded that as a known limit. The maintainer's answer was that the cost was worth paying: a
textarea cannot colour Python, cannot indent a block and has nowhere to put a completion popup, and
"easier for users to develop" is the entire point of the page. A markdown cell is still a textarea —
there is nothing to highlight in prose.

**Why the kernel and not `pylsp`.** The image already has `python-lsp-server` and `jupyterlab-lsp`,
and using them is the wrong move. A language server reads *files*; a notebook's meaning lives in an
interpreter that has already run `from tit import catalog`, and only that interpreter can say what
`catalog.` holds — it is the thing holding it. IPython answers `complete_request` from that live
namespace using `jedi`, already inside `ipykernel`. So the choice was between a second process to
install, configure and keep in sync with a namespace it cannot see, and one message on a socket that
is already open. Verified in the container: `jedi 0.19.2`, and `from tit import get_pa` completes to
`get_path_manager` against the real kernel.

**Why the palette is variables.** `EditorView.theme` is compiled once, so a theme built from hex
values would need a second palette and a rebuilt editor on every theme switch. Every rule resolves to
`var(--…)` instead. KaTeX is likewise a real npm package compiled into the bundle, **not** a CDN
script: the renderer's CSP forbids remote scripts, and a CDN would have drawn nothing and said
nothing about it.

**Known consequence — a notebook restart could take the API down, and did.** Restart closed the ZMQ
channels while the iopub and shell pumps were still polling them; libzmq's answer was an assertion
failure that aborted the `tit.server` process — every running job's API, killed by a notebook button.
The pumps are now stopped and joined before anything touches a socket, and the client is rebuilt
because `restart_kernel` makes the old session key stale. Three tests pin the ordering. This was
invisible to every unit test and to the mock e2e. (The other three defects the driven runs found —
a command-mode guard testing for a textarea, ⇥ dismissing the popup it should accept, and a
completion range that filtered every option away — are in `HISTORY.md`.)

**Cost.** *A CDN for KaTeX and CodeMirror* — blocked by the CSP, silently. *Client-side static
completion from a Python grammar* — it cannot see the namespace, which is the only thing that makes
`tit.` completion worth having. *Settings on the server, per project* — these follow the person, not
the project, so they are `localStorage` and not in the `.ipynb`.

**Revisit if.** The six `@codemirror/*` packages plus `katex` become a maintenance cost out of
proportion to one page.

### 2026-09-06 (CX5) — Grey matter is opaque, and only the skin has an opacity slider

**Decision.** The pane's grey-matter surface is drawn fully opaque and its opacity control is gone;
the skin keeps its slider. Translucency remains a property of the outer surface only.

**Why.** A translucent cortex under a translucent scalp was not readable as anatomy. Two sheets of
alpha compose to a colour that belongs to neither, and the fresnel silhouette boost every surface
carries pushes both towards white at the rim — so a region's own atlas hue arrived at the screen
diluted by a factor that depended on where on the head the fragment was, which is precisely what the
atlas-border work then had to measure around (`#4b327d` reaching the buffer as `[150,137,169]`). One
translucent sheet over an opaque one has a single, predictable composition.

**Cost.** *Order-independent transparency for both sheets* — real cost for a view
whose depth reading was never the complaint. *Keeping the slider at a fixed default of 1.0* — a
control that exists but must not be moved is worse than no control.

**Revisit if.** Order-independent transparency becomes affordable, or the open idle-marker contrast measurement below forces a design change.

### 2026-09-06 (CX5) — The camera is the user's, not the data's

**Decision.** A pane keeps its camera across a payload change: switching net, montage or subject
reframes nothing. The framing pass runs on the pane's *first* payload and on an explicit reset.

**Why.** Changing a montage to compare two placements threw away the view the comparison was being
made from — the one interaction where the camera matters most was the one that destroyed it. A
camera is a statement about what the user is looking at; a new net is not a statement about that.

**Cost.** A first payload that frames badly stays badly framed until the user resets.

**Revisit if.** A payload change ever moves the anatomy far enough that the kept camera frames nothing.

### 2026-09-06 (CX5) — Free-hand placement lives in the Simulator, not in a panel

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

**Revisit if.** Real 3-D electrode geometry is modelled — it needs a surface-tangent frame per electrode and a shape the solver agrees with.

### 2026-09-06 (CX5) — Subject Info is deleted rather than migrated

**Decision.** The Subject Info Viewer panel, its page and `GET /api/subjects/{id}/info` with the
`SubjectInfo`, `SubjectSimulationInfo` and `FileRef` schemas are removed from the contract.

**Why.** Overview already answers "what does this subject have" for every subject at once, in one
bounded request. Two surfaces for one question means two answers whenever one of them lags — and the
panel's per-subject request was the one that would have had to grow a column each time a data stage
was added.

**Cost.** A breaking contract removal, and any client using `GET /api/subjects/{id}/info` loses it.

**Revisit if.** A per-subject question appears that Overview cannot answer inside its bounded request.

### 2026-09-06 (CX5) — A plan's ETA is modelled from what drives the job, not from a constant

**Decision.** `POST /api/plan` returns an estimated wall clock derived from the job's own drivers —
the leadfield's presence and size, the electrode count, the search's iteration budget — rather than a
per-kind constant.

**Why.** The number exists to answer "do I start this now or after lunch", and a constant answers
that wrongly in both directions: it makes a flex search on a computed leadfield look like the same
half hour as one that must build it first. The drivers are already in the config the plan validates,
so the estimate reads the same object the run will.

**Revisit if.** The estimates are measured against real runs and found systematically wrong in one direction.

### 2026-09-06 (CX5) — The image carries what the v3 server needs, and nothing the GUI used to

**Decision.** `Dockerfile.ti-toolbox` drops gmsh, PyQt5 and the SimNIBS TMS coil model set.

**Why.** v3 has no Qt GUI and no external mesh viewer to launch: Gmsh and Freeview were the v2
flow, and the run pages now draw their own panes (§7.2). PyQt5 was a dependency of a GUI that no
longer ships. The coil models are for TMS, which this toolbox does not simulate. Each was carried
only because it had always been carried.

**Cost.** Anything still importing `tit.gui` fails in the image rather than starting a
window nobody can see, which is the honest failure. The v2 loader path is unaffected — it runs its
own image.

**Revisit if.** TMS is ever simulated, or an external mesh viewer returns to the workflow.

### 2026-09-06 (CX5) — A triangle's region label is transferred, not left to the provoking vertex

**Decision.** Before upload, each grey-matter triangle is rotated so its **last** corner carries the
majority region label, and label shading is `flat`. Winding is preserved: `[a,b,c] -> [c,a,b]` is a
rotation, so normals, culling and the outward orientation the service guarantees are untouched.

**Why.** The shader reads the region id from a `flat` varying, and WebGL 2 fixes the provoking vertex
to the triangle's last index — an arbitrary corner as far as the anatomy is concerned. On the
packaged ernie guide with DK40, 15 289 of 145 402 triangles (10.5 %) straddle a border; 14 965 have a
clear two-to-one majority, and with the last corner deciding, roughly a third of those took the
*minority* label. Each is a triangle-sized spike of the neighbour's colour across the border — the
saw-tooth the maintainer reported. Rotated, the border follows the mesh edges between the regions.

**Cost.** *Interpolating labels* — a label is not a quantity and the midpoint of two
region ids is a third region. *Splitting border triangles* — changes the mesh the solver and the
service agree on to fix a shading artefact. A triangle whose three corners are three different
regions is a genuine triple junction (324, 0.22 %): there is no majority to rotate to, and it is
left exactly as it came.

**Revisit if.** The guide's mesh changes, or a smooth-shaded label path is added — a rotation is only correct for `flat`.

### 2026-09-06 (CX5) — The rail counts from ⌘0

**Decision.** `shortcutForSlot` is the row's index in `NAV_ORDER`, starting at zero: ⌘0 Overview
through ⌘9 Jobs. Settings takes no digit and keeps ⌘, as its only chord; Help stays the `?` sheet.
This supersedes the 2026-09-05 entry above, which gave Settings the first digit the rail did not use.

**Why.** Maintainer, 2026-09-06: *"start from 0 the rail digit and finish at 9."* A keyboard has ten
digits and the rail has ten workflow rows — they match exactly, but only when the count starts at
zero. Counting from one spent ⌘0 on Settings, which is not a rail row at all, and left the tenth row
with no key: the Notebooks insertion had just taken ⌘9 away from Jobs, the row opened by keyboard
many times an hour.

**Cost.** *Moving Notebooks to the end of `NAV_ORDER`* — implemented first, and it
buys Jobs its key back by taking one from Notebooks and by putting the rail out of workflow order.
*Printing ⌘10* — a chord no keyboard can send. An eleventh row would again have no number, which is
a limit of ten digits rather than of this function, and `NAV_ORDER`'s job to stay within.

**Revisit if.** An eleventh rail row is added. Ten digits is the limit, and staying inside it is `NAV_ORDER`'s job, not `shortcutForSlot`'s.

### 2026-09-06 (CX5) — A cap with no electrodes is not an EEG net

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

**Cost.** A cap file that legitimately carries no `Electrode` rows would disappear too.

**Revisit if.** A zero-electrode cap file turns out to mean something to a user.

### 2026-09-06 (CX5) — Open: an idle electrode can be invisible against the opaque-GM scalp

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

**Revisit if.** The maintainer makes the design call — a thin contour on *every* marker is the obvious candidate, and it keeps colour as the whole state signal because the contour is constant.

### 2026-09-07 (NB lane) — signature help from the kernel, and nothing left half-built

**Decision.** Signature help is a kernel round trip like completion: `inspect_request` on `(` and on
⇧⇥, showing IPython's own signature line and the docstring's first paragraph in a CodeMirror
tooltip, honouring the existing `signatureHelp` preference. Escape dismisses the tooltip **before**
it leaves edit mode. The kernel status pill is also the recovery — clicking it restarts, or starts
one when none is running. ⌘S saves from anywhere on the page, leaving the page flushes rather than
prompting, and closing the window hands every kernel back. ARCHITECTURE §7.6 rules 5 and 9.

**Why the tooltip is a summary and not the reply.** `inspect_reply`'s `text/plain` is the whole of
`get_path_manager?` — signature, full numpydoc body, `File:`, `Type:` — forty lines hanging over the
code it describes. `parseInspect` reads IPython's *field* format (each field ending at the next
label, not at the next newline, because signatures wrap) and `firstParagraph` stops at a blank line
**or at a numpydoc section underline**.

**Why Escape needed the highest precedence.** The notebook's own Escape leaves edit mode; bound at
equal precedence one keystroke would have done both, throwing the author out of the cell they were
typing in. `Prec.highest` puts the dismissal first and returns false when there is nothing to
dismiss.

**Why leaving the page flushes instead of prompting.** Autosave already writes 1.5 s after the last
keystroke, so the only thing a modal could ask is whether to do the save the app was about to do
anyway. The guard writes. What was actually broken — navigating inside that 1.5 s window losing the
edit — is fixed, and that is what the e2e asserts.

**Revisit if.** The kernel round trip becomes too slow on a loaded container to answer a keystroke.

### 2026-09-07 (CX6) — the six numerical corrections, and the two modelling calls with them

*One entry for SCI-01 … SCI-08. The user-facing record — what was wrong, which versions, which
outputs move and by how much, how a user spots an affected result, and whether to re-run or rescale
— is [`SCIENTIFIC-CORRECTIONS.md`](SCIENTIFIC-CORRECTIONS.md), which is the page to read first and
the page a change to any of these must update. The numbers are in
[`BENCHMARKS.md`](BENCHMARKS.md) § External audit response. What is recorded here is only the
decision each one settles.*

**Decisions.**

| | Decision | Why, in one line |
|---|---|---|
| **SCI-01** | Two-sided and left-tailed cluster inference labels positive and negative supra-threshold voxels as **separate** components (`engine.label_signed`) and maps a cluster to a statistic monotone in extremeness (`engine.tail_statistic`), so observed and permuted values live on one scale and the comparison is always right-tailed. `surface._label_graph_signed` does the same on fsaverage. | A bare `scipy.ndimage.label` fused touching opposite-sign blobs into one cluster whose signed mass is their *difference*, and `max()` over signed masses under a left or two-sided tail selects the cluster **closest to zero**. The largest discrepancy measured was a null of **−64.06 where the correct oriented value is +64.06** — the wrong sign, so nearly any observed cluster cleared it. |
| **SCI-02** | `tit/stats/nifti.py::_check_same_grid` compares shape, direction block and origin against the first subject and **raises**, naming the subject, its file and the reference. | The loader kept the first affine and never looked at the others, so any images sharing an array shape were compared voxel-by-voxel — translated, rotated, rescaled or left/right flipped alike. A handedness flip is the worst case and is named in the error. |
| **SCI-03** | `Analyzer._compute_focality_metrics` takes an explicit `weight_to_cm`: `1000.0` on the voxel path (mm³ → cm³), `100.0` on the mesh path (mm² → cm²). The field **names** (`focality_*_area`) are deliberately unchanged. | One hard-coded constant served two unit systems. Making the caller state the unit is the fix; keeping `..._area` as the name of a volume is a knowing wart, paid so scripts and the group aggregator keep working. |
| **SCI-04** | `pval_from_histogram(..., sampled=True)` (the default) returns `(b+1)/(m+1)`; `sampled=False` restores the exact `b/m`, documented as correct **only** for an exhaustive enumeration. | `b/m` over a Monte-Carlo null can return **0**, and is anti-conservative exactly in the tail where cluster inference operates. `p = 0` from 1000 draws is not a measurement. |
| **SCI-05** | `voxel_volume_mm3(affine)` is `|det A|` and `_world_distance_grid` is `‖A(v − c)‖`; `_analyze_voxel_roi` takes the affine and derives the volume itself, so there is no second, disagreeing source of geometry. | `header.get_zooms()` are the affine's **column norms**; `prod(zooms)` and the zoom-scaled distance both assume orthogonal voxel axes, false for any sheared affine. |
| **SCI-06** | `engine._safe_t` divides under `np.errstate` so the IEEE result reaches `t.sf` unchanged (`0/0` → `nan`, `±x/0` → `±inf` with the tail-consistent p, matching scipy exactly); `ttest_voxelwise` **excludes** degenerate voxels from `valid_mask` and logs the count, and the permutation workers neutralise any degeneracy a relabelling creates. | `t = 0, p = 1` for every zero-standard-error voxel reported the strongest evidence the data can carry as the weakest. `nan`/`inf` cluster mass would corrupt the permutation machinery, hence the exclusion. |
| **The field list is a legal pair count** | `tit/calc.py::_validate_field_list` accepts exactly `tit.constants.is_valid_pair_count`'s counts — even, at least two — the same rule the montage config validates. | One rule, one place. An odd field list otherwise reached the envelope through a door the config had already closed. (Supersedes the earlier "`channels` partitions `fields`" entry: `main` removed the grouping, and the positional field list is a partition by construction.) |
| **SCI-07** | The exposure metrics are stated over **carriers**, not raw fields: `hf_sar = Σ_c \|E_c\|²`, `hf_peak = max_s \|Σ_c s_c E_c\|`. Which fields share a carrier is the wiring's business, and on `main` the wiring is **positional** — `electrode_pairs` two at a time, each pair at its own frequency — so one field is one carrier and the coherent pre-sum is the identity. No `channels=` argument on either `tit.calc` or `tit.fields`. | Cassarà et al. 2025 Part II p. 8: *"coherent field superposition was used for identical frequencies, and incoherent superposition (i.e., SAR addition) was used when the frequencies differed."* Stating the metric over carriers is what makes it right for *any* wiring; carrying a `channels=` parameter that the shipped `Montage` cannot express is dead surface that can only ever be the identity — see `7a5ee2dd`, `d4706e5a`, `b19a1c26`. |
| **SCI-08** | `_envelope_from_PQ` computes `2√2·Q / (√(P+Q) + √(P−Q))` rather than `√(2(P+Q)) − √(2(P−Q))`. | Algebraically identical, but the subtraction form cancels catastrophically at `Q ≪ P` — weak modulation, i.e. every off-target voxel, which is the denominator of a focality ratio. Below `Q/P ≈ 1e-16` it returns exactly `0`. |

**The engine's modelling convention, stated once.** The simulation is **quasi-static**: every FEM
field is a phasor amplitude vector and there is no time axis. Exposure quantities are therefore worst
cases over the unknown relative phases — the same convention that already derives the modulation
depth. For carriers at incommensurate frequencies the supremum over time of `|Σ_c E_c cos(θ_c)|` is
attained at a vertex of the phase box (a convex function on a box maxes at a vertex), so the sign
enumeration **equals** the time-domain peak rather than merely bounding it. That is checked in
`tests/numerical/` against a synthesised `E(t)`, which is the only place a time axis appears anywhere
in the repository.

**Cost.** SCI-01, -02, -05 and -06 require a **re-run** (the null distribution, the stacking gate or
`valid_mask` itself moved); SCI-03 and -04 are **rescalable**; SCI-07 is recomputable from the stored
per-pair fields without re-running the FEM; SCI-08 changes nothing the old form got right. `greater`
is untouched by SCI-01 (0 of 20 relabellings changed). A group that previously ran may now fail
loudly, and a montage that silently dropped a field now fails — both intended.

**Revisit if.** A tail is added whose oriented statistic is none of the three; a resampling step is
added upstream, at which point SCI-02's check becomes an assertion on its output rather than a gate
on user input; an exhaustive-enumeration path is wired into `correct_groups` (it must pass
`sampled=False`, and nothing does today); or a montage architecture reappears in which several pairs
share one carrier — see the 2026-09-07 amendment below for what that would take.

### 2026-09-07 — allowed electrode-pair counts stated once

**Decision.** One electrode pair is one current channel, and every channel needs a partner to beat
against, so the allowed pair counts are **even and ≥ 2**: 2 (standard TI), then 4, 6, 8, 12, 16 …
(mTI). `tit.constants.is_valid_pair_count` is the single statement of the rule;
`Montage.simulation_mode` and `tit.calc._validate_field_list` both defer to it.

**Why.** The rule was stated three times and two of them disagreed: `tit.calc` required an even
count ≥ 2, while `Montage.simulation_mode` accepted `2 or >= 4` — so a 5-pair montage passed config
validation and then failed deep inside the field maths.

**Cost.** A 5- or 7-pair montage that previously reached the solver now fails at config time. No
such montage can have produced a valid mTI result, so nothing usable is lost.

**Revisit if.** The maintainer wants the tighter rule they also described — pair counts of 2, 4, 8,
12, 16 (multiples of four beyond the first), excluding 6. That is a one-line change to
`is_valid_pair_count`.

### 2026-09-07 (CX6) — a kernel's idle clock starts when a request concludes

**Decision.** `KernelRegistry` stamps `last_used` again on **completion**, not only on submission,
keeps an `in_flight` counter under the same lock the reaper holds, and the reaper skips busy or
starting sessions. Submission joined the critical section that selection and removal were already
in, so a kernel cannot be reaped between `get` and `execute`. The registry takes an injectable
`clock` so the reaper is tested without sleeping.

**Why.** `last_used` stamped at submission means a cell that runs longer than the idle timeout has
its own interpreter shut down mid-execution — the reaper killing the only thing keeping it alive.

**Cost.** A wedged cell now holds a kernel indefinitely; the cap and an explicit restart are the
answer, not a timer. Verified against a **real** SimNIBS kernel with `idle_timeout=3.0`: not reaped
at 1 s, reaped past the cap, `manager.is_alive()` false afterwards.

**Revisit if.** A hung-cell watchdog is wanted — that is a separate, longer, execution-time budget,
not this timeout.

### 2026-09-07 (CX6) — a capped resource is reserved before it is acquired, not after

**Decision.** Two places reserve under the lock rather than trusting an out-of-date snapshot.
`KernelRegistry` reserves a `max_kernels` slot before startup and releases it in a `finally`.
`JobScheduler._tick` treats every running job's recorded lock keys as held (`_reserved_holders`) and
adds a just-admitted job's keys to the snapshot before evaluating the next candidate. `locks.hold`
raises `LockConflictError` on write-against-live-write and never claims a directory owned by a
different, still-live job.

**Why.** Both were the same bug: a check and an acquisition in two critical sections with a
multi-second gap. N concurrent kernel starts all passed a cap none had yet answered; two queued jobs
needing the same exclusive write lock were both admitted, because a runner writes its lock
descriptors only after it has started — and a write lock's directory is named for the resource alone,
so the second job overwrote the first's descriptor and its release freed the first job's lock.

**Cost.** The scheduler admits slightly less aggressively; a spawn that fails leaves the job
terminal, so its reservation is never taken.

**Revisit if.** Lock state moves out of the filesystem — the reservation covers the window in which
the filesystem does not yet know.

### 2026-09-07 (CX6) — an unknown `after` dependency is not a satisfied one

**Decision.** `_dependency_state` skips a job whose `after` names an id it does not know, with its
own distinct reason (`dependency <id> is unknown`), separate from a dependency that failed.
`POST /api/jobs` additionally rejects an unknown `after` at submission with 422, before anything is
persisted.

**Why.** It logged "not found; treating as satisfied" and ran the dependant immediately, unordered,
against a precondition nobody had established — a typo in an id silently discarded the ordering the
user asked for. It is also the right answer during recovery from the job store, where the record
may have been deleted after submission.

**Cost.** A job whose dependency was deliberately deleted now waits rather than running. Deleting a
dependency is the unusual act; `POST /api/jobs/{id}/force` remains the escape hatch.

**Revisit if.** Dependencies become expressible across server restarts by name rather than id.

### 2026-09-07 (CX6) — one subject-id grammar, enforced before an id becomes a path

**Decision.** `tit.paths.SUBJECT_ID_RE` is the grammar: letters, digits, `_` and `-`, first character
alphanumeric, at most 64 — BIDS labels plus the separators existing projects use, matching
`tit.catalog.is_safe_name`. Every `PathManager` accessor that puts an id in a path validates it; the
job routes check before persisting (422), `JobManager.submit` re-checks,
`tit.pre.structural.run_pipeline` checks at the entrypoint, and `ensure_subject_dirs` additionally
refuses any path that does not resolve inside the project root.

**Why.** Ids carrying separators or `..` were accepted and persisted, and
`ensure_subject_dirs(project, "../../../outside")` then created directories outside the project —
reproduced before the fix. Validating at the API alone would leave the config-file and
script-argument routes open, which is why the check sits where the id becomes a path.

**Cost.** A project with a subject directory outside this grammar cannot be driven until it is
renamed; the grammar is a superset of what the toolbox itself writes.

**Revisit if.** A real dataset appears with a legitimate id this rejects — widen the regex in one
place, not the call sites.

### 2026-09-07 (CX6) — a `tools` job's arguments are confined to the project directory

**Decision.** `kinds.command_for` takes the manager's project root and checks **every** argument
before the argv is built, so a job is refused before it is spawned and before any file is created.
`TOOL_ARG_POLICY` declares which options a tool treats as identifiers (`--pipeline`, `--node`), as
subject ids, or as the project root; every other argument falls under the default rule — if it looks
like a path it must resolve inside the project, and a path-shaped argument with no project root bound
is refused rather than trusted.

**Why.** The `tools` allowlist closed *which module runs* but not *what it could be told to touch*:
`config.args` was forwarded verbatim, so an allowlisted tool handed an absolute output path would
write anywhere the container's user can write.

**Cost.** A new tool needs a `TOOL_ARG_POLICY` row if any of its arguments are identifiers rather
than paths; without one it gets the default containment rule, which is the safe direction.

**Revisit if.** A tool legitimately needs to read outside the project — that is an explicit policy
entry, not a relaxation of the default.

### 2026-09-07 (CX6) — a notebook save carries the revision it wrote

**Decision.** Every save carries an edit revision. Only the revision **actually written** clears
`dirty`; edits arriving mid-flight queue a follow-up `PUT` that `flush()` waits on.

**Why.** A save already in flight was joined by the next one, so `dirty` was cleared when the *old*
request resolved and `flush()` returned true without ever sending the text typed while it was in
flight — silent data loss on exactly the slow connection where saving matters.

**Cost.** A burst of edits during a slow save costs one extra round trip. Leaving the page flushes
rather than prompting: autosave already writes 1.5 s after the last keystroke, so a modal could
only ask whether to do the save the app was about to do anyway.

**Revisit if.** The document grows large enough that a per-revision full-text `PUT` is the wrong
unit and a diff is wanted.

### 2026-09-07 (CX6) — the reconnect snapshot is authoritative

**Decision.** The REST job snapshot taken on every (re)connect **replaces** what the store knows:
known jobs are overwritten, missing ones removed, and only jobs the live stream touched while the
request was in flight survive it.

**Why.** The seed only *added* ids the store had not seen, so a job that finished while the socket
was down stayed `running` for ever and a job deleted in the meantime stayed on screen — no WS
message for either was ever coming. A reconciliation that can only add is not a reconciliation.

**Cost.** A job created and completed entirely within the window of an in-flight snapshot request
would be dropped; the live-stream exemption is what prevents that.

**Revisit if.** The snapshot endpoint gains paging — a partial snapshot must not be treated as
authoritative over the whole store.

### 2026-09-07 (CX6) — rich notebook output is sanitised, not sandboxed

**Decision.** `text/html` outputs pass an allowlist that drops `style`, `script`, `link`, `base` and
`iframe`, every `on*` handler and every `javascript:` URL, while keeping DataFrame tables and their
per-cell styling. `image/svg+xml` renders through `<img src="data:image/svg+xml,...">`, where
scripting is off.

**Why.** Both went in through `innerHTML`, so a `<style>` block inside a stored output restyled (or
hid) the app chrome and an `<img onerror>` ran in the app's origin — from a `.ipynb` a user opened,
which is not a trusted document.

**Alternative rejected: a sandboxed `srcdoc` frame.** Documented in `sanitize.ts`. `srcdoc`
inherits the app's `script-src 'self'` CSP, so the frame's own sizing script — and any plotting
library's — would not run. The frame would be safe and useless.

**Cost.** An output that genuinely needs a `<style>` block loses it, and interactive plots stay
unavailable.

**Revisit if.** Interactive plots are wanted: that needs a privileged scheme for output frames (the
way SUNA's `suna-output:` works), which is a shell change, not a notebook change
(`RELEASE.md` §B, Notebooks).

### 2026-09-07 (CX6) — the quit plan belongs to the app, not to the Docker branch

**Decision.** The running-jobs question lives in `shared/quitPlan.ts` and runs for **every** backend
this app owns. Its "stop" answer cancels the jobs and waits — bounded — for the server to
acknowledge before the runtime is torn down.

**Why.** The question was asked on the Docker branch only, so ⌘Q with the bundled native runtime
fell straight through to a `SIGTERM` of the process group (`SIGKILL` 1.5 s later) and ended a
running FEM job without a word. Which backend is running is not something the user's data loss
should depend on.

**Cost.** Quit is slower by the bounded acknowledgement wait when jobs are running.

**Revisit if.** A third backend is added — it must go through `quitPlan`, which is the point of
having moved it there.

### 2026-09-07 (CX6) — one release workflow, for one application

**Decision.** `.github/workflows/release-v3.yml` is the release pipeline; `release-build.yml` and its
companion are deleted, and the legacy 2.x launcher under `package/` is **retired** (ADR row 5's
Phase 6). The pipeline puts everything checkable without credentials first: **plan** (refuse to build
when the tag and the version sites disagree) → **image** (failing loudly when no compatible Tetravox
embed release resolves, rather than baking a placeholder) → **desktop-validate** (unsigned builds for
macOS arm64+x64, Windows and Linux, each inspected and uploaded, published nowhere) →
**create-release** → **desktop-publish** (signed and notarised, failing closed when a signing secret
is absent). `workflow_dispatch` defaults to `dry_run=true`.

**Why.** Pushing a v3.0.0 tag ran `release-build.yml`, which built the **legacy** launcher (its
`package.json` says 2.4.0) with Node 20, while the v3 app is under `desktop/` and needs Node ≥ 22.12
— a v3 tag would have published v2 artifacts under a v3 release title. And while `package/` exists
the repository has two apps, two version numbers and two compose files, and every future automation
has to remember which one is real.

**Cost.** `update_version.py` drops its four `package/` entries and gains `desktop/package.json` and
`dev/loader/docker-compose.dev.yml`, whose old `dev/bash_dev/…` path had been silently skipped on
every bump. `.gitignore`'s `!package/build/` exception moved to `!desktop/build/`.

**Revisit if.** A 2.x point release is ever needed — it would come from the v2 tags, not from a
directory kept alive on `main`.

### 2026-09-07 (CX6) — the packaging check is what makes the validation job worth having

**Decision.** `desktop/scripts/verify-package.mjs` reads the built app's asar directly — no
dependencies, so it runs against a downloaded artifact — and checks the version, the main entry, the
files the app reads at runtime, the absence of dev-only and deleted content, and the per-platform
staged runtime.

**Why, and what it found.** Run against a scratch `--dir` build it found two configurations that
could not have produced a shippable artifact, both invisible on a maintainer's machine.
**`docker/**` was not in electron-builder's `files:`** while `src/main/stack.ts#resolveComposeFile`
reads `docker/docker-compose.v3.yml` from `app.getAppPath()` at every stack start, so every packaged
build would have died on first launch with `compose-invalid`. And **`desktop/build/` was never
committed** — `.gitignore`'s global `build/` rule swallowed the four icon and entitlement files
`electron-builder.yml` names by path, so a release job packaging a fresh checkout would have failed
on the first artifact. Two config entries were removed rather than fixed: `mac.identity: null` was a
hard "never sign" the workflow cannot lift, and the `.runtime-staging` `extraResources` entry made
the config unbuildable without a multi-GB python-build-standalone tree the shipping app does not use.

**Cost.** The target list is now exactly what CI builds and verifies, nothing more; adding a target
means adding its verification.

**Revisit if.** The native runtime is unparked — `--expect-runtime` is the check that would then have
to pass, and it has never run against a real staged tree.

### 2026-09-06 — the run receipt is removed (tombstone on 2026-09-05's third rendering)

**Decision.** Reverses the receipt half of *One selection grammar, with the receipt as the
confirmation* (2026-09-05). `pages/_shared/run/Receipt` and `PageLayout`'s `receipt` slot are gone.
A run page states its batch twice and no more — the plan grid in the run pane, and the action bar's
digest — both rendered from one `PlanModel`. The selection-grammar half of that decision stands
unchanged. The Pipeline page keeps its own `Receipt`, which states a canvas plan, not a batch.

**Why.** The maintainer: "we have enough info overlapping on the right planning window". Three
renderings of the same `PlanModel` in one viewport is redundancy, not confirmation, and the slot
cost every run page vertical room above Run.

**Cost.** The existing-outputs count is no longer visible before the dialog asks; `planCounts()`
survives to supply it there.

**Revisit if.** A run page's batch ever becomes something the plan grid cannot show in full.

### 2026-09-07 — SCI-07 restated on `main`'s positional carrier model (amends 2026-09-06)

**Decision.** Amends the SCI-07 row of the ADR index. The physics is unchanged — coherent within a
carrier, incoherent (power for `hf_sar`, worst-case sign for `hf_peak`) across carriers, the ½
applied once in the SAR calibration — but it is now **driven by the montage's positional structure
rather than a `channels=` argument**. `main` removed the Lee-2022 shared-carrier wiring outright
(`7a5ee2dd` "Remove Lee-2022 carrier wiring: mTI is always positional (channels->carriers)",
`d4706e5a` "drop legacy channels parameter from tit.calc public API", `b19a1c26` "consolidate
tit.calc to three envelope functions"), so `Montage` has no `channels` field, `MExConfig` has none,
and `electrode_pairs` taken two at a time *are* the carriers. Accordingly `tit.fields.hf_peak`,
`hf_sar` and `hf_peak_is_exact` take fields positionally; `channel_index_groups`, `_carrier_stack`
and `tit.calc._resolve_channels` are deleted.

**Why.** With one wiring, a grouping parameter can only ever be the identity — dead surface that
invites a caller to express a montage the toolbox cannot simulate, and a second place for the
carrier definition to drift from `tit.calc`'s. The correction that mattered was *stating the metric
over carriers instead of over raw FEM fields*; that statement survives the API change intact, and
under positional wiring it is what the code now computes. No released version ever had `channels`
(added in `ff823ce1`, removed in `7a5ee2dd`, both inside the v2.5.0 pre-release window), so no
user-visible number moves.

**Cost.** A shared-carrier montage is currently inexpressible. Reintroducing one means a `Montage`
field, a coherent pre-sum in `tit.fields`, and the same grouping consumed by `tit.calc` — the table
in `SCIENTIFIC-CORRECTIONS.md` § SCI-07 and
`test_shared_frequency_would_need_a_coherent_presum_and_never_occurs` are the specification.

**Revisit if.** A montage architecture returns in which several electrode pairs are driven
phase-locked from one source.

### 2026-09-07 (CX9) — SCI-09: a pooled variance is a sum of squares, not a sum of variances

**Decision.** `engine.ttest_ind` builds the pooled variance from each group's **sum of squared
deviations** about its own mean, `Σ(x − x̄)²`, divided by `n₁ + n₂ − 2`. It no longer reconstructs
that sum as `(n − 1) · np.var(x, ddof=1)`. Recorded as
[SCI-09](SCIENTIFIC-CORRECTIONS.md#sci-09); fix `1b5ffdd7`, tests
`tests/numerical/test_sci09_singleton_group.py` (real scipy) and
`tests/test_stats_engine.py::TestTtestInd::test_singleton_group_*`.

**Why.** The two forms are equal for `n ≥ 2`, and differ for exactly one input the toolbox accepts:
a group of **one**. There `np.var(x, ddof=1)` is a `0/0` `nan`, and `(n − 1) · nan` is `0 * nan ==
nan`, not the `0` the pooled estimator calls for — so the pooled variance, the standard error and
the t of every voxel of a one-vs-many comparison came out `nan`. `df = n₁ + n₂ − 2 = 1` is
under-powered, but it is not undefined, and the engine had no business reporting it as data with no
variance in it. Summing the deviations gives the singleton its true contribution, which is exactly
zero, and needs no special case.

**What it cost users.** On 2.2.3 – 2.5.0 the `nan` was swallowed by the zero-standard-error guard
`valid = se_diff > 0` (`nan > 0` is `False`), leaving `t = 0, p = 1` at every voxel: a complete,
well-formed, uniformly null result set. That is the worst shape a defect can take — the run
succeeded and reported "no effect anywhere" as a finding. The loud shape appeared only on this
branch, between `682cbfcf` ([SCI-06](SCIENTIFIC-CORRECTIONS.md#sci-06), which made `_safe_t`
IEEE-correct) and the fix: the `nan` reached `ttest_voxelwise`, emptied `valid_mask` and raised
`No voxel could be tested` after the log existed and before any map was written. Both are a
**re-run**; there is nothing to rescale, because the statistic was never computed.

**What the fix does not buy.** A 2-vs-1 design still cannot reach significance. Three subjects admit
`C(3,1) = 3` relabellings, so the permutation null has three members — one of them the observation —
and the floor on a cluster p-value is `1/3` exhaustively, `2/4` under the shipped sampled estimator.
**Zero significant clusters from three subjects is the arithmetic of the design, not a defect**, and
that is now said on the [Cluster-Based Permutation Testing]({{ site.baseurl }}/wiki/cluster-permutation-testing/)
page next to the data requirements, with `C(6,3) = 20` (three per group) named as the first size at
which `α = 0.05` is even reachable. What the fix buys is that the `t` and `p` maps are the real
ones, so the effect can be *read* where it cannot be *tested*.

**Revisit if.** A degenerate-input guard is added anywhere else in the engine that tests a derived
quantity for `> 0` — `nan > 0` is `False`, and a guard written for zero will quietly take the zero
branch on `nan`. `_safe_t` is the pattern to follow instead: let the IEEE value through and classify
it explicitly.

### 2026-09-08 — Internal distribution through the existing product pipeline

**Documentation presentation superseded 2026-09-09** by the current-product/branch-lifecycle
decision below. Artifact identity and explicit publication boundaries remain in force.

**Decision.** Architecture §10 separates internal artifacts from public announcements. Continue the
existing desktop implementation toward main, produce a matching image and loaders for local and
colleague testing, and permit the public site to describe upcoming functionality as unavailable to
the public. Reuse the existing workflow and documentation roster. Keep public release metadata and
Docker `latest` unchanged until a later production decision.

**Why.** The maintainer requested “an actual continuation of the things that we have”, “put the
Docker container in Docker Hub without actually cutting a release”, and documentation that clearly
says “what is coming and not yet available for the public”. A signed/public release is not a
prerequisite for a controlled internal trial, but a matching container is.

**Cost.** Development runtime versions and stable release announcement metadata have distinct owners.
Every shared internal tag needs an immutable artifact receipt. Unsigned installers need explicit
internal-test instructions, and full platform certification is still a production gate.

**Revisit if.** The maintainer authorizes production publication or changes the internal distribution
channel. Acceptance is command-based: same image from both loaders and desktop, package validation,
real-container execution, unchanged public release/update state, and a built site with preview notices.
Measured results belong in BENCHMARKS.md, not this decision.

### 2026-09-08 — Separate Blender rendering from scientific dependencies

**Decision.** Preserve SimNIBS 4.6's NumPy 2.3.5 environment. Use a pinned official Blender
background process for montage scene composition, passing prepared geometry and electrode
data across that boundary. Keep the existing job, configuration and artifact interfaces.
Vector, region and subcortical exports remain in the scientific environment.

**Why.** Rebuilding the image exposed that installing `bpy` downgraded NumPy to 1.26.4,
contradicting SimNIBS/SAMSEG requirements. A Blender 4.4 wheel with permissive metadata still
reported NumPy ABI initialization failures with NumPy 2.3.5. Successful imports or a tiny
render did not establish a supported shared environment. Geometry preparation therefore stays
with SimNIBS and rendering stays with Blender's supported runtime.

**Cost and verification.** The image carries a separate Blender runtime and a narrow prepared-data
boundary. Preserve the scalp geometry used for electrode placement, the public return values,
output names and job cancellation. Verify actual montage export and reopen the resulting scene,
and verify the scientific environment independently. Measurements belong in BENCHMARKS.md.

**Related build recovery.** The official FastSurfer checkpoint downloader failed on a TLS chain
and its alternate host timed out. A cache is allowed only with an explicit archive digest and
independent publisher checksum/size evidence for all three weights. Extract fixed filenames;
do not relax TLS verification. This is an optional path in the existing builder.

**Revisit if.** An upstream supported Blender and SimNIBS combination removes the ABI conflict,
or the montage exporter gains additional scientific operations across this boundary.

**Internal image identity enforcement.** A running project container may be reused only when its
configured image reference matches the requested loader/desktop reference. A mismatch is an
actionable refusal, never permission to kill active jobs or silently attach to an older cohort.
Alternate aliases are not inferred to be equal. Registry existence-check and push operations are
serialized by their resolved image tag, including runs from different source refs.

### 2026-09-09 — Current-product documentation and release stabilization branches

**Decision.** Describe the Electron/Docker application directly, as the documentation that will
be merged into main. Remove preview/teaser and stable-version detours from active guides; retain
historical releases and scientific-correction records. Keep current artifact availability on the
installation page. Rename `develop` to `release/3.0.0` and use the general branch lifecycle in
CONTRIBUTING: protected production main, short-lived topic branches, bounded release branches,
and immutable version tags after promotion. No permanent develop branch is required.

**Why.** The maintainer asked to “treat it as what it will become” and to use production, feature,
fix and release branches before merging to main. One guide avoids divergent instructions for
colleagues and experienced Git users. The subsequent explicit answer was to wait until after
manual testing before publishing the Docker image.

**Cost.** Release-targeted PRs need the same validation as main. Hotfixes must reach active
release branches, and the availability note changes when an artifact is actually published.
Documentation can be merge-prepared while security and manual acceptance gates remain open.

**Verification.** Check release-branch identity and unchanged commit ancestry, workflow event
filters and actionlint, absence of teaser/stable detours in active guides, and both documentation
builds. Keep runtime/public version metadata and Docker Hub unchanged. Results belong in
BENCHMARKS; this decision itself does not declare publication or scientific acceptance.

**Revisit if.** Parallel supported release lines require a long-lived maintenance branch, or
release integration becomes frequent enough to justify another persistent integration branch.


### 2026-09-09 — Interactive setup for argument-free loaders

**Decision.** All four root/development Python/Bash entry points prompt for launch settings
when called without arguments: one project question, with the last path remembered, matching
the v2 interaction. Advanced settings remain flags; `--interactive` forces the project prompt.
The shared CLI owns input validation and cancellation before Docker dispatch. Interactive
launches with no explicit image reconnect to the project's running session and identify it;
explicit image requests retain the mismatch guard, and no running session is replaced.

**Why.** The maintainer ran the dev loader without flags and encountered the missing-project
error, then requested an interactive setup across all four entry points. The maintainer
rejected a multi-question setup and asked to preserve the simple v2 behavior.

**Cost.** Interactive setup requires terminal stdin. Scripts pass explicit flags; Bash
continues forwarding to Python instead of maintaining a separate prompt implementation.

**Revisit if.** A native folder chooser becomes a requirement for the terminal launchers.


### 2026-09-09 — Shared extension run layout and contextual export previews

**Decision.** Move computational extension inputs left and their plan/live terminal right,
using the existing run-page components. Add export-specific atlas, montage and volume
previews with selection callbacks to the same export fields.

**Why.** The maintainer requested the Pre-processing/Simulator layout for extensions and
a useful visual selection surface for cortical, subcortical and montage exports.

**Cost.** The idle terminal intentionally reserves space for output. Geometry tests now
measure plan/terminal bounds instead of treating that space as missing form content.
Subject previews may need scene preparation; missing data remains explicit.

**Revisit if.** An export mode gains a final-geometry preview API; do not imply one exists
by drawing a reference head or scalar field as its completed output.


### 2026-09-09 — Progressive and incremental Tetravox scene loading

**Decision.** Implement dataset concurrency, layer adoption as ready, and retained-dataset
reuse in Tetravox's engine rather than duplicating its loader in TI-Toolbox. Reuse matches
resolved URLs and sidecars within the current selection; explicit Reload clears the frame.
TI-Toolbox reconciles progress by source name, keeps read-byte counts distinct from indexing
work units, and displays partial failures without covering successful layers.

**Why.** The maintainer showed a six-volume scene with blank panes and stale queued entries,
requested incremental rendering, and requested that adding files not reload existing ones.

**Cost.** Concurrent decoding increases peak work and memory. Re-selecting an unchanged URL
reuses memory even if a file was overwritten; Reload is the explicit freshness boundary.

**Revisit if.** Measured memory pressure calls for a bounded load queue or server-provided
file revisions make automatic freshness detection reliable.

### 2026-09-09 — Left-aligned forms and per-job field mapping

**Decision.** Content-sized, left-aligned labels leave remaining width to controls. Participant
Add actions stay in the summary header while conditional selection tools occupy a separate row.
Source exposes EEG forward preparation; Simulator settings expose opt-in fsaverage projection
through the existing config flag. Python defaults and standalone mapping remain compatible.

**Why.** The maintainer requested readable left alignment, stable Add buttons as rows grow,
and mapping alongside the simulation job rather than a second Source workflow.

**Cost.** Control left edges vary with label length; UI mapping now starts off unless inherited
from the last configured job. **Revisit if** per-job projection needs spacing or field overrides.

### 2026-09-09 — Resolve automatic search folders before preview

**Decision.** The Optimizer resolves the subject root through the server, then plans and submits
one explicit folder. Automatic names use local date/time, milliseconds and row identity; a
successful submission refreshes them. Manual basenames resolve inside the subject results root.

**Why.** The maintainer requested that timestamp timing differences not become user warnings.
Pinning the destination also prevents two simultaneous UI rows from sharing an automatic folder.

**Cost.** Flex planning makes a second lightweight request. Raw API callers omitting the output
folder retain the existing warning because their destination has not been pinned.

### 2026-09-09 — Align form control starting edges

**Decision.** Keep labels left-aligned, but restore the shared `--field-label-w` column.
**Why.** The maintainer clarified that control starts should align rather than stagger after
individual labels. Long labels wrap inside the shared column; controls retain their existing
full-width or compact numeric sizing. This supersedes content-sized labels above.

### 2026-09-09 — Expose Optimizer settings directly

**Decision.** Put ratio controls on one row, remove Solver’s nested Advanced disclosure and
keep After the search open without a disclosure. **Why.** The maintainer requested fewer rows
and direct access to these settings. Parameter values and submitted configs are unchanged.

### 2026-09-09 — Verify the checkout before developer attach

**Decision.** Keep the existing Node dev loop and Python/Bash wrappers, verify actual checkout
mounts and Python import precedence, and use only the checkout renderer in mounted mode (§10).
**Why.** The developer container still mounted an obsolete worktree; an environment marker or
a baked UI could make local fixes appear ineffective. **Cost.** Python-only UI testing needs a
local renderer build; Vite avoids that rebuild during frontend editing. A container whose jobs
cannot be checked needs explicit intervention. **Revisit if.** Development moves to remote
Docker hosts, where host-path identity needs a different contract.

### 2026-09-09 — Project permission and per-run overwrite confirmation

**Decision.** Retain the existing project-scoped `allow_unsafe_overrides` setting, default
false, and gate existing-output replacement in shared dialogs and submission routes.
**Why.** Confirmation was offered without the setting, and the simulation job's recorded
overwrite flag was never delivered to SimNIBS. **Cost.** Scripts submitting destructive jobs
through the server must opt in for that project; a successful earlier confirmation cannot
suppress the next one. **Revisit if.** The server gains authenticated per-user roles.

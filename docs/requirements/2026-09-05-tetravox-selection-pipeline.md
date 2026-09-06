# Maintainer requirements — 2026-09-05 (second batch)

These are hard gates for the Tetravox-currency / electrode-dots / selection-grammar / pipeline pass.
They refine [ARCHITECTURE.md](../ARCHITECTURE.md) §§1–6 and add §7. They do **not** reverse the
[first 2026-09-05 batch](2026-09-05-overview-batch-viewer.md); they follow it. The plan of record is
`dev/notes/v3-tetravox-selection-pipeline-plan.md` (decisions A–D, lanes TX/AU/EL/SG/PC/CX2); the
per-lane evidence is in `dev/notes/v3-tetravox-selection-pipeline/`.

## Asks, verbatim

1. "We shipped a new TetraVox that fixed a few visualization bugs, so please make sure that we incorporate that into the TI toolbox."
2. "think deeply about how we should implement the TI toolbox in such a way that it automatically gets updated if Tetravox is releasing a new version"
3. "I don't want to use the native Tetravox for the EEG electrode visualization. Instead, I want to use dot-like visuals for the electrodes … Instead of creating circles around the electrodes please change their colors and make sure that the selection deselection works properly."
4. "you have to create tests to make sure that the selection and visualization of electrodes and channels works properly."
5. "I want to come up with a solution for all windows on how we should create the selection logic of elements. In the TI toolbox 2.5.0, we had a great logic for selecting multiple jobs … right now it's too convoluted for the users to choose and to understand the jobs that they're selecting."
6. "a canvas-like graphical programming where users create nodes of processing and (1) run it as a pipeline — one flow of complete processing … as a single job — and (2) create Jupyter notebooks out of it … shared, visualized, and modified programmatically."

## A — Tetravox currency and automatic updates

The coupling between the two projects is a **protocol range plus named features**, never a version
(A1). "Is there a newer one" is answered by the GitHub Releases API of `idossha/tetravox`, reading
`protocol` out of a published `tetravox-embed-<v>.manifest.json` asset so compatibility costs ~2 KB
rather than a 6 MB download (A2). Setting `tetravox.auto_update` defaults **on**: the server checks
at startup and every 24 h, installs only a compatible release, and reports rather than installs a
release past the range (A3). Rollback stays one click and the last two installs are kept (A4). The
image bake resolves the newest compatible release by the same rule (A5). The Tetravox side ships the
three release assets and the 3-D dot pass (A6, Tetravox PR #35).

* Gate test: a loopback fake GitHub API serving real tarballs, digests and manifests drives the whole
  policy — a protocol past the range is reported `unsupported` and never downloaded; a bad digest
  installs nothing and leaves no pin; a hand-installed dev bundle numbered *ahead* of every real
  release does not freeze the updater (provenance, not the active bundle, is the baseline); the
  startup check does not delay `/api/health`; `build.sh`'s resolver picks a release with assets and
  skips a prerelease. Proved on the host and inside the container.

## B — Electrodes are dots whose colour is their whole state

The montage scene pane draws a points layer of `shape: "dot"` and says everything with colour:
neutral grey idle, 35 % grey disabled, the channel's Okabe-Ito hue when placed. No ring, no outline,
no second glyph — `setPointTool` and `setPointSelection` are never sent, which are the messages that
draw one. Names are shown for placed electrodes only. A channel legend above the pane names the
pairs in the same hues the pair editor uses.

* Gate test: unit — the marker→point mapping (state, colour, radius) and that `setPointSelection` is
  never emitted; mock e2e — pick an idle dot and the form slot fills and exactly that dot repaints in
  the pair's colour, pick a selected one and it goes back to grey, two pairs are two hues; **real**
  e2e against the live embed — the screenshot's pixel at the projected electrode equals the state
  colour within a measured tolerance, and the radial profile of the changed pixels is one solid disc
  that reaches zero and stays zero (a ring is by construction a non-zero band after a zero one).

## C — One selection grammar for every window

Anything chosen out of a set — subjects, montages, ROI regions, electrodes, participants, jobs — is
one primitive: click selects one, ⇧-click ranges, ⌘/Ctrl-click toggles, ⌘A takes what the filter
shows, Esc clears it; a checkbox column is the visible form of the same toggle; an always-on filter,
`All · None` as the only bulk buttons, one `N of M selected` badge. Bulk buttons act on the visible
rows and a hidden row keeps its state. Every run page ends with a plain **receipt** — "this will run
N jobs", the first 15, "… and K more" — immediately above Run, and existing outputs are one shared
Skip / Replace / Cancel question. No drag-to-reorder; no per-item options.

* Gate test: the same control and testids on all four subject pages; ⇧-range and ⌘-toggle; filter ×
  All; the receipt's count equals the plan grid's row count and updates live; the receipt is above
  the action bar by bounding box; the Jobs multi-select cancel sends exactly the selected ids; the
  shared dialog's three answers.

## D — A pipeline is a DAG of existing jobs, run as one group, exportable as a notebook

Nodes are existing job kinds carrying exactly the config the matching page already builds; edges are
typed bindings between one node's named output and another's same-named input. Running one is
exactly one `submit_plan` — one `group_id`, one row-group in Jobs, cancellable as one thing. There
is no pipeline executor and no new job kind. Bindings that cannot be known up front are resolved by
a small `resolve` job planned between producer and consumer, whose result is merged into the
consumer's runner config at admission. Export is a pure function of the document into an `nbformat`
v4 notebook written against the public `tit` scripting API, carrying the document in
`metadata.ti_toolbox.pipeline`. Importing hand-edited notebooks is a non-goal.

* Gate test: a four-node `pre → flex → sim → analyzer` pipeline validates, runs as exactly one group
  whose `after` chain matches the edges, shows one Jobs row-group, and exports a notebook that
  `nbformat.validate`s and whose code cells execute against a stub `tit` in a subprocess; on the real
  container a two-node `sim → analyzer` on sub-ernie completes end to end and the analyzer's output
  lands inside the simulation the edge named.

## Decisions this pass settles

Recorded in [DECISIONS.md](../DECISIONS.md): the Tetravox release index and the protocol-range pin;
automatic updates on by default with one-click rollback; "newer" measured against release provenance;
app-level events on their own socket; dots and colour-as-state with an Okabe-Ito palette; one
selection grammar with a receipt and one existing-outputs dialog; React Flow and `nbformat` as
dependencies; a pipeline run is one job group; static-versus-`resolve` bindings; notebook export
public-API-only; Settings' ⌘-number derived rather than hard-coded.

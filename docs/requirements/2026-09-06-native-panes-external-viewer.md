# Maintainer requirements — 2026-09-06 (native panes, external viewer, jobs tables)

These are hard gates for the pass that took the 3-D viewer *out* of the run pages and put a jobs
table *into* them. They **reverse** parts of the two 2026-09-05 batches — the embed-in-panes half of
[2026-09-05 Tetravox/selection/pipeline](2026-09-05-tetravox-selection-pipeline.md) (A, B) and the
"Viewer loads into a retained iframe" rule of
[2026-09-05 overview/batch/viewer](2026-09-05-overview-batch-viewer.md) — and they replace
[ARCHITECTURE.md](../ARCHITECTURE.md) §7.1 and rewrite §7.2. The plan of record is
`dev/notes/v3-native-panes-external-viewer-plan.md` (decisions N1–N4, V1–V5, lanes NR/VX/JB/CX3);
the per-lane evidence is in `dev/notes/v3-native-panes-external-viewer/`.

## Asks, verbatim

1. "I still don't like our implementation for both the optimizer, simulator, and analyzer for the 3D viewer … we had a really neat implementation that worked very well and showed the electrodes in a better fashion and also the atlas ROIs were interactive."
2. "instead of trying to complexly implement the Tetravox into the TI toolbox … write our own little module based on the logic from Tetravox and embed it exactly how we need it into our tabs."
3. "for the viewer, instead of embedding the web version of Tetravox … the viewer tab only acts as the data selection and it actually opens up everything in [an external window] like we have in 2.5.0."
4. "for both the optimizer and the analyzer we need that interactive atlas … see atlases, see the selected labels and regions, and also select from their labels and regions."
5. "I want the complexity to be as simple as possible and the implementation to require minimal maintenance."
6. "The simulator UI looks very very good, but there is a problem where it's hard to separate users, montages, modes in different jobs. In 2.5.0, within a job users could manipulate the subject, the mode, the montage, the current intensities, and so on. We need that capability. This is also true for the Analyzer — we need a list of jobs in a table that allows users flexibility in what they input to the job."

## N — The run-page panes are our own renderer (asks 1, 2, 4)

The Simulator, Optimizer and Analyzer 3-D panes are drawn by `desktop/src/renderer/scene/`, a WebGL2
renderer with no runtime dependency, restored from the 2026-09-04 build (N1). It consumes the
packaged guide over `GET /api/guide/*` in `TVSC1`, including the per-vertex `uint16` label payloads
the guide packages again for it. Electrodes are screen-space dots whose colour is their whole state
— idle grey, the channel's Okabe-Ito hue when placed, **no ring** (N2). The atlas is interactive:
the pane carries its own atlas selector, hover names the region under the cursor, a click adds or
removes it, and the pane and `RoiPicker` edit **one** selection with one key function, in both
directions (N3). Nothing under `pages/` imports the Tetravox embed (N4).

* Gate test: unit — the restored renderer's nine suites (camera, framing, normals, orientation,
  pick, selection, tvsc, unproject, pane-model); mock e2e — an atlas click selects the region the
  ROI picker then lists, a region chosen in the picker is highlighted by the pane, an aimed
  electrode click fills the montage slot, zero `iframe` elements on a run page, and three subject
  switches cost zero guide requests and keep the same canvas element; **real** e2e against the live
  server — drawing-buffer pixels: the idle grey, the channel hue, a radial profile with no ring, the
  ROI tint, warm first paint and orbit fps.

## V — The viewer is a separate application (asks 3, 5)

TI-Toolbox ships no viewer. The Viewer page is a **data selector** whose action is **Open in
Tetravox** (V1). Open writes the ViewSpec v2 document to
`<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`, with every dataset path rewritten from an
`/api/files/raw/…` URL to the *host's* own absolute path, and Electron main hands that file to the
host-installed Tetravox desktop app, detached; a second Open is a second spawn that Tetravox's
single-instance lock routes into the window already open (V2). Discovery is the platform's
conventional locations plus one Settings override, with a download link when the app is absent; with
no Electron shell, the button downloads the scene file instead (V3). The embed, its protocol range,
its release index, its install store, its update channel, its WebSocket event, `/tetravox/` and
`Capabilities.tetravox_embed` are all removed, and the image bakes no viewer (V4).

* Gate test: mock e2e — one Open writes one scene file and calls the launch bridge exactly once with
  that file (the real IPC channel, only the spawn stubbed), no `iframe` on any page the nav rail
  offers, Settings shows the resolved app or the download link; **real** — Open on `sub-ernie`
  produces a schema-valid ViewSpec at the host path whose every dataset resolves on the host, and,
  where Tetravox is installed, the spawn *argv* is asserted without launching anything.

## J — A run page that submits many jobs describes them as a table (ask 6)

One row is one job, and the row owns every input that differs between jobs: the Simulator's row is
`Subject · Source · EEG net · Montage · Pairs · Currents`, the Analyzer's is
`Subject · Simulation · Space · Field`. A page with a jobs table has no page-level subject control;
the subject grammar's "listed with its reason, unselectable" rule (C, 2026-09-05) applies inside the
cell. The subject-set × montage-list cross-product is no longer the only thing the page can express
— it survives as an explicit button ("Add job for each ready subject", "Quick add"). A group is a
switch over the same rows, and rows that disagree about what a cohort can only do once are refused
with the reason on the button. The table survives the run.

* Gate test: mock e2e — a two-row table submits two jobs with two different subjects and two
  different montages; a half-filled row is shown and is not planned; a source switch changes what is
  inside the cells and moves no column; the group switch refuses mismatched rows with a stated
  reason; **real** — the wire shape of a TI and an mTI job (2 pairs/2 currents, 4 pairs/4 currents)
  and a flex result resolving to real electrodes on `sub-ernie`.

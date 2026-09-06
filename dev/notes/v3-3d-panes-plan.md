# 3D panes — Tetravox Embed protocol extension (spec, 2026-09-03)

> **SUPERSEDED for the run pages (2026-09-04).** The maintainer asked for "a slim scene management that loads
> exactly what we need", so Simulator/Optimizer/Analyzer get their own small scene service and renderer:
> `dev/notes/v3-scene-ia-plan.md`. What stays live below is the ask for the **Viewer** (points layer, pick, camera),
> which is still the right way to get interaction in the general result viewer.

Maintainer's ask, verbatim: *"for the simulator — use logic from tetravox to render a single 3d pane that has the
skin + GM with some transparency and show users the EEG net they have selected + allow them to select/deselect
electrodes + rotate the model in space. for the optimizer — the same for mesh or nifti and have users select ROIs
to target."*

Rule that shapes this: TI-Toolbox contains no Tetravox code; the viewer is the released **Tetravox Embed** served at
`/tetravox/` and driven over postMessage (`desktop/src/renderer/viewer/protocol.ts`, upstream `docs/EMBED.md` in
`/Users/idohaber/00_development/tetravox-wt-embed`, branch `feat/embed`, 0.3.4, protocol 1). The protocol is
additive-only, so everything below is new optional messages and one new layer kind — a v1 host keeps working.

## What v1 already gives us (host-side only, no upstream change)

- `setLayout {kind:'3d'}` — a single 3D view; orbit/zoom/pan are the embed's own.
- A `MeshLayer` over the subject's `m2m_<id>/<id>.msh` with `tagStyle` (per SimNIBS tissue tag: visible, colour,
  opacity → skin 1005 at ~0.25, GM 1002 opaque, everything else hidden), `opacity`, `solidColor`, `faceMode`,
  `flatShading`, `edges`.
- `probe {world}` → value under a world point; `cursor` events.
- `screenshot` for a montage thumbnail in the Results preview and the run report.

So a **"transparent head" pane is buildable now**: Simulator and Optimizer mount a second embed iframe (the Viewer
page's store already handles one; make it a per-page instance), load the head mesh with the tag style above, `3d`
layout, theme-synced. What is missing is everything the user interacts *with*.

## What the embed lacks — the upstream ask (protocol 2, embed 0.4.0)

| Message / feature | Direction | Payload | Used for |
|---|---|---|---|
| `DatasetRef.kind = 'points'` + `PointsLayer` | in `load` / `updateLayer` | `points: [{ id, label, world:[x,y,z], color?, radius?, state?: 'idle'\|'selected'\|'disabled' }]`, `labelMode: 'none'\|'hover'\|'always'`, `radiusMm` default | the EEG net's electrodes (from `m2m/eeg_positions/<net>.csv`, already served by the catalog), selected pairs highlighted |
| `setPointState` | host → embed | `layerId`, `ids: string[]`, `state` | (de)select electrodes from the form as well as from the click |
| `pick` | embed → host | `layerId`, `kind: 'point'\|'mesh'\|'volume'`, `id?` (point id), `world`, `tag?` (mesh tissue tag), `label?` (label-volume value), `modifiers: { shift, meta }` | click-to-select an electrode; click-to-target a region |
| `hover` (optional, throttled) | embed → host | same as `pick` without modifiers | hover highlight + tooltip in the host |
| `setLayerPickable` | host → embed | `layerId`, `pickable` | only the points layer answers clicks in the montage pane |
| `setCamera` / `camera` | both | `{ azimuth, elevation, distance, target }` | "front / left / top" presets in the host, restore the view between runs |
| `MeshLayer.tagStyle` documented in EMBED.md §4.4 with the SimNIBS tag table | docs | — | so the host does not guess |

Acceptance for the embed side (numbers): a points layer of 256 electrodes renders at ≥ 30 fps in the 3D view on
this Mac's WebGL2; a `pick` arrives within 50 ms of the click with the right id (tested by the embed's own suite by
posting synthetic pointer events); the tarball's `protocol.schema.json` validates the new messages;
`manifest.json.protocol` becomes 2.

## Host side, after 0.4.0 lands (TI-Toolbox lanes)

1. `viewer/embedInstance.ts`: the Viewer store's iframe/handshake logic becomes a reusable per-page instance
   (Viewer, Simulator, Optimizer each own one; teardown on unmount via `reset`).
2. `pages/simulator/MontagePane.tsx`: head mesh + points layer for the selected net; clicking an electrode
   toggles it into the next open slot of the current pair (the form's `electrode_pairs` is the single source);
   the pane and the pairs editor stay in sync both ways; presets front/left/right/top; a "screenshot" that lands
   in the plan as the montage thumbnail.
3. `pages/optimizer/TargetPane.tsx`: for atlas ROIs a label volume (`labelMode`, `visibleLabels`) or the
   annotated surface, click → `pick.label` → the ROI picker's region list; for spherical ROIs click → centre
   coordinate, radius from the form; the non-ROI is drawn in a second colour.
4. Gates: offscreen e2e per pane asserting the store state after synthetic `pick` messages posted into the page
   (no pixels), `paneWidths`, and the plan grid reflecting the selection.

## Who does the embed work

The Tetravox side is a change in the tetravox repo (branch `feat/embed`, unpushed). Another Claude session
(`tetravox-d6`) is active in that repo right now, so the orchestrator did not start a lane there. Options for the
maintainer: hand this file to that session, or ask the orchestrator to run an Opus lane in a fresh tetravox
worktree off `feat/embed`.

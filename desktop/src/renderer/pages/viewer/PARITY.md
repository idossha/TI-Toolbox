# Viewer — parity checklist

Source: `tit/gui/nifti_viewer_tab.py` (`NiftiViewerTab`), a **Freeview launcher**: it scanned the
subject's directories, built a `freeview` argv and `subprocess.Popen`'d it.

**v3 does not launch anything.** X11 is out of the runtime, `POST /api/viewers/{freeview,gmsh}` is
out of the server, and the launch buttons, the argv preview, the `viewer` job and the X-server
capability callout are out of this page (D3, `docs/dev/DECISIONS.md § 2026-09-03 (Docker streamline)`; W3a's server
notes for the routes that went with them). What replaced it: `GET /api/view/{kind}` returns a
Tetravox **ViewSpec v2** document, which `POST /api/view/open` writes to disk for the host-installed
Tetravox desktop app to open (V1/V2, `docs/dev/DECISIONS.md § 2026-09-06 (native panes, external viewer)`). The rest
of this checklist still speaks of the retired embed and wants a pass from whoever owns the parity
question — see `docs/dev/DECISIONS.md § 2026-09-06 (native panes, external viewer)` §8.3.
So the Qt tab's *outputs* are all still reachable — the difference is that they are rendered in the
window instead of shelled out to another process.

## U5 (program v3, `docs/dev/DECISIONS.md § 2026-09-03 (UI program)`): the inspector is gone

v2 drew a Layers / Cursor / Scene inspector beside the embed — a second, host-drawn copy of
controls the embed already draws in its own panels. DESIGN.md §10's ownership rule (image chrome is
the embed's toolbar's job, not a second copy) resolves that duplication by deleting the host's copy
outright, not by picking a side per-control. So every row below that used to read "Per-layer …,
posted as …" is now **entirely the embed's** — there is no host affordance for it at all, optimistic
or otherwise, and no gap to report: it was never this page's job to begin with once the ownership
rule is stated plainly. What stayed on this side of the boundary is what only the HOST can supply
(picking a subject/simulation/field/space and asking the server for a scene) or what only the host
can *observe* (the embed's own `cursor`/`ready.caps` events, now one line in the status bar instead
of a form).

## Controls

| Qt control | Default | v3 equivalent | Status |
|---|---|---|---|
| Visualization Mode: Single Subject / Group | Single Subject | `kind`, derived: `simulation` when the source bar names one, `subject` otherwise; `analysis`/`group`/`custom` reachable by deep link (`?kind=`) | Done — implicit rather than a radio; the source bar is 40 px and a mode picker in it would cost a select for something the other selects already say |
| Subject combo | first subject | Source bar **Subject** select, bound to the shell's subject switcher (one subject picker in the app, and this select *is* it while the page is on) | Done |
| Space combo (Subject/MNI) | Subject | Source bar ⟨Subject │ MNI⟩ segmented control — it chooses which files the **server** puts in the scene, so it is a source control, not a read-out; the status bar's `space` cell names the resulting space | Done |
| Simulation combo | first simulation | Source bar **Simulation** select | Done |
| Colormap combo (grayscale/heat/jet/…) | heat | **The embed's own panel** — U5 deleted the host's read-only mirror along with the rest of the inspector | Moved, not a gap |
| Opacity slider + label | 0.70 | **The embed's own panel** | Moved, not a gap |
| Visible checkbox | checked | **The embed's own panel** | Moved, not a gap |
| Percentile Mode + min/max spinboxes | checked, 95 / 99.9 | Resolved **server-side** into the scene's concrete `scale`/`threshold` (`tit/viewspec.py`); no client control | Simplified — gap 1 |
| Atlas / analysis overlay combos | disabled until scanned | Server-built layers for `kind=analysis`; no client-side layer adder | Simplified — gap 2 |
| "Show / Create Electrode Overlay" | unchecked | **Not on this page any more** — gap 3 |
| Load Subject Data / Refresh buttons | — | Implicit: the scene refetches whenever subject/simulation/field/space changes; the source bar's reload `IconButton` remounts the frame itself | Done |
| Console (file list, sizes, status) | — | Per-dataset load rows over the canvas with the byte count the loader reports (the embed's own toolbar; the host's is gone with the rest of the inspector) | Done |
| Freeview launch (`subprocess.Popen`) | — | **Deleted** (D3) | n/a |
| Gmsh launch | — | **Deleted** (D3) | n/a |
| Capability gating (X11) | n/a | No X11 anywhere. `GET /api/capabilities`'s `tetravox_embed` says which embed bundle this server has and which protocol it speaks; a host asks for a named feature, never a version. There is nothing for a person to install (VE) | Done |

## Known gaps (report to orchestrator)

1. **No client-side percentile control.** `GET /api/view/{kind}` has no query parameter for a
   client-chosen percentile pair, so the window is whatever the server resolved. Unchanged from v1
   (it was gap 3 there); the difference is that the numbers now reach a renderer instead of an argv.
2. **No client-side "add a layer".** The v1 page had an "Additional NIfTI" `PathInput`. It is gone
   with the layer-editing form: the scene is the server's document, and adding a layer client-side
   would mean this page inventing a `ViewSpec` layer object — the exact Tetravox-vocabulary
   knowledge the service boundary keeps out of this repo. The right shape is a `path` parameter on
   `GET /api/view/custom` (which exists) plus a way to merge two views, which does not.
3. **Electrode-overlay creation lost its home.** The v1 page submitted
   `POST /api/jobs {kind:"tools", config:{module:"tit.tools.electrode_overlay", …}}` and showed a
   status chip from `GET /api/catalog/electrode-overlays`. It is a *preprocessing* action, not a
   viewing one, and it does not belong in a 40 px source bar — it should move to Simulate or
   Prepare. Nothing else calls those two endpoints today, so the capability is currently
   unreachable from the UI. **Flagged for the lane that owns Simulate/Prepare.**
4. **`store.probe(world)` has no caller.** It is implemented and unit-tested (the protocol's
   `probe`/`probe` round-trip), but with the inspector gone there is no "Values at cursor" block
   left to put its answer in, and a 40 px source bar has no room for one either. Left in the store
   as an inert, tested capability rather than deleted — `viewer-real.spec.ts`'s screenshot assertion
   used to lean on the same request machinery this uses, so the plumbing is worth keeping even with
   nothing on screen calling it yet.

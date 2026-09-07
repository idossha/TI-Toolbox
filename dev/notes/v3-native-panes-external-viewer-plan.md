# Native run-page panes and an external Tetravox viewer (plan of record, 2026-09-06)

Status: **implemented and gated (2026-09-06)**. Lanes NR/VX/JB done, seams closed and records landed
by CX3 — evidence `dev/notes/v3-program-history.md § 2026-09-06 (native panes, external viewer){NR,VX,JB,CX3}.md`, requirements
`docs/requirements/2026-09-06-native-panes-external-viewer.md`, contract `docs/ARCHITECTURE.md`
§§7.1/7.2/7.5, ADR row 27.

One correction to the text below: V2's working name `<name>.tvx.json` is **wrong**. The app's scene
extension is the compound `.tetravox.json` and nothing else; any other suffix is read as a volume,
silently. See VX.md §1.
Supersedes the embed-in-panes half of `v3-embed-convergence-plan.md` (E6) and the Viewer-in-iframe half of
ADR rows 15/23; the Tetravox update channel (ARCHITECTURE §7.1) is retired with them.

## Maintainer asks, verbatim

> "I still don't like our implementation for both the optimizer, simulator, and analyzer for the 3D viewer … we had a
> really neat implementation that worked very well and showed the electrodes in a better fashion and also the atlas
> ROIs were interactive."
> "instead of trying to complexly implement the Tetravox into the TI toolbox … write our own little module based on
> the logic from Tetravox and embed it exactly how we need it into our tabs."
> "for the viewer, instead of embedding the web version of Tetravox … the viewer tab only acts as the data selection
> and it actually opens up everything in [an external window] like we have in 2.5.0."
> "for both the optimizer and the analyzer we need that interactive atlas … see atlases, see the selected labels and
> regions, and also select from their labels and regions."
> "I want the complexity to be as simple as possible and the implementation to require minimal maintenance."

## 0. What is true now

- The 2026-09-04 native renderer is intact at `~/.treehouse/ti-v3-firstmate/uiux/desktop/src/renderer/scene/`
  (camera, glScene, pickId, selection, normals, palette, tvsc, types, SceneCanvas, scene.css; 5 048 lines) with its
  unit suites `tests/unit/scene-{camera,framing,normals,orientation,pane-model,pick,selection,tvsc,unproject}.test.ts`
  and e2e `scene.spec.ts`, `scene-tabs.spec.ts`, plus that era's `pages/_shared/scene/{api,model,queries,ScenePane}`.
  It read TVSC1 surfaces with per-vertex uint16 labels from `/api/scene/*`, drew electrodes as screen-space markers,
  picked regions and electrodes via an id pass, and fed picks into the forms.
- Today's panes drive the Tetravox embed (`pages/_shared/scene/embedScene.ts`, `viewer/**`) over the packaged Ernie
  guide (`/api/guide/*`, TVSC1 for surfaces, GIfTI-only for labels). The Viewer page hosts the embed in an iframe;
  Results preview uses it too. `tit/tetravox/` + `/api/tetravox/*` + Settings card implement the runtime update channel.
- The Tetravox desktop app (github.com/idossha/tetravox, 0.3.11) is signed/notarised, auto-updates via
  electron-updater, opens files and scene documents from the CLI (`Tetravox a.nii mesh.msh`, `Open Scene…`), and its
  scene format is the ViewSpec v2 `tit/viewspec.py::build_view` already emits.
- The container has no display; a GUI Tetravox inside Docker would need X11, which v3 removed — so "install Tetravox
  like a Linux package" is realised as the **host-installed desktop app**, which is also the one with an updater.

## 1. Decisions

**N — Native panes (Simulator, Optimizer, Analyzer)**
- N1 Restore the 2026-09-04 renderer verbatim into `desktop/src/renderer/scene/` (own code, zero deps, WebGL2) and
  make it the only renderer on the run pages. The pane consumes the packaged guide: `GET /api/guide/surface?…&format=tvsc`
  (skin, gm) and TVSC1 label payloads per atlas — regenerate the guide assets so TVSC1 carries per-vertex labels
  again (`tit/scene/guide_build.py`; keep the GIfTI copies until VX no longer needs them, then drop).
- N2 Electrodes = screen-space dots coloured by state (idle grey / selected = channel hue, Okabe-Ito), no rings;
  click toggles into the next free slot of the active pair; the active row's net+montage is what the pane draws
  ("Showing:" chip stays).
- N3 Interactive atlas: atlas selector (packaged DK40 / HCP-MMP1 / a2009s + subcortical volume legend where the old
  pane had it), hover names the region, click selects/deselects it, selected regions tinted with the ROI colour and
  listed in the legend; the same selection model as `RoiPicker` (one source of truth, both directions). Optimizer:
  regions = target/avoid ROI; Analyzer: regions = analysis ROI. Sphere targets keep typed coordinates only.
- N4 Zero Tetravox imports under `pages/` after this; `pages/_shared/scene/embedScene.ts` deleted.

**V — External viewer**
- V1 The Viewer page is a data selector (keep today's draft → Load grammar, rename Load → **Open in Tetravox**) and
  a small "what will open" summary. Results preview gets the same button; no iframe anywhere.
- V2 Open = the server writes the ViewSpec to `code/ti-toolbox/viewer/<name>.tvx.json` in the project (host path via
  `host_path`), Electron main spawns the Tetravox app with that file (`Tetravox <scene>`; macOS `open -a Tetravox
  <scene>`; Windows/Linux the resolved binary), detached; a second Open re-uses the running app via a second spawn
  (the app's single-instance/open-file handling — verify in the Tetravox repo and record it).
- V3 Discovery: `/Applications/Tetravox.app`, `~/Applications`, Linux `tetravox` on PATH or a configured AppImage,
  Windows `%LOCALAPPDATA%\Programs\Tetravox\Tetravox.exe`; Settings ▸ Viewer shows the resolved path/version, a
  path override, and a **Download Tetravox** link to the GitHub release page when absent. Browser mode (no Electron):
  the button downloads the scene file instead and says to open it in Tetravox.
- V4 Retire the embed: delete `desktop/src/renderer/viewer/**`, `pages/_shared/scene/embedScene.ts`, `tit/tetravox/`,
  `tit/server/routes/tetravox.py`, `/tetravox/` static route + CSP, `/ws/tetravox`, the Settings Tetravox card, the
  Dockerfile/`build.sh` embed bake, `contracts` tetravox section, their tests and mock routes. `tit/viewspec.py` and
  `/api/view/*` stay (they produce the scene file). Tetravox PR #35 remains useful upstream but nothing here depends
  on it.
- V5 Records: ARCHITECTURE §7.1 replaced by "external viewer" contract; DECISIONS entries reversing the embed decisions
  with the maintainer's reasoning; ADR row; DESIGN §10 rewritten; ROADMAP: the embed protocol work is parked.

## 2. Lanes (Opus, concurrent, disjoint)

| Lane | Owns |
|---|---|
| **NR** | `desktop/src/renderer/scene/**` (restored), `pages/_shared/scene/**` (rewritten on the native renderer), `pages/_shared/roi/RoiPicker.tsx` (selection model shared with the pane), the three pages' pane wiring, `tit/scene/guide_build.py` + regenerated `tit/scene/guide/**` (TVSC1 labels), `tit/server/routes/guide.py` (+`format=tvsc` labels), tests (`scene-*.test.ts`, `scene*.spec.ts`, `guide.spec.ts`, real `embed-electrodes.spec.ts` → `scene-electrodes.spec.ts` with drawing-buffer pixel assertions) |
| **VX** | `pages/viewer/**`, `pages/results/**` preview, `desktop/src/main/**` (launch + discovery + preload bridge entry ≤ budget), `pages/settings/**` (Viewer card replaces Tetravox card), `tit/server/routes/{viewers,view*,static}.py`, `tit/server/app.py` CSP, deletions in V4, contracts, container recipe, tests |
| **CX3** | seams, records, full gate + real subset, after both |

## 3. Gates
- NR: unit suites restored and green; mock e2e: atlas hover/click selects a region that appears in RoiPicker and vice
  versa; electrode click fills the montage slot; real e2e: drawing-buffer pixel at a selected electrode = channel colour,
  a selected region's pixel = ROI tint, no pixels of the old ring; first paint ≤ 300 ms warm; 60 fps orbit at 1280.
- VX: mock e2e: Open writes one scene file and calls the launch bridge once with it (spy); no iframe in the DOM
  anywhere; Settings shows the resolved app or the download link; real: Open on sub-ernie produces a valid ViewSpec
  file on the host path and (if Tetravox is installed on this Mac — check `/Applications`) the app opens it
  offscreen-safe (do not steal focus in CI: only assert the spawn args unless the maintainer runs it).
- CX3: typecheck, lint, vitest, `e2e:quiet`, pytest, route guard, contracts, build, real subset; DESIGN/ARCHITECTURE
  /DECISIONS/ROADMAP/ADR landed; zero occurrences of `postMessage`/`tetravox-host`/`embedProtocol` under `desktop/src`.

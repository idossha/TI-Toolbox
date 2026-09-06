# v3 desktop — Tetravox embed + UX/IA redesign (plan of record, 2026-09-02)

Supersedes the *screen layout* parts of `dev/notes/v3-build-plan.md` and `desktop/DESIGN.md` §2–§5;
the job model, contract gate, ownership discipline and quality floor of those documents stay.
ADR rows 15–17 in `tracks/active/v3-electron-gui.md` record the decisions.

Baseline for review: `git diff refs/baselines/v3-20260902` (a dangling commit of the whole
uncommitted worktree taken before this program started; nothing on the branch was changed).

## 0. Decisions

| # | Decision | Chosen |
|---|---|---|
| D1 | Internal viewer | **Tetravox as a service** (revised 2026-09-02 after maintainer feedback: "instead of copying the entire codebase of tetravox … wrap around it … it should be considered a microservice"). Tetravox stays its own product, repo and release; TI-Toolbox integrates through a versioned contract only: (1) **Tetravox Embed** — a browser build of the Tetravox viewer released by the tetravox repo as a static bundle (`tetravox-embed-<ver>.tgz`), installed into the TI image at build time (dev: `TIT_TETRAVOX_EMBED_DIR` pointing at a local build), served by `tit.server` under `/tetravox/` with its own CSP, mounted by the renderer in an `<iframe>` and driven over `postMessage` (protocol v1, §4.5); (2) **Tetravox desktop app** launched with a scene file as the external/no-WebGL2 path (Freeview/Gmsh stay as the last fallback). No Tetravox source or engine code lives in this repo; TI owns only the iframe host, the protocol types and the scene builder. |
| D2 | Data path | Same-origin HTTP. New `GET/HEAD /api/files/raw/{path:path}` on `tit.server` (jailed, streamed, Range via Starlette `FileResponse`, no gzip encoding). The engine's `fileUrl()` passes absolute `http(s)://` URLs straight to the worker (`packages/engine/src/datasets/source.ts:56-59`); the URL must END with the file name so gzip/volume sniffing works. No custom Electron scheme, no container→host path mapping in the renderer. |
| D3 | Dependency | **Released artifact, not source** (revised 2026-09-02). The first cut vendored `@tetravox/{protocol,wasm,engine}` source under `desktop/vendor` (Stage 0, lane F1) — measured to work, but rejected by the maintainer as growing the monolith; it is removed. TI pins a Tetravox Embed *release version* (manifest `{name, version, protocol}`); upgrading = replacing a directory in the image. The scene contract is Tetravox's own ViewSpec v2 with URL dataset refs (TI-specific `TitScene` retired). |
| D4 | Freeview/Gmsh/X11 | Kept, demoted to an **"Open externally ▾"** menu and to the designed **no-WebGL2 fallback state** (Chromium ≥137 has no SwiftShader fallback). `x11_display/freeview/gmsh` capabilities stay. Removal is a later decision on a timer, not a side effect of this work. |
| D5 | Information architecture | Workflow-first: one **subject switcher** in a context bar scopes every subject page; nav = Project · Prepare · Simulate · Optimize · Analyze · Results · Viewer · Jobs (+ Settings/Help pinned). **Panels nav group deleted**; every panel re-homed (§2). Optimizer flex/ex/mex merged into **Optimize** with a Method segment. Analyzer + the three group-stats panels merged into **Analyze** with a Scope segment. |
| D6 | Density | One shipped density (no user toggle): base type 13/18, controls 28 px, table rows 28 px, 12 px floor for anything read, flush form sections (no card-in-card), label-left field rows (`--field-label-w: 160px`) with named full-bleed exceptions, no page headers, sticky 44 px action bar, Plan as the inspector's top block. Acceptance numbers in §3. |
| D7 | Not adopted | Dark default theme; minimum window > 1024×680; persistent always-mounted canvas; one-at-a-time step accordions; "defaults are invisible" field placement; deleting the Jobs route; icon-only rail at all widths; a density switch; System page moved into Settings. |
| D8 | Viewer as input (later milestone) | "⊕ Pick in viewer" for ROI spheres (`Engine.setPointTool`), atlas region checkboxes bound to `RoiRegion[]` (ids already equal label indices), electrode assignment by clicking the net on the scalp. Always an *additional* affordance beside the numeric row. Scheduled after the Viewer page ships (Stage 4). |

## 1. Shell (light and dark; 1024×680 minimum; breakpoints 1280 → icon rail, 1100 → inspector becomes a drawer)

```
┌──────────┬────────────────────────────────────────────────────────────────────┐
│ Nav rail │ Context bar 40: [Dataset 000 ▾] › [ernie ▾ raw fs m2m] [+2 more ▾] │
│ 216 px   │                       ⌘K search · ● connected · 3 running          │
│ (56 px   ├───────────────────────────────────────────┬────────────────────────┤
│  icons   │ Work pane (flush sections, 2-col grid     │ Inspector 300 px       │
│  <1280)  │ ≥ 560 px, max 880 px)                     │ (resizable):           │
│          │                                           │  Plan block (top)      │
│ Project  │                                           │  page-specific blocks  │
│ ───────  │                                           │                        │
│ Prepare  ├───────────────────────────────────────────┴────────────────────────┤
│ Simulate │ Action bar 44: "2 jobs · 8 CPU · 16 GB · 1 overwrite" ⚠2 [Run ⌘⏎] │
│ Optimize ├────────────────────────────────────────────────────────────────────┤
│ Analyze  │ Jobs rail 32 (collapsed traces) / 260 (⌘J: table + console tabs   │
│ Results  │ [Jobs][Console][Host][Report])                                     │
│ Viewer   ├────────────────────────────────────────────────────────────────────┤
│ ───────  │ Status bar 24: cursor RAS (space ▾) · renderer · tit x.y · api v1  │
│ Jobs     └────────────────────────────────────────────────────────────────────┘
│ Settings · Help (pinned bottom)
```

- The **subject switcher** (`⌘P`, also palette entries) is the ONLY subject picker in the app. Batch is
  additive: "+N more ▾" opens `ui/SubjectPicker.tsx` in a popover. Pages read `useSubject()`.
- **Command palette** (`cmdk`, `⌘K`): pages, subjects, simulations/runs, actions (Run, Stop job,
  Open in viewer, Save scene, toggle theme). Nav rows lose their Kbd badges; shortcuts live in the
  palette and the `?` sheet.
- **Viewer page** is full-bleed (no work-pane padding, no max width): 40 px source bar over the
  canvas grid; the inspector holds Layers / Cursor / Regions / Layout blocks.
- **Jobs** is one component at three heights (rail 32 / panel 260 / full page route `jobs`); the
  panel's Host tab absorbs `pages/system` (live CPU/RAM/disk, processes); Report tab shows the
  sandboxed report iframe at full width.
- **Quick notes** → global drawer `⌘⇧N`. **Subject info** → Project page's subject inspector
  (Workbench: Prepare / Target / Simulate / Analyze stage cards with complete/partial/running/missing
  chips and one "next" action each). **Source (EEG forward)** → Prepare ▸ Source mode.
  **NIfTI group average / Cluster permutation / Nilearn visuals** → Analyze ▸ Group / Figures.
  **Gallery** → palette only (`VITE_INCLUDE_GALLERY`).
- Settings ▸ "Feature panels" becomes ▸ "Optional tools" and toggles *modes* inside Prepare/Analyze,
  never nav items. No window reload on toggle.

## 2. Page migration map (nothing is lost)

| Today | New home | Notes |
|---|---|---|
| subjects, panel-subject-info | **project** | table = subject-info's superset (raw/fs/m2m/dwi/ct/leadfields); inspector = Workbench stage cards + Export |
| preprocess, panel-source | **prepare** | modes: Structural (recon-all/charm), DWI (QSIPrep/QSIRecon dialogs), Source (EEG forward) |
| simulator | **simulate** | Montage / Flex-result / Free-hand tabs stay; subject from context bar; flush sections; Electrode + Conductivity under disclosure with value summary |
| optimizer-flex, optimizer-ex | **optimize** | Method ⟨Flex │ Ex │ mEx⟩; ONE `pages/_shared/roi/RoiPicker`; delete `optimizer-ex/roi/RoiPicker.tsx`, `optimizer-ex/PlanPanel.tsx`; ex results tab → Results; cost line ("185 electrodes · 7 splits · 119,140 combos") lives beside the buckets AND in the action bar |
| analyzer, panel-nifti-group-average, panel-cluster-permutation, panel-nilearn-visuals | **analyze** | Scope ⟨Subject │ Group │ Figures⟩; Group = average / permutation methods; Figures = nilearn visuals |
| results (+ optimizer-ex results tab) | **results** | one tree: simulations · flex · ex/mex · analyses · group · figures · reports; every row has "Open in viewer" (deep link `/viewer?kind=&subject=&simulation=&field=`) and "Open externally ▾" |
| viewer | **viewer** | Tetravox full-bleed (§4); Freeview/Gmsh in "Open externally ▾"; no-WebGL2 state |
| jobs, system | **jobs** (route) + jobs panel [Jobs][Console][Host][Report] | System's charts/process table = Host tab |
| panel-quick-notes | global drawer ⌘⇧N | same `/api/notes` |
| settings, help | settings, help | About lists Tetravox (MIT) notice; Help `?` sheet lists app + viewer keys |
| dev (gallery) | palette only | extended with the new primitives |

Page ids that other code navigates to (`navigate('/simulator')` etc.: panels/source:200, panels/
subject-info:176, system:163, simulator/FlexTab:65, simulator/index:136, simulator/PlanPanel:113,
subjects:30, analyzer/ResultsPanel:68) are updated by the lane that owns the *caller*; `App.tsx`
landing = `project`.

## 3. Design rules and acceptance numbers (DESIGN.md v2 carries these)

- Tokens unchanged (colours, `--field`, theme mechanics). New: `--canvas` (#0B0D10 in both themes),
  `--control-h: 28px`, `--row-h: 28px`, `--field-label-w: 160px`, type scale 11/14 (chips only) ·
  12/16 · **13/18 base** · 14/20 prose · 16/22 · 20/26.
- `FormSection`: flush (eyebrow 11 px uppercase + 1 px rule + 12 px body), 28 px sticky header with
  a right-aligned **value summary** when collapsed ("ellipse · 8×8 mm · gel 4 mm"), a **•** when any
  child is non-default, a `--danger` dot when any child has an error, a ⋯ menu (Reset section).
  A collapsed group with a non-default value **force-opens** and badges "Advanced · 2 changed".
- `Field`: label-left grid `var(--field-label-w) minmax(0,1fr)`, min-height 28; help → (i) popover;
  units as suffix inside the control. Full-bleed exceptions: coordinate/sphere tables,
  ElectrodePairsEditor, KeyValueTable, PathInput, chip MultiSelect, consoles, callouts.
- Defaults are visible, changes are marked: default value text `--ink-2`, changed value `--ink` with a
  2 px accent tick in the label gutter.
- No page header (title + purpose) except Settings and Help. No `--shadow-1` on cards; elevation only
  on Popover/Drawer/Dialog/Toast. Ground inversion: app ground `--surface`, `--bg` only in gutters.
- Empty states inside panes: left/top aligned, ≤ 2 lines, one action. Whole-page empties stay centred.
  Skeletons only on first load, sized to real rows; refetch = 2 px indeterminate bar under the context bar.
- A failed data load is never a toast; it is an inline error in the surface that failed. Disconnected
  = warning strip + action bar disabled with reason.
- Keyboard: unmodified keys belong to whatever has focus (canvas included); every app shortcut carries
  ⌘/Ctrl; `?` opens one sheet listing app + viewer keys; Esc is scoped; `⌘⇧V` focuses the canvas.
- **Acceptance (measured on the e2e screenshots at 1280×800):** work column ≥ 880 px (was 674);
  vertical space below chrome ≥ 684 px (was 582); per-section chrome ≤ 41 px (was 94); page header
  0 px (was 86); Simulate and Optimize first screens show all Tier-1 controls without scrolling.

## 4. Tetravox integration architecture (revised 2026-09-02 — service boundary)

```
tetravox repo ──release──▶ tetravox-embed-<ver>.tgz ──installed──▶ /opt/tetravox/embed  (TI image; dev: TIT_TETRAVOX_EMBED_DIR)
                                                                        │ served by tit.server at /tetravox/ (own CSP)
tit.server  GET /api/view/{kind}  ──scene: ViewSpec v2 (URL refs)──▶  renderer pages/viewer  ──<iframe src="/tetravox/index.html?embed=1&hostOrigin=…">
            GET /api/files/raw/{path}  ◀── embed's dataset worker fetch ──┘        │ postMessage protocol v1 (§4.5): load / setLayout / setCursor / screenshot … ; ready / status / progress / layers / cursor / probe
                                                                                  └─ fallback: POST /api/viewers/tetravox → launches the Tetravox desktop app with the scene file (no X11); Freeview/Gmsh last
```

Boundaries: TI never imports Tetravox code. The embed bundle is opaque to TI (a directory with a manifest). Data never crosses the boundary except as URLs (the embed fetches `/api/files/raw/...` itself, same origin, session cookie) and as JSON messages. A crashed or leaking viewer is confined to its iframe; unmounting the iframe frees every worker and WASM heap.

### 4.1 Scene contract — SUPERSEDED: the `scene` field on `GET /api/view/{kind}` / `POST /api/view/args` becomes a **Tetravox ViewSpec v2** document (Tetravox-owned schema, `viewspec.schema.json` shipped in the embed bundle) whose `datasets[].ref.path` are absolute same-origin `/api/files/raw/...` URLs; the `TitScene` shape below was the Stage-0 interim and is retired in Stage 2b. Kept for reference:

```jsonc
{
  "version": 1,
  "title": "ernie · Thalamus · TI_max",
  "space": "subject",                       // "subject" | "mni"
  "cursor": null,                           // [x,y,z] world RAS or null
  "layout": "2x2",                          // "1x1" | "2x2" | "3d+1" | "3d"
  "datasets": [
    { "id": "t1", "name": "T1.nii.gz", "kind": "volume", "bytes": 13400000,
      "path": "/mnt/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz",
      "url": "/api/files/raw/mnt/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz",
      "lazy": false },
    { "id": "tissues", "name": "final_tissues.nii.gz", "kind": "volume", "bytes": 2600000, "path": "…", "url": "…",
      "sidecars": { "lut": { "path": "…/final_tissues_LUT.txt", "url": "/api/files/raw/…/final_tissues_LUT.txt" } }, "lazy": true },
    { "id": "gm", "name": "grey_Thalamus_TI.msh", "kind": "mesh", "bytes": 48000000, "path": "…", "url": "…",
      "sidecars": { "opt": { "path": "…/grey_Thalamus_TI.msh.opt", "url": "…" } }, "lazy": true }
  ],
  "layers": [
    { "id": "L0", "datasetId": "t1", "kind": "volume", "role": "base", "name": "T1", "visible": true, "opacity": 1, "colormap": "gray" },
    { "id": "L1", "datasetId": "timax", "kind": "volume", "role": "field", "name": "TI_max", "visible": true, "opacity": 0.7,
      "colormap": "hot", "window": { "percentile": { "lo": 95, "hi": 99.9 } }, "threshold": { "lo": null, "hi": null } },
    { "id": "L2", "datasetId": "tissues", "kind": "volume", "role": "atlas", "name": "Tissues", "visible": false, "opacity": 0.5, "isLabel": true },
    { "id": "L3", "datasetId": "gm", "kind": "mesh", "role": "mesh", "name": "GM mesh · TI_max", "visible": false, "opacity": 1,
      "field": "TI_max", "colormap": "hot", "window": { "percentile": { "lo": 95, "hi": 99.9 } }, "clip": "cursor", "contours": true }
  ]
}
```

Rules: `url` is origin-relative (the client prefixes `location.origin`, which makes it absolute for
the engine); `path` is the container path (display, and what `POST /api/viewers/*` needs); hidden
layers' datasets are `lazy` (bytes fetched when first made visible); thresholds are `null`, never
±Infinity; `window.percentile` keys map onto the engine's `Stats.percentiles` so no server-side
NIfTI read is needed (`cal_min/cal_max` from the ViewSpec become `window: {lo, hi}` when set).
Electrode overlay LUTs must carry alpha 255 (fix `tit/tools/electrode_overlay.py`; the engine honours
LUT alpha verbatim).

### 4.2 Raw file route

`GET|HEAD /api/files/raw/{path:path}` — path is an absolute container path without the leading `/`;
jail = project dir + `resources/atlas/` (narrowed from `resources/`); refuse `.html .htm .xhtml
.svg .xml .xsl .mhtml`; `application/octet-stream` (+ `.wasm`→`application/wasm` for the static
bundle), `x-content-type-options: nosniff`, `content-disposition: attachment`, `accept-ranges: bytes`,
ETag from mtime+size with 304 on `If-None-Match`; never gzip-encode; `os.open(O_NOFOLLOW)`-based fd
stream to close the TOCTOU window. Mock server: `TIT_MOCK_DATA_ROOT` streams the same route from a
host directory for e2e against real files.

### 4.3 Client (`desktop/src/renderer/viewer/`) — REVISED: an iframe host, not an in-process engine. `TetravoxFrame.tsx` mounts the embed URL (from `GET /api/capabilities.tetravox_embed`), owns the postMessage channel (origin-checked), and exposes the same store surface (`status`, `layers`, `cursor`+`space`, `progress`, actions) so the shell's status bar and the Viewer page do not care where rendering happens. `protocol.ts` = the embed's published `HostMessage`/`EmbedMessage` types (copied from the embed manifest's `.d.ts` at install time or hand-pinned by protocol version). The Stage-0 in-process files (`engine.ts`, `scene.ts`, vendored packages) are deleted. Original Stage-0 text kept for history:

- `engine.ts` — `probeWebGL2()`, `createEngine(canvas)`, theme sync (`Engine.setTheme` from the app
  theme store), resize observer + DPR, `dispose()` = `removeDataset` for every dataset (worker
  terminate — the only way WASM memory is released).
- `scene.ts` — `applyScene(engine, scene, origin)`: datasets → `addDataset({kind:'path', path: origin + url, sidecars})`
  (lazy ones deferred until a layer becomes visible), layers → `addLayer/updateLayer`, layout →
  `setLayout`, cursor → `setCursor`; percentile windows resolved from `Dataset.stats.percentiles`.
- `store.ts` (zustand) — `status: 'idle'|'loading'|'ready'|'no-webgl2'|'error'`, `scene`, `layers`
  (engine mirror), `cursor` + `space`, `progress` per dataset, actions (toggle/opacity/colormap/window,
  set layout, screenshot, save scene JSON, load deep link).
- `TetravoxCanvas.tsx` — the canvas element + status overlays (loading per dataset with bytes,
  no-WebGL2 state with renderer name and the two external buttons, error inline).
- Tests: vitest with `MockEngine`-style stub for `applyScene`; Playwright `viewer-engine.spec.ts`
  loads real `sub-ernie` T1 + TI_max + tissues via the mock's raw route, asserts `probe()` values
  and `Dataset.stats`, and takes light/dark screenshots (pixels are not asserted).

### 4.5 Embed protocol v1 (owned by tetravox `docs/EMBED.md`; summarised here)

Envelope `{ tvx: 1, type, id?, …payload }`. Embed accepts only messages from `window.parent` with `event.origin === hostOrigin` (query param); host accepts only `event.origin === embedOrigin`. Host → embed: `hello`, `load {scene, baseUrl?}`, `setTheme`, `setLayout`, `setCursor`, `setLayerVisible`, `setLayerOpacity`, `updateLayer`, `setActiveLayer`, `screenshot {id,…}`, `serialize {id}`, `probe {id, world}`, `focus`, `reset`. Embed → host: `ready {version, caps}`, `status {phase}`, `progress`, `loaded`, `layers`, `cursor`, `probe`, `screenshot`, `scene`, `error`. Additive-only after v1.

### 4.4 Build (REVISED: applies to the embed bundle served at `/tetravox/`, not to the TI renderer bundle)

Vite: `optimizeDeps.exclude: ['@tetravox/wasm','@tetravox/engine','@tetravox/protocol']`,
`worker.format: 'es'`, `build.assetsInlineLimit: 0`, `base: './'` (already). Engine + wasm in their
own lazy chunk (only the viewer page imports them). ESLint ignores `vendor/`. `tsconfig.web.json`
type-checks the vendored TS (it passes under the current strict flags; pin the vendored sha).
CSP (`tit/server/app.py`): add `script-src 'self' 'wasm-unsafe-eval'`; keep `worker-src 'self' blob:`;
no COOP/COEP. Third-party notice: `desktop/THIRD-PARTY-NOTICES.md` + Settings ▸ About.

## 5. Stages, lanes, ownership (one agent per lane; Opus; no lane edits outside its files; shared needs are *reported*, not edited)

### Stage 0 — Foundations (parallel)
| Lane | Owns | Delivers |
|---|---|---|
| **F1 Tetravox client** | `desktop/vendor/**`, `desktop/scripts/vendor-tetravox.sh`, `desktop/src/renderer/viewer/**`, `desktop/package.json` + lockfile, `desktop/electron.vite.config.ts`, `desktop/eslint.config.mjs`, `desktop/tsconfig*.json`, `desktop/THIRD-PARTY-NOTICES.md`, `desktop/tests/e2e/viewer-engine.spec.ts`, `desktop/tests/unit/viewer-*.test.ts` | §4.3 + §4.4; proves T1 + TI_max + tissues + GM mesh load from real files through the mock raw route with probe assertions and screenshots |
| **F2 Server** | `tit/server/**`, `tit/viewspec.py`, `tit/catalog.py`, `tit/tools/electrode_overlay.py`, `contracts/**`, `tests/*.py`, `desktop/tests/mock-server/**`, `desktop/tests/fixtures/**`, `desktop/src/renderer/api/schema.d.ts` (via `gen:api`) | §4.1 + §4.2 + CSP + capabilities + contract gate green + pytest; mock server raw route + scene fixtures |
| **F3 Design system** | `desktop/DESIGN.md`, `desktop/src/renderer/ui/**`, `desktop/src/renderer/index.css`, `desktop/src/renderer/pages/dev/**`, `desktop/tests/unit/{cssRules,layoutPrimitives,tokenContrast}.test.ts` | §3 primitives: tokens, flush `FormSection`, label-left `Field`, `ActionBar`, `ContextBar` pieces, `PageLayout` variants (`standard`/`full-bleed`, no header), `StatusBar`, `SegmentedControl`, value-summary/changed-marker helpers; Gallery shows all; DESIGN.md v2 with guardrails + acceptance numbers. **No page files edited.** |

### Stage 1 — Shell + IA (parallel, after F3)
| Lane | Owns | Delivers |
|---|---|---|
| **S1 Shell** | `desktop/src/renderer/app/**` (except `jobs-rail/**`), `desktop/src/renderer/main.tsx`, `desktop/tests/unit/{navBrandMark,topBarProject,useSystemStream}.test.tsx`, `desktop/tests/e2e/{_helpers,smoke,launcher,gallery}.spec/ts` | nav rail (§1), context bar with subject switcher + batch chip, command palette, keyboard rules, `useSubject()` spine (URL-synced), status bar, `PageDef` v2 (`navGroup: 'project'|'subject'|'system'`, `layout`, `hideHeader`), landing = project, quick-notes drawer host, inspector/action-bar slots |
| **S2 Jobs three heights** | `desktop/src/renderer/app/jobs-rail/**`, `pages/jobs/**`, `pages/system/**`, `pages/panel-quick-notes/**` + `pages/panels/quick-notes*`, `tests/e2e/{jobs,system}.spec.ts`, `tests/unit/{jobsStream,jobStateChip,systemStream}.test.*` | one Jobs component at rail/panel/page heights; panel tabs Jobs/Console/Host/Report; `pages/system` folded into Host; quick notes as the drawer S1 hosts |

### Stage 2 — Pages (parallel, after Stage 1)
P1 project · P2 prepare · P3 simulate · P4 optimize · P5 analyze · P6 results · P7 viewer · P8 settings+help (+ About notice, keyboard sheet) — ownership = the page directories in §2 plus each page's own `tests/e2e/<page>.spec.ts` and `tests/unit/<page>-*.test.ts`; `pages/_shared/roi/**` → P4; `pages/panels/_shared.ts` + `pages/panels/*` shims → P8 (delete with the panels group). P7 also owns `renderer/viewer/**` from here on.

### Stage 3 — Integration, verification, QA
Gate: `npm run typecheck && npm run lint && npx vitest run && npm run build && npm run e2e` (mock,
per-run ports), `pytest` host suite, `dev/contracts_check.py`, `black` on touched Python. Real
container (`tit-v3-spike`, image `idossha/simnibs:v2.5.0`, worktree at `/ti-toolbox`, Dataset 000 at
`/mnt/000`): restart, rebuild renderer, real-data Playwright run of the viewer (probe values on
sub-ernie Thalamus), Electron tour screenshots of every screen light+dark. Then a 3-reviewer QA panel
(designer / researcher / engineer) against DESIGN.md v2 + §3 numbers + a security check of the raw
route, a fix pass, and a recheck.

### Stage 4 (next program) — viewer as input device (D8), Tetravox published to npm, X11 retirement timer.

## 6. Risks carried into the build
- Test contract: 21 e2e locators key on nav labels (incl. the middle dot in "Optimizer · Ex/mEx-search"),
  `smoke.spec.ts` pins `window.tit`'s 12 keys and ⌘1/⌘8/⌘9, `cssRules.test.ts` asserts raw CSS —
  every lane updates the specs it owns; S1 owns the helpers.
- WASM memory only returns on `removeDataset`; the viewer must terminate datasets on subject switch.
- Large meshes: default scenes never include `high_frequency` or full-head `.msh`; `bytes` is shown
  before a lazy load; `ernie.msh` (184 MB) is opt-in.
- Vendored engine drift: pinned sha in `VENDORED.md`; `npm run typecheck` covers it.
- Upstream: Tetravox §1 lists URL loading as a non-goal although `fileUrl()` supports it — ask for a
  DECISIONS.md line + an `http://` test in tetravox (follow-up PR).

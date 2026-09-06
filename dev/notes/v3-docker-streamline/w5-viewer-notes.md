# W5 — Desktop: the Viewer on the Tetravox embed, and the vendored engine removed (2026-09-03)

Lane brief: `dev/notes/v3-docker-streamline-plan.md` row W5 (Phase B). Read before starting:
that plan's D1/D3 + §1 contracts + §3 gates, `dev/notes/v3-ux-redesign-plan.md` §1/§4/§4.3/§4.5,
`dev/notes/v3-docker-streamline/w3a-server-notes.md` (scene shape, `/tetravox/` route + CSP,
capabilities, fake-embed message set), `desktop/DESIGN.md` §10 + §8.1, and — this is the one that
changed the plan — the **real** protocol source, which lane W1 had already landed:
`/Users/idohaber/00_development/tetravox-wt-embed/packages/embed/src/protocol.ts` and
`docs/EMBED.md` at commit `46195178df549de9843a5e2eb308fb67ef8319fe` (branch `feat/embed`).

## What shipped

1. **`desktop/src/renderer/viewer/protocol.ts`** — W1's message interfaces copied **verbatim**,
   header naming that commit. Two mechanical deviations, both marked `TI DEVIATION` in place:
   upstream's `import type { Layer, LayoutKind, ProbeResult, ViewSpec, vec3 } from
   '@tetravox/engine'` is replaced by local structural declarations (§0 of the file), and the guard
   half is the **host's** — upstream's `isEmbedMessage` verbatim plus `acceptEmbedMessage`, the
   mirror `docs/EMBED.md` §3 tells every host to write. Three payload-shape widenings are listed
   under "Protocol deviations" below.
2. **`viewer/TetravoxFrame.tsx`** — the iframe host. Mounts
   `<iframe src="${origin}/tetravox/index.html?embed=1&hostOrigin=${encodeURIComponent(origin)}"
   sandbox="allow-scripts allow-same-origin">`, connects the store's channel on mount, disconnects
   on unmount, and renders the three states that replace the pane (`no-webgl2`, `no-embed`,
   `error`) plus the per-dataset loading rows. Exposes `data-viewer-status` on its host div, which
   is what the e2e asserts on.
3. **`viewer/store.ts`** — same public surface as the Stage-0 in-process store
   (`status`/`scene`/`layers`/`cursor`+`space`/`progress`/actions), so `app/viewerStatus.ts` and
   `app/AppStatusBar.tsx` compile untouched. `'no-embed'` is new in the `status` union. The engine
   handle became a `Channel`: id-correlated `postMessage` with origin **and** source checks, a
   handshake timeout, and a per-request timeout.
4. **`pages/viewer/`** — rewritten as a full-bleed page: 40 px source bar
   (`[Subject][Simulation][Field]` + ⟨Subject │ MNI⟩) over the frame, inspector blocks Layers /
   Cursor / Layout / Export (screenshot + scene). Deep links read `?kind=&subject=&simulation=&field=`
   from the router's query **and** the document's. Capability gate:
   `capabilities.tetravox_embed.available === false` shows a designed "not bundled in this image"
   state naming the reported embed version. `api.ts` lost `launchFreeview`/`launchGmsh`/`cancelJob`
   and every job/console import; PARITY.md rewritten around "v3 does not launch anything".
5. **`pages/results/`** — `useOpenInFreeview`/`useOpenInGmsh` replaced by one `useOpenInViewer()`
   navigation, and `viewerSearch(link)` is exported from `pages/results/index.tsx` as the shared
   query-key convention. (Two other lanes had already started importing it —
   `pages/analyzer/AnalyzerPage.tsx:55` and `pages/optimizer-flex/index.tsx:23` — so the signature
   `{subject, simulation?, field?, kind?}` is now a cross-page contract, not a local helper.)
6. **Un-vendored** — `desktop/vendor/**`, `desktop/scripts/vendor-tetravox.sh`,
   `viewer/{engine,scene,types}.ts`, `viewer/TetravoxCanvas.tsx`, `pages/viewer-dev/**`,
   `tests/e2e/viewer-engine.spec.ts` and `tests/unit/viewer-scene.test.ts` deleted; the three
   `@tetravox/*` `file:` deps and `gl-matrix` removed from `package.json`; `electron.vite.config.ts`
   lost the tetravox `manualChunks` branch, `optimizeDeps.exclude`, `worker.format` and
   `assetsInlineLimit`; `eslint.config.mjs` lost the `vendor/` ignore; THIRD-PARTY-NOTICES rewritten
   to say the embed ships **with the image**, not with this package.
7. **Tests** — `tests/unit/viewer-protocol.test.ts` (11 cases: the four ways a message is refused,
   the `'*'` escape hatch, the type unions, the URL contract, the shape-tolerance helpers),
   `tests/unit/viewer-store.test.ts` (17 cases: handshake + timeout + `no-webgl2`, load/progress/
   live-id replacement/re-send-on-reload, optimistic-then-authoritative layer edits, layout
   translation, id-echo correctness for `screenshot`, serialize fallback, disconnect),
   `tests/e2e/viewer.spec.ts` (4), the two new `tests/e2e/results.spec.ts` cases, and
   `tests/e2e/viewer-real.spec.ts` (skipped unless `TIT_TETRAVOX_EMBED_DIR` names a built embed).

## The iframe: sandbox, CSP and origin decisions

**`sandbox="allow-scripts allow-same-origin"`.** The pair together normally reads as "a sandbox
that is not a sandbox", so the reasoning is written out in `TetravoxFrame.tsx`'s header and
summarised here. The embed is served from **this app's own origin** by the same `tit.server`, and
it has to be:

- its dataset workers `fetch('/api/files/raw/…')`, a route authenticated by the session cookie. A
  frame without `allow-same-origin` is an *opaque* origin: no cookie, every fetch cross-origin,
  every file 401.
- the protocol's entire trust model is `event.origin === hostOrigin`. An opaque origin posts
  `"null"`, indistinguishable from any other sandboxed frame on the page — the origin check would
  have to be dropped exactly where it matters.
- `tit/server/static.py`'s `TETRAVOX_CSP` grants `script-src 'self' 'wasm-unsafe-eval'` and
  `worker-src 'self' blob:`. An opaque origin cannot use a `'self'` source at all.

So the two flags grant nothing a plain same-origin iframe would not already have; the flags that
are **absent** are the ones doing work — no `allow-popups`, `allow-modals`, `allow-top-navigation`
(a crash in the viewer cannot navigate the app away), `allow-downloads`, `allow-forms`. Real
confinement is the server-side CSP on `/tetravox/` plus the fact that unmounting the frame kills
every worker and WASM heap. Electron logs a warning for the pair; it is expected and correct here.

**The app's own CSP already permits all of this** (`tit/server/app.py`): `frame-src 'self'` for the
iframe, `img-src 'self' data: blob:` for the screenshot preview. Nothing needed to change server-side.

**Downloads are `<a download>` with a `data:` href**, for both the PNG and the scene JSON, and that
was picked against two alternatives: `window.tit` has no write-a-file method (only
`selectFile`/`selectDirectory`, which put a native modal on the screen — forbidden by DESIGN.md
§8.1 on this machine), and `window.open(dataUrl)` is a top-level `data:` navigation, which Chromium
blocks. A `data:` href on an anchor is not governed by CSP, and the anchor lives in the app's own
document, so no `allow-downloads` is needed in the frame. The e2e asserts the `href` and never
clicks it — a save dialog is a window.

**Scene refs need no rewriting.** W3a's contract says every `DatasetRef.path` *and* `.absPath` is
the same origin-relative `/api/files/raw/<path>` string, and W1's `LoadMessage` docs say a
root-relative path is resolved against `baseUrl`, which defaults to the embed document's own
`baseURI` — same origin. So the page passes the server's `scene` through **verbatim** and sends no
`baseUrl`. The two lanes' designs agree; nothing had to be made absolute anywhere.

## Protocol deviations (host-side widenings, all marked in `protocol.ts`)

The real embed satisfies the upstream types exactly; these three exist so the same host also works
against the e2e fake embed (`desktop/tests/e2e/fixtures/fake-embed/index.html`, W3a's), whose
payloads are a lossy subset. None of them loosen a security check.

| # | Upstream | This host accepts | Why |
|---|---|---|---|
| 1 | `ReadyMessage.version: 1` | `number \| string` | the fake posts `version: "fake"`; nothing branches on the value |
| 2 | `LoadedMessage.{datasets,layers}: LoadedDataset[] / Layer[]` | also `string[]` of ids | the fake posts ids only; `normalizeLoadedDatasets`/`normalizeLayers` fold both |
| 3 | `CursorMessage.space: string` (required) | optional | the fake echoes `world` only; the host knows the space from the server |

One behavioural consequence of #2 needed a decision: an id-only `loaded` would blank every
inspector row down to `L0`, `L1`. `store.ts::withPreservedNames` lets a nameless incoming layer
inherit the name the mirror already had **for that id, else at that position** — position because
`Engine.load` re-issues ids, which is exactly when it matters. Only the *name* is inherited;
visibility, opacity and everything else always come from the embed.

Also added, and useful beyond the fake: **`REQUEST_TIMEOUT_MS = 6000`** on every request
(`screenshot`, `serialize`, `probe`). The protocol says "ignore a type you do not know", so silence
is *correct* far-side behaviour for a message a given build does not implement — a host that waited
forever would leave a button spinning until the window closed. Every caller has a fallback
(`serializeScene()` falls back to the scene the server built; the others answer `null`).

## BLOCKER for another lane: the fake embed's inline script is blocked by its own CSP

`desktop/tests/e2e/fixtures/fake-embed/index.html` (W3a's, not this lane's) puts its whole
implementation in an **inline** `<script>`, and both the mock (`tests/mock-server/server.mjs`'s
`TETRAVOX_CSP`) and the real server (`tit/server/static.py`'s `TETRAVOX_CSP`) serve
`script-src 'self' 'wasm-unsafe-eval'` on every `/tetravox/` response. Chromium refuses it:

```
[error] Executing inline script violates the following Content Security Policy directive
'script-src 'self' 'wasm-unsafe-eval''. Either the 'unsafe-inline' keyword, a hash
('sha256-gGZV9uys5EWHW5e335KwYCkI7btdM8aNH8gI1eWb9iw='), or a nonce ('nonce-...') is required.
```

The double therefore never ran, and the whole desktop e2e path it exists to enable was red before
this was found. **The fix is one file split, no behaviour change:** move the contents of the
`<script>…</script>` block into `desktop/tests/e2e/fixtures/fake-embed/embed.js` and replace the
block with `<script src="embed.js"></script>`. That keeps the mock's CSP identical to production
(which is the point of it) and matches the real embed, whose scripts are external modules. Adding
`'unsafe-inline'` to the mock's CSP would work too but would make the mock stop mirroring the
server, so it is the worse fix.

**Not applied here — that fixture is W3a's file.** Every gate below was therefore run twice: once
in-tree (the fixture as it stands) and once with `TIT_MOCK_EMBED_DIR` pointed at a CSP-compliant
copy of the same fixture built in the scratchpad (identical bytes, script externalised). The mock
already reads that env var, and Playwright merges `webServer.env` onto `process.env`, so no repo
file had to change to prove it.

## Gates — commands and results

```
$ cd desktop && npm run typecheck
12 errors, NONE in this lane's files (list below)

$ npm run lint
✖ 3 problems (0 errors, 3 warnings)          # warnings are pre-existing react-compiler notes on
                                             # ui/DataTable.tsx and ui/VirtualList.tsx

$ npx vitest run
Test Files  2 failed | 43 passed (45)
Tests       4 failed | 465 passed (469)      # the 4 are W3b's PreprocessConfig schema, below
$ npx vitest run tests/unit/viewer-protocol.test.ts tests/unit/viewer-store.test.ts
Test Files  2 passed (2) / Tests 28 passed (28)

$ npm run build
✓ built in 1.78s

# with the fixture fix (scratchpad copy) — the state the tree reaches once W3a lands the split:
$ TIT_MOCK_EMBED_DIR=<scratchpad>/fake-embed-csp TIT_E2E_RUN_ID=w5-14850 \
    bash scripts/e2e-quiet-check.sh npx playwright test \
      tests/e2e/viewer.spec.ts tests/e2e/results.spec.ts tests/e2e/smoke.spec.ts
15 passed (1.3m)
e2e-quiet-check: no Electron/Chromium window reached the screen.   PASS

# in-tree, fixture as it stands:
$ TIT_E2E_RUN_ID=w5-intree bash scripts/e2e-quiet-check.sh npx playwright test <same three>
10 passed, 5 failed (2.5m)
  — the 4 viewer.spec cases and results.spec's "'Open in viewer' deep-links a simulation",
    all stuck at data-viewer-status="loading" because the embed never boots. Same failure, one
    cause, and it is the CSP blocker above.
e2e-quiet-check: no Electron/Chromium window reached the screen.
```

Screenshots (evidence, not assertions): `desktop/tests/e2e/artifacts/w5-shot2/viewer-{light,dark}.png`
at 1280×900. The dark rectangle is the fake embed's own body; a real embed paints its panes there.

### The 12 typecheck errors, none in this lane's files

| File | Owner | What |
|---|---|---|
| `src/renderer/app/jobs-rail/api.ts:47` | S2 / W4 (`app/**`) | still declares the `"viewer"` `JobKind`, which W3a removed from the contract. Exactly the dead-code deletion W3a's notes flagged for `tit/jobs/kinds.py`, on the client side. |
| `src/renderer/pages/preprocess/index.tsx` (8) | W3b | `run_recon`, `run_subcortical_segmentations`, `parallel_recon` against the new `PreprocessConfig` (`run_fastsurfer`, `fastsurfer_threads`) |
| `tests/unit/preprocess-defaults.test.ts:173`, `tests/unit/shell-subject.test.tsx:79,85` | W3b / S1 | same rename, plus `SubjectDetail.has_fastsurfer` now required |

The four vitest failures (`tests/unit/preprocess-defaults.test.ts` ×3,
`tests/unit/forms-ajvResolver.test.ts` ×1) are the same `PreprocessConfig` change, validated against
`contracts/schema.json`. All were present before this lane started and none touch the viewer.

`src/renderer/pages/analyzer/api.ts` and `src/renderer/pages/optimizer-flex/api.ts` were in this
list at the start of the lane (dead `launchFreeview`/`launchGmsh`) and were fixed by a concurrent
lane while this work was in progress; they are clean now.

## contracts_for_other_lanes

- **`viewerSearch(link)` / `ViewerLink`**, exported from
  `desktop/src/renderer/pages/results/index.tsx`, is the deep-link convention every page uses to
  open the viewer: `{subject, simulation?, field?, kind?}` → `?kind=&subject=&simulation=&field=`,
  with `kind` defaulting to `"simulation"` when a simulation is named and `"subject"` otherwise.
  Navigate with `navigate({pathname: "/viewer", search: viewerSearch(...)}, {state: {subject}})`.
  Already consumed by `pages/analyzer/AnalyzerPage.tsx` and `pages/optimizer-flex/index.tsx`.
- **`renderer/viewer`'s public surface** (`src/renderer/viewer/index.ts`): `TetravoxFrame`,
  `useViewerStore`, the protocol types and guards. `ViewerStatus` gained `'no-embed'`; everything
  `app/viewerStatus.ts` and `app/AppStatusBar.tsx` read is unchanged.
- **`protocol.ts` is a copy, not a fork.** When the embed ships a new protocol version, re-copy the
  interfaces from `packages/embed/src/protocol.ts` and update the commit in the file header. The
  installed bundle's version is reported at `capabilities.tetravox_embed.protocol`.

## needs_from_other_lanes

1. **`desktop/tests/e2e/fixtures/fake-embed/index.html`** (W3a) — **BLOCKING the e2e gate.** Split
   the inline `<script>` into `embed.js` beside it and reference it with
   `<script src="embed.js"></script>`. No other change. See the blocker section for the exact
   Chromium error and why the alternative (`'unsafe-inline'` in the mock's CSP) is worse.
2. **`desktop/tests/e2e/fixtures/fake-embed/index.html`** (W3a) — non-blocking: the fake implements
   no `serialize` handler, so `viewer.spec.ts`'s "Save scene" assertion currently waits out
   `REQUEST_TIMEOUT_MS` (6 s) and exercises the store's fallback rather than the happy path. Adding
   a `case "serialize": post("scene", { id: msg.id, spec: lastScene })` would make it a real
   round-trip and cut ~6 s from the suite. While there: `loaded` could carry
   `[{id, name, kind}]` objects and `cursor` could carry `space`, which would let this host drop
   deviations #2 and #3.
3. **`desktop/src/renderer/app/jobs-rail/api.ts:47`** (S2 / W4) — delete the `"viewer"` `JobKind`
   branch; nothing submits a viewer job any more (W3a removed the routes, this lane removed the
   last caller). It is one of the 12 typecheck errors.
4. **`desktop/src/renderer/app/viewerStatus.ts`** (S1 / `app/**`) — its header says
   *"`viewer/store.ts` imports `@tetravox/engine`, which pulls ~530 KB of JS and ~850 KB of wasm"*.
   That has not been true since this lane: the store is a few KB of postMessage plumbing. The
   `import.meta.glob` lazy loader still works and is harmless, but it now produces a build warning
   (*"dynamically imported … but also statically imported"*) and the comment is misleading. A plain
   `import { useViewerStore }` would be simpler and the warning would go. **Behaviour is unaffected
   either way — do not change it as a side effect of something else.**
5. **`desktop/src/renderer/pages/_shared/roi/RoiPicker.tsx`** (P4 / optimize lane) — the prop is
   still called `onOpenFreeview` and the button still reads *"Open T1 in Freeview"*, though
   `pages/optimizer-flex/index.tsx:309-314` now wires it to a viewer deep link and says so in a
   comment. Rename to `onOpenInViewer` / "Open T1 in viewer" so the UI stops naming a program this
   runtime does not have. Also `desktop/src/renderer/dev/Gallery.tsx:184` has an
   `aria-label="Open in Freeview"` demo IconButton.
   (`pages/help/AcknowledgmentsTab.tsx`'s Gmsh entry is a *citation* for the mesh format and should
   stay.)
6. **`desktop/DESIGN.md` §10** (F3 / design-system lane) — the "No WebGL2" bullet still prescribes
   *"the two external routes ('Open in Freeview', 'Open in Gmsh')"* and says Freeview and Gmsh
   remain available behind "Open externally ▾". Both are gone (D3). The implemented state names the
   detected renderer and explains that Chromium M137 removed the software fallback, with no
   buttons; §10 should say that, and should gain the third state (`no-embed`, an image built
   without the bundle).

## Known limitations, deliberately

- **Colormap is read-only** in the inspector. `updateLayer` takes an arbitrary patch, so a picker is
  a small change — but the list of valid colormap names is the *engine's*, and this repo has no copy
  of it by design. It needs a `colormaps` field on `ready` or in the manifest; raise upstream rather
  than hard-code names that will drift. (PARITY gap 1.)
- **`store.probe()` is implemented and unused.** The round-trip is typed and tested; nothing renders
  the answer yet. It is the natural content of a "Values at cursor" block and the thing
  `viewer-real.spec.ts` should assert numerically against sub-ernie. (PARITY gap 5.)
- **Electrode-overlay creation lost its home.** The v1 Viewer page submitted the
  `tit.tools.electrode_overlay` job and showed a status chip. That is a preprocessing action, not a
  viewing one, and it does not fit a 40 px source bar — it belongs in Simulate or Prepare. Nothing
  in the UI calls `GET /api/catalog/electrode-overlays` today. (PARITY gap 4; flagged for the lane
  that owns those pages.)
- **The space control is in the source bar only.** ⟨Subject │ MNI⟩ decides which files the *server*
  puts in the document, so it is a source choice; the Cursor block names the resulting space
  (`"World RAS in subject space — change the space in the source bar"`) instead of repeating the
  control. The brief listed a space selector in both places; one control with one state was the
  better reading.
- **No per-artifact "Open" on Results.** A row navigates to its simulation's scene, not to itself —
  there is no `GET /api/view` shape that means "this one NIfTI as a layer over the subject's T1".
  Written up as gap 5 in `pages/results/PARITY.md`.

## Note on the environment

`e2e-quiet-check` reported the frontmost app changing to **Tetravox** during several runs and
warned about it. Nothing in this lane launches a desktop app — `viewer-real.spec.ts` is skipped
without `TIT_TETRAVOX_EMBED_DIR` and launches nothing even when it runs. It was another process on
the machine. Every run's own verdict was the one that matters and it was the same each time:
*"no Electron/Chromium window reached the screen."*

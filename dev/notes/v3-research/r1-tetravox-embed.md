# R1 — Embedding the Tetravox **engine** in the TI-Toolbox v3 desktop renderer

Reader/designer report. Every claim below is cited `path:line`. Two roots, used as prefixes throughout:

- `TVX` = `/Users/idohaber/00_development/tetravox` (public, MIT, v0.3.3)
- `TI`  = `/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui`

Claims marked **[measured]** were produced by running a command in this session (scratchpad only; nothing in
either repo was modified).

---

## 0. Verdict in one page

**Embedding `@tetravox/engine` as a React component in `TI/desktop` is straightforward and needs no
architectural change on either side.** The engine is a framework-free TypeScript package with a single
`create(canvas, opts) → Engine` entry (`TVX/packages/engine/src/api.ts:675-679`), it imports no React
(**[measured]**: `grep -rn "from 'react" TVX/packages/{engine,wasm,protocol}/src` → no matches), and the
`@tetravox/app` React shell already consumes it the same way `TI/desktop` would — as raw TS through Vite 7
(`TVX/packages/app/package.json:26,47`; `TVX/packages/engine/package.json:8-15` points `main`/`exports` at
`./src/index.ts`).

Four things have to be true, and three of them are one-liners:

| # | What | Where it lands | Size |
|---|---|---|---|
| 1 | Get the three packages **including the built `pkg/tvx_wasm_bg.wasm`** into `TI/desktop/node_modules` | packaging change in `TVX` + a dep line in `TI` | small, but **blocked today** — see §2 |
| 2 | Four Vite options (`optimizeDeps.exclude`, `worker.format:'es'`, `assetsInlineLimit:0`, `base:'./'`) | `TI/desktop/electron.vite.config.ts` | 6 lines |
| 3 | A raw-bytes HTTP route + `'wasm-unsafe-eval'` in the CSP | `TI/tit/server/routes/files.py`, `TI/tit/server/app.py:23-27` | ~30 lines |
| 4 | Re-implement the **app chrome** (layer list, property editors, histogram, cursor readout, layout switcher) | `TI/desktop/src/renderer/pages/viewer/` | **~4–5k lines of React** — this is the real cost |

**No custom Electron scheme is needed.** The engine's `kind:'path'` → `LoadSource{kind:'url'}` mapping passes
an already-absolute URL through unchanged (`TVX/packages/engine/src/datasets/source.ts:56-59`), and the dataset
worker fetches it with a plain `fetch(url)` — no Range, no custom headers, no streaming protocol
(`TVX/packages/wasm/src/sources.ts:142-157`). A same-origin `http://127.0.0.1:<port>/api/files/raw/...` URL
served by `tit.server` is all it takes, and the session cookie rides along automatically because the worker
shares the document's origin.

**The blocker (§2.4) is packaging, not code:** `packages/wasm/pkg/` is git-ignored (`TVX/.gitignore:9-11`;
`git ls-files packages/wasm/pkg` → only `tvx_wasm.d.ts`) *and* `npm pack` silently drops it (**[measured]**).
So neither a git subtree nor a tarball delivers the 848 KB WebAssembly binary today. The fix is one line in
`TVX/scripts/build-wasm.sh` (**[measured]** to work).

---

## 1. What the engine actually is — the embedding surface

### 1.1 Entry point and lifetime

```ts
// TVX/packages/engine/src/api.ts:675-679
export function create(canvas: HTMLCanvasElement, opts?: EngineOptions): Engine {
  return new TetravoxEngine(canvas, opts);
}
```

- `EngineOptions` — `TVX/packages/engine/src/api.ts:429-438`: `{ dpr?, deterministic?, forceDiscardClip?,
  forceCaps?, aa? }`. All optional; the app passes none (`TVX/packages/app/src/renderer/src/engine/factory.ts:69-73`).
- `create()` **throws** when there is no WebGL2 context: `createContext` does
  `if (gl === null) throw new WebGL2UnavailableError()` (`TVX/packages/engine/src/gl/context.ts:182-184`).
  The app therefore probes on a throwaway canvas *first*
  (`TVX/packages/app/src/renderer/src/engine/factory.ts:54-62`) and shows an error screen instead
  (`TVX/packages/app/src/renderer/src/ui/Shell.tsx:196-208`). **TI must copy this probe** — Chromium M137
  removed the automatic SwiftShader fallback, so a blocklisted driver returns `null`
  (`TVX/docs/ARCHITECTURE.md:25`).
- `destroy()` — `TVX/packages/engine/src/api.ts:672`, implementation
  `TVX/packages/engine/src/engine.ts:3292-3313`: cancels rAF, disposes pointer/interaction/cuts, **terminates
  every dataset worker**, disposes GL. Must be called on unmount.

### 1.2 The `Engine` interface (frozen — `TVX/docs/ARCHITECTURE.md:3101`)

Full member list at `TVX/packages/engine/src/api.ts:440-673`. Grouped, with the lines TI will actually call:

| Group | Members | Line |
|---|---|---|
| state | `caps`, `scene`, `views` | 442-444 |
| datasets | `addDataset(src): Promise<Dataset>`, `removeDataset(id)`, `cancelDataset(id)` | 446-450 |
| layers | `addLayer(spec): Layer`, `removeLayer`, `updateLayer<T>(id, patch)`, `reorderLayers`, `setActiveLayer` | 452-456 |
| cursor / views | `setCursor`, `stepCursor`, `nudgeCursor`, `setLayout(layout)`, `setView(id, patch)`, `setRadiological` | 458-473 |
| picking | `pick`, `contourAtScreen`, `setCursorFromPick`, `probe(world): ProbeResult` | 475-485 |
| measurements | `setMeasureMode`, `measureMode`, `addMeasurement`, `removeMeasurement`, `cancelMeasurement` | 498-511 |
| point tool | `setPointTool`, `pointTool`, `pointAtScreen`, `setPointSelection`, `pointSelection` | 527-549 |
| coordinates | `coordinateSpaces()`, `toSpace`, `fromSpace`, `setTemplateSpace`, `attachFsaverage` | 560-596 |
| regions | `labelCentroids(layerId): Promise<LabelCentroid[]>` | 611 |
| chrome | `resetView`, `cameraPreset`, `setAnnotations(patch)`, `setTheme(patch)` | 614-634 |
| perf | `heapBytes`, `iso3dStatus`, `requestRender`, `renderNow`, `whenSettled` | 636-652 |
| output | `screenshot(opts): Promise<Blob>`, `readPixel` | 653-655 |
| persistence | `serialize(): ViewSpec`, `setSceneDir?`, `load(spec, resolve)` | 657-669 |
| events | `on<E>(e, cb): () => void` | 671 |

Events (`TVX/packages/engine/src/api.ts:385-427`): `cursor`, `hover`, `pick`, `probe`, `layers`, `datasets`,
`measurements`, `pointTool`, `progress`, `frame`, `quality`, `error`. The app's subscription pattern is
`TVX/packages/app/src/renderer/src/store/controller.ts:249-298`.

### 1.3 Ancillary exports TI gets for free

`TVX/packages/engine/src/index.ts` re-exports pure helpers so a host does **not** have to re-derive engine
maths in React:

- colormap sampling for a DOM swatch/ramp: `sampleColormap`, `scalePosition`, `isColormapName` (`:23`)
- `fallbackLabelColor` (`:25`) — the deterministic colour a label with no LUT entry gets
- `defaultIso3d`, `derivedIsoLayers`, `iso3dLabels` (`:33`)
- `migrateViewSpec`, `SCENE_VERSION`, `sidecarPathsFor` (`:44`)
- coordinate spaces: `coordinateSpaceOptions`, `toSpace`, `fromSpace`, `vox2rasTkr`, … (`:56-73`)
- `DEFAULT_OVERLAY_THEME` + `OverlayTheme` type (`:83-84`)
- glyph scaling / legend text (`:91-99`), measurement formatting (`:106-115`),
  bounded voxel reads (`:127`), point hit-testing (`:140-146`)
- `probeCapabilities` + `Capabilities` (`:10-11`; shape at `TVX/packages/engine/src/gl/caps.ts:23-47`)

### 1.4 Interaction ownership

The engine attaches its own **pointer** listeners to the canvas
(`TVX/packages/engine/src/engine.ts:509`, `TVX/packages/engine/src/input/pointer.ts:208`): left-drag sets the
cursor, right-drag is window/level, wheel steps the slice, double-click picks (§7.5). It attaches **no keyboard
listeners** — the host owns the key map and calls `stepCursor`/`nudgeCursor`/`cameraPreset`/`resetView`
(`TVX/packages/app/src/renderer/src/keyboard/keymap.ts`).

Consequence for the pane: any DOM you put over the canvas must be `pointer-events: none`, or it eats every
gesture — see the comment at `TVX/packages/app/src/renderer/src/ui/ViewGrid.tsx:8-11`.

---

## 2. Dependency strategy

### 2.1 What the three packages look like on disk

| Package | `main`/`exports` | `files` | `private` | Notes |
|---|---|---|---|---|
| `@tetravox/protocol` | `./src/index.ts` | `["src"]` | `true` | `TVX/packages/protocol/package.json:5-15` |
| `@tetravox/wasm` | `./src/index.ts` + `./worker` → `src/compute-worker.ts` + `./pkg` → `pkg/tvx_wasm.js` | `["src","pkg"]` | `true` | `TVX/packages/wasm/package.json:5-27` |
| `@tetravox/engine` | `./src/index.ts` | `["src"]` | `true` | `TVX/packages/engine/package.json:5-18`; deps: `@tetravox/protocol: workspace:*`, `@tetravox/wasm: workspace:*`, `gl-matrix ^3.4.4` (`:24-28`) |

**There is no `dist`.** Consumers compile the TypeScript source. That is not a rough edge — it is the
*tested* path: `@tetravox/app` (React 19, Vite ^7.3.6, electron-vite ^5) consumes exactly this
(`TVX/packages/app/package.json:26,44,47`). React 19 vs TI's React 18 is irrelevant: the engine has no React
dependency at all (§0).

### 2.2 Does Vite 7 / tsc handle raw TS from a linked package? — **[measured] yes, both**

- **Vite**: existence proof above (`@tetravox/app` builds today with `vite ^7.3.6`).
- **tsc**: TypeScript *does* type-check `.ts` files inside `node_modules` when they are reached by an import,
  and `skipLibCheck` does **not** suppress it (that only covers `.d.ts`). **[measured]** — a stub package with
  a deliberate `noUncheckedIndexedAccess` violation under `node_modules/@fake/pkg/src/index.ts` produced
  `error TS18048: 'first' is possibly 'undefined'` from `TI/desktop/node_modules/.bin/tsc` with TI's exact
  compiler options.
- **But the engine passes cleanly under TI's options.** **[measured]** — running
  ```
  tsc --noEmit --target ES2022 --module ESNext --moduleResolution bundler \
      --lib ES2023,DOM,DOM.Iterable --jsx react-jsx --strict --noUncheckedIndexedAccess \
      --noFallthroughCasesInSwitch --skipLibCheck --esModuleInterop --resolveJsonModule \
      --isolatedModules packages/engine/src/index.ts
  ```
  from `TVX` exits 0 with no diagnostics. TI's `moduleResolution` is already `"bundler"`
  (`TI/desktop/tsconfig.web.json:6`), which is what makes the `exports`-map-to-`.ts` resolution work.
  Differences from `TVX/tsconfig.base.json` that do **not** matter: TI omits `verbatimModuleSyntax`,
  `moduleDetection: force` and the `WebWorker` lib — the worker entry
  (`TVX/packages/engine/src/worker/dataset-worker.ts`) is reached only through `new URL(...)`, so it is not in
  TI's program, and it carries its own `/// <reference lib="webworker" />` (`:9`).

  **Risk to log:** this is a moving target. A future engine commit that only compiles under
  `exactOptionalPropertyTypes: false` + `verbatimModuleSyntax` could break `npm run typecheck` in TI. Pin
  exact versions and treat a bump as a change that runs TI's typecheck.

### 2.3 The wasm asset and the worker — how Vite must be told

Two `new URL(..., import.meta.url)` sites carry the whole build contract:

```ts
// TVX/packages/engine/src/engine.ts:560-563
const worker = new Worker(new URL('./worker/dataset-worker.ts', import.meta.url), {
  type: 'module',
  name: `tvx-${id}`,
});
```
```js
// TVX/packages/wasm/pkg/tvx_wasm.js:1158-1159  (wasm-bindgen --target web glue)
if (module_or_path === undefined) module_or_path = new URL('tvx_wasm_bg.wasm', import.meta.url);
```
called as bare `init()` from `TVX/packages/wasm/src/compute-worker.ts:48-49,99-105`.

Vite turns both into emitted assets **only if those files are in Vite's own module graph** — i.e. not
pre-bundled by esbuild. That is exactly what `TVX/packages/app/electron.vite.config.ts:41-49` says:

```ts
// The wasm-pack glue is a linked workspace package; pre-bundling it would move
// `new URL('tvx_wasm_bg.wasm', import.meta.url)` out of Vite's asset graph.
optimizeDeps: { exclude: ['@tetravox/wasm'] },
worker: { format: 'es' },
build: { target: 'chrome138', sourcemap: true, assetsInlineLimit: 0 },
```

and `base: './'` is load-bearing for the same reason — see the file header
(`TVX/packages/app/electron.vite.config.ts:1-9`): with `base: './'`, `index.html` and every chunk sit at the
same depth, so the relative `new URL` resolves to `<origin>/assets/…` and the `.wasm` arrives with
`content-type: application/wasm`. **TI already sets `base: "./"`** (`TI/desktop/electron.vite.config.ts:20`).

Streaming instantiation degrades gracefully: if the server does not answer `application/wasm`, the glue logs a
warning and falls back to `WebAssembly.instantiate(await response.arrayBuffer())`
(`TVX/packages/wasm/pkg/tvx_wasm.js:1093-1107`). So a wrong MIME type is slow, not fatal.

### 2.4 The blocker: `pkg/` is git-ignored *and* unpackable — **[measured]**

```
TVX/.gitignore:9-11
  # wasm-pack output. NEVER a pnpm workspace member (§2); ...
  packages/wasm/pkg/*
  !packages/wasm/pkg/tvx_wasm.d.ts
```
`git ls-files packages/wasm/pkg` → `packages/wasm/pkg/tvx_wasm.d.ts` **only**. The real artefacts
(`tvx_wasm_bg.wasm` 848 311 B, `tvx_wasm.js` 40 932 B) exist on disk but are not in git. They are produced by
`TVX/scripts/build-wasm.sh:54` (`wasm-pack build --target web`, wasm-pack 0.15.0 pinned at `:11`, requires
`rustup target add wasm32-unknown-unknown`, `:30-34`).

**[measured]** `npm pack --dry-run` in `TVX/packages/wasm` emits:

```
npm warn gitignore-fallback No .npmignore file found, using .gitignore for file exclusion.
npm notice 📦  @tetravox/wasm@0.3.3
npm notice 820B package.json
npm notice ... src/*.ts only ...
npm notice total files: 10        <- pkg/ is ABSENT
```

Cause: npm falls back to ignore files, and `TVX/packages/wasm/pkg/.gitignore` contains a single `*` (written by
wasm-pack; noted at `TVX/scripts/build-wasm.sh:67-68`). The `files: ["src","pkg"]` allowlist does not override
a per-directory ignore file. `pnpm pack` has the same result (**[measured]**: 21 418 B tarball, `src/` +
`package.json` + `LICENSE` only).

**[measured] fix, verified:** copy `packages/wasm` to a scratch dir, `rm -f pkg/.gitignore`, `npm pack
--dry-run` →
```
npm notice 377B   pkg/package.json
npm notice 848.3kB pkg/tvx_wasm_bg.wasm
npm notice 4.6kB  pkg/tvx_wasm_bg.wasm.d.ts
npm notice 16.7kB pkg/tvx_wasm.d.ts
npm notice 40.9kB pkg/tvx_wasm.js
...
npm notice package size: 382.0 kB
```
One line at the end of `TVX/scripts/build-wasm.sh` (`rm -f "$ROOT/packages/wasm/pkg/.gitignore"`, or write an
empty `pkg/.npmignore`) makes every packaging route work. The root `.gitignore` already keeps `pkg/` out of
git, so nothing regresses.

### 2.5 The second blocker: `workspace:*` — **[measured]**

`@tetravox/engine`'s deps are `workspace:*` (`TVX/packages/engine/package.json:25-26`). **[measured]**
installing a plain `npm pack` tarball of the engine into an npm project fails:

```
npm error code EUNSUPPORTEDPROTOCOL
npm error Unsupported URL Type "workspace:": workspace:*
```

**[measured]** `pnpm pack` rewrites them — the packed `package.json` carries
`"@tetravox/wasm": "0.3.3", "@tetravox/protocol": "0.3.3"`. So **tarballs must be produced with `pnpm pack`
(or `pnpm publish`), never `npm pack`.**

Third item: all three manifests are `"private": true`
(`TVX/packages/{protocol,wasm,engine}/package.json:4-5`), so `pnpm publish` refuses until that is flipped.

### 2.6 Option comparison

| Option | Delivers wasm? | Cross-manager (pnpm→npm)? | Reproducible in CI? | Verdict |
|---|---|---|---|---|
| **A. npm `file:` link to the local checkout** | yes (reads `pkg/` in place) | yes-ish | **no** — lockfile records `../../../../../../../Users/idohaber/00_development/tetravox/packages/engine` (**[measured]**), and npm installs **none** of the engine's transitive deps (**[measured]**: "added 1 package", no `gl-matrix`), relying on the tetravox checkout's own `pnpm install` having been run (`TVX/packages/engine/node_modules` → `@tetravox`, `gl-matrix`) | **dev only** |
| **B. `pnpm pack` tarballs vendored into `TI/desktop/vendor/`** | only after the §2.4 fix | yes (pnpm rewrites `workspace:`) | yes, if the tarballs are committed (382 KB + ~460 KB + ~10 KB) | **good stopgap** |
| **C. git subtree / submodule of `TVX`** | **no** — `pkg/` is not in git; TI's build would need Rust + `wasm-pack 0.15.0` + `wasm32-unknown-unknown` (`TVX/scripts/build-wasm.sh:18-34`) | n/a | yes but heavy; also drags `crates/`, `Cargo.lock` (frozen, `TVX/docs/ARCHITECTURE.md:3140-3141`) and a second lockfile discipline into TI | **reject** |
| **D. publish `@tetravox/{protocol,wasm,engine}` to npm or GitHub Packages** | yes, after §2.4 + §2.5 | yes | yes | **recommended target state** |

### 2.7 Recommendation

**Do D, with B as the bridge and A for day-to-day development.**

Upstream asks for `TVX` (all small, all additive):

1. `scripts/build-wasm.sh`: `rm -f packages/wasm/pkg/.gitignore` after `wasm-pack` (**[measured]** fix).
2. Flip `"private": true` → publishable on `protocol`, `wasm`, `engine`; add `repository`/`homepage`.
3. Publish with `pnpm publish -r` (rewrites `workspace:*` — **[measured]**), from a CI job that runs
   `pnpm wasm` first (`TVX/package.json:13-14`).
4. Optional: add `"sideEffects": false` and consider **not** shipping `*.test.ts` in `files` (the engine tarball
   currently carries them — **[measured]** `npm pack --dry-run` lists `src/color/colormaps.test.ts` etc.).
5. Optional but worth discussing: a `dist` build (`tsc -b` → `.js` + `.d.ts`). It would make TI's
   `npm run typecheck` immune to §2.2's drift, at the cost of a second build artefact and of breaking the
   `new URL(..., import.meta.url)` worker/wasm resolution unless the emitted JS keeps those expressions intact
   (it does with `module: ESNext`). **Not required for v1** — raw TS is what the app ships with.

TI side, once published:

```jsonc
// TI/desktop/package.json  "dependencies"
"@tetravox/engine": "0.3.4",     // exact, no caret — see §11 version drift
"@tetravox/wasm": "0.3.4",
"@tetravox/protocol": "0.3.4"
```

### 2.8 The exact `TI/desktop/electron.vite.config.ts` diff

```ts
  renderer: {
    base: "./",                                   // already present, TI/desktop/electron.vite.config.ts:20
    plugins: [react(), tailwindcss()],
+   // The engine spawns a module Worker and the wasm glue resolves its binary with
+   // `new URL(..., import.meta.url)`; pre-bundling either moves both out of Vite's asset graph.
+   // (mirrors TVX/packages/app/electron.vite.config.ts:41-49)
+   optimizeDeps: { exclude: ["@tetravox/engine", "@tetravox/wasm", "@tetravox/protocol"] },
+   worker: { format: "es" },
    server: {
      host: "127.0.0.1",
+     // ONLY while @tetravox/* is an npm `file:` link to a checkout outside this project.
+     fs: { allow: [".", process.env.TETRAVOX_SRC ?? "."] },
      proxy: { /* unchanged */ },
    },
    build: {
+     target: "chrome138",
+     assetsInlineLimit: 0,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
+           if (/[\\/]node_modules[\\/]@tetravox[\\/]/.test(id)) return "tetravox";
            ...
```

`worker.format: "es"` is mandatory: the engine constructs `new Worker(url, { type: 'module' })`
(`TVX/packages/engine/src/engine.ts:561`), and Vite's default worker format is IIFE, which cannot be a module
worker.

---

## 3. The data path — how bytes reach the engine

### 3.1 The chain, verbatim

```
Engine.addDataset({ kind:'path', path })                       api.ts:446
  → sourceName(src) = path.split(/[/\\]/).pop()                datasets/source.ts:42-46
  → looksLikeVolume(name) ? 'loadVolume' : 'loadMesh'          engine.ts:559,599,628-631
  → toLoadSource(src) = { kind:'url', url: fileUrl(path), sidecars:{lut?,opt?} }
                                                               datasets/source.ts:61-77
  → new Worker(new URL('./worker/dataset-worker.ts', import.meta.url), { type:'module' })
                                                               engine.ts:560-563
  → worker: loadSource(source)                                 wasm/src/sources.ts:213-235
      → fetch(url)                                             wasm/src/sources.ts:143
      → readStream(urlName(url), response.body, content-length)  sources.ts:156
      → DecompressionStream('gzip') iff name ends '.gz' AND first two bytes are 1f 8b
                                                               sources.ts:110,130-139
      → Uint8Array → wasm                                      compute-worker.ts:115-120
```

### 3.2 The URL prefix **is** pluggable — no fork needed

```ts
// TVX/packages/engine/src/datasets/source.ts:56-59
export function fileUrl(path: string): string {
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(path) || path.startsWith('/@fs/')) return path;
  return `tetravox://file/${encodeURIComponent(path)}`;
}
```

An **absolute** `http://…` string passes through verbatim (the doc comment at `:49-55` says this is deliberate —
a scene file may reference a URL, and the §11 test harness serves the reference dataset over Vite's `/@fs/`).
`tetravox://` is only the Electron-app default.

**A root-relative `/api/...` does NOT pass through** — it would become
`tetravox://file/%2Fapi%2F...`. TI must build absolute URLs:

```ts
const url = new URL(`/api/files/raw${containerPath}`, window.location.origin).toString();
engine.addDataset({ kind: 'path', path: url, sidecars: { lut: lutUrl } });
```

This works identically in `electron-vite dev` (Vite proxies `/api` — `TI/desktop/electron.vite.config.ts:24-28`)
and in production (the BrowserWindow loads the server origin).

### 3.3 What the server route must answer

| Requirement | Evidence | Note |
|---|---|---|
| **`200 OK`, whole body.** No Range, no `206`. | `fetch(url)` with no init, `if (!response.ok) throw` — `TVX/packages/wasm/src/sources.ts:143-149` | Tetravox's own Electron handler is a plain 200 stream with no Range support either (`TVX/packages/app/src/main/protocol.ts:102-121`) |
| **Streaming body preferred.** | `response.body` drained chunk-by-chunk (`sources.ts:151-156`, `drain` at `:67-98`); `arrayBuffer()` fallback if `body === null` (`:152-154`) | Starlette `FileResponse` streams — good |
| **`content-length` optional.** | only used for the progress denominator; the code already tolerates it being wrong (`sources.ts:77-88`) | |
| **Never set `content-encoding: gzip` on a `.nii.gz`.** | `sources.ts:8-12` explains the double-inflate hazard; TI has no `GZipMiddleware` (`TI/tit/server/app.py:145-147` adds only CSP + TrustedHost) — keep it that way | |
| **The URL's last path segment must be the real filename.** | `urlName(url)` strips `?#` then takes the last `/` segment (`sources.ts:159-167`); `sourceName(source)` does the same (`:41-52`); the engine's volume-vs-mesh routing keys on the same basename (`engine.ts:559,599`) | **This kills `?path=` query-style URLs** — see §3.4 |
| **`.gz` handled client-side**; and the Rust NIfTI reader sniffs `1f 8b` itself as a second line of defence (`TVX/crates/tvx-nifti/src/common.rs:22-23,80`, `format.rs:105-106`) | `TVX/docs/ARCHITECTURE.md:1017-1019` | A gzipped **mesh** has no such fallback |
| **Auth**: the worker's `fetch` sends no headers, so `Authorization: Bearer` is impossible. Same-origin `fetch` defaults to `credentials: 'same-origin'`, so the `HttpOnly` session cookie is sent. | `TI/tit/server/auth.py:43-53` accepts cookie or bearer; `TI/tit/server/app.py:159-173` mints the cookie | The raw route stays behind `require_auth` — **no need to add it to `OPEN_MODULES`** (`TI/tit/server/routes/__init__.py:19`) |

### 3.4 The route shape (recommended)

**Do not** copy `/api/files/artifact?path=…` (`TI/tit/server/routes/files.py:93-108`). A query-style URL makes
`urlName()` return `"raw"`, which means:
- `.gz` inflation in the worker is skipped (a `.nii.gz` still loads because the Rust reader sniffs gzip, but a
  `.msh.gz` would not),
- `MeshMeta.name` / the layer name / the colour-bar title all read `"raw"`,
- and `looksLikeVolume` (`TVX/packages/engine/src/datasets/source.ts:19-21`) would be deciding volume-vs-mesh
  off a mangled string.

Use a path-suffix route so the filename is the last segment:

```python
# TI/tit/server/routes/files.py  (new)
@router.get(
    "/api/files/raw/{path:path}",
    summary="Raw bytes of one project file (NIfTI/mesh/LUT), jailed to the project",
)
def raw(path: str) -> FileResponse:
    resolved = _resolve_jailed("/" + path.lstrip("/"))      # reuses files.py:53-69
    if resolved.suffix.lower() not in _ALLOWED_RAW_EXTS:    # .nii .gz .msh .opt .gii .txt .lut .pos .geo .annot
        raise HTTPException(403, "File type not servable")
    return FileResponse(
        resolved,
        media_type="application/octet-stream",
        headers={"x-content-type-options": "nosniff", "cache-control": "no-store"},
    )
```

Resulting URL, for the real ernie data (`/mnt/000` is the container mount of
`/Users/idohaber/datasets/000`):

```
http://127.0.0.1:8765/api/files/raw/mnt/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz
```

Last segment `T1.nii.gz` → `looksLikeVolume` ✓, gzip inflation ✓, layer name `T1.nii.gz` ✓.

The jail is already the right one: `_resolve_jailed` uses `tit.viewspec.jail_roots()`
(`TI/tit/server/routes/files.py:53-69`, `TI/tit/viewspec.py:514-521`), the same boundary the Freeview launcher
enforces (`TI/tit/server/routes/viewers.py:64-84`). So "replace Freeview" does not widen the file-read surface.

**Sidecars are fetched by the worker too**, best-effort — a 404 is a missing table, not a failed load
(`TVX/packages/wasm/src/sources.ts:190-207`, doc at `:178-189`). They go through the same route.

### 3.5 Do we need a custom Electron scheme? — **No**

`tetravox://file/` exists because the Tetravox *app* reads local disk with no server
(`TVX/packages/app/src/main/protocol.ts:1-22`, allow-list `TVX/packages/app/src/main/paths.ts:16-50`,
rationale `TVX/docs/ARCHITECTURE.md:1037-1045`). TI-Toolbox's data lives **inside the container** at container
paths (`/mnt/000/...`), which the Electron main process cannot open at all; the server is the only process that
can read them. HTTP same-origin is therefore not a workaround — it is the correct architecture here, and it is
the same path the future pure-browser mode will use.

One consequence worth stating: TI gets `tetravox://file`'s allow-list guarantee for free, from a different
mechanism — the `jail_roots()` check plus `require_auth`.

---

## 4. CSP — exact changes to `tit.server`

Current (`TI/tit/server/app.py:23-27`):

```
default-src 'self'; connect-src 'self'; img-src 'self' data: blob:;
style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; frame-src 'self'; object-src 'none'
```

Tetravox's own, for comparison (`TVX/packages/app/src/main/protocol.ts:69-93`):

```
default-src 'none'; script-src 'self' 'wasm-unsafe-eval' tetravox://module;
style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:;
connect-src 'self' tetravox:; worker-src 'self'; base-uri 'none'; form-action 'none'
```

### What must change

```diff
 CSP_HEADER = (
-    "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; "
-    "style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; frame-src 'self'; "
-    "object-src 'none'"
+    "default-src 'self'; "
+    # WebAssembly.instantiate/instantiateStreaming is gated by script-src; without an explicit
+    # script-src the fallback is default-src 'self', which does NOT admit wasm compilation.
+    # No COOP/COEP: Tetravox's wasm is single-threaded forever and must NOT be cross-origin
+    # isolated (ARCHITECTURE.md §1) -- SharedArrayBuffer is deliberately undefined.
+    "script-src 'self' 'wasm-unsafe-eval'; "
+    "connect-src 'self'; img-src 'self' data: blob:; "
+    "style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; frame-src 'self'; "
+    "object-src 'none'"
 )
```

Notes, each verified:

- **`worker-src 'self' blob:` is already sufficient.** The engine's worker is a Vite-emitted same-origin asset
  (`TVX/packages/engine/src/engine.ts:560`), which `'self'` covers. Tetravox actually *removed* `blob:` for
  exactly that reason (`TVX/packages/app/src/main/protocol.ts:85-90`). TI can keep `blob:` (harmless) or drop it.
- **`connect-src 'self'` is already sufficient**: the worker fetches a same-origin URL.
- **`'wasm-unsafe-eval'` in `script-src` is the one real addition.** Belt-and-braces note: TI's middleware only
  attaches CSP to `text/html` responses (`TI/tit/server/app.py:54-59`), so the worker script asset carries no
  policy of its own, and in Chromium a dedicated worker loaded over http takes its CSP from *its own* response
  headers. In practice the wasm compile inside the worker is therefore unrestricted today. Add the directive
  anyway: it costs nothing, it is required the moment the policy is broadened to all responses, and it is
  required in browsers that inherit the owner's policy.
- **No COOP/COEP.** Do not add them. `TVX/docs/ARCHITECTURE.md:29` makes non-isolation load-bearing: cancelling
  an in-flight wasm call is `worker.terminate()` precisely because `SharedArrayBuffer` is `undefined`.
- **`font-src`/`base-uri`/`form-action`** — orthogonal; TI's `default-src 'self'` already covers fonts.
- **MIME type for `.wasm`.** The bundle is served by `FileResponse` with `mimetypes`-guessed types
  (`TI/tit/server/static.py:67`). **[measured]** on this host (Python 3.14) `mimetypes.guess_type('a.wasm')` →
  `('application/wasm', None)`; the container is Python 3.11 where this is **not guaranteed**. Add, once, at
  server start:
  ```python
  import mimetypes; mimetypes.add_type("application/wasm", ".wasm")
  ```
  Failure mode without it is a console warning plus a non-streaming instantiate
  (`TVX/packages/wasm/pkg/tvx_wasm.js:1099-1101`), not a broken viewer.

---

## 5. `TetravoxPane.tsx` — a minimal, correct sketch

Design notes baked in, each with its source:
- The canvas is created **imperatively, once**, outside React's render, and adopted into the DOM. A `<canvas>`
  inside a conditional branch is a different element on either side and the engine keeps drawing into the one it
  was handed (`TVX/packages/app/src/renderer/src/ui/Shell.tsx:11-15,184-189`).
- Sizing is `ResizeObserver` on the host, `Math.max(1, …)` to survive a transient 0×0 flex reflow, and an
  explicit `requestRender()` because reallocating the drawing buffer is not a scene mutation
  (`TVX/packages/app/src/renderer/src/ui/ViewGrid.tsx:33-65`).
- Overlays are `pointer-events: none` (`TVX/packages/app/src/renderer/src/ui/ViewGrid.tsx:8-11`).
- WebGL2 is probed on a throwaway canvas before `create()`
  (`TVX/packages/app/src/renderer/src/engine/factory.ts:47-62`).

```tsx
// TI/desktop/src/renderer/pages/viewer/TetravoxPane.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { create as createEngine, DEFAULT_OVERLAY_THEME } from "@tetravox/engine";
import type { Engine, Layer, ProbeResult, vec3, LayoutKind } from "@tetravox/engine";

/** One entry of what the server told us to show. Container paths, not URLs. */
export interface PaneSource {
  path: string;                                    // "/mnt/000/.../T1.nii.gz"
  sidecars?: { lut?: string; opt?: string };
  layer?: Partial<Layer>;                          // colormap / scale / threshold / tagStyle / field ...
  kind?: Layer["kind"];                            // omit -> derived from the dataset
}

export interface TetravoxPaneProps {
  sources: PaneSource[];
  layout?: LayoutKind;                             // default "2x2"
  dark: boolean;
  onCursor?: (world: vec3, probe: ProbeResult) => void;
  onLayers?: (layers: Layer[]) => void;
  onEngine?: (engine: Engine | null) => void;      // hand the facade to the surrounding chrome
}

function webgl2Available(): boolean {
  try { return document.createElement("canvas").getContext("webgl2") !== null; }
  catch { return false; }
}

/** Container path -> same-origin absolute URL. Absolute, because a root-relative path would be
 *  percent-encoded into `tetravox://file/...` (TVX/packages/engine/src/datasets/source.ts:56-59),
 *  and path-suffixed, so the URL's last segment is the real filename (see report §3.4). */
function fileUrl(containerPath: string): string {
  return new URL(`/api/files/raw${containerPath}`, window.location.origin).toString();
}

export function TetravoxPane({ sources, layout = "2x2", dark, onCursor, onLayers, onEngine }: TetravoxPaneProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [engine, setEngine] = useState<Engine | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;

  const canvas = useMemo(() => {
    const el = document.createElement("canvas");
    el.className = "absolute inset-0 h-full w-full";
    el.setAttribute("data-testid", "tetravox-canvas");
    return el;
  }, []);

  // ---- engine lifetime -------------------------------------------------------------------
  useEffect(() => {
    if (!webgl2Available()) { setFatal("This machine has no WebGL2 context."); return; }
    let created: Engine;
    try { created = createEngine(canvas); }                        // api.ts:675
    catch (err) { setFatal(err instanceof Error ? err.message : String(err)); return; }
    setEngine(created);
    onEngine?.(created);
    created.requestRender();
    return () => { onEngine?.(null); setEngine(null); created.destroy(); };  // api.ts:672
  }, [canvas]);

  // ---- adopt + size ----------------------------------------------------------------------
  useEffect(() => {
    const host = hostRef.current;
    if (host === null || engine === null) return;
    host.insertBefore(canvas, host.firstChild);
    const resize = () => {
      const w = Math.max(1, Math.round(host.clientWidth * dpr));
      const h = Math.max(1, Math.round(host.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w; canvas.height = h;
        engine.requestRender();                                     // ViewGrid.tsx:41-56
      }
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);
    return () => { ro.disconnect(); canvas.remove(); };
  }, [canvas, dpr, engine]);

  // ---- events ----------------------------------------------------------------------------
  useEffect(() => {
    if (engine === null) return;
    const offs = [
      engine.on("cursor", (world) => onCursor?.(world, engine.probe(world))),   // api.ts:386,485
      engine.on("probe", ({ world, result }) => onCursor?.(world, result)),     // api.ts:402
      engine.on("layers", (layers) => onLayers?.(layers)),                      // api.ts:403
      engine.on("error", (e) => console.error(`[tetravox] ${e.code}: ${e.message}`)), // api.ts:426
    ];
    return () => { for (const off of offs) off(); };
  }, [engine, onCursor, onLayers]);

  // ---- theme -----------------------------------------------------------------------------
  useEffect(() => {
    if (engine === null) return;
    // The panes stay dark in both themes (imaging convention, ARCHITECTURE §8:2736); only the
    // chrome the engine draws into the framebuffer follows the app theme. api.ts:634.
    engine.setTheme(
      dark
        ? DEFAULT_OVERLAY_THEME
        : { ...DEFAULT_OVERLAY_THEME, text: [0.95, 0.96, 0.99, 1], halo: [0, 0, 0, 1] },
    );
  }, [engine, dark]);

  // ---- layout ----------------------------------------------------------------------------
  useEffect(() => {
    if (engine === null) return;
    engine.setLayout({ kind: layout, cells: ["axial", "coronal", "sagittal", "view3d"] }); // api.ts:471
    engine.setAnnotations({ scaleBar: true, colorbars: true, orientationCube: true });     // api.ts:618
  }, [engine, layout]);

  // ---- the scene -------------------------------------------------------------------------
  useEffect(() => {
    if (engine === null) return;
    let cancelled = false;
    (async () => {
      for (const l of [...engine.scene.layers]) engine.removeLayer(l.id);
      for (const [id] of engine.scene.datasets) engine.removeDataset(id);   // api.ts:448 -> worker.terminate()
      for (const src of sources) {
        if (cancelled) return;
        const ds = await engine.addDataset({                                // api.ts:446
          kind: "path",
          path: fileUrl(src.path),
          ...(src.sidecars
            ? { sidecars: {
                  ...(src.sidecars.lut ? { lut: fileUrl(src.sidecars.lut) } : {}),
                  ...(src.sidecars.opt ? { opt: fileUrl(src.sidecars.opt) } : {}),
              } }
            : {}),
        });
        if (cancelled) return;
        engine.addLayer({ datasetId: ds.id, kind: src.kind ?? (ds.kind === "volume" ? "volume" : "mesh"),
                          ...src.layer });                                   // api.ts:452
      }
      engine.resetView("view3d");                                            // api.ts:614
    })().catch((err) => setFatal(String(err)));
    return () => { cancelled = true; };
  }, [engine, sources]);

  if (fatal !== null) return <div className="p-4 text-sm">Viewer unavailable: {fatal}</div>;

  return (
    <div ref={hostRef} tabIndex={-1} className="relative min-h-0 min-w-0 flex-1 outline-none">
      {/* every overlay MUST be pointer-events:none — the engine owns the gestures on the canvas */}
      <div className="pointer-events-none absolute inset-0" />
    </div>
  );
}
```

Two things deliberately **not** in the sketch and worth deciding on:

- **Load ordering.** The loop above is sequential; each `addDataset` spawns its own worker + wasm instance
  (`TVX/docs/ARCHITECTURE.md:1002-1005`). Parallel loads are legal but multiply peak wasm memory. For a
  T1 + TI_max + tissues + electrodes scene, sequential is fine (~seconds); for `ernie.msh` (184 MB) do it
  last and show `engine.on('progress')` in a load card.
- **`engine.load(spec, resolve)`** (`api.ts:669`) is the *other* way to build a scene — see §6.

---

## 6. Expressing the standard TI views

### 6.a T1 (gray) + TI_max NIfTI (hot, percentile window) + `final_tissues` label LUT + electrode overlay

Real files, verified present under
`/Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie/`:

```
m2m_ernie/T1.nii.gz
m2m_ernie/final_tissues.nii.gz            + m2m_ernie/final_tissues_LUT.txt
Simulations/Thalamus/TI/niftis/grey_Thalamus_TI_subject_TI_max.nii.gz
Simulations/Thalamus/TI/montage_imgs/electrode_overlay_subject.nii.gz
                                          + .../electrode_overlay_subject.lut
```

```ts
// 1. T1 — grayscale, 2–98 % window is the engine default (scene/defaults.ts:118-125,127-149)
const t1 = await engine.addDataset({ kind: "path", path: fileUrl(`${m2m}/T1.nii.gz`) });
engine.addLayer({ datasetId: t1.id, kind: "volume" });          // colormap 'gray' by default

// 2. TI_max — heat, thresholded at p95, top of the ramp at p99.9.
//    TI's own default percentile window is {lo:95, hi:99.9} (TI/tit/viewspec.py:130), and BOTH are
//    exact keys of Stats.percentiles (TVX/.../scene/types.ts:107) — no histogram interpolation needed,
//    unlike Tetravox's own p90/p97 preset (TVX/.../automation/presets.ts:221-223,61).
const ti = await engine.addDataset({ kind: "path", path: fileUrl(`${sim}/TI/niftis/grey_Thalamus_TI_subject_TI_max.nii.gz`) });
const p = ti.kind === "volume" ? ti.stats.percentiles : null;
const lo = p!["95"], hi = p!["99.9"];
engine.addLayer({
  datasetId: ti.id, kind: "volume",
  colormap: "hot",                                              // ColormapName, types.ts:63-79
  scale: { kind: "heat", min: lo, mid: (lo + hi) / 2, max: hi,
           truncate: false, inverse: false, negative: "hide" }, // types.ts:85-95
  threshold: { lo, hi: Number.POSITIVE_INFINITY, symmetric: false,
               mode: "hide", softEdge: 0 },                     // types.ts:97-105
  opacity: 0.85, showColorbar: true,
});

// 3. final_tissues — label volume + LUT sidecar. `interpolation` is FORCED to 'nearest' for a
//    label volume (scene/defaults.ts:143); labelMode 'outline' reads better over a T1.
const seg = await engine.addDataset({
  kind: "path",
  path: fileUrl(`${m2m}/final_tissues.nii.gz`),
  sidecars: { lut: fileUrl(`${m2m}/final_tissues_LUT.txt`) },   // api.ts:49
});
engine.addLayer({
  datasetId: seg.id, kind: "volume",
  labelMode: "outline", outlineWidthPx: 1, opacity: 0.7,
  visibleLabels: new Uint32Array([1, 2, 3, 4, 5]),              // types.ts:395
});

// 4. Electrode overlay — a label volume whose LUT is `electrode_overlay_subject.lut`.
//    ⚠ That file writes ALPHA 0 (`1 Channel_1 0 0 255 0`), the worker's LUT parser takes alpha
//    verbatim (TVX/crates/tvx-wasm/src/lut.rs:71-87) and buildLabelPalette multiplies it in
//    (TVX/packages/engine/src/layers/volume.ts:400) -> the electrodes render FULLY TRANSPARENT.
//    Override per-label colours on the layer (types.ts:407) until the generator writes 255.
const el = await engine.addDataset({
  kind: "path",
  path: fileUrl(`${sim}/TI/montage_imgs/electrode_overlay_subject.nii.gz`),
  sidecars: { lut: fileUrl(`${sim}/TI/montage_imgs/electrode_overlay_subject.lut`) },
});
engine.addLayer({
  datasetId: el.id, kind: "volume",
  labelColors: { 1: [0, 0, 1, 1], 2: [1, 0, 0, 1] },            // types.ts:407, beats the LUT
  opacity: 0.85,
});
```

### 6.b Gmsh `.msh` with an element field, tissue-tag isolation, cut plane

```ts
// The .msh.opt sidecar seeds tag names/colours/visibility, the field range and the colormap
// (TVX/packages/engine/src/scene/defaults.ts:274-282,442-449). Pass it EXPLICITLY: Tetravox's own
// candidate derivation is app-private (TVX/packages/app/src/renderer/src/lib/sidecars.ts:55-61).
const msh = await engine.addDataset({
  kind: "path",
  path: fileUrl(`${sim}/TI/mesh/grey_Thalamus_TI.msh`),
  sidecars: { opt: fileUrl(`${sim}/TI/mesh/Thalamus_TI.msh.opt`) },
});

const layer = engine.addLayer({
  datasetId: msh.id, kind: "mesh",
  colorMode: "field",                                          // types.ts:563
  field: { source: "elm", name: "TI_max", component: "mag" },   // types.ts:566
  colormap: "jet",
  scale: { kind: "linear", lo, hi },
  threshold: { lo, hi: Number.POSITIVE_INFINITY, symmetric: false, mode: "hide", softEdge: 0 },
  // Tissue isolation — keep only grey matter (SimNIBS tet tag 2)
  isolate: { tags: [2], combine: "all" },                       // types.ts:466-479, 598
  // Cut plane through the cursor
  clip: {
    planes: [{ plane: { normal: [1, 0, 0], offset: 0 },
               enabled: true, followCursor: true }],            // types.ts:451-464
    caps: true, capColorMode: "inherit",                        // types.ts:597
  },
  contoursIn2D: true, fillIn2D: true,                           // defaults for a tet mesh
  showColorbar: true,
});

// Per-tissue overrides without changing the layer's colouring, e.g. a fixed skull colour:
engine.updateLayer(layer.id, {
  tagStyle: { 7: { visible: true, opacity: 0.35, colorMode: "color" } },  // types.ts:586-589
});
```

For very large meshes (`ernie_TDCS_1_scalar.msh`, 5.9 M elements) also set
`glyphs.origins: 'volume'` if you draw arrows — one origin per interior tet via the `meshCentroids` op
(`TVX/packages/engine/src/scene/types.ts:544-558`).

### 6.c GM surface `.gii` with a scalar

```ts
const gm = await engine.addDataset({ kind: "path", path: fileUrl(`${m2m}/surfaces/lh.central.gii`) });
// `isSurfaceMesh` = nTets === 0 (scene/defaults.ts:189-191): the defaults switch to contour-only,
// 1.5 px, and take the next colour from SURFACE_CONTOUR_PALETTE (yellow first, Freeview's pial).
engine.addLayer({
  datasetId: gm.id, kind: "mesh",
  colorMode: "field",
  field: { source: "node", name: "E_magn", component: "mag" },
  colormap: "hot",
  scale: { kind: "heat", min: lo, mid, max: hi, truncate: false, inverse: false, negative: "hide" },
  fillIn2D: false, contoursIn2D: true, contourWidthPx: 1.5,      // defaults.ts:237-244
});
```

For a `.label.gii` / `.annot`, the LabelTable is seeded automatically onto `MeshLayer.label`
(`TVX/packages/engine/src/scene/defaults.ts:266-271`) — flip `colorMode` to `'label'` to use it.

For fsaverage correspondence in the cursor readout, `engine.attachFsaverage({ surfaceId, subjectSphereId,
fsavgSphereId, fsavgSurfaceId })` (`api.ts:596`) — the subject `lh.sphere.reg.gii` is present in
`m2m_ernie/surfaces/`.

---

## 7. What the server emits — ViewSpec / Scene JSON

Tetravox already has **exactly the TI scene** as a committed fixture:
`TVX/packages/app/src/shared/scenes/ernie-ti.tetravox.json` — T1 gray + `grey_TI.msh` coloured by the `elm`
field `TI_max` with a cursor-following clip plane + `TI_max.nii.gz` as a `heat` volume. `ernie-tissues`,
`ernie-eeg` and `ernie-pial` in the same directory cover the label-LUT, electrode-points and surface-contour
cases. **These four files are the spec for what `tit.server` should emit.**

### 7.1 The shape

`ViewSpec` — `TVX/packages/engine/src/scene/types.ts:1100-1166`. `SCENE_VERSION = 2`
(`TVX/packages/engine/src/scene/serialize.ts:459`); v1 is still readable via `migrateViewSpec` (`:475`).

```jsonc
{
  "version": 2,
  "datasets": [ { "id": "ds1", "kind": "volume", "name": "T1.nii.gz",
                  "path": "<relative-to-scene or URL>", "absPath": "...",
                  "fingerprint": "tvxfp1-…",                 // may be "" — see below
                  "sidecars": { "lut": { "path": "final_tissues_LUT.txt" } } } ],
  "layers":  [ /* SerializableLayer[] — Layer with visibleLabels as number[] (types.ts:1086-1094) */ ],
  "activeLayerId": "layer2",
  "slices": [ /* SliceView[] */ ], "view3d": { … }, "layout": { "kind": "2x2", "cells": [...] },
  "cursor": [x,y,z], "radiological": false, "background": [r,g,b,a],
  "lighting": { "ambient": 0.25, "headlight": true },
  "annotations": { "orientationLabels": true, "cornerInfo": true, "conventionBadge": true,
                   "scaleBar": true, "colorbars": true, "crosshair": true, "orientationCube": true },
  "transparency": { "mode": "twoPhase" }
}
```

### 7.2 How TI should use it

`Engine.load(spec, resolve)` (`api.ts:669`, impl `TVX/packages/engine/src/engine.ts:3246-3290`) takes a
resolver `(ref: DatasetRef) => string | null`. **That is the seam TI wants**: the server emits `DatasetRef.path`
as a **container path**, and the renderer's resolver turns it into a same-origin URL:

```ts
await engine.load(specFromServer, (ref) => fileUrl(ref.absPath ?? ref.path));
```

Two consequences, both good:
- The scene JSON stays portable across machines/ports (it holds container paths, not
  `http://127.0.0.1:8765/...`). If you instead put URLs in it, `isOpaqueLocation`
  (`TVX/packages/engine/src/scene/serialize.ts:83-85`) keeps them verbatim — legal, but the file then pins a
  port.
- Sidecars ride along and are re-derived against wherever the dataset resolved (`engine.ts:3259-3267`,
  `sidecarPathsFor` exported at `TVX/packages/engine/src/index.ts:44`).

Caveats:
- `load()` only restores layer kinds `isRestorableKind` accepts (`serialize.ts:448`, used at `engine.ts:3276`) —
  today `volume` and `mesh`; `iso` and `points` layers are skipped. Build those with `addLayer` after the load,
  or wait for upstream.
- `fingerprint` is a loader-side field that is still `''` in practice
  (`TVX/packages/engine/src/scene/serialize.ts:12-15,258`). The server can emit `""`.
- `Threshold.lo/hi` in the committed fixtures are `null` where the engine's own default is
  `±Infinity` (`TVX/packages/engine/src/scene/defaults.ts:38-44`) — JSON has no `Infinity`. Emit `null` and
  let the engine's defaults fill in, or emit a finite bound.

### 7.3 Recommended split of responsibility

Keep `TI/tit/viewspec.py`'s domain logic (which files, which LUT, which percentile — the six audit-bug fixes at
`TI/tit/viewspec.py:11-52`) and add a **second renderer** beside `to_freeview_args`
(`TI/tit/viewspec.py:472`): `to_tetravox_scene(spec) -> dict`. The existing `ViewLayer` fields map almost
one-to-one:

| TI `ViewLayer` (`TI/tit/viewspec.py:133-157`) | Tetravox |
|---|---|
| `path` | `DatasetRef.path` |
| `kind: "volume"` | dataset kind (mesh is derived from the extension) |
| `colormap: "grayscale"` | `VolumeLayer.colormap: "gray"` |
| `colormap: "heat"` | `"hot"` + `scale.kind:"heat"` |
| `colormap: "jet"` / `"lut"` | `"jet"` / label path (`interpolation:"nearest"` + `sidecars.lut`) |
| `opacity` | `LayerBase.opacity` |
| `visible` | `LayerBase.visible` |
| `cal_min` / `cal_max` | `scale.min`/`scale.max` (heat) or `scale.lo`/`hi` (linear) |
| `percentile: {lo,hi}` | resolve server-side as today (`resolve_percentiles`, `TI/tit/viewspec.py:445`) **or** let the client read `Dataset.stats.percentiles['95']`/`['99.9']` (`types.ts:107`) — the second is free and avoids a second NIfTI read |
| `lut` | `DatasetRef.sidecars.lut` |

Also available: `TVX/python/tetravox` (stdlib-only `Job`/scene builder, `job.py` 546 lines,
`runner.py` 244) and `TVX/docs/AUTOMATION.md`. That client drives the **packaged Tetravox app** offscreen
(`--job`, `AUTOMATION.md:14-25`); it is the right tool for *batch figure generation from `tit`* and the wrong
tool for the embedded pane. Worth keeping in mind as a separate, later capability.

---

## 8. Chrome: what the engine draws vs what TI must build

### 8.1 Drawn by the engine, into the GL framebuffer (free)

`TVX/packages/engine/src/overlay/`: `letters.ts` (L/R/A/P/S/I on all four edges of every 2D pane),
`corner.ts` (view name, slice index, world RAS), `badge.ts` (RAD/NEU — not optional,
`types.ts:924-925`), `scale-bar.ts`, `colorbar.ts` (one per visible scalar layer, ticks, threshold notch,
field name, units), `crosshair.ts`, `gizmo.ts` (cut-plane handles), `orientation-cube.ts`,
`measure.ts`, `point-ring.ts`, `point-labels.ts`, `contours.ts`.

Controlled entirely through two calls: `setAnnotations(patch)` (`api.ts:618`, fields at `types.ts:921-943`) and
`setTheme(patch)` (`api.ts:634`, `OverlayTheme` at `TVX/packages/engine/src/overlay/theme.ts:25-67`,
defaults `:77-92`).

**Design rule to inherit**: the panes stay dark in both themes — imaging convention
(`TVX/docs/ARCHITECTURE.md:2736-2738`, `TVX/packages/app/src/renderer/src/theme/tokens.ts:21-25`). So TI's
light theme must *not* set a light `OverlayTheme.background`.

### 8.2 Must be re-implemented in TI (React), with a size estimate

Measured line counts from `TVX/packages/app/src/renderer/src`:

| Chrome | File(s) | Lines | TI needs it? |
|---|---|---|---|
| Layer list: order, eye, opacity, active border, disclosure | `panels/layers/LayerPanel.tsx` | 234 | **yes** |
| Load cards (phase + % + elapsed + Cancel) | `panels/layers/LoadCards.tsx` | 112 | **yes** (drives `engine.on('progress')` / `cancelDataset`) |
| Volume property editor (colormap, window, threshold, labels, iso3d) | `panels/layers/volume/VolumeProperties.tsx` + `iso3d.ts` + `patches.ts` | 656 + ~250 | **yes**, trimmed |
| Mesh property editor (field, tags, clip planes, isolation, glyphs, cross-section) | `panels/layers/mesh/*` | ~1 650 | **yes**, trimmed hard |
| Points / iso editors | `points/PointsProperties.tsx`, `iso/IsoProperties.tsx` | 398 | maybe |
| Histogram with draggable window/threshold handles + presets | `panels/histogram/*` | ~450 | nice-to-have; `sampleColormap`/`scalePosition` are exported (`index.ts:23`) so the ramp is free |
| Cursor readout / info panel (per-layer voxel, value, label, element, tag, fields) | `panels/info/InfoPanel.tsx` + `HeaderPanel.tsx` | 469 | **yes** — this is what replaces Freeview's readout |
| Coordinate bar with space selector | `panels/coordinate/CoordinateBar.tsx` | 180 | **yes**; the arithmetic is all engine-exported (`index.ts:56-73`) |
| Region panel (search, solo, jump-to-centroid) | `panels/regions/*` | ~600 | later |
| Measurement strip | `panels/measure/MeasurePanel.tsx` | 99 | later; formatting is exported (`index.ts:106-115`) |
| Toolbar (layout, radiological, reset, crosshair, colour bars, measure, scale bar, cube, screenshot) | `toolbar/Toolbar.tsx` + `AppMenu.tsx` | 378 | **yes**, trimmed |
| Status bar | `ui/StatusBar.tsx` | 214 | optional |
| **View grid + layout switcher + active-pane border** | `ui/ViewGrid.tsx` + `lib/layout.ts` | ~250 | **yes** — `layoutGrid`/`cellIndexAt`/`layoutCellStyle` are pure and worth porting verbatim |
| Keyboard map | `keyboard/*` | ~300 | **yes** |
| WebGL2 error screen | `ui/Webgl2Error.tsx` | 40 | **yes** |
| Theme tokens ↔ `OverlayTheme` bridge | `theme/tokens.ts`, `theme/theme.ts` | ~250 | small — TI has its own tokens under `TI/desktop/src/renderer/app/theme` |

**Total realistic re-implementation: ~4 000–5 000 lines of React**, of which maybe 2 500 is unavoidable for a
credible Freeview replacement (layer list + volume/mesh editors + info panel + coordinate bar + view grid +
toolbar). None of it is *hard* — §8's rule is "everything the UI can do must be reachable from the `Engine` API
alone. No logic in React" (`TVX/docs/ARCHITECTURE.md:2655`), and the app's panels are thin — but it is the
dominant line-item of this project.

**None of `packages/app` is importable**: it is `@tetravox/app`, `private: true`, an Electron application, React
19, Tailwind 4 with its own token file, and every panel reaches `useController()`/`useUi()` (its zustand store)
— e.g. `TVX/packages/app/src/renderer/src/ui/ViewGrid.tsx:17,25-29`. Treat it as a **reference
implementation to read and port**, not a dependency. Its MIT licence makes copying code legal (§11).

---

## 9. Could TI-Toolbox be a Tetravox **extension** instead? — **Reject for the v3 Viewer; keep as a later, separate idea**

§13 (`TVX/docs/ARCHITECTURE.md:3176-3270`) defines an extension as a `manifest.json` + `index.js` installed at
runtime through File ▸ Extensions…, running **inside the Tetravox app's renderer**, against the frozen
`ModuleHost` (`MODULE_HOST_VERSION = 1`, `:3230-3235`).

Reasons to reject, in order of decisiveness:

1. **It cannot talk to `tit.server`.** The Tetravox app's CSP is `connect-src 'self' tetravox:`
   (`TVX/packages/app/src/main/protocol.ts:84`). A `fetch("http://127.0.0.1:8765/api/jobs")` from an extension
   is blocked outright. Every TI workflow — submit a job, poll status, read the catalog — is an HTTP call.
2. **The host surface has no network and no general file IO.** Extension file access is four narrow IPC
   channels: UTF-8 text ≤ 1 MiB from an already-allow-listed path, an Open sheet, a Save sheet, and a ≤ 8 MiB
   text write (`TVX/docs/ARCHITECTURE.md:1062-1071`). No `.nii.gz`, no subprocess, no Docker.
3. **The dependency wall forbids it.** An ESLint wall on `modules/<id>/**` allows `../host`, the shared control
   kit and `@tetravox/engine` **types** only, and forbids the store, the engine runtime, `bridge()` and
   `automation/*`; `modules.test.ts` re-proves it by reading the sources (`:3221-3228`).
4. **It inverts the product.** TI-Toolbox v3 is an application with ~20 screens
   (`TI/desktop/src/renderer/pages/*`, discovered by `TI/desktop/src/renderer/app/registry.ts:29`); the viewer
   is one of them. As an extension, TI becomes a panel inside someone else's window with no nav rail, no jobs
   rail, no settings.
5. **Distribution.** Extensions are downloaded per-version from their own repository and consented to
   (`:3264-3269`, `:3484+`), and third-party code remains a §1 non-goal (`:3184-3185`). TI would be asking to be
   a first-party Tetravox extension.

**Where it *does* fit** (worth a line in the roadmap, not in this project): a small `tit.roi` or `tit.montage`
extension for users whose primary tool is Tetravox — e.g. placing electrode positions on a scalp surface and
writing a `.tsv` — which is exactly the shape of the shipped sEEG contact editor. That is a *second* product,
built on the frozen `ModuleHost`, not the v3 Viewer.

---

## 10. Risks

### 10.1 GPU / WebGL2

- **`getContext('webgl2')` can return `null`.** Chromium M137 removed the automatic SwiftShader fallback, so a
  blocklisted driver yields `null` (`TVX/docs/ARCHITECTURE.md:25`). This is a **precondition, not an error**:
  probe first (`TVX/packages/app/src/renderer/src/engine/factory.ts:47-62`) and show a real message. On Linux
  under X11 forwarding / VMs / headless CI this is the *common* case. **Recommendation: do not delete the
  Freeview/Gmsh launcher in the same release** — keep it as the documented fallback while the Tetravox pane is
  the default. TI already gates the viewer buttons on `/api/capabilities.x11_display`
  (`TI/desktop/src/main/x11.ts:12-14`); add a symmetric `webgl2` capability on the client side.
- **Electron versions match**: TI pins `electron 44.0.0` (`TI/desktop/package.json:69`), Tetravox `^44.0.0`
  (`TVX/packages/app/package.json:42`). Same Chromium ⇒ identical ESSL semantics.
- `sandbox: true, contextIsolation: true, webSecurity: true` in TI's BrowserWindow
  (`TI/desktop/src/main/index.ts:334-340`) — no obstacle to WebGL2; nothing in `TI/desktop/src/main/*` calls
  `disableHardwareAcceleration` (**[measured]** grep found none).
- **Never `gl_CullDistance`** and never assume `EXT_texture_norm16`: `MAX_CULL_DISTANCES_WEBGL` is 0 on
  ANGLE/Metal but 8 under SwiftShader, and SwiftShader has no norm16
  (`TVX/packages/engine/src/gl/caps.ts:13-18`). This is the engine's problem, not TI's, but it means **CI
  goldens taken under SwiftShader do not prove a real Mac works** — TI's Playwright screenshots of a Tetravox
  pane will be near-useless as pixel assertions.

### 10.2 Memory

`TVX/docs/ARCHITECTURE.md:2832-2866`:
- wasm32 linear memory is capped at 4 GiB with **4032 MiB usable**, and it **grows and never shrinks**
  (`:2834-2836`). This is why every dataset gets its own worker and why `removeDataset` = `terminate()`
  (`api.ts:447-448`, `TVX/docs/ARCHITECTURE.md:1002-1005`). **TI must call `removeDataset` when a layer is
  closed** — not just `removeLayer` — or memory ratchets.
- Load path budget **< 2 × file size**: ≤ 380 MB for `ernie.msh` (184 MB), ≤ 800 MB for
  `ernie_TDCS_1_scalar.msh` (5.9 M elements), ≤ 1.0 GB for the SEEG meshes (`:2846`).
- `buildTopology` budget **< 3.2 × file size** live; `ernie.msh` ≈ 600 MB live / 960 MB resident (`:2847`).
- Renderer JS heap ≤ 400 MB, **no single ArrayBuffer > 1 GB**; GPU ≤ 500 MB (`:2848-2849`).
- **256³ volumes are a non-issue**: 256×256×256 u16 = 33.5 MB on GPU + the same on CPU for probes. The quoted
  worst case is 512×512×416 = 208 MB as R16, 416 MB as R32F, *and the same again* on the CPU (`:2865-2866`).
- The practical TI risk is **T1 + TI_max + tissues + electrodes + `ernie.msh`** open at once: five workers,
  five wasm instances, ~1 GB resident total. Fine on a 16 GB Mac, tight in a constrained VM. Load the mesh
  last, and offer "close layer" that terminates.

### 10.3 Version drift between two repos

- `scene/types.ts`, `api.ts`, `protocol/src/index.ts` and `wasm/src/index.ts` are **frozen**
  (`TVX/docs/ARCHITECTURE.md:3095-3112`): changes must be additive, must edit `ARCHITECTURE.md` in the same
  commit, and must append to `DECISIONS.md`. That is a strong stability guarantee for TI — and a process TI
  must respect when asking for anything.
- **Pin exact versions** (no caret) in `TI/desktop/package.json`, and add a smoke test that boots the pane,
  loads a small fixture and asserts a probe value — a semantic check, not a pixel one (see §10.1).
- `SCENE_VERSION = 2` with an in-place migration (`TVX/packages/engine/src/scene/serialize.ts:459,475`) means
  TI's server-emitted scenes survive an engine bump; TI should still stamp its own emitted version.
- **§1 lists "remote/URL loading" as a non-goal** (`TVX/docs/ARCHITECTURE.md:35`). The mechanism exists, is
  exercised by the §11 harness over `/@fs/`, and is explicitly passed through by `fileUrl`
  (`TVX/packages/engine/src/datasets/source.ts:49-58`) — but TI would be the first *product* depending on it.
  **Ask upstream to promote it from "works" to "supported"** (a `DECISIONS.md` line, plus a test that fetches
  over `http://`). Without that, a future change to `fileUrl` could silently break TI.
- The two repos use different package managers (TI: npm + `package-lock.json`; TVX: pnpm 10.30.3,
  `TVX/package.json:8`) and different lockfile disciplines (`TVX`'s lockfiles are frozen and never merged,
  `:3140-3141`). The registry route (§2.7) is what makes that a non-issue.

### 10.4 Licensing

- Tetravox is **MIT** (`TVX/LICENSE:1-3`, "Copyright (c) 2026 Ido Haber"); every package declares
  `"license": "MIT"`.
- TI-Toolbox desktop is **GPL-3.0** (`TI/desktop/package.json:8`).
- MIT → GPL-3.0 is a permitted one-way combination. Obligations: **keep the MIT copyright notice and permission
  text with the distributed bundle** (an `about`/`licenses` screen, or a `THIRD-PARTY-NOTICES` file shipped in
  the app and in the served static dir). This applies to *copied* code too — porting `ViewGrid.tsx` or
  `layout.ts` into TI carries the notice obligation.
- Same author on both sides, so there is no consent problem; the notice obligation is still real for
  redistribution.
- No copyleft flows back: nothing in TI needs to be MIT.

### 10.5 Small, specific gotchas (each verified above)

1. **Electrode LUT alpha 0** → invisible electrodes. `TI/…/electrode_overlay_subject.lut` writes
   `1 Channel_1 0 0 255 0`; alpha is taken verbatim (`TVX/crates/tvx-wasm/src/lut.rs:71-87`,
   `TVX/crates/tvx-core/src/lut.rs:36-41,60`) and multiplied into the palette
   (`TVX/packages/engine/src/layers/volume.ts:400`). Fix in `tit/tools/electrode_overlay.py` (write 255) or
   override with `VolumeLayer.labelColors`.
2. **Query-string URLs break the filename** (§3.4).
3. **`.msh.opt` and `_LUT.txt` must be passed explicitly** — the sidecar candidate derivation is app-private
   (`TVX/packages/app/src/renderer/src/lib/sidecars.ts:55-61`) and would not find
   `electrode_overlay_subject.lut` anyway (it tries `<stem>_LUT.txt` and `<stem>.txt` only).
4. **`npm pack` silently ships a wasm-less `@tetravox/wasm`** (§2.4) — the failure is a runtime
   `Failed to fetch Wasm`, far from the cause.
5. **`tsc` type-checks the engine's source** (§2.2) — a red `npm run typecheck` in TI can be caused by a
   dependency bump with no TI code change.
6. **`Threshold` uses `±Infinity`** (`TVX/packages/engine/src/scene/defaults.ts:38-44`) which JSON cannot carry.
7. **Bundle weight**: +~460 KB of engine TS (transpiled, before minification) and a separate 848 KB `.wasm`
   asset on the served bundle. Check against TI's existing `manualChunks` budget
   (`TI/desktop/electron.vite.config.ts:41-48`).

---

## 11. Upstream checklist for `TVX` (everything TI needs from Tetravox)

| # | Ask | Size | Blocking? |
|---|---|---|---|
| 1 | `rm -f packages/wasm/pkg/.gitignore` at the end of `scripts/build-wasm.sh` (or write an empty `pkg/.npmignore`) | 1 line, **[measured]** to work | **yes** |
| 2 | Make `protocol`, `wasm`, `engine` publishable (`private: false` + repository fields) and publish with `pnpm publish -r` after `pnpm wasm` | ~10 lines + a CI job | **yes**, for a shippable TI |
| 3 | A `DECISIONS.md` line + a test promoting **`http(s)://` dataset URLs** from "passes through" to "supported" (§10.3) | small | no, but strongly advised |
| 4 | Optional: exclude `*.test.ts` from the published `files` | 1 line | no |
| 5 | Optional: a `dist` build so consumers' `tsc` does not compile engine source | medium | no |
| 6 | Optional: an `EngineOptions.fileUrlBase` (or accept root-relative `/…` in `fileUrl`) so a host need not build absolute URLs. `datasets/source.ts` is **not** frozen; `EngineOptions` is (`api.ts` — additive change, `ARCHITECTURE.md` §12.3) | small | no — the absolute-URL workaround is clean |

---

## 12. Suggested order of work in `TI`

1. **Spike (half a day, no commitments).** `npm i file:$TETRAVOX_SRC/packages/{protocol,wasm,engine}`, add the
   four Vite options (§2.8), add `/api/files/raw/{path:path}` (§3.4) and `'wasm-unsafe-eval'` (§4), drop the
   `TetravoxPane.tsx` of §5 into `pages/dev/`, and load `m2m_ernie/T1.nii.gz`. This proves the whole data path
   end-to-end in one screen.
2. **The three TI scenes** (§6) behind a hard-coded subject/simulation picker.
3. **Chrome**, in this order: view grid + layout switcher → layer list + load cards → volume property editor
   (colormap / window / threshold / labels) → info panel + coordinate bar → mesh property editor.
4. **`to_tetravox_scene(spec)`** in `tit/viewspec.py` beside `to_freeview_args` (§7.3), and switch the pane to
   `engine.load(spec, resolve)`.
5. **Keep the Freeview/Gmsh launcher** until a WebGL2 capability probe is reported and the pane has parity;
   then demote it to a fallback (§10.1).

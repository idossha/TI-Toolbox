# Lane T — Tetravox embed, protocol 2 (2026-09-04)

Branch `feat/embed-protocol2` in `/Users/idohaber/00_development/tetravox-wt-embed-p2`, based on
`origin/main` (e5671b7). **Committed locally, not pushed, no PR** — the maintainer opens it. Another
session was working in that repo throughout; `main` was never checked out and no other worktree was
touched (`main` moved e3f1ab4 → 7cf896f under that session while this ran, without interference).

## 1. Bringing `packages/embed` forward

**Cherry-picked, not rebased.** The four commits (`e8a44bf aba51ca 1957a7d c56c3c8`) were 32 commits
behind `origin/main`; a rebase would have replayed them onto a moving `main` that a second session is
committing to, while a cherry-pick onto a branch cut from `origin/main` gives one linear history that
the maintainer can rebase once, later, on their own schedule.

**What broke, and it was only documentation.** Three conflicts, all append-only prose that both sides
had grown: `CHANGELOG.md`'s `[Unreleased]` block (main's camera/probe extension entry vs the embed's
two), `docs/DECISIONS.md` (two entries dated 2026-09-03), `docs/RELEASING.md` (main's §9.3 extensions
refresh vs the embed's §10). All three resolved by keeping **both** sides in order. No code conflicted,
`pnpm-lock.yaml` did not move (`origin/main` already carries the `packages/embed` importer), and
`Cargo.lock` was untouched — AGENTS.md rule 4 never came into play.

Green against current main **before** anything was added: `pnpm install --frozen-lockfile`, `pnpm wasm`,
`pnpm --filter @tetravox/embed typecheck`, `build`, vitest 32/32, e2e **13/13**.

## 2. What protocol 2 is (decision E5)

Envelope `tvx` stays **1**; `PROTOCOL_VERSION` (i.e. `ready.version` and `manifest.json.protocol`) is
**2**; embed version **0.4.0**. Splitting those two numbers is the whole compatibility story — a
protocol-1 host filters on `tvx !== 1` and posts `tvx: 1`, so bumping the envelope would have made an
*additive* release unreachable by exactly the hosts the additive promise was made to.

Six new host→embed messages and three new embed→host events, all optional:

| Message | Notes for lane M |
|---|---|
| `setPointTool { layerId \| null, mode?, template? }` | `Engine.setPointTool` — the sEEG editor's Add button. Arming **materialises `p<index>` ids** on points that carry none and fires `layers`; it also turns measure mode off. |
| `setPointSelection { layerId, pointId \| null }` | By id, never index. An id not in the live array clears with `reason: 'selection'`. |
| `setPoints { layerId, points }` | Replaces the array (also how a point is deleted). **Use this, not `updateLayer` with a `points` patch** — only this path runs the `state` → colour resolution. |
| `setPickEvents { enabled }` | **Off by default.** |
| `getCamera { id }` → `camera` | |
| `setCamera { preset?, patch? }` | A *patch*: `near`/`far` are derived from the fit radius, and writing all seven fields carries a stale clip range into a restored pose. `preset` is `'A'/'P'/'L'/'R'/'S'/'I'` or `1..6`. |

| Event | Payload |
|---|---|
| `pick` | `kind: 'point' \| 'tri' \| 'tet' \| 'slice' \| 'cursor'`, `world`, `viewId?`, `layerId?`, `pointId?`, `elementId?`, `label? {id,name?,layerId}`, `tag?`, `modifiers {shift,ctrl,alt,meta}`, `probe: ProbeResult`. **One per left press**, ranked point > element > cursor. |
| `pointTool` | The engine's `PointToolEvent` verbatim. Only while a tool is armed. |
| `camera` | A reply only; never announced. |

**ViewSpec points layer**, written inline (`viewspec.schema.json` → `PointsLayer` / `Point`):
`points[] = { position (required), id, name, state, color, radiusMm, group, ordinal, value }`, plus
layer-level `shape`, `radiusMm`, `color`, `labelMode`, `stateColors`, `offPlaneOpacity`, `dotRadiusPx`.

Two host-vocabulary fields resolve before the engine sees the layer:
* `points[].state` → a per-point `color`. Defaults are **byte-exact**: `selected` = `[1,0.8,0.2,1]`
  = `rgb(255,204,51)`, `disabled` = `[0.6,0.6,0.6,1]` = `rgb(153,153,153)`; `idle` is the layer's own
  colour. An explicit `color` wins. Override per layer with `stateColors`.
* `labelMode: 'none' | 'names' | 'labels'` → §4.4's `showLabels` + `labelSource`. **There is no
  `'hover'`** — the engine draws no hover text; draw your own tooltip from `pick`.
  `labelMode` is *spent* (it has a §4.4 twin); `state`/`stateColors` are *kept* on the layer, which is
  where a later `setPoints` reads the palette back from.

### Things lane M must know

1. **`datasetId` names a dataset already in the spec** — the T1 the electrodes sit over. §4.4 gives
   every layer a carrier and there is no points file an embed could fetch. No extra `DatasetRef`, no
   extra fetch.
2. `pick.probe`'s **mesh** rows are at most one round trip stale (§4.7 — `locate` is a worker call).
   The **volume** rows, `label` among them, are exact. For the settled mesh answer send a `probe` with
   the `world` the event carried.
3. `pick` only fires after `setPickEvents { enabled: true }`.
4. A plain `select`-mode click emits `selected` **and** a zero-length `dragEnd` — compare positions
   before recording an edit. A click on a ghosted (off-slice) point emits `selected` alone.
5. `cleared.reason` decides whether to re-arm: `'esc' | 'load' | 'layer' | 'host'` → yours to re-arm;
   `'measure'` → the user chose the other mode, leave it; `'selection'` → the tool is still armed.

## 3. An unplanned repair: `setLayout` used to kill the viewer

`docs/EMBED.md` has documented `setLayout` kinds `'3d' | 'axial' | 'coronal' | 'sagittal'` since
protocol 1 and **none of the four is a §4.5 `LayoutKind`**. TypeScript could not catch it (declared
`LayoutKind`, actual value JSON), so one of them reached `Engine.setLayout` with `cells: undefined` —
`layoutCells`'s exhaustive switch falls off the end — and the **next frame** threw
`Cannot read properties of undefined (reading 'length')` inside `viewports()`, in the render loop,
with nothing reported to the host and no recovery short of reloading the iframe.

`dev/notes/v3-3d-panes-plan.md` opens with `setLayout {kind:'3d'}` as the way to get a single 3-D pane,
so lane M would have hit this on day one. Fixed in `packages/embed/src/layout.ts`: the four names now
mean what the table always said (`'3d'` → `'3d-only'`; a slice name → `'1x1'` with that pane made
active first, which is the only way to choose *which* single pane), and any other string is answered
with an `error` reply instead of a crash. `src/layout.test.ts` pins all three branches.

## 4. Compatibility — proved, not assumed

`packages/embed/test/e2e/embed-compat.spec.ts`, five tests:

* `ready.tvx === 1` and `ready.version === 2` — the two numbers, from a host's side.
* A **protocol-1 ViewSpec** (mesh only, no points/camera/tool) loads to the same layers, the same
  live-id rule, the same `setLayerVisible`/`setLayerOpacity`/`updateLayer`, `serialize`, `screenshot`
  and `probe` behaviour.
* **Every message the embed posts during a whole session** — boot, load, a real click in a pane,
  `setCursor`, `setLayout`, `setTheme`, `serialize`, `reset` — is one of protocol 1's ten types,
  checked against a hard-coded v1 list (not imported, so appending to the union cannot make it pass).
* A click emits **no `pick`** before `setPickEvents`, one after, and none again once it is turned off.
* Protocol-2 and unknown messages posted at a build are answered or dropped, never fatal to the session.

The existing suite ran **unchanged except one line**: `expect(ready['version']).toBe(1)` → `2` in
`embed.spec.ts`, which is the number being bumped. `git diff` on that file is 2 insertions, 1 deletion.

## 5. §11 (their rule 1): numbers first, picture second

`packages/embed/test/e2e/embed-points.spec.ts` — analytic pixel assertions computed from first
principles, then a golden.

* Fixture `testdata/mesh_v2_binary.msh` (committed; **not** gated on `TETRAVOX_TESTDATA`). Its bbox is
  exactly ±10 mm on every axis per `testdata/manifest.json`, so the scene bounds centre is the world
  origin and `center: [0,0]` at `mmPerPx: 0.05` is an exact 20 px/mm ruler: world `(x,·,z)` →
  `(CX + x/0.05, CY − z/0.05)`.
* The scene carries **no mesh layer**, only the dataset the points hang off, and an authored
  `background: [0,0,0,1]`. A 2-D cross-section is unshaded and the points are opaque, so a disc's
  centre pixel is `round(c·255)` of its own colour whatever is behind it.
* Asserted: four discs = `rgb(255,0,0)` (no state), `rgb(255,204,51)` (`selected`),
  `rgb(153,153,153)` (`disabled`), `rgb(0,255,0)` (explicit colour beating its state); 1.5 mm out is
  inside the 2 mm disc and 2.5 mm out is background (so it is a world radius, not a screen one);
  `setPoints` repaints; a host's own `stateColors` are the ones painted (`[0,0.4,1,1]` = `rgb(0,102,255)`).
* Golden `packages/embed/test/golden/swiftshader/embed-points.png` (946×589), captured under the
  §11 policy — same helpers as `packages/engine` (imported, not copied), `updateSnapshots: 'none'`,
  `TETRAVOX_UPDATE_GOLDENS` required, ratio 0.002/0.01 and threshold 0.15.

**One deviation from §11's letter, stated on purpose.** `expectPixel` reads the drawing buffer through
the engine test pages' `window.__tvxRender()`; the app renderer has no such hook and its context is
`preserveDrawingBuffer: false`, so a `readPixels` after compositing reads undefined content (measured —
it returned a stale frame). The embed's analytic pixels therefore come through the documented
`screenshot` message and are decoded in the page: lossless RGBA8, and they are the pixels the product
actually hands a host. `docs/TESTING.md` records this.

## 6. Numbers

| | |
|---|---|
| vitest, `@tetravox/embed` | **56 passed** (was 32) — 4 files: protocol, normalize, points, layout |
| vitest, whole repo | 1905 passed / 83 skipped, 113 files |
| Playwright, `@tetravox/embed` | **30 passed** (was 13) — 13 pre-existing + 5 compat + 12 points/tool/camera |
| typecheck | all 6 packages clean |
| lint | `eslint . && prettier --check .` clean (3 pre-existing warnings in `packages/engine/test/e2e/*`) |
| windowless | `scripts/e2e-quiet-check.sh pnpm --filter @tetravox/embed run e2e` → **PASS**, 49 samples, no window reached the screen |

## 7. The artefact lane M installs

```
/Users/idohaber/00_development/tetravox-wt-embed-p2/packages/embed/dist-pkg/tetravox-embed-0.4.0.tgz
sha256  bd08e6979b52e2751cb5690e274a30f7a5f0fc1809b16076d7018fb3ed95527f
bytes   1786185
manifest.json  { "name": "@tetravox/embed", "version": "0.4.0", "protocol": 2,
                 "sha": "dd9c06a71221bba0ecd5dac2d423dad930ccfd75" }
```

Built with `pnpm wasm && pnpm --filter @tetravox/embed build && pnpm --filter @tetravox/embed pack:embed`.
`dist/` and `dist-pkg/` are gitignored, so the tarball is regenerable from the branch but is not in it;
re-packing produces a different sha256 (tar metadata), so quote the digest of the file you install.

**Smoked as an installed bundle**, not just in the dev server: extracted, served by a plain static
server sending `application/wasm` and `text/javascript`, framed from a minimal host page. It booted,
reported `{ tvx: 1, version: 2, webgl2: true }`, accepted `setLayout {kind:'coronal'}` with no page
error (the crash above), and answered `setLayout {kind:'nonsense'}` with
`error: unknown layout kind 'nonsense'`.

## 8. Open issues for the maintainer

1. **Version lockstep.** `scripts/release.sh` bumps all six `package.json`s to one version, but
   `packages/embed/package.json` now reads `0.4.0` against a `0.3.8` tree, because the tarball a host
   installs is named by that file and lane M needs `0.4.0`. **The next cut should be
   `scripts/release.sh 0.4.0`**; cutting `0.3.9` would walk the embed *back* and ship a protocol-2
   bundle under a version a host may already have seen. Noted in `docs/RELEASING.md` §10.
2. **`screenshot` with `target: 'view'` is untested against a single-pane layout.** It works under the
   default `2x2` (verified); the failure I chased there turned out to be the `setLayout` crash, not the
   screenshot, but nothing now covers `target: 'view'` with a `viewId` under `'1x1'`.
3. **`ready.version` moved 1 → 2.** No host in this programme reads it as an equality check (the
   TI-Toolbox viewer widens it to `number | string` deliberately), but a third-party host that wrote
   `version === 1` would now fail closed. `tvx` is the field that promises stability; this is called
   out in `docs/EMBED.md` §3.
4. **`docs/ARCHITECTURE.md` was not edited**, and nothing required it: no §12.3 frozen interface moved
   (`packages/embed/**` is not on that list, and `engine/src/api.ts`, `scene/types.ts`,
   `protocol/src/index.ts`, `wasm/src/index.ts` and `modules/host.ts` are all untouched). `EMBED.md`,
   `DECISIONS.md`, `RELEASING.md`, `TESTING.md` and the CHANGELOG carry the change.

## 9. Files

New: `packages/embed/src/points.ts`, `src/points.test.ts`, `src/layout.ts`, `src/layout.test.ts`,
`test/e2e/embed-points.spec.ts`, `test/e2e/embed-compat.spec.ts`,
`test/golden/swiftshader/embed-points.png`.

Changed: `src/protocol.ts`, `src/protocol.test.ts`, `src/host.ts`, `src/normalize.ts`,
`src/normalize.test.ts`, `protocol.schema.json`, `viewspec.schema.json`, `example/host.html`,
`playwright.config.ts`, `tsconfig.json`, `package.json`, `scripts/pack.mjs`,
`test/e2e/embed.spec.ts` (one line), `docs/EMBED.md`, `docs/RELEASING.md`, `docs/TESTING.md`,
`docs/DECISIONS.md`, `CHANGELOG.md`.

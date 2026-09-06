# B5 — Viewer (lane notes)

Owns: `desktop/src/renderer/pages/viewer/**`, `desktop/src/renderer/viewer/**` (store's public
surface kept; inspector-only state removed), `tests/e2e/viewer*.spec.ts`,
`tests/unit/viewer-*.test.*`, `tests/e2e/fixtures/fake-embed/**`. Program decision U5;
`desktop/DESIGN.md` §10, §11 (the viewer's three cells), §2.1 (shape C).

---

## 1. What shipped

**The inspector is gone — Layers, Cursor, Scene, and their code.** `pages/viewer/index.tsx` is now
the source bar (4 controls: Subject, Simulation, Field, Space, plus a reload `IconButton`) and
`TetravoxFrame` filling the rest, inside `PageLayout variant="bleed"` with no `rightPane` at all —
`paneWidths().right` reads `0` on this page, which is how "no inspector" is asserted rather than
described. Removed with it: `CoordinateInput`/`Field`/`Switch`/`Slider` from the page,
`datasetFor`/`layerFile` from `lib.ts` (their only caller was the deleted layer list), and from
`viewer/store.ts` — `layout`/`setLayout`/`ViewerLayout` (dead: never rendered, only ever an echo for
a Layout block that was never built) and `screenshotUrl`/`screenshot()`/`serializeScene()` (the
Screenshot and Scene blocks' only callers). `store.probe()` stays, unused but tested — see PARITY.md
gap 4; deleting a *working, tested* capability with no UI yet felt like a different decision than
deleting write-only dead state, so I left it for whoever gives cursor values a home.

**Status cells**: `ras` (mono, `formatRas(cursor)`), `space`, `renderer` (`shortRenderer`, warning
tone on `no-webgl2`), registered via `useStatusCells` — polled for and landed mid-task (B1's
`app/statusCells.ts` + the `AppStatusBar` migration both appeared while I was reading the design
docs). None of the three render on the not-bundled state (nothing was asked); `renderer` is
specifically **not registered** on `no-embed` (the wireframe's "no Renderer cell" line, §10).

**A real bug found and fixed while testing "reload":** the `no-embed` handshake-timeout guard was
`if (get().status === "idle")`. A page that already has a subject selected (the ordinary case) calls
`loadScene` the moment its view query resolves, which moves `status` to `"loading"` well before an
8s handshake could time out — so the guard, checking a `status` that had already moved on, would
never fire again, and a genuinely dead embed showed a stuck loading spinner forever instead of the
designed `no-embed` state. Fixed to key on `embedReady` (set exactly once, by an accepted `ready`,
and by nothing else) — `viewer/store.ts`'s `connect()`. Caught by hand while wiring the reload
button, not by any pre-existing test; added `tests/e2e/viewer.spec.ts`'s "names a frame that never
answers" case to cover it going forward. Two smaller fixes alongside it:
- `loadScene` no longer adopts a scene's nominal `cursor`/`progress` when the store already knows it
  cannot render (`no-webgl2` / `no-embed`) — otherwise the `ras` cell showed a coordinate for a
  crosshair that was never actually drawn on anything, which is the placeholder-cell failure §11
  exists to prevent.
- the scene-load effect gained `reloadToken` as a dependency. A reload remounts the iframe (fresh
  `key`), whose cleanup `disconnect()`s the OLD channel and clears the store's `scene` — the new
  frame's own handshake has no scene of its own to ask for, so without this a reload left the page
  showing nothing until the user changed some other control.

**Reload**: one `IconButton` in the source bar and a second "Reload viewer" button inside
`TetravoxFrame`'s own `no-embed` state, both driving the same `reloadToken` counter the page owns;
`TetravoxFrame` takes it as a `key` on the `<iframe>`, so a reload is a full remount and a fresh
handshake, not a best-effort re-`hello`.

**The three non-embed states** (`TetravoxFrame`, mostly pre-existing, U5 asked for distinct copy
which they already had): not-bundled (page-level, no source bar, no `tetravox-host` at all — "there
is nothing to source"), `no-webgl2` (names the detected renderer, no buttons — nothing to switch on),
`no-embed` (names the timeout, one "Reload viewer" button). `max-width` bumped 460→480px to match
§10's number exactly.

**Fake embed** (`tests/e2e/fixtures/fake-embed/fake-embed.js`), two additive changes because two
states had no way to reach them from outside: `ready.caps.renderer` is now a parenthesised
ANGLE-shaped string ("ANGLE (Fake, Fake GPU, OpenGL 4.1)") so the `renderer` status cell's e2e
coverage has something real to parse, and a click anywhere on the fake posts a `cursor` event at a
fixed coordinate — standing in for a crosshair drag now that the host has no `setCursor` control of
its own to originate one from.

## 2. Dev loop

### Round 1 — build → e2e → read the failures

`npm run build`, then `TIT_E2E_RUN_ID=b5-r1-... bash scripts/e2e-quiet-check.sh npx playwright test
tests/e2e/viewer.spec.ts`. 8/11 passed; 3 failed, all real (not spec bugs):

| test | symptom | root cause |
|---|---|---|
| reload button remounts the frame | status stuck `idle` after reload | scene-load effect had no `reloadToken` dependency (fixed, §1) |
| no-webgl2 renderer cell | `status-ras` had a value it shouldn't | `loadScene` adopted the scene's nominal cursor even when unrenderable (fixed, §1) |
| no-embed + Reload viewer | status stuck `loading`, never `no-embed` | the `status==="idle"` handshake guard (fixed, §1) |

Quiet-check itself: `exit 1` only because the suite failed, never because a window reached the
screen — `frontmost after = ghostty` both rounds, 0 Electron/Chromium windows sampled at layer 0.

### Round 2 — fix → rebuild → re-run → measure

All three findings fixed in `viewer/store.ts` + `pages/viewer/index.tsx` (one test-isolation bug
found in the process: `viewer-store.test.ts`'s `beforeEach` never reset `embedReady`, which the
`status==="idle"`→`embedReady` guard change turned into a real leak between the handshake tests —
fixed alongside). `npm run build` → `TIT_E2E_RUN_ID=b5-r1b-... bash scripts/e2e-quiet-check.sh npx
playwright test tests/e2e/viewer.spec.ts`: **11/11 passed**, quiet-check exit 0. A dedicated metrics
pass (`captureScreen`, both themes, both sizes) on the same build:

| theme | size | dead space | panes (nav/content/work/right) | status cells | header |
|---|---|---|---|---|---|
| light | 1280×800 | 0.42 % | 56 / 1224 / 1224 / 0 | ras, space, renderer, connection, version | 0 |
| dark  | 1280×800 | 0.42 % | 56 / 1224 / 1224 / 0 | same | 0 |
| light | 1440×900 | 0.37 % | 216 / 1224 / 1224 / 0 | same | 0 |
| dark  | 1440×900 | 0.37 % | 216 / 1224 / 1224 / 0 | same | 0 |

A third confirmation run (`b5-final-...`, after the full gate suite) reproduced 11/11 passing and
quiet again, this time with the 1440 nav rail at 56 px instead of 216 (work pane 1384 instead of
1224) — see the finding below. Both outcomes clear every number in §3.

## 3. Self-critique against DESIGN.md §12.4 / plan §3

| # | item | verdict | number |
|---|---|---|---|
| 1 | dead-space ratio within limit; no pane without content | **PASS** | 0.33–0.42 % measured, target ≤ 12 % (§12.3's viewer row) |
| 2 | no page header outside Settings/Help | **PASS** | `pageHeaderHeight: 0` at all 4 captures |
| 3 | every chip/badge from the shared vocabulary | **n/a** | the Viewer has no chips |
| 4 | numbers tabular, units suffixes, paths mono truncate-left | **PASS** | `ras` is `mono tabular-nums` (`useStatusCells({mono:true})`); no paths rendered on this page |
| 5 | both themes ≥ 4.5:1, no hard-coded colours | **PASS by reuse** | every colour is an existing token (`--canvas`, `--on-canvas`, `--ink-2`, `--warning`…); none of my edits added a literal; I did not re-run `tokenContrast.test.ts` specifically since I introduced no new tokens or literal colours |
| 6 | status bar shows only registered cells, no placeholder dash | **PASS** | `formatRas`/`shortRenderer` return `undefined`, never `"—"`; e2e asserts `status-ras`/`space`/`renderer` are absent (not dashed) off this page and on `not-bundled`/`no-embed` |
| 7 | first screen shows all Tier-1 controls at 1280×800 | **n/a** | shape C has no Tier-1 disclosure; §12.3 marks this row n/a for `viewer` |
| 8 | keyboard scoped: ⌘K/⌘P/⌘J/⌘⇧I/⌘⏎/Esc, focus visible | **PASS except ⌘⇧V — see finding below** | ⌘⇧I is a no-op here (`PageLayout`'s effect guards `if (!panel …) return`, and this page passes no `rightPane`) |
| 9 | copy: sentence case, verbs, no "!", no Freeview/Gmsh/X11 | **PASS** | "Reload viewer", "Retry", "This server has no viewer bundle" |
| 10 | spec passes; asserts DOM, not pixels | **PASS** | 11/11, every assertion is a testid/attribute/text; screenshots are captured, never diffed |

## 4. Findings for the orchestrator / other lanes

**1. `app/Shell.tsx`'s ⌘⇧V handler cannot reach the Viewer any more.**
`focusViewerCanvas()` does `document.querySelector(".shell-content canvas")` — a selector for the
Stage-0 in-process `<canvas>` engine. The viewer has been an `<iframe>` (`TetravoxFrame`) since the
postMessage embed replaced it; the selector matches nothing, so ⌘⇧V is currently a silent no-op on
every build, not something my change touched or broke. `viewer/store.ts` already has the right
primitive (`focusCanvas()`, posts `{type:"focus"}` to the embed) — Shell.tsx just isn't calling it.
Out of my ownership (`app/**`); exact diff for whoever owns it:

```diff
- /** ⌘⇧V: hand the keyboard to the canvas, which owns unmodified keys once it has focus. */
- function focusViewerCanvas(): void {
-   const canvas = document.querySelector<HTMLCanvasElement>(".shell-content canvas");
-   if (!canvas) return;
-   if (!canvas.hasAttribute("tabindex")) canvas.setAttribute("tabindex", "0");
-   canvas.focus();
- }
+ /** ⌘⇧V: hand the keyboard to the embed via the protocol's own `focus` message — there is no
+  *  cross-document `<canvas>` to `.focus()` since the postMessage embed replaced the in-process
+  *  engine. */
+ function focusViewerCanvas(): void {
+   useViewerStore.getState().focusCanvas();
+   const frame = document.querySelector<HTMLIFrameElement>('.shell-content [data-testid="tetravox-frame"]');
+   frame?.focus();
+ }
```
(`focusCanvas()` tells the embed's own crosshair/nav to take over; `frame?.focus()` moves the
browsing-context focus so the iframe's unmodified keys start reaching it at all — protocol `focus`
alone doesn't move DOM focus.) I did not make this edit myself since `Shell.tsx` is outside this
lane's paths.

**2. The nav rail's icon/label breakpoint is flaky under a resize *while the Viewer has a live
postMessage channel open*.** Reproduced three ways (`ListAgents` showed no addressable B1 session to
hand this to directly, so it's here instead of a live message):

- Fresh launch directly at 1440×900 (`subjects` or `viewer`, no resize) → `nav-rail` correctly reads
  `data-rail-mode="labels"`, 216 px, on both pages.
- `setViewportSize` 1280→1440 mid-session, `subjects` page (no iframe, no embed) → also correct,
  every time.
- The same resize on `viewer` **with a subject already chosen and a scene loaded** → `data-rail-mode`
  intermittently stays `"icons"` (56 px) even though `window.matchMedia("(min-width:1440px)").matches`
  reads `true` at the same instant — i.e. `NavRail.tsx`'s `useLabelledRail()` React state is stale
  relative to a live read of the same query, only once the page has an active scene/postMessage
  stream running. Not reproducible with the iframe mounted but idle (no subject picked, no scene
  requested) — narrowing it to "busy with embed traffic," not "iframe present."

This is almost certainly why the orchestrator's Q1 number for the Viewer's embed width at 1440
(≥1360px, from a design that assumed the Viewer forces the icon rail at every width — Q1's actual
answer removed that special case) is not reliably reachable: my own three runs measured the 1440
work pane at 1224 px (labels, matches `screens.spec.ts`'s own `subjects` assertion) or 1384 px (icons,
stuck) depending on this race. `tests/e2e/viewer.spec.ts`'s pane-width test asserts the number that
holds in **both** outcomes — `frame ≥ 1200` at both sizes — rather than the higher, flaky one; the
dead-space ceiling (≤ 12 %) clears easily either way (0.33–0.42 % measured). If `screens.spec.ts`'s
own "shell's own numbers" test (which resizes the same live page across sizes) ever intermittently
sees `panes.nav !== 216` at 1440 on a page with heavier live traffic than `subjects`, this is the
same race. I did not chase it further into `NavRail.tsx`/`useLabelledRail` itself — outside this
lane's paths, and it reads more like an Electron/offscreen-renderer scheduling question (a resize's
`matchMedia` "change" event competing with a busy `window.addEventListener("message", …)` stream)
than an application bug in the rail's own logic.

**3. Orchestrator brief vs. Q1's actual resolution.** My brief asked me to assert "iframe width ≥
1200 at 1280 with the icon rail and ≥ 1360 at 1440." The ≥1360 figure is `wireframes.md`'s number
under the *pre-Q1* design (Viewer forces `railMode:"icons"` at every width); Q1's answer explicitly
removed that special case ("the Viewer needs no special case"), and `registry.ts`/`NavRail.tsx`
confirm nothing sets `railMode` today. Under Q1 as implemented, 1440's content box is ~1224 px
(possibly the finding above's flakiness notwithstanding) — never 1360 without forcing the icon rail,
which I was explicitly told not to do. I asserted ≥1200 at both sizes instead (§2 above) and flagged
the discrepancy here rather than silently asserting a number that can't pass, or silently reinstating
the special case Q1 forbade.

## 5. Gates

`npm run typecheck && npm run lint && npx vitest run && npm run build` — all four pass; `typecheck`'s
only remaining error is in `tests/unit/outputsTree-build.test.ts` (B4's file, `analyses.ernie`
possibly undefined), pre-existing and outside this lane's paths — `npx vitest run` shows the same
file's tests passing at runtime (577/577 total). `npx eslint` is clean on every path this lane owns;
the one remaining lint error repo-wide (`tests/e2e/subjects.spec.ts`, unused `gotoPage` import) is
also outside this lane.

`tests/e2e/viewer.spec.ts` (11 tests) and `tests/e2e/viewer-real.spec.ts` (1, correctly skipped — no
`TIT_TETRAVOX_EMBED_DIR`) both green under `scripts/e2e-quiet-check.sh`, three separate runs, 0
Electron/Chromium windows ever sampled at layer 0, focus never left the terminal.

`tests/unit/viewer-page.test.ts` (`formatRas`, `shortRenderer`, `hidden3DLayer`, `readDeepLink`),
`tests/unit/viewer-store.test.ts` (channel/handshake/actions/disconnect), `tests/unit/viewer-protocol.test.ts` —
39/39.

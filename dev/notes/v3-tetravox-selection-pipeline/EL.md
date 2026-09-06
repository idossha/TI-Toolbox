# Lane EL — electrodes as coloured dots, real select/deselect (2026-09-05)

Plan of record: `dev/notes/v3-tetravox-selection-pipeline-plan.md` §1-B (B1–B5). Nothing committed.

## 1. What changed

| File | What |
|---|---|
| `desktop/src/renderer/pages/_shared/scene/model.ts` | `SCENE_PALETTE.channels` is now the **Okabe-Ito** six-hue colour-blind-safe set (was blue/orange/green/pink, whose green and orange collide under deuteranopia — the exact case a 4-pair mTI montage hits). Added `SCENE_PALETTE.idle` (neutral grey) and `SCENE_PALETTE.disabled` (35 % grey). `channelCss()` unchanged, so the form chips follow automatically. |
| `desktop/src/renderer/pages/_shared/scene/embedScene.ts` | Points layer is `shape: "dot"`, `dotRadiusPx: 5`, `stateColors {idle, disabled}` (**no** layer-level `selected`), `labelColorSource: "points"`. `pointsFromMarkers(markers, selection, activeChannel)` gives **every** point an explicit `color` (idle grey / the channel hue), sets `name` only on selected points, and `radiusPx: 7` on the active channel. Exports `channelColor`, `DOT_RADIUS_PX`, `ACTIVE_DOT_RADIUS_PX`. Deleted the now-unused `selectedPointId`. |
| `desktop/src/renderer/pages/_shared/scene/ScenePane.tsx` | **`setPointSelection` and `setPointTool` are no longer sent at all** (`syncPointTool` deleted). `setPoints` stays fire-and-forget. New `activeChannel` (derived from the cursor) + `activateChannel`, `data-active-channel` on the host, and the legend rendered above the stage in the electrode gesture. |
| `desktop/src/renderer/ui/ChannelLegend.tsx` | **new** — one chip per pair: colour swatch + `"E1 → E2"`; click = make that pair active. |
| `desktop/src/renderer/pages/_shared/scene/scene-pane.css` | `.channel-legend` / `.channel-chip` (active state stated by ring **and** ink, never by hue alone). |
| `desktop/src/renderer/viewer/protocol.ts` | Types only, additive: `EmbedPointsLayer.dotRadiusPx`, `.labelColorSource`, `EmbedPoint.radiusPx`, and doc comments recording the measured `stateColors` precedence. |
| `desktop/tests/e2e/fixtures/fake-embed/{index.html,fake-embed.js}` | The fake now mirrors the last `setPoints` into `#points` (one row per point with its `state`, `color`, `name`, `radiusPx`), records every host message type on `document.body.dataset.hostMessages`, and lets a spec pick a **named** electrode by clicking its row. |
| `desktop/tests/unit/scene-pane-embed.test.ts` | +6 cases (colours, names-for-selected-only, palette distinctness, active radius, no ring, dot layer). |
| `desktop/tests/unit/scene-pane-legend.test.tsx` | **new**, 4 cases. |
| `desktop/tests/e2e/scene-pane.spec.ts` | +4 cases (no ring messages; idle→selected; selected→removed; two hues + legend click). |
| `desktop/tests/e2e/real/embed-electrodes.spec.ts` | **new**, 3 pixel tests against the real 0.4.0 embed. |

Not touched: any page file, `ui/ElectrodePairsEditor.tsx` (lane SG), the Tetravox repo, `tit/`.

## 2. The three things measured off the real 0.4.0 bundle

Read out of `/root/.config/ti-toolbox/tetravox/embed/0.4.0/assets/index-CdUrh5CF.js` in
`ti-toolbox-fad740e5-tit-1`, then confirmed by pixels.

**M1 — `stateColors.idle` is dead code; a per-point `color` always wins.** The normaliser is

```js
function $b(n, e) {                      // (point, stateColors)
  const t = n.state;
  if (t === void 0 || t === "idle" || n.color !== void 0) return n;   // idle returns early
  const s = e?.[t] ?? AL[t];
  return { ...n, color: s };
}
```

so an idle point with no colour falls through to the **layer's** `color`, and a layer cannot be
both "idle grey" and "disabled grey". The host therefore writes idle grey and the channel hue
per point. `stateColors.disabled` is still sent (it *is* consulted); `stateColors.selected` is
deliberately absent, because one layer colour cannot say *which* channel.

**M2 — names are per point.** The label builder skips a point whose `name` is absent or empty
(`if (s.name === undefined || s.name === "") continue`), so "names for the selected only" is
expressed by omitting `name` on idle points — no extra message, no `labelMode` toggling.

**M3 — `shape: "dot"` is honoured in the 2-D slice pass only.** `dotRadiusPx` reaches exactly one
uniform, `uDotPx`, set in the `POINTS_2D` shader path; the 3-D pass has no such uniform and draws
an instanced millimetre sphere. The pane is `layout: "3d-only"`, so **`dotRadiusPx` is inert
there today**. Measured, not inferred:

```
dotRadiusPx 5  -> 209 px changed, extent [21,18]
dotRadiusPx 15 -> 209 px changed, extent [21,18]      (identical)
sphere radiusMm 4  -> 209 px                          (identical to both dots)
sphere radiusMm 12 -> 1835 px                         (radiusMm IS what drives size)
```

This is **not** faked around. The host sends the correct payload (`shape: "dot"`,
`dotRadiusPx: 5`), the layer keeps `radiusMm: 4` so nothing regresses visually, and
`embed-electrodes.spec.ts`'s third test pins the defect so it fails the day TX's fix lands. Every
other part of B1–B4 — colour as the whole state signal, per-channel hues, selected-only names, no
ring — does hold on this bundle and is measured below.

**Hover is omitted, deliberately.** The embed's only hover is `hoverAtScreen`, which sets a *world*
cursor and emits a `hover` event carrying a position; there is no per-point hover state and no
`stateColors.hover`. B2's "hover = same hue, lighter" is therefore not expressible against 0.4.0
and is not implemented. Ask for TX below.

## 3. Gate evidence — commands and real output

```
$ cd desktop && pnpm run typecheck
  clean apart from tests/unit/tetravox-card.test.tsx (2 × TS2741 `auto_update` missing) — lane AU's
  in-flight contract change, none in this lane's files.

$ pnpm run lint
  ✖ 4 problems (1 error, 3 warnings)
  the 1 error is tests/e2e/settings.spec.ts:140 'card' assigned but never used — lane AU's file.
  0 problems in this lane's files.

$ pnpm run test
  Test Files  2 failed | 79 passed (81)
       Tests  8 failed | 915 passed (923)
  all 8 failures are tetravox-card.test.tsx (7) and settings-warm-cache.test.tsx (1) — lane AU.
  This lane's: scene-pane-embed.test.ts 13 passed, scene-pane-legend.test.tsx 4 passed.
```

### Mock e2e (offscreen, fake embed)

```
$ TIT_E2E_OFFSCREEN=1 npx playwright test tests/e2e/scene-pane.spec.ts --reporter=list
  ✓ 1 mounts the embedded Tetravox scene and exposes form-owned state (29ms)
  ✓ 2 a protocol-2 point pick starts a montage draft in the form (72ms)
  ✓ 3 surface opacity reaches the live layers and survives other workflow tabs (234ms)
  ✓ 4 a renderer failure stays readable until explicit retry (164ms)
  ✓ 5 the pane never sends a point tool or a point selection — there is no selection ring (3ms)
  ✓ 6 a pick on an idle dot fills the active slot and repaints exactly that dot in the pair's colour (69ms)
  ✓ 7 a pick on a selected dot removes it and puts the grey back (42ms)
  ✓ 8 two pairs are two hues, and a legend chip decides which pair the next click fills (170ms)
  8 passed (6.2s)

$ TIT_E2E_OFFSCREEN=1 npx playwright test tests/e2e/guide.spec.ts tests/e2e/scene-errors.spec.ts \
    tests/e2e/scene-tabs.spec.ts tests/e2e/scene-rendering.spec.ts --reporter=list
  10 passed, 2 skipped (26.6s)
```

`tests/e2e/simulator.spec.ts` fails at `_subjects.ts:110` on `subjects-select-all-button`, a
testid that existed in **no** source file at the time — lane SG's `SelectionList` mid-flight, not
this lane's.

**Late cross-lane regression, recorded because it changes the numbers above.** At 22:31 the runs
above no longer reproduce: `scene-pane.spec.ts` test 2 and `guide.spec.ts` test 5 — both
*pre-existing* tests this lane did not write, both green against this lane's code at 22:20 —
now time out on `.electrode-pair-row … element(s) not found`, with the failure snapshot showing
the **Subjects disclosure open** (`Filter subjects`, `Done [expanded]`) where the montage editor
should be. `src/renderer/pages/_shared/subjects/SubjectsField.tsx` was rewritten at 22:17 by lane
SG and rebuilt into the shared `out/` between the two runs. The four tests this lane added
(5–8) are unaffected in the sense that they run after the same fixture, so they are blocked by the
same serial failure rather than failing on their own account; the green run at 22:20 is the honest
record of them, and they should be re-run once SG's subjects work settles. Nothing here is in this
lane's ownership.

### Real e2e (real embed, real guide surface, real electrode positions)

```
$ TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<container TIT_SERVER_TOKEN> \
  TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
  tests/e2e/real/embed-electrodes.spec.ts --reporter=list

  ✓ 1 an idle electrode is grey, and toggling it to selected repaints THAT marker in its channel's colour (792ms)
  ✓ 2 selecting a dot adds NO ring: the changed pixels are one solid disc and nothing else (669ms)
  ✓ 3 MEASUREMENT: embed 0.4.0 ignores `shape: "dot"` in the 3-D view — the dot pass is 2-D only (2.4s)
  3 passed (8.9s)
  e2e-quiet-check: PASS — no new Electron/Chromium window reached the screen.
```

Pixels, at camera preset `A`, `Fpz` (the near pole), 640×480 screenshot, guide skin opaque:

| state | screenshot colour at the marker centroid | host sent | Δ |
|---|---|---|---|
| idle | `148,155,167` | `158,166,179` | 12 |
| selected, pair 1 | `0,106,166` | `0,114,178` (#0072B2) | 12 |
| selected, pair 2 | `215,149,0` | `230,159,0` (#E69F00) | 15 |

The offset is a **constant** 0.935 factor in every channel of every probe — the layer's ambient
lighting term, not a colour anyone chose — which is where the spec's tolerance of 20 comes from
(a measured number, and still four times smaller than the ~90 that separates any two channel hues).
The centroid is identical across all three states: the state changed the hue and nothing else.

**No ring**, self-calibrating rather than assuming a device pixel ratio: the radial profile of the
changed pixels from the centroid is

```
idle     [1,8,12,16,32,25,31,22,21,21,10,7,3,0,0,0,…]
selected [1,8,12,16,32,25,31,22,21,21,10,7,3,0,0,0,…]   (identical)
```

— one solid disc that reaches zero at r = 13 and stays zero out to 60 px. A `setPointSelection`
ring is by construction a non-zero band *after* a zero one; there is none, in either state, and
the selected marker's bounding box is byte-identical to the idle one.

## 4. What lane SG's pair editor must expose

The pairs model itself needs **no change** — `Pair = [string, string]`, flat list, order = channel
index — and this lane consumes it exactly as it is. Two additions would close the loop:

1. **A shared active slot.** The pane owns a cursor (flattened `pair * 2 + col`) that decides which
   slot the next 3-D click fills, and the legend now moves it. The editor has its own focus and the
   two do not know about each other, so focusing pair 2 slot B in the form leaves the scene filling
   pair 1. The exact ask:
   ```ts
   activeSlot?: number;                          // flattened pair*2 + col
   onActiveSlotChange?: (slot: number) => void;  // fired on focus of either Select
   ```
   `ScenePane` would take the same two props and drop its internal `cursor` state. Until then the
   two cursors are independent, which is a real (small) inconsistency, not a design.
2. **The channel colour in the pair row.** `channelCss(i)` from
   `pages/_shared/scene/model` is the one source of the pair hues; a 9 px swatch on
   `.electrode-pair-index` makes "pair 2 is orange" true in the editor as well as in the legend and
   the scene. The legend's chips already read from that function, and a unit test pins the
   agreement (`scene-pane-legend.test.tsx`).

Note the palette **changed** in this lane (Okabe-Ito), so any colour SG hard-codes for a pair must
come from `channelCss`, not from a literal.

## 5. Ask for lane TX (the Tetravox side)

Three, in the order that matters:

1. **`shape: "dot"` in the 3-D pass.** Today `uDotPx` is set only in `POINTS_2D`; the 3-D
   instanced-sphere path needs the same screen-space branch. Without it, B1 is undeliverable in a
   `3d-only` pane. Measurement in §2 M3.
2. **A per-point dot radius.** `p1(layer)` reads the layer only; the host already sends
   `point.radiusPx` for the active channel (B1's "7 when active"), and it is inert.
3. **A per-point hover state** — either a `pointHover` event carrying a `pointId`, or a
   `stateColors.hover` applied by the engine. B2's hover half is not implementable without one.

Also worth stating upstream: `stateColors.idle` is unreachable (§2 M1). Either make it reachable or
delete it from the schema; as it stands it is a field that silently does nothing.

## 6. Proposed record entries (for the consolidation lane)

**`desktop/DESIGN.md` §9/§10 — add:**
> In the montage scene pane, an electrode's **colour is its whole state**: neutral grey when it is
> in no channel, 35 % grey when it is unusable, and its channel's hue when it is placed. No ring,
> no outline, no second glyph — the pane never sends `setPointTool` or `setPointSelection`, which
> are the messages that draw one. Names are shown for placed electrodes only. The channel hues are
> Okabe-Ito and are the same colours the pair editor and the channel legend use, so "pair 2 is
> orange" means one thing everywhere.

**`docs/DECISIONS.md`:**
> **2026-09-05 — the run-page scene marks electrodes by colour, and the host writes every colour
> itself.** The embed's selection ring was unreadable on a dense EEG net and could not say *which*
> channel a marker belonged to. Selection is now a per-point colour in a whole-layer `setPoints`
> replacement driven by the form. Every point carries an explicit `color`, including idle ones,
> because embed 0.4.0's normaliser returns an `idle` point untouched and never consults
> `stateColors.idle`. The channel palette is Okabe-Ito, so a four-pair mTI montage stays readable
> under the common colour-vision deficiencies.

> **2026-09-05 — `shape: "dot"` is sent but not yet honoured in 3-D, and that is recorded as a
> measurement rather than worked around.** Embed 0.4.0 sets its dot uniform only in the 2-D slice
> pass, so a `3d-only` pane still draws millimetre spheres. The host sends the correct payload, the
> layer keeps `radiusMm: 4` so nothing regresses, and `tests/e2e/real/embed-electrodes.spec.ts`
> pins the defect so it fails when the upstream fix lands.

**`docs/ARCHITECTURE.md` — contract amendment (additive, embed protocol 2):**
> `EmbedPointsLayer` gains `dotRadiusPx` and `labelColorSource`; `EmbedPoint` gains `radiusPx`.
> A point's own `color` takes precedence over `stateColors`, and a point whose `state` is `idle`
> is never state-coloured at all — a host that wants per-point colour must set it on every point.
> A point with no `name` draws no label, which is how "labels for the selection only" is expressed.

**`docs/ROADMAP.md`:** *B1–B5 (electrode dots, colour-as-state, channel legend, select/deselect
tests) — done except B1's dot shape, which is blocked on the Tetravox 3-D dot pass (lane TX).*

## 7. Open items

- **Two cursors** until SG adds `activeSlot` (§4.1).
- **`SceneGesture` still contains `"sphere"`** and `buildPaneViewSpec` still branches on it for the
  scalp opacity and the sphere point shape; the pane never produces it (lane GD's open item, unchanged).
- **`ACTIVE_DOT_RADIUS_PX` is inert** in 0.4.0 (§5.2). Asserted in the unit test and in the mock
  e2e so it cannot drift, and honestly labelled everywhere it appears.
- **The fake embed still implements `setPointSelection`.** Left in place: it is a real protocol
  message and the fixture should model the protocol, not this lane's usage. What is asserted is
  that the *pane* never sends it.
- The `data-host-messages` record is cumulative for the fixture's lifetime, which is what makes
  "never sent" checkable; it is stripped from nothing because the fake embed ships only in tests.

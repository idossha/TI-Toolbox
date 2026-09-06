# Lane N1 — the EEG net looked wrong because the head did not hide it (2026-09-04)

Maintainer's report, from the Simulator's montage pane: *"the EEG net visualisation looks wrong;
the electrode positions look wrong"*.

Two defects, both about what is on screen and neither about the data. The data was cleared before
this lane started: `GET /api/scene/electrodes?subject=ernie&net=EEG10-10_UI_Jurak_2007.csv` returns
75 of 75 electrodes byte-identical to the source CSV, Fp1 is left (x = −26.08) and Fp2 right
(x = +29.62), and lane SCA measured every electrode of every net within **1.81 mm** of the served
skin. The net the pane requests is the net the montage editor resolved.

Files: `desktop/src/renderer/scene/{glScene.ts,camera.ts,SceneCanvas.tsx,scene.css}`,
`desktop/src/renderer/pages/_shared/scene/ScenePane.tsx`, and their tests
(`desktop/tests/unit/scene-orientation.test.ts` new, `desktop/tests/unit/scene-framing.test.ts`,
`desktop/tests/e2e/scene.spec.ts`, `desktop/tests/e2e/real/{_scene.ts,scene-simulator.spec.ts}`).

---

## 1. Defect A — every electrode was painted over the head, front and back

### 1.1 Cause

`glScene.ts::render` drew, in this order:

1. **markers**, `depthMask(true)`, opaque;
2. back faces of every surface, `depthMask(false)`;
3. front faces of every surface, `depthMask(false)`.

There was no depth pre-pass anywhere in the file. The markers therefore met an **empty** depth
buffer and every one of them was rasterised at full opacity; the surfaces that followed wrote no
depth of their own, so nothing could ever hide a marker. The only thing a surface in front of a
marker could do was blend over it at its own alpha (0.09–0.22 per layer), which left ~50–80 % of the
marker still showing. From any angle the user saw all 75 electrodes of a net at once, the far
hemisphere superimposed on the near one — which is exactly what "the positions look wrong" looks
like when the positions are right.

The header comment stated the premise out loud: *"They are the thing being chosen, so they are never
hidden by anatomy."* That premise is correct for a cursor and wrong for an electrode; §3 keeps both.

### 1.2 The reproduction, before the fix

`desktop/tests/e2e/scene.spec.ts` → **"an electrode on the far side of the head is hidden by the
scalp"**, offscreen, `--project=default`, gallery fixture (an 78×98×88 mm skin ellipsoid, a
64×82×70 mm grey matter, 36 markers on 1.03× the skin), front preset, 880×420 pane.

The expectation is analytic: for each marker, the ray from the eye is intersected with the skin
ellipsoid in closed form (`skinEntry`, the same unit-sphere quadratic the file's region helper
uses), and `behindMm = |marker − eye| − t_entry`. The observation is a **pixel read back from the
drawing buffer**, and the discriminator needs no colour model at all: the same frame is rendered
twice, once with the marker pass suppressed (`GlScene.samplePixels(..., {markers:false})`), and a
marker is "painted at this pixel" exactly when the two frames differ there. The surfaces are
identical in both, so the difference is 0 wherever no marker fragment won.

```
SCENE-OCCLUSION hidden=12 drawn=12 maxDelta=157 | control near=6 drawn=6 minDelta=172
  Error: marker 7 is 112 mm behind the scalp at (533, 87) and must be hidden by it
  expect(received).toBe(expected)   Expected: 0   Received: 154
```

**12 of 12** electrodes on the far hemisphere were drawn, 112 to 190 mm behind the scalp their own
ray crossed first, contributing up to **157 of 255** per channel through two translucent shells. The
control in the same test — 6 near-side electrodes, all drawn, minimum delta 172 — is what stops the
assertion passing because the sampler reads nothing.

The pick half, **"what the eye can no longer see, the cursor can no longer hit"**, failed the same
way: a click at the projected position of the most deeply hidden marker selected it.

```
  Array []   ->   Array [ 22 ]
  Timeout 5000ms exceeded while waiting on the predicate
```

**The defect is still measurable after the fix, on the fixed build**, which is better than a number
in a note about a build that no longer exists. Occlusion is a switch (§1.4), so both tests take the
same three points a third time with it off — the draw order the renderer had until today — and
assert that every one of those electrodes is painted again. On the gallery fixture that is **12 of
12 at max Δ 186/255**; on ernie's own scalp, **9 of 9 at max Δ 181**. The fix and the defect are one
`expect` apart.

### 1.3 The fix

`render` is now, and the module header says why in full:

1. back faces, outermost first, depth test on, **depth write off**;
2. front faces, innermost first, depth test on, **depth write off**;
3. a **depth-only pre-pass** of every surface, both faces, `colorMask(false…)` + `depthMask(true)`;
4. **markers**, depth-tested against that, drawn last and over the composited head.

**Why the pre-pass is third and not first**, which was the question worth answering: a depth buffer
holding the nearest surface rejects the back faces and the whole inner shell, and the grey matter
vanishes inside the head — the bug the back-to-front ordering exists to prevent. Composing the head
against an empty depth buffer and only then filling it keeps both properties at once: the shells
still show through each other, and a marker behind the scalp is behind the scalp. The cost is one
extra geometry pass (draw calls per frame **5 → 7**), whose colour writes are off.

**Why the pre-pass is biased by 4 mm** (`MARKER_OCCLUSION_BIAS_MM`). Without a bias an electrode has
to be *strictly* in front of the scalp to survive, and it is not: the served skin is a simplified
surface, so an electrode projected onto the original mesh lands within **1.81 mm** of it on either
side (lane SCA). At bias 0 roughly half of every net would be culled by a fraction of a millimetre
of decimation error — a worse defect than the one being fixed. 4 mm is more than twice the worst
measured error and two orders of magnitude below the ~190 mm an electrode on the far hemisphere sits
behind the near scalp, so it separates "on the surface" from "behind the head" with a wide margin at
both ends.

It is applied as a **translation along the view axis** — one entry of the view matrix,
`view[14] − 4` — rather than as `gl.polygonOffset`. Rejected alternative: `polygonOffset`'s units are
multiples of the smallest resolvable depth difference, which on a 24-bit buffer with `near =
0.01 · distance` is a different number of millimetres at every depth and at every zoom level, and a
tolerance nobody can state in mm is a tolerance nobody can check against the 1.81 mm it has to
clear.

`drawPickSequence` runs the same pre-pass before the marker pass, so the pick occludes exactly as
the eye does. Its old `clear(DEPTH)` — "what the eye can see, the cursor can hit" — was correct under
the old premise and is now the opposite of the rule; the rule and its comment moved together.

One latent defect was found and fixed alongside, because the change makes it reachable: `pick()`
never cleared the pick framebuffer's **colour**, only its depth (and only inside the marker branch).
It got away with it while every pick drew something into its 3×3 scissor box. A pick can now
legitimately draw nothing at all — an occluded marker with no selectable region — and would then
read back the id an earlier pick left in the same texels, i.e. "you clicked the electrode you clicked
last time it was in front of the head". `pick()` now clears both buffers.

### 1.4 A marker that is not an electrode

Applying occlusion unconditionally would have introduced a new defect in the same commit. In
`sphere` gesture the Analyzer and Optimizer draw exactly **one** marker: the sphere centre, which is
a point inside the brain by construction and would be hidden by everything. So occlusion is a
property of what the markers *mean*, not of the renderer: `GlScene.setMarkerOcclusion`, surfaced as
`<SceneCanvas markersOccluded>` (default `true`), and `ScenePane` passes `gesture !== "sphere"`. The
two kinds are never mixed in one scene — the pane draws either a net or a single sphere centre.

---

## 2. Defect B — the Top view was upside down, and the pane never said which way round it was

Honest answer to the second half of the sentence: the projection is **not** mirrored, the presets are
**not** swapped, and the electrode positions are exactly where the data puts them — except in one
view.

### 2.1 The convention this renderer uses

Derived from `cameraBasis`, the same function the view matrix comes from (`screenAnatomy` in
`camera.ts`), for each preset:

| Preset | screen right is | screen up is | facing |
|---|---|---|---|
| `front` | **the subject's left** | superior | anterior |
| `left` | posterior | superior | the subject's left |
| `right` | anterior | superior | the subject's right |
| `top` | the subject's right | anterior | superior |
| `reset` (3/4) | the subject's left | superior | anterior |

**The front view faces the subject**: their left hand is on the viewer's right, the way a photograph
of a person works and the mirror image of a radiological axial slice. The top view is the other way
round, because looking down at a vertex from behind it is a genuinely different viewpoint. Both are
correct, which is precisely why the pane now states which one it is showing.

### 2.2 What was wrong

`PRESET_ANGLES.top` was `{ yaw: 0, pitch: PITCH_LIMIT }`. At a pitch of 89.85° the yaw no longer
picks a side of the head — it only decides how the head is *rotated* on screen. Yaw 0 puts the eye a
fraction of a degree **anterior** of the vertex, `up` collapses onto −Y, and the axial view comes out
with the nose at the **bottom**: measured on ernie's 10-20 net at 400×320, Fp1/Fp2 at y = 289 and
O1/O2 at y = 38–39. Upside down against every convention a neuroimaging user has, and one of the
things that reads as "the electrode positions look wrong".

`top` is now `{ yaw: Math.PI, pitch: PITCH_LIMIT }` — the eye a fraction of a degree posterior — so
`up` is +Y and `right` is +X: nose at the top, subject's left on the viewer's left.

It costs a little framing. From directly above there is nothing for the `focus_bbox` (neck-trimmed)
framing to win, and the near-tie lands on the other side of zero: measured on
`tests/fixtures/scene/ernie-*-support-points.json`, the focus framing gained **+0.0037 / +0.0051 /
+0.0082** of the pane at 1192×544 / 1280×800 / 420×420 under yaw 0 and **loses 0.0040 / 0.0055 /
0.0089** under yaw π. Under 1 % of the pane, for an axial view that is the right way up.
`scene-framing.test.ts`'s slack for that one view moved from 0.002 to 0.010, with the measurement
written next to it; the presets where the neck actually costs something are still asserted with real
gains in the test below it.

### 2.3 The pane now says it

`.scene-orientation`, top-left of the canvas opposite the preset buttons, `data-testid=
"scene-orientation"`, derived from the live camera so it cannot drift from the projection and so it
keeps up with a free orbit rather than with the last button pressed:

```
Anterior view · right = subject's L      (front, and the default 3/4 reset)
Left view · right = posterior            (left)
Superior view · right = subject's R      (top)
Posterior view · right = subject's R     (orbited 180° from the front)
```

with the long form in its `title`: *"Looking at anterior of the head. The right of the screen is the
subject's left; the top of the screen is superior."*

### 2.4 The test

`desktop/tests/unit/scene-orientation.test.ts`, **20 tests**, pure arithmetic, two landmark sets:

- **axis landmarks** — points defined by nothing but their anatomical role, so the expectation
  cannot be wrong and pins the convention itself;
- **ernie's 10-20 net** as the container serves it (Fp1, Fp2, Fz, T7, T8, O1, O2 — this net has no
  Oz, so O1/O2 are its posterior pair). Nothing here is a recorded expectation: the coordinates are
  input, and the first test checks that each name's coordinates match the anatomy its name asserts
  (Fp1 left, T8 the rightmost, Fz the most superior) before any of them is projected.

For every preset it asserts the screen side of the landmarks (Fp1 right of Fp2 in the front view, T7
the rightmost, Fz the topmost, O1 further from the eye than Fp1, …) and the caption string. Checked
against the defect: restoring `top: { yaw: 0 }` fails **4 of the 20**.

The same assertion runs on real anatomy in `tests/e2e/real/scene-simulator.spec.ts`, where the
caption on screen is read back and the served Fp1/Fp2, T7/T8, O1/O2 pairs have to fall on the side
the caption claims.

---

## 3. Numbers

| | before | after |
|---|---|---|
| Far-side electrodes painted over the head — gallery fixture, front preset, 12 tested | **12 / 12**, max Δ 157/255 per channel | **0 / 12**, Δ exactly **0**; the same 12 with occlusion switched off: **12 / 12**, max Δ 186 |
| Near-side electrodes painted — the control, 6 tested | 6 / 6, min Δ 172 | 6 / 6 |
| Click on the most deeply hidden electrode | selected marker 22 | selects nothing (the pixel resolves to the scalp region the user actually clicked, which montage mode ignores) |
| Electrodes hidden by ernie's own scalp — `EEG10-20_Okamoto_2004.csv`, the run pane's own camera | with occlusion switched off, **9 / 9** painted, max Δ 181 | **0 / 9** drawn: F8 @ 62 mm, C4 @ 78, T8 @ 147, Pz @ 66, P3 @ 58, P4 @ 141, P8 @ 179, O1 @ 108, O2 @ 167 behind the scalp |
| Electrodes on the near scalp — the control, same run | — | **9 / 9** drawn: Fp1, Fp2, Fz, F3, F4, F7, C3, T7, P7 |
| Draw calls per frame | 5 | 7 |
| Orbiting 156 096 triangles at 1280×800 @ dpr 2 (S8 wants ≥ 30) | 60 fps | **60.0 fps**, 0.100 ms/frame |
| Pick world-point error, FIX-A's own measurement | 1.086 mm | **1.086 mm** (unchanged) |
| Top preset: Fp1/Fp2 vs O1/O2 screen y (400×320) | 289 vs 38 — nose at the bottom | nose at the top |
| The pane's stated convention | nothing on screen | `Anterior view · right = subject's L`, with T7 (subject's left) at x = 302 and T8 at x = 90 on a 400 px pane |
| Orientation assertions | none | 20 unit tests + the real-anatomy half of the Simulator spec |

---

## 4. Gates

| Gate | Result |
|---|---|
| host `python3 -m pytest -q` | **3587 passed**, 32 skipped, 21 deselected, 48.7 s |
| desktop `npm run typecheck` | clean |
| desktop `npm run lint` | **0 errors**, 3 pre-existing warnings |
| desktop `npx vitest run` | **955 passed**, 78 files (909 before; this lane adds 20, the rest is another lane's) |
| `--project=default` `scene.spec.ts` + `scene-tabs.spec.ts`, offscreen | **14 passed**, `e2e-quiet-check: PASS`, no window reached the screen |
| `--project=real` `scene-{simulator,optimizer,analyzer}.spec.ts` | **13 passed, 1 failed** — the failure is the Simulator's `firstScreenControls` gate, proved pre-existing in §5 |
| `npm run build` (plain, what the container serves) | rebuilt last: `index-CN3gV2-0.js`, **0** `__scene` strings, **0** "Design gallery" strings, byte-identical to the plain build another lane made from the same source at 13:42 |
| container `GET /api/health` after every save | 200 (nothing under `tit/` was touched by this lane) |

Every e2e run went through `TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh`, and every one of them
reported `no new Electron/Chromium window reached the screen`.

---

## 5. Open, and not this lane's

**The Simulator's `firstScreenControls` gate fails once a montage draft is open, and it is not this
lane.** `tests/e2e/real/scene-simulator.spec.ts`'s last test asserts `hidden: []` at 1280×800; with
a draft open it reports 21 Tier-1 controls with **`["Cancel", "Save montage"]`** below the fold. Run
alone (fresh app, no draft) the same test passes at **13/13**, which is the number lane SCC and the
critic recorded — so what earlier lanes measured was the no-draft state.

Proved not to be lane N1's, by running the spec with the new N1 test **excluded**, i.e. exactly the
pre-N1 sequence: it fails identically (`Expected: [] / Received: ["Cancel", "Save montage"]`). N1
touches the renderer, the pane's caption and `_scene.ts`'s marker chooser; none of them changes the
work pane's DOM. The finding is real and belongs to whoever owns `pages/simulator/**` and the action
bar: **a montage draft's own two actions are below the first screen at 1280×800.**

- `desktop/out/` is a shared, racy resource: another lane rebuilt it **mid-run** during this lane's
  first full `--project=default` pass (9 of 12 specs failed with "Design gallery heading not found",
  the documented symptom of a build without `VITE_INCLUDE_GALLERY`). Nothing is wrong with either
  lane; there is one `out/` and two lanes that need different flags in it. A `--project=default`
  gallery run is only trustworthy if nobody builds during it.
- `tests/unit/tetravox-card.test.tsx` (another lane's file) was failing `tsc` twice while this lane
  ran — `TS2493: Tuple type '[]' of length '0' has no element at index '0'` — and was fixed by its
  owner both times. Not this lane's, and green at the end.

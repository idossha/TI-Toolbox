# Lane CL1 — the scene-side cleanup items

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Nothing committed, staged, stashed or pushed. Plan of record `dev/notes/v3-scene-ia-plan.md`;
items carried forward by `fix-a-notes.md` (§5.1, §5.2, §5.3, §5.4), `fix-b-notes.md` (O2, O3),
`fix-c-notes.md` (open issue 2) and `verify-notes.md`'s open-issues list.

Every Electron/Playwright run went through `TIT_E2E_OFFSCREEN=1` + `desktop/scripts/e2e-quiet-check.sh`;
every one reported **PASS — no new Electron/Chromium window reached the screen**. `/api/health`
answered **200** after every save under `tit/` and at the end. No container was restarted,
recreated or stopped; port 5173 untouched; `desktop/out/` left on a **plain** `npm run build`.

---

## Item 1 — the served grey-matter surface was wound inward

### Reproduction, before

Two measurements on the bytes the container actually served for `sub-ernie`, decoded from
`GET /api/scene/surface`, each computed by an expression written for the purpose:

| part | signed volume (divergence theorem) | triangles whose normal points away from the centroid | degenerate |
|---|---|---|---|
| `skin` | **+4 841 347.0 mm³** | 99.5 % | 0 |
| `gm` | **−1 316 328.7 mm³** | 30.9 % | 0 |

A negative enclosed volume is the whole finding: every grey-matter triangle wound inward.
Reproduced one level further up, inside the container, straight off `crop_mesh` before any
simplification — so it is the head mesh's own convention for tag 1002, not something the builder
did: `gm` source `−1 309 124.2 mm³`, outward fraction 32.6 %; `skin` source `+4 841 347.0`, 99.5 %.
(FIX-A's independent rasterised measurement — front-facing at **0.0 %** of sampled `gm` pixels
against 100.0 % for skin — is the same fact seen from the renderer.)

### Cause

`tit/scene/build.py::_read_surface` handed `crop_mesh`'s triangles straight through. Nothing in a
SimNIBS head mesh promises a consistent winding between tissue boundaries, and tag 1005 (skin) and
tag 1002 (grey matter) do not have one.

### What it broke, and what it did not

Not the pick — FIX-A fixed that properly, by drawing both faces, and that fix stays: a camera
inside the scalp, an open edge and a folded cortical sheet all present back faces as the nearest
thing under the cursor whatever the winding. What it did break is the renderer's **back-to-front
translucency order**: `glScene.ts` draws two translucent shells by culling `gl.FRONT` first and
`gl.BACK` second (decision B5), so for an inverted `gm` "back faces" *were* the near wall and the
cortex was composited near-over-far — the wrong order for alpha blending — plus anything that
trusted the served normals.

### The fix

`tit/scene/build.py`:

- `signed_volume(vertices, triangles)` — the divergence theorem, about the vertex centroid, with
  the reference-point caveat for open surfaces written into the docstring.
- `orient_outward(vertices, triangles) -> (triangles, flipped)` — flips the winding when the signed
  volume is negative. A flip permutes two indices, so no vertex moves and every per-vertex label,
  electrode alignment and cache property is untouched.
- `_read_surface` applies it, and the sidecar records `winding_flipped` and `signed_volume_mm3`
  of what is **published**, so the property is recorded rather than the intention, and a change of
  convention upstream becomes visible instead of being silently absorbed.

**Cache invalidation.** `cache.fingerprint` hashed only `(name, size, mtime_ns)` of the source
files, which cannot see a change in the code that read them — the mesh had not changed, so a
corrected build would never have been reached. `cache.fingerprint(sources, version="")` now takes a
salt, `build.BUILDER_VERSION = "2"` is it, and `build.surface_fingerprint` /
`build.labels_fingerprint` are the single definition both the builder and
`routes/scene.py` call (they were computing it separately, which is how a bump reaches one and not
the other). Labels are salted too: their positions are copied out of the `gm` payload, and their
sidecar's `aligned_to_fingerprint` would otherwise name an entry that no longer exists.

Proven both ways: an entry keyed by the old fingerprint is **not found** (so the build re-runs), and
`cache.publish`'s `prune_stale` **deletes** it — asserted in
`test_an_entry_an_older_builder_wrote_is_never_served_and_is_deleted`, and confirmed live: after the
rebuild `scene_cache/sub-ernie/` holds one entry per key and none of the three pre-change
fingerprints (`0c3f9503…`, `ed5f8d74…`, `97c8299e…`) survives.

### The tests, and the red

`tests/test_scene_orientation.py` (new, 10 cases). The criterion is independent of the renderer:
the signed volume a surface encloses, computed in the test by the **tetrahedron form**
`Σ a·(b×c)/6` — a different expression from `build.signed_volume`'s — plus, for the sphere fixture,
the fraction of normals pointing away from the centroid. Fixture orientation is established without
the code under test (a UV sphere's outward normal is radial; a 3 mm cube encloses 27 mm³).
`build_surfaces` is driven end to end through a fake `read_msh` over a synthetic head whose `gm` is
wound inward the way SimNIBS's really is.

Red, with `orient_outward` neutered to the pre-fix behaviour and the salt removed:

```
4 failed, 6 passed
E   AssertionError: gm encloses -267,007.7 mm3 -- wound inward
    assert -267007.7286025851 > 0
```

`tests/test_scene_realdata.py` (container-gated) gained
`test_both_served_surfaces_are_wound_outward`, on the real mesh. Its tolerance is measured, not
chosen: for an open surface "enclosed volume" depends on the reference point, so
`_reference_spread` evaluates the volume about four different references and the two expressions
must agree to within that spread.

```
[skin] encloses 4,841,347.0 mm3; sidecar says 4,845,375.7 (0.08 % apart, against a 1.31 %
       reference spread over 974 boundary edges); winding_flipped=False
[gm]   encloses 1,316,328.7 mm3; sidecar says 1,299,736.2 (1.26 % apart, against a 5.83 %
       reference spread over 3370 boundary edges); winding_flipped=True
```

### After, live

The maintainer's three subjects all rebuilt on the next request (new fingerprints
`82080c29ae183c3b` / `ca272a35bc29b1b5` / `fb430fa4fb69fbf2`), and the served bytes now measure:

| part | before | after |
|---|---|---|
| `gm` signed volume | **−1 316 328.7 mm³** | **+1 316 328.7 mm³** |
| `gm` outward normals | 30.9 % | **69.1 %** |
| `skin` | +4 841 347.0 mm³, 99.5 % | unchanged |

(69.1 % rather than 100 % is the cortex being folded — the radial test is only indicative on a
convoluted sheet. The signed volume is the criterion, and it is exactly negated.)

### The compensation removed

`tests/e2e/real/_scene.ts::chooseRegionPixel` filtered out back-facing candidates
(`if (area > 0) continue;`) for two reasons, both now gone: the pick pass culled back faces (FIX-A
fixed it) and `gm` was inverted (fixed here). The filter is deleted, so the rule is "the nearest
triangle containing the pixel", full stop — strictly stronger than the culled one. The renderer's
own `drawPickSequence` keeps drawing both faces, deliberately: FIX-A's argument for that does not
depend on the winding.

Re-run after removing it, live: `SCENE-OPT region-pick label=27 name=lh.rostralmiddlefrontal
pixel=(600.0,276.0) support=5`, with the renderer's own hover agreeing —
`hover={"kind":"region","index":27}`.

---

## Item 2 — the sphere gesture now uses the real pick point

### Before

`ScenePane.tsx` drew a clickable marker at every atlas region's centroid (snapped to a served
vertex) and a click moved the sphere centre to the nearest of them — lane SCC's C11, the closest the
old pick contract allowed. The specs then clicked a marker and asserted the form carried *that
marker's own coordinate*: the implementation agreeing with itself, which would pass just as well
with the camera, the projection and the pick all wrong together.

### A second defect found on the way

Wiring `onPickAt` was not enough, and the first live run said so: **every click in spherical mode
left the form's x/y/z at 0.** `glScene.ts::pick` read the depth only `if (options.depth === true &&
hit !== null)`, and `drawPickSequence` drew the surfaces only `if (options.regions)`. A sphere pane
is `MODE_RULES.inspect` — `regions: "none"` — so no surface was ever rasterised in the pick pass
and nothing was ever hit. `pick.world` was silently `null` in exactly the mode it was built for.

"Which region did I click" and "where did I click" are different questions. `drawPickSequence` now
draws the labelled surfaces when `options.regions || options.depth`, and the depth read runs
whenever `options.depth`, with background told from geometry by a clear-colour sentinel (white
decodes to a packed depth of 1 — the far plane, which no fragment of a framed scene reaches).
`ScenePick.world` now means one thing in every mode: the point on the anatomy under the cursor,
independent of what happens to be selectable.

### The fix

- `ScenePane.tsx`: `onPickAt={(pick) => { if (pick.world) onSphereChange(roundCoord(pick.world)); }}`,
  the sphere branch of `onPick` deleted, `regionCentroids` no longer called.
- `model.ts::sphereMarkers(centre)` — the centroid markers are gone; the sphere pane's only marker
  is the centre itself. The atlas is still shaded, which is what tells a user which gyrus they are
  about to click.
- The hint is now `"Click the cortex to move the sphere centre there."` — accurate, because the pick
  pass draws the surfaces that carry atlas labels, i.e. the grey matter. A point on the scalp would
  be a meaningless ROI centre.

### The assertion, against an independent intersection

`tests/e2e/real/_scene.ts` gained `surfaceRaster` / `chooseSurfacePixel` / `mergeRasters`. The
expectation is solved from `GET /api/scene/surface`'s triangles by **perspective-correct
interpolation** of the screen-space barycentric weights,
`world = Σ (wᵢ/zᵢ) Pᵢ / Σ (wᵢ/zᵢ)` — a different expression from the renderer's own (which packs a
window depth into RGBA8 and unprojects it). `chooseSurfacePixel` requires the hit to be stable
across four ±3 px probes and the incidence not to be grazing, both so the tolerance can be tight
and derived rather than chosen: `worldPerPx / cos(incidence) + 0.5 mm` (FIX-A's own derivation,
plus faceting and the form's 0.1 mm rounding).

| | before | after |
|---|---|---|
| Analyzer | form == the clicked centroid marker's own `world` (implementation) | `error=0.093 mm` against the independent ray/surface hit, tolerance 0.898 mm |
| Optimizer | same | `error=0.164 mm`, tolerance 1.046 mm |

```
SCENE-ANA sphere pixel=(600,276) expected=[-39.7, 74.0, 43.2] form=[-39.6, 74.0, 43.1]
          error=0.093mm tolerance=0.898mm cos=0.974 worldPerPx=0.388
SCENE-OPT sphere pixel=(168,264) expected=[-36.4, 77.4, 45.0] form=[-36.5, 77.5, 45.1]
          error=0.164mm tolerance=1.046mm cos=0.937 worldPerPx=0.512
```

The red for the wiring is the first live run of exactly these two cases before the `glScene.ts`
change: `expected: not 0 / Timeout 10000ms exceeded` (Optimizer — the field never moved) and
`Expected: <= 0.887 / Received: 47.62` (Analyzer — the page's default centre, untouched).

---

## Item 3 — framing: the manifest's bbox included the neck

### Where it belongs

**In the manifest.** Which millimetre is "the bottom of the head" is a question about anatomy, and
only the server has the mesh; a hint computed once at build time is also one answer every client
shares, and it keeps the renderer the dumb form control decision S1 says it is. FIX-A proposed
exactly this in §5.4.

### The fix

- `tit/scene/build.py::focus_bbox(vertices, floor_z)` — the part's box above `floor_z`, which is the
  lowest **grey-matter** vertex (`FOCUS_FLOOR_PART`), i.e. the bottom of the cerebellum and
  brainstem. Stored per part; `GET /api/scene/manifest` unions it into `focus_bbox` exactly as it
  unions `bbox`, and answers `null` when no part reports one (an older cache entry, or a 202) so the
  field is additive. Declared in `contracts/openapi.v1.yaml`; `schema.d.ts` regenerated.
- `SceneCanvas` gained `focus?: Bounds`. `sceneBounds` stays the whole scene (the zoom clamp and the
  near/far planes must still contain what is drawn); the camera's **target** and its **fit set** come
  from the focus box, and only its **z floor** filters the fit points. Cutting on the floor alone
  rather than on the whole box is deliberate: the box is tighter in y as well (a template's jaw), and
  filtering on that would push a nose off the edge of a lateral view. Markers are never filtered — an
  electrode below the floor keeps itself in frame.
- `ScenePane` forwards `manifest.focus_bbox` and decides nothing.

Live, on the maintainer's subjects: `ernie` z0 −128.861 → **−50.713**; `101` −150.519 → **−92.394**;
`MNI152` −150.135 → **−65.164**. On ernie that is **34.2 % of the framed height** that was neck
(228.8 mm → 150.7 mm), printed by `test_the_framing_box_drops_the_neck_and_keeps_the_head`.

### The numbers, at the narrow default pane and beyond

`tests/unit/scene-framing.test.ts`, on the real geometry
(`tests/fixtures/scene/ernie-focus-support-points.json`, new: the support set of the 93 985 served
vertices above the floor, reproducing that subset's support function to 1.04 mm). The head is the
same 357 points in both columns; only the camera changes. **`fill` is FIX-A's metric (the larger
axis ratio) and it is not enough on its own here** — on a portrait pane the head is already
width-constrained and the neck costs nothing along the axis `fill` reads — so the area fraction is
reported beside it.

| pane | preset | head area | fill |
|---|---|---|---|
| **348 × 544 (the narrow default)** | reset | **0.540 → 0.559** | 0.927 → 0.927 |
| | front | **0.522 → 0.556** | 0.913 → 0.913 |
| | left | **0.381 → 0.393** | 0.933 → 0.933 |
| | top | 0.690 → 0.689 | 0.914 → 0.914 |
| 1192 × 544 (expanded) | reset | 0.238 → 0.270 (**+13 %**) | 0.720 → **0.784** |
| | front | 0.184 → 0.266 (**+45 %**) | 0.630 → **0.794** |
| | left | 0.218 → 0.427 (**+96 %**) | 0.576 → **0.839** |
| | top | 0.280 → 0.284 | 0.882 → 0.888 |
| 1280 × 800 | left | 0.299 → 0.585 (**+96 %**) | 0.576 → **0.839** |
| 420 × 420 | front | 0.403 → 0.584 (**+45 %**) | 0.639 → **0.794** |

Two honest readings. **At the narrow default pane the gain is small** (head area 54.0 % → 55.9 %
in the reset view): 348 px of width is the binding constraint there and the neck adds none, so what
the focus box buys is composition — the camera's target rises 39 mm, from the centre of the
head-and-neck to the centre of the head. The gain is large where the *height* binds: the expanded
pane a user actually inspects in, and the lateral view most of all (+96 %). **The top view gains
nothing anywhere** and is asserted as such, because from directly above the neck is behind the head
and adds no silhouette — a physical fact, not slack.

No head point leaves the canvas at any of the 4 panes × 4 presets; neck points do, which is the
trade, asserted both ways.

Live, in `scene-analyzer.spec.ts`: `targetZ=24.6 focusZ=24.6 bboxZ=-14.5` — the camera aims at the
focus box, 39.1 mm above where it used to, while `stats.triangles` still equals the manifest's full
count (nothing stopped being drawn).

---

## Item 4 — hygiene

**a. The scene e2e hooks have their own build flag.** `SCENE_DEBUG` was
`import.meta.env.DEV || VITE_INCLUDE_GALLERY === "1"` — the design gallery's flag. It is now
`VITE_SCENE_HOOKS === "1"`. Verified in the built bundle: a `VITE_SCENE_HOOKS=1` build contains
`__scenePane` and **zero** occurrences of "Design gallery"; a plain `npm run build` contains none of
the five strings. `pree2e` sets both flags, `desktop/README.md` and the three real scene specs'
error messages updated, and `dev/notes/v3-pipelines/RUNBOOK.md`'s Level B recipe is now
`VITE_SCENE_HOOKS=1 npx electron-vite build` with a table saying which spec needs which flag
(`tests/e2e/scene.spec.ts` is the only one needing both — it mounts the scene inside the gallery).

**b. The mock server's six scene routes speak the product's sentences.** All six answered
`` `Unknown subject: ${subject}` ``, which the real server stopped sending in FIX-B's round. One
helper, `sceneSubjectProblem`, mirrors `tit/server/routes/scene.py::_scene_subject`'s two sentences
in its order, data-driven off `subjects.json`'s own `has_m2m` and with a natural-key id ordering to
match. The manifest also carries `focus_bbox` now, computed the same way, so the pane's framing
path is exercised offscreen too. The shipped fixtures give every subject a head model, so
`TIT_MOCK_SUBJECTS_NO_M2M` reaches the other branch without adding a fourth subject to a fixture
five other suites count.

Red, with the old wording restored:

```
× names the subjects the project does have, in natural order, on all six routes
  Expected: "This project has no subject 'zzz'. It has: 101, ernie, MNI152."
  Received: "Unknown subject: zzz"
× says what is missing and what to run, on all six routes
```

**c. `ScenePane.tsx`'s stale comment** quoted `"Unknown subject: 102"` as the server's answer. It
now quotes what the server says, and states the prop's remaining reason (the page already knows the
answer, so the round trip buys nothing) rather than the one that was fixed.

---

## Numbers

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3519 passed, 32 skipped, 21 deselected, 44.5 s** (3507/30 before; +12 tests) |
| Container `simnibs_python -m pytest -q tests/test_scene_{realdata,orientation,routes,build,cache}.py` | **123 passed** |
| `npm run typecheck` | clean, both projects |
| `npm run lint` | **0 errors**, 3 pre-existing warnings |
| `npx vitest run` | **909 passed / 75 files** |
| `npm run build` | clean; `out/` left **plain** (0 occurrences of all five hook/gallery strings) |
| `python3 dev/route_import_guard.py` | **17 route module(s) clean**, exit 0 |
| `dev/contracts_check.py contracts/openapi.v1.yaml <live dump>` | **47 problems / 140 warnings** — byte-identical to CR2's baseline; the `focus_bbox` addition introduced none |
| e2e `scene.spec.ts` + `gallery.spec.ts` (both flags) | **12 passed (1.1 m)**, quiet-check PASS — FIX-A's `SCENE-PICKAT` and all four `SCENE-FRAMING` lines unchanged |
| **real** `scene-simulator` + `scene-optimizer` + `scene-analyzer` (container, ernie + 101 + 102) | **13 passed (19.3 s)**, quiet-check PASS |
| Default e2e suite, whole | **135 passed, 1 skipped, 0 failed (8.7 m)**, quiet-check PASS |

Before → after, one line each:

| Item | Before | After |
|---|---|---|
| 1 `gm` winding | served surface encloses **−1 316 328.7 mm³**; 30.9 % of normals outward; cache could not see a builder change | **+1 316 328.7 mm³**, 69.1 %; `BUILDER_VERSION` salt rebuilt all three subjects and pruned every stale entry |
| 2 sphere gesture | centroid snap; every click in spherical mode left the form at 0 once the snap was removed | the clicked point, **0.093 / 0.164 mm** from an independently solved ray/surface hit |
| 3 framing | `bbox` z0 −128.9 mm; head **54.0 %** of the 348 × 544 pane, 23.8 % of 1192 × 544 | `focus_bbox` z0 −50.7 mm; **55.9 %** / **27.0 %** (and +96 % in the lateral view), no head point cropped |
| 4a hooks flag | `VITE_INCLUDE_GALLERY` gated both | `VITE_SCENE_HOOKS`; hooks-only build has zero gallery strings |
| 4b mock 404s | `Unknown subject: 102` on all six routes | the real server's two sentences, both branches tested |
| 4c stale comment | quoted the old sentence | quotes the current one |

### Files

| File | What changed |
|---|---|
| `tit/scene/build.py` | `BUILDER_VERSION`, `FOCUS_FLOOR_PART`, `signed_volume`, `orient_outward`, `focus_bbox`, `surface_fingerprint`, `labels_fingerprint`; `_read_surface` orients; `build_surfaces` extracts both parts before simplifying either and records `focus_bbox` / `winding_flipped` / `signed_volume_mm3` |
| `tit/scene/cache.py` | `fingerprint(sources, version="")` — the builder-version salt |
| `tit/server/routes/scene.py` | the shared fingerprint helpers; `focus_bbox` per part and unioned into the manifest |
| `contracts/openapi.v1.yaml`, `contracts/openapi.v1.json`, `desktop/src/renderer/api/schema.d.ts` | `focus_bbox` declared and regenerated |
| `desktop/src/renderer/scene/glScene.ts` | pick pass draws the surfaces when a depth is read, not only when a region is selectable; depth read no longer gated on the id pass; far-plane clear-colour sentinel |
| `desktop/src/renderer/scene/SceneCanvas.tsx` | `focus?: Bounds`, `framingBounds`, `fitPoints` filtered at the focus floor |
| `desktop/src/renderer/scene/types.ts` | `ScenePick.world` documented as independent of `target` |
| `desktop/src/renderer/pages/_shared/scene/ScenePane.tsx` | `onPickAt` writes the sphere centre; centroid snap removed; `focus` forwarded; hint and the stale comment rewritten |
| `desktop/src/renderer/pages/_shared/scene/model.ts` | `sphereMarkers(centre)` |
| `desktop/tests/mock-server/server.mjs` | `sceneSubjectProblem` + `naturalCompare` + `TIT_MOCK_SUBJECTS_NO_M2M`; `focus_bbox` in the manifest |
| `desktop/package.json`, `desktop/README.md`, `dev/notes/v3-pipelines/RUNBOOK.md` | the `VITE_SCENE_HOOKS` split |
| `tests/test_scene_orientation.py` | **new**, 10 cases |
| `tests/test_scene_realdata.py` | 2 cases added (winding, framing box) + `_reference_spread` |
| `tests/test_scene_routes.py` | 2 cases added; fixtures moved to the salted fingerprint |
| `desktop/tests/unit/scene-framing.test.ts` | 5 cases added (the neck) |
| `desktop/tests/unit/scene-pane-model.test.ts` | `sphereMarkers` case rewritten |
| `desktop/tests/mock-server/server.test.ts` | 4 cases added (the six routes' two sentences) |
| `desktop/tests/e2e/real/_scene.ts` | culling filter deleted; `surfaceRaster`, `chooseSurfacePixel`, `mergeRasters`, `Manifest.focus_bbox` |
| `desktop/tests/e2e/real/scene-{analyzer,optimizer}.spec.ts` | the two sphere cases rewritten against the independent hit; the live framing assertion |
| `desktop/tests/e2e/scene.spec.ts` | the flag it names |
| `desktop/tests/fixtures/scene/ernie-focus-support-points.json` | **new**, 357 points, provenance and error bound in the file |

---

## Open issues

1. **`useRunPaneController.ts` is still not deleted** — LAY, FIX-C, FIX-D and CR2 have each filed
   it; still imported by `pages/{optimizer,simulator}/index.tsx` and `pages/analyzer/AnalyzerPage.tsx`.
   Outside this lane's files.
2. **The sphere gesture is dead on a subject with no cortical atlas.** The pick pass draws only
   labelled surfaces, so with no atlas there is nothing to hit; the pane says
   "Loading the cortical surface…" rather than offering a gesture it cannot honour. Every real
   subject with a head model on Dataset 000 has DK40, so this is not reachable there. If it ever is,
   the choice is between a dead gesture and a centre on the scalp — and a scalp point is a
   meaningless ROI centre, so the current behaviour is the deliberate one. Worth revisiting only
   with a subject that proves otherwise.
3. **`focus_bbox` is a z floor, not a head.** It cuts at the lowest grey-matter vertex, which on
   `MNI152` also trims 7.2 mm of jaw out of the box's *y* extent. The renderer deliberately uses
   only the floor, so nothing is cropped laterally — but if a subject ever has anatomy worth framing
   below the cerebellum, the floor is the wrong rule and a real foramen-magnum landmark would be
   the right one.
4. **`dev/contracts_check.py` still reports 47 problems** on the live dump, all pre-existing and all
   "dump response has no declared schema" for routes that return plain dicts. Unchanged by this
   lane, and not this lane's to fix.

## State left behind

- `desktop/out/` is a **plain** `npm run build` (0 occurrences of `Design gallery`,
  `Every primitive`, `Mount scene`, `window.__scene`, `__scenePane` in any asset).
- Container `ti-toolbox-fad740e5-tit-1` never restarted, recreated or stopped; `/api/health` = 200
  after every save under `tit/` and at the end. Port 5173 untouched.
- Dataset 000: the scene cache for `ernie`, `101` and `MNI152` was rebuilt by the fingerprint bump
  (one entry per key; every pre-change entry pruned by `publish`). No job was submitted; the only
  writes were the cache rebuild the server does on demand.
- Nothing committed, staged, stashed or pushed.

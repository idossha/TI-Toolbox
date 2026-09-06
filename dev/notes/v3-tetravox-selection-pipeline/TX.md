# Lane TX — Tetravox embed on 0.3.11, release assets, ack, dot schema (2026-09-05)

Plan of record: `dev/notes/v3-tetravox-selection-pipeline-plan.md` §1-A A6.
All work is in the Tetravox repo. Nothing was merged, nothing was tagged, `main` was never checked out.

**PR: https://github.com/idossha/tetravox/pull/35** — `feat/embed-release` → `main`, open, do not merge.

Worktree: `/Users/idohaber/00_development/tetravox-wt-embed-release` (branch `feat/embed-release`,
pushed to `origin`).

## Commits

Rebased `feat/embed-viewport` (6 commits) onto `origin/main` (0.3.11), then four new commits on top:

| SHA | Commit |
|---|---|
| `ebd814b` | `fix(render): shape 'dot' is a screen-space disc in the 3-D pane too (§4.4, §7.2)` |
| `1a263da` | `ci(release): the embed ships a digest and a manifest beside its tarball` |
| `2526608` | `test(embed): pin the points-layer schema, and read the dot's pixels` |
| `a8293a9` | `fix(embed): the three point messages answer, so a host can await them` |
| `aba8d96` | `chore(embed): the embed carries the repository version, not one of its own` |
| `00e2f1d` | `feat(embed): §8 hosts can request only the viewport` (rebased) |
| `4553d42` | `feat(embed): host protocol 2 — a points layer, the point tool, pick and the camera` (rebased) |
| `6732606` | `chore(embed): carry packages/embed at the tree's 0.3.4` (rebased) |
| `b455bf6` | `build(embed): pack the bundle as a release asset, and document it` (rebased) |
| `1f84c01` | `feat(embed): host protocol v1, its schema, an example host and the suites` (rebased) |
| `8b3a653` | `feat(embed): a browser build of the renderer, driven over postMessage` (rebased) |

Rebase conflicts: `docs/DECISIONS.md` only, three times, all "both sides appended". Resolved by
keeping both, in date order. Lockfiles were not touched by the rebase (`pnpm-lock.yaml` gains only the
embed importer entry, as before); `pnpm install` re-ran clean.

## Gate — commands and real results

Run at `1a263da`, macOS arm64, `TETRAVOX_TESTDATA=/Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie`.

| Command | Result |
|---|---|
| `pnpm install` | ok, 1.7 s, lockfile unchanged |
| `pnpm wasm` | ok |
| `pnpm build` | exit 0 |
| `pnpm test` | exit 0 — **1917 passed, 83 skipped** (2000 collected), every cargo `test result: ok` |
| `pnpm lint` | prettier: all files clean. eslint: 0 errors, **3 warnings, all pre-existing on `main`** (unused `no-console` disables in `packages/engine/test/e2e/{derived,glyphs-real,mesh-real}.spec.ts`) |
| `pnpm --filter @tetravox/embed typecheck` | exit 0 |
| `pnpm --filter @tetravox/embed e2e` | exit 0 — **43 passed** in 43.8 s, both legs (`chromium-swiftshader` + `chromium-angle`), existing goldens unchanged |
| `node scripts/check-frozen-docs.mjs --base origin/main` | `ok` |
| `node --test scripts/check-frozen-docs.test.mjs` | 0 failures |
| `pnpm --filter @tetravox/embed build && pack:embed` | `packed packages/embed/dist-pkg/tetravox-embed-0.3.11.tgz` |
| sidecar commands, run by hand exactly as `release.yml` runs them | `.sha256` round-trips through `sha256sum -c` (`OK`); extracted manifest = `{"name":"@tetravox/embed","version":"0.3.11","protocol":2,"sha":"2526608…"}` |

Negative control: commenting out the three `this.ack(message)` call sites in `packages/embed/src/host.ts`
makes the new `ack` e2e **fail**. It tests the fix, not the harness.

## Follow-up round (`ebd814b`) — EL's three asks

**1. `shape: 'dot'` in the 3-D pane — fixed.** `uDotPx` was set only in the `POINTS_2D` branch and
hard-coded to 0 in the other, so a `3d-only` layout drew millimetre spheres whatever `shape` said
(EL's measurement: 5 and 15 → an identical 209 px marker). A slice pane converts pixels to millimetres
with `mmPerPx`; a 3-D pane under perspective has no such constant, so the dot's quad is now expanded
**in clip space** — `clip.xy += aCorner * (uDotPx * 2 / uViewportPx) * clip.w` — which is exactly
`uDotPx` device pixels at every depth and the orthographic case for free. `clip.z` is untouched, so
the disc is depth-tested at its own centre and an occluded electrode stays occluded, as asked. A 3-D
dot is **flat**, not a shaded hemisphere, because a shaded rim is a gradient across a colour that is
meant to be read as one state. `pointAtPane3D`'s grab radius follows at
`max(POINT_HIT_3D_PX, dotRadiusPx · uiScale)`, so the disc is the click target.

**2. `stateColors.idle` — fixed, not just documented.** `resolvePoint` returned early for an idle
point without consulting the palette. It now applies `stateColors.idle` when the point carries no
`color` of its own; a layer that names no `idle` still falls through to the layer's `color`, exactly
as before. **EL can stop writing an explicit `color` on every idle point** — from a 0.3.12 bundle.

**3. Per-point hover — added as `pointHover`, not as a colour.** `setHoverEvents { enabled }` (off by
default, like `setPickEvents`) turns on `pointHover { layerId, pointId }`, fired **on the edge** (when
the answer changes, not per move) and `null`/`null` when the pointer leaves every point. It reports
what `pointAtScreen` reports, so the highlighted point and the point a click selects cannot differ.
There is deliberately **no `stateColors.hover`**: the host owns colour, and the engine cannot know
that "lighter than this channel's hue" is what B2 meant. EL paints hover itself via `setPoints`.

**Not done: per-point `radiusPx`** (EL ask 2 — "7 px when active"). It needs a second per-instance
vertex attribute: `aRadius` carries millimetres and the 2-D branch culls off-slice points by them
*before* the dot branch overrides the radius, so overloading it would break the off-slice cull. That
is an instance-buffer change with its own tests, not a line in a shader. **EL's "7 when active" must
stay expressed as colour (or as a second layer) until this ships.** Recorded in DECISIONS as the next
ask.

### Evidence

Five new analytic e2e tests in the 3-D pane (`embed-points.spec.ts`), all checked **red** first by
forcing `uDotPx` to 0: measured diameter = `2 · dotRadiusPx · devicePixelRatio`; the sampled centre
pixel is the colour the host sent; `dotRadiusPx` 5 and 15 separate (EL's identical-209 measurement,
inverted); the width survives a doubled camera distance **while the same layer as a `sphere` shrinks**
(the control that stops a marker which ignores the camera because it ignores everything from passing);
and the non-background pixels around the disc are its own π·r², which a ring's ~280 extra pixels
cannot hide inside. One new golden, `embed-points-3d-dot.png`. Plus one hover e2e (off by default →
silence; edge-only; the hovered id equals the picked id) and two unit tests for `stateColors.idle`.

The test scene uses `dotRadiusPx: 20` against a `radiusMm: 4` sphere that measures ~18 px at that
camera. 10 px would have been indistinguishable from the bug — which is how the bug survived.

### Gate at `ebd814b`

| Command | Result |
|---|---|
| `pnpm run typecheck` (whole tree) | exit 0 |
| `pnpm build` | exit 0 |
| `pnpm test` | exit 0 — **1918 passed, 83 skipped** |
| `pnpm lint` | prettier clean; eslint 0 errors, same 3 pre-existing warnings |
| `pnpm --filter @tetravox/embed e2e` | exit 0 — **49 passed**, both legs, all three goldens |
| `node scripts/check-frozen-docs.mjs --base origin/main` | ok |

With `TETRAVOX_TESTDATA` exported, one **pre-existing** cargo real-data test fails on this machine:
`ernie_seeg_exceeds_the_twenty_one_bit_face_key`, `NotFound` on `m2m_ernie/ernie_seeg.msh` — that file
is not in the local dataset. Unrelated to this branch; the 1918 figure is the run without it.

### Protocol delta this round (for EL and AU)

Still protocol **2**, still `tvx: 1`, all additive:

* host → embed: `setHoverEvents` (appended to `HOST_MESSAGE_TYPES` after `setCamera`)
* embed → host: `pointHover` (appended to `EMBED_MESSAGE_TYPES` after `ack`)
* frozen `api.ts` gains `paneAt(x, y): PaneHit | null` (engine-internal for TI-Toolbox, but it is why
  `pointHover` needed no guessing about which pane the pointer is in)

## What the AU lane must expect

**Asset names on a Release `vX.Y.Z`** (three, all attached by `release.yml`'s `embed` job, and all
three required by `verify` before the draft is published):

```
tetravox-embed-<X.Y.Z>.tgz
tetravox-embed-<X.Y.Z>.tgz.sha256
tetravox-embed-<X.Y.Z>.manifest.json
```

* `<X.Y.Z>` is **the Tetravox release version, without a leading `v`** — the tag is `vX.Y.Z`, the
  assets are not. The embed no longer has a version of its own (it read `0.4.0`; that is gone), so
  `tetravox-embed-<v>.tgz` is always the embed built from Tetravox `<v>` and AU can derive all three
  names from the release's `tag_name` with one `lstrip('v')`.
* Download URL pattern (the GitHub Releases API gives it as `assets[].browser_download_url`):
  `https://github.com/idossha/tetravox/releases/download/v<X.Y.Z>/tetravox-embed-<X.Y.Z>.tgz`
* `.sha256` is **`sha256sum` format**: `<64 lowercase hex><two spaces><filename>\n`. Parse the first
  whitespace-separated token; do not assume a bare digest.
* `.manifest.json` is a byte-for-byte copy of the tarball's own `manifest.json`:
  `{"name": "@tetravox/embed", "version": "<X.Y.Z>", "protocol": <int>, "sha": "<git sha>"}`.
  **This is the file AU reads to decide compatibility without downloading the tarball** — `protocol`
  is the number to test against `SUPPORTED_PROTOCOL_MIN..MAX`. `verify` diffs it against the copy
  inside the tarball, so the two cannot disagree on a published release.
* Tarball layout is unchanged: one directory prefix `tetravox-embed-<X.Y.Z>/` containing
  `manifest.json`, `LICENSE`, `EMBED.md`, `protocol.schema.json`, `viewspec.schema.json`,
  `dist/index.html`, `dist/assets/*`.
* **`protocol` is 2** for anything cut from this branch onward. Nothing bumps it in this PR.
* **No release before this one carries the sidecars**, and none carries an embed asset at all. AU's
  lookup must treat a release with no `tetravox-embed-*` asset as "not incorporable", not as an error.
* There is **no `releases.json`** and there will not be one — see the DECISIONS entry. The GitHub
  Releases API is the index.

**Protocol change AU/EL should know about:** `setPointTool`, `setPointSelection` and `setPoints` now
reply `{ tvx: 1, type: 'ack', id, of }` when the request carried an `id`. `ack` is appended to
`EMBED_MESSAGE_TYPES` (after `camera`). A host that ignores it sees exactly what it saw before, and an
id-less send is still answered with nothing — so EL's fire-and-forget `setPoints` keeps working
unchanged, and the §3 risk "the host must not `await` `setPoints`" is lifted *for bundles built from
0.3.12 or later only*.

## Open items

1. **The release itself is the maintainer's.** The PR body carries the exact steps: merge, then on a
   clean `main` run `scripts/release.sh 0.3.12`, `git push origin main`, `git push origin v0.3.12`.
   The tag push is what builds and drafts the Release; `verify` publishes it.
2. **Until 0.3.12 exists, no release carries an embed asset**, so AU cannot integration-test against a
   real Tetravox release. Its loopback fake GitHub API must serve the three names above.
3. `CHANGELOG.md`'s `[Unreleased]` section now holds the embed entries (the rebase had put them under
   the already-published `[0.3.9]`). The maintainer may want to re-word them before cutting.
4. The dev container currently runs a runtime-installed **0.4.0** embed. Once 0.3.12 ships, that
   version string goes *backwards* numerically while the bundle goes forwards. AU should pin by
   protocol + install-time ordering (or clear the user root once), not by comparing version strings
   against the installed `0.4.0`.
5. Not attempted here: bumping `PROTOCOL_VERSION`. Everything in this PR is additive within protocol 2 —
   including `setHoverEvents` / `pointHover`, which were appended after the first pass and before
   protocol 2 was ever released.
6. **Per-point `radiusPx` is still inert** and is the next Tetravox ask (see the follow-up round).
   EL's B1 "7 px when hovered/active" cannot be expressed as a radius until it ships.
7. EL's own `embed-electrodes.spec.ts` third test pins the 3-D dot defect and is expected to **fail**
   once TI-Toolbox runs against a 0.3.12 bundle — that is what it was written to do, and EL should
   invert it then rather than deleting it.

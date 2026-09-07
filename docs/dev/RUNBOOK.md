# v3 pipelines runbook

> Live. This is the runbook for the two-level smoke harness, cited by
> `desktop/tests/e2e/batch.spec.ts` and `real/pipeline.spec.ts`. The program
> narrative is `docs/dev/HISTORY.md` § 2026-09-03 — Pipelines
> program; the numbers are in `docs/dev/BENCHMARKS.md`.

One page, commands only. Every command below was run for real this session (2026-09-04, lane
HX) against `ti-toolbox-fad740e5-tit-1` / `http://127.0.0.1:8765` unless a line says otherwise
and names whose run it cites instead. Full detail: `docs/dev/HISTORY.md` (2026-09-03) and `docs/dev/BENCHMARKS.md`.

## Dev mode

```bash
cp desktop/.env.dev.example desktop/.env.dev   # then set TIT_DEV_PROJECT_DIR
npm run dev                                    # container + Vite + Electron, no launcher, no token in hand
npm run dev:web                                # the same without Electron
npm run dev:down                               # stop + remove *this project's* container only
```
- `npm run dev` — proves the packaged app's own attach-or-start path reaches a real,
  populated `subjects` page offscreen. Not re-run here (D0 owns `scripts/dev.ts`); cited from
  D0's own verified run: `TIT_E2E_OFFSCREEN=1`, quiet-check **PASS**, `DATA-PAGE subjects`,
  `SUBJECT-ROWS 4`, `LAUNCHER-SHOWN false` (dev-mode contract; `docs/dev/HISTORY.md`, 2026-09-03).
- `npm run dev:web` — proves the Vite proxy serves the API with **no cookie, no header** from
  the client. Verified fresh here on a scratch project (`TIT_DEV_PROJECT_DIR=<scratch>
  TIT_DEV_PORT=8792`, never the shared project — a mismatched recreate mints a new token and
  kills every other lane's jobs): Vite auto-walked `5173`→`5174` (both busy: the maintainer's
  own `dev:web`) to **5175**; `curl http://127.0.0.1:5175/api/version` → `200`
  `{"tit_version":"2.4.0",...}`, empty cookie jar.
- `npm run dev:down` — proves it tears down only the container it was pointed at. Verified:
  `stopped and removed ti-toolbox-8bdd8023-tit-1`; `ti-toolbox-fad740e5-tit-1` (the shared one)
  untouched, confirmed with `docker ps -a --filter label=tit.stack=ti-toolbox-v3` before/after.

## Level A — API smoke (`tests/smoke/`)

```bash
dev/smoke.sh --list                       # every dev-stack container + its exact selector, runs nothing
dev/smoke.sh                              # the whole matrix, sequential, cleaned up
dev/smoke.sh <row-id-or-kind>...          # one row or kind (row id, or a kind -> every row of it)
dev/smoke.sh --keep <row>...              # keep everything created, for inspection
dev/smoke.sh --full <row>...              # run long kinds to completion instead of cancelling
```
- `--list` — proves discovery needs no `docker inspect` by hand. Verified: one container ->
  `ti-toolbox-fad740e5-tit-1  port=8765  project=/Users/idohaber/datasets/000`, exit 0; a
  throwaway second container -> both printed with `TIT_SMOKE_CONTAINER=<name> dev/smoke.sh`
  under each, exit 0 for `--list` / exit 2 for an unresolved ambiguous run (both cases run
  live this session, fixture container removed after).
- bare matrix run — `21 passed, 0 failed` in 280.7s, zero paths left on disk (run of record:
  `docs/dev/BENCHMARKS.md`).
- one row/kind, **replayed twice in a row** (the HX fix: a recorded payload's name-bearing
  field is rewritten to a fresh `smoke-<runid>` tag on every load, not just the session that
  recorded it) — proves a payload never skips its own second replay. Verified:
  `dev/smoke.sh analyzer_mesh analyzer_voxel stats_group nifti_average nilearn sim`, back to
  back, **7 passed / 7 passed**, every row `payload:` sourced both times, distinct job ids and
  distinct `smoke-200417-*` / `smoke-200517-*` output names, zero paths left on disk either
  time (`tests/smoke/artifacts/results-20260904T010508Z-200417.md` /
  `-20260904T010609Z-200517.md`; before the fix, pass 2 of these five `completed` rows skipped
  with "recorded payload targets existing output(s) ... refusing to overwrite").
- `--keep` — proves nothing is deleted. Verified: `dev/smoke.sh --keep pre_qsiprep` (chosen
  because it needed no wait behind another lane's job then running); its manifest recorded
  `"keep": true` and `"removed": false` on every claim.
- `--full` — not re-run to completion here (16+ minutes under emulation per kind, and another
  lane held the shared container at the time); last real completion measured on this container:
  `sim` 16 min, job `35ea5755` (`tests/smoke/matrix.py`'s own row note).
- **Ambiguous, no selector**: prints every container with its exact
  `TIT_SMOKE_CONTAINER=<name> dev/smoke.sh` line and exits **2** — verified live (above).

## Level B — real e2e (`desktop/tests/e2e/real/`)

```bash
cd desktop
npm run build   # only if out/ is stale for your change; racing another lane's build corrupts it
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=devtoken TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real tests/e2e/real/<spec>.spec.ts
```
Proves the page really submits what the runner needs, offscreen, against a live server.
Verified: `tests/e2e/real/nilearn-visuals.spec.ts` -> **1 passed (21.7s)**, quiet-check
**PASS** (no window reached the screen), job `6d4c9fba24a84b08` succeeded, 4 artifacts;
`out/` was already current from another lane, so `npm run build` was skipped this run.

**`--project=real`, not `--project real`.** Playwright 1.62.1's `--project` takes a variadic
list, so `--project real tests/e2e/real/x.spec.ts` swallows the spec path as a second
(nonexistent) project and fails `Project(s) "tests/e2e/real/x.spec.ts" not found` — hit running
this for real, 2026-09-04; the `=` form is the fix. Never `npm run e2e` for a real-server run:
its `pree2e` hook force-rebuilds `out/` and races any other lane's build.

**The three `scene-*` specs need a different build than every other spec here** (defect 3,
fix-round 2026-09-04, lane FIX-C — the critic ran the plain-build command above literally and
got 3 failed / 10 skipped, one per scene spec file:
`docs/dev/HISTORY.md`, 2026-09-04). `tests/e2e/real/scene-simulator.spec.ts`,
`scene-optimizer.spec.ts` and `scene-analyzer.spec.ts` read `window.__scene` /
`window.__scenePane` (`SCENE_DEBUG` in `src/renderer/scene/SceneCanvas.tsx`), which a *plain*
`npm run build` correctly strips — `import.meta.env.DEV` is false for every `electron-vite build`
regardless of `--mode` (see `desktop/README.md`'s "Design gallery" section) — so those three specs
need the build re-run with the scene-hooks flag first:
```bash
cd desktop
VITE_SCENE_HOOKS=1 npx electron-vite build
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=devtoken TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
  tests/e2e/real/scene-simulator.spec.ts tests/e2e/real/scene-optimizer.spec.ts tests/e2e/real/scene-analyzer.spec.ts
npm run build   # plain again before any other spec, or before leaving out/ for someone else —
                # the container serves out/renderer, and a hooks-flagged build is not what a
                # plain `npm run build`'s own claim ("a plain build ships no test hooks",
                # verified by grepping the built bundle for window.__scene / __scenePane) promises
```
**`VITE_SCENE_HOOKS=1` is the scene hooks' own flag** (lane CL1, 2026-09-04). It used to be
`VITE_INCLUDE_GALLERY=1` — the design gallery's flag, which gated the hooks too because nobody had
split them, and which cost three lanes time: a scene spec built with it dragged a whole `dev/`
route it never opens into the bundle, and a build *without* it failed with "Design gallery heading
not found" rather than anything about a missing hook (`docs/dev/HISTORY.md`, 2026-09-04, open
issue 2, `fix-a-notes.md` §5.5). The two are now independent:

| Spec | Build flags |
|---|---|
| `tests/e2e/real/scene-{simulator,optimizer,analyzer}.spec.ts` | `VITE_SCENE_HOOKS=1` |
| `tests/e2e/scene.spec.ts` (offscreen, mounts the gallery's scene page) | `VITE_INCLUDE_GALLERY=1 VITE_SCENE_HOOKS=1` |
| `tests/e2e/gallery.spec.ts` | `VITE_INCLUDE_GALLERY=1` |
| everything else | plain `npm run build` |

`npm run e2e`'s `pree2e` hook sets both, which is why the default suite works untouched — and is
still not what to use for a real-server run (it force-rebuilds `out/` and races other lanes).

## Restart rule (`tit/server/**`, `tit/jobs/**`, `tit/catalog.py`)

```bash
curl -s -H "Authorization: Bearer $TOKEN" $URL/api/jobs           # must show nothing running/queued
docker restart <container>                                       # only if the line above is empty
curl -s $URL/api/health                                           # poll until {"status":"ok"}
```
Proves nothing is killed by the restart. Verified live this session: the jobs check caught a
real running job (`source`, sub-101, another lane's) and correctly meant no restart was taken.
A plain `restart` keeps the same token (only a *recreate* mints a new one; S1/F0 measured
~2-5s back to healthy for a plain restart, this program's `s1-notes.md`/`f0-notes.md`).

## One-FEM-at-a-time rule (P7)

The harness enforces it itself, no separate command: any row with `behaviour == completed` or
`heavy == True` (`sim`, `flex`, `leadfield`, `source`, `blender`, charm, FastSurfer) blocks on
`GET /api/jobs` until nothing is `running`/`queued` before submitting. Verified live: while
another lane's `source` job was running, `dev/smoke.sh --keep pre_qsiprep` (refused-behaviour,
not heavy) ran immediately (6.1s, no wait) — a `completed`-behaviour row would have blocked
behind it instead.

## Where the results tables live

```bash
ls -t tests/smoke/artifacts/results-*.md | head -1    # newest matrix run's table (decision P8)
ls -t tests/smoke/artifacts/manifest-*.json | head -1  # its created-path manifest
```
The run of record for the whole matrix is the smoke-matrix table in
`docs/dev/BENCHMARKS.md`.

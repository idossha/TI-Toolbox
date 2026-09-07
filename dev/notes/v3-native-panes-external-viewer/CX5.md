# Lane CX5 — third consolidation: the reds, the rail's digits, records, gate

Branch `feature/v3-electron-gui`, worktree `.claude/worktrees/v3-electron-gui`, 2026-09-06 (night).
Plan of record `dev/notes/v3-program-history.md § 2026-09-06 (native panes, external viewer)`; lanes `{CX3,CX4,TR,PL,TI,VM,
VM2,OJ,NB,NR,VE,JB,IB}.md`. Every Playwright run was **offscreen and serial**, under
`/tmp/tit-e2e.lock`; `git stash` was not run in any form.

Twenty-nine commits landed tonight across ten lanes (§4). Five reds were reported at hand-off, and a
sixth was found by running the suite. Every one turned out to be a real defect rather than a
disagreement between lanes — which is the opposite of CX4's evening.

---

## 1. The reds, and what each one actually was

### (a) 18 `noUncheckedIndexedAccess` errors — a missing bounds check, not missing `!`

`labelFaces.ts` indexed `labels[indices[i]]` three times per triangle. Under
`noUncheckedIndexedAccess` both lookups are `T | undefined`, and the tempting fix is nine `!`s.

That would have been wrong, because the second lookup has a real failure mode: a corner index past
the end of `labels` yields `undefined` for two corners, and `la === lb` is then **true** — two
`undefined`s "agree", the function decides there is a majority, and it rotates a triangle on the
strength of a label that does not exist. The honest fix is the bounds check the type was asking
for: a triangle with any corner outside `labels` is left exactly as it came, which is the same
answer the function already gives a triple junction. The two test files use the suite's existing
`!` convention, which is fine — a fixture's own array literal is in scope three lines up.

`935f8d15`.

### (b) `retained-pages.test.tsx` — uPlot's `matchMedia` at module scope

Four units in this suite already stub `matchMedia`, and they get away with a stub in the body
because they `await import()` the module under test. This file imports `Shell` **statically**, so
uPlot (reached through the `ui` barrel) ran its module-scope `matchMedia()` before any line of the
body. `vi.hoisted` puts the same stub above the imports. `cb1a5600`.

### (c) The uncommitted `openapi.v1.json` fixture — the Subject Info removal, unstaged

Regenerated and compared structurally rather than by diff: paths identical to
`contracts/openapi.v1.json` in both directions, schema bodies differing only by the `x-tit-config`
merge, as designed. What the working copy dropped is exactly `1e03cae0`'s surface —
`/api/subjects/{id}/info`, `SubjectInfo`, `SubjectSimulationInfo`, `FileRef`, and two panel names in
the Settings description. `dev/contracts_check.py` was green before and after. `5cbf1f23`.

### (d) `smoke.spec.ts` "navigation outside the server origin is blocked" — a race, not the guard

The guard works: the URL after the blocked `app://evil/` navigation was the server origin, exactly
as asserted. What failed was the *other* half of the assertion, `hasTable: true`. The test waited
only for the URL before provoking the navigation, and the URL arrives long before Overview's first
fetch resolves — so on a busy machine the table had not painted when the 500 ms probe ran. The
precondition is now waited for. `67d08bb8`.

### (e) `real/scene-electrodes.spec.ts` — stale against the optimizer's jobs table

`getByRole("radiogroup", { name: "Method" })` no longer exists: a row *is* the method (`452`'s
"All three run pages carry a jobs table"), and the target is chosen inside the row's editor. The
spec follows the mock `scene-pane.spec.ts` pattern — assert the first row is already Flex, open its
editor, pick Cortical, close, and rely on the row staying active so the pane draws its atlas.
`e3ef8198`.

### (f) The rail's digits — asked for twice, and the second answer is better

Reported: Jobs lost ⌘9 when Notebooks made the rail ten workflow rows. The first instruction was to
move `notebooks` to the end of `NAV_ORDER` (`9ebcc8f5`), which buys Jobs its key back by taking one
from Notebooks and by putting the rail out of workflow order.

The maintainer's own answer is better and cost less code: **"start from 0 the rail digit and finish
at 9."** Ten digits, ten rows, counted from zero — every row has a key and `NAV_ORDER` keeps its
workflow order. Settings, which was only ever holding a digit because the count started at one, goes
back to ⌘, alone. `shortcutForSlot` is now `String(index)`. `3c772d5c`.

---

### (g) Two more, found by running the real suite rather than reported

* **`Fiducials.csv` was listed as an EEG net.** It holds only registration landmarks, so a row that
  picked it could never resolve an electrode and stayed unrunnable with nothing said. Found by the
  real `flex-result-selection` spec, which maps a run onto *every* net the subject has instead of
  one known-good one. `ff7acbe7`.
* **The net option's label lost its `.csv`.** `MontageManager` renders `netStem(n)` so a narrow
  column reads "BioSemi-128-A1"; every real spec still asked for the filename and timed out. The
  extension is now dropped in `_jobs.ts`'s `setJobNet`, once. `4ca1fad2`.

And one **left open**: since the grey matter became opaque, an idle electrode's worst contrast
against the composed scalp is **2/255** (median 35) over the 24 front-most electrodes of
ernie/GSN-HydroCel-185 — at that pixel the marker is invisible. The spec now measures its colour
claims where the difference can prove something and logs both numbers; the fix (a thin contour on
every marker, not only on the ones carrying a channel colour) is a design call, recorded in
DECISIONS rather than taken here.

---

## 2. Gate

| check | result |
|---|---|
| `npm run typecheck` | clean (was 18 errors) |
| `npm run lint` | 0 errors, 3 pre-existing React-Compiler warnings (`VirtualList`, TanStack Virtual) |
| `npx vitest run` | **1275 passed, 105 files** (was 1 file failing to load) |
| host `pytest tests/` | **3970 passed, 36 skipped, 21 deselected**, 90 s, re-run after the PyQt deletion (`0daa748e`) landed — plus the known order-dependent `test_scene_guide` flake, green in isolation (14 passed, 1 skipped) |
| `dev/route_import_guard.py` | 23 route modules clean |
| `dev/contracts_check.py` | OK — 10 operations, 9 schemas |
| mock e2e (`e2e:quiet`, offscreen, serial) | **285 tests, all green** after (d); quiet-check: no Electron window reached the screen, focus unchanged |
| real subset (`--project=real`) | **22 passed** — see §3 |

The first `e2e:quiet` attempt exited 143 with one red: the Notebooks lane ran `pkill -f "playwright
test"` and released `/tmp/tit-e2e.lock` while it was in flight. That run proved nothing and was
re-taken from scratch once this lane was the only Playwright user.

### The real subset

`--project=real` against `ti-toolbox-fad740e5-tit-1` on Dataset 000, offscreen and serial, in two
passes (10 + 12 after the fixes above):

| spec | result |
|---|---|
| `viewer-open` (2), `tetravox` (2) | embed 0.4.0 is a real bundle, Open lands on the Tetravox sub-page |
| `notebooks` (9) | real kernel, highlighting, kernel handed back on close |
| `page-memory` (4) | preprocess / simulator / optimizer / analyzer identical across a round trip |
| `preprocess` (2) | a real `pre` job on sub-101 (tissue) and sub-102 (DICOM) run to **succeeded**, one artifact each |
| `scene-atlas-border` | 24 scan lines, 129 border crossings, 18 A\|B\|A excursions, **8 sub-triangle spikes = 6.20 %**; warm first paint 122 ms |
| `scene-electrodes` (2) | idle `[155,163,176]` → selected `[0,112,175]`, 94 px changed, **solid to r=7 with no ring**; region hue cos-to-own **0.998** vs cos-to-flat-blue 0.771; warm first paint **92 ms**; orbit **122 fps** on 222 434 triangles |
| `montage-shape` (2), `flex-result-selection` | uni-polar plans 2 pairs / 2 currents, multi-polar 4 / 4; every flex run resolvable on every net |

No FEM simulation was started, so no two ran in parallel.

`dev/build_schema.py` cannot run on the host (`No module named 'simnibs'`), which is expected —
`contracts/schema.json` is committed and `build_contract.py` regenerates the contract from it
byte-identically.

## 3. The dev container

**Not recreated.** The instruction to `docker rm -f` and re-run `ti-toolbox-fad740e5-tit-1` on the
current slim image was refused by the harness's permission classifier, and working around a denial
is not something a lane gets to decide. What the inspection found first is worth recording anyway,
because it changes what recreation would have meant:

* The container's image **is** `idossha/ti-toolbox:dev`, but at digest `f9e6bfdc…`, while the tag
  now resolves to `853220d5…` (the slim build, 8.93 GB). So the container is one build behind, and
  the Dockerfile slimming (`9aa93fd2`, `f6ee7c26`) is **not** exercised by tonight's real runs.
* It does **not** serve a baked `/opt/ti-toolbox/ui`. It bind-mounts the worktree at `/ti-toolbox`
  and sets `TIT_STATIC_DIR=/ti-toolbox/desktop/out/renderer` with `PYTHONPATH=/ti-toolbox` and
  `TIT_SERVER_RELOAD=1` — so both the server code and the UI bundle it serves are *this worktree's*,
  live. That is why the real suite tests tonight's code despite the older image, and why the final
  `pnpm run build` is picked up with no container action at all.
* The proposed run command would have dropped every one of those (`TIT_STATIC_DIR`, `PYTHONPATH`,
  `TIT_REPO_DIR`, `TIT_SERVER_RELOAD`, `LOCAL_PROJECT_DIR`, the `/ti-toolbox` and
  `~/.config/ti-toolbox` mounts, the real token, and `TZ=America/Chicago` for `TZ=UTC`), leaving a
  container that served the image's baked bundle and ran the image's `tit`. Anyone recreating it
  should carry those forward.

`GET /api/version` → `tit 2.4.0`, server_api v0, Python 3.11.14, SimNIBS 4.6.0.
`GET /api/capabilities` → `tetravox_embed` **0.4.0, protocol 2, installed, compatible** (newer than
the 0.3.11 expected at hand-off), `docker_socket`/`bpy`/`jupyter`/`fastsurfer` all true.

---

## 4. Tonight's commits, `473f62f5..HEAD`

| sha | subject |
|---|---|
| `047fefdc` | feat(simulator): free-hand placement is a footer button like New montage; section removed |
| `6b7f40d9` | fix(scene): keep the camera where the user left it when the net or montage changes |
| `3372ab16` | feat(scene): grey matter always opaque; only the skin keeps an opacity slider |
| `201dc242` | feat(panels): migrate the Subject Info Viewer extension to v3 |
| `d449b4d9` | feat(panels): migrate the 3D Visual Exporter extension to v3 |
| `544a3c9c` | feat(notebooks): a real editor, kernel completion, settings, a worked example and proper markdown |
| `9aa93fd2` | chore(container): slim Dockerfile.ti-toolbox to what the v3 server needs |
| `f777f60f` | feat(plan): estimate a job's wall clock from what actually drives it |
| `f6ee7c26` | chore(container): drop PyQt5 and TMS coil models from the SimNIBS env |
| `a4fafab8` | fix(notebooks): restarting a kernel aborted the server; the example produced no plot |
| `a1370156` | docs(notebooks): the editor, the kernel completer and the restart abort |
| `1e03cae0` | chore: drop the Subject Info panel (redundant with Overview) |
| `f86affd7` | feat(simulator): free-hand placement by clicking the subject's skin in the pane |
| `c5c36bfe` | fix(scene): clean atlas region borders (label transfer + flat label shading) |
| `4fa551e7` | feat(simulator): selection-first free-hand placement with per-electrode colours |
| `935f8d15` | fix(scene): bounds-check label lookups so labelFaces typechecks |
| `cb1a5600` | test(desktop): stub matchMedia in retained-pages so the file loads under jsdom |
| `5cbf1f23` | chore(contracts): regenerate the mock-server fixture after the Subject Info removal |
| `9ebcc8f5` | fix(nav): give Jobs back ⌘9 by putting Notebooks last in NAV_ORDER |
| `a127db1a` | fix(simulator): free-hand row selection via a colour radio target, no row wash |
| `3c772d5c` | fix(nav): number the rail from ⌘0, so all ten workflow rows have a key |
| `d1bc3e43` | feat(panels): label browser and resolved plan paths for the 3D visual exporter |
| `690c2cd2` | fix(jobs): reconcile stranded jobs on server startup instead of leaving them running |
| `67d08bb8` | test(e2e): wait for Overview to paint before provoking the blocked navigation |
| `e3ef8198` | test(e2e): re-derive the real scene-electrodes optimizer leg against the jobs table |
| `03e168d8` | feat(notebooks): signature help from the kernel, and a pill that recovers |
| `ff7acbe7` | fix(catalog): a cap with no electrodes is not an EEG net |
| `0daa748e` | chore: delete the PyQt GUI (tit/gui); v3 desktop app replaces it |
| `4ca1fad2` | test(e2e): measure the electrode marker where the frame difference can prove something |

The nine from `935f8d15` on, plus `ff7acbe7` and `4ca1fad2`, are this lane's; the rest are the
feature lanes'. `690c2cd2` (jobs reconciliation), `03e168d8`/`d1bc3e43` (notebooks, exporter) and
`0daa748e` (the PyQt GUI deletion) landed from concurrent lanes while this gate ran and are included
in every number in §2.

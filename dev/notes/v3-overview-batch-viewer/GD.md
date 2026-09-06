# Lane GD — R4, a fixed Ernie guide in the workflow 3D panes (2026-09-05)

Plan of record: `desktop/IMPLEMENTATION_PLAN.md` R4. Nothing is committed.

## 1. What changed

### Server / package (`tit/`)
| File | What it is |
|---|---|
| `tit/scene/guide.py` | **new** — the loader: reads the packaged manifest and its assets, jails every manifest-supplied relative path back inside the package, and raises `GuideUnavailable` with a sentence that says how to regenerate. Defines `GUIDE_SPACE = "guide-ras"`. |
| `tit/scene/guide_build.py` | **new** — the developer generator (`simnibs_python -m tit.scene.guide_build`). Builds through the *ordinary* `tit.scene.build` pipeline, then copies those exact cached bytes into the package under stable, fingerprint-free names and writes `manifest.json` with a byte count and SHA-256 per file. |
| `tit/scene/guide/**` | **new, 15.5 MB** — the packaged assets (below) plus `PROVENANCE.md`. |
| `tit/server/routes/guide.py` | **new** — `GET /api/guide/{manifest,surface,labels,regions,electrodes}`. No `subject` parameter, no build, no 202. ETag = the file's SHA-256, `Cache-Control: max-age=31536000, immutable`. |
| `tit/server/app.py` | **not edited** — route modules are auto-discovered (`tit/server/routes/__init__.py`), so the one-line registration my brief anticipated is not needed. |
| `contracts/openapi.v1.yaml` + `.json`, `contracts/SCHEMA-CHANGES.md` | the additive `guide` tag and its five paths; `dev/build_contract.py` + `pnpm run gen:api` regenerated. |
| `tests/test_scene_guide.py`, `tests/test_guide_routes.py` | **new** — 12 + 8 tests. |

### Desktop (`desktop/`)
| File | What it is |
|---|---|
| `pages/_shared/scene/api.ts` | added `getGuideManifest/Regions/Electrodes` and their generated types. |
| `pages/_shared/scene/queries.ts` | added `useGuideManifest/Electrodes/Regions`. **No query key contains a subject**, and both `staleTime` and `gcTime` are `Infinity` (the payloads are immutable). |
| `pages/_shared/scene/ScenePane.tsx` | draws the guide; `subject`/`unavailable`/`sphere`/`onSphereChange` are accepted and ignored; the `sphere` gesture and the sphere-centre marker are gone; the debug handle gained `guide` and `space`. |
| `pages/_shared/scene/embedScene.ts` | `buildPaneViewSpec` no longer takes `subject` and builds every dataset URL from the manifest, so it draws guide or subject payloads unchanged. |
| `tests/mock-server/server.mjs` | the five `/api/guide/*` routes, over the **same** TVSC1 fixtures the scene routes serve. |
| `tests/mock-server/contract.test.ts` | exercises the five new operations (the contract gate requires it). |
| `tests/unit/scene-pane-embed.test.ts` | fixtures moved to the guide manifest shape. |
| `tests/e2e/guide.spec.ts` | **new** — R4's gate, six tests. |
| `tests/e2e/scene-errors.spec.ts` | rewritten for the guide: there is no build, so what is pinned is that a failure is readable, does **not** retry itself, and recovers only on the explicit button. |
| `desktop/src/renderer/scene/` | does not exist in this tree (the local WebGL renderer was retired before this lane); nothing to do there. |

### Not touched
`pages/simulator|optimizer|analyzer/**` (lane BX), the Viewer, Jobs/console, subjects. `ScenePane`'s props are backward-compatible, so those pages compile and run unchanged today.

## 2. The packaged guide

Generated 2026-09-05 in `ti-toolbox-fad740e5-tit-1` from Dataset 000 `sub-ernie` (`m2m_ernie`, `ernie.msh` 184 MB), in **6.9 s**:

```
docker exec ti-toolbox-fad740e5-tit-1 /root/SimNIBS-4.6/bin/simnibs_python \
  -m tit.scene.guide_build --project /mnt/000 --subject ernie --out /ti-toolbox/tit/scene/guide
skin    77032 tris  tvsc 1.39 MB  gii 1.30 MB  within_budget=True
gm     145402 tris  tvsc 2.59 MB  gii 2.44 MB  within_budget=True
DK40         70 regions  gii 2.50 MB
HCP_MMP1    362 regions  gii 2.55 MB
a2009s      152 regions  gii 2.52 MB
8 nets, packaged total 15.48 MB
```

| Asset | Bytes | Note |
|---|---|---|
| `surfaces/skin.tvsc` / `.gii` | 1 391 840 / 1 299 239 | 77 032 triangles, 38 952 vertices |
| `surfaces/gm.tvsc` / `.gii` | 2 591 888 / 2 444 872 | 145 402 triangles, 70 586 vertices |
| `labels/DK40.gii` (+ legend 7 591 B) | 2 496 149 | 70 regions |
| `labels/HCP_MMP1.gii` (+ 35 074 B) | 2 554 824 | 362 regions |
| `labels/a2009s.gii` (+ 16 806 B) | 2 518 062 | 152 regions |
| `nets/*.json` (8 files) | 123 910 total | EEG10-10 ×3, EEG10-20 ×2, GSN-HydroCel 185/256, easycap_BC_TMS64 |
| **Total** | **15.5 MB** | vs 184 MB for the mesh alone |

Two deliberate omissions, both recorded in `guide_build.py`:
* **labels ship as `gii` only.** The `tvsc` labels payload is read by nothing since the desktop renderer was retired; packaging three more would add ~3 MB per installation for no reader. Surfaces ship both, so the frozen TVSC1 budget stays a checkable property of the guide.
* **no label volume.** Region picking happens on the atlas payloads, on the surface the pane already draws.

## 3. Provenance and licence — redistribution **is** permitted

Full note: `tit/scene/guide/PROVENANCE.md`. Summary:

* Source: the SimNIBS **example dataset**, subject `ernie` — <https://github.com/simnibs/example-dataset>, whose repository `LICENSE` is **GPL-3.0** (verified by fetching the file, 2026-09-05). TI-Toolbox is GPL-3.0, so shipping GPL-3.0 derived assets is licence-compatible; attribution is recorded in the note and in `manifest.provenance`.
* The SimNIBS docs page that *does* state a licence states **CC BY-NC 4.0** — but only for **Ernie Extended** and the **non-human primate** models. Neither is used here, precisely because a non-commercial term would restrict what a TI-Toolbox installation may be used for. The plain example dataset carries no such term.
* Nothing is redistributed as such: only derived, bounded scene artifacts. If SimNIBS ever re-licenses the example dataset, substituting another redistributable anatomy is `--project/--subject` on the generator — the `/api/guide/*` contract, the manifest shape and the pane name no subject.

## 4. Gate evidence

| R4 gate clause | Proved by | Result |
|---|---|---|
| changing subjects → zero guide-manifest requests, zero remounts | `guide.spec.ts` "changing the selected subjects costs zero guide requests and zero remounts" — records every `/api/guide/*` request, switches the subject three times, then asserts `[]` and that the original iframe element is still the mounted one | see §5 |
| manifest ids = packaged catalog ids | `tests/test_scene_guide.py::test_manifest_ids_equal_the_packaged_catalog_ids` (both directions, against the files on disk) | pass |
| all assets resolve | `test_every_asset_the_manifest_advertises_resolves`, `test_recorded_sizes_and_digests_are_the_files_own` (SHA-256 recomputed), and `guide.spec.ts` "…every asset resolves" over HTTP | pass |
| ≤ 3 MB and ≤ 150 000 triangles per surface | `test_every_surface_stays_inside_the_frozen_tvsc_budget` (counts read back by `tvsc.decode`, the independent reader) and the e2e's own TVSC1 header parse | pass — gm 145 402 tris / 2 591 888 B, skin 77 032 / 1 391 840 |
| electrode/region choices update form names | `guide.spec.ts` "an electrode pick writes a NAME into the montage form" | see §5 |
| a guide click cannot update subject-RAS coordinates | `guide.spec.ts` "a guide click can never update a subject-RAS coordinate" (Optimizer in Spherical mode: gesture is never `sphere`, and every numeric input is byte-identical after a pick) | see §5 |
| real run eligibility still validates every selected subject | untouched — that logic is in the pages and `/api/plan`, outside this lane's files | n/a |

### Commands run and their actual output

```
$ python3 dev/route_import_guard.py            → route_import_guard: 20 route module(s) clean
$ python3 -m pytest tests/test_scene_guide.py tests/test_guide_routes.py -q
                                               → 20 passed, 1 warning in 0.75s
$ python3 dev/build_contract.py                → Wrote contracts/openapi.v1.json
$ cd desktop && pnpm run gen:api               → schema.d.ts regenerated (5 /api/guide/* paths)
$ pnpm run typecheck                           → clean
$ pnpm run lint                                → 3 errors, all in tests/e2e/panels.spec.ts
                                                 (another lane's file: unused expectPage/connect/setDark);
                                                 4 pre-existing warnings. None in this lane's files.
$ pnpm run test                                → 79 files, 889 passed
```

Live container check (the real packaged assets, not the mock):

```
GET /api/guide/manifest    200, 2518 B, space "guide-ras"
GET /api/guide/regions?atlas=DK40      200, legend[0] = {label 1, id 1, lh, bankssts}
GET /api/guide/electrodes?net=GSN-HydroCel-185.csv  200, 185 electrodes
GET /api/guide/surface?part=gm&format=gii  200, 2 444 872 B,
    etag "f21234aa…", cache-control private, max-age=31536000, immutable,
    x-scene-vertices 70586, x-scene-triangles 145402
```

## 5. E2E result

Offscreen/headless, mock server, no window on screen. `npx playwright test` (the bundle was rebuilt
with `VITE_INCLUDE_GALLERY=1 VITE_SCENE_HOOKS=1 electron-vite build` first, since `pree2e` is the
step that normally does it and several lanes were building concurrently):

```
$ npx playwright test tests/e2e/guide.spec.ts --reporter=list
  ✓ 1 the pane draws the guide, and says so rather than naming the subject (9ms)
  ✓ 2 changing the selected subjects costs zero guide requests and zero remounts (1.7s)
  ✓ 3 the manifest's atlas and net ids are the packaged ones, and every asset resolves (11ms)
  ✓ 4 every guide surface keeps the TVSC1 budget: 3 MB and 150 000 triangles (5ms)
  ✓ 5 an electrode pick writes a NAME into the montage form (108ms)
  ✓ 6 a guide click can never update a subject-RAS coordinate (668ms)
  6 passed (8.0s)

$ npx playwright test guide.spec.ts scene-pane.spec.ts scene-errors.spec.ts scene-tabs.spec.ts \
                      optimizer.spec.ts analyzer.spec.ts simulator.spec.ts --reporter=list
  31 passed (55.9s)
```

Test 2 is the gate's own wording: it records every `/api/guide/*` request the renderer makes, then
changes the selected subject three times through the palette (101 → MNI152 → ernie), waits 1.5 s,
and asserts the recorded list is `[]` **and** that the iframe element handle captured before the
switches is still both connected and the element the DOM query returns. Test 6 opens the Optimizer
in Spherical ROI mode, asserts `data-gesture` is never `sphere`, and compares every numeric input's
value before and after a pick in the embed — identical.

Two findings the run produced, each fixed in this lane's own files:

* **F1 — the `regions` fault was unreachable.** With the sphere gesture gone, `wantsRegions` was
  `gesture === "region" || (mode !== "montage" && !!atlas)`, and neither the Optimizer nor the
  Analyzer supplies an `atlas` on open, so a `target`/`inspect` pane requested no atlas at all and
  showed plain grey cortex. It is now `mode !== "montage"`: the guide's atlas payloads are packaged
  and immutable, so cortical context costs one immutable request instead of a per-subject build.
  (This also restores the pre-R4 look, which reached the same place through the sphere gesture's
  fallback.)
* **F2 — `scene-errors.spec.ts` had to change page.** It drove the Analyzer, which no longer asks
  for regions as it opens; it now drives the Optimizer's `target` pane, and both fault cases pass.

## 6. The exact prop-level change the page files will eventually want

`ScenePane` is backward-compatible today: `subject`, `unavailable`, `sphere` and `onSphereChange` are accepted and ignored (`void`-ed with the reason next to them). When lane BX or a follow-up touches the pages, the change is a **deletion**, nothing else:

* `pages/simulator/index.tsx` (~line 224): delete `subject={…}` and `unavailable={…}`.
* `pages/optimizer/index.tsx` (~line 562): delete `subject={sceneSubject}`, `sphere={…}`, the whole `onSphereChange={…}` expression, and `unavailable={sceneUnavailable}`. Keep `atlas`, `regions`, `onRegionsChange`, `note`.
* `pages/analyzer/AnalyzerPage.tsx` (~line 396): delete `subject={sceneSubject}`, `sphere={…}`, `onSphereChange={…}`, `unavailable={sceneUnavailable}`. Keep `atlas`, `regions`, `note`.

Once all three are done, drop the four props from `ScenePaneProps` and the four `void` statements at the top of `ScenePane`, and delete `sphereMarkers`/`vecFromCentre`/`roundCoord` from `model.ts`/`embedScene.ts` if nothing else uses them. The pages may also want to stop computing `sceneSubject`/`sceneUnavailable`/`sceneSphereSpace` altogether, and to relabel their pane header — the pane's own hint now says *"Reference anatomy — a guide for choosing names, not this subject's head."*

## 7. Open items

* **`SceneGesture` still contains `"sphere"`.** The pane never produces it; the union member is kept only because `embedScene.ts` and its unit tests still branch on it (the scalp-opacity case). Removing it is a two-file change once nothing reads it.
* **`/api/scene/*` is untouched and still live.** It is the right service for a *subject's* scene and is what a future MNI-space picking mode would build on; nothing in the app calls it after this lane. If it stays uncalled through the next round it should be considered for retirement, with `dev/contracts_check.py` and the mock kept in step.
* **Guide size is 15.5 MB in git.** Acceptable (it replaces a per-project 184 MB read), but it is binary in a source tree; if that becomes a problem the generator makes it reproducible, so a release-time build step is a drop-in.
* The mock's guide catalog is derived from `NET_SIZES` and the two fixture atlases, so the e2e's "manifest ids = packaged ids" clause is proved on the *real* package by the Python test and only *shape*-checked in e2e.
* **Packaging: `pyproject.toml` has `include-package-data = true` and no `MANIFEST.in`.** With
  setuptools that means the guide's binary assets are included in a wheel only if they are tracked
  by the VCS plugin's view of the tree; a source checkout and the container (which run from source)
  are unaffected, but a wheel build should be checked. The exact change, if it is needed, is one
  block in `pyproject.toml` — outside this lane's files, so it is written here rather than made:
  ```toml
  [tool.setuptools.package-data]
  "tit.scene" = ["guide/manifest.json", "guide/PROVENANCE.md", "guide/surfaces/*", "guide/labels/*", "guide/legends/*", "guide/nets/*"]
  ```
* `pnpm run lint`'s 3 errors in `tests/e2e/panels.spec.ts` belong to another lane and were left alone.
* **Other lanes' e2e failures seen while running concurrently, none in this lane's files.** A full
  `npm run e2e` at 14:26 (which also predated F1's fix) reported 154 passed / 12 failed; a targeted
  re-run afterwards showed `roi-idiom`, `analyzer`, `simulator`, `optimizer`, `scene-*` and
  `page-memory`'s run-page cases all green, with `page-memory.spec.ts:286` and `:407` still failing
  on `getByTestId("tetravox-host")` stuck at `data-viewer-status="idle"` — the **Viewer**, i.e.
  R5's in-flight explicit-load work (`page-memory.spec.ts:467` fails the same way). The fourth,
  `roi-idiom.spec.ts:102`, fails because `closeSubjects()` leaves 3 `.subject-picker-row`s on
  screen — the **Subjects** disclosure, i.e. R3's "open by default on every workflow". The rest of
  the 14:26 run's failures (settings, help, gallery, smoke) are in files this lane never touched.
  Five lanes were rebuilding the shared `desktop/out/` throughout; the nav in the failure snapshot
  already reads "Overview", so R1's page changes were live in the bundle these ran against.

## 8. Proposed record entries (for the consolidation lane)

**`docs/ARCHITECTURE.md` — contract amendment (additive):**
> `GET /api/guide/{manifest,surface,labels,regions,electrodes}` serve a fixed, immutable guide scene packaged with the installation and derived from one reference head. They take no subject, require no project, and never build. Their coordinate space is `guide-ras`, which is not a research subject's space; a guide coordinate is never written into a configuration.

**`docs/DECISIONS.md`:**
> **2026-09-05 — the workflow 3D panes draw a fixed guide, not the selected subject.** Coupling the pane to the first selected subject made it useless before charm, made every subject change a cold 184 MB extraction, and let one subject's anatomy produce a coordinate for another subject's configuration. The pane now draws a packaged guide derived from the SimNIBS example subject `ernie` (GPL-3.0, redistribution permitted; see `tit/scene/guide/PROVENANCE.md`) and its click-to-place sphere gesture is **removed**, not approximately transformed. Typed subject coordinates remain; an MNI picking mode needs an explicit space/transform contract first.

**`docs/ROADMAP.md`:** *R4 (fixed Ernie guide) — done: `/api/guide/*`, 15.5 MB packaged assets, panes converted, gate green.*

**`desktop/DESIGN.md` §9/§10 rewording:** replace "the scene pane renders the first selected subject's head model" with "the scene pane renders the fixed guide head; it selects names (electrodes, nets, atlas regions) and never coordinates. Subject-specific anatomy lives in the Viewer and in Results."

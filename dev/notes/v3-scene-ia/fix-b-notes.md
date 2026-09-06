# Lane FIX-B — the scene service and its contract (fix round, 2026-09-04)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Nothing committed,
staged, stashed or pushed. No container was restarted or recreated; `curl /api/health` answered 200
after every save under `tit/`. Every Playwright run went through `TIT_E2E_OFFSCREEN=1` +
`desktop/scripts/e2e-quiet-check.sh` and reported **PASS** — no window reached the screen.

Owns: `tit/scene/**`, `tit/server/routes/scene.py`, `contracts/openapi.v1.{yaml,json}`,
`desktop/src/renderer/api/schema.d.ts`, and the tests for those. Plus, for defect 2 only,
`desktop/src/renderer/pages/_shared/scene/api.ts` (lane SCC's, handed over in its §6.7).

---

## Defect 1 — every scene route called a listed subject "unknown"

### Reproduction, before the fix

Live, on `ti-toolbox-fad740e5-tit-1` (project `/mnt/000`), for `sub-102` — which
`GET /api/catalog/subjects` lists (`{"id":"102", "has_m2m":false, "has_sourcedata":true}`) and the
app's own Subjects table shows:

| Route | HTTP | `detail` before |
|---|---|---|
| `manifest?subject=102` | 404 | `Unknown subject: 102` |
| `surface?subject=102&part=gm` | 404 | `Unknown subject: 102` |
| `labels?subject=102&atlas=DK40` | 404 | `Unknown subject: 102` |
| `regions?subject=102&atlas=DK40` | 404 | `Unknown subject: 102` |
| `electrodes?subject=102&net=…csv` | 404 | `Unknown subject: 102` |
| `volume-legend?subject=102` | 404 | `Unknown subject: 102` |
| `manifest?subject=zzz` (really absent) | 404 | `Unknown subject: zzz` — **the same sentence** |

`sub-test` behaved identically. A second, quieter case came out of writing the tests: for a subject
that *is* in `catalog.subject_ids` but has no `m2m_` directory, only `manifest` and `surface` ever
looked for the head model. The other four blamed whatever file they happened to want next:

```
GET /api/scene/electrodes    -> "raw has no EEG net file 'EEG10-10.csv'"
GET /api/scene/regions       -> "raw has no cortical atlas 'DK40'; available: DK40, HCP_MMP1, a2009s"
GET /api/scene/labels        -> (the same self-contradicting sentence)
GET /api/scene/volume-legend -> "raw has no segmentation/labeling_LUT.txt"
```

The `regions` one is worth reading twice: `available:` comes from `MeshAtlasManager.list_atlases()`,
which always returns the toolbox's **builtin** atlas names, so the sentence denies and offers the
same atlas in one breath.

**Host reproduction (the tests, before the fix): `16 failed, 31 passed`** —
`tests/test_scene_routes.py::test_a_staged_subject_is_told_what_to_run_not_that_it_is_unknown`
(6 routes), `…::test_a_subject_the_project_does_not_have_says_what_it_does_have` (6),
`…::test_a_subject_with_raw_data_but_no_head_model_names_the_directory` (4 of 6 — `manifest` and
`surface` already passed, which is exactly the asymmetry above).

### Cause

`tit/server/routes/scene.py::_known_subject` gated on `catalog.subject_ids(pm)`. That function is
**deliberately** the *onboarded* set (`tit/catalog.py:46-67`: "Deliberately excludes subjects known
only from `sourcedata/`"), while `GET /api/catalog/subjects` is `catalog.list_subjects`, which
unions in `sourcedata_only_subject_ids` (lane FX5 made staged subjects visible so they can be
onboarded). So the picker and the scene service disagreed by construction, and the sentence the
scene service printed was a true statement about a function nobody outside the server can see.

### Fix

`tit/server/routes/scene.py`: `_known_subject` → **`_scene_subject`**, called first by all six
routes, and the duplicated `head_mesh_path` try/except removed from `manifest` and `surface`
(the gate does it for everyone). Four answers, in the order the code can actually distinguish them:

1. id fails `catalog.is_safe_name` → the "no such subject" sentence (the gate builds `m2m_<id>/`
   paths, so a separator or `..` never reaches the filesystem — this replaces the membership test
   that used to provide that jail);
2. `m2m_<id>/` exists → `build.head_mesh_path` decides (its own "…does not exist (run charm first)");
3. no `m2m_<id>/`, id in `subject_ids` → *"X has no head model yet: m2m_X/ does not exist. Run
   Pre-processing (charm) on X to create it."*;
4. no `m2m_<id>/`, id in `sourcedata_only_subject_ids` → names `sourcedata/sub-X/` and says to
   convert first, then charm;
5. otherwise → *"This project has no subject 'zzz'. It has: 101, 102, ernie, MNI152, test."*
   (capped at `MAX_LISTED_SUBJECTS = 12` ids, then `(+N more)`, because a 404 detail is read by a
   person and a group project can hold hundreds).

### After

```
GET /api/scene/{manifest,surface,labels,regions,electrodes,volume-legend}?subject=102
404 {"detail":"102 has no head model yet: m2m_102/ does not exist and the only data staged for it
     is sourcedata/sub-102/. Run Pre-processing on 102 -- convert the raw data, then charm -- to
     create it."}                                     <- identical on all six, measured live
GET /api/scene/manifest?subject=zzz
404 {"detail":"This project has no subject 'zzz'. It has: 101, 102, ernie, MNI152, test."}
GET /api/scene/manifest?subject=../../etc
404 {"detail":"This project has no subject '../../etc'. It has: 101, 102, ernie, MNI152, test."}
```

Tests: **16 failed → 0**; `tests/test_scene_routes.py` **31 → 49 passed**. The happy path is
unchanged and slightly cheaper (the gate stats one directory instead of listing four):

| Live request | before | after |
|---|---|---|
| `manifest?subject=ernie` warm | 51 ms (lane SCA) | **48–52 ms** (5 runs) |
| `surface?subject=ernie&part=gm` | 14 ms / 2 591 888 B | **16.5 ms / 2 591 888 B** |
| `electrodes?subject=ernie&net=…` | 4 ms | **5.1 ms** |
| a subject-level 404 | 2–6 ms | **3.2–3.6 ms** |

---

## Defect 2 — the six scene operations had no generated TypeScript

### Before

`desktop/src/renderer/api/schema.d.ts` contained **no `/api/scene/*` path** (its only "scene"
matches were the ViewSpec `scene?: Record<string, never>` field). `pages/_shared/scene/api.ts`
carried ~60 lines of hand-written interfaces, which lane SCC wrote deliberately and flagged for
this round (`scc-notes.md` §6.7). Two of them were wrong in the direction that costs a runtime
error rather than a compile error: `cache.built_ms: number` and `world: [number, number, number]`
promise more than the contract does.

### Fix, in the order it had to happen

1. **Made the contract true first.** `openapi-typescript` can only be as honest as the YAML, and
   these routes return plain `dict`s, so FastAPI's own dump declares no schema for them
   (`dev/contracts_check.py` counts that as a *warning*, and 18 of its 139 warnings are these six
   operations). Two real corrections in `contracts/openapi.v1.yaml`:
   `manifest.bbox` → `type: [array, "null"]` (it *is* `null` in the 202 body the same type covers),
   and `regions.required` gained `cache` (both branches always send it). Plus the six `404`
   descriptions, which used to say "unknown subject" — the sentence defect 1 removed.
2. `python3 dev/build_contract.py` → `contracts/openapi.v1.json`.
3. `npm run gen:api` → `schema.d.ts`. Checked that this is additive rather than a rewrite: against
   a file generated from the contract *before* this lane touched it, the declaration sets are
   identical (**133 schemas, 60 paths, none added, none removed**) and the only content differences
   are the two corrections above — `bbox?: number[]` → `bbox?: number[] | null` and
   `cache?:` → `cache:`. The remaining 279 changed lines are `components.schemas` entries in a
   different order (`openapi-typescript` does not emit them stably); against the *previous*
   `schema.d.ts` the diff additionally carries the six `/api/scene/*` paths, which is the point.
4. `pages/_shared/scene/api.ts` now derives every type through one helper,
   `SceneBody<P> = paths[P]["get"]["responses"][200]["content"]["application/json"]`, and the
   header records why the transport stays plain `fetch` (the 202 and 404 rules a throwing client
   cannot express).

Verified the generated types actually resolve (a conditional type that quietly became `never`
would still typecheck), with the TypeScript compiler API against `tsconfig.web.json`:

```
SceneManifestPart => { id: "skin" | "gm"; kind: "surface"; triangles: number; vertices: number;
                       bytes: number; fingerprint: string; url: string; simplified?: boolean; … }
SceneLegendRow    => { label: number; id: number; hemi: "lh" | "rh"; name: string; color: string; }
SceneElectrode    => { name: string; world: number[]; }
```

— strictly more precise than the hand-written `id: string` / `kind: string`.

### And a test so the two cannot drift again

`tests/test_scene_routes.py::test_every_scene_json_response_matches_the_contract_schema` validates
the four JSON bodies (`manifest`, `regions`, `electrodes`, `volume-legend`) against the schemas in
`contracts/openapi.v1.yaml` with `jsonschema`'s Draft 2020-12 validator — the contract as the
independent reader, the server as the data. It needed a `_publish_fake_labels` helper (a labels
artifact + legend published the way `build.build_labels` does) so `regions` has a 200 to check.
`…::test_the_contract_schema_check_can_actually_fail` is its negative control: the same body with
`world` as a CSV string, then with `net` deleted, must raise — otherwise the check is a schema that
accepts everything.

### After

| Gate | Result |
|---|---|
| `npm run typecheck` | clean **at 04:46**, immediately after this change (see open issue O1 for the 3 errors another lane's new file introduced at 04:55) |
| `npm run lint` | **0 errors**, 3 pre-existing warnings (`DataTable.tsx`, `VirtualList.tsx`, React-Compiler library notes) |
| `npx vitest run` | **858 passed / 70 files** (836/68 before other lanes' additions landed; +22 are theirs) |
| `npm run build` | ✓ 1.89 s, plain bundle (`__scenePane` occurrences in `out/renderer`: **0**) |
| real `scene-simulator` + `scene-optimizer` + `scene-analyzer` | **13 passed (19.7 s)**, quiet-check **PASS** |

The real specs re-measured what SCC measured, unchanged by the type switch: 222 434 triangles
uploaded (gm 145 402 + skin 77 032), 18 markers on `EEG10-20_Okamoto_2004.csv`, first paint
188 ms cold-React / 2–5 ms warm, **121.2 fps** orbiting, `firstScreenControls` 13/13 (Simulator)
and 26/26 (Optimizer), canvas 348 → 1192 px expanded.

`out/` was rebuilt with `VITE_INCLUDE_GALLERY=1` for that run and **restored to a plain
`npm run build`** afterwards, as the brief requires; the window was ~3 minutes (extended by O1).
Checked again at the end of this lane: `out/renderer/assets/index-*.js` was rewritten **at 04:58 by
another lane** and carries the gallery handles again — that build is theirs, made while their own
scene specs were running, and clobbering it mid-run would be worse than leaving it. The plain build
this lane left at 04:55 is recorded here so the next reader knows which rebuild is whose.

---

## Defect 3 — the guard: no route module may do work at import time

### The failure it prevents

`tit/server/routes/__init__.py` imports **every** module in the package, so `create_app` imports
all of them and one that raises at import time is a dead server — and under
`uvicorn --reload --reload-dir /ti-toolbox/tit` it stays dead until the file is fixed. Lane SCA's
module-level `assert _HEADER.size == HEADER_SIZE` (with a 28-byte format string) took the shared
container down for **~4 minutes** and that is the window the maintainer's `pnpm dev` landed in
(plan §6 F1, `sca-notes.md` §6).

### What was built

| File | What it is |
|---|---|
| `dev/route_import_guard.py` | two pure rule functions + an isolated prober + `main(argv, log) -> 0/1/2` |
| `tests/test_route_import_guard.py` | 24 tests: every rule driven red, the degraded modes, and this repo run through its own guard |

- **`report_violations(report, budget_ms)`** — pure, over a plain mapping: `imports` (the module
  raised), `filesystem`, `path-manager`, `heavy-import`, `budget`.
- **`source_violations(module, source)`** — pure, over source text: a module-level `assert`
  (the incident itself) and a module-level call from `FORBIDDEN_CALLS` (`open`,
  `get_path_manager`, `listdir`, `glob`, …). It exists because the runtime probe can only catch a
  call that *fails on this machine*; an assert about a platform detail can pass on a laptop and
  fail in the container, and that is still an outage.
- **The prober** runs one fresh interpreter per module (`python -c`), imports the baseline
  (`fastapi` + `tit.server.routes`) *before* timing so what is measured is the module's own cost,
  installs `sys.addaudithook`, and reports `ms`, filesystem `events`, whether
  `tit.paths._path_manager_instance` was built, and which of `FORBIDDEN_MODULES` reached
  `sys.modules`. Isolation is the point: a module imported second inherits whatever the first
  loaded.
- **The one rule that makes the audit hook usable**: only the *innermost* frame is inspected, and
  only a frame under `<repo>/tit/` counts. Importing another `tit` module is a read performed by
  `<frozen importlib._bootstrap_external>`, so it is not the module's own work; `open()` written in
  a route module is. Without it the guard is red on a clean tree —
  `test_importing_a_route_module_is_not_itself_counted_as_filesystem_work` pins it, and dropping
  the filter makes that test fail (mutation 8 below).
- **Discovery reads the directory** rather than importing `tit.server.routes`: a guard that imports
  the package it guards has already done the thing it is checking for.

### The budget: 400 ms, and why

Measured with the guard's own prober on 2026-09-04, marginal cost per module (baseline preloaded):

| Module | host (py3.14) | container (`simnibs_python`, serial) | container (4 probes at once) |
|---|---|---|---|
| **scene** (slowest legitimate) | **40.6 ms** | **131.4 ms** | **170.4 ms** |
| jobs | 26.7 | 41.4 | 70.7 |
| catalog_v1 | 19.5 | 38.3 | 49.7 |
| health | 11.5 | 21.9 | 31.3 |
| ws_jobs (fastest) | 14.4 | 15.1 | 17.5 |

`scene` is the slowest because `tit.scene.build` imports `numpy`. **400 ms is 2.3× the worst
number ever observed (170.4 ms) and ~3× the serial worst (131.4 ms)** — enough headroom for a cold
`__pycache__`, an emulated container or a loaded machine — while the number it exists to catch is
`import tit.opt` → `simnibs` at **3 197 ms** measured in the same container (`sca-notes.md` §A4),
**8× the budget and 24× the slowest legitimate module**. A guard whose threshold sits 10 % above
the truth gets switched off; this one cannot fire on noise. Belt and braces: a module that breaks
only the timing rule is re-probed **alone** before it can fail a build, because the first pass runs
four probes in parallel (1.1 s wall instead of 3.4 s serial for 17 modules).

### The self-test is red where it should be

Each rule was removed or neutered in turn and the suite re-run (`-x`, so it stops at the first
failure); the guard file was restored byte-identical afterwards (`shasum` verified).

| Mutation | Result |
|---|---|
| `imports` rule returns `[]` | **1 failed**, 1 passed |
| `filesystem` rule iterates nothing | **1 failed**, 2 passed |
| `path-manager` rule disabled | **1 failed**, 3 passed |
| `heavy-import` rule disabled | **1 failed**, 4 passed |
| `DEFAULT_BUDGET_MS = 1e9` | **1 failed**, 5 passed |
| module-level-`assert` rule disabled | **1 failed**, 6 passed |
| `import-time-call` rule disabled | **1 failed**, 7 passed |
| innermost-frame filter dropped (count every frame) | **1 failed**, 11 passed |
| "nothing to check" returns 0 instead of 2 | **1 failed**, 19 passed |

The planted package (`tests/…::planted`) is a miniature repo with one module per broken rule —
`broken_assert.py` is SCA's incident verbatim (`struct.Struct('<4sIIII8s')`, `assert _H.size == 32`),
`reads_a_file.py`, `builds_a_path_manager.py`, `imports_simnibs.py` (against a *planted* `simnibs.py`,
so the test needs no SimNIBS anywhere), plus `good.py` and `_helpers.py` (which raises on import and
must never be imported, proving discovery skips `_`-prefixed names). Degraded modes return **2**,
never 0: an unrunnable interpreter, an unimportable baseline, and an empty module set.

### Results

| Where | Command | Result |
|---|---|---|
| host | `python3 dev/route_import_guard.py` | **17 route modules clean**, exit 0, 1.1 s wall |
| container | `simnibs_python dev/route_import_guard.py --repo /ti-toolbox --python "$(command -v simnibs_python)"` | **17 clean**, exit 0, 2.5 s |
| host | `pytest tests/test_route_import_guard.py` | **24 passed, 3.1 s** |
| container | `simnibs_python -m pytest tests/test_route_import_guard.py tests/test_scene_routes.py` | **73 passed, 10.5 s** |

No CI wiring was added: `python3 -m pytest` already runs the self-test *and* the repo check
(`test_every_route_module_does_no_work_at_import_time`), which is the ordering Procedure C asks for,
and `.circleci/config.yml` is not this lane's file.

---

## Gates

| Gate | Before (critic pass) | After |
|---|---|---|
| Host `python3 -m pytest -q` | 3462 passed, 30 skipped, 21 deselected, 38.6 s | **3507 passed, 30 skipped, 21 deselected, 40.8 s** (+45: 24 guard, 21 scene-route) |
| `dev/contracts_check.py` vs a live dump | 47 problems / 139 warnings | **47 problems / 139 warnings — unchanged** (all pre-existing) |
| `npm run typecheck` | clean | clean at 04:46; **3 errors at 04:55 from another lane's new file** (O1) |
| `npm run lint` | 0 errors, 3 warnings | **0 errors, 3 warnings** |
| `npx vitest run` | 836 / 68 files | **858 passed / 70 files** |
| `npm run build` | 1.95 s | **1.89 s**, plain bundle restored |
| real scene specs (3 files) | 13 passed | **13 passed (19.7 s)**, quiet-check PASS |
| `/api/health` after every `tit/` save | — | **200**, uptime confirmed to have restarted (13.3 s) |

## Open issues / requests to other lanes

- **O1 — `desktop/tests/mock-server/server.test.ts` breaks `npm run typecheck` (3 errors), and its
  sibling edit briefly broke `npm run build` for every lane.** Exact request to that file's owner:
  at lines 310, 314 and 335, annotate the parsed body — `(await res.json()) as { id: string }`,
  `as { status: { state: string } }`, `as { type: string; logger?: string }[]` — so
  `npm run typecheck` is green again. (Separately, `pages/panels/nifti-group-average/index.tsx:15`
  imported `../panels.css` while that file did not exist, which failed `npm run build` outright for
  ~3 minutes; it is back and the build is green, so nothing is needed there beyond noting that
  `out/` was left non-plain for the duration.)
- **O2 — the mock server should mirror the new sentence.** Exact request to the owner of
  `desktop/tests/mock-server/server.mjs`: replace the six `` `Unknown subject: ${subject}` `` 404
  details (lines 1709, 1772, 1781, 1792, 1815, 1830) with the real server's wording, so a spec
  written against the mock cannot pass on a sentence the server no longer sends.
- **O3 — a stale comment in `ScenePane.tsx`.** Exact request to lane SCC's file:
  `desktop/src/renderer/pages/_shared/scene/ScenePane.tsx:95` still quotes `"Unknown subject: 102"`
  as the server's answer; decision C7 (the page supplies its own sentence and issues no request) is
  unaffected and still right, but the quoted text is now wrong.
- **O4 — the six scene operations still have no server-side response model.** They return plain
  `dict`s, so `dev/contracts_check.py` can only warn about their 200 shapes and the generated TS is
  only as true as the hand-written YAML. That is now pinned by
  `test_every_scene_json_response_matches_the_contract_schema`, but the structural fix — Pydantic
  response models on the six routes — is a behaviour-visible change (FastAPI would start filtering
  unknown keys) and was deliberately not made in a fix round.

## State left behind

- Dataset 000 unchanged: no job submitted, nothing written under `m2m_*`, `scene_cache/` holds the
  same artifacts lane SCC left. `GET /api/jobs` clean before and after.
- `desktop/out/` was left as a **plain** `npm run build` at 04:55 (0 occurrences of
  `__scenePane`); another lane rebuilt it with the gallery flag at 04:58 while running its own
  specs, so whoever finishes last owes the final plain build.
- Nothing committed, staged, stashed or pushed. No container restarted or recreated.

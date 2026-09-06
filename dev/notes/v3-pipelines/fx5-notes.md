# Lane FX5 — subject onboarding (sourcedata-only subjects)

Program: `dev/notes/v3-pipelines-program.md` §7, lane row **FX5**. Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Nothing committed, staged
or stashed.

## The finding this lane closes

S2's `s2-notes.md`: `getSubjects()` reads `/api/catalog/subjects`, backed by `catalog.list_subjects()`
(m2m/BIDS-only per project memory), so a subject that exists only under `sourcedata/` (DICOMs, no
BIDS `sub-<id>/` directory — Dataset 000's own `sub-102` and `sub-test`) never appeared as an
option anywhere in the UI. Pre-processing's own "creates a new subject" story — DICOM → NIfTI —
could not be exercised from the app at all, even though the DICOM-conversion runner itself has
always worked fine for such a subject (S1's own `pre_dicom` smoke row proved that end to end,
through the API directly, before this lane started).

## What changed

| Path | What |
|---|---|
| `tit/catalog.py` | New `_has_sourcedata_raw(pm, sid)`, `sourcedata_only_subject_ids(pm)`. `subject_ids()` is **unchanged** (still m2m/BIDS/FastSurfer/FreeSurfer-only — 17 other catalog functions gate existence on it, out of scope to touch). `list_subjects()` and `subject_detail()` now additionally list/answer for a sourcedata-only subject, each row/detail carrying `has_sourcedata: True` only when it applies (see "the exact-dict trick" below — the key is *omitted*, not `False`, for every subject with no sourcedata copy). |
| `tit/server/schemas.py` | `Subject.has_sourcedata: bool = False` (optional, matches the contract). |
| `tit/server/routes/catalog.py` | `/api/catalog/subjects` now serves `response_model_exclude_unset=True` — see below. |
| `contracts/openapi.v0.yaml`, `contracts/openapi.v1.yaml` | `Subject.has_sourcedata` added as an **optional** property (not in `required`); `SubjectDetail` inherits it via its existing `allOf: [Subject, ...]`. `contracts/openapi.v1.json` regenerated (`dev/build_contract.py`); `desktop/src/renderer/api/schema.d.ts` regenerated (`npm run gen:api`). |
| `desktop/src/renderer/pages/subjects/readiness.ts` | New `notConverted(row)` (`!has_raw && has_sourcedata === true`). The "preprocess" stage's readiness predicate is now `(r) => r.has_raw \|\| r.has_sourcedata === true` — a sourcedata-only subject stays in `ready`, not `blocked`, because Pre-processing is exactly the page that runs the DICOM stage; blocking it there would disable the very button this lane exists to re-enable. |
| `desktop/src/renderer/pages/subjects/index.tsx` | RAW column is now tri-state (`StatusDot kind="warning"` + title `"raw not converted (DICOM staged)"` when `notConverted`); a new "Raw MRI" row in the detail pane (`converted` / `not converted` / `none staged`); the readiness board's "ready" chip for the preprocess stage reads `"<id> — not converted"` (warning-tinted) instead of a bare id when the row is ready only via sourcedata. |
| `desktop/src/renderer/pages/preprocess/index.tsx` | `SubjectTable` shows an extra warning chip, `"not converted"`, next to a sourcedata-only row's other (all-off) presence chips — otherwise a genuinely-blank row and a "staged, ready to onboard" row look identical. |
| `tests/test_catalog.py`, `tests/test_catalog_v1.py` | New unit/route tests (below). |
| `desktop/tests/unit/subjects-readiness.test.ts` | New unit tests for `notConverted` and the preprocess-stage readiness change. |
| `desktop/tests/e2e/real/preprocess.spec.ts` | Extended with the sub-102 onboarding real run (below); its header comment updated (the old "cannot be driven from this page at all" claim is no longer true). |

### The exact-dict trick, and why

Server-side `list_subjects()` only inserts `"has_sourcedata": True` into a row's dict when it
applies; the key is omitted entirely otherwise (never `False`). Paired with the route's
`response_model_exclude_unset=True`, the JSON body for every project that has no sourcedata-only
subject — which is every project except the one this lane exists to fix — is **byte-identical**
to what it was before this lane touched anything. This was not the first design tried: setting
`has_sourcedata: bool = False` on every row broke `tests/test_server_skeleton.py::test_catalog_subjects`,
an **exact-dict** assertion in a file D0 owns (`tests/test_server_*`), not FX5. Rather than either
edit another lane's file or leave the host gate red, the sparse-key redesign makes the two
compatible with **zero** cross-lane touch — confirmed: `test_server_skeleton.py::test_catalog_subjects`
passes unmodified in the final host run below. `subject_detail()` (a plain-dict route, no pydantic
model, no exact-dict test anywhere) keeps `has_sourcedata` always present (`True`/`False`) — no
such trick needed there.

## Contract check (P8-style verification, "add optional fields only")

```
python3 dev/build_contract.py                                          # openapi.v1.yaml -> openapi.v1.json
python3 dev/contracts_check.py contracts/openapi.v0.yaml contracts/openapi.v1.json
  -> OK — 10 operation(s) and 9 schema(s) from openapi.v0.yaml are present in openapi.v1.json
python3 -m tit.server --dump-openapi /tmp/dump.json --project .        # a real, live FastAPI dump (works host-side)
python3 dev/contracts_check.py contracts/openapi.v1.json /tmp/dump.json
  -> same 39 pre-existing gaps as before this lane's changes (dict/list-typed routes with no
     pydantic model — Report, JobStatus, Event, ... — and one enum on LockConflict.kind/PlanJob.kind
     the dump can't describe from a bare-dict response); grep for "subject"/"has_sourcedata" in the
     output: zero hits. Not introduced or touched by this lane; not fixed by this lane (out of scope
     — FX2/FX3-shaped, `tit/server/**`/`tit/jobs/**` ownership).
```

`npm run gen:api` regenerated `schema.d.ts`; confirmed `Subject.has_sourcedata?: boolean` present
with its description carried through from the YAML.

## Real verification against the shared container

**Container restarts: 1.** `tit/catalog.py` and `tit/server/routes/catalog.py` are server-side —
checked `GET /api/jobs` first (waited out two other lanes' jobs, `mex`/`source`, until 0 active),
`docker restart ti-toolbox-fad740e5-tit-1`, healthy again in **2 s**. Every Python change in this
lane landed before that one restart (batched, per the shared rule).

**Renderer**: `npm run build`, then `docker cp desktop/out/renderer/. ti-toolbox-fad740e5-tit-1:/opt/ti-toolbox/ui/`
(S2's own documented gotcha: the container serves a static, image-baked copy, not the bind mount)
— done once, immediately before the restart above, so the restart and the renderer swap land in
the same window with jobs still confirmed at 0.

Direct API check right after the restart, before touching the UI at all:

```
GET /api/catalog/subjects        -> sub-102: has_raw=false, has_sourcedata=true (also true, unsurprisingly,
                                     for 101/ernie/MNI152 — the DICOM pipeline leaves the sourcedata/ copy
                                     in place after conversion — and for "sub-test", the dataset's other
                                     sourcedata-only subject the project memory already knew about)
GET /api/catalog/subjects/102    -> has_raw=false, has_sourcedata=true, has_m2m=false, ...
```

### Real e2e run (`tests/e2e/real/preprocess.spec.ts`, `--project real`)

First attempt (before a fix, kept as evidence the pre-flight guard works as designed): the
sub-102 test failed at its own pre-flight check —
`derivatives/ti-toolbox/reports/sub-102` already existed (a genuine, pre-existing April-2026
report on this dataset, unrelated to any smoke run). Correct behaviour, not a bug: the test
refused to touch it rather than guessing. Redesigned cleanup to match `tests/smoke/cleanup.py`'s
actual discipline for a **shared** directory — `claim_produced`, not a whole-directory claim: only
`sub-102` (project root) and `derivatives/SimNIBS/sub-102` are required to not pre-exist and
deleted whole; the reports directory is left alone and only the file(s) this run's own jobs wrote
(mtime at/after the Run click) are removed.

Second attempt (with the redesigned cleanup) passed, but a leftover survived: the trailing
`report` job's own report file was written by the server *after* `finally`'s `readdirSync`
snapshot, since the test only waited for the `pre` (G1) job's terminal state, not the group's
`report` job. Fixed by also waiting for the trailing `report` job to reach a terminal state before
cleanup runs. Removed the stray file by hand once
(`pre_processing_report_20260904_012532.html`), confirmed only the genuine April 2026 report
remained, then reran.

Third attempt — the run of record:

```
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=devtoken TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test tests/e2e/real/preprocess.spec.ts --project real
```

```
✓ tissue analysis on sub-101: accepted, started, and completed with a real artifact  (1.4m)
✓ sub-102 DICOM onboarding: not converted -> plan -> run -> converted (lane FX5)     (25.1s)
2 passed
e2e-quiet-check: PASS (no new Electron/Chromium window reached the screen)
```

The sub-102 test, exactly: the batch table lists `102` with a "not converted" chip (bug
confirmed fixed, in the page, not just the API); plan shows `plan-cell-102-G1` = `new`; Run
submits `POST /api/jobs/groups` (`kind: "pre"`, `subject_ids: ["102"]`, recorded to
`tests/smoke/payloads/pre_dicom.json` for lane S1); the `pre` job reaches `succeeded` with an
artifact that exists on host; `GET /api/catalog/subjects` afterward shows `has_raw: true` for
102; the group's trailing `report` job also succeeds. Cleanup verified on host afterward:
`sub-102/` and `derivatives/SimNIBS/sub-102/` gone, `derivatives/ti-toolbox/reports/sub-102/`
holds only the original April-2026 file, `GET /api/catalog/subjects/102` back to
`has_raw: false, has_sourcedata: true` — the exact pre-test state.

`derivatives/ti-toolbox/logs/sub-102/` accumulates a small log file per run and is **not**
cleaned up — deliberately: `tests/smoke/matrix.py`'s own `pre_dicom` row's `creates=` list does
not include it either (dozens of pre-existing entries already there from every lane's real runs
today), so this matches the workflow's own established convention rather than diverging from it.

## Gates

| Gate | Result |
|---|---|
| `python3 -m pytest -q` (host, smoke deselected) | **3344 passed, 18 skipped, 21 deselected, 38.59 s** — includes `tests/test_catalog.py`/`test_catalog_v1.py`'s new tests; `test_server_skeleton.py::test_catalog_subjects` (D0's exact-dict test) passes **unmodified** |
| `tests/test_catalog.py` + `tests/test_catalog_v1.py` alone | 69 passed, 1.4 s |
| `desktop: npm run typecheck` | 0 errors |
| `desktop: npm run lint` | 0 errors, 3 pre-existing warnings (unrelated files, per D0's notes) |
| `desktop: npx vitest run` | **61 files, 716 passed** (+3 new: `subjects-readiness.test.ts`'s sourcedata-only describe block) |
| `desktop: npm run build` | ✓ built in ~2 s |
| `dev/contracts_check.py` (both directions) | OK; zero new gaps from `has_sourcedata` |

## New tests (each fails without its fix)

- `tests/test_catalog.py`: `test_sourcedata_only_subject_appears_in_list_subjects`,
  `test_sourcedata_only_subject_not_duplicated_once_onboarded`,
  `test_sourcedata_dir_without_valid_series_is_ignored`,
  `test_sourcedata_only_subject_ids_natural_sort`,
  `test_subject_detail_for_sourcedata_only_subject`,
  `test_subject_detail_still_unknown_without_any_raw_data` (+ `test_list_subjects` kept as the
  exact pre-FX5 shape, proving the sparse-key design).
- `tests/test_catalog_v1.py`: `test_sourcedata_only_subject_reachable_through_the_routes` (full
  HTTP round trip through `TestClient`); `test_subject_detail`'s existing assertions gained
  `has_sourcedata is False` for `ernie`.
- `desktop/tests/unit/subjects-readiness.test.ts`: `notConverted is true only for a subject
  staged under sourcedata/ with no BIDS dir yet`, `the preprocess stage stays reachable for a
  sourcedata-only subject, not blocked`, `a subject with neither raw nor sourcedata is still
  blocked with 'no raw MRI'`.
- `desktop/tests/e2e/real/preprocess.spec.ts`: the sub-102 onboarding test itself is the
  end-to-end proof (real container, no mock).

## Scope notes / what was deliberately not touched

- `app/subjectContext.ts`'s shared `presenceChips()` (used by the switcher, the command palette
  and every other page's subject picker) was **not** touched — the "not converted" indicator is
  built locally in `pages/subjects/index.tsx` and `pages/preprocess/index.tsx` (both mine), so no
  other page's subject picker changed behaviour. A subject with `has_sourcedata` but no BIDS dir
  now simply appears in every `getSubjects()`-driven picker across the app (results, viewer,
  jobs, the stats/nilearn panels, ...) exactly the way a raw-only subject with nothing else built
  yet already did — not a new class of "looks broken", just one more subject in the list.
- `tests/e2e/subjects.spec.ts` and its mock fixture `desktop/tests/fixtures/subjects.json` were
  **not** touched: neither is in this lane's ownership, and both are shared by dozens of other
  lanes' e2e screenshot goldens (the `tests/e2e/artifacts/` tree has hundreds of
  `subjects*.png` files from many prior lanes) — adding a fixture subject would have risked
  shifting counts/screenshots well outside this lane's scope. The Subjects-page "not converted"
  rendering therefore has unit-level coverage of its logic (`notConverted`, `readiness()`) and
  real-server proof that the underlying data is correct, but no dedicated mock-based e2e/screenshot
  test of the RAW-column dot or readiness-board chip specifically. Worth a small follow-up for
  whoever next touches `tests/fixtures/subjects.json` for an unrelated reason.
- `desktop/tests/e2e/_helpers.ts` (S2's file) was not touched; the sub-102 test's cleanup helpers
  live locally in `preprocess.spec.ts` since `cleanupSmokeOutputs` there is deliberately restricted
  to "smoke"-named paths and `sub-102`/`derivatives/SimNIBS/sub-102` are not smoke-tagged names.

## Open issues

None blocking. One informational note, not a defect: `derivatives/ti-toolbox/reports/sub-102/`
already carried a pre-existing report dated April 2026 before this lane ran anything — evidence
the dataset's sub-102 was fully converted and reduced back to sourcedata-only at some point before
this workflow began (consistent with the maintainer's brief describing Dataset 000 as a live,
evolving project, not a fresh fixture).

## Requests to other lanes

None. This lane's contract change is additive-only and required no other lane's file (see the
exact-dict trick above, which exists specifically to avoid needing one).

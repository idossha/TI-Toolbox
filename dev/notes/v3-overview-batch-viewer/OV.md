# Lane OV — R1: replace Subjects with a project Overview (2026-09-05)

Plan of record: `desktop/IMPLEMENTATION_PLAN.md` §R1. Branch `feature/v3-electron-gui`, worktree
`.claude/worktrees/v3-electron-gui`. **Nothing committed** (per LANES.md).

## What changed

### Server — one bounded aggregate read

| File | Change |
| --- | --- |
| `tit/server/routes/overview.py` | **new.** `GET /api/catalog/overview`: `build_overview(pm, jobs)` aggregates every Overview fact for the whole project — presence per subject, EEG nets/leadfields, output counts, per-stage readiness, project coverage/totals — over `tit.catalog`'s own discovery helpers (`list_subjects`, `subject_detail`, `flex_runs`, `ex_runs`, `analyses`) plus `pm.list_simulations`. No new discovery rules. |
| `tit/server/schemas.py` | **appended:** `PresenceState`, `OverviewCounts`, `OverviewReadiness`, `OverviewSubject`, `OverviewCoverage`, `OverviewTotals`, `Overview`. |
| `tests/test_server_overview.py` | **new**, 10 tests: the pure state machine (`presence`, `job_states_by_subject`) plus the route over a real temporary project tree (ernie/101/102-sourcedata-only) through `TestClient`. |

- **No `tit/server/app.py` edit was needed** — `tit/server/routes/__init__.py` auto-discovers every
  module in the package, so adding the file mounts the route. (The lane brief anticipated a
  one-line registration; there is none to make.)
- **Import cost:** `tit.catalog`, `tit.paths` and the job manager are imported *inside* the handler;
  module import is `fastapi` + this package's schemas only.
- **Five distinguishable states.** `present · absent · partial · pending · failed`. What is on disk
  always wins; only an absent artefact can be `pending`/`failed`, and those come from the job
  manager's own newest-first listing (`pre` → the pre-processing columns, `leadfield` → leadfield),
  with a succeeded rerun clearing an older failure and an active job outranking one. `partial` is
  real: raw staged under `sourcedata/` but never converted, and "some but not all of this subject's
  EEG nets have a leadfield".
- **Bounded:** exactly one `GET`, plus one `list_jobs()` call inside it. Nothing per-subject crosses
  the wire.

### Contracts

`contracts/openapi.v1.yaml` (authored) → `python3 dev/build_contract.py` → `contracts/openapi.v1.json`
→ `pnpm run gen:api` → `desktop/src/renderer/api/schema.d.ts`. One new path + seven new schemas,
additive only; `contracts/SCHEMA-CHANGES.md` carries the dated entry (2026-09-05 — OV).
`GET /api/catalog/subject-info` is left in the contract on purpose: removing it is breaking, and it
belongs to the API's next versioned cleanup.

### Desktop

| File | Change |
| --- | --- |
| `pages/subjects/` → `pages/overview/` | renamed. `index.tsx` (page id/title/icon/purpose now `overview` / "Overview" / `LayoutGrid`), `readiness.ts` → `model.ts`, `subjects.css` → `overview.css`, `api.ts` now reads the aggregate endpoint. All `subjects-*` test ids/classes are `overview-*`. |
| `pages/overview/model.ts` | presentation only. The arithmetic it used to do (coverage, readiness, per-stage totals) is the server's now; what is left is how a `PresenceState` reads (kind, pulse, title), the column order, the stage cards and the status cell. |
| `pages/panel-subject-info/`, `pages/panels/subject-info/` | **deleted** (page, shim, api, PARITY). |
| `pages/panels/_shared.ts` | `PanelId` loses `"subject-info"`. |
| `pages/settings/index.tsx` | the Subject Info toggle is gone from `PANEL_INFO`; `PARITY.md` records why and that a stale saved id still loads. |
| `app/registry.ts` | `NAV_ORDER[0] = "overview"`; landing-page comment updated. Cmd+1, first launch, catch-all, rail and palette all derive from this one array + `landingPage()`, so no other routing edit was needed. |
| `pages/results/useOutputs.ts` | doc comment only: it is no longer the source of any project-wide count, so `EAGER_SUBJECT_LIMIT` can no longer blank one. |
| `pages/help/KeyboardTab.tsx` | **one word**, outside my ownership list, flagged below. |

### Tests / fixtures

- `desktop/tests/fixtures/overview.json` — the 3-subject mock project.
- `desktop/tests/mock-server/server.mjs` — serves `GET /api/catalog/overview`; `makeLargeOverview(30)`
  builds the 30-subject project deterministically (spending its rows on all five presence states);
  `POST /api/__mock/project {"subjects": 3|30}` switches between them (mock-only, like `__mock/reset`).
- `desktop/tests/mock-server/contract.test.ts` — exercises the new operation.
- `desktop/tests/unit/overview-model.test.ts` — **new** (8 tests), replaces `subjects-readiness.test.ts`.
- `desktop/tests/unit/shell-registry.test.ts` — page id `subjects` → `overview`.
- `desktop/tests/e2e/overview.spec.ts` — **new** (7 tests, two of them the gate), replaces `subjects.spec.ts`.
- Existing specs updated only where they named the old route/testids: `smoke`, `help`, `gallery`,
  `results`, `jobs`, `page-memory`, `layout`, `screens`, `panels-shape`, `panels-forms`, `table-room`,
  `quick-notes`, `native-launch`, `viewer`, `viewer-real`. `panels.spec.ts` was **deleted** — its only
  test was the Subject Info panel.

## Gate test

> *In mock projects containing 3 and 30 subjects, opening Overview makes exactly one overview catalog
> request, renders every subject and every defined presence/count column, and Cmd+1, first launch,
> catch-all, rail, and palette all resolve to `/overview`. No Subject Info route or toggle is
> discoverable.*

```
$ cd desktop && npx playwright test tests/e2e/overview.spec.ts
Running 7 tests using 1 worker
  ✓  1 … is the coverage strip, the presence matrix and the readiness rows — no page header (4.5s)
  ✓  2 … GATE: one overview request renders every subject and every column — at 3 subjects and at 30 (9.1s)
  ✓  3 … GATE: first launch, Cmd+1, the rail and the palette all resolve to Overview; Subject Info does not exist (4.7s)
  ✓  4 … the detail pane exists only when a row is selected, and links into Results (4.5s)
  ✓  5 … the filter and the scope segments narrow the table (4.5s)
  ✓  6 … a run verb navigates, scoped to the selected subject (4.6s)
overview parts: readiness 10.5% · table 19.3% · detail 47.5%
overview dead space: unselected 1280x800 15.4% · … · populated 1440x900 24.7%
  ✓  7 … hits its §12.3 numbers at 1280x800 and 1440x900, light and dark (5.1s)
  7 passed (38.0s)
```

What test 2 asserts, precisely: `page.on("request")` counts `/api/catalog/overview` requests; it is
**1** after the 3-subject page has fully rendered and **1** again after relaunching against the
30-subject project; all eight presence columns and all three count columns appear in the header; all
3 / all 30 rows render (including `S026`–`S030`, past the old 25-subject eager cap) with their eight
dots and their counts; and all five presence states are visible as five different labels in the
30-subject project.

Test 3 covers first launch, Cmd+1, the rail's first row (`railIds[0] === "overview"`) and the
palette. **Catch-all**: the app is a `MemoryRouter` with no address bar, so a bogus path cannot be
typed in an e2e run; `App.tsx`'s `path="*"` element is `<Navigate to={landingPage().id}>` and is
unchanged, and `tests/unit/shell-registry.test.ts` proves `landingPage()?.id === "overview"` and that
no page claims `panel-subject-info`, so `/panel-subject-info` falls through to `/overview`. Test 3
also asserts the palette has no "Subject info" option and Settings has no such checkbox.

### Other commands run

| Command | Result |
| --- | --- |
| `python3 -m pytest tests/test_server_overview.py -q` | 10 passed |
| `python3 -m pytest tests/test_server_overview.py tests/test_catalog.py tests/test_catalog_v1.py -q` | 79 passed |
| `python3 dev/route_import_guard.py` | 19 modules clean; `overview` **18.6 ms** (budget 400 ms) |
| `pnpm run typecheck` | clean for my files (3 pre-existing errors in another lane's `run/jobGroups.ts`, `preprocess/api.ts`, `simulator/index.tsx`) |
| `pnpm run lint` | 0 errors, 4 pre-existing warnings |
| `npx vitest run tests/unit` | 77 files, 859 passed |
| `npx vitest run tests/mock-server` | 29 passed, 1 failed — **another lane's**: five `/api/guide/*` paths are declared in the contract with no mock route yet. `/api/catalog/overview` is exercised and not in the diff. |
| `npx playwright test tests/e2e/{smoke,help}.spec.ts` (after the fixes) | 9 passed, 1 failed — `smoke.spec.ts:161` ("the rail's icon/label breakpoint … while the Viewer streams") fails selecting a `Thalamus` option in the Viewer's source bar. **Not mine**: `npx playwright test tests/e2e/viewer.spec.ts` is 18/18 green including that lane's new draft/Load specs, i.e. smoke's inline Viewer dance predates the Viewer lane's R5 rework. |
| `npx playwright test tests/e2e/results.spec.ts` | passed |
| `npx playwright test tests/e2e/viewer.spec.ts` | 18 passed |
| `npx playwright test tests/e2e/{page-memory,table-room}.spec.ts` | 13 passed, 3 failed — all three are Viewer-iframe tests (`tetravox-frame`, "keeps session-only page state", "preserves the live viewer session", "Results deep links replace the retained viewer selection"), i.e. the Viewer lane's R5 rework. The Overview-touching case in that file (row click → Open in Results) passes. |

### Real container (Dataset 000, `ti-toolbox-fad740e5-tit-1`, port 8765)

```
$ curl -s -H "Authorization: Bearer <TIT_SERVER_TOKEN>" http://127.0.0.1:8765/api/catalog/overview
101    raw=present m2m=present fastsurfer=absent leadfield=partial  {'simulations': 3, 'optimizations': 10, 'analyses': 2}
102    raw=partial m2m=absent  …                                    reasons: no head model / no simulations
ernie  raw=present m2m=present leadfield=partial                    {'simulations': 6, 'optimizations': 12, 'analyses': 7}
MNI152 raw=present m2m=present leadfield=absent                     {'simulations': 1, 'optimizations': 3, 'analyses': 0}
test   raw=partial m2m=absent  …
totals: 5 subjects · 10 simulations · 25 optimizations · 9 analyses
        coverage raw 3/5 · recon 2/5 · m2m 3/5 · dwi 0/5 · leadfield 2/5
```

Correct on real data, including the two sourcedata-only subjects (`102`, `test`) that
`list_all_subjects()` sees and `subject_ids()` does not. Timing: **3.4 s cold, 0.12–0.13 s warm**
(three consecutive calls). The cold cost is the flex/ex manifest reads over 25 optimization runs.

## Open items

1. **`pages/help/KeyboardTab.tsx`** — I changed one word (`[modKey("1"), "Subjects"]` →
   `"Overview"`), outside my ownership list. It is the keyboard sheet's label for the Cmd+1 target,
   which R1 moved; leaving it would have printed a page name that no longer exists. Revert and
   re-home it if the help lane objects.
2. **`tit/server/routes/settings.py`'s `_VALID_PANELS` still accepts `"subject-info"`** — deliberate
   and not mine to change: a project `settings.json` that lists it must keep loading, and with no
   page claiming the id the registry ignores it (which is exactly the "stale saved panel ids are
   ignored" requirement). A later cleanup can drop it from that frozenset.
3. **Overview cold latency** (3.4 s on a 5-subject project with 25 optimization runs) is manifest
   parsing inside `catalog.flex_runs`/`ex_runs`/`analyses`. If a large project makes this bite, the
   fix is a counts-only path in `tit.catalog` (directory counts without manifest reads), not more
   requests. Not needed for Dataset 000.
4. **Cross-lane failures observed, not fixed**: `run/jobGroups.ts` + `preprocess/api.ts` +
   `simulator/index.tsx` typecheck errors and `tests/unit/subjects-in-parallel.test.tsx` (5 failures,
   `Invalid URL` in `submitJobGroup`) belong to the batch lane; the five undeclared `/api/guide/*`
   mock routes belong to the guide lane.
5. `desktop/DESIGN.md` §9/§10 still describe Subjects as the first rail item — reworded below for
   the consolidation lane, not edited here.

## Proposed record entries

**`docs/DECISIONS.md`**

> **2026-09-05 — the app opens on a project Overview, and Subject Info is deleted.** The first rail
> item, the Cmd+1 target, the initial route, the catch-all destination and the palette's first page
> are `overview`. The Subjects page is its starting implementation, reshaped to answer the project
> question rather than the per-subject one. Its facts come from one `GET /api/catalog/overview`
> whose request count does not grow with subjects, simulations or outputs — the fan-out it replaced
> was capped at 25 subjects in the renderer and therefore silently rendered no counts for a larger
> project. Presence is now five distinguishable states (`present · absent · partial · pending ·
> failed`), because "staged but not converted", "running right now" and "the last run failed" are
> three different answers that one boolean swallowed. The Subject Info panel, its page id, its
> Settings toggle and its fixtures are removed; `/panel-subject-info` falls through to `/overview`
> and a stale saved panel id is ignored. `GET /api/catalog/subject-info` stays in the contract until
> the API's next versioned cleanup. Results remains the only detailed outputs browser: Overview
> carries counts, never trees or previews.

**`docs/ARCHITECTURE.md`** (contract amendment, §catalog)

> `GET /api/catalog/overview` → `Overview` is the project Overview page's single read. It is the one
> catalog endpoint that aggregates across subjects; every other catalog route stays per-subject and
> lazy. Server-side aggregation is required, not an optimisation: a client-side fan-out cannot state
> a project-wide count without a per-subject request budget. `PresenceState` (`present`, `absent`,
> `partial`, `pending`, `failed`) is the vocabulary for "does this subject have X"; `pending` and
> `failed` are derived from the job scheduler's records and only ever describe an artefact that is
> still absent.

**`docs/ROADMAP.md`**

> - [x] R1 — Overview replaces Subjects; one aggregate catalog endpoint; Subject Info deleted (OV, 2026-09-05).

**`desktop/DESIGN.md` §9 (rail) — proposed rewording**

> The rail's first row is **Overview** (⌘1), the app's landing page and its catch-all destination:
> the project's coverage, its presence matrix, and who can run what next. It is not subject-scoped —
> a subject is chosen in the context bar or on a page's own batch table.

**`desktop/DESIGN.md` §10 — proposed rewording**

> Overview shows, per subject, raw staged/converted, FastSurfer, FreeSurfer, m2m, DWI, CT,
> leadfields, EEG nets and high-level totals for simulations, optimizations and analyses, in five
> presence states. It links into a workflow or into Results; it never lists outputs itself.

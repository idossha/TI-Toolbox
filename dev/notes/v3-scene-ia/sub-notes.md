# Lane SUB — one subject grammar (plan §3, J1–J4)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Nothing committed, nothing staged. Every Electron/Playwright run below went through
`TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh`; each individual run reported **PASS** (one
whole-suite run did not — §6, and it is another lane's spec).

## 0. What was there, measured before touching anything

| Page | Control | Blocked wording for "this subject cannot run" |
|---|---|---|
| `pages/preprocess/index.tsx` | local `SubjectTable` (`<tr class="subject-picker-row">`), always open, `presenceChips()` + a "not converted" chip | none (no eligibility at all) |
| `pages/simulator/index.tsx` | one-line summary → `FormSection` + `ui/SubjectPicker` (label rows), Select all / none / Done | none — an m2m-less subject was **silently dropped** by `eligibleSubjectsFor` on the way to the plan |
| `pages/optimizer/index.tsx` | `Field label="Subjects"` + `ui/Combobox`'s `MultiSelect`, inside the method row | two page-local sentences: `No <net> leadfield for 101 — generate it, or deselect that subject.` / `This target is not available for 101 — …` |
| `pages/analyzer/AnalyzerPage.tsx` | one-line summary → `FormSection` + `ui/SubjectPicker`, one "sim" chip | none — Subject scope ticked N and analysed the **first** (`effectiveSubjectIdsFor`) |
| `pages/panels/source/index.tsx` | `ui/SubjectPicker`, list **filtered** to `has_m2m` | none — a subject without a head model simply did not appear |
| `pages/panels/{nifti-group-average,cluster-permutation,nilearn-visuals}` | per-row `(subject, simulation, group/response/effect)` tables | n/a (see §4) |
| `pages/panels/subject-info` | `ui/DataTable` browse + export | n/a (see §4) |

Four vocabularies, three disclosure behaviours, two "why is this disabled" styles, and two pages
where an unusable subject was hidden or dropped rather than explained.

## 1. What was built

`desktop/src/renderer/pages/_shared/subjects/` (555 lines incl. CSS):

- `types.ts` — `SubjectsFieldProps` exactly as the brief names them (`subjects`, `value`,
  `onChange`, `columns`, `eligibility`, `mode`), plus `defaultOpen`, `help`, `loading`,
  `emptyMessage`.
- `model.ts` — the pure core: `subjectsSummary` (J1 line + J4 semantics), `filterSubjects`,
  `toggleSelection`, `selectAll`, `blockedSubjects`, `subjectsBlockedReason`.
- `columns.ts` — `presenceColumns({dwi, ct})` (RAW/FS/FSR/M2M/DWI/CT, the same booleans and the
  same words as `app/subjectContext.ts`'s `presenceChips`) and `notConvertedColumn()`.
- `SubjectsField.tsx` — summary line + `Change subjects…` disclosure + filter + select-all +
  one row per subject + per-row reason.
- `subjects.css`, `index.ts`.

Rendered grammar, identical on five pages:

```
Subjects   3 subjects · 101, ernie, MNI152 · one job per subject     [ Change subjects… ]
[ filter subjects… ]                                                 [ Select all / none ]
☑ | Subject | Present                    | Why not
☑ | ernie   | raw fastsurfer ·fsr· m2m   |
☐ | 101     | raw ·fastsurfer· m2m       | no EEG10-10_UI_Jurak_2007 leadfield
```

Testids (the shared contract `tests/e2e/_subjects.ts` drives): `subjects-field`
(`data-mode`/`data-open`/`data-selected`), `subjects-summary`, `subjects-change`,
`subjects-filter`, `subjects-select-all-button`, `subjects-field-table`, `subject-row-<id>`
(`data-eligible`/`data-selected`), `subject-reason-<id>`.

## 2. Decisions, and the failure each prevents

| # | Decision | Failure it prevents |
|---|---|---|
| D1 | **One component, five adoptions**, and the four bespoke controls plus `ui/SubjectPicker.tsx` are **deleted** (its two types moved to their producer, `app/subjectContext.ts`; `ui/index.ts` and `dev/Gallery.tsx` updated). | A second way to do it surviving in the design-system gallery, which is how the third vocabulary appeared in the first place. |
| D2 | **Not a `FormSection`.** The control renders its own header row. | `ui/Layout.tsx`'s section registers with `RunWork`'s fill controller, which Simulator and Analyzer both measured oscillating a subject table open/closed once later content grew after mount. Each page still wraps it in its own `data-tier="1"` div, which is the contract `_metrics.ts`'s `firstScreenControls` reads. |
| D3 | **A third mode, `single`.** The brief names `per-subject` and `grouped`; the Analyzer's Subject scope is neither — it submits ONE job for ONE subject (`AnalyzerConfig.subject_id`). `single` says "one job" in the summary and makes the control single-select; `setMode("single")` narrows the ticked set visibly. | The page silently analysing the first of three ticked subjects — J4's exact failure, previously hidden inside `effectiveSubjectIdsFor`. |
| D4 | **An ineligible subject is shown, tickable, and explained** — never hidden (Source used to filter them out) and never a disabled row. Its reason is the sentence the action bar and the Run button print. Select-all still skips them. | A dead control with the explanation hidden behind it, and "my subject is missing from this page", which is not a diagnosis a user can act on. First written the other way (disabled rows) — `real/ex.spec.ts` then failed on a `disabled` checkbox, which is the measurement that settled it. |
| D5 | **One blocked sentence**, `subjectsBlockedReason`: `Select at least one subject.` / `101 cannot run — no EEG10-10_UI_Jurak_2007 leadfield. Deselect it, or fix it first.` Every page's own `blockedReason` takes it as its first (or, on the Optimizer, its per-subject) clause. | Four pages inventing four blocked-state wordings, and a batch blocked by a sentence that never says which subject is the problem. |
| D6 | **Readiness is a prop.** `columns` with two kinds: `presence` (always shown, success/muted) and `flag` (warning, only when true — Pre-processing's "not converted"). | A fork per page, or a new dot vocabulary per page. |
| D7 | **Row class `.subject-picker-row` kept** on the new `<tr>`, overridden with `tr.subject-picker-row { display: table-row }` (element+class beats the `display:flex` rule in `components.css`). | Rewriting `real/preprocess.spec.ts`, `real/source.spec.ts` and four mock specs for a rename that buys nothing. |
| D8 | **Pre-processing and the Source panel open by default**; the three other run pages open on the disclosure. | Costing Pre-processing (whose whole job is batch) a click, and costing the Simulator the headroom its 4-pair mTI montage editor needs at 1280×900. |
| D9 | **Optimizer: leadfields and atlases are fetched for every project subject *with an m2m*** (was: every *ticked* subject). Readiness before ticking is the point of a readiness column; `GET /api/catalog/{leadfields,atlases}` answers **404** for a subject with no head model and React Query retries three times. | A column that cannot answer for a subject you have not ticked yet — and 14 requests per m2m-less subject per page visit (§5). |

## 3. Adoptions, and the behaviour deliberately preserved

- **Pre-processing** — full RAW/FS/FSR/M2M/DWI/CT + `not converted`; no `eligibility` (a
  sourcedata-only subject stays selectable: the DICOM stage is what onboards it, lane FX5);
  "Subjects in parallel" untouched; `Select at least one processing step.` still its second clause.
- **Simulator** — presence columns; eligibility `no head model (m2m)` with `eligibleSubjectsFor`'s
  own fallback (nothing to compare against ⇒ nothing blocked); montage rows still keyed
  `${id}:${subject}`; `useSimPlan` now takes the shared sentence (its own
  `Choose a subject to plan a simulation.` is gone — it was the only page that said that).
- **Optimizer** — control moved out of the method row to the top of the work pane (a summary line
  plus a table is not a form field); `m2m` + `leadfield` columns; both per-subject blockers
  (missing leadfield, missing atlas target) are now `eligibility`, each answering only for a
  subject whose own query has landed; the page-wide clauses (`Select an EEG net.`,
  `Generate a leadfield for this net first.`, buckets, no target) keep their order.
  `nets.ts::subjectsMissingLeadfield` deleted with its test — dead once the check became
  eligibility. `useAtlasLookups` now returns `{lookup, ready}`.
- **Analyzer** — `sim` column and eligibility from the same "has run the chosen simulation" rule
  (before a simulation is picked: "has run something"); Group mode unchanged; `blockedReasonFor`
  now takes `subjectsBlocked` instead of a count.
- **Source panel** — every subject listed, `no head model (m2m)` as the reason; the
  "No subjects with a head model yet." empty state kept for when none has one.

## 4. Panels deliberately NOT adopted (evidence, not preference)

`nifti-group-average`, `cluster-permutation` and `nilearn-visuals` do not take a *set of
subjects*: each row is a `(subject, simulation, role)` tuple — group name, response 0/1, effect
size — and **the same subject may legitimately appear twice** (`cluster-permutation`'s
`testType: "paired"` is exactly that design; `nifti-group-average`'s diff pairs likewise). A set
control cannot express that, so forcing `SubjectsField` there would remove an expressible study
design and still need a second control per row. `subject-info` is a shape-B browse table over
`tit.catalog.subject_info_matrix` with an export action, not a run's subject set.

Recorded as an open issue rather than done silently: if the program wants these three unified, the
right shape is *this control choosing who participates* plus a per-participant detail row, and
that is a change to what the panels can express.

## 5. Numbers

| Measurement | Value |
|---|---|
| New shared module | 555 lines (`SubjectsField.tsx` 222, `model.ts` 113, CSS 87, `types.ts` 68, `columns.ts` 50, barrel 15) |
| Deleted | `ui/SubjectPicker.tsx` + 4 bespoke page controls + `nets.ts::subjectsMissingLeadfield`; the five adopting files went 2398 → 2344 lines (−54 net, and that is with the Optimizer *gaining* its eligibility comments) |
| Unit tests added | 24 in `tests/unit/subjects-field.test.tsx` (pure model 15, rendered DOM 9); suite 718 → 741 (one obsolete `optimizer-nets` case removed) |
| Mock e2e, the six touched spec files, one run | **28 passed / 0 failed** (54.5 s), quiet-check PASS |
| `real/analyzer-mesh` | 1 passed (13.1 s), job `2462769127a6435a` succeeded, 5 artifacts |
| `real/ex` | 2 passed (40.9 s), job `34347a793ecb43be` succeeded, 2 artifacts — incl. the two-subject row + named blocker on real data |
| `real/sim` | 1 passed (5.5 s), TI montage accepted → started → cancelled |
| `real/preprocess` | 2 passed (1.8 min), jobs `3e6fb6f8b9bb4788` (101, tissue, succeeded) and `65ed40eee0e54d71` (102, dicom, succeeded) |
| `real/source` | **failed** — not the control (see §6) |
| Optimizer catalog requests, per `real/ex` run, container access log | before: `test`/`102` 14 each (404 + 3 retries) + 6–8 per real subject; after D9: **0** for `test`/`102`, 2 leadfield + 4 atlas per m2m subject |
| Pre-processing `firstScreenControls` | 21 total, 21 visible, `hidden: []` at 1280×800 light (the filter and select-all are new and both on the first screen) |
| Desktop gates | `npm run typecheck` **0 errors**; `npx eslint .` **0 errors** (3 pre-existing warnings); `npx vitest run` 816/817 (the one failure is not this lane — §6) |
| Host Python gate | `python3 -m pytest -q` → **3462 passed, 30 skipped, 21 deselected, 37.3 s** |

Dataset 000 after the runs: no `*smoke*` path left anywhere, `sub-101/forward/` absent,
`sub-ernie/ex-search` unchanged (`docs_ex_large`, `docs_ex_symmetric`), no job running or queued.

## 6. Bugs and failures found

1. **Fixed (mine).** `real/ex` failed against the container when ineligible rows were disabled:
   `locator.click: Timeout … <button disabled role="checkbox">`. The blocked state is the thing
   worth explaining, so it must be reachable — D4.
2. **Fixed (mine).** `expectSubjectsGrammar` counted 6 rows for 5 subjects on the Optimizer:
   `pages/_shared/roi/RoiPicker.tsx:223` renders its saved-ROI rows with the same
   `.subject-picker-row` class. The helper now scopes rows to the control. The class-borrowing
   itself is left for `_shared/roi`'s owner (open issue).
3. **Fixed (mine).** `primaryLeadfields = leadfieldQueries[0]` became wrong the moment the query
   list covered every subject rather than the ticked ones — the Ex leadfield strip would have
   stated the *first project subject's* leadfields. Now indexed by the primary subject.
4. **Fixed (mine).** D9's 404-plus-retry storm for m2m-less subjects.
5. **Not mine — `real/source.spec.ts` fails on a runtime budget.** Every UI assertion passed (job
   accepted, `subject_ids == ["101"]`, `eeg_net` without `.csv`, console lines rendering); the
   forward-solution job `b4b527c72e3c4f8e` then did not reach a terminal state within the spec's
   600 000 ms. I cancelled it from the API (state `cancelled`, 06:15:31Z) so it would not hold the
   one-FEM slot, and confirmed no `forward/` directory was left behind. The spec's `afterAll`
   deletes `FORWARD_DIR` while the job is still writing, which is worth fixing whichever way the
   budget goes.
6. **Not mine — `tests/mock-server/contract.test.ts` fails**: the OpenAPI contract now declares six
   `GET /api/scene/*` operations that the mock server does not implement (58 vs 64).
7. **Not mine — the whole-suite run hijacked the screen.** `npx playwright test` (default project,
   96 passed / 7 failed, 9.1 min) ended with quiet-check **FAIL**: "the frontmost app changed to/
   from a test binary: 'ghostty' -> 'Electron'" and windows appearing on screen. The only spec file
   failing was `tests/e2e/scene.spec.ts` (6 of the 7 failures); every spec file I ran individually,
   including all six of mine and `gallery`/`screens`, reported quiet-check PASS.
8. **Not mine — suite-order flake in `optimizer.spec.ts`.** In the whole-suite run the Flex test
   read `1 job · 8 CPU · 16 GB · 1 wait · population 13 × …` where it expects no `wait` clause: an
   earlier spec's job was still holding a lock on the shared mock server. Passes in isolation and
   in the six-file run above.

## 7. Requests to other lanes

- **LAY (phase 3)** — `SubjectsField` is a plain block, first in the work pane, wrapped by the page
  in `data-tier="1"`. If §4's skeleton wants it inside a section, wrap it there; do not give it
  `FormSection`'s `collapsible` (D2). The Simulator's and Analyzer's long-standing note stands:
  `.page-layout-main` does not reserve the sticky action bar's height in its scrollable content.
- **SCC (phase 2)** — `pages/_shared/roi/RoiPicker.tsx:223` borrows `.subject-picker-row` for
  saved-ROI rows. Rename it (e.g. `roi-saved-row`) when you are in that file; any unscoped
  `.subject-picker-row` locator on the Optimizer or Analyzer counts those rows too.
- **SCA/SCB** — items 6 and 7 above.
- **Whoever owns `real/source.spec.ts`** — item 5.

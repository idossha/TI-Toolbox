# Lane BX — R3: standardize subject selection and execution policy

Date: 2026-09-05 · Worktree `.claude/worktrees/v3-electron-gui` · nothing committed.

## What R3 asked, and what it now is

`Subjects in parallel` used to exist on exactly one page (Pre-processing) and be honest on exactly
one page. Simulator, Optimizer and the Source panel submitted a batch as an **awaited `for` loop of
`POST /api/jobs`** — one request per subject (per `(subject, montage)` on the Simulator, per
`(subject, target)` on Ex/mEx). That loop names a policy and decides nothing: the server admitted
whatever its budget allowed the moment each job landed, so "sequential" was a description of the
renderer's `await`, not of what ran.

Now every workflow that runs one independent job per subject submits **one**
`POST /api/jobs/groups` carrying `parallel_subjects`, and `tit.jobs.scheduler.evaluate` releases the
group that-many-at-a-time. The selector is open on first visit everywhere. Group Analyzer is
untouched: one job over the cohort, therefore no cap control.

## Files changed

**Server (`tit/`)**

- `tit/jobs/plans.py` — new `GROUP_KINDS` and `plan_per_subject(kind, [(subject, config)], tags,
  overwrite)`: one independent `PlannedJob` per entry, each config round-tripped through the kind's
  dataclass with `subject_id` **forced** to that entry's subject. `_KIND_CONFIG_CLASS` is a
  deliberate copy of `validate.SIMPLE_KIND_CLASS` (jobs must not import server), kept honest by a
  test. `plan_preprocessing` unchanged.
- `tit/server/routes/jobs.py` — `/api/jobs/groups` accepts every kind in `GROUP_KINDS`; `pre` still
  goes through `plan_preprocessing` (`_plan_pre_group`), the rest through `plan_per_subject`
  (`_plan_generic_group`), which also validates/expands the new optional `subject_configs`, `tags`
  and `overwrite`. A cohort kind (`analyzer`, `stats`) is a 422 with a sentence saying so.
- `tit/jobs/spec.py` — `PlannedJob.overwrite` (optional, default `False`).
- `tit/jobs/manager.py` — `submit_plan` passes `PlannedJob.overwrite` through to `submit`.
- Scheduler untouched: `group_cap` admission already did the right thing; it is now reachable from
  five more kinds.

**Contract**

- `contracts/openapi.v1.yaml` — `JobGroupRequest.kind` widened to
  `[pre, sim, flex, flex_adaptive, flex_pareto, ex, mex]`; new optional `subject_configs`, `tags`,
  `overwrite`. Additive only; a client sending the old body behaves identically.
- `contracts/openapi.v1.json` regenerated (`python3 dev/build_contract.py`),
  `desktop/src/renderer/api/schema.d.ts` regenerated (`pnpm run gen:api`),
  `contracts/SCHEMA-CHANGES.md` gained the dated `BX (batch)` entry.

**Desktop**

- `pages/_shared/run/SubjectsInParallel.tsx` (new) — the one control. `parallelSummary(1)` reads
  `sequential`, not `1 in parallel`.
- `pages/_shared/run/jobGroups.ts` (new) — `submitJobGroup(kind, config, subjectIds, cap, opts,
  client)`. Deliberately has no fan-out helper: a page that needs different configs per subject
  sends `subject_configs` in the same one request.
- `pages/_shared/run/index.ts` — exports both.
- `pages/preprocess/index.tsx` — uses the shared control (its inline `Field` + `NumberInput` is
  gone); `outputsSummary` now reads through `parallelSummary`.
- `pages/simulator/index.tsx` + `RunControls.tsx` — `defaultOpen` selector, an `Execution` section
  with the shared control, and one `POST /api/jobs/groups` with one `subject_configs` entry per
  `(subject, montage)` row replacing the per-row POST loop.
- `pages/optimizer/index.tsx` — `defaultOpen` selector, an `Execution` section, and a local
  `submitGroup()` used by all three methods, replacing both POST loops.
- `pages/analyzer/AnalyzerPage.tsx` — `defaultOpen` selector only; no cap control (comment in place
  saying why). `ParticipantsField` and stats panels untouched.
- `pages/panels/source/index.tsx` — untouched: its selector was already `defaultOpen`, and its two
  pipelines are single cohort jobs with their own `cpus`/`workers` fields, not per-subject groups.
- `pages/_shared/scene/` untouched, and the `<ScenePane …>` call sites in the page files are as
  lane GD left them.

**Tests**

- `tests/test_jobs_routes.py` — generic-group suite: per-subject isolation, `subject_configs`
  (including two jobs for one subject), 422s, cap-1 never-two-running, cap-2 reaches two.
- `tests/test_jobs_model.py` — `plan_per_subject` unit tests + the `_KIND_CONFIG_CLASS` ↔
  `SIMPLE_KIND_CLASS` drift guard.
- `desktop/tests/unit/subjects-in-parallel.test.tsx` (new) — the control's DOM and the one-request
  guarantee (a fetch spy counts calls).
- `desktop/tests/mock-server/server.mjs` — group route generalized (per-subject configs, subject-id
  forcing, 422s); `server.test.ts` gained three cases for it.
- `desktop/tests/e2e/batch.spec.ts` (new) — the gate, below.
- Minimal edits to existing specs: `optimizer.spec.ts` (now asserts one group request with
  `subject_configs`), `simulator.spec.ts` / `analyzer.spec.ts` (selector open on first visit, then
  closed explicitly), `tests/unit/preprocess-defaults.test.ts` (the `sequential` wording).

## Gate test and evidence

Plan's R3 gate, clause by clause.

| Clause | Where | Result |
| --- | --- | --- |
| shared selector shown on first visit of every subject-taking workflow | `batch.spec.ts` tests 1–5 (preprocess, simulator, optimizer, analyzer, Source panel; fresh user-data dir) | pass |
| two subjects → two plan rows | `batch.spec.ts` "two subjects produce two plan rows" | pass |
| no client-side parallel POST substitution | `batch.spec.ts` "the cap goes to the server in ONE request…" — records every `POST /api/jobs*`, expects exactly 1 | pass |
| cap 1 never >1 group member `running` | `batch.spec.ts` "a cap of 1…" (peak asserted `=== 1`, not just `<= 1`) and `tests/test_jobs_routes.py::test_group_cap_of_one_never_runs_two_members_at_once` | pass |
| cap 2 allows two when resources/locks permit | `batch.spec.ts` "a cap of 2…" and `::test_group_cap_of_two_admits_two_members_at_once` | pass |
| config subject-id isolation | `batch.spec.ts` "each generated config carries exactly its own subject id" and `::test_sim_group_is_one_job_per_subject_with_isolated_configs` | pass |

Commands and actual output:

```
$ python3 -m pytest tests/ -q
3655 passed, 47 skipped, 21 deselected, 13 warnings in 55.29s

$ python3 -m pytest tests/test_jobs_routes.py tests/test_jobs_model.py -q
24 passed + 56 passed

$ python3 dev/route_import_guard.py
route_import_guard: 20 route module(s) clean

$ cd desktop && npx vitest run
Test Files  79 passed (79) · Tests  892 passed (892)

$ cd desktop && pnpm run lint
✖ 4 problems (0 errors, 4 warnings)        # all pre-existing react-compiler/incompatible-library

$ cd desktop && pnpm run typecheck
clean except tests/unit/subjects-readiness.test.ts (lane OV: it imports pages/subjects/readiness,
which that lane is deleting) — not this lane's file, reported not fixed

$ cd desktop && npx playwright test tests/e2e/batch.spec.ts
10 passed (9.1s)

$ cd desktop && npx playwright test tests/e2e/optimizer.spec.ts tests/e2e/analyzer.spec.ts tests/e2e/simulator.spec.ts
17 passed (25.6s)

$ cd desktop && npx playwright test tests/e2e/preprocess.spec.ts tests/e2e/panels.spec.ts \
    tests/e2e/panels-forms.spec.ts tests/e2e/controls-consistency.spec.ts \
    tests/e2e/table-room.spec.ts tests/e2e/page-memory.spec.ts
27 passed, 3 failed — all three failures are `page-memory.spec.ts` viewer cases waiting for
`tetravox-host[data-viewer-status="ready"]` and getting `idle` (R5's explicit-load change, lane
VW). Not this lane's files; noted, not touched.
```

Why the cap is proved on the mock server and not on the shared container: the pipelines program's
standing rule is that two FEM simulations must never run concurrently there
(`dev/notes/v3-pipelines/RUNBOOK.md`), so a real-data proof of a cap of 2 would be exactly the thing
that rule forbids. The cap logic is asserted twice instead — against the real
`tit.jobs.scheduler.evaluate` in `tests/test_jobs_routes.py` (fake-runner jobs, real manager), and
against the mock's mirror of it from the UI in `batch.spec.ts`.

## Open items

1. **Source panel.** `source` is not in `GROUP_KINDS`: both of its pipelines are single jobs over
   the whole selection with their own `cpus`/`workers` fields, so a per-subject cap would be a
   second, conflicting knob. If a later pass makes forward-solution building one job per subject,
   `source` joins the enum and `SubjectsInParallel` replaces its `Workers` field. Flagged, not done.
2. **Cap semantics are job-count, not distinct-subject.** Unchanged from the existing contract, and
   now visible on the Simulator, where one subject with three montages is three jobs: a cap of 2
   can run two montages of the *same* subject together. The lock layer (`tit.jobs.locks`) is what
   keeps that safe; the control's help says "how many of this batch's jobs run at once" there
   rather than pretending it counts subjects. If subject-count semantics are wanted, that is a
   scheduler change plus a contract note, not a UI change.
3. **`tests/unit/subjects-readiness.test.ts`** fails typecheck against lane OV's in-flight deletion
   of `pages/subjects/`. Left alone.
4. **Simulator's `Execution` section** is a new collapsible section on that page; if the layout lane
   is counting `firstScreenControls`, the measured runs above were green at 1280x800 and 1440x900
   (`simulator.spec.ts`'s acceptance test passed), but it is worth a look in the consolidation pass.

## Proposed record entries (for the consolidation lane to land)

**`docs/DECISIONS.md`**

> **2026-09-05 — Batch execution is a scheduler cap, not renderer request timing.** Every workflow
> that runs one independent job per subject submits one `POST /api/jobs/groups` with
> `parallel_subjects`; `tit.jobs.scheduler.evaluate` enforces it as an admission cap on how many of
> the group's jobs are `running`. A `Promise.all` or an awaited POST loop is explicitly not an
> implementation of sequential or parallel execution and is removed from the Simulator and the
> Optimizer. Consequence: `JobGroupRequest.kind` widens beyond `pre` to `sim`, `flex`,
> `flex_adaptive`, `flex_pareto`, `ex`, `mex`, and grows optional `subject_configs`/`tags`/
> `overwrite`. Cohort kinds (grouped `analyzer`, `stats`) stay on `POST /api/jobs` — one job, no cap.

**`docs/ARCHITECTURE.md` (§ jobs / contract amendment)**

> `/api/jobs/groups` is the batch seam for every per-subject kind. The request carries one template
> `config` plus optional `subject_configs` for workflows whose config depends on the subject; the
> server forces each generated config's `subject_id` to its own subject, so subject isolation is a
> server guarantee and not a client convention.

**`desktop/DESIGN.md` (§ run pages)**

> `SubjectsField` is open by default on every subject-taking workflow. Beside it, every workflow
> that produces one job per subject shows the shared `Subjects in parallel` control: `1` sequential,
> `N` up to N concurrent, enforced by the server. A workflow that produces one job over the whole
> selection (grouped Analyzer, statistics) shows no such control.

**`docs/ROADMAP.md`**

> R3 (subject selection + execution policy) closed 2026-09-05 — evidence in
> `dev/notes/v3-overview-batch-viewer/BX.md`.

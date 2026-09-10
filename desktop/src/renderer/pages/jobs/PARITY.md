# Jobs — parity checklist

No PyQt tab is the source here: 2.x has no persistent job registry, only per-tab progress bars and
a `BaseProcessThread` per running subprocess (each tab tracked its own job and forgot it on close).
The parity source is `TODO.md` §2.3 ("Job model") and §2.5 ("Live monitoring") — the job registry
and the live-monitoring behaviour v3 is adding, not replacing.

## Controls

| Spec requirement (lane brief / TODO §2.5) | v3 implementation | Status |
|---|---|---|
| Full table: state chip, kind, subjects, stage progress or LivenessBadge, elapsed, CPU%/RSS, waiting_on link, Stop, Rerun, Force, Delete | `DataTable` in the "All jobs" tab (state/kind/subjects/stage-or-liveness/elapsed/CPU/RSS/waiting-on columns); Stop/Rerun/Force/Delete live in the row's detail drawer rather than as table-row buttons — see gap 1 | Done, with a documented simplification |
| Filters: state / kind / subject | Three `Select`s above the table, client-side filtered against the merged (REST + live) job list | Done |
| Group jobs as subject → stage trees | "Groups" tab (`GroupsView.tsx`): `group_id` → subject → ordered stage `JobStatus[]`, each stage a clickable state chip that opens the same detail drawer | Done — see gap 2 for the mock's current fidelity |
| Per-job detail drawer with console | `JobDetailDrawer.tsx`, "Console" tab: `ui/Jobs`'s `JobConsole` (already gives level colours, text filter, follow-tail) fed by `history` (REST backfill) ∪ `live` (the shared `/ws/jobs` ring buffer), deduped by `seq` | Done |
| "Load earlier" via `/events?since=` | "Load earlier" button above the console calls `GET /api/jobs/{id}/events?since=-1` (full history) and merges it in — see gap 3 for why `since` alone doesn't page backward | Done, with a documented interpretation |
| Raw log tab via `/log?tail=` | "Raw log" tab, `GET /api/jobs/{id}/log?tail=`, rendered by the shared `JobConsole` filling the detail pane (2026-09-06). The fixed-height `<pre>` and its "Load more" button are gone: one console, with follow-tail, filter, level colours and Reveal, wherever a log is read | Done |
| "Reveal log file" | Wired in both the Console and Raw log tabs via `TitBridge.showItemInFolder` — see gap 4 (no contract field for the log path, so it's still reconstructed client-side) | Done, with a documented gap |
| Artifacts list with Open / View / Reveal | "Artifacts" tab, `ui/Jobs`'s `ArtifactList`; Open/View both open `/api/files/artifact?path=` in a new tab (no distinct native "open" vs. in-app "view" without the P9 bridge — same simplification `pages/results` makes); Reveal uses the shared `reveal()` helper | Done |
| Error taxonomy: preflight / lock_wait / budget_wait / runner_failed / oom_suspected / cancelled / skipped / lost / docker_unavailable, last 20 lines | `ErrorTaxonomyPanel` in the drawer: a `Callout` keyed off `job.error.type` (label table in `format.ts`, falls back to a humanised string for any type the mock's synthetic engine still uses) + `waiting_on` state for queued jobs + special-cased `cancelled`/`lost`; `error.last_lines.slice(-20)` in a `<pre>` | Done — see gap 6 (the mock's error types don't literally match the nine-value list) |
| Rail behaviours in `app/jobs-rail/` | Not touched — `JobsRail.tsx` is already a complete implementation (traces, expand/collapse, table, console), not a stub; `app/jobs/README.md` explicitly assigns cancel/rerun/force/groups-tree to this page, not the rail | N/A, confirmed not a stub |
| "Test job" button, dev only, to exercise the rail + table end to end | `Button` in the page header, gated on `import.meta.env.DEV`, calling `submitTestJob()` (`POST /api/jobs` with `config.__mock_fast: true`) | Done |

## Known gaps (report to orchestrator / B1 / B2)

1. **Stop/Rerun/Force/Delete live only in the drawer, not as table-row buttons.** A `JobStatus`
   row has five to six columns already before actions; adding four more icon buttons per row (at
   36px row height) crowded out the numeric columns DESIGN.md calls first-class citizens. The
   drawer opens on a single click and carries every action plus its confirmation, so nothing is
   unreachable — but a power user cancelling several queued jobs in a row has to open each one.
   Consider a row-hover action cluster (icons only, `aria-label`ed) as a follow-up if usage shows
   this matters.
2. ~~**The mock's `/api/jobs/groups` creates one job per subject, not a per-stage DAG.**~~
   **Resolved** — `desktop/tests/mock-server/server.mjs`'s `POST /api/jobs/groups` now mirrors
   `tit.jobs.plans.plan_preprocessing`'s `G1={dicom} → G2a={create_m2m} → G2b={recon} → G3={tissue}
   → G4={qsiprep} → G5={qsirecon} → G6={dti} → report` stage DAG (only a stage whose
   `PreprocessConfig` flag is set gets planned, chained by `after`, one trailing `"report"` job per
   subject), several `JobStatus` rows per subject sharing one `group_id` — exactly what
   `GroupsView.tsx` was already built to render. `tests/e2e/jobs.spec.ts`'s "shows a job group"
   test was still submitting `config: {}` (the old shape's zero-flags-needed assumption, which now
   plans zero stages and creates zero jobs) — updated to set `convert_dicom: true` so the group has
   jobs to show.
3. **`GET /api/jobs/{id}/events?since=` is forward-only, not a backward page cursor.** The plan
   text says "'load earlier' via `/events?since=`", but `since` returns events with `seq > since`
   — there is no way to ask for events *before* a given seq. Interpreted here as "since=-1" (full
   history from the start), which correctly backfills anything the client-side 500-event ring
   buffer (`app/jobs/jobsStream.ts`) has dropped for a long-running job. If a real deployment needs
   true incremental backward paging (say, a 50k-line job opened cold), the contract will need a
   `before=<seq>&limit=` pair or a page cursor — flagging for B1.
4. **No contract field carries the stdout.log path.** `JobStatus`/`JobDetail`/`Artifact` have
   nothing pointing at `<project>/code/ti-toolbox/jobs/<id>/stdout.log` (TODO §2.3's documented
   location). `JobDetailDrawer.tsx` reconstructs it client-side from `GET /api/project`
   (`host_path ?? container_path`) + the documented path convention, the same way the mock
   reconstructs artifact paths from `PROJECT_ROOT`. A cleaner fix: either add `JobStatus.log_path`
   or have the runner emit an `Artifact{kind: "log"}` entry so every client gets it from one place.
5. **`window.tit` has no `showItemInFolder` yet** (v3-build-plan.md open issue #4's sibling on the
   write side). `reveal()` (`pages/jobs/reveal.ts`) mirrors the exact fallback
   `pages/results/index.tsx` already uses ("Reveal in file manager isn't wired up yet") so both
   pages behave identically until P9 lands the bridge method — no page change needed once it does.
6. **Some of the mock's synthetic `error.type` values (`Forced`, `DependencyFailed`) are not
   in the nine-value taxonomy** the real server is meant to emit (`preflight`/`lock_wait`/
   `budget_wait`/`runner_failed`/`oom_suspected`/`cancelled`/`skipped`/`lost`/`docker_unavailable`).
   `errorLabel()` (`format.ts`) falls back to a humanised version of whatever string it gets, so
   the panel never shows a raw enum-looking string, but the E2E test can only exercise
   `__mock_fail`'s `runner_failed` path, not the other eight categories — those need a real
   `tit.server`/`tit.jobs.runner` integration test (B1/B4 own that surface).
7. **`components["schemas"]["JobStatus"]` (contract-generated) and `app/jobs/types.ts`'s
   `JobStatus` (the shared `/ws/jobs` store's hand-written type) are not structurally
   identical.** The contract marks `group_id`, `started_at`, `progress`, `liveness`, `exit_code`,
   `error`, `cpu_percent` and `rss` as `T | null`; `app/jobs/types.ts` models the same fields as
   `T | undefined` (no `null`). This page needs one shape to merge a REST `GET /api/jobs` page
   with the live store without a cast at every call site (`app/jobs/README.md`'s documented
   pattern), so `pages/jobs/api.ts` standardises on `app/jobs/types`'s shape and casts the
   REST-fetched values (`as unknown as JobStatus`) at the four functions that return one
   (`listJobs`, `cancelJob`, `rerunJob`, `forceJob`) — documented inline there. Not a runtime bug
   today (`JSON.parse` never produces `null` where the mock always sends a concrete value or omits
   the key), but a real server that actually returns JSON `null` for one of those fields would
   silently violate the type at that cast boundary. Flagging for F1a (contract) and F2 (the shared
   store) to agree on one nullability convention.

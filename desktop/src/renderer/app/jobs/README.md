# app/jobs/

The `/ws/jobs` client (plan §3). One shared connection for the whole renderer — the rail
(`app/jobs-rail/`) and P7's full Jobs page both read the same store instead of opening their own
sockets.

## API surface (kept intentionally small)

```ts
import { useJobsStream, subscribeJob, unsubscribeJob } from "./useJobsStream";

const { status, jobs, eventsByJob, attempt, lastError } = useJobsStream();
// status: "idle" | "connecting" | "open" | "reconnecting" | "closed"
// jobs: Record<jobId, JobStatus>            — latest snapshot per job, from `{type:"job"}` messages
// eventsByJob: Record<jobId, JobEvent[]>    — ring buffer (last 500), only for jobs you subscribed to

subscribeJob(jobId);              // start streaming one job's events (log/stage/progress/...)
subscribeJob(jobId, sinceSeq);    // resume after a reconnect or a page remount
unsubscribeJob(jobId);            // stop and drop its buffered events (call on unmount of a console)
```

`useJobsStream()` acquires the shared connection on mount and releases it on unmount (same
pattern as `ws/useSystemStream.ts`); calling it from multiple components is free — only the first
mount opens the socket, only the last unmount closes it.

`jobs` holds every job the server has told us about since the socket opened: every `JobStatus`
*transition* is pushed unprompted (plan §3, "server → `{type: 'job', job}` on every transition"),
plus — as of ra_12 #4 — a one-time `GET /api/jobs` fetched right after each successful connect
(`jobsStream.ts`'s `seed` option, wired to the real endpoint in `useJobsStream.ts`) and merged in
for any job id the store doesn't already have. Without that seed, a job that was already
running before this tab connected (and so never earns a fresh transition this session) would
never appear — the rail showed "No jobs running" while the Jobs table, which did its own
`GET /api/jobs`, showed one running. The seed never overwrites a job id the store already learned
from a live WS message, so it can't clobber fresher state on a flaky reconnect. This means the
rail's job list needs no separate poll of its own, and **any other consumer of this same store —
including P7's Jobs page — sees the same merged data**, so "rail == table" holds by construction
rather than by two independent fetches agreeing. `eventsByJob` only fills in for jobs you called
`subscribeJob` on (e.g. an open `JobConsole` or `JobTrace` detail) — call `unsubscribeJob` when
that UI closes so the ring buffer is dropped.

## What P7 builds on top

This store intentionally does not do: sorting/filtering, cancel/rerun/force actions, or a groups
tree. P7's Jobs page may still keep its own `useQuery(["jobs"], listJobs)` for react-query's
caching/invalidation ergonomics (e.g. refetching after a mutation) — that is redundant with this
store's own seed but harmless, since both resolve to the same `GET /api/jobs` data merged the
same way. It is not required for correctness any more: `jobs` from `useJobsStream()` alone is
already a complete, current list.

## Types

`types.ts` mirrors plan §3's `JobStatus`/`Event`/`WS /ws/jobs` shapes exactly — keep it in sync
with `contracts/events.schema.json` (F1a) rather than re-deriving it independently.

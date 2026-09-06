import type { JobStatus } from "./api";

/**
 * Merge a `GET /api/jobs` page (jobs that existed before the `/ws/jobs` socket opened — the
 * shared store deliberately excludes those, see `app/jobs/README.md`) with the live map from
 * `useJobsStream()`. Live entries win on id collision since they are the more current snapshot.
 */
export function mergeJobs(initial: JobStatus[] | undefined, live: Record<string, JobStatus>): JobStatus[] {
  const byId = new Map<string, JobStatus>();
  for (const j of initial ?? []) byId.set(j.id, j);
  for (const j of Object.values(live)) byId.set(j.id, j);
  return [...byId.values()];
}

/** "3m 12s" / "45s" between start and now (or finish, if the job is done). */
export function elapsedLabel(job: JobStatus, now: number): string {
  const startIso = job.started_at ?? job.created_at;
  const start = Date.parse(startIso);
  const end = job.finished_at ? Date.parse(job.finished_at) : now;
  if (Number.isNaN(start)) return "—";
  const s = Math.max(0, Math.round((end - start) / 1000));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return m > 0 ? `${m}m ${rem}s` : `${rem}s`;
}

const ERROR_LABEL: Record<string, string> = {
  preflight: "Preflight check failed",
  lock_wait: "Waiting on a lock",
  budget_wait: "Waiting on the resource budget",
  runner_failed: "Runner failed",
  oom_suspected: "Likely out of memory",
  cancelled: "Cancelled",
  skipped: "Skipped",
  lost: "Lost (server restarted mid-run)",
  docker_unavailable: "Docker is unavailable",
  kind_error: "Invalid job configuration",
};

/** Human label for an `error.type` — the nine-value taxonomy (plan §2.5) when it matches, else a
 * title-cased fallback so an unrecognised type (e.g. the mock's synthetic ones) still reads. */
export function errorLabel(type: string): string {
  const known = ERROR_LABEL[type];
  if (known) return known;
  return type
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/^./, (c) => c.toUpperCase());
}

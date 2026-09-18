/**
 * The Overview's "Recent jobs" row model — pure, so the destination a row leads to is a function
 * of the job record and can be read by a unit test without a DOM.
 *
 * Why it lives here and not in `app/jobs-rail/model.ts`: the rail's model answers "what is running
 * now"; this answers "what has this project done, and where do I go to see it". Both read the SAME
 * store (`useJobsModel()`), so this file adds no fetch of its own.
 */
import type { JobStatus } from "../../app/jobs-rail/api";

/** How many rows the Overview draws before "See all" takes over. */
export const RECENT_JOBS_LIMIT = 8;

/**
 * Job kinds `pages/results` actually browses. Everything else (`leadfield`, `project_init`,
 * `pre`, `tools`, `viewer`, `blender`, `source`, `nifti_average`, `nilearn`) produces inputs or
 * side effects rather than a result Results lists, so its row opens the Jobs page — a destination
 * that always has something to show — instead of a subject with no entry for it.
 */
export const RESULTS_KINDS = new Set([
  "sim",
  "flex",
  "flex_adaptive",
  "flex_pareto",
  "ex",
  "mex",
  "analyzer",
  "stats",
  "report",
]);

export type RecentJobDestination =
  | { page: "results"; subject: string | null }
  | { page: "jobs"; jobId: string };

export interface RecentJobRow {
  id: string;
  kind: string;
  /** `subject_ids` joined, or "project" for a job that belongs to no subject. */
  subjects: string;
  /** The directory this job's outputs share, or null when it wrote none. */
  runName: string | null;
  state: JobStatus["state"];
  pulse: boolean;
  /** "just now" / "12m ago" / "3h ago" / "2d ago". */
  started: string;
  /** "45s" / "3m 12s", or "—" before the job starts. */
  duration: string;
  destination: RecentJobDestination;
}

/**
 * Where clicking this job goes.
 *
 * - a job that succeeded in a kind Results browses → Results, scoped to its first subject (the
 *   exact addressing Results already supports: `state.subject`, the same link the detail pane's
 *   "Open in Results" uses). Results has no per-job address, and inventing one would mean a new
 *   field on the record and a contract change for a link the page can already make.
 * - anything else — running, queued, failed, cancelled, or a kind with no Results view → the Jobs
 *   page with that job selected, which is where its log is.
 */
export function destinationFor(job: JobStatus): RecentJobDestination {
  if (job.state === "succeeded" && RESULTS_KINDS.has(job.kind) && job.artifacts.length > 0) {
    return { page: "results", subject: job.subject_ids[0] ?? null };
  }
  return { page: "jobs", jobId: job.id };
}

/**
 * The run this job wrote, named by the directory its outputs share — `mock_abc` for artifacts
 * under `…/Simulations/mock_abc/report/` and `…/Simulations/mock_abc/TI/mesh/`. The job record
 * carries no run name of its own, and this is derivable from what it does carry.
 */
export function runNameOf(job: JobStatus): string | null {
  const paths = job.artifacts.map((a) => a.path).filter((p) => p.length > 0);
  if (paths.length === 0) return null;
  const parts = paths.map((p) => p.split("/").slice(0, -1));
  const first = parts[0] as string[];
  let shared = first.length;
  for (const other of parts.slice(1)) {
    let i = 0;
    while (i < shared && i < other.length && first[i] === other[i]) i += 1;
    shared = i;
  }
  return first[shared - 1] ?? null;
}

/** "just now" / "12m ago" / "3h ago" / "2d ago" — the coarse grain a list of eight rows wants. */
export function relativeTime(iso: string | null | undefined, now: number): string {
  if (!iso) return "—";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";
  const s = Math.max(0, Math.round((now - then) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

/** How long the job ran: start → finish, or start → now while it is still going. "—" if unstarted. */
export function durationLabel(job: JobStatus, now: number): string {
  if (!job.started_at) return "—";
  const start = Date.parse(job.started_at);
  if (Number.isNaN(start)) return "—";
  const end = job.finished_at ? Date.parse(job.finished_at) : now;
  const s = Math.max(0, Math.round((end - start) / 1000));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
}

export function recentJobRows(jobs: JobStatus[], now: number, limit = RECENT_JOBS_LIMIT): RecentJobRow[] {
  return [...jobs]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .slice(0, limit)
    .map((job) => ({
      id: job.id,
      kind: job.kind,
      subjects: job.subject_ids.join(", ") || "project",
      runName: runNameOf(job),
      state: job.state,
      pulse: job.liveness === "active",
      started: relativeTime(job.started_at ?? job.created_at, now),
      duration: durationLabel(job, now),
      destination: destinationFor(job),
    }));
}

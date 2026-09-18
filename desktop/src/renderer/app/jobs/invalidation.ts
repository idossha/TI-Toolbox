/**
 * Job completion -> React Query invalidation.
 *
 * Catalog queries never poll (`main.tsx`: `staleTime: 60_000`, no refetch on focus) because the
 * data they show only changes when a job finishes. This is the one place that knowledge lives:
 * `queriesAffectedBy(kind)` says which query-key prefixes a finished job of that kind may have
 * changed, and `useJobCompletionInvalidation` (mounted once, in the Shell) watches the shared
 * `/ws/jobs` store for every transition into a terminal state and invalidates them.
 *
 * `invalidateQueries` refetches the affected queries that are currently observed — and every
 * retained page keeps its queries observed while hidden — and marks the rest stale, so a page
 * mounted later fetches fresh data on mount. No page needs its own completion effect.
 *
 * Failed and cancelled runs invalidate too: the catalog ignores a run without its completion
 * manifest, but preprocessing can leave a usable head model behind a later failing stage, and a
 * refetch that finds nothing new is cheap.
 */
import { useEffect, useRef } from "react";
import { useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";
import type { JobState, JobStatus } from "./types";
import { useJobsStream } from "./useJobsStream";

export const TERMINAL_STATES: ReadonlySet<JobState> = new Set<JobState>(["succeeded", "failed", "cancelled", "skipped", "lost"]);

/** Every finished job may have changed a subject's summary and the project-level rollups. */
const COMMON: readonly QueryKey[] = [
  ["subjects"],
  ["subject-detail"],
  ["jobs-subjects"],
  ["overview"],
  ["project-summary"],
  ["project-status"],
  ["system-storage"],
];

const SIMULATIONS: readonly QueryKey[] = [
  ["simulations"],
  ["results-simulations"],
  ["results-simulation-figures"],
  ["export-montage"],
  ["viewer-tree"],
  ["viewer-candidates"],
];

const SEARCH_RESULTS: readonly QueryKey[] = [
  ["results-flex-runs"],
  ["results-ex-runs"],
  ["optimization-candidates"],
  ["optimization-candidate-history"],
  ["viewer-tree"],
  ["viewer-candidates"],
];

const ANALYSES: readonly QueryKey[] = [["results-analyses"], ["results-reports"], ["viewer-tree"], ["viewer-candidates"]];

const GROUP_OUTPUTS: readonly QueryKey[] = [["results-group"], ["results-reports"], ["results-simulation-figures"]];

/** Head model, EEG nets, atlases and the scene panes all come from `m2m_<sid>`. */
const HEAD_MODEL: readonly QueryKey[] = [
  ["eeg-nets"],
  ["eeg-net-electrodes"],
  ["atlases"],
  ["atlas-regions"],
  ["nifti-labels"],
  ["rois"],
  ["scene"],
  ["results-reports"],
  ["leadfield-eta"],
];

const BY_KIND: Record<string, readonly QueryKey[]> = {
  pre: HEAD_MODEL,
  report: [["results-reports"]],
  project_init: HEAD_MODEL,
  sim: SIMULATIONS,
  // A flex run is also a montage source for the Simulator (`flex-runs` / `flex-mapping`).
  flex: [...SEARCH_RESULTS, ["flex-runs"], ["flex-mapping"]],
  flex_adaptive: [...SEARCH_RESULTS, ["flex-runs"], ["flex-mapping"]],
  flex_pareto: [...SEARCH_RESULTS, ["flex-runs"], ["flex-mapping"]],
  ex: SEARCH_RESULTS,
  mex: SEARCH_RESULTS,
  recip: SEARCH_RESULTS,
  leadfield: [["leadfields"], ["leadfield-eta"], ["plan"]],
  analyzer: ANALYSES,
  stats: GROUP_OUTPUTS,
  nifti_average: GROUP_OUTPUTS,
  nilearn: GROUP_OUTPUTS,
  source: GROUP_OUTPUTS,
  blender: GROUP_OUTPUTS,
  tools: [],
};

/** Query-key prefixes a finished job of `kind` may have changed; unknown kinds get the common set. */
export function queriesAffectedBy(kind: string): QueryKey[] {
  const specific = BY_KIND[kind] ?? [];
  const seen = new Set<string>();
  const out: QueryKey[] = [];
  for (const key of [...COMMON, ...specific]) {
    const id = JSON.stringify(key);
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(key);
  }
  return out;
}

/** Job ids that moved into a terminal state between two store snapshots. A job first seen
 * already finished (the connect-time seed replaying history) is not a completion. */
export function completedBetween(previous: Record<string, JobStatus>, next: Record<string, JobStatus>): JobStatus[] {
  const done: JobStatus[] = [];
  for (const job of Object.values(next)) {
    if (!TERMINAL_STATES.has(job.state)) continue;
    const before = previous[job.id];
    if (before && !TERMINAL_STATES.has(before.state)) done.push(job);
  }
  return done;
}

export function invalidateForJobs(queryClient: QueryClient, jobs: readonly JobStatus[]): void {
  const keys = new Map<string, QueryKey>();
  for (const job of jobs) for (const key of queriesAffectedBy(job.kind)) keys.set(JSON.stringify(key), key);
  for (const queryKey of keys.values()) void queryClient.invalidateQueries({ queryKey });
}

/** Mount once per app: refetches every input list a just-finished job may have changed. */
export function useJobCompletionInvalidation(): void {
  const queryClient = useQueryClient();
  const { jobs } = useJobsStream();
  const previous = useRef<Record<string, JobStatus>>({});
  useEffect(() => {
    const done = completedBetween(previous.current, jobs);
    previous.current = jobs;
    if (done.length > 0) invalidateForJobs(queryClient, done);
  }, [jobs, queryClient]);
}

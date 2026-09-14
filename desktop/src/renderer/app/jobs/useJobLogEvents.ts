import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getJobEvents, TERMINAL_STATES } from "../jobs-rail/api";
import { jobEventsToLogLines, mergeJobEvents } from "./logLines";
import { subscribeJob, unsubscribeJob, useJobsStream } from "./useJobsStream";
import type { JobState } from "./types";

/** Once the process exits, fetch its complete transcript instead of replaying a queued socket
 * backlog underneath a finished status. The final fetch includes the manager's drained tail. */
export function useJobLogEvents(jobId: string | undefined, state: JobState | undefined) {
  const { eventsByJob } = useJobsStream();
  const terminal = state !== undefined && TERMINAL_STATES.includes(state);
  useEffect(() => {
    if (!jobId || terminal) return;
    subscribeJob(jobId);
    return () => unsubscribeJob(jobId);
  }, [jobId, terminal]);

  const backlog = useQuery({
    queryKey: ["job-events", jobId, terminal ? "final" : "live"],
    queryFn: () => getJobEvents(jobId as string),
    enabled: !!jobId,
    staleTime: terminal ? Infinity : 5_000,
    // Retain the visible history while the final snapshot arrives, but never another job's log.
    placeholderData: (previous, query) => query?.queryKey[1] === jobId ? previous : undefined,
  });
  const lines = useMemo(() => jobEventsToLogLines(mergeJobEvents(
    backlog.data ?? [],
    !terminal && jobId ? eventsByJob[jobId] ?? [] : [],
  )), [backlog.data, eventsByJob, jobId, terminal]);
  return { lines, isLoading: backlog.isLoading };
}

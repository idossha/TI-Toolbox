/**
 * The `project_init` jobs that install example data, keyed by sample id.
 *
 * Progress is the job's own stream — the same `/ws/jobs` store the rail reads — so nothing here
 * polls. Shared by the chooser and Help ▸ Example data so both report on the same jobs, and both
 * refresh the Overview matrix and the catalogue's `installed` flags when one finishes.
 */
import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { TERMINAL_STATES } from "../jobs-rail/api";
import { subscribeJob, useJobsStream } from "../jobs/useJobsStream";
import { EXAMPLE_DATA_QUERY_KEY, startExampleData } from "./api";

export function useExampleDataJobs() {
  const queryClient = useQueryClient();
  const { jobs, eventsByJob } = useJobsStream();
  const [jobIdBySample, setJobIdBySample] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  const finished = Object.values(jobIdBySample).filter(
    (id) => jobs[id] && TERMINAL_STATES.includes(jobs[id]!.state),
  ).length;
  useEffect(() => {
    if (finished === 0) return;
    void queryClient.invalidateQueries({ queryKey: ["overview"] });
    void queryClient.invalidateQueries({ queryKey: EXAMPLE_DATA_QUERY_KEY });
  }, [finished, queryClient]);

  const start = useCallback(async (sampleId: string) => {
    setError("");
    try {
      const status = await startExampleData(sampleId);
      setJobIdBySample((prev) => ({ ...prev, [sampleId]: status.id }));
      subscribeJob(status.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start the download.");
      throw cause;
    }
  }, []);

  /** The line a row shows while its job runs, or undefined when none is running. */
  const busyText = useCallback(
    (sampleId: string): string | undefined => {
      const id = jobIdBySample[sampleId];
      const job = id ? jobs[id] : undefined;
      if (!job || TERMINAL_STATES.includes(job.state)) return undefined;
      const pct = job.progress ? ` ${Math.round(job.progress.pct)}%` : "";
      const last = id ? [...(eventsByJob[id] ?? [])].reverse().find((e) => e.type === "log")?.msg : undefined;
      return `${job.state}${pct}${last ? ` · ${last}` : ""}`;
    },
    [eventsByJob, jobIdBySample, jobs],
  );

  return { start, busyText, error };
}

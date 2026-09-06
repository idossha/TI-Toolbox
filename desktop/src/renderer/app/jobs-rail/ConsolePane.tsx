/**
 * The selected job's console. `ui/Jobs.tsx`'s `JobConsole` does the virtualised rendering,
 * follow-tail, filter and level colours; this pane owns the subscription (one job's events at a
 * time on the shared `/ws/jobs` socket) and the "load earlier" REST backfill.
 */
import { useEffect, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { jobEventsToLogLines, mergeJobEvents } from "../jobs/logLines";
import { subscribeJob, unsubscribeJob, useJobsStream } from "../jobs/useJobsStream";
import { Button } from "../../ui/Button";
import { EmptyState } from "../../ui/Feedback";
import { JobConsole } from "../../ui/Jobs";
import { notify } from "../../ui/Toast";
import { getJobEvents, type JobEvent, type JobStatus } from "./api";
import { reveal } from "./reveal";

export function ConsolePane({ job }: { job: JobStatus | undefined }) {
  const jobId = job?.id;
  const [history, setHistory] = useState<JobEvent[]>([]);
  const { eventsByJob } = useJobsStream();

  const [resetForJobId, setResetForJobId] = useState(jobId);
  if (jobId !== resetForJobId) {
    setResetForJobId(jobId);
    setHistory([]);
  }

  useEffect(() => {
    if (!jobId) return;
    subscribeJob(jobId);
    return () => unsubscribeJob(jobId);
  }, [jobId]);

  const loadEarlier = useMutation({
    mutationFn: () => getJobEvents(jobId!),
    onSuccess: setHistory,
    onError: (e) => notify.error("Could not load the full event history.", e instanceof ApiError ? e.message : String(e)),
  });

  const lines = useMemo(() => {
    if (!jobId) return [];
    // Dedupe by seq: `history` is the full-backlog REST fetch, the ring-buffered WS tail
    // (capped at 500/job) is `live` — a job open long enough to have dropped early events from
    // that buffer gets them back this way.
    const live = eventsByJob[jobId] ?? [];
    return jobEventsToLogLines(mergeJobEvents(history, live));
  }, [history, eventsByJob, jobId]);

  if (!job) {
    return (
      <div className="jobs-pane-empty">
        <EmptyState variant="inline" message="Select a job to see its console." />
      </div>
    );
  }

  const logPath = job.log_path ?? undefined;

  return (
    <div className="console-pane" data-testid="job-console-pane">
      <div className="console-pane-head">
        <span className="text-eyebrow">
          {job.kind} · {job.subject_ids.join(", ") || "project"}
        </span>
        <Button variant="ghost" size="sm" loading={loadEarlier.isPending} onClick={() => loadEarlier.mutate()}>
          Load earlier
        </Button>
      </div>
      <div className="console-pane-body">
        <JobConsole sourceKey={`job:${job.id}`} lines={lines} onRevealLogFile={logPath ? () => reveal(logPath) : undefined} />
      </div>
    </div>
  );
}

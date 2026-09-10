/**
 * The Raw log tab of `JobDetailPane` — the *same* console the run pages host, not a second,
 * lesser log viewer.
 *
 * It used to be a fixed-height `<pre>` holding a `tail=400` snapshot with a "Load more" button
 * under it, which on a tall detail pane left roughly two thirds of the pane empty (maintainer's
 * screenshot, Sep 2026). What a reader wants there is what the run page's terminal already gives
 * them: the whole transcript, virtualised, filling the pane to its bottom edge, with Follow / a
 * filter / Clear / Reveal log file in the console's own toolbar. So this component is a thin
 * source adapter around `ui/Jobs.tsx`'s `JobConsole`, exactly like `pages/_shared/run/JobTerminal`:
 *
 *   REST backlog (`getJobEvents`) ∪ the socket's ring-buffered tail  →  `jobEventsToLogLines`
 *
 * with one addition JobTerminal does not need: a job whose events the server no longer holds (an
 * old job, restarted server) still has its log *file*, so when the event stream yields nothing the
 * adapter falls back to `getJobLog` and splits the file into the same line model. Either way the
 * whole log is in the list — no paging control, and nothing for the user to click to see more.
 */
import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { JobConsole } from "../../ui/Jobs";
import { jobEventsToLogLines, mergeJobEvents, splitLogText, type JobLogLine } from "../jobs/logLines";
import { subscribeJob, unsubscribeJob, useJobsStream } from "../jobs/useJobsStream";
import { getJobEvents, getJobLog, TERMINAL_STATES, type JobStatus } from "./api";
import { reveal } from "./reveal";

function fileToLogLines(text: string): JobLogLine[] {
  // One row per VISUAL line, `\r` progress counters collapsed — the console's rows are a fixed
  // 18 px, so a "line" holding an embedded newline paints over the rows below it.
  return splitLogText(text).map((text, i) => ({ seq: i, key: `f${i}`, text }));
}

export function JobRawLog({ job }: { job: JobStatus }) {
  const jobId = job.id;
  const { eventsByJob } = useJobsStream();
  const running = !TERMINAL_STATES.includes(job.state);

  useEffect(() => {
    subscribeJob(jobId);
    return () => unsubscribeJob(jobId);
  }, [jobId]);

  const backlog = useQuery({
    queryKey: ["job-events", jobId],
    queryFn: () => getJobEvents(jobId),
    staleTime: 5_000,
  });

  const eventLines = useMemo(
    () => jobEventsToLogLines(mergeJobEvents(backlog.data ?? [], eventsByJob[jobId] ?? [])),
    [backlog.data, eventsByJob, jobId],
  );

  // Only when the event stream has nothing to show — see the header comment. `tail` is omitted so
  // the server returns the whole file; a running job refetches so the fallback tails too.
  const file = useQuery({
    queryKey: ["job-log", jobId, "full"],
    queryFn: () => getJobLog(jobId),
    enabled: !backlog.isLoading && eventLines.length === 0,
    refetchInterval: running ? 3000 : false,
  });
  const fileLines = useMemo(() => (file.data ? fileToLogLines(file.data) : []), [file.data]);

  const lines = eventLines.length > 0 ? eventLines : fileLines;
  const logPath = job.log_path ?? undefined;

  return (
    <div className="job-detail-rawlog" data-testid="job-detail-rawlog">
      <JobConsole
        sourceKey={`job:${jobId}`}
        lines={lines}
        onRevealLogFile={logPath ? () => reveal(logPath) : undefined}
      />
    </div>
  );
}

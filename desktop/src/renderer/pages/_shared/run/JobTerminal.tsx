/**
 * The run page's own live console (DESIGN.md v3 §4.6). It exists so nobody has to open the jobs
 * panel to find out what their own run is doing.
 *
 * Everything about *rendering* a log — virtualisation, the filter box, follow-tail, the level
 * colours, "Reveal log file" — is already `ui/Jobs.tsx`'s `JobConsole` and is reused unchanged.
 * What this component adds is the two things a page-scoped terminal needs and the jobs panel does
 * not: the 24px identity header ("which log am I reading") and the pin.
 *
 * Which job it follows is `terminalSources.ts`'s `resolveFollowedJob`, and the rule it now obeys
 * (fix lane FXU2) is: **nothing is pinned on page open unless a job of this page's kind is really
 * running or queued — or unless this page session started it.** Opening a tab must never look like
 * it started something; equally, a job you did start here must not disappear the instant it ends.
 */
import { useEffect, useMemo } from "react";
import { Pin, PinOff } from "lucide-react";
import { IconButton } from "../../../ui/Button";
import { JobConsole } from "../../../ui/Jobs";
import { JobStateChip, type JobState } from "../../../ui/Status";
import { resolveFollowedJob, type FollowableJob, type RunStep, type TerminalSource } from "./terminalSources";
import { useJobLogEvents } from "../../../app/jobs/useJobLogEvents";
import { useJobsModel } from "../../../app/jobs-rail/model";
import { elapsedLabel } from "../../../app/jobs-rail/format";
import { type JobStatus } from "../../../app/jobs-rail/api";
import { reveal } from "../../../app/jobs-rail/reveal";
import { jobFolder } from "../../../app/jobs-rail/artifacts";
import "./run.css";

function toFollowable(job: JobStatus, now: number): FollowableJob {
  return {
    id: job.id,
    kind: job.kind,
    subject: job.subject_ids.join(", ") || "project",
    subjects: job.subject_ids,
    state: job.state as JobState,
    progressPct: job.progress?.pct ?? undefined,
    liveness: (job.liveness ?? undefined) as FollowableJob["liveness"],
    elapsed: elapsedLabel(job, now),
    createdAt: Date.parse(job.created_at),
    logPath: job.log_path ?? undefined,
  };
}

export interface JobTerminalProps {
  /** Kinds this terminal may follow, most specific first. */
  kinds: string[];
  subjects: string[];
  pinnedJobId?: string | null;
  onPinJob?: (jobId: string | null) => void;
  /**
   * Jobs THIS page session started (the ids of the last Run press). They keep their log and final
   * status line in the pane after they finish, instead of the pane emptying itself the moment the
   * run the user was watching succeeds (maintainer, 2026-09-07). Page-session state, so navigating
   * away and back keeps it; a fresh app start starts empty.
   */
  startedJobIds?: readonly string[];
  onRevealLogFile?: (jobId: string) => void;
  /**
   * Accepted and ignored since FXU2, when the pane's "What will run" preview was retired: showing
   * a plan in the log pane is the thing that made an idle tab look busy. Kept in the signature so
   * the pages that still compute their step list (`stepsFor`) need no edit, and so a future
   * work-pane preview has its input ready.
   */
  steps?: RunStep[];
  parallel?: number;
  /** Reported upward so the page can assert which of the two states it is showing. */
  onSourceChange?: (source: TerminalSource) => void;
}

export function JobTerminal({
  kinds,
  subjects,
  pinnedJobId,
  startedJobIds,
  onPinJob,
  onRevealLogFile,
  onSourceChange,
}: JobTerminalProps) {
  const { all, now } = useJobsModel();

  const followable = useMemo(() => all.map((j) => toFollowable(j, now)), [all, now]);
  const job = useMemo(
    () => resolveFollowedJob(followable, kinds, subjects, pinnedJobId, startedJobIds),
    [followable, kinds, subjects, pinnedJobId, startedJobIds],
  );
  const jobId = job?.id;
  // `job` (from `resolveFollowedJob`) is a `FollowableJob`, which drops `artifacts` in
  // `toFollowable` above — it only ever carried `logPath`, which is why this pane used to reveal
  // `code/ti-toolbox/jobs/<id>/` (the job's bookkeeping record) instead of its real output folder.
  // The full `JobStatus` `jobFolder()` needs is right there in `all`, so look it up by id rather
  // than growing `FollowableJob` for one field only this pane uses.
  const rawJob = useMemo(() => all.find((j) => j.id === jobId), [all, jobId]);
  const folder = useMemo(() => (rawJob ? jobFolder(rawJob) : null), [rawJob]);
  // `jobFolder()` itself falls back to the log's directory when the job has written no artifacts
  // yet, so `folder` alone can't say which folder it is. The label needs to.
  const hasArtifact = !!rawJob?.artifacts.some((a) => a.path);

  const { lines } = useJobLogEvents(jobId, job?.state);

  const pinned = !!pinnedJobId && pinnedJobId === jobId;

  const source: TerminalSource = job ? "live" : "empty";
  useEffect(() => {
    onSourceChange?.(source);
  }, [source, onSourceChange]);

  return (
    <section className="job-terminal" data-testid="job-terminal" data-source={source}>
      <header className="job-terminal-head">
        {/* DESIGN.md §4.6's own wireframe heads this pane "TERMINAL" via a `.text-eyebrow` — the
            two-part rhythm the critic's round-1 finding 6 asked for. Grouped with the identity so
            the header stays a two-item `justify-content: space-between` row (eyebrow+identity vs.
            the pin button). */}
        <span className="job-terminal-title">
          <span className="text-eyebrow job-terminal-eyebrow">Terminal</span>
          {job ? (
            <span className="job-terminal-identity" data-testid="job-terminal-identity">
              <span className="job-terminal-kind">{job.kind}</span>
              <span className="job-terminal-sep">·</span>
              <span className="mono job-terminal-subject">{job.subject}</span>
              <span className="job-terminal-sep">·</span>
              <JobStateChip state={job.state} pulse={job.liveness === "active"} />
              <span className="job-terminal-elapsed">{job.elapsed}</span>
            </span>
          ) : (
            /* "Which log am I reading" is still answered when the answer is "none": the header
               says so rather than leaving a bare box the reader has to interpret. */
            <span className="job-terminal-identity" data-testid="job-terminal-identity">
              <span className="job-terminal-kind">No job</span>
            </span>
          )}
        </span>
        {job && onPinJob && (
          <IconButton
            aria-label={pinned ? "Unpin this job" : "Pin this job"}
            size="sm"
            variant="ghost"
            icon={pinned ? <PinOff size={12} /> : <Pin size={12} />}
            onClick={() => onPinJob(pinned ? null : job.id)}
          />
        )}
      </header>
      <div className="job-terminal-body">
        {job ? (
          <JobConsole
            sourceKey={`job:${job.id}`}
            lines={lines}
            onRevealLogFile={
              folder || job.logPath || onRevealLogFile
                ? () =>
                    onRevealLogFile
                      ? onRevealLogFile(job.id)
                      : reveal((folder ?? job.logPath) as string)
                : undefined
            }
            revealLabel={hasArtifact ? "Show the job's output folder" : "Reveal log file"}
          />
        ) : (
          <div className="job-terminal-empty" data-testid="job-terminal-empty">
            <span>No job running. Start one with Run, or pick a job from the Jobs page.</span>
          </div>
        )}
      </div>
    </section>
  );
}

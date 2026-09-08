/**
 * The selected job's detail, as a PANE — not a modal. `pages/jobs/JobDetailDrawer.tsx` used to
 * open a Radix `Drawer` over the whole window to say what a row already had room to say; plan §1
 * puts it in the right half of whatever surface you are on (the 260px panel, or the full page),
 * so the table stays visible and a second job is one click away.
 *
 * Everything the drawer did survives: the error taxonomy, the definition list, the raw-log tail,
 * artifacts, and cancel / rerun / force / delete behind their `AlertDialog` confirmations.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FolderOpen, RotateCw, Square, Trash2, Zap } from "lucide-react";
import { ApiError } from "../../api/client";
import { Button, IconButton } from "../../ui/Button";
import { Callout, DefinitionList, EmptyState, InlineError, Skeleton } from "../../ui/Feedback";
import { ArtifactList, type ArtifactItem } from "../../ui/Jobs";
import { Cluster, Stack, Tabs } from "../../ui/Layout";
import { AlertDialog } from "../../ui/Overlay";
import { Chip, JobStateChip, LivenessBadge } from "../../ui/Status";
import { notify } from "../../ui/Toast";
import { bytes, pct } from "../../ui/utils";
import {
  artifactUrl,
  cancelJob,
  deleteJob,
  forceJob,
  getJobLog,
  rerunJob,
  TERMINAL_STATES,
  type JobStatus,
} from "./api";
import { elapsedLabel, errorLabel, failureReason } from "./format";
import { JobRawLog } from "./JobRawLog";
import { openNative, reveal } from "./reveal";

type ConfirmKind = "stop" | "force" | "delete";

function toArtifactItems(job: JobStatus): ArtifactItem[] {
  return job.artifacts.map((a) => ({ path: a.path, kind: a.kind, label: a.label ?? a.path }));
}

export interface JobDetailPaneProps {
  job: JobStatus | undefined;
  allowUnsafeOverrides: boolean;
  /** Jump the pane to another job (a "waiting on" link, or a deleted job clearing the selection). */
  onOpenJob: (jobId: string | null) => void;
  /** `panel` drops the tabs to fit 260px; `page` shows raw log + artifacts beside the summary. */
  density?: "panel" | "page";
  /**
   * Rendered at the right end of the pane's own header row. The Jobs page passes `ui/Layout`'s
   * `PaneHeaderControls` here (program U13) so the collapse/expand buttons sit in the pane header
   * the user is looking at, rather than in a second header the shell would have to draw above it.
   */
  headerControls?: ReactNode;
}

export function JobDetailPane({ job, allowUnsafeOverrides, onOpenJob, density = "page", headerControls }: JobDetailPaneProps) {
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState<ConfirmKind | null>(null);
  const [tab, setTab] = useState("summary");
  const [now, setNow] = useState(() => Date.now());
  const jobId = job?.id;

  // Reset per-job UI state during render when the selection changes, rather than in an effect
  // (React's documented "adjusting state when a prop changes" pattern).
  const [resetForJobId, setResetForJobId] = useState(jobId);
  if (jobId !== resetForJobId) {
    setResetForJobId(jobId);
    setTab("summary");
  }

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // The Summary tab's own console excerpt (§3.2 finding, B6 → this lane): at `page` density the
  // Summary tab was just the definition list, leaving ~30% of a 736px pane blank — the wireframe's
  // own Jobs design (docs/dev/DESIGN.md §4.10) fills that with the tail of the same
  // log, not a second empty pane the user has to click "Raw log" to see anything in. Fixed at 40
  // lines and always on at `page` density (unlike the Raw log tab's `logTail`, which grows on
  // demand): a live-refetching excerpt for a running job so the pane keeps painting content, not a
  // frozen snapshot from the moment the job was selected.
  const excerptQuery = useQuery({
    queryKey: ["job-log", jobId, "excerpt", 40],
    queryFn: () => getJobLog(jobId!, 40),
    enabled: !!jobId && density === "page",
    refetchInterval: job && !TERMINAL_STATES.includes(job.state) ? 3000 : false,
  });

  const invalidateJobs = () => queryClient.invalidateQueries({ queryKey: ["jobs"] });

  const stop = useMutation({
    mutationFn: () => cancelJob(jobId!),
    onSuccess: () => {
      notify.success("Stop requested.");
      invalidateJobs();
    },
    onError: (e) => notify.error("Could not stop the job.", e instanceof ApiError ? e.message : String(e)),
  });
  const rerun = useMutation({
    mutationFn: () => rerunJob(jobId!),
    onSuccess: (status) => {
      notify.success(`Queued: rerun of ${status.kind} for ${status.subject_ids.join(", ") || "the project"}.`);
      invalidateJobs();
    },
    onError: (e) => notify.error("Could not rerun the job.", e instanceof ApiError ? e.message : String(e)),
  });
  const force = useMutation({
    mutationFn: () => forceJob(jobId!),
    onSuccess: () => {
      notify.success("Forced to a terminal state.");
      invalidateJobs();
    },
    onError: (e) => notify.error("Could not force the job.", e instanceof ApiError ? e.message : String(e)),
  });
  const del = useMutation({
    mutationFn: () => deleteJob(jobId!),
    onSuccess: () => {
      notify.success("Job deleted.");
      invalidateJobs();
      onOpenJob(null);
    },
    onError: (e) => notify.error("Could not delete the job.", e instanceof ApiError ? e.message : String(e)),
  });

  const artifacts = useMemo(() => (job ? toArtifactItems(job) : []), [job]);

  if (!job) {
    return (
      <div className="job-detail" data-testid="job-detail">
        <EmptyState variant="inline" message="Select a job to see its detail and actions." />
      </div>
    );
  }

  const isTerminal = TERMINAL_STATES.includes(job.state);
  const canStop = job.state === "queued" || job.state === "running";
  const canForce = allowUnsafeOverrides && !isTerminal;
  const logPath = job.log_path ?? undefined;

  const summary = (
    <Stack gap={2} className="job-detail-tab job-detail-tab-scroll">
      <ErrorTaxonomyPanel job={job} onOpenJob={onOpenJob} />
      <DefinitionList
        entries={[
          ["Kind", job.kind],
          ["Subjects", job.subject_ids.join(", ") || "—"],
          ["Group", job.group_id ?? "—"],
          ["Created", new Date(job.created_at).toLocaleString()],
          ["Elapsed", elapsedLabel(job, now)],
          ["CPU", pct(job.cpu_percent)],
          ["RSS", job.rss ? bytes(job.rss) : "—"],
          ["Exit code", job.exit_code ?? "—"],
        ]}
      />
      {density === "page" && (
        <div className="job-detail-console" data-testid="job-detail-console">
          <div className="job-detail-console-head text-eyebrow">Console · last 40 lines</div>
          {excerptQuery.isLoading && <Skeleton rows={8} />}
          {excerptQuery.isError && (
            <InlineError message="Could not load the console excerpt." onAction={() => void excerptQuery.refetch()} />
          )}
          {excerptQuery.data !== undefined && (
            <pre className="job-detail-log job-detail-console-body mono text-caption">
              {excerptQuery.data || "(no output yet)"}
            </pre>
          )}
        </div>
      )}
    </Stack>
  );

  return (
    <div className="job-detail" data-testid="job-detail" data-density={density}>
      <div className="job-detail-head">
        <JobStateChip state={job.state} pulse={job.liveness === "active"} />
        <span className="job-detail-title">
          {job.kind} · {job.subject_ids.join(", ") || "project"}
        </span>
        {job.liveness && <LivenessBadge state={job.liveness} />}
        <span className="job-detail-id mono text-caption">id {job.id}</span>
        {/* ONE folder for the whole pane, in its header — the job's own directory. Every artifact
            a job writes lives there, so the per-row folder icons the artifact list used to carry
            were N buttons that all opened the same place (maintainer review). */}
        {logPath && (
          <IconButton
            aria-label="Show the job folder"
            data-testid="job-detail-reveal"
            icon={<FolderOpen size={14} />}
            onClick={() => reveal(logPath)}
          />
        )}
        {headerControls}
      </div>

      <div className="job-detail-actions">
        {canStop && (
          <Button variant="secondary" size="sm" icon={<Square size={14} />} onClick={() => setConfirm("stop")}>
            Stop
          </Button>
        )}
        {isTerminal && (
          <Button variant="secondary" size="sm" icon={<RotateCw size={14} />} loading={rerun.isPending} onClick={() => rerun.mutate()}>
            Rerun
          </Button>
        )}
        {canForce && (
          <Button variant="destructive" size="sm" icon={<Zap size={14} />} onClick={() => setConfirm("force")}>
            Force
          </Button>
        )}
        {isTerminal && (
          <Button variant="destructive" size="sm" icon={<Trash2 size={14} />} onClick={() => setConfirm("delete")}>
            Delete
          </Button>
        )}
      </div>

      <div className="job-detail-body">
        {/* The tabs own the pane's remaining height, not just their natural height: the Raw log
             tab is a full console that has to reach the pane's bottom edge (`.job-detail-tabs`).

             At `panel` density this pane used to be the Summary alone, because the 260px panel
             had a Console tab of its own. That tab is gone (`store.ts`), so the panel gets the
             same three tabs the page has — which is what keeps a job's console one click from
             the table you picked the job out of, instead of a screen away. The Summary's 40-line
             console excerpt stays off at this density: it is what fills a 736px page pane, and
             in a 260px panel it would push the definition list off the top. */}
        <div className="job-detail-tabs">
            <Tabs
              value={tab}
              onValueChange={setTab}
              items={[
                { id: "summary", label: "Summary", content: summary },
                { id: "log", label: "Raw log", content: <JobRawLog job={job} /> },
                {
                  id: "artifacts",
                  label: `Artifacts${artifacts.length > 0 ? ` (${artifacts.length})` : ""}`,
                  content: (
                    <div className="job-detail-tab job-detail-tab-scroll">
                      <ArtifactList
                        artifacts={artifacts}
                        onView={(a) => window.open(artifactUrl(a.path), "_blank", "noopener")}
                        onOpen={(a) => openNative(a.path)}
                      />
                    </div>
                  ),
                },
            ]}
          />
        </div>
      </div>

      <AlertDialog
        open={confirm === "stop"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Stop job"
        description={`Stop the ${job.kind} job for ${job.subject_ids.join(", ") || "the project"}? Its process tree will be terminated.`}
        confirmLabel="Stop job"
        onConfirm={() => {
          setConfirm(null);
          stop.mutate();
        }}
      />
      <AlertDialog
        open={confirm === "force"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Force to terminal state"
        description="Marks this job failed without waiting for its process — only use this on a job that is stuck or has lost its process. It may leave orphaned work running."
        confirmLabel="Force"
        onConfirm={() => {
          setConfirm(null);
          force.mutate();
        }}
      />
      <AlertDialog
        open={confirm === "delete"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Delete job"
        description="Removes this job from the list permanently. Its outputs on disk are not affected."
        confirmLabel="Delete job"
        onConfirm={() => {
          setConfirm(null);
          del.mutate();
        }}
      />
    </div>
  );
}

/** Error taxonomy (plan §2.5): preflight / lock_wait / budget_wait / runner_failed /
 * oom_suspected / cancelled / skipped / lost / docker_unavailable, plus the last 20 output lines
 * when the server captured them. */
function ErrorTaxonomyPanel({ job, onOpenJob }: { job: JobStatus; onOpenJob: (jobId: string) => void }) {
  if (job.waiting_on && job.waiting_on.length > 0 && job.state === "queued") {
    return (
      <Callout kind="info" title="Waiting">
        {job.waiting_on.map((w) => (
          <Cluster key={w.job_id} gap={2}>
            <Chip kind="warning">{w.key}</Chip>
            <Button variant="ghost" size="sm" icon={<ExternalLink size={12} />} onClick={() => onOpenJob(w.job_id)}>
              View blocking job
            </Button>
          </Cluster>
        ))}
      </Callout>
    );
  }
  if (job.state === "cancelled") {
    return (
      <Callout kind="warning" title="Cancelled">
        {job.error?.message ?? "Cancelled by the user."}
      </Callout>
    );
  }
  if (job.state === "lost") {
    return (
      <Callout kind="danger" title={errorLabel("lost")}>
        The server restarted while this job was running and its process could not be reaccounted for. Rerun it from its
        spec.
      </Callout>
    );
  }
  if (job.error) {
    // One line, not the traceback: the CONSOLE excerpt below is the single place the tail is shown
    // (maintainer, Sep 2026 — the callout used to repeat it verbatim). `failureReason` picks the
    // last meaningful error line of the captured output, else "exited with code N".
    return (
      <Callout kind={job.state === "skipped" ? "warning" : "danger"} title={errorLabel(job.error.type)}>
        <p className="job-detail-reason mono" style={{ margin: 0 }} data-testid="job-detail-reason">
          {failureReason(job.error.last_lines, job.exit_code)}
        </p>
      </Callout>
    );
  }
  return null;
}

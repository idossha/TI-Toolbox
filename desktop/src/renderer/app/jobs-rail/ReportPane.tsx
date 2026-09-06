/**
 * The Report tab: the selected job's generated HTML report, in a sandboxed iframe over
 * `GET /api/files/report/{id}` — the same route and the same `sandbox="allow-scripts"` posture
 * `pages/results` uses, so a report renders identically wherever you reach it from.
 *
 * Resolving a job to a report id. The contract does not yet carry one: `JobStatus.artifacts` are
 * `{path, kind, label}` and `Report` is `{id, kind, title, path, created}`, so the link is made by
 * matching the report's `path` against the job's artifact paths. A `report`-kind job with no
 * artifact recorded yet falls back to its subject's newest report, which is what that job just
 * produced. Reported to F2 as an ask: put the report id on the artifact and this whole function
 * becomes one lookup.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState, InlineError, Skeleton } from "../../ui/Feedback";
import { Button } from "../../ui/Button";
import { getReports, reportUrl, type JobStatus, type Report } from "./api";

export function resolveReportId(job: JobStatus | undefined, reports: Report[] | undefined): string | null {
  if (!job || !reports || reports.length === 0) return null;
  const artifactPaths = new Set(job.artifacts.map((a) => a.path));
  const matched = reports.find((r) => artifactPaths.has(r.path));
  if (matched) return matched.id;
  if (job.kind !== "report") return null;
  const newest = [...reports].sort((a, b) => Date.parse(b.created) - Date.parse(a.created))[0];
  return newest?.id ?? null;
}

export function ReportPane({ job, onOpenResults }: { job: JobStatus | undefined; onOpenResults: () => void }) {
  const subject = job?.subject_ids[0];
  const reports = useQuery({
    queryKey: ["jobs-reports", subject],
    queryFn: () => getReports(subject!),
    enabled: !!subject,
  });

  const reportId = useMemo(() => resolveReportId(job, reports.data), [job, reports.data]);

  if (!job) {
    return (
      <div className="jobs-pane-empty">
        <EmptyState variant="inline" message="Select a job to see its report." />
      </div>
    );
  }
  if (reports.isLoading) {
    return (
      <div className="jobs-pane-empty">
        <Skeleton rows={4} />
      </div>
    );
  }
  if (reports.isError) {
    return (
      <div className="jobs-pane-empty">
        <InlineError message="Could not load this subject's reports." onAction={() => void reports.refetch()} />
      </div>
    );
  }
  if (!reportId) {
    return (
      <div className="jobs-pane-empty">
        <EmptyState
          variant="inline"
          message="This job has no report yet."
          actionLabel="Open in Results"
          onAction={onOpenResults}
        />
      </div>
    );
  }

  return (
    <div className="report-pane" data-testid="job-report-pane">
      <div className="report-pane-head">
        <span className="text-eyebrow">{reports.data?.find((r) => r.id === reportId)?.title ?? reportId}</span>
        <Button variant="ghost" size="sm" onClick={onOpenResults}>
          Open in Results
        </Button>
      </div>
      {/* Generated reports are static, always-light documents (like a printed page), so the frame
          keeps its own colour scheme rather than inheriting the app theme. */}
      <iframe
        className="report-pane-frame"
        title="Job report"
        src={reportUrl(reportId)}
        sandbox="allow-scripts"
        style={{ colorScheme: "light" }}
      />
    </div>
  );
}

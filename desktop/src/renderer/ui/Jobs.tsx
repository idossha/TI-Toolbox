import { Eraser, ExternalLink, FileText, FolderOpen } from "lucide-react";
import { useMemo, useState } from "react";
import type { JobLogLine } from "../app/jobs/logLines";
import { IconButton, Button } from "./Button";
import { JobStateChip, type JobState } from "./Status";
import { DataTable, type DataTableColumn } from "./DataTable";
import { VirtualList } from "./VirtualList";
import { Switch } from "./Toggle";
import { cn } from "./utils";

export interface JobSummary {
  id: string;
  kind: string;
  subject: string;
  state: JobState;
  /** 0-100, or undefined when the job has no progress reporting yet. */
  progressPct?: number;
  liveness?: "active" | "stalled";
  elapsed: string;
}

/**
 * One rail item: kind, subject, elapsed time, and a progress or liveness trace. `finishing` dims
 * it slightly — the collapsed rail (`app/jobs-rail/JobsRail.tsx`) keeps a job here for 4s after it
 * leaves a running state, showing its final `JobStateChip`, before dropping it (DESIGN.md quality
 * floor: "never just vanishes"); the dim + fade is cosmetic only and, like every other transition
 * in the app, is zeroed by `ui/base.css`'s `prefers-reduced-motion` rule.
 */
export function JobTrace({ job, onClick, finishing }: { job: JobSummary; onClick?: () => void; finishing?: boolean }) {
  return (
    <button type="button" className={cn("job-trace", finishing && "job-trace-finishing")} onClick={onClick}>
      <JobStateChip state={job.state} pulse={job.liveness === "active"} />
      <span className="job-trace-kind">{job.kind}</span>
      <span className="job-trace-subject">{job.subject}</span>
      {job.state === "running" && (
        <span className="job-trace-bar" aria-hidden>
          <span className="job-trace-bar-fill" style={{ width: `${job.progressPct ?? 8}%` }} />
        </span>
      )}
      <span className="job-trace-elapsed">{job.elapsed}</span>
    </button>
  );
}

export function JobsTable({ jobs, onOpen }: { jobs: JobSummary[]; onOpen: (job: JobSummary) => void }) {
  const columns = useMemo<DataTableColumn<JobSummary>[]>(
    () => [
      { header: "Kind", accessorKey: "kind" },
      { header: "Subject", accessorKey: "subject" },
      { header: "State", cell: ({ row }) => <JobStateChip state={row.original.state} pulse={row.original.liveness === "active"} /> },
      { header: "Progress", numeric: true, cell: ({ row }) => (row.original.progressPct !== undefined ? `${Math.round(row.original.progressPct)} %` : "—") },
      { header: "Elapsed", numeric: true, accessorKey: "elapsed" },
    ],
    [],
  );
  return <DataTable data={jobs} columns={columns} getRowId={(j) => j.id} onRowClick={onOpen} emptyMessage="No jobs yet." />;
}

export type { JobLogLine } from "../app/jobs/logLines";

export function JobConsole({
  sourceKey,
  lines,
  onRevealLogFile,
}: {
  /** Stable identity of the job or file; changing it restores the complete new transcript. */
  sourceKey: string;
  lines: JobLogLine[];
  onRevealLogFile?: () => void;
}) {
  const [follow, setFollow] = useState(true);

  return (
    <JobConsoleSource
      key={sourceKey}
      lines={lines}
      follow={follow}
      onFollowChange={setFollow}
      onRevealLogFile={onRevealLogFile}
    />
  );
}

function JobConsoleSource({
  lines,
  follow,
  onFollowChange,
  onRevealLogFile,
}: {
  lines: JobLogLine[];
  follow: boolean;
  onFollowChange: (follow: boolean) => void;
  onRevealLogFile?: () => void;
}) {
  const [filter, setFilter] = useState("");
  const [clearedThrough, setClearedThrough] = useState<number | null>(null);
  const afterClear = clearedThrough === null ? lines : lines.filter((line) => line.seq > clearedThrough);
  const filtered = filter
    ? afterClear.filter((line) => line.text.toLowerCase().includes(filter.toLowerCase()))
    : afterClear;

  function clear(): void {
    if (lines.length === 0) return;
    setClearedThrough(Math.max(...lines.map((line) => line.seq)));
  }

  return (
    <div className="job-console">
      <div className="job-console-toolbar">
        <input
          className="control"
          style={{ height: 24, fontFamily: "var(--font-mono)", fontSize: 12 }}
          placeholder="Filter…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="Filter log lines"
        />
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--ink-2)" }}>
            <Switch checked={follow} onCheckedChange={onFollowChange} aria-label="Follow tail" />
            Follow
          </label>
          <IconButton
            aria-label="Clear terminal"
            title="Clear terminal"
            icon={<Eraser size={14} />}
            disabled={afterClear.length === 0}
            onClick={clear}
          />
          {onRevealLogFile && (
            <IconButton aria-label="Reveal log file" icon={<FolderOpen size={14} />} onClick={onRevealLogFile} />
          )}
        </div>
      </div>
      {clearedThrough !== null && afterClear.length === 0 ? (
        <div className="job-console-empty" data-testid="job-console-cleared">
          Terminal cleared. New output will appear here.
        </div>
      ) : (
        <VirtualList
          className="job-console-lines"
          items={filtered}
          rowHeight={18}
          followTail={follow}
          getRowKey={(line, i) => line.key ?? `i${i}`}
          renderRow={(line) => (
            <div className={cn("job-console-line", line.level === "error" && "job-console-line-error", line.level === "warning" && "job-console-line-warning", line.level === "debug" && "job-console-line-debug")}>
              {line.text}
            </div>
          )}
        />
      )}
    </div>
  );
}

export interface ArtifactItem {
  path: string;
  kind: string;
  label: string;
}

export function ArtifactList({
  artifacts,
  onOpen,
  onView,
  onReveal,
}: {
  artifacts: ArtifactItem[];
  onOpen?: (artifact: ArtifactItem) => void;
  onView?: (artifact: ArtifactItem) => void;
  onReveal?: (artifact: ArtifactItem) => void;
}) {
  if (artifacts.length === 0) return <p className="field-help">No artifacts yet.</p>;
  return (
    <div className="artifact-list">
      {artifacts.map((a) => (
        <div key={a.path} className="artifact-row">
          <FileText size={14} style={{ color: "var(--ink-3)", flex: "none" }} />
          <span title={a.path} className="artifact-path">
            {a.label}
          </span>
          <div className="artifact-actions">
            {onView && (
              <Button variant="ghost" size="sm" onClick={() => onView(a)}>
                View
              </Button>
            )}
            {onOpen && (
              <Button variant="ghost" size="sm" icon={<ExternalLink size={12} />} onClick={() => onOpen(a)}>
                Open
              </Button>
            )}
            {onReveal && <IconButton aria-label={`Reveal ${a.label}`} icon={<FolderOpen size={14} />} onClick={() => onReveal(a)} />}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * The ONE jobs table. The 260px panel and the full `jobs` page render this same component with a
 * different `density` — they do not maintain two column lists that drift apart (plan §1).
 *
 * Columns, in the order the brief fixes them: state · kind · subjects · elapsed · CPU · RSS ·
 * waiting-on. Numbers are right-aligned and tabular (DESIGN.md §4.3). CPU and RSS show the run's
 * peak with its average beside it (`resourceLabel`); the per-page terminals own stage/progress,
 * so the STAGE column this table used to carry is gone (DECISIONS 2026-09-19).
 *
 * **That order is load-bearing.** `jobs-rail.css` sizes the columns by `nth-child` (the shared
 * `ui/DataTable` renders plain cells with no column identity), so reordering this array without
 * reordering those rules puts every width on the wrong column.
 */
import { useMemo, type CSSProperties } from "react";
import { Button } from "../../ui/Button";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { InlineError, Skeleton } from "../../ui/Feedback";
import { JobStateChip } from "../../ui/Status";
import { cn } from "../../ui/utils";
import type { JobStatus } from "./api";
import { cpuLabel, elapsedLabel, rssLabel } from "./format";
import { densitySpec, type JobsTableDensity } from "./model";

export interface JobsTableProps {
  jobs: JobStatus[];
  now: number;
  density: JobsTableDensity;
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** First load only — a refetch keeps the rows (DESIGN.md §4.4). */
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyMessage?: string;
  /** Draw ground rows to the bottom of the table's box — the shape of the list (`ui/DataTable`). */
  fill?: boolean;
  className?: string;
}

const RESOURCE_HINT = "Peak · average over the run, summed over the job's process tree";

/** `peak · avg x` as one tabular cell; the average is the quieter half. "—" only when never sampled. */
function ResourceCell({ label }: { label: { peak: string; avg: string | null } | null }) {
  if (!label) return <span className="jobs-cell-none">—</span>;
  return (
    <span className="jobs-cell-resource tabular-nums" title={label.avg ? `peak ${label.peak} · average ${label.avg}` : `peak ${label.peak}`}>
      {label.peak}
      {label.avg && <span className="jobs-cell-resource-avg"> · avg {label.avg}</span>}
    </span>
  );
}

function errorDetail(error: unknown): string | undefined {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return undefined;
}

export function JobsTable({
  jobs,
  now,
  density,
  selectedId,
  onSelect,
  loading = false,
  error,
  onRetry,
  emptyMessage = "No jobs match these filters.",
  fill = false,
  className,
}: JobsTableProps) {
  const spec = densitySpec(density);
  // Distinct ids per height: the panel and the page can be on screen at the same time, and one
  // shared testid would make every `getByTestId("jobs-table")` a strict-mode violation.
  const testId = density === "page" ? "jobs-table" : "jobs-panel-table";

  const columns = useMemo<DataTableColumn<JobStatus>[]>(
    () => [
      {
        id: "state",
        header: "State",
        cell: ({ row }) => <JobStateChip state={row.original.state} pulse={row.original.liveness === "active"} />,
      },
      { id: "kind", header: "Kind", accessorKey: "kind" },
      {
        id: "subjects",
        header: "Subjects",
        // The column takes the slack the fixed-width neighbours leave (`jobs-rail.css`), so a
        // batch of eight subjects has to give way somewhere; it ellipsizes and keeps the whole
        // list on hover rather than pushing CPU/RSS out of the box.
        cell: ({ row }) => {
          const label = row.original.subject_ids.join(", ") || "—";
          return (
            <span className="jobs-cell-subjects" title={label}>
              {label}
            </span>
          );
        },
      },
      { id: "elapsed", header: "Elapsed", numeric: true, cell: ({ row }) => elapsedLabel(row.original, now) },
      {
        id: "cpu",
        header: () => <span title={RESOURCE_HINT}>CPU</span>,
        numeric: true,
        cell: ({ row }) => <ResourceCell label={cpuLabel(row.original)} />,
      },
      {
        id: "rss",
        header: () => <span title={RESOURCE_HINT}>RSS</span>,
        numeric: true,
        cell: ({ row }) => <ResourceCell label={rssLabel(row.original)} />,
      },
      {
        id: "waiting",
        header: "Waiting on",
        cell: ({ row }) => {
          const w = row.original.waiting_on?.[0];
          if (!w) return <span className="jobs-cell-none">—</span>;
          return (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onSelect(w.job_id);
              }}
            >
              {w.key}
            </Button>
          );
        },
      },
    ],
    [now, onSelect],
  );

  if (error) {
    return (
      <div className={cn("jobs-table", className)}>
        <InlineError message="Could not load jobs." detail={errorDetail(error)} onAction={onRetry} />
      </div>
    );
  }

  return (
    <div
      className={cn("jobs-table", className)}
      data-density={density}
      data-testid={testId}
      style={{ "--row-h": `${spec.rowH}px` } as CSSProperties}
    >
      {loading ? (
        <div className="jobs-table-skeleton">
          <Skeleton rows={density === "panel" ? 5 : 10} />
        </div>
      ) : (
        <DataTable
          data={jobs}
          columns={columns}
          getRowId={(j) => j.id}
          selected={selectedId ? { [selectedId]: true } : {}}
          onRowClick={(j) => onSelect(j.id)}
          emptyMessage={emptyMessage}
          fill={fill}
        />
      )}
    </div>
  );
}

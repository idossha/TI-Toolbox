/**
 * The ONE jobs table. The 260px panel and the full `jobs` page render this same component with a
 * different `density` — they do not maintain two column lists that drift apart (plan §1).
 *
 * Columns, in the order the brief fixes them: state · kind · subjects · stage/progress · elapsed ·
 * CPU · RSS · waiting-on. Numbers are right-aligned and tabular (DESIGN.md §4.3).
 */
import { useMemo, type CSSProperties } from "react";
import { Button } from "../../ui/Button";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { InlineError, Skeleton } from "../../ui/Feedback";
import { JobStateChip, LivenessBadge } from "../../ui/Status";
import { bytes, cn, pct } from "../../ui/utils";
import type { JobStatus } from "./api";
import { elapsedLabel } from "./format";
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
      { id: "subjects", header: "Subjects", cell: ({ row }) => row.original.subject_ids.join(", ") || "—" },
      {
        id: "stage",
        header: "Stage",
        cell: ({ row }) => {
          const j = row.original;
          if (j.progress) {
            return (
              <span className="text-caption tabular-nums">
                {j.progress.stage} · {Math.round(j.progress.pct)} %
              </span>
            );
          }
          if (j.liveness) return <LivenessBadge state={j.liveness} />;
          return <span className="jobs-cell-none">—</span>;
        },
      },
      { id: "elapsed", header: "Elapsed", numeric: true, cell: ({ row }) => elapsedLabel(row.original, now) },
      { id: "cpu", header: "CPU", numeric: true, cell: ({ row }) => pct(row.original.cpu_percent) },
      { id: "rss", header: "RSS", numeric: true, cell: ({ row }) => (row.original.rss ? bytes(row.original.rss) : "—") },
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

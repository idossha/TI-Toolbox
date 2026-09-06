/**
 * The Jobs page's flat list, as **the** selection list (plan §1-C, C4).
 *
 * Jobs was the one list in v3 with no selection at all: a click opened the detail pane, and
 * cancelling five queued jobs meant opening five of them and pressing Cancel five times. 2.5.0's
 * whole point was that a batch is chosen the way a batch is run — as a set — so the rows get the
 * same grammar as every other list here (click / ⇧-range / ⌘-toggle / ⌘A / Esc, a checkbox column,
 * a filter, `All · None`, an `N of M selected` badge) and the bulk action acts on that set.
 *
 * Two things it keeps from `app/jobs-rail/JobsTable`, deliberately:
 *   - the **columns**, in the order the brief fixes them (state · kind · subjects · stage ·
 *     elapsed), so the page and the 260px rail still read as one component;
 *   - the **testid** `jobs-table` and the `role="row"` rows, which is what every existing jobs spec
 *     locates a job by — and which is also the *correct* ARIA for a multi-column table: a
 *     multi-selectable `grid`, not a `listbox` (`ui/SelectionList`'s `aria` prop).
 *
 * Selecting exactly one row also opens that job's detail pane, which is what a plain click did
 * before this — so the gesture people already have keeps working and the set is the new part.
 */
import { useMemo, type CSSProperties } from "react";
import { X } from "lucide-react";
import { Button } from "../../ui/Button";
import { InlineError, Skeleton } from "../../ui/Feedback";
import { SelectionList, type SelectionColumn, type SelectionItem } from "../../ui/SelectionList";
import { JobStateChip, LivenessBadge } from "../../ui/Status";
import { bytes, pct } from "../../ui/utils";
import type { JobStatus } from "../../app/jobs-rail/api";
import { elapsedLabel } from "../../app/jobs-rail/format";
import { densitySpec } from "../../app/jobs-rail/model";

function jobOf(item: SelectionItem): JobStatus {
  return item.value as JobStatus;
}

export function JobsSelectionTable({
  jobs,
  now,
  selected,
  onSelectedChange,
  /** Cancels every selected job. `null` while nothing selected is cancellable. */
  onCancelSelected,
  cancelling,
  loading,
  error,
  onRetry,
  emptyMessage = "No jobs match these filters.",
}: {
  jobs: JobStatus[];
  now: number;
  selected: string[];
  onSelectedChange: (ids: string[]) => void;
  onCancelSelected?: () => void;
  cancelling?: boolean;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyMessage?: string;
}) {
  const items = useMemo<SelectionItem[]>(
    () =>
      jobs.map((j) => ({
        id: j.id,
        // The state chip is the row's first cell, as it is in the 260px rail — the column order the
        // brief fixes (state · kind · subjects · stage · elapsed) is kept exactly.
        label: <JobStateChip state={j.state} pulse={j.liveness === "active"} />,
        // The filter has to match what the row SHOWS, not the job's opaque id: "ernie", "failed",
        // "sim" are the words a person types.
        search: `${j.id} ${j.kind} ${j.subject_ids.join(" ")} ${j.state}`,
        value: j,
      })),
    [jobs],
  );

  const columns = useMemo<SelectionColumn[]>(
    () => [
      { id: "kind", header: "Kind", cell: (i) => jobOf(i).kind },
      { id: "subjects", header: "Subjects", cell: (i) => jobOf(i).subject_ids.join(", ") || "—" },
      {
        id: "stage",
        header: "Stage",
        cell: (i) => {
          const j = jobOf(i);
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
      { id: "elapsed", header: "Elapsed", numeric: true, cell: (i) => elapsedLabel(jobOf(i), now) },
      { id: "cpu", header: "CPU", numeric: true, cell: (i) => pct(jobOf(i).cpu_percent) },
      { id: "rss", header: "RSS", numeric: true, cell: (i) => (jobOf(i).rss ? bytes(jobOf(i).rss as number) : "—") },
    ],
    [now],
  );

  if (error) {
    return (
      <div className="jobs-table">
        <InlineError message="Could not load jobs." detail={error instanceof Error ? error.message : undefined} onAction={onRetry} />
      </div>
    );
  }

  return (
    <div className="jobs-table" data-density="page" data-testid="jobs-table" style={{ "--row-h": `${densitySpec("page").rowH}px` } as CSSProperties}>
      {loading ? (
        <div className="jobs-table-skeleton">
          <Skeleton rows={10} />
        </div>
      ) : (
        <SelectionList
          items={items}
          value={selected}
          onChange={onSelectedChange}
          label="Jobs"
          aria="grid"
          headers={{ label: "State" }}
          columns={columns}
          filterPlaceholder="Filter jobs…"
          idPrefix="job"
          scrollTestId="jobs-selection-scroll"
          scrollFill
          emptyMessage={emptyMessage}
          toolbar={
            onCancelSelected && selected.length > 0 ? (
              <Button
                variant="secondary"
                size="sm"
                icon={<X size={14} />}
                loading={cancelling}
                onClick={onCancelSelected}
                data-testid="jobs-cancel-selected"
              >
                Cancel {selected.length}
              </Button>
            ) : undefined
          }
        />
      )}
    </div>
  );
}

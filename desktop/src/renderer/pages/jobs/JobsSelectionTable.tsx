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
 *   - the **columns**, from the one shared definition (`app/jobs-rail/columns.tsx`: state · kind ·
 *     subjects · elapsed · CPU · RSS), so the page, the 260px rail and the Summary tab read as one;
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
import type { JobStatus } from "../../app/jobs-rail/api";
import { JOB_COLUMNS, stateCell } from "../../app/jobs-rail/columns";
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
        // The state chip is the row's first cell, as it is in the 260px rail — the shared column
        // order (state · kind · subjects · elapsed · CPU · RSS) is kept exactly.
        label: stateCell(j),
        // The filter has to match what the row SHOWS, not the job's opaque id: "ernie", "failed",
        // "sim" are the words a person types.
        search: `${j.id} ${j.kind} ${j.subject_ids.join(" ")} ${j.state}`,
        value: j,
      })),
    [jobs],
  );

  // Every column but State (the row's `label` above) comes from the shared definition, so this
  // list, the 260px rail and the Summary tab print the same strings for the same job.
  const columns = useMemo<SelectionColumn[]>(
    () =>
      JOB_COLUMNS.filter((c) => c.id !== "state").map((c) => ({
        id: c.id,
        header: c.header,
        numeric: c.numeric,
        cell: (i) => c.cell(jobOf(i), now),
      })),
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

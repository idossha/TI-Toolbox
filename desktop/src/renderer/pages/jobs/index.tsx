/**
 * Jobs — height 3 of 3 (plan §1, "Jobs is one component at three heights"). The same
 * `JobsTable` + `JobDetailPane` the 260px panel renders, at full height, from the same
 * `useJobsModel()`; this file is composition only.
 *
 * What v1 had here and where it went: the 120px filter `Card` is now a 28px toolbar row; the
 * "Groups" tab is a grouping toggle in that toolbar (a tree and a table are two renderings of one
 * list, not two destinations); `JobDetailDrawer` — a modal opened over the table you were reading
 * — is now the right pane of a split. There is no page header (DESIGN.md §2); the nav rail
 * already says which page this is.
 *
 * v3 (program U1, DESIGN.md §2.1/§4.1 shape B — "never an empty pane"): the work pane
 * (`data-testid="page-work"`) takes every pixel the detail pane does not, and the detail pane
 * (`data-testid="page-right-pane"`, `jobs-page.css`) is a fixed 360/400px column that is **not
 * rendered at all** with nothing selected — `JobDetailPane`'s own empty state ("Select a job to
 * see its detail") is exactly the 360px-of-nothing U1 forbids, so this file omits the pane rather
 * than render that state. The split applies to both the flat table and the grouped tree — a tree
 * and a table are two renderings of one list, and selecting a job in either should open the same
 * detail.
 *
 * The page does not use `PageLayout`: its `standard` variant caps the work pane at 880px, which a
 * table-plus-detail split does not want, and it has no inspector and no action bar to place.
 * `.shell-content` is the scroller and already carries the shell's padding.
 *
 * Parity source: `TODO.md` §2.5 (there is no PyQt equivalent — 2.x had no job registry).
 */
import { useMemo, useState, type CSSProperties } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ListChecks } from "lucide-react";
import { Button } from "../../ui/Button";
import { RefetchBar } from "../../ui/Chrome";
import { PaneHeaderControls, PaneSeparator, usePaneController } from "../../ui/Layout";
import { Select, type SelectOption } from "../../ui/Select";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { notify } from "../../ui/Toast";
import { ApiError } from "../../api/client";
import type { PageDef } from "../../app/registry";
import { GroupsView } from "../../app/jobs-rail/GroupsView";
import { JobDetailPane } from "../../app/jobs-rail/JobDetailPane";
import { JobsSelectionTable } from "./JobsSelectionTable";
import { useJobsModel } from "../../app/jobs-rail/model";
import { ALL, applyJobsFilters, useJobsUi } from "../../app/jobs-rail/store";
import { JOB_KINDS, JOB_STATES, TERMINAL_STATES, cancelJob, getSettings, getSubjects, submitTestJob } from "../../app/jobs-rail/api";
import "./jobs-page.css";

/** One 28px filter: a 12px label that names the control, then the select. */
function Filter({
  id,
  label,
  value,
  onValueChange,
  options,
}: {
  id: string;
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
}) {
  return (
    <>
      <label className="jobs-toolbar-label text-caption" htmlFor={id}>
        {label}
      </label>
      <Select id={id} value={value} onValueChange={onValueChange} options={options} />
    </>
  );
}

function JobsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const model = useJobsModel();
  const { selectedId, select, filters, setFilter, grouped, setGrouped } = useJobsUi();

  const subjectsQuery = useQuery({ queryKey: ["jobs-subjects"], queryFn: getSubjects });
  const settingsQuery = useQuery({ queryKey: ["jobs-settings"], queryFn: getSettings });

  const filtered = useMemo(() => applyJobsFilters(model.all, filters), [model.all, filters]);

  /* C4: the rows are a set, and the bulk action acts on the set. Selecting exactly one row also
     opens that job's detail pane, which is what a plain click did before this — the gesture people
     already have keeps working, and the set is the new part. Only the jobs that can still be
     cancelled are sent: a finished job has nothing to cancel, and sending it anyway would make the
     toast lie about how many were stopped. */
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const cancellable = selectedIds.filter((id) => {
    const job = model.all.find((j) => j.id === id);
    return job !== undefined && !TERMINAL_STATES.includes(job.state);
  });
  const cancelSelected = useMutation({
    mutationFn: async () => {
      await Promise.all(cancellable.map((id) => cancelJob(id)));
      return cancellable.length;
    },
    onSuccess: (n) => {
      notify.success(n === 1 ? "Cancelled 1 job." : `Cancelled ${n} jobs.`);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => notify.error("Could not cancel the selected jobs.", e instanceof ApiError ? e.message : String(e)),
  });
  const selected = selectedId ? model.all.find((j) => j.id === selectedId) : undefined;

  // U13: the same pane primitive Results uses, not a second copy of it. `enabled` is the selection,
  // so with nothing selected the page owns neither the chord nor a collapsed state to restore --
  // "no pane" (U1) and "the user collapsed the pane" stay two different things.
  const pane = // `minWidth: 320` — the detail column is DESIGN.md §2.1's fixed 360/400 px column, not the run
  // shape's 45 vw document pane, so it keeps the narrower floor while gaining the 70 vw ceiling.
  usePaneController({ pageId: "jobs", name: "job detail", minWidth: 320, enabled: !!selected });

  // Empty state (fix round, lane FIX-D, defect 4). It used to be DESIGN.md §4.4's *whole-page*
  // row: one centred `EmptyState` and no filter strip. Measured at 1280x800 that page was **99.1 %
  // dead** — one sentence in the middle of a 1224 x 704 box — and it told a first-time user
  // nothing about what a job even looks like here. §4.4's *table* row is the one that applies: a
  // page whose populated state is a table shows that table, with its column headers and the
  // message inside its body. The toolbar stays for the same reason: it is the shape of the page.
  const isEmpty = !model.isLoading && !model.error && model.all.length === 0;

  const testJob = useMutation({
    mutationFn: () => submitTestJob(),
    onSuccess: (status) => {
      notify.success(`Queued: test ${status.kind} job for ${status.subject_ids.join(", ")}.`);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => notify.error("Could not submit the test job.", e instanceof ApiError ? e.message : String(e)),
  });

  const stateOptions: SelectOption[] = [{ value: ALL, label: "All states" }, ...JOB_STATES.map((s) => ({ value: s, label: s }))];
  const kindOptions: SelectOption[] = [{ value: ALL, label: "All kinds" }, ...JOB_KINDS.map((k) => ({ value: k, label: k }))];
  const subjectOptions: SelectOption[] = [
    { value: ALL, label: "All subjects" },
    ...(subjectsQuery.data ?? []).map((s) => ({ value: s.id, label: s.id })),
  ];

  return (
    <div className="jobs-page">
      <RefetchBar active={model.isRefetching} />
      <div className="jobs-toolbar" data-testid="jobs-toolbar">
        <Filter id="jobs-filter-state" label="State" value={filters.state} onValueChange={(v) => setFilter("state", v)} options={stateOptions} />
        <Filter id="jobs-filter-kind" label="Kind" value={filters.kind} onValueChange={(v) => setFilter("kind", v)} options={kindOptions} />
        <Filter
          id="jobs-filter-subject"
          label="Subject"
          value={filters.subject}
          onValueChange={(v) => setFilter("subject", v)}
          options={subjectOptions}
        />
        <SegmentedControl
          aria-label="Grouping"
          size="sm"
          value={grouped ? "groups" : "flat"}
          onValueChange={(v) => setGrouped(v === "groups")}
          options={[
            { value: "flat", label: "All jobs" },
            { value: "groups", label: "Groups", title: "Group jobs by submission group, as subject → stage trees" },
          ]}
        />
        <span className="jobs-toolbar-count text-caption tabular-nums">
          {filtered.length} of {model.all.length}
        </span>
        {import.meta.env.DEV && (
          <Button variant="secondary" size="sm" loading={testJob.isPending} onClick={() => testJob.mutate()}>
            Submit test job
          </Button>
        )}
      </div>

      <div className="jobs-page-body">
        <div
          className="jobs-page-split"
          data-pane-mode={pane.mode}
          style={pane.width === null ? undefined : ({ "--jobs-pane-w": `${pane.width}px` } as CSSProperties)}
        >
          {/* Expanded: the table is not rendered at all, so `paneWidths().work` reads 0 rather than
              reporting the width of a table nobody can see (the same rule U1 puts on an empty pane). */}
          {!(selected && pane.expanded) && (
            <div className="jobs-page-work" data-testid="page-work">
              {grouped ? (
                <div className="jobs-page-groups" data-testid="jobs-groups">
                  <GroupsView jobs={filtered} now={model.now} onOpenJob={select} />
                </div>
              ) : (
                <>
                  <JobsSelectionTable
                    jobs={filtered}
                    now={model.now}
                    selected={selectedIds}
                    onSelectedChange={(ids) => {
                      setSelectedIds(ids);
                      if (ids.length === 1) select(ids[0] as string);
                    }}
                    onCancelSelected={cancellable.length > 0 ? () => cancelSelected.mutate() : undefined}
                    cancelling={cancelSelected.isPending}
                    loading={model.isLoading}
                    error={model.error}
                    onRetry={model.refetch}
                    emptyMessage={isEmpty ? "Nothing has run yet." : "No jobs match these filters."}
                  />
                  {isEmpty && (
                    <div className="jobs-page-empty-action">
                      <Button variant="secondary" size="sm" onClick={() => navigate("/preprocess")}>
                        Open Pre-processing
                      </Button>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
          {selected && !pane.expanded && <PaneSeparator controller={pane} />}
          {selected && !pane.collapsed && (
            <div
              className="jobs-page-right"
              data-testid="page-right-pane"
              data-pane-mode={pane.mode}
              /* An arrow, not `ref={pane.attach}`: passing a hook's returned function straight to
                 `ref` makes the React Compiler treat the whole object as a ref and reject every
                 `pane.*` read in this render. */
              ref={(el) => pane.attach(el)}
            >
              <JobDetailPane
                job={selected}
                density="page"
                allowUnsafeOverrides={settingsQuery.data?.allow_unsafe_overrides ?? false}
                onOpenJob={select}
                headerControls={<PaneHeaderControls controller={pane} />}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const page: PageDef = {
  id: "jobs",
  title: "Jobs",
  purpose: "Every job the server has run or is running, with live progress and controls.",
  navGroup: "system",
  order: 80,
  icon: ListChecks,
  shortcut: "8",
  Component: JobsPage,
  enabled: true,
};

export default page;

/**
 * Height 2 of 3: the 260px panel behind ⌘J. Tabs [Jobs][Host] as a `SegmentedControl` (one 28px
 * row, not a 44px tab strip) — see `store.ts`'s `JOBS_PANEL_TABS` for why Console and Report are
 * gone — and Jobs is a master–detail split: the table on the left, the selected job's detail and
 * actions in a pane on the right. Clicking a job opens its detail on the full Jobs page.
 */
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { IconButton } from "../../ui/Button";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { getSettings } from "./api";
import { HostPanel } from "./host/HostPanel";
import { JobDetailPane } from "./JobDetailPane";
import { JobsSplit } from "./JobsSplit";
import { JobsTable } from "./JobsTable";
import { JOBS_PANEL_TABS, useJobsUi } from "./store";
import type { JobsModel } from "./model";

export function JobsPanel({ model, onCollapse }: { model: JobsModel; onCollapse: () => void }) {
  const { selectedId, select, tab, setTab, clearFilters, setGrouped } = useJobsUi();
  const navigate = useNavigate();
  function openJob(id: string | null) {
    select(id);
    if (id === null) return;
    clearFilters();
    setGrouped(false);
    onCollapse();
    navigate("/jobs", { state: { openJobId: id } });
  }
  const settings = useQuery({ queryKey: ["jobs-settings"], queryFn: getSettings });
  const selected = selectedId ? model.all.find((j) => j.id === selectedId) : undefined;

  return (
    <div className="jobs-panel">
      <div className="jobs-panel-head">
        <SegmentedControl
          aria-label="Jobs panel"
          size="sm"
          value={tab}
          onValueChange={setTab}
          options={JOBS_PANEL_TABS.map((t) => ({ value: t.value, label: t.label }))}
        />
        <span className="jobs-panel-count text-caption tabular-nums">
          {model.runningCount} running · {model.all.length} total
        </span>
        <IconButton aria-label="Collapse jobs rail" icon={<ChevronDown size={16} />} onClick={onCollapse} />
      </div>

      <div className="jobs-panel-body">
        {tab === "jobs" && (
          <JobsSplit
            list={
              <JobsTable
                jobs={model.all}
                now={model.now}
                density="panel"
                selectedId={selectedId}
                onSelect={openJob}
                loading={model.isLoading}
                error={model.error}
                onRetry={model.refetch}
                emptyMessage="No jobs yet."
              />
            }
            detail={
              <JobDetailPane
                job={selected}
                density="panel"
                allowUnsafeOverrides={settings.data?.allow_unsafe_overrides ?? false}
                onOpenJob={openJob}
              />
            }
          />
        )}
        {tab === "host" && <HostPanel />}
      </div>
    </div>
  );
}

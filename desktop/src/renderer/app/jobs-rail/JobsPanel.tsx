/**
 * Height 2 of 3: the 260px panel behind ⌘J. Tabs [Jobs][Console][Host][Report] as a
 * `SegmentedControl` (one 28px row, not a 44px tab strip), and Jobs is a master–detail split —
 * the table on the left, the selected job's detail and actions in a pane on the right, inside the
 * panel. Nothing here opens a modal.
 */
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { IconButton } from "../../ui/Button";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { ResizablePanels } from "../../ui/Layout";
import { getSettings } from "./api";
import { ConsolePane } from "./ConsolePane";
import { HostPanel } from "./host/HostPanel";
import { JobDetailPane } from "./JobDetailPane";
import { JobsTable } from "./JobsTable";
import { ReportPane } from "./ReportPane";
import { JOBS_PANEL_TABS, useJobsUi } from "./store";
import type { JobsModel } from "./model";

export function JobsPanel({ model, onCollapse }: { model: JobsModel; onCollapse: () => void }) {
  const navigate = useNavigate();
  const { selectedId, select, tab, setTab } = useJobsUi();
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
          <ResizablePanels
            defaultLeftWidth={560}
            minLeftWidth={360}
            maxLeftWidth={880}
            left={
              <JobsTable
                jobs={model.all}
                now={model.now}
                density="panel"
                selectedId={selectedId}
                onSelect={select}
                loading={model.isLoading}
                error={model.error}
                onRetry={model.refetch}
                emptyMessage="No jobs yet."
              />
            }
            right={
              <JobDetailPane
                job={selected}
                density="panel"
                allowUnsafeOverrides={settings.data?.allow_unsafe_overrides ?? false}
                onOpenJob={select}
              />
            }
          />
        )}
        {tab === "console" && <ConsolePane job={selected} />}
        {tab === "host" && <HostPanel />}
        {tab === "report" && <ReportPane job={selected} onOpenResults={() => navigate("/results")} />}
      </div>
    </div>
  );
}

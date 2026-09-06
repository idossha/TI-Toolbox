/**
 * The right pane of every run page (DESIGN.md v3 §4.5/§4.6, program U2): a Plan grid on top and,
 * below it, the Terminal — or, on a page that passes a `scene`, the **Terminal · Scene** tab host
 * (plan of record `dev/notes/v3-scene-ia-plan.md` decision S7). Nothing else goes in it.
 *
 * The plan grid is capped at 45% of the pane height and scrolls internally past that, so a
 * twelve-subject plan cannot squeeze the log out of existence (§4.6, "Height").
 *
 * `scene` is additive: a page that passes nothing gets byte-for-byte the pane it always had —
 * Pre-processing has no head model to preview and must not grow a tab strip with one empty half.
 */
import { useState, type ReactNode } from "react";
import { PlanGrid, type PlanCellDetail } from "./PlanGrid";
import { JobTerminal } from "./JobTerminal";
import { RunPaneTabs, type RunPaneTab } from "./RunPaneTabs";
import type { PlanKind, PlanModel } from "./planModel";
import type { RunStep, TerminalSource } from "./terminalSources";
import "./run.css";

export interface RunPanelProps {
  kind: PlanKind;
  /** `null` while the page has nothing to plan — the grid renders its inline empty state. */
  plan: PlanModel | null;
  loading?: boolean;
  refetching?: boolean;
  error?: ReactNode;
  onRefetch?: () => void;
  /** Subjects the page has selected: the terminal's job filter and the grid's skeleton count. */
  subjects: string[];
  /** Extra kinds whose jobs this page's terminal may follow (Optimizer: ["flex","ex","mex"]). */
  jobKinds?: PlanKind[];
  onRevealLogFile?: (jobId: string) => void;
  /** Clicking a plan row pins the terminal; the page owns the state so ⌘K can clear it. */
  pinnedJobId?: string | null;
  onPinJob?: (jobId: string | null) => void;
  emptyMessage?: string;
  onEmptyAction?: () => void;
  /** The ordered steps of the current configuration — the terminal's "What will run" source. */
  steps?: RunStep[];
  /** Subjects that may run at once, for the preview's estimate (Pre-processing's parallel count). */
  parallel?: number;
  onTerminalSourceChange?: (source: TerminalSource) => void;
  /** A `<ScenePane>`. Given, the lower half becomes the Terminal · Scene tab host (S7). */
  scene?: ReactNode;
  onPaneTabChange?: (tab: RunPaneTab) => void;
  /** `<PaneHeaderControls controller={…} />`, shown in the tab row. Requires `scene`. */
  paneControls?: ReactNode;
  /** How the grid's cells read — `"counts"` for a summary column set (the Simulator's). */
  cellDetail?: PlanCellDetail;
}

export function RunPanel({
  kind,
  plan,
  loading,
  refetching,
  error,
  onRefetch,
  subjects,
  jobKinds,
  onRevealLogFile,
  pinnedJobId,
  onPinJob,
  emptyMessage,
  onEmptyAction,
  steps,
  parallel,
  onTerminalSourceChange,
  scene,
  onPaneTabChange,
  paneControls,
  cellDetail,
}: RunPanelProps) {
  /**
   * "Clicking a row pins the Terminal to that subject's job" (§4.5). A *plan* row has no job id —
   * the job does not exist until Run is pressed — so the row narrows the terminal's subject
   * filter instead of asserting an id it cannot know; clicking the same row again clears it.
   * `pinnedJobId` remains the explicit per-job pin, set from the terminal's own header.
   */
  const [rowSubject, setRowSubject] = useState<string | null>(null);
  const focused = rowSubject && subjects.includes(rowSubject) ? [rowSubject] : subjects;

  const terminal = (
    <JobTerminal
      kinds={jobKinds ?? [kind]}
      subjects={focused}
      pinnedJobId={pinnedJobId}
      onPinJob={onPinJob}
      onRevealLogFile={onRevealLogFile}
      steps={steps}
      plan={plan}
      parallel={parallel}
      onSourceChange={onTerminalSourceChange}
    />
  );

  return (
    <div className="run-panel" data-testid="run-panel">
      <PlanGrid
        plan={plan}
        loading={loading}
        refetching={refetching}
        error={error}
        onRefetch={onRefetch}
        skeletonRows={Math.max(1, subjects.length)}
        emptyMessage={emptyMessage}
        onEmptyAction={onEmptyAction}
        cellDetail={cellDetail}
        onSelectRow={(subject) => setRowSubject((prev) => (prev === subject ? null : subject))}
      />
      {scene ? (
        <RunPaneTabs kinds={jobKinds ?? [kind]} terminal={terminal} scene={scene} onTabChange={onPaneTabChange} controls={paneControls} />
      ) : (
        terminal
      )}
    </div>
  );
}

/**
 * The right pane of every run page (DESIGN.md v3 §4.5/§4.6, program U2): the Terminal — or, on a
 * page that passes a `scene`, the **Terminal · Scene** tab host (plan of record
 * `docs/dev/DECISIONS.md § 2026-09-04 (Scene service and retained pages)` decision S7). Nothing
 * else goes in it.
 *
 * The Plan grid that used to sit above the terminal was retired: its per-job time estimate had no
 * reliable basis and the rest of the card (job/CPU/mem counts, the subject×stage matrix) was not
 * worth keeping without it. Pages still compute a `PlanModel` for the action bar's digest and the
 * existing-outputs confirmation — only the on-screen card is gone.
 *
 * `scene` is additive: a page that passes nothing gets byte-for-byte the pane it always had —
 * Pre-processing has no head model to preview and must not grow a tab strip with one empty half.
 */
import type { ReactNode } from "react";
import { JobTerminal } from "./JobTerminal";
import { RunPaneTabs, type RunPaneTab } from "./RunPaneTabs";
import type { PlanKind } from "./planModel";
import type { RunStep, TerminalSource } from "./terminalSources";
import "./run.css";

export interface RunPanelProps {
  kind: PlanKind;
  /** Subjects the page has selected: the terminal's job filter. */
  subjects: string[];
  /** Extra kinds whose jobs this page's terminal may follow (Optimizer: ["flex","ex","mex"]). */
  jobKinds?: PlanKind[];
  onRevealLogFile?: (jobId: string) => void;
  pinnedJobId?: string | null;
  onPinJob?: (jobId: string | null) => void;
  /** Ids of the jobs this page session started; they stay in the terminal after they finish. */
  startedJobIds?: readonly string[];
  /**
   * Accepted and ignored since FXU2: the terminal's "What will run" preview was retired (an idle
   * pane must not look like a run in progress). The pages still compute their step list, so the
   * props stay in the signature rather than rippling an edit through four pages.
   */
  steps?: RunStep[];
  onTerminalSourceChange?: (source: TerminalSource) => void;
  /** A `<ScenePane>`. Given, the lower half becomes the Terminal · Scene tab host (S7). */
  scene?: ReactNode;
  onPaneTabChange?: (tab: RunPaneTab) => void;
  /** `<PaneHeaderControls controller={…} />`, shown in the tab row. Requires `scene`. */
  paneControls?: ReactNode;
}

export function RunPanel({
  kind,
  subjects,
  jobKinds,
  onRevealLogFile,
  pinnedJobId,
  onPinJob,
  startedJobIds,
  onTerminalSourceChange,
  scene,
  onPaneTabChange,
  paneControls,
}: RunPanelProps) {
  const terminal = (
    <JobTerminal
      kinds={jobKinds ?? [kind]}
      subjects={subjects}
      pinnedJobId={pinnedJobId}
      startedJobIds={startedJobIds}
      onPinJob={onPinJob}
      onRevealLogFile={onRevealLogFile}
      onSourceChange={onTerminalSourceChange}
    />
  );

  return (
    <div className="run-panel" data-testid="run-panel">
      {scene ? (
        <RunPaneTabs kinds={jobKinds ?? [kind]} ranHere={(startedJobIds?.length ?? 0) > 0} terminal={terminal} scene={scene} onTabChange={onPaneTabChange} controls={paneControls} />
      ) : (
        terminal
      )}
    </div>
  );
}

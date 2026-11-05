import type { ReactNode } from "react";
import { usePageSession } from "../../app/pageSession";
import { JobTerminal } from "../_shared/run/JobTerminal";
import { RunPaneTabs } from "../_shared/run/RunPaneTabs";
import "./panels.css";

/** Keep submitted jobs visible after completion and navigation, including successive actions. */
export function useExtensionJobs() {
  const [startedJobIds, setStartedJobIds] = usePageSession<string[]>("startedJobs", []);
  const [pinnedJobId, setPinnedJobId] = usePageSession<string | null>("pinnedJobId", null);
  function trackJob(job: { id: string }) {
    setStartedJobIds((previous) => [...new Set([...previous, job.id])]);
    setPinnedJobId(null);
  }
  return { startedJobIds, pinnedJobId, setPinnedJobId, trackJob };
}

/** Extensions keep their own plan vocabulary but share the run pages' live job console. */
export function ExtensionRunPanel({
  kind, subjects, plan, planLine, startedJobIds, pinnedJobId, setPinnedJobId, scene, paneControls, extraTab, sceneFocusKey,
}: {
  /** The job kinds this page's terminal follows. */
  kind: string | string[];
  subjects: string[];
  plan: ReactNode;
  /** One line standing for the plan, which then opens on a click: the scene is the column's point. */
  planLine?: ReactNode;
  extraTab?: { label: string; content: ReactNode };
  sceneFocusKey?: string;
  startedJobIds: readonly string[];
  pinnedJobId: string | null;
  setPinnedJobId: (id: string | null) => void;
  scene?: ReactNode;
  paneControls?: ReactNode;
}) {
  const kinds = Array.isArray(kind) ? kind : [kind];
  const terminal = <JobTerminal kinds={kinds} subjects={subjects} startedJobIds={startedJobIds} pinnedJobId={pinnedJobId} onPinJob={setPinnedJobId} />;
  return (
    <div className="run-panel extension-run-panel" data-testid="run-panel">
      {planLine ? (
        <details className="extension-plan extension-plan-line" aria-label="Plan" data-testid="extension-plan">
          <summary data-testid="extension-plan-line">{planLine}</summary>
          <div className="extension-plan-body">{plan}</div>
        </details>
      ) : (
        <section className="extension-plan" aria-label="Plan" data-testid="extension-plan">
          <header className="plan-grid-head"><span className="text-eyebrow">Plan</span></header>
          <div className="extension-plan-body">{plan}</div>
        </section>
      )}
      {scene ? <RunPaneTabs kinds={kinds} ranHere={startedJobIds.length > 0} terminal={terminal} scene={scene} controls={paneControls} extra={extraTab} sceneFocusKey={sceneFocusKey} /> : terminal}
    </div>
  );
}

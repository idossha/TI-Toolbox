/**
 * The lower half of the run pane: **Terminal · Scene**, one at a time (plan of record decision S7).
 *
 * The rule, and the failure each half of it prevents:
 *
 *  - **Scene while configuring, Terminal from the moment a job of this page's kind is running.**
 *    A 3D pane that stays on screen while a run is producing output hides the only place that
 *    output is visible on the page; a terminal that is shown before there is anything to show is
 *    the empty box the run pane was redesigned to stop being.
 *  - **A tab the user chose is never taken away from them.** The automatic switch applies only
 *    while nobody has picked a tab on this page; one click on either tab pins it for the rest of
 *    the session on that page. Without this, watching the scene while a batch runs is impossible —
 *    every new job of the kind would yank the pane back to the log.
 *
 *    "For the rest of the session on that page" was only true until the user left the page (lane
 *    N2): the choice lived in this component's `useState`, and a page unmounts on every navigation
 *    (`app/App.tsx` renders one route element), so a step onto Results and back dropped it —
 *    measured as `data-tab terminal → scene` on the Optimizer and the Analyzer by
 *    `tests/e2e/page-memory.spec.ts`. It is now held in the page's session bag
 *    (`app/pageSession.ts`), which is what the sentence above always claimed.
 *
 * Both panels stay mounted. The terminal is subscribed to a live job's event stream and the scene
 * holds 4 MB of decoded geometry and a WebGL context; unmounting either on a tab click would drop
 * the log tail and re-upload 150 k triangles on every switch. `hidden` (not `display:none` in a
 * style prop) is what `[hidden]` in the stylesheet acts on.
 */
import { useMemo, type ReactNode } from "react";
import { SegmentedControl } from "../../../ui/SegmentedControl";
import { usePageSession } from "../../../app/pageSession";
import { useJobsModel } from "../../../app/jobs-rail/model";
import { RUNNING_STATES } from "../../../app/jobs-rail/model";
import type { JobState } from "../../../ui/Status";
import "./run.css";

export type RunPaneTab = "terminal" | "scene";

/** True when any job of `kinds` is queued or running — the signal that flips the default tab. */
export function hasActiveJob(jobs: { kind: string; state: string }[], kinds: string[]): boolean {
  return jobs.some((job) => kinds.includes(job.kind) && RUNNING_STATES.includes(job.state as JobState));
}

/**
 * Which tab is shown: the user's explicit choice when there is one, otherwise Terminal while a job
 * of this page's kind is active and Scene while there is not.
 */
export function resolveTab(chosen: RunPaneTab | null, active: boolean): RunPaneTab {
  if (chosen) return chosen;
  return active ? "terminal" : "scene";
}

export interface RunPaneTabsProps {
  kinds: string[];
  terminal: ReactNode;
  scene: ReactNode;
  /** Reported upward so a page (or a spec) can assert which panel is showing. */
  onTabChange?: (tab: RunPaneTab) => void;
  /**
   * The pane's own expand/collapse buttons ({@link PaneHeaderControls}). They live in THIS row
   * because the gesture S7 asks for is "give the scene the full content width" — the control
   * belongs beside the thing it widens, and the run pane has no header of its own to put it in.
   */
  controls?: ReactNode;
  /**
   * True once this page session has started a job. The automatic Scene→Terminal switch would
   * otherwise flip back to Scene the instant that job finished, taking the output the user was
   * watching off the screen — the tab-level half of the same complaint that made a finished job
   * stay in the terminal (maintainer, 2026-09-07).
   */
  ranHere?: boolean;
}

export function RunPaneTabs({ kinds, terminal, scene, onTabChange, controls, ranHere }: RunPaneTabsProps) {
  const { all } = useJobsModel();
  const [chosen, setChosen] = usePageSession<RunPaneTab | null>("runPaneTab", null);
  const live = useMemo(() => hasActiveJob(all, kinds), [all, kinds]);
  const active = live || !!ranHere;
  const tab = resolveTab(chosen, active);

  return (
    <section className="run-tabs" data-testid="run-pane-tabs" data-tab={tab} data-active-job={live ? "1" : "0"} data-ran-here={ranHere ? "1" : "0"} data-chosen={chosen ?? ""}>
      <header className="run-tabs-head">
        <SegmentedControl
          aria-label="Run pane"
          size="sm"
          value={tab}
          onValueChange={(value) => {
            const next = value as RunPaneTab;
            setChosen(next);
            onTabChange?.(next);
          }}
          options={[
            { value: "terminal", label: "Terminal", title: "The log of the job this page is following" },
            { value: "scene", label: "Scene", title: "The subject's head model — pick from it, or from the form" },
          ]}
        />
        {controls}
      </header>
      <div className="run-tabs-body">
        <div className="run-tabs-panel" data-testid="run-pane-panel-terminal" hidden={tab !== "terminal"}>
          {terminal}
        </div>
        <div className="run-tabs-panel" data-testid="run-pane-panel-scene" hidden={tab !== "scene"}>
          {scene}
        </div>
      </div>
    </section>
  );
}

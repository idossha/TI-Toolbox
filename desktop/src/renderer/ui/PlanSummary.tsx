import type { ReactNode } from "react";
import { Callout, DefinitionList, Skeleton } from "./Feedback";
import { Stack } from "./Layout";
import { cn } from "./utils";

/**
 * The Plan/context panel every run screen shows before its primary action (DESIGN.md §4's
 * "Plan / context panel"). Before this existed each run page invented its own vocabulary and
 * layout for the same five facts — "ESTIMATED COST 8 CPUs · 16 GB" vs. "Jobs / Estimated CPUs /
 * Estimated memory" vs. "Runs queued / [cpu-icon] 8 / Memory 12 GB" vs. no panel at all
 * (ra_12 #7). `PlanSummary` is the one shape every page adopts: a `DefinitionList` of
 * Jobs · CPUs · Memory · Outputs · Waits, a warnings slot for preflight problems (existing-output
 * conflicts, infeasible search spaces, …), and one idle sentence for "nothing to plan yet".
 *
 * Pages own translating their own plan response into these props (`jobs.length`, `cost.cpus`,
 * `cost.mem_gb`, `PlanJob[]`, `LockConflict[]`, `warnings: string[]` — see
 * `contracts/openapi.yaml`'s `PlanResult`) — this component intentionally does not import
 * `components["schemas"]` itself, matching `ui/Jobs.tsx`'s own `JobSummary` pattern, so the design
 * system does not need to change shape every time the generated schema does.
 */
export interface PlanSummaryOutput {
  label: ReactNode;
  /** DESIGN.md §6.2: overwriting existing outputs is one of the actions an AlertDialog gates —
   * flagging it here is what tells the page it needs one. */
  willOverwrite?: boolean;
}

export interface PlanSummaryProps {
  /** The plan query is in flight — shows a skeleton in place of every row instead of a blank or
   * stale panel (DESIGN.md §6.7: "never a blank page"). */
  loading?: boolean;
  /** The plan query failed. Shown instead of the definition list. */
  error?: ReactNode;
  /**
   * Nothing to plan yet (no subject/ROI/target chosen) — e.g. "Pick a subject and ROI to see the
   * plan." Shown instead of the definition list whenever `jobs` is undefined, so a page does not
   * need its own `if (!plan) return <p>...</p>` branch (ra_12 #5's flex-search gap: an ungated
   * idle state, not just a bare empty card).
   */
  idleMessage?: string;
  jobs?: number;
  cpus?: number;
  memoryGb?: number;
  outputs?: PlanSummaryOutput[];
  waits?: ReactNode[];
  /** Preflight problems the plan surfaced — existing-output conflicts, lock waits, an infeasible
   * search space, and the like. DESIGN.md §6.3: "preflight problems show in the Plan panel with
   * the affected subject" — the Run button itself stays enabled regardless. */
  warnings?: string[];
  className?: string;
}

function OutputsCell({ outputs }: { outputs: PlanSummaryOutput[] }) {
  if (outputs.length === 0) return <>—</>;
  return (
    <Stack gap={1} className="plan-summary-outputs">
      {outputs.map((o, i) => (
        <span key={i} className={cn("plan-summary-output", o.willOverwrite && "plan-summary-output-overwrite")}>
          {o.label}
          {o.willOverwrite && " (overwrites)"}
        </span>
      ))}
    </Stack>
  );
}

function WaitsCell({ waits }: { waits: ReactNode[] }) {
  if (waits.length === 0) return <>none</>;
  return (
    <Stack gap={1}>
      {waits.map((w, i) => (
        <span key={i}>{w}</span>
      ))}
    </Stack>
  );
}

export function PlanSummary({ loading, error, idleMessage, jobs, cpus, memoryGb, outputs = [], waits = [], warnings = [], className }: PlanSummaryProps) {
  if (loading) {
    return (
      <Stack gap={2} className={cn("plan-summary", className)}>
        <Skeleton height={14} width="60%" />
        <Skeleton height={14} width="40%" />
        <Skeleton height={14} width="80%" />
      </Stack>
    );
  }
  if (error) {
    return (
      <Callout kind="danger" title="Could not load the plan.">
        {error}
      </Callout>
    );
  }
  if (jobs === undefined) {
    return <p className={cn("text-caption", "plan-summary-idle", className)}>{idleMessage ?? "Nothing to plan yet."}</p>;
  }
  return (
    <Stack gap={3} className={cn("plan-summary", className)}>
      <DefinitionList
        entries={[
          ["Jobs", jobs],
          ["CPUs", cpus ?? "—"],
          ["Memory", memoryGb !== undefined ? `${memoryGb} GB` : "—"],
          ["Outputs", <OutputsCell key="outputs" outputs={outputs} />],
          ["Waits", <WaitsCell key="waits" waits={waits} />],
        ]}
      />
      {warnings.length > 0 && (
        <Callout kind="warning" title="Before you run this">
          <Stack gap={1}>
            {warnings.map((w, i) => (
              <span key={i}>{w}</span>
            ))}
          </Stack>
        </Callout>
      )}
    </Stack>
  );
}

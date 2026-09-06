/**
 * The Plan grid (DESIGN.md v3 §4.5, u0-design-notes §3.3): a stats strip, a subject × stage
 * matrix of chips from one fixed vocabulary, one legend, and a warnings callout.
 *
 * It replaces the v2 Plan card, which printed "Output — exists, will skip" once per stage per
 * subject in prose. The matrix says the same thing in one 24px row per subject with no repeated
 * labels, which is what lets a four-subject plan sit in a 360px pane above a live terminal.
 */
import { RefreshCw } from "lucide-react";
import { IconButton } from "../../../ui/Button";
import { RefetchBar } from "../../../ui/Chrome";
import { Callout, EmptyState, InlineError, Skeleton } from "../../../ui/Feedback";
import { Chip, type SemanticKind } from "../../../ui/Status";
import type { PlanCell, PlanChip, PlanModel } from "./planModel";
import "./run.css";

export type ChipKind = SemanticKind;

/** The chip vocabulary → the shared semantic tokens. No page invents a sixth chip or a colour. */
export const PLAN_CHIP_KIND: Record<PlanChip, ChipKind> = {
  new: "success",
  skip: "neutral",
  overwrite: "warning",
  blocked: "danger",
  wait: "accent",
};

const CHIP_ORDER: PlanChip[] = ["new", "skip", "overwrite", "blocked", "wait"];

/** What each chip means, one clause, for the legend's title attribute. */
const CHIP_MEANING: Record<PlanChip, string> = {
  new: "nothing exists yet; this stage will be created",
  skip: "output exists and the configuration keeps it",
  overwrite: "output exists and will be replaced",
  blocked: "a precondition is missing; this stage cannot run",
  wait: "queues behind a job already holding the lock",
};

/** The chips actually present in the matrix, in vocabulary order. */
export function chipsPresent(plan: PlanModel): PlanChip[] {
  const seen = new Set<PlanChip>();
  for (const row of plan.subjects) for (const cell of row.cells) if (cell.chip) seen.add(cell.chip);
  return CHIP_ORDER.filter((c) => seen.has(c));
}

export interface PlanGridProps {
  plan: PlanModel | null;
  loading?: boolean;
  /** A refetch of a populated grid: a 2px bar, rows stay (DESIGN.md §4.4). */
  refetching?: boolean;
  error?: React.ReactNode;
  onRefetch?: () => void;
  /** Skeleton rows on first load — pass the selected-subject count so the panel does not resize
   *  when the data lands. */
  skeletonRows?: number;
  emptyMessage?: string;
  onEmptyAction?: () => void;
  onSelectRow?: (subject: string, cell: PlanCell) => void;
}

function StatTile({ id, label, value, tone }: { id: string; label: string; value: string; tone?: "warning" }) {
  return (
    <div className="plan-stat" data-testid={`plan-stat-${id}`} title="per job">
      <span className="plan-stat-label">{label}</span>
      <span className={tone === "warning" ? "plan-stat-value plan-stat-value-warning" : "plan-stat-value"}>{value}</span>
    </div>
  );
}

export function PlanGrid({
  plan,
  loading,
  refetching,
  error,
  onRefetch,
  skeletonRows = 2,
  emptyMessage = "Select a subject to see the plan.",
  onEmptyAction,
  onSelectRow,
}: PlanGridProps) {
  return (
    <section className="plan-grid" data-testid="plan-grid">
      <header className="plan-grid-head">
        <span className="text-eyebrow">Plan</span>
        {onRefetch && (
          <IconButton aria-label="Refresh the plan" size="sm" variant="ghost" icon={<RefreshCw size={12} />} onClick={onRefetch} />
        )}
      </header>
      <RefetchBar active={!!refetching && !loading} />

      {loading ? (
        <div className="plan-grid-body">
          <Skeleton height={40} />
          <Skeleton rows={Math.max(1, skeletonRows)} />
        </div>
      ) : error ? (
        <div className="plan-grid-body">
          <InlineError message="Could not build the plan." detail={typeof error === "string" ? error : undefined} onAction={onRefetch} />
        </div>
      ) : !plan ? (
        /* An empty plan is two readable lines, never a blank strip (FXU1): what is missing, and
           what happens once it is supplied. */
        <div className="plan-grid-body">
          <div className="plan-empty" data-testid="plan-empty">
            <span className="plan-empty-message">{emptyMessage}</span>
            <span className="plan-empty-hint">
              The grid then shows one row per subject and one column per stage, with what each will do.
            </span>
            {onEmptyAction && (
              <EmptyState variant="inline" message="" actionLabel="Choose subject ⌘P" onAction={onEmptyAction} />
            )}
          </div>
        </div>
      ) : (
        <div className="plan-grid-body">
          <div className="plan-stats">
            <StatTile id="jobs" label="Jobs" value={String(plan.stats.jobs)} />
            <StatTile id="cpus" label="CPUs" value={String(plan.stats.cpus)} />
            <StatTile id="mem" label="Mem" value={`${plan.stats.memoryGb} GB`} />
            <StatTile id="waits" label="Waits" value={String(plan.stats.waits)} tone={plan.stats.waits > 0 ? "warning" : undefined} />
          </div>

          {plan.subjects.length > 0 && plan.stages.length > 0 ? (
            <div className="plan-matrix-scroll">
              <table className="plan-matrix">
                <thead>
                  <tr>
                    <th scope="col" className="plan-matrix-subject-head">
                      Subject
                    </th>
                    {plan.stages.map((stage) => (
                      <th key={stage.id} scope="col" title={stage.label}>
                        {stage.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {plan.subjects.map((row) => (
                    <tr key={row.subject}>
                      <th scope="row" className="mono plan-matrix-subject">
                        {row.subject}
                      </th>
                      {row.cells.map((cell) => (
                        <td key={cell.stageId} data-testid={`plan-cell-${row.subject}-${cell.stageId}`} title={cell.outputDir || undefined}>
                          {cell.chip ? (
                            <button
                              type="button"
                              className="plan-cell-button"
                              onClick={() => onSelectRow?.(row.subject, cell)}
                              title={cell.outputDir || undefined}
                            >
                              <Chip kind={PLAN_CHIP_KIND[cell.chip]}>{cell.chip}</Chip>
                            </button>
                          ) : (
                            <span className="plan-cell-none" aria-label="not part of this run">
                              ·
                            </span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="plan-empty" data-testid="plan-empty">
              <span className="plan-empty-message">Nothing to run with this configuration.</span>
              <span className="plan-empty-hint">Pick at least one stage and one subject to fill the grid.</span>
            </div>
          )}

          {/* One muted line naming only the chips the matrix actually contains. A row of all five
              chips read as data rather than as a key — the failure the orchestrator called out. */}
          {chipsPresent(plan).length > 0 && (
            <p className="plan-legend" data-testid="plan-legend">
              {chipsPresent(plan).map((chip, i) => (
                <span key={chip}>
                  {i > 0 && <span className="plan-legend-sep"> · </span>}
                  <span title={CHIP_MEANING[chip]}>{chip}</span>
                </span>
              ))}
              <span className="plan-legend-sep"> — </span>
              <span>{`${plan.stats.jobs} job${plan.stats.jobs === 1 ? "" : "s"} in this plan`}</span>
            </p>
          )}

          {plan.warnings.length > 0 && (
            <div data-testid="plan-warnings" className="plan-warnings">
              <Callout kind="warning" title="Before you run this">
                {plan.warnings.map((w, i) => (
                  <div key={i}>{w}</div>
                ))}
              </Callout>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

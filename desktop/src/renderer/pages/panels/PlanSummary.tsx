/**
 * Shared Plan panel for every run screen under `pages/panels/**` and `pages/panels/source`
 * (design QA #7: "Plan vocabulary differs on every run screen ... one PlanSummary primitive").
 * Same shape/vocabulary as `pages/analyzer/PlanSummary.tsx` (Jobs · CPUs · Memory · Outputs ·
 * Waits) — kept as a local component here rather than moved into `ui/` because `ui/**` is owned
 * by the design-system agent (see `dev/notes/v3-build-plan.md` §2's ownership map); this converges
 * the four panels this lane owns onto one wording instead of inventing a fifth.
 */
import { DefinitionList, Skeleton, Callout } from "../../ui/Feedback";
import { Chip } from "../../ui/Status";
import type { PlanResult } from "./_shared";

export function PlanSummary({
  plan,
  loading,
  error,
  idleMessage = "Configure the run to see its plan.",
  serverErrors = [],
}: {
  plan: PlanResult | null | undefined;
  loading: boolean;
  error?: string;
  /** Shown when there is nothing yet to plan (no subjects/config chosen). */
  idleMessage?: string;
  /** `/api/validate/{kind}` field errors — shown above the plan, not by disabling Run (DESIGN.md §6.3). */
  serverErrors?: string[];
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      {serverErrors.length > 0 && (
        <Callout kind="danger">
          {serverErrors.map((e) => (
            <div key={e}>{e}</div>
          ))}
        </Callout>
      )}

      {loading && <Skeleton height={100} />}
      {!loading && error && <Callout kind="danger">{error}</Callout>}
      {!loading && !error && !plan && <p className="field-help">{idleMessage}</p>}

      {!loading && !error && plan && (
        <>
          <div>
            <div className="card-title" style={{ marginBottom: "var(--space-2)" }}>
              Output{plan.jobs.length === 1 ? "" : "s"}
            </div>
            {plan.jobs.length === 0 && <p className="field-help">Select a subject to resolve the output path.</p>}
            {plan.jobs.map((j, i) => (
              <div key={`${j.subject}-${i}`} style={{ marginBottom: "var(--space-2)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <span className="text-dense">{j.subject}</span>
                  {j.exists && (
                    <Chip kind={j.will_overwrite ? "warning" : "neutral"} dot>
                      {j.will_overwrite ? "will overwrite" : "already exists"}
                    </Chip>
                  )}
                </div>
                <div className="mono text-dense" style={{ color: "var(--ink-2)", wordBreak: "break-all" }}>
                  {j.output_dir}
                </div>
              </div>
            ))}
          </div>

          {plan.lock_conflicts.length > 0 && (
            <Callout kind="warning" title="Will queue behind">
              {plan.lock_conflicts.map((c) => (
                <div key={c.key}>
                  #{c.held_by} — {c.kind} {c.subject}
                </div>
              ))}
            </Callout>
          )}

          {plan.warnings.length > 0 && (
            <Callout kind="warning">
              {plan.warnings.map((w) => (
                <div key={w}>{w}</div>
              ))}
            </Callout>
          )}

          <DefinitionList
            entries={[
              ["Jobs", String(plan.jobs.length)],
              ["CPUs", String(plan.cost.cpus)],
              ["Memory", `${plan.cost.mem_gb} GB`],
            ]}
          />
        </>
      )}
    </div>
  );
}

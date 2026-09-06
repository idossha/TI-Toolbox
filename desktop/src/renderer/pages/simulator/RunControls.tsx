/**
 * The Simulator's plan + submit, split out of the v2 `PlanPanel` card. v3 puts the plan *grid* in
 * the shared `RunPanel` (DESIGN.md §4.5) and the button in the action bar (§2.3), so what is left
 * here is exactly the page-specific part: one `POST /api/plan/sim` per (subject, montage) row,
 * folded into one `PlanModel`, and the submit with its overwrite `AlertDialog` — one
 * `POST /api/jobs/groups` for the whole batch (R3), never a loop of per-job POSTs.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueries } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { Button } from "../../ui/Button";
import { notify } from "../../ui/Toast";
import {
  ExistingOutputsDialog,
  mergePlanResults,
  planModelFrom,
  submitJobGroup,
  useRunShortcut,
  type PlanModel,
  type PlanResult as SharedPlanResult,
  type PlanStage,
} from "../_shared/run";
import { planSim, type PlanResult } from "./api";
import { buildMontageSources, buildSimulationConfig, type GlobalParams } from "./buildConfig";
import type { SelectedRow } from "./types";

/** Debounces plan requests as the form changes (DESIGN.md §2: "on debounce"). */
function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

export interface SimPlan {
  model: PlanModel | null;
  loading: boolean;
  refetching: boolean;
  error: ReactNode;
  refetch: () => void;
  /** Non-null when the plan cannot resolve; the digest and the primary's tooltip read it verbatim. */
  blockedReason: string | null;
  /** Jobs whose output already exists — what the overwrite dialog counts. */
  existingCount: number;
}

/**
 * `subjectsBlocked` is the subject grammar's own sentence (`pages/_shared/subjects`'s
 * `subjectsBlockedReason`) — passed in rather than re-derived here so this page's wording for
 * "no subject" / "this subject cannot run" is the same wording every other page prints (J3).
 */
export function useSimPlan(
  rows: SelectedRow[],
  params: GlobalParams,
  subjects: string[],
  subjectsBlocked: string | null = null,
): SimPlan {
  const key = useDebounced(JSON.stringify({ rows, params }), 350);
  const debouncedRows = useMemo<SelectedRow[]>(() => (JSON.parse(key) as { rows: SelectedRow[] }).rows, [key]);
  const debouncedParams = useMemo<GlobalParams>(() => (JSON.parse(key) as { params: GlobalParams }).params, [key]);

  const queries = useQueries({
    queries: debouncedRows.map((row) => {
      const config = buildSimulationConfig(row, debouncedParams);
      const montageSources = buildMontageSources(row);
      return {
        queryKey: ["plan-sim", config, montageSources],
        queryFn: () => planSim(config, [row.subjectId], false, montageSources),
      };
    }),
  });

  const results = queries.map((q) => q.data).filter((d): d is PlanResult => !!d);
  const loading = rows.length > 0 && queries.some((q) => q.isPending);
  const refetching = queries.some((q) => q.isRefetching);
  const failed = queries.some((q) => q.error);

  const blockedReason = subjectsBlocked ?? (rows.length === 0 ? "Select at least one montage." : null);

  // Derived on every render rather than memoized: `useQueries` hands back a fresh array each
  // render, so a manual `useMemo` over it can only be keyed on a serialisation — which React
  // Compiler (correctly) refuses to treat as a preserved memoization. `planModelFrom` is a fold
  // over at most a few dozen plan jobs and the grid it feeds is cheap.
  const model: PlanModel | null =
    blockedReason || results.length === 0
      ? null
      : planModelFrom("sim", mergePlanResults(results as unknown as SharedPlanResult[]), subjects, {
          // Columns = one per selected montage, in the order they were picked (FXU1). The plan
          // itself would only produce a column for a montage whose `output_dir` came back, so a
          // row still resolving would silently drop out of the matrix.
          stages: debouncedRows.reduce<PlanStage[]>((acc, row) => {
            if (!acc.some((s) => s.id === row.name)) acc.push({ id: row.name, label: row.name });
            return acc;
          }, []),
        });

  return {
    model,
    loading,
    refetching,
    error: failed ? "Could not compute the plan for one or more jobs." : undefined,
    refetch: () => queries.forEach((q) => void q.refetch()),
    blockedReason,
    existingCount: results.reduce((n, r) => n + r.jobs.filter((j) => j.exists).length, 0),
  };
}

export function RunButton({
  rows,
  params,
  plan,
  parallelSubjects,
  onSubmitted,
  label,
}: {
  rows: SelectedRow[];
  params: GlobalParams;
  plan: SimPlan;
  /** The `Subjects in parallel` cap; goes onto the one group request as `parallel_subjects`. */
  parallelSubjects: number;
  onSubmitted: () => void;
  label: string;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  /**
   * ONE request for the whole batch (R3). This used to be a `for` loop of `POST /api/jobs`, one
   * per (subject, montage) row, awaited in sequence — which named itself sequential execution but
   * decided nothing: the server admitted whatever its budget allowed the moment each job landed.
   * Now the group is created queued in a single `POST /api/jobs/groups` carrying
   * `parallel_subjects`, and `tit.jobs.scheduler` releases the members that-many-at-a-time.
   *
   * Every row's config is resolved here and sent as its own `subject_configs` entry — the same
   * `(subject, montage)` job the plan grid previewed — so one subject with three montages is
   * three jobs, each config carrying only its own subject id (the server forces that too).
   */
  async function submit(overwriteExisting: boolean): Promise<void> {
    setSubmitting(true);
    const subjectIds = [...new Set(rows.map((r) => r.subjectId))];
    const subjectConfigs = rows.map((row) => ({
      subject_id: row.subjectId,
      config: buildSimulationConfig(row, params),
    }));
    try {
      const result = await submitJobGroup("sim", subjectConfigs[0]?.config ?? {}, subjectIds, parallelSubjects, {
        subjectConfigs,
        tags: subjectIds.length > 1 ? ["sim-batch"] : [],
        overwrite: overwriteExisting,
      });
      notify.success(
        result.jobs.length === 1
          ? `Queued: simulation for ${subjectIds[0]}`
          : `Queued ${result.jobs.length} simulation jobs${parallelSubjects > 1 ? ` (${parallelSubjects} at a time)` : " (one at a time)"}`,
      );
      onSubmitted();
    } catch {
      notify.error("Could not queue the simulation jobs.");
    } finally {
      setSubmitting(false);
      setConfirmOpen(false);
    }
  }

  function handleRun(): void {
    // §4.2 rule 8: the primary is never silently disabled — pressing it with an unresolvable plan
    // says why.
    if (plan.blockedReason) {
      notify.error(plan.blockedReason);
      return;
    }
    if (plan.existingCount > 0) setConfirmOpen(true);
    else void submit(false);
  }

  // ⌘⏎ fires exactly the function the button runs — one code path, so the shortcut can never do
  // something the button does not (DESIGN.md §2.3).
  useRunShortcut(handleRun);

  return (
    <>
      <Button
        variant="primary"
        icon={<Play size={14} />}
        loading={submitting}
        onClick={handleRun}
        disabled={!!plan.blockedReason}
        data-testid="run-button"
        title={plan.blockedReason ?? undefined}
      >
        {label}
      </Button>
      {/* The one existing-outputs question, shared with the other three run pages (C3). Skip is
          the answer this page never used to offer: before, "Cancel" was the only way not to
          overwrite, so finishing a half-done batch meant deselecting its finished rows by hand. */}
      <ExistingOutputsDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        existing={plan.existingCount}
        total={rows.length}
        noun="simulation output"
        busy={submitting}
        onDecide={(decision) => void submit(decision === "replace")}
      />
    </>
  );
}

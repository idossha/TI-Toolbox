/**
 * The two status cells every run page registers (DESIGN.md v3 §11.1): `lastJob` at priority 10 and
 * `planCost` at 20. One hook, so the four run pages cannot word them differently — and so a cell
 * with nothing to say (no plan yet, no job of this kind ever) is simply absent rather than a dash.
 */
import { useMemo } from "react";
import { useStatusCells } from "../../../app/statusCells";
import { useJobsModel } from "../../../app/jobs-rail/model";
import { elapsedLabel } from "../../../app/jobs-rail/format";
import { resolveFollowedJob, type FollowableJob } from "./JobTerminal";
import { planDigest, type PlanKind, type PlanModel } from "./planModel";
import type { JobState } from "../../../ui/Status";

/** `pre · running 4m12s` — the same job the page's terminal is following, stated in the bar. */
export function lastJobLabel(job: { kind: string; state: string; elapsed: string } | null): string | null {
  if (!job) return null;
  return `${job.kind} · ${job.state} ${job.elapsed}`;
}

export function useRunStatusCells(kind: PlanKind, subjects: string[], plan: PlanModel | null, jobKinds?: PlanKind[]): void {
  const { all, now } = useJobsModel();
  const kinds = jobKinds ?? [kind];
  const kindsKey = kinds.join(",");
  const subjectsKey = subjects.join(",");

  const job = useMemo(() => {
    const followable: FollowableJob[] = all.map((j) => ({
      id: j.id,
      kind: j.kind,
      subject: j.subject_ids.join(", ") || "project",
      subjects: j.subject_ids,
      state: j.state as JobState,
      elapsed: elapsedLabel(j, now),
      createdAt: Date.parse(j.created_at),
    }));
    return resolveFollowedJob(followable, kindsKey.split(",") as PlanKind[], subjectsKey ? subjectsKey.split(",") : []);
  }, [all, now, kindsKey, subjectsKey]);

  useStatusCells([
    { id: "lastJob", label: "Job", value: lastJobLabel(job), priority: 10 },
    { id: "planCost", label: "Plan", value: plan && !plan.blockedReason ? planDigest(plan) : null, priority: 20 },
  ]);
}

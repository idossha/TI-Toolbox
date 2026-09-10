/**
 * `planCounts` is a *derivation* of `PlanModel`, not a second count — which is why the number the
 * existing-outputs dialog asks about cannot disagree with the plan grid or the action-bar digest.
 * (It is what survived the run receipt, removed 2026-09-06: the grid and the digest are the
 * confirmation now, so only the numbers the dialog needs are still computed.)
 */
import { describe, expect, it } from "vitest";
import { planCounts, planModelFrom, type PlanResult } from "../../src/renderer/pages/_shared/run/planModel";

function result(jobs: Partial<PlanResult["jobs"][number]>[]): PlanResult {
  return {
    jobs: jobs.map((j) => ({ subject: "ernie", output_dir: "/out/x", exists: false, will_overwrite: false, ...j })) as PlanResult["jobs"],
    lock_conflicts: [],
    cost: { cpus: 4, mem_gb: 8 },
    warnings: [],
    resolved: null,
  };
}

describe("planCounts", () => {
  it("counts exactly the planned jobs the grid draws a cell for", () => {
    const plan = planModelFrom(
      "sim",
      result([
        { subject: "ernie", output_dir: "/out/L_Insula", stage: "L_Insula" },
        { subject: "ernie", output_dir: "/out/R_Insula", stage: "R_Insula" },
        { subject: "101", output_dir: "/out/L_Insula", stage: "L_Insula" },
      ]),
      ["101", "ernie"],
      { stages: [{ id: "L_Insula", label: "L_Insula" }, { id: "R_Insula", label: "R_Insula" }] },
    );
    // The grid draws a `·` for (101, R_Insula) and it is not counted, because a job that will not
    // run is not a job — so the count equals the model's own `stats.jobs`.
    expect(planCounts(plan).jobs).toBe(3);
    expect(planCounts(plan).jobs).toBe(plan.stats.jobs);
  });

  it("counts the existing outputs the shared dialog will ask about", () => {
    const plan = planModelFrom(
      "sim",
      result([
        { subject: "ernie", stage: "a", exists: true },
        { subject: "ernie", stage: "b", exists: true, will_overwrite: true },
        { subject: "ernie", stage: "c" },
      ]),
      ["ernie"],
    );
    expect(planCounts(plan)).toMatchObject({ jobs: 3, existing: 2, overwrites: 1 });
  });

  it("counts nothing for a page with no plan yet", () => {
    expect(planCounts(null)).toEqual({ jobs: 0, existing: 0, overwrites: 0, blocked: 0, waits: 0 });
  });
});

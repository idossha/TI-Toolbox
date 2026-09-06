/**
 * The receipt (plan C3) is a *derivation* of `PlanModel`, not a second count — which is the whole
 * reason it can be trusted next to the Run button. These assertions pin that: the number in
 * "This will run N jobs" is the number of non-`·` cells in the grid, and the existing-outputs line
 * is the same skip/overwrite cells the grid draws, so the receipt, the grid and the action bar's
 * digest cannot disagree.
 */
import { describe, expect, it } from "vitest";
import { planModelFrom, type PlanResult } from "../../src/renderer/pages/_shared/run/planModel";
import { receiptExistingLine, receiptFrom, receiptHeadline } from "../../src/renderer/pages/_shared/run/Receipt";

function result(jobs: Partial<PlanResult["jobs"][number]>[]): PlanResult {
  return {
    jobs: jobs.map((j) => ({ subject: "ernie", output_dir: "/out/x", exists: false, will_overwrite: false, ...j })) as PlanResult["jobs"],
    lock_conflicts: [],
    cost: { cpus: 4, mem_gb: 8 },
    warnings: [],
    resolved: null,
  };
}

describe("the receipt", () => {
  it("has exactly one row per planned job, in the page's display order", () => {
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
    const receipt = receiptFrom(plan);
    expect(receipt.jobs).toBe(3);
    expect(receipt.rows.map((r) => `${r.subject}·${r.stage}`)).toEqual(["101·L_Insula", "ernie·L_Insula", "ernie·R_Insula"]);
    // The grid draws a `·` for (101, R_Insula); the receipt has no row for it, because a job that
    // will not run is not a job.
    expect(receipt.jobs).toBe(plan.stats.jobs);
    expect(receiptHeadline(plan, receipt)).toBe("This will run 3 jobs:");
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
    const receipt = receiptFrom(plan);
    expect(receipt).toMatchObject({ jobs: 3, existing: 2, overwrites: 1 });
    expect(receiptExistingLine(receipt, "skip")).toBe("2 jobs already have output. You will be asked to skip or replace them.");
    expect(receiptExistingLine(receipt, "replace")).toBe("2 jobs already have output and will be replaced.");
  });

  it("says nothing about existing outputs when there are none", () => {
    const plan = planModelFrom("sim", result([{ subject: "ernie", stage: "a" }]), ["ernie"]);
    expect(receiptExistingLine(receiptFrom(plan), "skip")).toBeNull();
    expect(receiptHeadline(plan, receiptFrom(plan))).toBe("This will run 1 job:");
  });

  it("prints the page's own blocked sentence rather than a count of nothing", () => {
    const plan = planModelFrom("sim", result([]), [], { blockedReason: "Select at least one montage." });
    expect(receiptHeadline(plan, receiptFrom(plan))).toBe("Select at least one montage.");
    expect(receiptHeadline(null, receiptFrom(null))).toBe("Nothing to run yet.");
  });
});

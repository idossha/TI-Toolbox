/**
 * The search-cost read-out (`pages/optimizer/cost.ts`). It is stated in two places — beside the
 * control that changes it and in the action-bar digest — so it is worth one pure test that the
 * number itself is right, rather than trusting two renderings of it.
 */
import { describe, expect, it } from "vitest";
import { currentSplits, exCost, flexCost, mexCost } from "../../src/renderer/pages/optimizer/cost";
import { defaultExFormState, defaultMExFormState } from "../../src/renderer/pages/optimizer/exConfig";
import { defaultFlexFormState } from "../../src/renderer/pages/optimizer/flexConfig";

describe("currentSplits", () => {
  it("counts every split where both channels stay inside the limit", () => {
    // total 2.0, step 0.2 → c1 = 0.2 … 1.8; the 1.6 limit needs 0.4 ≤ c1 ≤ 1.6, i.e. seven of
    // the nine, because the partner channel carries 2.0 − c1 and must fit too.
    expect(currentSplits(2.0, 0.2, 1.6)).toBe(7);
  });

  it("keeps the balanced split when the limit is exactly half the total", () => {
    // Floating-point steps would otherwise drop c1 = 1.0 against a 1.0 limit.
    expect(currentSplits(2.0, 0.2, 1.0)).toBe(1);
  });

  it("is unlimited when there is no channel limit", () => {
    expect(currentSplits(2.0, 0.5, null)).toBe(3); // 0.5, 1.0, 1.5
  });

  it("is zero for a non-positive step, rather than dividing by it", () => {
    expect(currentSplits(2.0, 0, 1.6)).toBe(0);
  });
});

describe("exCost", () => {
  it("multiplies the four buckets and the splits, and counts distinct electrodes", () => {
    const form = {
      ...defaultExFormState(),
      buckets: { e1_plus: ["F7", "F5"], e1_minus: ["P7"], e2_plus: ["F3"], e2_minus: ["P3", "P5"] },
    };
    const cost = exCost(form);
    expect(cost.electrodes).toBe(6);
    expect(cost.montages).toBe(4);
    expect(cost.splits).toBe(7);
    expect(cost.combinations).toBe(28);
    expect(cost.line).toBe("6 electrodes · 7 splits · 28 combinations");
  });

  it("counts an electrode used in two buckets once", () => {
    const form = {
      ...defaultExFormState(),
      buckets: { e1_plus: ["F7"], e1_minus: ["P7"], e2_plus: ["F7"], e2_minus: ["P3"] },
    };
    expect(exCost(form).electrodes).toBe(3);
  });

  it("counts pool mode as four distinct electrodes, unordered within and between pairs", () => {
    const form = { ...defaultExFormState(), electrodeMode: "all" as const, pool: ["A", "B", "C", "D", "E"] };
    // 5·4·3·2 / 8 = 15
    expect(exCost(form).montages).toBe(15);
  });

  it("is zero montages for a pool that cannot make one montage", () => {
    const form = { ...defaultExFormState(), electrodeMode: "all" as const, pool: ["A", "B", "C"] };
    expect(exCost(form).montages).toBe(0);
  });
});

describe("mexCost", () => {
  it("multiplies all eight buckets and says the number is a pre-symmetry ceiling", () => {
    const buckets = Object.fromEntries(
      ["e1_plus", "e1_minus", "e2_plus", "e2_minus", "e3_plus", "e3_minus", "e4_plus", "e4_minus"].map((k, i) => [
        k,
        i === 0 ? ["A", "B"] : [`E${i}`],
      ]),
    );
    const cost = mexCost({ ...defaultMExFormState(), buckets });
    expect(cost.montages).toBe(2);
    expect(cost.combinations).toBe(2);
    expect(cost.line).toBe("9 electrodes · 4 pairs · 2 combinations");
    expect(mexCost({ ...defaultMExFormState(), buckets, symmetricBucket: true }).line).toContain("before symmetry");
  });
});

describe("flexCost", () => {
  it("is population × generations for a single-run search", () => {
    const cost = flexCost(defaultFlexFormState());
    expect(cost.solves).toBe(13 * 500);
    expect(cost.line).toBe("population 13 × 500 generations ≈ 6,500 solves");
  });

  it("multiplies by the multistart count", () => {
    expect(flexCost({ ...defaultFlexFormState(), nMultistart: 3 }).solves).toBe(13 * 500 * 3);
  });

  it("multiplies by the Pareto sweep's threshold combinations", () => {
    const form = {
      ...defaultFlexFormState(),
      goal: "focality" as const,
      focalityMode: "pareto" as const,
      paretoRoiPcts: "80,70",
      paretoNonRoiPcts: "20,30,40",
    };
    expect(flexCost(form).solves).toBe(13 * 500 * 6);
  });
});

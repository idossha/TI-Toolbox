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

  it("is the single balanced split when there is no channel limit", () => {
    // generate_current_ratios(total, step, None) == [(total / 2, total / 2)], whatever the step.
    expect(currentSplits(2.0, 0.5, null)).toBe(1);
    expect(currentSplits(0.4, 0.5, null)).toBe(1);
  });

  it("is zero for a non-positive step, rather than dividing by it", () => {
    expect(currentSplits(2.0, 0, 1.6)).toBe(0);
  });
  it("starts at an off-grid channel limit, including a single balanced split", () => {
    // Backend visits (1.5,.5), (1.1,.9), (.7,1.3), rather than multiples of .4.
    expect(currentSplits(2, 0.4, 1.5)).toBe(3);
    expect(currentSplits(2, 0.3, 1)).toBe(1);
    expect(currentSplits(2, 0.3, 0.9)).toBe(0);
  });

});

describe("exCost", () => {
  it("multiplies the four buckets and the splits, and counts distinct electrodes", () => {
    const form = {
      ...defaultExFormState(),
      buckets: { e1_plus: ["F7", "F5"], e1_minus: ["P7"], e2_plus: ["F3"], e2_minus: ["P3", "P5"] },
      channelLimit: 1.6,
    };
    const cost = exCost(form);
    expect(cost.electrodes).toBe(6);
    expect(cost.montages).toBe(4);
    expect(cost.splits).toBe(7);
    expect(cost.combinations).toBe(28);
    expect(cost.line).toBe("6 electrodes · 4 montages · 7 current splits · 28 iterations");
  });

  it("runs one balanced split by default, so iterations equal montages", () => {
    // The page starts at total 2.0 mA with a 1.0 mA limit (half the total): only 1.0 / 1.0.
    const form = {
      ...defaultExFormState(),
      buckets: { e1_plus: ["F7", "F5"], e1_minus: ["P7"], e2_plus: ["F3"], e2_minus: ["P3", "P5"] },
    };
    const cost = exCost(form);
    expect(cost.splits).toBe(1);
    expect(cost.combinations).toBe(cost.montages);
    expect(cost.line).toBe("6 electrodes · 4 montages · 1 current split · 4 iterations");
  });

  it("counts an electrode used in two buckets once", () => {
    const form = {
      ...defaultExFormState(),
      buckets: { e1_plus: ["F7"], e1_minus: ["P7"], e2_plus: ["F7"], e2_minus: ["P3"] },
    };
    expect(exCost(form).electrodes).toBe(3);
  });

  it("counts each physical montage of a pool once", () => {
    const form = { ...defaultExFormState(), electrodeMode: "all" as const, pool: ["A", "B", "C", "D", "E"], totalCurrent: 2, currentStep: 0.2, channelLimit: 1.6 };
    // C(5,4) = 5 sets × 3 ways to pair them. TI ignores a channel's polarity, and the 1.6 … 0.4
    // sweep is its own mirror, so the other 4! / 3 = 8 orderings of each montage repeat it.
    expect(exCost(form).montages).toBe(15);
  });

  it("is zero montages for a pool that cannot make one montage", () => {
    const form = { ...defaultExFormState(), electrodeMode: "all" as const, pool: ["A", "B", "C"] };
    expect(exCost(form).montages).toBe(0);
  });
  it("has one iteration per montage when only balanced currents are allowed", () => {
    const fixed = exCost({ ...defaultExFormState(), electrodeMode: "all", pool: ["A", "B", "C", "D"], totalCurrent: 2, currentStep: 0.2, channelLimit: 1 });
    expect(fixed.splits).toBe(1);
    expect(fixed.montages).toBe(3); // AB|CD, AC|BD, AD|BC at 1 mA each
    expect(fixed.combinations).toBe(fixed.montages);
  });

  it("matches an explicit enumeration of distinct stimulations, including imported duplicate labels", () => {
    // 2 mA in 0.2 mA steps, limit 1.6: channel 1 carries 1.6, 1.4, … 0.4 mA (seven splits).
    const splits = [1.6, 1.4, 1.2, 1.0, 0.8, 0.6, 0.4].map((a) => [a, Math.round((2 - a) * 10) / 10]);
    for (const pool of [["A", "B", "C", "D", "E"], ["A", "A", "B", "C", "D"]]) {
      const tuples = pool.flatMap(a => pool.flatMap(b => pool.flatMap(c => pool.map(d => [a, b, c, d]))));
      const valid = tuples.filter(tuple => new Set(tuple).size === 4);
      // One stimulation = the set of its channels, each an unordered pair at its current.
      const physical = new Set(
        valid.flatMap(([a, b, c, d]) =>
          splits.map(([i1, i2]) => [[a, b].sort().join("-") + "@" + i1, [c, d].sort().join("-") + "@" + i2].sort().join("|")),
        ),
      );
      const cost = exCost({ ...defaultExFormState(), electrodeMode: "all", pool, totalCurrent: 2, currentStep: 0.2, channelLimit: 1.6 });
      expect(cost.combinations).toBe(physical.size);
      expect(cost.montages * 7).toBe(physical.size);
    }
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
    expect(cost.line).toBe("9 electrodes · 4 channels · 2 combinations");
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

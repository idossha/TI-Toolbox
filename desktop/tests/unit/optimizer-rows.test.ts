import { describe, expect, it } from "vitest";
import {
  emptyOptimizerRow,
  flexFormForMethod,
  isFlexMethod,
  isRunnableOptimizerRow,
  OPT_COLUMN_MIN,
  optimizerAvoidLabel,
  optimizerJobsSummary,
  optimizerMethodSummary,
  optimizerTargetLabel,
  readStoredOptColumns,
  resolveOptColumnWidths,
  roiModesFor,
  rowGoal,
  rowPlanKind,
  withMethod,
  type OptimizerRow,
} from "../../src/renderer/pages/optimizer/rows";
import type { RoiValue } from "../../src/renderer/pages/_shared/roi";

/**
 * The Optimizer's jobs-table row model (lane OJ, 2026-09-06). Pure: the model, what a row *says*
 * about itself in the table's second line, and the column resolver whose whole contract is that
 * the widths sum to the container so the table can never scroll sideways.
 */
const cortical: RoiValue = { mode: "cortical", atlas: "DK40", regions: [{ id: 1, name: "insula", hemi: "lh" }] };

describe("the method vocabulary", () => {
  it("treats the three flex kinds as one family and ex/mEx as another", () => {
    expect(["flex", "flex_adaptive", "flex_pareto"].every((m) => isFlexMethod(m as never))).toBe(true);
    expect(["ex", "mex"].some((m) => isFlexMethod(m as never))).toBe(false);
  });

  it("plans the whole flex family under one kind, and ex/mEx under their own", () => {
    expect(rowPlanKind(emptyOptimizerRow({ method: "flex_pareto" }))).toBe("flex");
    expect(rowPlanKind(emptyOptimizerRow({ method: "mex" }))).toBe("mex");
  });

  it("offers each family only the ROI modes it can express", () => {
    expect(roiModesFor("flex")).toEqual(["cortical", "subcortical", "spherical"]);
    // There is no cortical ex-search target: the leadfield is volumetric.
    expect(roiModesFor("ex")).toEqual(["saved", "subcortical"]);
  });

  it("derives goal and focality mode from the method, so the two cannot disagree", () => {
    const base = emptyOptimizerRow().flex;
    expect(flexFormForMethod(base, "flex_adaptive")).toMatchObject({ goal: "focality", focalityMode: "adaptive" });
    expect(flexFormForMethod(base, "flex_pareto")).toMatchObject({ goal: "focality", focalityMode: "pareto" });
    // Coming back to plain Flex from an orchestrated mode lands on manual thresholds, not on a
    // kind the row no longer is.
    const adaptive = flexFormForMethod(base, "flex_adaptive");
    expect(flexFormForMethod(adaptive, "flex").focalityMode).toBe("manual");
    expect(rowGoal(emptyOptimizerRow({ method: "flex_pareto" }))).toBe("focality");
    // Ex/mEx rank every montage by the ROI field — there is no goal to choose.
    expect(rowGoal(emptyOptimizerRow({ method: "ex" }))).toBeNull();
  });

  it("keeps a target when the family does not change, and clears it when it does", () => {
    const row: OptimizerRow = { ...emptyOptimizerRow({ method: "flex" }), roi: cortical };
    expect(withMethod(row, "flex_pareto").roi).toEqual(cortical);
    // A saved CSV is not a cortical parcellation: carrying one across would leave a row that looks
    // configured and can never be planned.
    expect(withMethod(row, "ex").roi).toMatchObject({ mode: "saved", selected: [] });
  });
});

describe("isRunnableOptimizerRow", () => {
  const has = () => true;
  const hasNot = () => false;

  it("needs a subject and a complete target", () => {
    expect(isRunnableOptimizerRow(emptyOptimizerRow(), has)).toBe(false);
    expect(isRunnableOptimizerRow(emptyOptimizerRow({ subjectId: "ernie" }), has)).toBe(false);
    expect(isRunnableOptimizerRow({ ...emptyOptimizerRow({ subjectId: "ernie" }), roi: cortical }, has)).toBe(true);
  });

  it("additionally needs a leadfield for Ex/mEx, and never for Flex", () => {
    const ex: OptimizerRow = { ...emptyOptimizerRow({ subjectId: "ernie", method: "ex" }), roi: { mode: "saved", selected: ["A.csv"], combine: false, radius: 3, space: "subject" } };
    expect(isRunnableOptimizerRow(ex, hasNot)).toBe(false);
    expect(isRunnableOptimizerRow(ex, has)).toBe(true);
    expect(isRunnableOptimizerRow({ ...emptyOptimizerRow({ subjectId: "ernie" }), roi: cortical }, hasNot)).toBe(true);
  });
});

describe("what the row says about itself", () => {
  it("states a target in words, and says so when there is none", () => {
    expect(optimizerTargetLabel(emptyOptimizerRow().roi)).toBe("Choose a target…");
    expect(optimizerTargetLabel(cortical)).toBe("Cortical · DK40 · lh.insula");
    expect(optimizerTargetLabel({ mode: "saved", selected: ["A.csv", "B.csv"], combine: true, radius: 3, space: "mni" })).toBe(
      "Saved · A.csv + B.csv (combined) · r3 mm · MNI",
    );
    expect(
      optimizerTargetLabel({ mode: "spherical", spheres: [{ x: -45, y: 12, z: 6, radius: 10 }], space: "subject", volumetric: false, tissues: "GM" }),
    ).toBe("Sphere -45,12,6 r10 mm · Subject");
  });

  it("names the avoid ROI only for a focality goal", () => {
    const row: OptimizerRow = { ...emptyOptimizerRow(), roi: cortical };
    expect(optimizerAvoidLabel(row)).toBeNull();
    expect(optimizerAvoidLabel({ ...row, method: "flex_adaptive" })).toBe("avoid everything else");
    expect(
      optimizerAvoidLabel({ ...row, method: "flex_adaptive", flex: { ...row.flex, nonRoiMethod: "specific" }, nonRoi: cortical }),
    ).toBe("avoid Cortical · DK40 · lh.insula");
    // Ex/mEx have no non-ROI at all.
    expect(optimizerAvoidLabel({ ...row, method: "ex" })).toBeNull();
  });

  it("summarises the search in its own method's vocabulary, from the shared cost functions", () => {
    const flex = optimizerMethodSummary({ ...emptyOptimizerRow(), roi: cortical });
    expect(flex).toContain("2 pairs · 1 mA · ratio 1:1");
    expect(flex).toContain("≈ 6,500 solves");
    const row = emptyOptimizerRow({ method: "ex" });
    const ex = optimizerMethodSummary({ ...row, ex: { ...row.ex, buckets: { e1_plus: ["E1"], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E4"] } } });
    expect(ex).toBe("buckets: 4 · 2 mA total · 4 electrodes · 7 splits · 7 combinations");
    expect(optimizerMethodSummary(emptyOptimizerRow({ method: "mex" }))).toContain("buckets: 8");
  });

  it("summarises the table the way the disabled Run and the plan grid count it", () => {
    expect(optimizerJobsSummary([], [])).toBe("no jobs yet");
    const a = { ...emptyOptimizerRow({ subjectId: "ernie" }), roi: cortical };
    const b = { ...emptyOptimizerRow({ subjectId: "101" }), roi: cortical };
    expect(optimizerJobsSummary([a, b], [a, b])).toBe("2 searches · 2 subjects");
    expect(optimizerJobsSummary([a, b], [a])).toBe("1 search · 1 subject · 1 incomplete");
    expect(optimizerJobsSummary([a], [])).toBe("no complete job · 1 incomplete");
  });
});

describe("resolveOptColumnWidths", () => {
  const total = (w: { subject: number; method: number; net: number; goal: number; actions: number }) =>
    w.subject + w.method + w.net + w.goal + w.actions;

  it("always sums to the container — the invariant that keeps the table from scrolling sideways", () => {
    for (const container of [400, 560, 608, 830, 1200]) {
      expect(total(resolveOptColumnWidths(container, {})), `container ${container}`).toBe(container);
    }
  });

  it("honours a dragged width, and still sums to the container", () => {
    const w = resolveOptColumnWidths(830, { subject: 200 });
    expect(w.subject).toBe(200);
    expect(total(w)).toBe(830);
  });

  it("never lets a column fall below its minimum while the container has room", () => {
    const w = resolveOptColumnWidths(830, { subject: 10, method: 10 });
    expect(w.subject).toBe(OPT_COLUMN_MIN.subject);
    expect(w.method).toBe(OPT_COLUMN_MIN.method);
    expect(total(w)).toBe(830);
  });

  it("reads nothing rather than throwing from disabled or corrupt storage", () => {
    expect(readStoredOptColumns(undefined)).toEqual({});
    expect(readStoredOptColumns({ getItem: () => "not json" })).toEqual({});
    expect(readStoredOptColumns({ getItem: () => JSON.stringify({ subject: "wide" }) })).toEqual({});
    expect(readStoredOptColumns({ getItem: () => JSON.stringify({ subject: 180 }) })).toEqual({ subject: 180 });
  });
});

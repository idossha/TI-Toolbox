import { describe, expect, it } from "vitest";
import {
  emptyOptimizerRow,
  isFlexMethod,
  isRunnableOptimizerRow,
  OPT_COLUMN_MIN,
  OPT_METHODS,
  optimizerJobsSummary,
  optimizerMethodSummary,
  optimizerTargetLabel,
  readStoredOptColumns,
  resolveOptColumnWidths,
  roiModesFor,
  rowGoal,
  rowJobKind,
  rowPlanKind,
  rowStage,
  rowVariantLabel,
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
  it("offers exactly two methods — a search is free-placement or exhaustive", () => {
    // Coordinator, 2026-09-06: the five job kinds this page submits are not five methods. A method
    // is the kind of SEARCH; the kind is derived from options the row's editor already holds.
    expect(OPT_METHODS.map((m) => m.value)).toEqual(["flex", "ex"]);
    expect(isFlexMethod("flex")).toBe(true);
    expect(isFlexMethod("ex")).toBe(false);
  });

  it("offers each family only the ROI modes it can express", () => {
    expect(roiModesFor("flex")).toEqual(["cortical", "subcortical", "spherical"]);
    // There is no cortical ex-search target: the leadfield is volumetric.
    expect(roiModesFor("ex")).toEqual(["saved", "subcortical"]);
  });

  it("clears the target when the family changes, and is a no-op otherwise", () => {
    const row: OptimizerRow = { ...emptyOptimizerRow({ method: "flex" }), roi: cortical };
    expect(withMethod(row, "flex")).toBe(row);
    // A saved CSV is not a cortical parcellation: carrying one across would leave a row that looks
    // configured and can never be planned.
    expect(withMethod(row, "ex").roi).toMatchObject({ mode: "saved", selected: [] });
  });

  it("has no goal for an exhaustive search — it ranks every montage by the ROI field", () => {
    expect(rowGoal(emptyOptimizerRow({ method: "flex" }))).toBe("mean");
    expect(rowGoal(emptyOptimizerRow({ method: "ex" }))).toBeNull();
  });
});

describe("rowJobKind — the kind is derived, never chosen", () => {
  const flex = (patch: Partial<OptimizerRow["flex"]>): OptimizerRow => {
    const row = emptyOptimizerRow({ method: "flex" });
    return { ...row, flex: { ...row.flex, ...patch } };
  };

  it("reads a flex row's kind off its focality mode, exactly as 2.5.0 did", () => {
    expect(rowJobKind(flex({ goal: "mean" }))).toBe("flex");
    expect(rowJobKind(flex({ goal: "focality_tf" }))).toBe("flex");
    expect(rowJobKind(flex({ goal: "focality", focalityMode: "manual" }))).toBe("flex");
    expect(rowJobKind(flex({ goal: "focality", focalityMode: "adaptive" }))).toBe("flex_adaptive");
    expect(rowJobKind(flex({ goal: "focality", focalityMode: "pareto" }))).toBe("flex_pareto");
    // A mode only means something under the focality goal: `mean` with `pareto` left over from an
    // earlier edit is still a plain flex search.
    expect(rowJobKind(flex({ goal: "mean", focalityMode: "pareto" }))).toBe("flex");
  });

  it("reads an exhaustive row's kind off its electrode count — 4 is TI, 8 is mTI", () => {
    expect(rowJobKind(emptyOptimizerRow({ method: "ex", exPairs: 2 }))).toBe("ex");
    expect(rowJobKind(emptyOptimizerRow({ method: "ex", exPairs: 4 }))).toBe("mex");
  });

  it("plans the whole flex family under one kind, and ex/mEx under their own", () => {
    expect(rowPlanKind(flex({ goal: "focality", focalityMode: "pareto" }))).toBe("flex");
    expect(rowPlanKind(emptyOptimizerRow({ method: "ex", exPairs: 4 }))).toBe("mex");
    // The plan grid's three columns follow the same derivation.
    expect(rowStage(flex({ goal: "focality", focalityMode: "adaptive" }))).toBe("flex");
    expect(rowStage(emptyOptimizerRow({ method: "ex", exPairs: 2 }))).toBe("ex");
    expect(rowStage(emptyOptimizerRow({ method: "ex", exPairs: 4 }))).toBe("mex");
  });

  it("states the derived variant in words, and says nothing for a plain flex search", () => {
    expect(rowVariantLabel(flex({ goal: "mean" }))).toBe("");
    expect(rowVariantLabel(flex({ goal: "focality", focalityMode: "adaptive" }))).toBe("adaptive");
    expect(rowVariantLabel(flex({ goal: "focality", focalityMode: "pareto" }))).toBe("Pareto");
    expect(rowVariantLabel(emptyOptimizerRow({ method: "ex", exPairs: 2 }))).toBe("4 electrodes (TI)");
    expect(rowVariantLabel(emptyOptimizerRow({ method: "ex", exPairs: 4 }))).toBe("8 electrodes (mTI)");
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
  it("states a target as a short chip, region first, and says so when there is none", () => {
    expect(optimizerTargetLabel(emptyOptimizerRow().roi)).toBe("Choose a target…");
    // The region is what the user chose; the atlas is where it came from.
    expect(optimizerTargetLabel(cortical)).toBe("lh.insula · DK40");
    expect(optimizerTargetLabel({ mode: "saved", selected: ["A.csv", "B.csv"], combine: true, radius: 3, space: "mni" })).toBe(
      "A.csv + B.csv MNI",
    );
    expect(
      optimizerTargetLabel({ mode: "spherical", spheres: [{ x: -45, y: 12, z: 6, radius: 10 }], space: "subject", volumetric: false, tissues: "GM" }),
    ).toBe("Sphere r10 @ -45,12,6");
    // A union of spheres is counted, not listed — the sentence this replaced.
    expect(
      optimizerTargetLabel({
        mode: "spherical",
        spheres: [{ x: 1, y: 2, z: 3, radius: 5 }, { x: 4, y: 5, z: 6, radius: 5 }],
        space: "mni",
        volumetric: false,
        tissues: "GM",
      }),
    ).toBe("Sphere ×2 MNI");
  });

  it("summarises only the essentials — never what line 1 already says", () => {
    const flexRow = { ...emptyOptimizerRow(), roi: cortical };
    expect(optimizerMethodSummary(flexRow)).toBe("goal mean · 2 pairs · 1 mA · ratio 1:1");
    // The derived variant qualifies the goal — the only place it is stated.
    expect(optimizerMethodSummary({ ...flexRow, flex: { ...flexRow.flex, goal: "focality", focalityMode: "adaptive" } })).toBe(
      "goal focality (adaptive) · 2 pairs · 1 mA · ratio 1:1",
    );
    expect(optimizerMethodSummary({ ...flexRow, flex: { ...flexRow.flex, goal: "focality", focalityMode: "pareto" } })).toBe(
      "goal focality (Pareto) · 2 pairs · 1 mA · ratio 1:1",
    );
    expect(optimizerMethodSummary({ ...flexRow, flex: { ...flexRow.flex, optimizeCurrentRatio: true } })).toContain("ratio sweep 21");

    const row = emptyOptimizerRow({ method: "ex" });
    const filled = { ...row, ex: { ...row.ex, buckets: { e1_plus: ["E1"], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E4"] } } };
    expect(optimizerMethodSummary(filled)).toBe("4 electrodes (TI) · 2 mA · 7 splits · 7 combinations");
    // The electrode count is the MONTAGE's, fixed by the pairs — an unfilled row used to report
    // the distinct pool ("0 electrodes"), which said nothing about the search.
    expect(optimizerMethodSummary(row)).toBe("4 electrodes (TI) · 2 mA · 7 splits · 0 combinations");
    // mEx sweeps no amplitudes, so it reports no splits.
    expect(optimizerMethodSummary(emptyOptimizerRow({ method: "ex", exPairs: 4 }))).toBe("8 electrodes (mTI) · 2 mA · 0 combinations");
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

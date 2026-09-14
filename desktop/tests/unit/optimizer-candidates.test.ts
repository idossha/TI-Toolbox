/** 2026-09-13: authored asymmetric metrics and rotated poses pin candidate comparison/replay.
 * Run npx vitest run tests/unit/optimizer-candidates.test.ts. FEM and rendered anatomy are separate.
 */
import { describe, expect, it } from "vitest";
import { frontierIds, intensityColor, metricDefinition, tradeoffCandidates, type Candidate } from "../../src/renderer/pages/results/candidates/model";
import { candidateMetricsChanged, candidateRow, patchCandidateRow } from "../../src/renderer/pages/simulator/candidateHandoff";
import { buildSimulationConfig } from "../../src/renderer/pages/simulator/buildConfig";
import { DEFAULT_JOB_SETTINGS } from "../../src/renderer/pages/simulator/types";
import { emptyOptimizerRow } from "../../src/renderer/pages/optimizer/rows";
import { GOAL_OPTIONS } from "../../src/renderer/pages/optimizer/FlexSections";
import { jobsForRow, rowFormReason } from "../../src/renderer/pages/optimizer/plan";

const candidate = (id: string, target: number, background: number, key = "same-head-domain"): Candidate => ({ id, objective: -100, objective_label: "Minimized cost", objective_direction: "minimize", metrics: { roi_mean: target, background_p95: background }, metric_labels: {}, comparison_key: key, positions: [] });
const poses = [11, 21, 31, 41].map((x) => [[0, -1, 0, x], [1, 0, 0, x + 2], [0, 0, 1, x + 3], [0, 0, 0, 1]]);
const config = {
  subject_id: "ernie",
  montages: [{ _type: "Montage", name: "picked", mode: "flex_free", electrode_pairs: [[[11, 13, 14], [21, 23, 24]], [[31, 33, 34], [41, 43, 44]]], eeg_net: null, electrode_poses: poses, provenance: { run: "test-run", candidate_id: "trial-8" } }],
  conductivity: "vn", aniso_maxratio: 8, aniso_maxcond: 1.5, intensities: [0.7, -1.3], electrode_shape: "rect", electrode_dimensions: [9, 17], gel_thickness: 3, rubber_thickness: 1, output_fields: ["TI_max"], map_to_fsavg: false,
};
const handoff = { id: "trial-8", subject: "ernie", kind: "flex", run: "test-run", config };

describe("candidate comparison", () => {
  it("uses measured common metrics and excludes incompatible/missing observations", () => {
    const all = [candidate("a", 3, 2), candidate("b", 2, 3), candidate("c", 4, 4), candidate("other", 99, 0, "other-domain"), candidate("missing", NaN, 2)];
    const comparable = tradeoffCandidates(all, "same-head-domain", "background_p95");
    expect(comparable.map((c) => c.id)).toEqual(["a", "b", "c"]);
    expect([...frontierIds(comparable, "background_p95")]).toEqual(["a", "c"]);
    expect(tradeoffCandidates(all, null, "background_p95")).toEqual([]);
  });
  it("keeps equal candidates on the evaluated frontier", () => {
    expect([...frontierIds([candidate("a", 2, 1), candidate("b", 2, 1)], "background_p95")]).toEqual(["a", "b"]);
  });
});

describe("normal simulation handoff", () => {
  it("preserves every pose, signed current, and original configuration field", () => {
    const row = candidateRow(handoff);
    expect(buildSimulationConfig(row, DEFAULT_JOB_SETTINGS)).toEqual(config);
    expect(candidateMetricsChanged(row)).toBe(false);
    const changed = { ...row, currents: "0.8,-1.2", settings: { ...row.settings!, dimensions: [13, 19] as [number, number] } };
    const built = buildSimulationConfig(changed, DEFAULT_JOB_SETTINGS);
    expect(built.intensities).toEqual([0.8, -1.2]);
    expect(built.electrode_dimensions).toEqual([13, 19]);
    expect((built.montages as typeof config.montages)[0]?.electrode_poses).toEqual(poses);
    expect(candidateMetricsChanged(changed)).toBe(true);
    expect(config.intensities).toEqual([0.7, -1.3]);
  });
  it("clears exact replay metadata when subject or positions are replaced", () => {
    const row = candidateRow(handoff);
    expect(patchCandidateRow(row, { subjectId: "other" }).candidate).toBeUndefined();
    expect(patchCandidateRow(row, { xyzPairs: [[[0, 1, 2], [3, 4, 5]]] }).candidate).toBeUndefined();
    expect(patchCandidateRow(row, { currents: "2,1" }).candidate).toEqual(row.candidate);
  });
  it("rejects subject mismatch and incomplete geometry before creating a draft", () => {
    expect(() => candidateRow({ ...handoff, subject: "different" })).toThrow("this subject");
    expect(() => candidateRow({ ...handoff, config: { ...config, intensities: [1] } })).toThrow("incomplete");
  });
});

it("historic threshold mode is visibly retired and cannot generate a new plan", () => {
  const row = emptyOptimizerRow({ method: "flex" });
  row.subjectId = "ernie";
  row.flex.goal = "focality";
  expect(rowFormReason(row)).toContain("retired");
  expect(jobsForRow(row, { atlas: () => () => undefined, leadfield: () => null })).toEqual([]);
  expect(row.flex.goal).toBe("focality");
  row.flex.goal = "focality_tf";
  expect(rowFormReason(row)).toBeNull();
});

it("presents the three scientific goals without renaming their definitions", () => {
  expect(GOAL_OPTIONS).toEqual([
    { value: "mean", label: "Mean TImax" },
    { value: "max", label: "Max TImax (99.9%)" },
    { value: "focality_tf", label: "Focality" },
  ]);
});

it("encodes ROI intensity with a bounded sequential gradient and handles a constant range", () => {
  const rgb = (value: number) => intensityColor(value, 1, 5).match(/\d+/g)!.map(Number);
  const colors = [1, 2, 3, 4, 5].map(rgb);
  // Higher intensity moves consistently from blue to orange; no objective weighting is used.
  for (let i = 1; i < colors.length; i++) {
    expect(colors[i]![0]).toBeGreaterThan(colors[i - 1]![0]!);
    expect(colors[i]![1]).toBeLessThan(colors[i - 1]![1]!);
    expect(colors[i]![2]).toBeLessThan(colors[i - 1]![2]!);
  }
  expect(intensityColor(-1, 1, 5)).toBe(intensityColor(1, 1, 5));
  expect(intensityColor(9, 1, 5)).toBe(intensityColor(5, 1, 5));
  expect(intensityColor(3, 3, 3)).toBe(intensityColor(3, 1, 5));
});

it("updates archived terminology while preserving scientific domain and percentile", () => {
  expect(metricDefinition("Target mean / background p95; whole-GM includes ROI"))
    .toBe("ROI mean / non-ROI p95; whole-GM includes ROI");
});

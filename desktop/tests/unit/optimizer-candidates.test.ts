/** 2026-09-13: authored asymmetric metrics and rotated poses pin candidate comparison/replay.
 * 2026-11-01: ex/mEx plot axes come from final_output.csv (header as tit.opt.ex.results.build_csv_rows
 * writes it); tick values are hand-derived below. Run npx vitest run tests/unit/optimizer-candidates.test.ts.
 * FEM and rendered anatomy are separate.
 */
import { describe, expect, it } from "vitest";
import { csvMetricColumns, frontierIds, intensityColor, metricDefinition, niceTicks, tradeoffCandidates, type Candidate } from "../../src/renderer/pages/results/candidates/model";
import { candidateMetricsChanged, candidateRow, patchCandidateRow } from "../../src/renderer/pages/simulator/candidateHandoff";
import { buildSimulationConfig } from "../../src/renderer/pages/simulator/buildConfig";
import { defaultJobSettings } from "../../src/renderer/pages/simulator/types";
import { GOAL_OPTIONS } from "../../src/renderer/pages/optimizer/FlexSections";

const candidate = (id: string, target: number, background: number, key = "same-head-domain"): Candidate => ({ id, objective: -100, objective_label: "Minimized cost", objective_direction: "minimize", metrics: { roi_mean: target, background_p95: background }, metric_labels: {}, comparison_key: key, positions: [] });
const poses = [11, 21, 31, 41].map((x) => [[0, -1, 0, x], [1, 0, 0, x + 2], [0, 0, 1, x + 3], [0, 0, 0, 1]]);
const config = {
  subject_id: "ernie",
  montages: [{ _type: "Montage", name: "picked", mode: "flex_free", electrode_pairs: [[[11, 13, 14], [21, 23, 24]], [[31, 33, 34], [41, 43, 44]]], eeg_net: null, electrode_poses: poses, provenance: { run: "test-run", candidate_id: "trial-8" } }],
  conductivity: "vn", aniso_maxratio: 8, aniso_maxcond: 1.5, intensities: [0.7, -1.3], electrode_shape: "rect", electrode_dimensions: [9, 17], gel_thickness: 3, rubber_thickness: 1, output_fields: ["TI_max"], map_to_fsavg: false, map_to_vol: false, map_to_mni: false,
};
const handoff = { id: "trial-8", subject: "ernie", kind: "flex", run: "test-run", config };

describe("ex/mEx plot axes are final_output.csv columns", () => {
  const header = "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index,HFpeak_Focality,TI_Selectivity".split(",");
  const row = (id: string, line: string): Candidate => ({ ...candidate(id, NaN, NaN), metrics: {}, csv: Object.fromEntries(line.split(",").map((cell, i) => [header[i]!, cell])) });
  // (TImean_ROI, Focality, TImean_GM): c is dominated by a on every stated axis.
  const a = row("a", "A_B <> C_D_I1-1.0mA_I2-1.0mA,1.0,1.0,0.4000,0.2000,0.1000,2.0000,0.4000,,");
  const b = row("b", "A_C <> B_D_I1-1.0mA_I2-1.0mA,1.0,1.0,0.5000,0.3000,0.2000,1.5000,0.4500,,");
  const c = row("c", "A_D <> B_C_I1-1.0mA_I2-1.0mA,1.0,1.0,0.3000,0.1000,0.3000,1.0000,0.1000,,");
  it("offers the metric columns some row has a number for: never the montage, its currents, the x axis or an empty column", () => {
    expect(csvMetricColumns([a, b, c])).toEqual(["TImax_ROI", "TImean_GM", "Focality", "Composite_Index"]);
    const carrier = { ...c, csv: { ...c.csv, HFpeak_Focality: "1.2500", TI_Selectivity: "0.8000" } };
    expect(csvMetricColumns([a, b, carrier])).toEqual(["TImax_ROI", "TImean_GM", "Focality", "Composite_Index", "HFpeak_Focality", "TI_Selectivity"]);
    expect(csvMetricColumns([candidate("flex", 1, 2)])).toEqual([]);
  });
  it("plots CSV cells against TImean_ROI, and draws a frontier only for a column with a stated direction", () => {
    expect(tradeoffCandidates([a, b, c], "same-head-domain", "HFpeak_Focality")).toEqual([]);
    expect(new Set(frontierIds([a, b, c], "Focality"))).toEqual(new Set(["a", "b"]));
    expect(new Set(frontierIds([a, b, c], "TImean_GM"))).toEqual(new Set(["a", "b"]));
    expect(frontierIds([a, b, { ...c, csv: { ...c.csv, HFpeak_Focality: "1.0" } }], "HFpeak_Focality").size).toBe(0);
  });
});

describe("round-number plot ticks", () => {
  // Hand-derived: span / 5 is rounded to a 1, 2 or 5 x 10^k step; ticks are its multiples inside the range.
  it("labels the axis at round steps inside the data range, never only at its ends", () => {
    expect(niceTicks(0.0448, 0.0952).map((tick) => tick.label)).toEqual(["0.05", "0.06", "0.07", "0.08", "0.09"]);
    expect(niceTicks(0.9664, 2.048).map((tick) => tick.label)).toEqual(["1.0", "1.2", "1.4", "1.6", "1.8", "2.0"]);
    expect(niceTicks(-1, 1).map((tick) => tick.label)).toEqual(["-1.0", "-0.5", "0.0", "0.5", "1.0"]);
    expect(niceTicks(0.9664, 2.048)[0]!.value).toBeCloseTo(1, 12);
  });
  it("gives one tick for a single value and none for no data", () => {
    expect(niceTicks(3, 3)).toEqual([{ value: 3, label: "3" }]);
    expect(niceTicks(Infinity, -Infinity)).toEqual([]);
  });
});

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
    expect(buildSimulationConfig(row, defaultJobSettings())).toEqual(config);
    expect(candidateMetricsChanged(row)).toBe(false);
    const changed = { ...row, currents: "0.8,-1.2", settings: { ...row.settings!, dimensions: [13, 19] as [number, number] } };
    const built = buildSimulationConfig(changed, defaultJobSettings());
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

it("presents the four scientific goals without renaming their definitions", () => {
  expect(GOAL_OPTIONS).toEqual([
    { value: "mean", label: "Mean TImax" },
    { value: "max", label: "Max TImax (99.9%)" },
    { value: "focality_tf", label: "Threshold-free focality" },
    { value: "focality", label: "Threshold-based focality" },
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

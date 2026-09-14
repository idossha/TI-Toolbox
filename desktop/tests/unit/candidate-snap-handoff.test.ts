import { describe, expect, it } from "vitest";
import { candidateMetricsChanged, candidateOriginalPairs, candidateRow, restoreCandidateRow, snapCandidateRow } from "../../src/renderer/pages/simulator/candidateHandoff";
import { buildSimulationConfig } from "../../src/renderer/pages/simulator/buildConfig";
import { DEFAULT_JOB_SETTINGS, isRunnableRow } from "../../src/renderer/pages/simulator/types";

const pairs = [[[11, 12, 13], [21, 22, 23]], [[31, 32, 33], [41, 42, 43]]];
const poses = pairs.flat().map(([x, y, z]) => [[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z], [0, 0, 0, 1]]);
const config = { subject_id: "101", montages: [{ _type: "Montage", name: "candidate-8", mode: "flex_free", electrode_pairs: pairs, electrode_poses: poses, eeg_net: null }], intensities: [0.7, -1.3], electrode_shape: "rect", electrode_dimensions: [9, 17], rubber_thickness: 2 };

describe("candidate cap selection", () => {
  it("maps the chosen candidate without carrying optimized poses into labeled placement", () => {
    const row = candidateRow({ id: "8", subject: "101", run: "run-a", config });
    expect(isRunnableRow({ ...row, mappingPending: true })).toBe(false);
    const snapped = snapCandidateRow({ ...row, currents: "0.8,-1.2" }, "cap.csv", [["F3", "F4"], ["P3", "P4"]]);
    expect(isRunnableRow(snapped)).toBe(true);
    const simulation = buildSimulationConfig(snapped, DEFAULT_JOB_SETTINGS);
    expect(simulation.montages).toEqual([{ _type: "Montage", name: "candidate-8", mode: "flex_mapped", electrode_pairs: [["F3", "F4"], ["P3", "P4"]], eeg_net: "cap.csv" }]);
    expect(simulation.intensities).toEqual([0.8, -1.2]);
    expect(simulation.rubber_thickness).toBe(2);
    expect(candidateOriginalPairs(snapped)).toEqual(pairs);
    expect(candidateMetricsChanged(snapped)).toBe(true);
    expect(config.montages[0]!.electrode_poses).toEqual(poses);
  });
  it("restores exact coordinates and poses after changing caps, retaining edited currents", () => {
    const row = candidateRow({ id: "8", subject: "101", run: "run-a", config });
    const first = snapCandidateRow(row, "cap.csv", [["F3", "F4"], ["P3", "P4"]]);
    const second = snapCandidateRow(first, "other.csv", [["A", "B"], ["C", "D"]]);
    const restored = restoreCandidateRow(second);
    expect(buildSimulationConfig(restored, DEFAULT_JOB_SETTINGS)).toEqual(buildSimulationConfig(row, DEFAULT_JOB_SETTINGS));
    expect(candidateMetricsChanged(restored)).toBe(false);
    expect(restoreCandidateRow({ ...second, currents: "0.8,-1.2" }).currents).toBe("0.8,-1.2");
  });
});

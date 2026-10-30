/**
 * "Write NIfTI volumes" and its sub-option "Also in MNI space" move together (2026-10-30).
 *
 * MNI output is itself a NIfTI (`SimulationConfig` turns `map_to_vol` on for `map_to_mni`), so the
 * Simulator's two checkboxes follow the same rule: ticking MNI ticks the NIfTIs, unticking the
 * NIfTIs unticks MNI, and what reaches the server says the same. The expectations are that rule.
 *
 * Run: cd desktop && npx vitest run tests/unit/simulator-nifti-options.test.ts
 */
import { describe, expect, it } from "vitest";
import { buildSimulationConfig, type GlobalParams } from "../../src/renderer/pages/simulator/buildConfig";
import { withMni, withNiftis, type JobSettings, type SelectedRow } from "../../src/renderer/pages/simulator/types";

const base: JobSettings = {
  conductivity: "scalar",
  electrodeShape: "ellipse",
  dimensions: [8, 8],
  gelThickness: 1,
  outputFields: ["TI_max", "hf_peak", "hf_sar"],
  customConductivities: {},
};
const row: SelectedRow = { id: "r", subjectId: "ernie", source: "montage", name: "F3_F4", currents: "1,1", pairs: [["E1", "E2"], ["E3", "E4"]] };
const sent = (settings: JobSettings) => {
  const config = buildSimulationConfig({ ...row, settings }, base as GlobalParams);
  return [config.map_to_vol, config.map_to_mni];
};

describe("NIfTI options", () => {
  it("ticking MNI ticks the NIfTIs too", () => {
    const s = withMni(base, true);
    expect([s.writeNiftis, s.mapToMni]).toEqual([true, true]);
    expect(sent(s)).toEqual([true, true]);
  });

  it("unticking MNI keeps the subject-space NIfTIs", () => {
    const s = withMni(withMni(base, true), false);
    expect([s.writeNiftis, s.mapToMni]).toEqual([true, false]);
    expect(sent(s)).toEqual([true, false]);
  });

  it("unticking the NIfTIs unticks MNI", () => {
    const s = withNiftis(withMni(base, true), false);
    expect([s.writeNiftis, s.mapToMni]).toEqual([false, false]);
    expect(sent(s)).toEqual([false, false]);
  });

  it("ticking the NIfTIs alone writes subject space only", () => {
    expect(sent(withNiftis(base, true))).toEqual([true, false]);
    expect(sent(base)).toEqual([false, false]); // the default: no NIfTIs
  });
});

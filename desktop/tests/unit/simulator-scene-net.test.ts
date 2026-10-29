/**
 * Which head the Simulator's scene draws a named montage's net on (2026-10-28): the packaged guide
 * when it carries the net, else a subject whose own eeg_positions has it.
 *
 * The names are real: the guide list is `tit/scene/guide/manifest.json`'s `nets[].name` (8 caps),
 * and BioSemi-64-10-10.csv is a cap the Caps panel warps onto a subject from
 * `resources/ElectrodeCaps_MNI/` — on the maintainer's sub-101 it sat in `eeg_positions` while the
 * guide had none of it, so the pane drew no electrodes. The `.csv`-less spellings are the montage
 * catalog's and the mock's.
 */
import { describe, expect, it } from "vitest";
import { subjectForOffGuideNet } from "../../src/renderer/pages/simulator/types";

const GUIDE = [
  "EEG10-10_Cutini_2011.csv",
  "EEG10-10_Neuroelectrics.csv",
  "EEG10-10_UI_Jurak_2007.csv",
  "EEG10-20_Okamoto_2004.csv",
  "EEG10-20_extended_SPM12.csv",
  "GSN-HydroCel-185.csv",
  "GSN-HydroCel-256.csv",
  "easycap_BC_TMS64_X21.csv",
];
const NETS = {
  "101": ["BioSemi-64-10-10.csv", "EEG10-10_Cutini_2011.csv", "GSN-HydroCel-185.csv"],
  ernie: ["EEG10-10_Cutini_2011.csv"],
};

describe("subjectForOffGuideNet", () => {
  it("keeps the guide for a net the guide carries, however it is spelled", () => {
    expect(subjectForOffGuideNet("EEG10-10_Cutini_2011.csv", GUIDE, ["101"], NETS)).toBeNull();
    expect(subjectForOffGuideNet("EEG10-10_Cutini_2011", GUIDE, ["101"], NETS)).toBeNull();
  });

  it("draws an off-guide net on the first candidate that has it", () => {
    expect(subjectForOffGuideNet("BioSemi-64-10-10.csv", GUIDE, ["ernie", "101"], NETS)).toBe("101");
    expect(subjectForOffGuideNet("BioSemi-64-10-10", GUIDE, [undefined, null, "101"], NETS)).toBe("101");
  });

  it("falls back to the guide when no candidate has the net, or before the guide's list arrives", () => {
    expect(subjectForOffGuideNet("BioSemi-64-10-10.csv", GUIDE, ["ernie"], NETS)).toBeNull();
    expect(subjectForOffGuideNet("BioSemi-64-10-10.csv", undefined, ["101"], NETS)).toBeNull();
    expect(subjectForOffGuideNet(null, GUIDE, ["101"], NETS)).toBeNull();
  });
});

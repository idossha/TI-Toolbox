import { describe, expect, it } from "vitest";
import { buildExNodeConfig, defaultExNodeEditor, editorFromExNode, exNodeError } from "../../src/renderer/pages/pipeline/exNodeEditor";

describe("Canvas Ex/mEx shared settings adapter", () => {
  it("restores pool electrodes, nondefault currents and a MNI mask", () => {
    const editor = editorFromExNode({ kind: "ex", config: {
      leadfield_hdf: "/data/sub-101/lf.hdf5", electrodes: { _type: "PoolElectrodes", electrodes: ["F3", "F4", "P3", "P4"] },
      total_current: 3, current_step: 0.1, channel_limit: null, run_name: "custom",
      roi_name: "target", roi_names: [], roi_atlas: [{ atlas_path: "/data/mask.nii.gz", label: null, atlas_space: "mni" }], roi_coordinate_space: "mni",
    } });
    const config = buildExNodeConfig(editor, () => undefined, ["101"]);
    expect(config).toMatchObject({ subject_id: "101", run_name: "custom", leadfield_hdf: "/data/sub-101/lf.hdf5", total_current: 3, current_step: 0.1, channel_limit: null, electrodes: { _type: "PoolElectrodes", electrodes: ["F3", "F4", "P3", "P4"] }, roi_atlas: [{ atlas_path: "/data/mask.nii.gz", label: null, atlas_space: "mni" }] });
  });
  it("restores all eight mTI buckets and carrier symmetry", () => {
    const buckets = { e1_plus: ["A"], e1_minus: ["B"], e2_plus: ["C"], e2_minus: ["D"], e3_plus: ["E"], e3_minus: ["F"], e4_plus: ["G"], e4_minus: ["H"] };
    const editor = editorFromExNode({ kind: "mex", config: { electrodes: { _type: "BucketElectrodes", ...buckets }, current_mA: 1.8, symmetric_bucket: true, symmetry_pairing: "cross_pairs", roi_name: "saved-target", roi_radius: 6, roi_coordinate_space: "mni" } });
    const config = buildExNodeConfig(editor, () => undefined, ["ernie"]);
    expect(config.electrodes).toEqual({ _type: "BucketElectrodes", ...buckets });
    expect(config).toMatchObject({ current_mA: 1.8, symmetric_bucket: true, symmetry_pairing: "cross_pairs", roi_name: "saved-target", roi_radius: 6, roi_coordinate_space: "mni" });
  });
  it("refuses silently discarding independent selected targets", () => {
    const editor = defaultExNodeEditor("ex");
    editor.roi = { mode: "saved", selected: ["one", "two"], radius: 3, space: "subject", combine: false };
    expect(exNodeError(editor)).toMatch(/one node per target/);
    editor.roi.combine = true;
    expect(exNodeError(editor)).toBeNull();
    editor.kind = "mex";
    expect(exNodeError(editor)).toMatch(/one node per target/);
  });
});

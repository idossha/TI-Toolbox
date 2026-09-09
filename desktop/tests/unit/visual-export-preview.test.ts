import { describe, expect, it } from "vitest";
import {
  exportRegionKey,
  readExportMontage,
  selectedSceneRegions,
  segmentationPreviewScene,
} from "../../src/renderer/pages/panels/visual-exporter/previewModel";

describe("export preview input identity", () => {
  it("keeps hemisphere identity for atlas regions sharing one annotation index", () => {
    const catalog = [
      { id: 8, name: "insula", hemi: "lh" as const },
      { id: 8, name: "insula", hemi: "rh" as const },
    ];
    expect(selectedSceneRegions(catalog, ["rh.insula"])).toEqual([
      { id: 8, name: "insula", hemi: "rh" },
    ]);
    expect(
      selectedSceneRegions(catalog, ["lh.insula", "rh.insula"]).map(
        exportRegionKey,
      ),
    ).toEqual(["lh.insula", "rh.insula"]);
  });
  it("does not map unknown selections to unlabeled geometry", () => {
    expect(
      selectedSceneRegions(
        [{ id: 1, name: "insula", hemi: "lh" }],
        ["rh.insula", "unknown"],
      ),
    ).toEqual([]);
  });
  it("reads the net and pairs recorded by the simulation without substituting catalog presets", () => {
    expect(
      readExportMontage(
        JSON.stringify({
          eeg_net: "subject-specific.csv",
          electrode_pairs: [
            ["E7", "E2"],
            ["E9", "E3"],
          ],
        }),
      ),
    ).toEqual({
      net: "subject-specific.csv",
      pairs: [
        ["E7", "E2"],
        ["E9", "E3"],
      ],
    });
  });
  it.each([
    {},
    { eeg_net: "", electrode_pairs: [["E1", "E2"]] },
    { eeg_net: "net.csv", electrode_pairs: [] },
    { eeg_net: "net.csv", electrode_pairs: [["E1", 4]] },
    { eeg_net: "net.csv", electrode_pairs: [["E1", ""]] },
    { eeg_net: "net.csv", electrode_pairs: [["E1", "E2", "E3"]] },
  ])(
    "refuses incomplete or ambiguous recorded montage metadata: %j",
    (config) => {
      expect(() => readExportMontage(JSON.stringify(config))).toThrow();
    },
  );
});

describe("segmentation preview display", () => {
  it("draws label geometry even when custom-file resolution uses scalar defaults", () => {
    const scene = {
      datasets: [{ path: "/api/files/raw/custom-name.nii.gz" }],
      layers: [
        {
          id: "L0",
          kind: "volume",
          showIn3D: false,
          interpolation: "linear",
          labelMode: "fill",
        },
        { id: "L1", kind: "mesh", showIn3D: false },
      ],
    };
    const preview = segmentationPreviewScene(scene);
    expect(preview.layers[0]).toMatchObject({
      showIn3D: true,
      interpolation: "nearest",
      labelMode: "both",
      selectedLabels: [],
    });
    expect(preview.datasets).toBe(scene.datasets);
    expect(preview.layers[1]).toBe(scene.layers[1]);
    expect(scene.layers[0]).toMatchObject({
      showIn3D: false,
      interpolation: "linear",
    });
  });
});

it("masks only zero background without masking any positive integer atlas label", () => {
  const original = {
    layers: [
      { kind: "volume", threshold: { lo: null, hi: null, mode: "clamp" } },
    ],
  };
  const preview = segmentationPreviewScene(original);
  const threshold = preview.layers[0]?.threshold as unknown as {
    lo: number;
    hi: number | null;
    mode: string;
  };
  expect(threshold.mode).toBe("hide");
  expect(threshold.hi).toBeNull();
  expect(0 < threshold.lo).toBe(true);
  expect(1 >= threshold.lo).toBe(true);
  expect(530 >= threshold.lo).toBe(true);
  expect(original.layers[0]?.threshold.lo).toBeNull();
});

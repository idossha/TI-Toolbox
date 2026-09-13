/**
 * The `saved` mode of the ONE shared ROI picker (`pages/_shared/roi`) and the ex/mEx target
 * expansion built on it. The merge's whole claim is that three methods share one picker; these
 * are the assertions that claim rests on.
 */
import { describe, expect, it } from "vitest";
import { emptyRoi, isRoiComplete, roiToConfig, type RoiValue } from "../../src/renderer/pages/_shared/roi/types";
import { exTargets } from "../../src/renderer/pages/optimizer/exConfig";

const noAtlas = () => undefined;

describe("the shared picker's `saved` mode", () => {
  it("starts empty, with the ex-search radius and subject space", () => {
    expect(emptyRoi("saved")).toEqual({ mode: "saved", selected: [], combine: false, radius: 3.0, space: "subject" });
  });

  it("is complete once one ROI is selected", () => {
    expect(isRoiComplete(emptyRoi("saved"))).toBe(false);
    expect(isRoiComplete({ mode: "saved", selected: ["A"], combine: false, radius: 3, space: "subject" })).toBe(true);
  });

  it("is not a FlexConfig ROI shape — `roiToConfig` refuses it rather than inventing one", () => {
    const value: RoiValue = { mode: "saved", selected: ["A"], combine: false, radius: 3, space: "subject" };
    expect(roiToConfig(value, noAtlas)).toBeUndefined();
  });

  it("still round-trips the three flex modes unchanged", () => {
    const sphere: RoiValue = {
      mode: "spherical",
      spheres: [{ x: 10, y: -20, z: 15, radius: 8 }],
      space: "mni",
      volumetric: false,
      tissues: "GM",
    };
    expect(roiToConfig(sphere, noAtlas)).toEqual({
      _type: "SphericalROI",
      x: [10],
      y: [-20],
      z: [15],
      radius: [8],
      use_mni: true,
      volumetric: false,
      tissues: "GM",
    });
  });
});

describe("exTargets", () => {
  it("unions the selected ROIs into one run when combine is on", () => {
    const value: RoiValue = { mode: "saved", selected: ["A", "B"], combine: true, radius: 5, space: "mni" };
    expect(exTargets(value, noAtlas, true)).toEqual([
      { roiName: "A+B", roiNames: ["A", "B"], roiAtlas: null, radius: 5, space: "mni" },
    ]);
  });

  it("ignores combine for mEx, whose run path has no combined mode", () => {
    const value: RoiValue = { mode: "saved", selected: ["A", "B"], combine: true, radius: 3, space: "subject" };
    expect(exTargets(value, noAtlas, false).map((t) => t.roiName)).toEqual(["A", "B"]);
  });

  it("builds an atlas-only target with the atlas's resolved path, not its id", () => {
    const value: RoiValue = {
      mode: "subcortical",
      atlasSpace: "subject",
      atlas: "CIT168",
      regions: [{ id: 10, name: "L-Thal" }, { id: 11, name: "R-Thal" }],
      tissues: "GM",
    };
    const targets = exTargets(value, () => ({ path: "/atlases/CIT168.nii.gz" }), true);
    expect(targets).toHaveLength(1);
    expect(targets[0]?.roiName).toBe("CIT168_2regions");
    expect(targets[0]?.roiNames).toEqual([]);
    // CircleCI 985: resolved atlas targets also retain their coordinate frame.
    expect(targets[0]?.roiAtlas).toEqual([
      { atlas_path: "/atlases/CIT168.nii.gz", label: 10, atlas_space: "subject" },
      { atlas_path: "/atlases/CIT168.nii.gz", label: 11, atlas_space: "subject" },
    ]);
  });

  it("has no target while the atlas has not resolved — which is what disables Run", () => {
    const value: RoiValue = { mode: "subcortical", atlasSpace: "subject", atlas: "CIT168", regions: [{ id: 10, name: "x" }], tissues: "GM" };
    expect(exTargets(value, noAtlas, true)).toEqual([]);
  });

  it("has no target for a flex-only mode, so Ex cannot silently submit a sphere table", () => {
    expect(exTargets(emptyRoi("cortical"), noAtlas, true)).toEqual([]);
  });
});

describe("custom NIfTI masks", () => {
  it("requires a NIfTI path before enabling the target", () => {
    expect(isRoiComplete(emptyRoi("mask"))).toBe(false);
    expect(isRoiComplete({ mode: "mask", path: "/mnt/project/mask.csv", space: "subject", tissues: "GM" })).toBe(false);
  });
  for (const space of ["subject", "mni"] as const) {
    it(`preserves ${space} and whole-mask semantics for Flex and Ex`, () => {
      const mask: RoiValue = { mode: "mask", path: "/mnt/project/my target.nii.gz", space, tissues: "both" };
      expect(roiToConfig(mask, noAtlas)).toEqual({ _type: "SubcorticalROI", atlas_path: mask.path, label: null, tissues: "both", atlas_space: space });
      expect(exTargets(mask, noAtlas)).toEqual([{ roiName: "my target", roiNames: [], roiAtlas: [{ atlas_path: mask.path, label: null, atlas_space: space }], radius: 3, space }]);
      expect(exTargets(mask, noAtlas, false)).toEqual(exTargets(mask, noAtlas));
    });
  }
});

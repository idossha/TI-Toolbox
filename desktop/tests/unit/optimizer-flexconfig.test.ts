import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAjvResolver } from "../../src/renderer/forms/ajvResolver";
import { resetSchemaCache, type JSONSchema } from "../../src/renderer/forms/schema";
import { roiToConfig, isRoiComplete, emptyRoi, emptySphereRow, type AtlasLookup } from "../../src/renderer/pages/_shared/roi/types";
import { buildFlexConfig, defaultFlexFormState, jobKindFor, parsePctList, sweepCombinationCount } from "../../src/renderer/pages/optimizer/flexConfig";

const schema: JSONSchema = JSON.parse(readFileSync(join(__dirname, "..", "..", "..", "contracts", "generated", "config.schema.json"), "utf8"));

// `createAjvResolver(name)` fetches `/api/schema` via `loadSchema()` (forms/schema.ts) — stub
// `fetch` to serve the document already read from disk above, and reset its cache so the stub
// is actually hit.
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(schema), { status: 200, headers: { "content-type": "application/json" } })),
  );
  resetSchemaCache();
});

describe("roiToConfig", () => {
  it("is undefined for an incomplete spherical ROI", () => {
    const value = emptyRoi("spherical");
    expect(isRoiComplete(value)).toBe(false);
    expect(roiToConfig(value, () => undefined)).toBeUndefined();
  });

  it("builds a SphericalROI wire object from one or more rows (union)", () => {
    const value = emptyRoi("spherical");
    if (value.mode !== "spherical") throw new Error("unreachable");
    value.spheres = [
      { x: 1, y: 2, z: 3, radius: 5 },
      { x: 4, y: 5, z: 6, radius: 5 },
    ];
    value.space = "mni";
    const cfg = roiToConfig(value, () => undefined);
    expect(cfg).toEqual({
      _type: "SphericalROI",
      x: [1, 4],
      y: [2, 5],
      z: [3, 6],
      radius: [5, 5],
      use_mni: true,
      volumetric: false,
      tissues: "GM",
    });
  });

  it("builds an AtlasROI from cortical regions, resolving lh/rh paths from the lh path", () => {
    const value = emptyRoi("cortical");
    if (value.mode !== "cortical") throw new Error("unreachable");
    value.atlas = "DK40";
    // 1 is the real DK40 `.annot` label index for "bankssts" (contracts/generated/config.schema.json's
    // `Region.id: integer` — see desktop/tests/fixtures/atlas_regions.json).
    value.regions = [
      { id: 1, name: "bankssts", hemi: "lh" },
      { id: 1, name: "bankssts", hemi: "rh" },
    ];
    const lookup = (): AtlasLookup => ({ path: "/mnt/example/m2m_ernie/segmentation/lh.DK40.annot" });
    const cfg = roiToConfig(value, lookup);
    expect(cfg).toEqual({
      _type: "AtlasROI",
      atlas_path: ["/mnt/example/m2m_ernie/segmentation/lh.DK40.annot", "/mnt/example/m2m_ernie/segmentation/rh.DK40.annot"],
      label: [1, 1],
      hemisphere: ["lh", "rh"],
    });
  });

  it("builds a SubcorticalROI unioning multiple regions from one atlas", () => {
    const value = emptyRoi("subcortical");
    if (value.mode !== "subcortical") throw new Error("unreachable");
    value.atlas = "CIT168";
    value.atlasSpace = "mni";
    value.regions = [
      { id: 1, name: "Putamen" },
      { id: 2, name: "Caudate" },
    ];
    const cfg = roiToConfig(value, () => ({ path: "/ti-toolbox/resources/atlas/CIT168_labeling_MNI152NLin2009cAsym.nii.gz" }));
    expect(cfg).toEqual({
      _type: "SubcorticalROI",
      atlas_path: ["/ti-toolbox/resources/atlas/CIT168_labeling_MNI152NLin2009cAsym.nii.gz", "/ti-toolbox/resources/atlas/CIT168_labeling_MNI152NLin2009cAsym.nii.gz"],
      label: [1, 2],
      tissues: "GM",
      atlas_space: "mni",
    });
  });
});

describe("flex-search config building", () => {
  it("job kind follows goal + focality mode", () => {
    const form = defaultFlexFormState();
    expect(jobKindFor({ ...form, goal: "mean" })).toBe("flex");
    expect(jobKindFor({ ...form, goal: "focality_tf" })).toBe("flex");
    expect(jobKindFor({ ...form, goal: "focality", focalityMode: "manual" })).toBe("flex");
    expect(jobKindFor({ ...form, goal: "focality", focalityMode: "adaptive" })).toBe("flex_adaptive");
    expect(jobKindFor({ ...form, goal: "focality", focalityMode: "pareto" })).toBe("flex_pareto");
  });

  it("counts Pareto sweep combinations as the cartesian product of the two lists", () => {
    const form = { ...defaultFlexFormState(), paretoRoiPcts: "80,70", paretoNonRoiPcts: "20,30,40" };
    expect(parsePctList(form.paretoRoiPcts)).toEqual([80, 70]);
    expect(sweepCombinationCount(form)).toBe(6);
  });

  it("builds a well-formed FlexConfig request body that validates against contracts/generated/config.schema.json", () => {
    const form = defaultFlexFormState();
    const roi = roiToConfig(
      { mode: "spherical", spheres: [{ x: -28, y: -12, z: 58, radius: 10 }], space: "subject", volumetric: false, tissues: "GM" },
      () => undefined,
    )!;
    const config = buildFlexConfig("ernie", form, roi, undefined);
    expect(config.subject_id).toBe("ernie");
    expect(config.roi).toEqual(roi);
    // `createAjvResolver(name)` (forms/ajvResolver.ts) now compiles a named $defs entry against
    // the whole cached schema document, so cross-referencing $refs like FlexConfig's
    // `#/$defs/OptGoal`/`FieldPostproc` resolve correctly — no synthetic document needed.
    const resolver = createAjvResolver("FlexConfig");
    return resolver(config as never, undefined, { shouldUseNativeValidation: false, fields: {} } as never).then((result) => {
      expect(result.errors).toEqual({});
    });
  });

  it("carries an adaptive/pareto block for those job kinds (provisional shape — see PARITY.md)", () => {
    const form = { ...defaultFlexFormState(), goal: "focality" as const, focalityMode: "adaptive" as const, adaptiveRoiPct: 75, adaptiveNonRoiPct: 15 };
    const roi = roiToConfig(emptySphericalWithOneRow(), () => undefined)!;
    const config = buildFlexConfig("ernie", form, roi, undefined);
    expect(config.adaptive).toEqual({ non_roi_pct: 15, roi_pct: 75 });
  });
});

function emptySphericalWithOneRow() {
  const value = emptyRoi("spherical");
  if (value.mode !== "spherical") throw new Error("unreachable");
  value.spheres = [{ ...emptySphereRow(), x: 0, y: 0, z: 0 }];
  return value;
}

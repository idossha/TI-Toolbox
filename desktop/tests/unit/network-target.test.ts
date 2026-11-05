/**
 * The `network` ROI mode: what its value builds, when it is complete, and what its pane draws.
 * The wire shape is also validated here against `contracts/generated/config.schema.json`; the
 * server's own verdict on the same configs is `tests/test_desktop_config_corpus.py`.
 * Run: cd desktop && npx vitest run tests/unit/network-target.test.ts
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import Ajv2020 from "ajv/dist/2020";
import { describe, expect, it } from "vitest";
import { drawnEdges, edgeSwatch, samePair, type TractEdge } from "../../src/renderer/pages/_shared/roi/tract";
import { emptyRoi, isRoiComplete, roiToConfig, withNetworkEdit, withRoiSpace, type NetworkRoiValue } from "../../src/renderer/pages/_shared/roi/types";
import { roiForSubject } from "../../src/renderer/pages/_shared/roi/subjectChange";
import { targetPreviewRoi } from "../../src/renderer/pages/_shared/scene/targetPreviewModel";
import { exTargets, buildExConfig, defaultExFormState } from "../../src/renderer/pages/optimizer/exConfig";
import { optimizerTargetLabel, roiModesFor } from "../../src/renderer/pages/optimizer/rows";
import { decodePickId, decodePickPixel, encodePickId, pickIdToRgb, PICK_KIND_EDGE } from "../../src/renderer/scene/pickId";
import { EMPTY_SELECTION, MODE_RULES, selectionReducer } from "../../src/renderer/scene/selection";
import { categoricalColor } from "../../src/renderer/scene/palette";

const PATH = "/p/derivatives/SimNIBS/sub-S1/m2m_S1/masks/tract-net.nii.gz";
const noAtlas = () => undefined;

function complete(): NetworkRoiValue {
  return {
    ...(emptyRoi("network") as NetworkRoiValue),
    seeds: ["lh.insula"],
    pairs: [["lh.insula", "Left-Thalamus-Proper"]],
    name: "net",
    mask: { path: PATH, fingerprint: "f", nEdges: 1, nStreamlines: 300, nVoxels: 900, volumeMm3: 900 },
  };
}

const edge = (region_a: string, region_b: string, n: number, edge_id = 0): TractEdge => ({ edge_id, region_a, region_b, n, share: n / 1000 });

describe("network value", () => {
  it("is offered for flex and ex, in subject space only", () => {
    expect(roiModesFor("flex")).toContain("network");
    expect(roiModesFor("ex")).toContain("network");
    expect(withRoiSpace(complete(), "mni").space).toBe("subject");
  });

  it("is complete only with a mask", () => {
    expect(isRoiComplete(emptyRoi("network"))).toBe(false);
    expect(isRoiComplete(complete())).toBe(true);
  });

  it("builds the flex ROI as white matter in subject space", () => {
    expect(roiToConfig(complete(), noAtlas)).toEqual({ _type: "SubcorticalROI", atlas_path: PATH, label: null, tissues: "WM", atlas_space: "subject" });
    expect(roiToConfig(emptyRoi("network"), noAtlas)).toBeUndefined();
  });

  it("builds the ex target as an atlas-only mask", () => {
    expect(exTargets(complete(), noAtlas)).toEqual([
      { roiName: "tract-net", roiNames: [], roiAtlas: [{ atlas_path: PATH, label: null, atlas_space: "subject" }], radius: 3, space: "subject" },
    ]);
    expect(exTargets(emptyRoi("network"), noAtlas)).toEqual([]);
  });

  it("validates against the generated config schema", () => {
    const schema = JSON.parse(readFileSync(join(__dirname, "..", "..", "..", "contracts", "generated", "config.schema.json"), "utf8"));
    const ajv = new Ajv2020({ strict: false, allErrors: true });
    ajv.addSchema({ ...schema, $id: "config" });
    const flexRoi = ajv.compile({ $ref: "config#/$defs/SubcorticalROI" });
    expect(flexRoi(roiToConfig(complete(), noAtlas)), JSON.stringify(flexRoi.errors)).toBe(true);
    const exConfig = ajv.compile({ $ref: "config#/$defs/ExConfig" });
    const config = buildExConfig("S1", "lf.hdf5", defaultExFormState(), exTargets(complete(), noAtlas)[0]!, "run");
    expect(exConfig(config), JSON.stringify(exConfig.errors)).toBe(true);
    const tract = ajv.compile({ $ref: "config#/$defs/TractConfig" });
    const rank = { _type: "TractConfig", subject_id: "S1", stages: ["target"], target: { selection: { name: "net", kind: "edges", pairs: [["a", "b"]] } } };
    expect(tract(rank), JSON.stringify(tract.errors)).toBe(true);
    expect(tract({ ...rank, target: { selection: { name: "net", kind: "nope" } } })).toBe(false);
  });

  it("any edit drops the mask and marks it stale, which leaves the row incomplete", () => {
    for (const patch of [{ seeds: [] }, { pairs: [] }, { minCount: 2 }, { minN: 9 }, { name: "other" }]) {
      const edited = withNetworkEdit(complete(), patch);
      expect(edited.mask).toBeUndefined();
      expect(edited.stale).toBe(true);
      expect(isRoiComplete(edited)).toBe(false);
    }
    // A first edit with no mask ever made has nothing to call stale.
    expect(withNetworkEdit(emptyRoi("network") as NetworkRoiValue, { name: "a" }).stale).toBeUndefined();
  });

  it("is cleared when the row moves to another subject", () => {
    const moved = roiForSubject(complete(), "S1", "S2");
    expect(isRoiComplete(moved.roi)).toBe(false);
    expect(moved.note).toContain("sub-S1");
  });

  it("names its mask in the target chip and the preview", () => {
    expect(optimizerTargetLabel(complete())).toBe("net · 1 edge · network");
    expect(optimizerTargetLabel(emptyRoi("network"))).toBe("Choose a target…");
    expect(targetPreviewRoi(complete())).toEqual({ kind: "mask", path: PATH, space: "subject" });
    expect(targetPreviewRoi(emptyRoi("network"))).toBeNull();
  });
});

describe("drawn edges", () => {
  const edges = [edge("a", "b", 900), edge("a", "c", 500), edge("a", "d", 3)];

  it("treats a pair as unordered", () => {
    expect(samePair(["a", "b"], ["b", "a"])).toBe(true);
    expect(samePair(["a", "b"], ["a", "c"])).toBe(false);
  });

  it("keeps a selected edge past the budget and the rest by count", () => {
    const many = Array.from({ length: 70 }, (_, i) => edge("a", `r${i}`, 1000 - i));
    const drawn = drawnEdges(many, [["r69", "a"]]);
    expect(drawn).toHaveLength(64);
    expect(drawn[0]!.region_b).toBe("r69");
    expect(drawn[1]!.region_b).toBe("r0");
  });

  it("colours a row by its table position, whatever is selected", () => {
    const drawn = drawnEdges(edges, [["a", "d"]]);
    expect(drawn[0]!.region_b).toBe("d");
    expect(edgeSwatch(edges, drawn[0]!)).toEqual(categoricalColor(2));
  });
});

describe("pick kind 3", () => {
  it("round-trips an edge through the bytes a shader writes", () => {
    for (const index of [0, 1, 63, 0xfffff]) {
      const id = encodePickId("edge", index);
      expect(id >>> 20).toBe(PICK_KIND_EDGE);
      expect(decodePickId(id)).toEqual({ kind: "edge", index });
      expect(decodePickPixel(pickIdToRgb(id))).toEqual({ kind: "edge", index });
    }
    expect(PICK_KIND_EDGE).toBe(3);
  });

  it("changes no selection of the pane's own: the page's row list owns it", () => {
    const state = { markers: [], regions: [7] };
    expect(selectionReducer(state, { type: "pick", target: { kind: "edge", index: 7 } }, MODE_RULES.target)).toBe(state);
    expect(selectionReducer(EMPTY_SELECTION, { type: "pick", target: { kind: "edge", index: 1 } }, MODE_RULES.target)).toBe(EMPTY_SELECTION);
  });
});

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
import { autoNetworkName, networkSelection, pairsFromTo, presetPairs, presetTotals, removedSentence, samePairSet, strongestPairs, withChoice, type TractConnection, type TractPreset } from "../../src/renderer/pages/_shared/roi/networkChoice";
import { emptyRoi, isRoiComplete, roiToConfig, withNetworkEdit, withRoiSpace, type NetworkRoiValue } from "../../src/renderer/pages/_shared/roi/types";
import { roiForSubject } from "../../src/renderer/pages/_shared/roi/subjectChange";
import { targetPreviewRoi } from "../../src/renderer/pages/_shared/scene/targetPreviewModel";
import { exTargets, buildExConfig, defaultExFormState } from "../../src/renderer/pages/optimizer/exConfig";
import { networkPlanLine } from "../../src/renderer/pages/panels/visual-exporter/config";
import { summarizeRegions } from "../../src/renderer/pages/panels/visual-exporter/NetworkSetup";
import { groupRenders, renderLabel } from "../../src/renderer/pages/panels/visual-exporter/NetworkRenders";
import { rankingConfig, rankingEstimate } from "../../src/renderer/pages/results/NetworkRanking";
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

const preset = (over: Partial<TractPreset> = {}): TractPreset => ({
  id: "posterior_thalamocortical",
  label: "Posterior thalamocortical",
  seeds: ["Left-Thalamus-Proper", "Right-Thalamus-Proper"],
  same_side: true,
  pairs: [["Left-Thalamus-Proper", "lh.lingual"], ["Right-Thalamus-Proper", "rh.lingual"]],
  n_edges: 2,
  n_streamlines: 1407,
  opposite_pairs: [["Right-Thalamus-Proper", "lh.lingual"], ["Left-Thalamus-Proper", "rh.lingual"]],
  n_opposite: 191,
  right_thalamus_to_left_cortex: 167,
  left_thalamus_to_right_cortex: 24,
  missing: [],
  ...over,
});

describe("choosing a network", () => {
  const base = { how: "preset" as const, seeds: [] as string[], pairs: [] as [string, string][] };

  it("a preset keeps same-side edges until the opposite ones are asked for, and says what left", () => {
    expect(presetPairs(preset(), false)).toEqual(preset().pairs);
    expect(presetPairs(preset(), true)).toHaveLength(4);
    expect(presetTotals(preset(), false)).toEqual({ streamlines: 1407, edges: 2 });
    expect(presetTotals(preset(), true)).toEqual({ streamlines: 1598, edges: 4 });
    expect(removedSentence(preset())).toBe("1,407 of 1,598; 191 opposite-hemisphere removed (right thalamus to left cortex 167, left thalamus to right cortex 24)");
  });

  it("the toggle reaches the network's name, for a same-side preset only", () => {
    expect(autoNetworkName({ ...base, preset: "posterior_thalamocortical", presetSameSide: true })).toBe("posterior_thalamocortical");
    expect(autoNetworkName({ ...base, preset: "posterior_thalamocortical", presetSameSide: true, includeOpposite: true })).toBe("posterior_thalamocortical_with_opposite");
    expect(autoNetworkName({ ...base, preset: "interhemispheric_cortical", presetSameSide: false, includeOpposite: true })).toBe("interhemispheric_cortical");
  });

  it("names follow the choice and are always valid Selection names", () => {
    expect(autoNetworkName({ ...base, how: "region", seeds: ["lh.insula"] })).toBe("lh_insula");
    expect(autoNetworkName({ ...base, how: "region", seeds: ["lh.insula"], to: ["Brain-Stem"] })).toBe("lh_insula_to_Brain-Stem");
    expect(autoNetworkName({ ...base, how: "region", seeds: ["lh.insula", "rh.insula"], to: ["a", "b", "c"] })).toBe("2_regions_to_3_regions");
    expect(autoNetworkName({ ...base, how: "connection", seeds: ["a"], pairs: [["lh.x", "Brain-Stem"]] })).toBe("lh_x_Brain-Stem");
    expect(autoNetworkName({ ...base, how: "connection", seeds: ["a.b"], pairs: [["a.b", "c"], ["a.b", "d"]] })).toBe("a_b_2_edges");
    expect(autoNetworkName({ ...base, how: "strongest" })).toBe("");
    expect(autoNetworkName({ ...base, how: "strongest", metric: "ti_max_mean", topN: 5 })).toBe("top_5_by_ti_max_mean");
  });

  it("from and to take every edge joining them, either way round, above the minimum", () => {
    const edges = [
      { region_a: "a", region_b: "x", n: 9 },
      { region_a: "y", region_b: "a", n: 4 },
      { region_a: "b", region_b: "x", n: 2 },
      { region_a: "c", region_b: "d", n: 9 },
    ];
    expect(pairsFromTo(edges, ["a"], [], 1)).toEqual([["a", "x"], ["y", "a"]]);
    expect(pairsFromTo(edges, ["a"], ["y"], 1)).toEqual([["y", "a"]]);
    expect(pairsFromTo(edges, ["a", "b"], ["x"], 3)).toEqual([["a", "x"]]);
  });

  it("the top N follow the named metric, above the minimum, with a stable tie", () => {
    const row = (region_a: string, n: number, ti_max_mean: number, align_index: number): TractConnection => ({ region_a, region_b: "z", n, ti_max_mean, align_index, ti_along_mean: 0, ti_avg_mean: 0 });
    const rows = [row("a", 9, 0.1, 3), row("b", 9, 0.3, 1), row("c", 1, 0.9, 9), row("d", 9, 0.3, 2)];
    expect(strongestPairs(rows, "ti_max_mean", 2, 5)).toEqual([["b", "z"], ["d", "z"]]);
    expect(strongestPairs(rows, "align_index", 1, 5)).toEqual([["a", "z"]]);
  });

  it("a top N names no seed, so the render lights its busiest ends instead", () => {
    const value = { ...(emptyRoi("network") as NetworkRoiValue), how: "strongest" as const, name: "n", seeds: ["a", "z"], pairs: [["a", "z"]] as [string, string][] };
    expect(networkSelection(value)).toEqual({ name: "n", kind: "edges", regions: [], pairs: [["a", "z"]] });
    expect(networkSelection({ ...value, how: "region" }).regions).toEqual(["a", "z"]);
  });

  it("two pair lists are the same network whichever way round", () => {
    expect(samePairSet([["a", "b"], ["c", "d"]], [["d", "c"], ["b", "a"]])).toBe(true);
    expect(samePairSet([["a", "b"]], [["a", "b"], ["c", "d"]])).toBe(false);
  });

  it("a name stays the user's once typed", () => {
    const value = { ...(emptyRoi("network") as NetworkRoiValue), how: "preset" as const, name: "mine", nameEdited: true };
    expect(withChoice(value, { preset: "x" }, withNetworkEdit).name).toBe("mine");
    expect(withChoice({ ...value, nameEdited: false }, { preset: "x" }, withNetworkEdit).name).toBe("x");
  });
});

describe("what the column says", () => {
  it("the Plan as one line says what it queues, draws and replaces", () => {
    expect(networkPlanLine({ jobs: 1, memGb: 6, title: "Cingulate cortical network", streamlines: 4332, replaced: ["a.png", "b.png"] })).toBe("1 job · 6 GB · Cingulate cortical network · 4,332 streamlines · will overwrite 2 files");
    expect(networkPlanLine({ jobs: 2, replaced: [] })).toBe("2 jobs · replaces nothing");
  });

  it("a long region list is summarised, by the word running through it when there is one", () => {
    const cingulate = ["caudalanteriorcingulate", "isthmuscingulate", "posteriorcingulate", "rostralanteriorcingulate"].flatMap((p) => [`lh.${p}`, `rh.${p}`]);
    expect(summarizeRegions(cingulate)).toBe("8 cingulate regions");
    expect(summarizeRegions(["lh.a", "rh.b", "Brain-Stem", "lh.c"])).toBe("4 regions");
    expect(summarizeRegions(["Left-Thalamus-Proper", "Right-Thalamus-Proper"])).toBe("Left-Thalamus-Proper, Right-Thalamus-Proper");
  });

  it("renders group by network, newest network first, and read as colour and view", () => {
    const render = (network: string, colour: string, view: string) => ({ path: `/${network}/${colour}_${view}.png`, name: `${colour}_${view}.png`, kind: "image" as const, modified_at: "t", network, colour, view });
    const groups = groupRenders([render("b", "ti_max", "superior"), render("a", "direction", "lateral"), render("b", "ti_max", "posterior")]);
    expect(groups.map((g) => g.network)).toEqual(["b", "a"]);
    expect(groups[0]!.renders.map(renderLabel)).toEqual(["TI_max · posterior", "TI_max · superior"]);
    expect(renderLabel({ colour: "direction", view: "lateral" })).toBe("Fibre direction · lateral");
  });
});

describe("ranking a run", () => {
  const mask = { name: "m", pairs: [["a", "b"]], min_count: 2 } as Parameters<typeof rankingConfig>[3];

  it("All sends no limit, and a top N its number", () => {
    expect(rankingConfig("S", "run", "lf.hdf5", mask, null).target).toMatchObject({ top_n: null, ex_run: "run", min_count: 2 });
    expect(rankingConfig("S", "run", "lf.hdf5", mask, 20).target.top_n).toBe(20);
  });

  it("estimates from the measured rate: 14,535 montages took about 29 minutes", () => {
    expect(rankingEstimate(14_535)).toBe("about 29 min");
    expect(rankingEstimate(210)).toBe("under a minute");
  });
});

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

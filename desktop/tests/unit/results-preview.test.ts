/**
 * The Results preview parsers (program U14), fed by the maintainer's own runs.
 *
 * `tests/fixtures/preview/` holds copies of four real files from Dataset 000 — a simulation's
 * `documentation/config.json`, a flex run's `flex_meta.json` / `summary.txt` /
 * `electrode_positions.json`, and an ex run's `run_config.json` + the head of its
 * `final_output.csv`. Reading them here is what makes the pane's rows numbers rather than a claim:
 * every expectation below is a value that exists in one of those files.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  EX_RANK_COLUMN,
  exRunConfigPath,
  shortMontage,
  netFromLeadfield,
  parseExRunConfig,
  rankExRows,
  type ExTable,
} from "../../src/renderer/pages/results/preview/ex";
import {
  flexManifestSummary,
  flexPositionsPath,
  flexRoiLabel,
  flexSummaryPath,
  parseFlexPositions,
  parseFlexSummaryText,
} from "../../src/renderer/pages/results/preview/flex";
import {
  electrodeGeometry,
  electrodePairs,
  mappingOptions,
  parseSimulationConfig,
  simulationConfigPath,
  trimNumber,
} from "../../src/renderer/pages/results/preview/simulation";

const fixture = (name: string): string => readFileSync(resolve(__dirname, "../fixtures/preview", name), "utf8");

/** `label -> value` for the rows a parser produced, so an expectation reads like the pane. */
const asMap = (rows: { label: string; value: string }[]): Record<string, string> =>
  Object.fromEntries(rows.map((r) => [r.label, r.value]));

/** The CSV fixture, parsed the way the mock server and `tit.catalog` both hand it to the page.
 * The real file is CRLF-terminated (SimNIBS writes it on the container's stdlib csv writer), which
 * is exactly why this normalises first — a `\r` left on the last column turned `Composite_Index`
 * into a column name nothing could look up. */
function exTable(): ExTable {
  const [head, ...body] = fixture("ex_final_output.csv").replace(/\r\n/g, "\n").trim().split("\n");
  const cell = (s: string): string | number => (s !== "" && !Number.isNaN(Number(s)) ? Number(s) : s);
  return { columns: head!.split(","), rows: body.map((line) => line.split(",").map(cell)) };
}

describe("simulation config.json — sub-ernie/Simulations/Thalamus", () => {
  const summary = parseSimulationConfig(fixture("simulation_config.json"))!;
  const rows = asMap(summary.rows);

  it("reads the mode, the net and the pairs the run actually used", () => {
    expect(summary.mode).toBe("TI");
    expect(summary.eegNet).toBe("EEG10-10_Cutini_2011");
    // Two stimulation channels, four electrodes: F7/P7 and F8/P8.
    expect(summary.pairs).toEqual(["F7 → P7", "F8 → P8"]);
  });

  it("states the physics in the units the file uses", () => {
    expect(rows.Intensity).toBe("1 / 1 mA");
    expect(rows.Conductivity).toBe("scalar");
    expect(rows.Electrodes).toBe("ellipse · 8 × 8 mm · gel 4 mm · rubber 2 mm");
    expect(rows["Mapped to"]).toBe("surface, fsaverage");
    expect(rows.Tissues).toBe("all");
    // The file's `created_at` is 2026-07-06T18:48:57; the row is locale-formatted, so assert the
    // parts that do not move rather than a string that depends on the runner's locale.
    expect(rows.Created).toMatch(/2026/);
  });

  it("emits no row for a field the file does not carry", () => {
    const trimmed = parseSimulationConfig(JSON.stringify({ simulation_mode: "mTI" }))!;
    expect(asMap(trimmed.rows)).toEqual({ Mode: "MTI" });
    expect(trimmed.pairs).toEqual([]);
  });

  it("returns undefined for a file that is not JSON, so the pane can fall back", () => {
    expect(parseSimulationConfig("<html>502 Bad Gateway</html>")).toBeUndefined();
    expect(parseSimulationConfig("[1,2,3]")).toBeUndefined();
  });

  it("names an XYZ montage rather than inventing electrode pairs", () => {
    const xyz = parseSimulationConfig(JSON.stringify({ is_xyz_montage: true, electrode_pairs: [] }))!;
    expect(asMap(xyz.rows).Montage).toBe("XYZ coordinates");
  });

  it("small helpers", () => {
    expect(trimNumber(8.0)).toBe("8");
    expect(trimNumber(1.5)).toBe("1.5");
    expect(electrodePairs([["F7", "P7"], ["bad"], "no"])).toEqual(["F7 → P7"]);
    expect(electrodeGeometry({})).toBeUndefined();
    expect(mappingOptions({ map_to_surf: false, map_to_vol: false })).toBe("none");
    expect(mappingOptions({})).toBeUndefined();
    expect(simulationConfigPath("/p/Sim/")).toBe("/p/Sim/documentation/config.json");
  });
});

describe("flex run — sub-ernie/flex-search/VAL_lhipp_flex_focality", () => {
  const manifest = JSON.parse(fixture("flex_meta.json")) as unknown;
  const rows = asMap(flexManifestSummary(manifest).rows);

  it("reads the goal, the ROI and the optimiser's own best value from flex_meta.json", () => {
    expect(rows.Goal).toBe("focality · max_TI");
    // A subcortical ROI is an atlas file plus a label index — left hippocampus is 17 in the
    // SimNIBS labelling, which is what this run targeted.
    expect(rows.ROI).toBe("subcortical · labeling.nii.gz label 17 · GM");
    expect(rows["Non-ROI"]).toBe("everything else");
    expect(rows.Current).toBe("2 mA");
    expect(rows.Channels).toBe("2 · 2 multistart");
    expect(rows.Thresholds).toBe("0.1,0.2");
    expect(rows["Min. distance"]).toBe("5 mm");
    expect(rows["Best value"]).toBe("-91.5567");
    expect(rows.Runs).toBe("2");
    expect(flexManifestSummary(manifest).bestValue).toBeCloseTo(-91.5566569, 6);
  });

  it("survives a manifest that is missing, empty or the wrong type", () => {
    expect(flexManifestSummary(undefined).rows).toEqual([]);
    expect(flexManifestSummary([]).rows).toEqual([]);
    expect(flexManifestSummary({}).rows).toEqual([]);
  });

  it("labels a spherical ROI by its centre and radius", () => {
    expect(flexRoiLabel({ type: "spherical", x: -12.4, y: -18.2, z: 7.9, radius: 5 })).toBe(
      "spherical · (-12.4, -18.2, 7.9) r 5 mm",
    );
  });

  it("lifts exactly four numbers out of SimNIBS' 90-line summary.txt", () => {
    const rows = asMap(parseFlexSummaryText(fixture("flex_summary.txt")));
    expect(rows).toEqual({
      Optimizer: "differential_evolution",
      "FEM evaluations": "710",
      "Function evaluations": "2288",
      // 1057.48… seconds of wall time, rounded — the pane is not a stopwatch.
      Duration: "1057 s",
    });
    // Nothing from the optimiser's settings dict or its 8-element bound vectors leaks in.
    expect(parseFlexSummaryText(fixture("flex_summary.txt"))).toHaveLength(4);
  });

  it("returns no rows for a run written before summary.txt existed", () => {
    expect(parseFlexSummaryText("")).toEqual([]);
  });

  it("pairs each optimized position with its channel and array index", () => {
    const electrodes = parseFlexPositions(fixture("electrode_positions.json"));
    expect(electrodes).toHaveLength(4);
    expect(electrodes.map((e) => [e.channel, e.array])).toEqual([
      [0, 0],
      [0, 1],
      [1, 0],
      [1, 1],
    ]);
    expect(electrodes[0]!.x).toBeCloseTo(-1.1062872, 5);
    expect(electrodes[0]!.z).toBeCloseTo(8.4871378, 5);
  });

  it("drops a malformed position rather than rendering a row of NaN", () => {
    expect(parseFlexPositions(JSON.stringify({ optimized_positions: [[1, 2], [1, 2, 3]] }))).toHaveLength(1);
    expect(parseFlexPositions("not json")).toEqual([]);
  });

  it("paths", () => {
    expect(flexSummaryPath("/p/run/")).toBe("/p/run/summary.txt");
    expect(flexPositionsPath("/p/run")).toBe("/p/run/electrode_positions.json");
  });
});

describe("ex run — sub-ernie/ex-search/docs_ex_symmetric", () => {
  const summary = parseExRunConfig(fixture("ex_run_config.json"))!;
  const rows = asMap(summary.rows);

  it("reads the search's own configuration, not its file paths", () => {
    expect(rows.ROI).toBe("L_Insula_MNI.csv · r 5 mm");
    expect(rows["EEG net"]).toBe("EEG10-10_UI_Jurak_2007");
    expect(rows.Electrodes).toBe("bucket · symmetric (within pairs)");
    expect(rows.Montages).toBe("343");
    expect(rows.Current).toBe("2 mA · step 0.25 mA");
    // `channel_limit_mA` is null in this run, so there is no row for it.
    expect(rows["Channel limit"]).toBeUndefined();
  });

  it("names the four electrode buckets the search enumerated", () => {
    expect(summary.buckets.map((b) => b.label)).toEqual(["Channel 1 +", "Channel 1 −", "Channel 2 +", "Channel 2 −"]);
    expect(summary.buckets[0]!.electrodes).toEqual(["F7", "FT7", "T7", "F5", "FC5", "AF7", "F3"]);
  });

  it("derives the net from a leadfield path in either spelling", () => {
    expect(netFromLeadfield("/p/ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5")).toBe("EEG10-10_UI_Jurak_2007");
    expect(netFromLeadfield("/p/GSN-HydroCel-185_leadfield.hdf5")).toBe("GSN-HydroCel-185");
    expect(netFromLeadfield(undefined)).toBeUndefined();
  });

  it("returns undefined for a run_config that is not JSON", () => {
    expect(parseExRunConfig("")).toBeUndefined();
  });
});

describe("rankExRows — the top of final_output.csv", () => {
  const table = exTable();

  it("takes the ten best rows by composite index, best first", () => {
    const ranked = rankExRows(table);
    expect(ranked.rows).toHaveLength(10);
    const rank = table.columns.indexOf(EX_RANK_COLUMN);
    const best = Math.max(...table.rows.map((r) => r[rank] as number));
    // The projection drops Composite_Index itself, so the check is against the source table: the
    // first ranked row must be the row that carries the maximum.
    const bestMontage = shortMontage(String(table.rows.find((r) => r[rank] === best)![0]));
    expect(ranked.rows[0]![0]).toBe(bestMontage);
    const focality = ranked.columns.indexOf("Focality");
    expect(typeof ranked.rows[0]![focality]).toBe("number");
  });

  it("projects onto the columns the pane shows, in that order", () => {
    expect(rankExRows(table).columns).toEqual([
      "Montage",
      "Current_Ch1_mA",
      "Current_Ch2_mA",
      "TImax_ROI",
      "TImean_ROI",
      "Focality",
    ]);
  });

  it("keeps an mEx run's own column names", () => {
    const mex: ExTable = {
      columns: ["Montage", "Current_Ch1_mA", "mTImax_ROI", "Focality", "Composite_Index"],
      rows: [["a", 1, 0.4, 1.7, 0.45], ["b", 1, 0.3, 1.7, 0.39]],
    };
    expect(rankExRows(mex).columns).toEqual(["Montage", "Current_Ch1_mA", "mTImax_ROI", "Focality"]);
    expect(rankExRows(mex).rows[0]![0]).toBe("a");
  });

  it("keeps the file's own order when there is no rank column, and survives an empty table", () => {
    const noRank: ExTable = { columns: ["Montage"], rows: [["z"], ["a"]] };
    expect(rankExRows(noRank).rows).toEqual([["z"], ["a"]]);
    expect(rankExRows(undefined)).toEqual({ columns: [], rows: [] });
    expect(rankExRows({ columns: [], rows: [] })).toEqual({ columns: [], rows: [] });
  });

  it("shows an unrecognised CSV layout rather than an empty table", () => {
    const odd: ExTable = { columns: ["Thing", "Value"], rows: [["a", 1]] };
    expect(rankExRows(odd).columns).toEqual(["Thing", "Value"]);
  });

  it("drops the current suffix the adjacent columns already carry", () => {
    expect(shortMontage("F7_P7 <> F3_PO7_I1-1.0mA_I2-1.0mA")).toBe("F7_P7 <> F3_PO7");
    expect(shortMontage("E24_E124 & E67_E77_I1-1.0mA_I2-0.8mA_I3-1.0mA_I4-1.0mA")).toBe("E24_E124 & E67_E77");
    expect(shortMontage("F7_P7 <> F3_PO7"), "a name with no suffix is untouched").toBe("F7_P7 <> F3_PO7");
    // The ranked table applies it, and only to the Montage column.
    expect(rankExRows(table).rows[0]![0]).not.toContain("mA");
  });

  it("paths", () => {
    expect(exRunConfigPath("/p/run/")).toBe("/p/run/run_config.json");
  });
});

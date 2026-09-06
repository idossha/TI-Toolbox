import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAjvResolver } from "../../src/renderer/forms/ajvResolver";
import { resetSchemaCache, type JSONSchema } from "../../src/renderer/forms/schema";
import { buildSimulationConfig, type GlobalParams } from "../../src/renderer/pages/simulator/buildConfig";
import {
  currentsCount,
  defaultCurrentsFor,
  inferMontageKind,
  polarityLabel,
  type SelectedRow,
} from "../../src/renderer/pages/simulator/types";
import {
  currentValues,
  formatPairs,
  montageOptionValue,
  parseMontageOptionValue,
} from "../../src/renderer/pages/simulator/MontageManager";
import { eligibleSubjectsFor, seedWithShellSubject } from "../../src/renderer/pages/simulator/index";

// contracts/schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(__dirname, "..", "..", "..", "contracts", "schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as JSONSchema;

// `createAjvResolver(name)` (forms/ajvResolver.ts) fetches `/api/schema` via `loadSchema()` and
// compiles the named `$defs` entry against the whole cached document, so `SimulationConfig`'s
// nested `$ref`s (e.g. `montages` -> `#/$defs/Montage`) resolve correctly — the resolver's
// original bug (compiling one `$defs` entry in isolation, "can't resolve reference
// #/$defs/<Nested> from id #") is fixed, so this test goes through the shared resolver directly
// like every other page's tests do.
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(schemaDoc), { status: 200, headers: { "content-type": "application/json" } })),
  );
  resetSchemaCache();
});

async function validate(defName: string, values: Record<string, unknown>): Promise<{ valid: boolean; errors: unknown }> {
  const resolver = createAjvResolver<Record<string, unknown>>(defName);
  const result = await resolver(values, undefined, { shouldUseNativeValidation: false } as never);
  return { valid: Object.keys(result.errors).length === 0, errors: result.errors };
}

const baseParams: GlobalParams = {
  conductivity: "scalar",
  electrodeShape: "ellipse",
  dimensions: [8, 8],
  gelThickness: 4,
  outputFields: ["TI_max"],
  customConductivities: {},
};

describe("Simulator page configs validate against contracts/schema.json", () => {
  it("a montage-source (net mode, uni-polar) row builds a valid SimulationConfig", async () => {
    const row: SelectedRow = {
      id: "montage:GSN-HydroCel-185:uni_polar:F3_F4:ernie",
      subjectId: "ernie",
      source: "montage",
      kind: "uni_polar",
      eegNet: "GSN-HydroCel-185",
      name: "F3_F4",
      pairs: [["E24", "E124"]],
      currents: "1.0,1.0",
    };
    const config = buildSimulationConfig(row, baseParams);
    expect(await validate("SimulationConfig", config)).toMatchObject({ valid: true, errors: {} });
  });

  it("a montage-source (multi-polar / mTI) row builds a valid SimulationConfig", async () => {
    const row: SelectedRow = {
      id: "montage:GSN-HydroCel-185:multi_polar:mTI_F3F4_P3P4:ernie",
      subjectId: "ernie",
      source: "montage",
      kind: "multi_polar",
      eegNet: "GSN-HydroCel-185",
      name: "mTI_F3F4_P3P4",
      pairs: [
        ["E24", "E124"],
        ["E67", "E77"],
      ],
      currents: "1.0,1.0,1.0,1.0",
    };
    const config = buildSimulationConfig(row, { ...baseParams, outputFields: ["TI_max", "hf_peak"] });
    expect(await validate("SimulationConfig", config)).toMatchObject({ valid: true, errors: {} });
  });

  it("a flex-search-source row (mapped labels) builds a valid SimulationConfig", async () => {
    const row: SelectedRow = {
      id: "flex:ernie:flex_Thalamus_20260810_101500",
      subjectId: "ernie",
      source: "flex",
      eegNet: "GSN-HydroCel-185",
      name: "flex_Thalamus_20260810_101500",
      pairs: [
        ["E37", "E87"],
        ["E12", "E102"],
      ],
      currents: "1.0,1.0,1.0,1.0",
    };
    const config = buildSimulationConfig(row, baseParams);
    expect(await validate("SimulationConfig", config)).toMatchObject({ valid: true, errors: {} });
  });

  it("a free-hand-source row (xyz pairs) builds a valid SimulationConfig", async () => {
    const row: SelectedRow = {
      id: "freehand:ernie:custom_4electrode",
      subjectId: "ernie",
      source: "freehand",
      name: "custom_4electrode",
      xyzPairs: [
        [
          [-68.1, -12.3, 22.5],
          [-55.4, 24.7, -8.1],
        ],
      ],
      currents: "1.0,1.0",
    };
    const config = buildSimulationConfig(row, baseParams);
    expect(await validate("SimulationConfig", config)).toMatchObject({ valid: true, errors: {} });
  });

  it("a single intensity value broadcasts to both electrodes of a pair", () => {
    const row: SelectedRow = {
      id: "montage:GSN-HydroCel-185:uni_polar:F3_F4:ernie",
      subjectId: "ernie",
      source: "montage",
      kind: "uni_polar",
      eegNet: "GSN-HydroCel-185",
      name: "F3_F4",
      pairs: [["E24", "E124"]],
      currents: "2.0",
    };
    const config = buildSimulationConfig(row, baseParams);
    expect(config.intensities).toEqual([2, 2]);
  });

  it("custom tissue conductivity overrides are forwarded under tissue_conductivities", () => {
    const row: SelectedRow = {
      id: "montage:GSN-HydroCel-185:uni_polar:F3_F4:ernie",
      subjectId: "ernie",
      source: "montage",
      kind: "uni_polar",
      eegNet: "GSN-HydroCel-185",
      name: "F3_F4",
      pairs: [["E24", "E124"]],
      currents: "1.0,1.0",
    };
    const config = buildSimulationConfig(row, { ...baseParams, customConductivities: { 2: 0.3 } });
    expect(config.tissue_conductivities).toEqual({ 2: 0.3 });
  });
});

// U16: Simulator's own page-owned Subjects table (`useSubject().batch` lost its only writer when
// U11 removed the context bar's switcher) — a multi-subject run must be reachable from this page
// alone.
describe("Simulator's page-owned subject selection (U16)", () => {
  it("seedWithShellSubject prepends the shell's primary subject when it is not already ticked", () => {
    expect(seedWithShellSubject([], "ernie")).toEqual(["ernie"]);
    expect(seedWithShellSubject(["101"], "ernie")).toEqual(["ernie", "101"]);
  });

  it("seedWithShellSubject never duplicates an already-ticked subject or fights an unticked one", () => {
    expect(seedWithShellSubject(["ernie", "101"], "ernie")).toEqual(["ernie", "101"]);
    // The primary was ticked, then the user unticked it in the table by hand — a later render with
    // the same shell subject (`shellSubject !== lastShellSubject` guards re-seeding on every
    // render) must not re-add it out from under the user.
    expect(seedWithShellSubject([], null)).toEqual([]);
  });

  it("eligibleSubjectsFor keeps only ticked subjects with a head model — a subject without an m2m cannot be simulated", () => {
    expect(eligibleSubjectsFor(["ernie", "101"], ["ernie"])).toEqual(["ernie"]);
    expect(eligibleSubjectsFor(["101"], ["ernie"])).toEqual([]);
  });

  it("eligibleSubjectsFor does not filter when the project has no m2m subjects at all (nothing to compare against)", () => {
    expect(eligibleSubjectsFor(["ernie", "101"], [])).toEqual(["ernie", "101"]);
  });

  it("two ticked subjects both stay eligible when both have a head model — the two-subject plan case", () => {
    expect(eligibleSubjectsFor(["ernie", "101"], ["ernie", "101", "MNI152"])).toEqual(["ernie", "101"]);
  });
});


// The montage table's own derivations: the net and the montage are columns of the table, and
// everything else in the row — the polarity chip, the pairs cell, how many current fields there
// are — follows from the montage rather than from a control the user has to set.
describe("montage table derivations", () => {
  it("infers a new montage's polarity from its pair count: 2 pairs is TI, more is mTI", () => {
    expect(inferMontageKind(2)).toBe("uni_polar");
    expect(inferMontageKind(4)).toBe("multi_polar");
    expect(inferMontageKind(6)).toBe("multi_polar");
    // Degenerate counts still resolve (the editor refuses to save them separately).
    expect(inferMontageKind(1)).toBe("uni_polar");
    expect(inferMontageKind(3)).toBe("multi_polar");
  });

  it("labels the polarity as the chip does", () => {
    expect(polarityLabel("uni_polar")).toBe("TI");
    expect(polarityLabel("multi_polar")).toBe("mTI");
  });

  it("takes 2 currents for a uni-polar montage and one per pair for a multi-polar one", () => {
    expect(currentsCount("uni_polar", 2)).toBe(2);
    expect(currentsCount("multi_polar", 4)).toBe(4);
    expect(defaultCurrentsFor("uni_polar", 2)).toBe("1.0,1.0");
    expect(defaultCurrentsFor("multi_polar", 4)).toBe("1.0,1.0,1.0,1.0");
  });

  it("normalises a row's currents to the count its polarity requires", () => {
    expect(currentValues("1.0,2.0", 2)).toEqual([1, 2]);
    expect(currentValues("1.0,2.0", 4)).toEqual([1, 2, 1, 1]);
    expect(currentValues("1,2,3,4", 2)).toEqual([1, 2]);
    expect(currentValues("", 2)).toEqual([1, 1]);
  });

  it("renders the pairs cell read-only, in the maintainer's notation", () => {
    expect(formatPairs([["E1", "E2"], ["E3", "E4"]])).toBe("E1\u2013E2 \u00b7 E3\u2013E4");
  });

  it("round-trips a montage option value, so one name can exist in both buckets of a net", () => {
    expect(montageOptionValue("multi_polar", "mTI:odd")).toBe("multi_polar:mTI:odd");
    expect(parseMontageOptionValue("multi_polar:mTI:odd")).toEqual({ kind: "multi_polar", name: "mTI:odd" });
    expect(parseMontageOptionValue(montageOptionValue("uni_polar", "F3_F4"))).toEqual({ kind: "uni_polar", name: "F3_F4" });
  });
});

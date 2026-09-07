/**
 * The 3D Visual Exporter builds four different config shapes for one job kind, and every one of
 * them has to validate against the dataclass the runner will rebuild it into. Same shape of test
 * as `nilearn-visuals-defaults.test.ts`, four times over, plus the byte-identity assertions that
 * are the whole point of the migration: the fields 2.5.0's `_run` hardcoded and never showed.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import {
  buildMontageConfig,
  buildRegionConfigs,
  buildSubcorticalConfig,
  buildVectorConfig,
  outputHint,
  parseLabels,
} from "../../src/renderer/pages/panels/visual-exporter/config";

const schemaPath = join(__dirname, "..", "..", "..", "contracts", "schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as { $schema: string; $defs: Record<string, unknown> };

const ajv = new Ajv2020({ allErrors: true, strict: false });
function validate(defName: string, values: unknown): { valid: boolean; errors: unknown } {
  const validateFn = ajv.compile({ $schema: schemaDoc.$schema, $defs: schemaDoc.$defs, $ref: `#/$defs/${defName}` });
  const valid = validateFn(values);
  return { valid, errors: validateFn.errors ?? [] };
}

describe("cortical regions mode", () => {
  const forms = { subjectId: "ernie", simulationName: "Thalamus", atlas: "DK40", fieldName: "TI_max", regions: ["lh.insula", "rh.insula"] };

  it("submits two jobs — STL then PLY — exactly as the Qt extension did", () => {
    const configs = buildRegionConfigs(forms);
    expect(configs.map((c) => c.format)).toEqual(["stl", "ply"]);
    for (const config of configs) expect(validate("RegionConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  it("keeps the fields the Qt widget hardcoded and never showed", () => {
    const [stl] = buildRegionConfigs(forms);
    // `keep_meshes=True` was passed by `_run` for both formats; dropping it would silently stop
    // writing the intermediate .msh files 2.5.0 left beside every export.
    expect(stl).toMatchObject({ keep_meshes: true, skip_regions: false, regions: ["lh.insula", "rh.insula"] });
  });

  it("with no regions chosen, skip_regions is true (whole grey matter only)", () => {
    const [stl] = buildRegionConfigs({ ...forms, regions: [] });
    expect(stl).toMatchObject({ skip_regions: true, regions: [] });
    expect(validate("RegionConfig", stl)).toMatchObject({ valid: true, errors: [] });
  });
});

describe("field vectors mode", () => {
  const form = {
    subjectId: "ernie",
    simulationName: "Thalamus",
    exportCh1Ch2: true,
    exportSum: false,
    exportTiNormal: true,
    count: 10000,
    allNodes: false,
    seed: 42,
    lengthScale: 1,
    vectorWidth: 1,
    anchor: "tail" as const,
    color: "magscale" as const,
    bluePercentile: 50,
    greenPercentile: 80,
    redPercentile: 95,
  };

  it("is a valid VectorConfig, with the 1.0 scale/length Qt always sent", () => {
    const config = buildVectorConfig(form);
    expect(config).toMatchObject({ vector_scale: 1, vector_length: 1 });
    expect(validate("VectorConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  it("carries the magscale percentiles through unchanged", () => {
    expect(buildVectorConfig(form)).toMatchObject({ blue_percentile: 50, green_percentile: 80, red_percentile: 95 });
  });
});

describe("montage visualizer mode", () => {
  it("negates the checkbox — 'only montage electrodes' is show_full_net: false", () => {
    const on = buildMontageConfig({ subjectId: "ernie", simulationName: "Thalamus", montageOnly: true, electrodeDiameterMm: 10, electrodeHeightMm: 6 });
    const off = buildMontageConfig({ subjectId: "ernie", simulationName: "Thalamus", montageOnly: false, electrodeDiameterMm: 10, electrodeHeightMm: 6 });
    expect(on.show_full_net).toBe(false);
    expect(off.show_full_net).toBe(true);
    expect(validate("MontageConfig", on)).toMatchObject({ valid: true, errors: [] });
  });
});

describe("sub-cortical mode", () => {
  const form = { subjectId: "ernie", simulationName: "Thalamus", niftiPath: "", labels: [10, 49], cleanComponents: true, fieldName: "TI_max" };

  it("parses the comma-separated label list Qt's line edit took — the fallback when the label browser cannot answer", () => {
    expect(parseLabels("10, 49")).toEqual([10, 49]);
    expect(parseLabels("")).toEqual([]);
    expect(() => parseLabels("10, thalamus")).toThrow(/Invalid label format/);
  });

  it("copies the chosen label ids rather than aliasing the caller's array", () => {
    const labels = [10, 49];
    const config = buildSubcorticalConfig({ ...form, labels });
    labels.push(53);
    expect(config.labels).toEqual([10, 49]);
  });

  it("is a valid SubcorticalConfig, and stays valid with no simulation", () => {
    expect(validate("SubcorticalConfig", buildSubcorticalConfig(form))).toMatchObject({ valid: true, errors: [] });
    expect(validate("SubcorticalConfig", buildSubcorticalConfig({ ...form, simulationName: "" }))).toMatchObject({ valid: true, errors: [] });
  });
});

describe("outputHint", () => {
  it("names the directory each mode actually writes into", () => {
    expect(outputHint("regions", "ernie", "Thalamus")).toBe("visual_exports/sub-ernie/Thalamus/cortical_stls");
    expect(outputHint("montage", "ernie", "Thalamus")).toBe("visual_exports/sub-ernie/montage_publication");
    expect(outputHint("subcortical", "ernie", "")).toBe("visual_exports/sub-ernie/sub-cortical");
  });
});

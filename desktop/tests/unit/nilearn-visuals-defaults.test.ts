import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import { buildNilearnConfig } from "../../src/renderer/pages/panels/nilearn-visuals/config";

// contracts/generated/config.schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(__dirname, "..", "..", "..", "contracts", "generated", "config.schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as { $schema: string; $defs: Record<string, unknown> };

const ajv = new Ajv2020({ allErrors: true, strict: false });
function validate(defName: string, values: Record<string, unknown>): { valid: boolean; errors: unknown } {
  const validateFn = ajv.compile({ $schema: schemaDoc.$schema, $defs: schemaDoc.$defs, $ref: `#/$defs/${defName}` });
  const valid = validateFn(values);
  return { valid, errors: validateFn.errors ?? [] };
}

describe("Nilearn visuals panel config validates against contracts/generated/config.schema.json", () => {
  it("a default single-pair config is a valid NilearnConfig", () => {
    const config = buildNilearnConfig({
      pairs: [{ subjectId: "ernie", simulationName: "Thalamus" }],
      subdirName: "thalamus_montage_v1",
      usePercentiles: false,
      minCutoff: 0.3,
      maxCutoff: 5,
      atlasName: "harvard_oxford_sub",
      selectedRegion: "__all__",
    });
    // Regression guard: this config used to be built with a `pairs` field —
    // `NilearnConfig.subject_simulation_pairs` is the real field name (ra_13 finding #10).
    expect(config).toHaveProperty("subject_simulation_pairs", [{ subject_id: "ernie", simulation_name: "Thalamus" }]);
    expect(config).not.toHaveProperty("pairs");
    expect(validate("NilearnConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  it("a multi-pair, percentile-cutoff config is a valid NilearnConfig", () => {
    const config = buildNilearnConfig({
      pairs: [
        { subjectId: "ernie", simulationName: "Thalamus" },
        { subjectId: "101", simulationName: "Thalamus" },
      ],
      subdirName: "group_avg",
      usePercentiles: true,
      minCutoff: 10,
      maxCutoff: 99.9,
      atlasName: "aal",
      selectedRegion: "__all__",
    });
    expect(validate("NilearnConfig", config)).toMatchObject({ valid: true, errors: [] });
  });
});

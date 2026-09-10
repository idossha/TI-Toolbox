import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import { buildNiftiAverageConfig } from "../../src/renderer/pages/panels/nifti-group-average/config";

// contracts/generated/config.schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(__dirname, "..", "..", "..", "contracts", "generated", "config.schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as { $schema: string; $defs: Record<string, unknown> };

const ajv = new Ajv2020({ allErrors: true, strict: false });
function validate(defName: string, values: Record<string, unknown>): { valid: boolean; errors: unknown } {
  const validateFn = ajv.compile({ $schema: schemaDoc.$schema, $defs: schemaDoc.$defs, $ref: `#/$defs/${defName}` });
  const valid = validateFn(values);
  return { valid, errors: validateFn.errors ?? [] };
}

describe("NIfTI group averaging panel config validates against contracts/generated/config.schema.json", () => {
  it("a default 2-subject, 2-group config is a valid NiftiAverageConfig", () => {
    const config = buildNiftiAverageConfig({
      outputName: "hippocampus_group_comparison",
      rows: [
        { subjectId: "ernie", simulationName: "Thalamus", group: "Group1" },
        { subjectId: "101", simulationName: "Thalamus", group: "Group2" },
      ],
      space: "mni",
      niftiFilePattern: "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
      diffPairs: [],
    });
    // Regression guard: this config used to be built with an `analysis_name` field —
    // `NiftiAverageConfig.output_name` is the real required field name (ra_13 finding #10).
    expect(config).toHaveProperty("output_name", "hippocampus_group_comparison");
    expect(config).not.toHaveProperty("analysis_name");
    expect(validate("NiftiAverageConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  it("a subject-space config with explicit diff pairs is a valid NiftiAverageConfig", () => {
    const config = buildNiftiAverageConfig({
      outputName: "responder_diff",
      rows: [
        { subjectId: "ernie", simulationName: "Thalamus", group: "Group1" },
        { subjectId: "101", simulationName: "Thalamus", group: "Group2" },
        { subjectId: "102", simulationName: "Thalamus", group: "Group3" },
      ],
      space: "subject",
      niftiFilePattern: "",
      diffPairs: ["Group1-Group2", "Group1-Group3"],
    });
    expect(validate("NiftiAverageConfig", config)).toMatchObject({ valid: true, errors: [] });
  });
});

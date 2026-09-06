import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import { buildForwardConfig, buildFsavgConfig } from "../../src/renderer/pages/panels/source/config";

// contracts/schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(__dirname, "..", "..", "..", "contracts", "schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as { $schema: string; $defs: Record<string, unknown> };

// Same whole-document compile as tests/unit/simulator-defaults.test.ts, for the same reason
// (SourceConfig's `forward`/`fsavg_map` are nested $refs to sibling $defs).
const ajv = new Ajv2020({ allErrors: true, strict: false });
function validate(defName: string, values: Record<string, unknown>): { valid: boolean; errors: unknown } {
  const validateFn = ajv.compile({ $schema: schemaDoc.$schema, $defs: schemaDoc.$defs, $ref: `#/$defs/${defName}` });
  const valid = validateFn(values);
  return { valid, errors: validateFn.errors ?? [] };
}

describe("Source panel configs validate against contracts/schema.json", () => {
  it("a default forward-solution config is a valid SourceConfig", () => {
    const config = buildForwardConfig({ subjectIds: ["ernie"], eegNet: "GSN-HydroCel-185", fsaverageSpacing: 5, cpus: 1, overwrite: false });
    expect(validate("SourceConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  it("a multi-subject forward-solution config is a valid SourceConfig", () => {
    const config = buildForwardConfig({ subjectIds: ["ernie", "101"], eegNet: "GSN-HydroCel-185", fsaverageSpacing: 6, cpus: 4, overwrite: true });
    expect(validate("SourceConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  it("a default fsaverage-mapping config is a valid SourceConfig", () => {
    const config = buildFsavgConfig({
      pairs: [{ subject_id: "ernie", simulation: "Thalamus" }],
      fields: ["TI_max", "TI_normal"],
      fsaverageSpacing: 5,
      workers: 1,
      overwrite: false,
    });
    expect(validate("SourceConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  it("a multi-pair, safety-field fsaverage-mapping config is a valid SourceConfig", () => {
    const config = buildFsavgConfig({
      pairs: [
        { subject_id: "ernie", simulation: "Thalamus" },
        { subject_id: "101", simulation: "docs_example" },
      ],
      fields: ["TI_max", "TI_normal", "hf_peak", "hf_sar"],
      fsaverageSpacing: 7,
      workers: 2,
      overwrite: true,
    });
    expect(validate("SourceConfig", config)).toMatchObject({ valid: true, errors: [] });
  });
});

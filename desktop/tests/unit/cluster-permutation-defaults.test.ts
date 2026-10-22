import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import { buildCorrelationConfig, buildGroupComparisonConfig, type SharedStatsFields } from "../../src/renderer/pages/panels/cluster-permutation/config";

// contracts/generated/config.schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(__dirname, "..", "..", "..", "contracts", "generated", "config.schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as { $schema: string; $defs: Record<string, unknown> };

const ajv = new Ajv2020({ allErrors: true, strict: false });
function validate(defName: string, values: Record<string, unknown>): { valid: boolean; errors: unknown } {
  const validateFn = ajv.compile({ $schema: schemaDoc.$schema, $defs: schemaDoc.$defs, $ref: `#/$defs/${defName}` });
  const valid = validateFn(values);
  return { valid, errors: validateFn.errors ?? [] };
}

const defaultShared: SharedStatsFields = {
  analysisName: "thalamus_group_comparison",
  clusterThreshold: 0.05,
  clusterStat: "mass",
  nPermutations: 1000,
  alpha: 0.05,
  nJobs: -1,
  tissueType: "grey",
  niftiPattern: "",
  space: "mni",
  fsaverageField: "TI_max",
  fsaverageSpacing: 5,
  atlasFiles: [],
};

// The schema has no cross-field rules, so the examples also keep the config classes' own:
// a correlation needs 3 subjects and a paired test equal groups (tit/stats/config.py; the page
// gate is `cluster-permutation-gates.test.tsx`). Two-subject correlations used to be called valid.
describe("Cluster Permutation panel configs validate against contracts/generated/config.schema.json", () => {
  it("a default classification config is a valid GroupComparisonConfig", () => {
    const config = buildGroupComparisonConfig(
      defaultShared,
      [
        { subjectId: "ernie", simulationName: "Thalamus", response: 1 },
        { subjectId: "101", simulationName: "Thalamus", response: 0 },
      ],
      { testType: "unpaired", alternative: "two-sided", group1Name: "Responders", group2Name: "Non-Responders", valueMetric: "Current Intensity" },
    );
    expect(validate("GroupComparisonConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  it("a fsaverage-space classification config with atlas overlap files is valid", () => {
    const config = buildGroupComparisonConfig(
      { ...defaultShared, space: "fsaverage", atlasFiles: ["HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz"] },
      [
        { subjectId: "ernie", simulationName: "Thalamus", response: 1 },
        { subjectId: "101", simulationName: "Thalamus", response: 0 },
        { subjectId: "MNI152", simulationName: "docs_example", response: 1 },
        { subjectId: "LA", simulationName: "docs_example", response: 0 },
      ],
      { testType: "paired", alternative: "greater", group1Name: "High responders", group2Name: "Low responders", valueMetric: "TI max" },
    );
    expect(validate("GroupComparisonConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  it("a default correlation config is a valid CorrelationConfig", () => {
    const config = buildCorrelationConfig(
      defaultShared,
      [
        { subjectId: "ernie", simulationName: "Thalamus", effectSize: 2.3, weight: 1 },
        { subjectId: "101", simulationName: "Thalamus", effectSize: -1.1, weight: 1 },
        { subjectId: "MNI152", simulationName: "Thalamus", effectSize: 0.6, weight: 1 },
      ],
      { correlationType: "pearson", useWeights: true, effectMetric: "Effect Size", fieldMetric: "Electric Field Magnitude" },
    );
    expect(validate("CorrelationConfig", config)).toMatchObject({ valid: true, errors: [] });
  });

  // The one `stats` job kind runs either class; the server and the runner tell them apart by
  // `_type`. Without it a Correlation job ran as a group comparison and failed on "response".
  it("each config names its own class, and the schema requires it", () => {
    const correlation = buildCorrelationConfig(
      defaultShared,
      [
        { subjectId: "ernie", simulationName: "Thalamus", effectSize: 2.3, weight: 1 },
        { subjectId: "101", simulationName: "Thalamus", effectSize: -1.1, weight: 1 },
        { subjectId: "MNI152", simulationName: "Thalamus", effectSize: 0.6, weight: 1 },
      ],
      { correlationType: "pearson", useWeights: true, effectMetric: "Effect Size", fieldMetric: "Electric Field Magnitude" },
    );
    expect(correlation._type).toBe("CorrelationConfig");
    const comparison = buildGroupComparisonConfig(
      defaultShared,
      [
        { subjectId: "ernie", simulationName: "Thalamus", response: 1 },
        { subjectId: "101", simulationName: "Thalamus", response: 0 },
      ],
      { testType: "unpaired", alternative: "two-sided", group1Name: "Responders", group2Name: "Non-Responders", valueMetric: "Current Intensity" },
    );
    expect(comparison._type).toBe("GroupComparisonConfig");
    expect(validate("CorrelationConfig", { ...correlation, _type: undefined }).valid).toBe(false);
  });

  it("a spearman correlation config with a custom NIfTI pattern is valid", () => {
    const config = buildCorrelationConfig(
      { ...defaultShared, niftiPattern: "custom_{simulation_name}.nii.gz", tissueType: "all" },
      [
        { subjectId: "ernie", simulationName: "Thalamus", effectSize: 0.5, weight: 0.8 },
        { subjectId: "101", simulationName: "Thalamus", effectSize: 1.2, weight: 1.2 },
        { subjectId: "MNI152", simulationName: "Thalamus", effectSize: 0.9, weight: 1 },
      ],
      { correlationType: "spearman", useWeights: false, effectMetric: "Mood score", fieldMetric: "TI max" },
    );
    expect(validate("CorrelationConfig", config)).toMatchObject({ valid: true, errors: [] });
  });
});

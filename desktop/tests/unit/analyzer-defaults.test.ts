import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import type { RoiValue } from "../../src/renderer/pages/_shared/roi/types";
import {
  AUTO_FIELD,
  buildConfig,
} from "../../src/renderer/pages/analyzer/buildConfig";
import { EMPTY_SPHERE } from "../../src/renderer/pages/analyzer/SphereRows";
import { effectiveSubjectIdsFor, seedWithShellSubject } from "../../src/renderer/pages/analyzer/AnalyzerPage";

// contracts/schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(
  __dirname,
  "..",
  "..",
  "..",
  "contracts",
  "schema.json",
);
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as {
  $schema: string;
  $defs: Record<string, unknown>;
};

/**
 * Validates against one `$defs` entry using the whole schema document as compile context, so
 * internal `$ref`s to sibling `$defs` resolve. Same approach as
 * `simulator-defaults.test.ts` (not `forms/ajvResolver.ts`'s single-entry compile, which fails on
 * any config with a nested `$ref` — reported there, not re-reported here).
 */
const ajv = new Ajv2020({ allErrors: true, strict: false });
function validate(
  defName: string,
  values: Record<string, unknown>,
): { valid: boolean; errors: unknown } {
  const validateFn = ajv.compile({
    $schema: schemaDoc.$schema,
    $defs: schemaDoc.$defs,
    $ref: `#/$defs/${defName}`,
  });
  const valid = validateFn(values);
  return { valid, errors: validateFn.errors ?? [] };
}

const corticalRoi: RoiValue = {
  mode: "cortical",
  atlas: "DK40",
  regions: [{ id: 29, name: "insula", hemi: "lh" }],
};
const subcorticalRoi: RoiValue = {
  mode: "subcortical",
  atlasSpace: "mni",
  atlas: "CIT168",
  regions: [{ id: 1, name: "CIT168_Pu_Putamen" }],
  tissues: "GM",
};

describe("Analyzer page configs validate against contracts/schema.json", () => {
  it("a single-mode spherical config is a valid AnalyzerConfig", () => {
    const config = buildConfig({
      mode: "single",
      subjectId: "ernie",
      subjectIds: [],
      simulation: "Thalamus",
      space: "mesh",
      tissueType: "GM",
      field: AUTO_FIELD,
      analysisType: "spherical",
      coordinateSpace: "subject",
      sphere: { x: -12.4, y: -18.2, z: 7.9, radius: 5 },
      roiValue: { mode: "cortical", atlas: undefined, regions: [] },
    });
    expect(validate("AnalyzerConfig", config)).toMatchObject({
      valid: true,
      errors: [],
    });
  });

  it("an explicit field selection round-trips (not just the Auto/null default)", () => {
    const config = buildConfig({
      mode: "single",
      subjectId: "ernie",
      subjectIds: [],
      simulation: "Thalamus",
      space: "voxel",
      tissueType: "both",
      field: "hf_peak",
      analysisType: "spherical",
      coordinateSpace: "mni",
      sphere: { x: -42, y: 32, z: 28, radius: 8 },
      roiValue: { mode: "cortical", atlas: undefined, regions: [] },
    });
    expect(config).toMatchObject({
      field: "hf_peak",
      tissue_type: "both",
      coordinate_space: "mni",
    });
    expect(validate("AnalyzerConfig", config)).toMatchObject({
      valid: true,
      errors: [],
    });
  });

  it("a cortical config carries atlas + a single region as a plain string", () => {
    const config = buildConfig({
      mode: "single",
      subjectId: "ernie",
      subjectIds: [],
      simulation: "L_Insula",
      space: "mesh",
      tissueType: "GM",
      field: AUTO_FIELD,
      analysisType: "cortical",
      coordinateSpace: "subject",
      sphere: EMPTY_SPHERE,
      roiValue: corticalRoi,
    });
    expect(config).toMatchObject({
      atlas: "DK40",
      region: "insula",
      center: null,
      radius: null,
    });
    expect(validate("AnalyzerConfig", config)).toMatchObject({
      valid: true,
      errors: [],
    });
  });

  it("multiple selected regions combine into a region list", () => {
    const multi: RoiValue = {
      mode: "cortical",
      atlas: "DK40",
      regions: [
        { id: 29, name: "insula", hemi: "lh" },
        { id: 29, name: "insula", hemi: "rh" },
      ],
    };
    const config = buildConfig({
      mode: "single",
      subjectId: "ernie",
      subjectIds: [],
      simulation: "L_Insula",
      space: "mesh",
      tissueType: "GM",
      field: AUTO_FIELD,
      analysisType: "cortical",
      coordinateSpace: "subject",
      sphere: EMPTY_SPHERE,
      roiValue: multi,
    });
    expect(config.region).toEqual(["insula", "insula"]);
    expect(validate("AnalyzerConfig", config)).toMatchObject({
      valid: true,
      errors: [],
    });
  });

  it("a subcortical config is a valid AnalyzerConfig (backend-support gap tracked separately)", () => {
    const config = buildConfig({
      mode: "single",
      subjectId: "ernie",
      subjectIds: [],
      simulation: "Thalamus",
      space: "voxel",
      tissueType: "GM",
      field: AUTO_FIELD,
      analysisType: "subcortical",
      coordinateSpace: "subject",
      sphere: EMPTY_SPHERE,
      roiValue: subcorticalRoi,
    });
    expect(config).toMatchObject({
      analysis_type: "subcortical",
      atlas: "CIT168",
      region: "CIT168_Pu_Putamen",
    });
    expect(validate("AnalyzerConfig", config)).toMatchObject({
      valid: true,
      errors: [],
    });
  });

  it("group mode sets subject_ids and clears subject_id", () => {
    const config = buildConfig({
      mode: "group",
      subjectId: null,
      subjectIds: ["ernie", "101"],
      simulation: "Thalamus",
      space: "mesh",
      tissueType: "GM",
      field: AUTO_FIELD,
      analysisType: "spherical",
      coordinateSpace: "subject",
      sphere: { x: -11.8, y: -17.6, z: 8.3, radius: 5 },
      roiValue: { mode: "cortical", atlas: undefined, regions: [] },
    });
    expect(config).toMatchObject({
      mode: "group",
      subject_id: null,
      subject_ids: ["ernie", "101"],
    });
    expect(validate("AnalyzerConfig", config)).toMatchObject({
      valid: true,
      errors: [],
    });
  });
});

// U16: Analyzer's own page-owned Subjects table (`useSubject().batch` lost its only writer when
// U11 removed the context bar's switcher) — a multi-subject Group-mode run must be reachable from
// this page alone.
describe("Analyzer's page-owned subject selection (U16)", () => {
  it("seedWithShellSubject prepends the shell's primary subject when it is not already ticked", () => {
    expect(seedWithShellSubject([], "ernie")).toEqual(["ernie"]);
    expect(seedWithShellSubject(["101"], "ernie")).toEqual(["ernie", "101"]);
  });

  it("seedWithShellSubject never duplicates an already-ticked subject or re-adds an unticked one", () => {
    expect(seedWithShellSubject(["ernie", "101"], "ernie")).toEqual(["ernie", "101"]);
    expect(seedWithShellSubject([], null)).toEqual([]);
  });

  it("Subject mode analyzes only the first ticked subject, however many are ticked", () => {
    expect(effectiveSubjectIdsFor("single", [])).toEqual([]);
    expect(effectiveSubjectIdsFor("single", ["ernie"])).toEqual(["ernie"]);
    expect(effectiveSubjectIdsFor("single", ["ernie", "101"])).toEqual(["ernie"]);
  });

  it("Group mode analyzes every ticked subject — the two-subject, two-job plan case", () => {
    expect(effectiveSubjectIdsFor("group", [])).toEqual([]);
    expect(effectiveSubjectIdsFor("group", ["ernie", "101"])).toEqual(["ernie", "101"]);
  });
});

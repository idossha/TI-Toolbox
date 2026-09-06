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
import { blockedReasonFor, cohortSubjects, groupMismatchReason, rowTargets } from "../../src/renderer/pages/analyzer/AnalyzerPage";
import {
  analyzerJobsSummary,
  analyzerTargetLabel,
  emptyAnalyzerRow,
  isPlannableAnalyzerRow,
  isRunnableAnalyzerRow,
  type AnalyzerRow,
} from "../../src/renderer/pages/analyzer/JobRows";

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

/*
 * 2026-09-06 jobs rework: the page-level Subjects table and the Scope segment are gone — a ROW is
 * a (subject, simulation, space, field) job, which is 2.5.0's Subject × Simulation pair table
 * (maintainer: "we need a list of jobs in a table that allows users flexibility in what they input
 * to the job").
 */
describe("the Analyzer's job rows", () => {
  const row = (subjectId: string, simulation: string, over: Partial<AnalyzerRow> = {}): AnalyzerRow => ({
    ...emptyAnalyzerRow({ subjectId, simulation }),
    ...over,
  });

  it("a row is a job once it names a subject and a simulation", () => {
    expect(isRunnableAnalyzerRow(emptyAnalyzerRow())).toBe(false);
    expect(isRunnableAnalyzerRow(row("ernie", ""))).toBe(false);
    expect(isRunnableAnalyzerRow(row("", "Thalamus"))).toBe(false);
    expect(isRunnableAnalyzerRow(row("ernie", "Thalamus"))).toBe(true);
  });

  it("the cohort is the distinct subjects the complete rows name, in row order", () => {
    expect(cohortSubjects([row("ernie", "Thalamus"), row("101", "Thalamus"), row("ernie", "Thalamus")])).toEqual([
      "ernie",
      "101",
    ]);
    // A half-filled row is never part of the cohort.
    expect(cohortSubjects([row("ernie", "Thalamus"), row("101", "")])).toEqual(["ernie"]);
  });

  it("group mode refuses rows that disagree about the one thing a cohort job runs", () => {
    expect(groupMismatchReason([row("ernie", "Thalamus"), row("101", "Thalamus")])).toBeNull();
    expect(groupMismatchReason([row("ernie", "Thalamus"), row("101", "Motor")])).toMatch(/one simulation/);
    expect(
      groupMismatchReason([row("ernie", "Thalamus"), row("101", "Thalamus", { space: "voxel" })]),
    ).toMatch(/one space/);
    expect(
      groupMismatchReason([row("ernie", "Thalamus"), row("101", "Thalamus", { field: "TI_max" })]),
    ).toMatch(/one field/);
  });

  it("the Jobs summary counts jobs per row, or one cohort job in group mode", () => {
    const rows = [row("ernie", "Thalamus"), row("101", "Thalamus")];
    expect(analyzerJobsSummary([], false)).toBe("no rows yet");
    expect(analyzerJobsSummary(rows, false)).toBe("2 analysis jobs · 2 subjects");
    expect(analyzerJobsSummary(rows, true)).toBe("one group analysis over 2 subjects");
    expect(analyzerJobsSummary([...rows, emptyAnalyzerRow()], false)).toBe("2 analysis jobs · 2 subjects · 1 incomplete");
  });

  it("the disabled Run states what is missing, and the empty table comes first", () => {
    expect(blockedReasonFor({ subjectsBlocked: null, rowCount: 0, targetReady: false })).toBe(
      "Add a row with a subject and a simulation.",
    );
    expect(blockedReasonFor({ subjectsBlocked: "101 cannot run — no simulations.", rowCount: 1, targetReady: true })).toMatch(
      /^101 cannot run/,
    );
    expect(blockedReasonFor({ subjectsBlocked: null, rowCount: 2, groupMismatch: "mixed", targetReady: true })).toBe("mixed");
    expect(blockedReasonFor({ subjectsBlocked: null, rowCount: 1, targetReady: false })).toBe(
      "Complete the target before running.",
    );
    expect(blockedReasonFor({ subjectsBlocked: null, rowCount: 1, targetReady: true })).toBeNull();
  });
});

/*
 * 2026-09-06, maintainer's second jobs pass: *"we can modify our analysis input per job"*. The
 * TARGET section is gone from the page — a ROW owns its ROI, states it in words in its Target
 * cell, and edits it in the shared `RoiPicker` scoped to that row.
 */
describe("a row's own target", () => {
  const sphereRoi = (over: Partial<Extract<RoiValue, { mode: "spherical" }>> = {}): RoiValue => ({
    mode: "spherical",
    spheres: [{ x: 10, y: 10, z: 10, radius: 30 }],
    space: "mni",
    volumetric: false,
    tissues: "GM",
    ...over,
  });
  const rowWith = (roi: RoiValue, over: Partial<AnalyzerRow> = {}): AnalyzerRow =>
    emptyAnalyzerRow({ subjectId: "ernie", simulation: "Thalamus", roi, ...over });

  it("the Target cell states the target in words, and says so when there is none", () => {
    expect(analyzerTargetLabel(emptyAnalyzerRow().roi)).toBe("Choose a target…");
    expect(analyzerTargetLabel(sphereRoi())).toBe("Sphere 10,10,10 r30 MNI");
    expect(analyzerTargetLabel(sphereRoi({ space: "subject" }))).toBe("Sphere 10,10,10 r30 subject");
    expect(analyzerTargetLabel(corticalRoi)).toBe("Cortical · DK40 · lh.insula");
    expect(analyzerTargetLabel(subcorticalRoi)).toBe("Subcortical · CIT168_Pu_Putamen");
  });

  it("more than one region or sphere is stated as a count, so the cell is one line", () => {
    expect(
      analyzerTargetLabel({
        mode: "cortical",
        atlas: "DK40",
        regions: [
          { id: 29, name: "insula", hemi: "lh" },
          { id: 29, name: "insula", hemi: "rh" },
        ],
      }),
    ).toBe("Cortical · DK40 · lh.insula +1");
    expect(
      analyzerTargetLabel(sphereRoi({ spheres: [{ x: 10, y: 10, z: 10, radius: 30 }, { x: 1, y: 2, z: 3, radius: 5 }] })),
    ).toBe("Sphere 10,10,10 r30 MNI +1");
  });

  it("a row is plannable only once its own target is complete", () => {
    expect(isRunnableAnalyzerRow(rowWith(emptyAnalyzerRow().roi))).toBe(true);
    expect(isPlannableAnalyzerRow(rowWith(emptyAnalyzerRow().roi))).toBe(false);
    expect(isPlannableAnalyzerRow(rowWith(sphereRoi()))).toBe(true);
  });

  it("one row is one config, except where 2.5.0 already fanned out", () => {
    // One sphere, one region set: one config.
    expect(rowTargets(rowWith(sphereRoi()))).toHaveLength(1);
    expect(rowTargets(rowWith(corticalRoi))).toHaveLength(1);
    // N sphere rows are N separate analyses — `center`/`radius` are a single point.
    expect(rowTargets(rowWith(sphereRoi({ spheres: [{ x: 1, y: 1, z: 1, radius: 5 }, { x: 2, y: 2, z: 2, radius: 5 }] })))).toHaveLength(2);
    // "Combine regions into one ROI" off: one analysis per region.
    const multi: RoiValue = {
      mode: "cortical",
      atlas: "DK40",
      regions: [
        { id: 29, name: "insula", hemi: "lh" },
        { id: 29, name: "insula", hemi: "rh" },
      ],
    };
    expect(rowTargets(rowWith(multi, { combine: true }))).toHaveLength(1);
    expect(rowTargets(rowWith(multi, { combine: false }))).toHaveLength(2);
  });

  it("a cohort needs the rows to agree about the target too", () => {
    const a = rowWith(sphereRoi());
    const b = rowWith(sphereRoi(), { subjectId: "101" });
    expect(groupMismatchReason([a, b])).toBeNull();
    expect(groupMismatchReason([a, rowWith(corticalRoi, { subjectId: "101" })])).toMatch(/one target/);
  });
});

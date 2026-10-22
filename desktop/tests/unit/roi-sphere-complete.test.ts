/**
 * A spherical target is complete only with a positive, finite radius and three finite coordinates
 * (2026-10-22).
 *
 * Before: `isRoiComplete` checked only that each number was defined, so a sphere of radius 0 or -5
 * (NumberInput's min is an HTML hint, not a gate) made the Analyzer and Optimizer rows runnable and
 * the job ended in an empty ROI. The expected verdicts come from the spec (a sphere has a radius
 * > 0) and from `AnalyzerConfig.__post_init__`, which now refuses the same values server-side
 * (tests/test_analyzer_sphere_validation.py). Boundary values just inside the rule stay complete.
 */
import { describe, expect, it } from "vitest";
import { emptyRoi, isRoiComplete, roiToConfig, type RoiValue, type SphereRow } from "../../src/renderer/pages/_shared/roi/types";
import { emptyAnalyzerRow, isPlannableAnalyzerRow, analyzerTargetLabel } from "../../src/renderer/pages/analyzer/JobRows";

function sphere(row: Partial<SphereRow>, extra: Partial<SphereRow>[] = []): RoiValue {
  const base: SphereRow = { x: 0, y: 0, z: 0, radius: 10 };
  return {
    mode: "spherical",
    spheres: [{ ...base, ...row }, ...extra.map((e) => ({ ...base, ...e }))],
    space: "subject",
    volumetric: false,
    tissues: "GM",
  };
}

describe("isRoiComplete for spheres", () => {
  it.each([
    ["radius 0", { radius: 0 }],
    ["radius -5", { radius: -5 }],
    ["radius NaN", { radius: Number.NaN }],
    ["radius Infinity", { radius: Number.POSITIVE_INFINITY }],
    ["radius unset", { radius: undefined }],
    ["x NaN", { x: Number.NaN }],
    ["y Infinity", { y: Number.POSITIVE_INFINITY }],
    ["z unset", { z: undefined }],
  ])("is incomplete with %s", (_label, row) => {
    expect(isRoiComplete(sphere(row))).toBe(false);
    expect(roiToConfig(sphere(row), () => undefined)).toBeUndefined();
  });

  it.each([
    ["radius just above 0", { radius: 1e-6 }],
    ["radius 0.1 (the input's own min)", { radius: 0.1 }],
    ["a centre at the origin", { x: 0, y: 0, z: 0, radius: 5 }],
    ["negative coordinates", { x: -35, y: -20, z: -5, radius: 8 }],
  ])("is complete with %s", (_label, row) => {
    expect(isRoiComplete(sphere(row))).toBe(true);
  });

  it("is incomplete when any one sphere of several is bad", () => {
    expect(isRoiComplete(sphere({ radius: 5 }, [{ radius: 5 }, { radius: 0 }]))).toBe(false);
    expect(isRoiComplete(sphere({ radius: 5 }, [{ radius: 5 }]))).toBe(true);
  });

  it("keeps the default empty sphere incomplete until a centre is typed", () => {
    expect(isRoiComplete(emptyRoi("spherical"))).toBe(false);
  });
});

describe("an Analyzer row with a radius-0 sphere", () => {
  it("cannot be planned and says it needs a target", () => {
    const row = emptyAnalyzerRow({ subjectId: "101", simulation: "L_Insula", roi: sphere({ radius: 0 }) });
    expect(isPlannableAnalyzerRow(row)).toBe(false);
    expect(analyzerTargetLabel(row.roi)).toBe("Choose a target…");
    const fixed = { ...row, roi: sphere({ radius: 3 }) };
    expect(isPlannableAnalyzerRow(fixed)).toBe(true);
  });
});

/**
 * Moving a row to another subject never carries the old subject's own-frame target (p19,
 * 2026-10-22).
 *
 * The rule is the coordinate-frame definition, not this code: subject-space millimetres and a
 * subject-space mask are points in ONE subject's scanner frame (`analyzer.py::_analyze_mask_file`
 * samples a mask by world coordinates; a flex/ex sphere is placed at those millimetres), so in
 * another head they measure or optimise different anatomy — silently. A saved ROI is a CSV under
 * the old subject's `rois/`. MNI spheres and masks are one frame for everyone (each run warps them
 * to its own head), and an atlas target is an atlas id each job resolves against its own subject
 * (U16). Before p19 `optimizer/JobRows.tsx` and `analyzer/JobRows.tsx` patched only `subjectId`.
 *
 * The table is 5 modes x 2 spaces; the expected verdict per cell is the rule above, typed by hand.
 * The Analyzer's cohort rule (a subject-space sphere cannot be one target for several heads) is
 * here too. The page gesture (Duplicate, change subject, Run blocked) is
 * `tests/e2e/subject-change-target.spec.ts`.
 * Reproduce: `cd desktop && npx vitest run tests/unit/roi-subject-change.test.ts`.
 */
import { describe, expect, it } from "vitest";
import { roiForSubject } from "../../src/renderer/pages/_shared/roi/subjectChange";
import { isRoiComplete, type RoiMode, type RoiSpace, type RoiValue } from "../../src/renderer/pages/_shared/roi";
import { groupMismatchReason } from "../../src/renderer/pages/analyzer/AnalyzerPage";
import { emptyAnalyzerRow } from "../../src/renderer/pages/analyzer/JobRows";

/** A complete target of each mode in each space. */
function complete(mode: RoiMode, space: RoiSpace): RoiValue {
  switch (mode) {
    case "spherical":
      return { mode, space, volumetric: false, tissues: "GM", spheres: [{ x: -42, y: -20, z: 55, radius: 10 }] };
    case "mask":
      return { mode, space, tissues: "GM", path: space === "mni" ? "/proj/masks/mni/hippocampus.nii.gz" : "/proj/masks/sub-ernie/imported/lesion.nii.gz" };
    case "saved":
      return { mode, space, selected: ["L-Insula", "R-Insula"], combine: false, radius: 3 };
    case "cortical":
      return { mode, space, atlas: "DK40", regions: [{ id: 35, name: "insula", hemi: "lh" }] };
    case "subcortical":
      return { mode, space, atlas: space === "mni" ? "CIT168" : "labeling.nii.gz", regions: [{ id: 17, name: "Left-Hippocampus" }], tissues: "GM" };
  }
}

/** The verdict per (mode, space): kept as it was, or cleared to an incomplete target. */
const TABLE: { mode: RoiMode; space: RoiSpace; kept: boolean; mentions?: RegExp }[] = [
  { mode: "spherical", space: "subject", kept: false, mentions: /sphere.*sub-ernie.*sub-101/ },
  { mode: "spherical", space: "mni", kept: true },
  { mode: "mask", space: "subject", kept: false, mentions: /mask.*sub-ernie.*sub-101/ },
  { mode: "mask", space: "mni", kept: true },
  // A saved ROI is a CSV of the old subject in either space.
  { mode: "saved", space: "subject", kept: false, mentions: /L-Insula, R-Insula.*sub-ernie/ },
  { mode: "saved", space: "mni", kept: false, mentions: /L-Insula, R-Insula.*sub-ernie/ },
  { mode: "cortical", space: "subject", kept: true },
  { mode: "cortical", space: "mni", kept: true },
  { mode: "subcortical", space: "subject", kept: true },
  { mode: "subcortical", space: "mni", kept: true },
];

describe("roiForSubject", () => {
  it.each(TABLE)("$mode in $space space: kept=$kept", ({ mode, space, kept, mentions }) => {
    const before = complete(mode, space);
    const { roi, note } = roiForSubject(before, "ernie", "101");
    if (kept) {
      expect(roi).toEqual(before);
      expect(note).toBeNull();
      return;
    }
    // Cleared, not deleted: the same mode and space, and incomplete — so the row cannot run
    // until a target for the NEW subject is chosen.
    expect(roi.mode).toBe(mode);
    expect(roi.space).toBe(space);
    expect(isRoiComplete(roi)).toBe(false);
    expect(note).toMatch(mentions!);
  });

  it("keeps everything else about a cleared target (sphere radius, mask tissue, saved radius)", () => {
    const sphere = roiForSubject(complete("spherical", "subject"), "ernie", "101").roi;
    expect(sphere).toMatchObject({ volumetric: false, tissues: "GM" });
    const mask = roiForSubject({ ...complete("mask", "subject"), tissues: "WM" } as RoiValue, "ernie", "101").roi;
    expect(mask).toEqual({ mode: "mask", space: "subject", tissues: "WM", path: "" });
    const saved = roiForSubject(complete("saved", "subject"), "ernie", "101").roi;
    expect(saved).toEqual({ mode: "saved", space: "subject", selected: [], combine: false, radius: 3 });
  });

  it("changes nothing when the subject does not change, or when the row had none yet", () => {
    for (const mode of ["spherical", "mask", "saved"] as const) {
      const value = complete(mode, "subject");
      expect(roiForSubject(value, "ernie", "ernie")).toEqual({ roi: value, note: null });
      expect(roiForSubject(value, "", "101")).toEqual({ roi: value, note: null });
    }
  });

  it("says nothing when there was nothing to clear", () => {
    const blank: RoiValue = { mode: "spherical", space: "subject", volumetric: false, tissues: "GM", spheres: [{ x: undefined, y: undefined, z: undefined, radius: 10 }] };
    expect(roiForSubject(blank, "ernie", "101").note).toBeNull();
    expect(roiForSubject({ mode: "mask", space: "subject", tissues: "GM", path: "" }, "ernie", "101").note).toBeNull();
  });
});

describe("Analyzer cohort: one target for several heads", () => {
  const cohort = (roi: RoiValue) => [
    emptyAnalyzerRow({ subjectId: "ernie", simulation: "Thalamus", roi }),
    emptyAnalyzerRow({ subjectId: "101", simulation: "Thalamus", roi }),
  ];

  it("refuses a subject-space sphere, as it refuses a subject-space mask", () => {
    expect(groupMismatchReason(cohort(complete("spherical", "subject")))).toMatch(/MNI/);
    expect(groupMismatchReason(cohort(complete("mask", "subject")))).toMatch(/MNI-space mask/);
  });

  it("accepts an MNI sphere and an atlas region", () => {
    expect(groupMismatchReason(cohort(complete("spherical", "mni")))).toBeNull();
    expect(groupMismatchReason(cohort(complete("cortical", "subject")))).toBeNull();
  });
});

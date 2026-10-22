/**
 * NIfTI group averaging: the builder sends each group label as the panel reads it (p23).
 *
 * The panel's eligibility check trims a label, but `buildNiftiAverageConfig` sent it untrimmed,
 * so rows typed "Group1" and "Group1 " reached the runner as two groups (two averages, a wrong
 * difference). The server now trims too (`NiftiAverageConfig.__post_init__`,
 * `tests/test_nifti_average_groups.py`); this pins the desktop half. Expected labels are the
 * typed ones with their edge whitespace removed, inner spaces and hyphens kept. Dated 2026-10-22.
 */
import { expect, it } from "vitest";
import { buildNiftiAverageConfig } from "../../src/renderer/pages/panels/nifti-group-average/config";

it("sends trimmed group labels, keeping inner spaces and hyphens", () => {
  const config = buildNiftiAverageConfig({
    outputName: "avg",
    rows: [
      { subjectId: "001", simulationName: "M1", group: "Group1" },
      { subjectId: "002", simulationName: "M1", group: "Group1 " },
      { subjectId: "003", simulationName: "M1", group: "  post op" },
      { subjectId: "004", simulationName: "M1", group: "\tpre-op\n" },
    ],
    space: "mni",
    niftiFilePattern: "",
    diffPairs: [],
  });
  expect(config.subjects.map((s) => s.group)).toEqual(["Group1", "Group1", "post op", "pre-op"]);
  expect(new Set(config.subjects.map((s) => s.group)).size).toBe(3);
  // The rows themselves are untouched: the subject and simulation of each row go out as typed.
  expect(config.subjects.map((s) => [s.subject_id, s.simulation_name])).toEqual([
    ["001", "M1"],
    ["002", "M1"],
    ["003", "M1"],
    ["004", "M1"],
  ]);
});

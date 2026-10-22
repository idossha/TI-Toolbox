/**
 * NIfTI group averages appear under Results › Group (2026-10-22, p11).
 *
 * Before: `GET /api/catalog/group` had no `nifti_average` key and `groupOutputsFor` no row for it,
 * so a finished NIfTI Group Averaging job showed nothing, although the job-completion refresh
 * (`queriesAffectedBy("nifti_average")`) re-read the group catalog. The server now lists each run
 * with the files it wrote (`tests/test_group_catalog_writers.py` runs the real runner); this pins
 * the desktop half.
 *
 * Expected values: the catalog row below, shaped like the server's response for a run named
 * `avg1` with two groups (the runner's own file names: `average_<group>.nii.gz`,
 * `difference_<a>_minus_<b>.nii.gz`, `config.json`).
 *
 * Run: cd desktop && npx vitest run tests/unit/results-group-nifti-average.test.ts
 */
import { describe, expect, it } from "vitest";
import type { components } from "../../src/renderer/api/schema";
import { queriesAffectedBy } from "../../src/renderer/app/jobs/invalidation";
import { GROUP_SUBJECT, groupOutputsFor, outputsStatusValue } from "../../src/renderer/pages/results/outputsTree";

type Group = components["schemas"]["GroupCatalog"];

const DIR = "/p/derivatives/ti-toolbox/nifti_average/avg1";
const ARTIFACTS = [
  { path: `${DIR}/average_Group1.nii.gz`, kind: "nifti", label: "average Group1" },
  { path: `${DIR}/average_Group2.nii.gz`, kind: "nifti", label: "average Group2" },
  { path: `${DIR}/config.json`, kind: "json", label: "config" },
  { path: `${DIR}/difference_Group1_minus_Group2.nii.gz`, kind: "nifti", label: "difference Group1 minus Group2" },
];

const catalog: Group = {
  stats: [],
  nilearn: [],
  group_analyses: [],
  nifti_average: [{ name: "avg1", path: DIR, created: "2026-10-22T05:00:00Z", artifacts: ARTIFACTS }],
};

describe("groupOutputsFor (NIfTI group averages)", () => {
  const outputs = groupOutputsFor(catalog);

  it("renders a 'NIfTI group averages' group with one row per run", () => {
    expect(outputs.subject).toBe(GROUP_SUBJECT);
    expect(outputs.groups.map((g) => [g.label, g.count])).toEqual([["NIfTI group averages", 1]]);
    expect(outputs.total).toBe(1);
    const node = outputs.groups[0]!.nodes[0]!;
    expect(node.label).toBe("avg1");
    expect(node.path).toBe(DIR);
    expect(node.created).toBe("2026-10-22T05:00:00Z");
  });

  it("previews the averages, the differences and the config the run wrote", () => {
    const node = outputs.groups[0]!.nodes[0]!;
    expect(node.preview).toEqual({ type: "artifacts", artifacts: ARTIFACTS });
  });

  it("counts the run in the status cell", () => {
    expect(outputsStatusValue(outputs)).toBe("Group · 1 group output");
  });

  it("keeps working against a catalog without the key (a server before this change)", () => {
    const older = { stats: [], nilearn: [], group_analyses: [] } as Group;
    expect(groupOutputsFor(older).groups).toEqual([]);
  });

  it("is re-read when a NIfTI averaging job finishes", () => {
    expect(queriesAffectedBy("nifti_average")).toContainEqual(["results-group"]);
  });
});

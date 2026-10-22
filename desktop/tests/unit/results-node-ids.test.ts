/**
 * Every Results tree row has its own node id, so selecting a row previews that row (2026-10-22, p11).
 *
 * Before: a group-comparison run and a correlation run both named `X` got the id
 * `analysis:Group:stats/X`; the page resolves the selection with `nodes.find(id)`, so clicking the
 * correlation row previewed the group comparison, and React saw two rows with one key. A Mesh and a
 * Voxel analysis of the same ROI collided the same way (`analysis:<sid>:<sim>/<name>`). The server
 * now names analyses uniquely within a simulation (`tests/test_catalog_analysis_identity.py`:
 * `Analyses__Mesh__X` / `Analyses__Voxel__X`), the stats id carries the run's type, and the
 * simulation pane's "Holds" buttons build their ids with the same helper as the tree.
 *
 * Expected values: each row's own `path` and `type`, as the catalog rows are written here (the
 * shapes `GET /api/catalog/group` and `/api/catalog/analyses` return); an id is right when it is
 * unique and `find(id)` lands on the row with that path.
 *
 * Run: cd desktop && npx vitest run tests/unit/results-node-ids.test.ts
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { components } from "../../src/renderer/api/schema";
import {
  analysisNodeId,
  groupOutputsFor,
  outputsTreeFor,
  type OutputNode,
  type SubjectOutputs,
} from "../../src/renderer/pages/results/outputsTree";

type Ana = components["schemas"]["Analysis"];
type Group = components["schemas"]["GroupCatalog"];

const ROOT = "/p/derivatives";

function nodesOf(outputs: SubjectOutputs): OutputNode[] {
  return outputs.groups.flatMap((g) => g.nodes);
}

/** The property every tree must hold: one id per row, and each id finds its own row. */
function expectResolvable(outputs: SubjectOutputs, paths: string[]): void {
  const nodes = nodesOf(outputs);
  const ids = nodes.map((n) => n.id);
  expect(nodes).toHaveLength(paths.length);
  expect(new Set(ids).size).toBe(ids.length);
  for (const path of paths) {
    const owner = nodes.filter((n) => n.path === path);
    expect(owner).toHaveLength(1);
    expect(nodes.find((n) => n.id === owner[0]!.id)!.path).toBe(path);
  }
}

function statsRow(type: string, name: string) {
  return { type, name, path: `${ROOT}/ti-toolbox/stats/${type}/${name}`, created: "2026-10-22T00:00:00Z" };
}

describe("group tree ids", () => {
  it("a group comparison and a correlation with one name are two selectable rows", () => {
    const stats = [statsRow("group_comparison", "X"), statsRow("correlation", "X")];
    const outputs = groupOutputsFor({ stats, nilearn: [], group_analyses: [] } as Group);
    expectResolvable(outputs, stats.map((r) => r.path));
    // Selecting the correlation row previews the correlation run, not the first "X".
    const nodes = nodesOf(outputs);
    const corr = nodes.find((n) => n.path === stats[1]!.path)!;
    expect(nodes.find((n) => n.id === corr.id)!.preview).toEqual({
      type: "groupStats",
      statsType: "correlation",
      name: "X",
    });
  });

  it("holds for every mix of names and types (hand-built catalogs)", () => {
    const types = ["group_comparison", "correlation"];
    const names = ["X", "Y", "X_1"];
    // Every subset of the 6 (type, name) runs, plus same-named nilearn / group-analysis rows.
    for (let mask = 1; mask < 1 << (types.length * names.length); mask++) {
      const stats = types
        .flatMap((t) => names.map((n) => statsRow(t, n)))
        .filter((_r, i) => mask & (1 << i));
      const nilearn = [{ name: "X", path: `${ROOT}/ti-toolbox/nilearn_visuals/X` }];
      const group_analyses = [{ name: "X", path: `${ROOT}/ti-toolbox/group_analysis/X` }];
      const outputs = groupOutputsFor({ stats, nilearn, group_analyses } as Group);
      expectResolvable(outputs, [...stats, ...nilearn, ...group_analyses].map((r) => r.path));
    }
  });
});

function analysis(sim: string, folder: string, name: string): Ana {
  const dir = `${ROOT}/SimNIBS/sub-ernie/Simulations/${sim}/${folder}`;
  return {
    name,
    space: "mni",
    analysis_space: folder.includes("Voxel") ? "voxel" : "mesh",
    field: "TI_max",
    roi: "",
    csv: `${dir}/results.csv`,
    json: `${dir}/analysis.json`,
    msh: null,
    nifti: null,
    pdf: null,
    figures: [],
    scene: null,
  };
}

describe("subject tree ids", () => {
  // The names the server lists when one ROI was analysed in both spaces.
  const S = "sphere_x0.00_y0.00_z0.00_r5.0_MNI";
  const both = [
    analysis("S1", `Analyses/Mesh/${S}`, `Analyses__Mesh__${S}`),
    analysis("S1", `Analyses/Voxel/${S}`, `Analyses__Voxel__${S}`),
    analysis("S1", "Analyses/Mesh/other", "other"),
    // The same name under another simulation is another analysis.
    analysis("S2", "Analyses/Mesh/other", "other"),
  ];
  const tree = outputsTreeFor("ernie", {
    simulations: [],
    flexRuns: [],
    exRuns: [],
    mexRuns: [],
    reports: [],
    analyses: { S1: both.slice(0, 3), S2: both.slice(3) },
  });

  it("gives a Mesh and a Voxel analysis of one ROI two ids that each find their own row", () => {
    expectResolvable(tree, both.map((a) => a.csv));
  });

  it("is the id the simulation pane's Holds buttons select", () => {
    const nodes = nodesOf(tree);
    for (const [sim, list] of [["S1", both.slice(0, 3)], ["S2", both.slice(3)]] as const) {
      for (const a of list) {
        const node = nodes.find((n) => n.id === analysisNodeId("ernie", sim, a.name));
        expect(node?.path).toBe(a.csv);
        expect(node?.preview).toMatchObject({ type: "analysis", simulation: sim, name: a.name });
      }
    }
  });

  it("is built by the same helper in the page's Holds buttons (no second spelling)", () => {
    const page = readFileSync(join(__dirname, "../../src/renderer/pages/results/index.tsx"), "utf8");
    expect(page).toContain("analysisNodeId(subject, node.label, a.name)");
    expect(page).not.toMatch(/`analysis:\$\{subject\}:/);
  });
});

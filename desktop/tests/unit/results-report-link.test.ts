/**
 * Results previews a simulation's own report, or its files when it has none (2026-10-22, p04).
 *
 * The catalog used to attach every report whose path contained the simulation's name, so a run
 * called `TI` or named after its subject previewed the charm report. The server now links only
 * `simulation_report_*` pages titled "<simulation> simulation", newest first, and usually there
 * are none (`tests/test_catalog_report_link.py`). These rows are shaped like the server's real
 * `SimulationDetail` for sub-ernie (Dataset 000 paths), not the mock fixture's.
 *
 * Run: cd desktop && npx vitest run tests/unit/results-report-link.test.ts
 */
import { describe, expect, it } from "vitest";
import type { components } from "../../src/renderer/api/schema";
import { outputsTreeFor, type OutputNode, type SubjectCatalog } from "../../src/renderer/pages/results/outputsTree";

type Sim = components["schemas"]["SimulationDetail"];
type Rep = components["schemas"]["Report"];

const ROOT = "/mnt/000/derivatives";
const SIM_DIR = `${ROOT}/SimNIBS/sub-ernie/Simulations/AF3_PO10_and_AF4_Oz`;

function simulation(reportIds: string[]): Sim {
  return {
    name: "AF3_PO10_and_AF4_Oz",
    path: SIM_DIR,
    has_ti: true,
    has_mti: false,
    montages: ["AF3_PO10_and_AF4_Oz"],
    fields: ["TI_max", "magnE"],
    space: ["subject"],
    report_ids: reportIds,
    niftis: [
      { path: `${SIM_DIR}/TI/niftis/grey_AF3_PO10_and_AF4_Oz_TI_subject_TI_max.nii.gz`, field: "TI_max", space: "subject", tissue: "grey" },
      { path: `${SIM_DIR}/high_Frequency/niftis/ernie_TDCS_1_vn_subject_magnE.nii.gz`, field: "magnE", space: "subject", tissue: null },
    ],
    meshes: [{ path: `${SIM_DIR}/TI/mesh/AF3_PO10_and_AF4_Oz_TI.msh`, kind: "field" }],
  } as Sim;
}

const REPORTS: Rep[] = ["charm_report", "simulation_report_20260923_184500"].map((stem) => ({
  id: `ernie/${stem}`,
  kind: stem === "charm_report" ? "charm_report" : "simulation_report",
  title: stem,
  path: `${ROOT}/ti-toolbox/reports/sub-ernie/${stem}.html`,
  created: "2026-09-23T18:45:00Z",
})) as Rep[];

function simulationNode(reportIds: string[]): OutputNode {
  const data: SubjectCatalog = {
    simulations: [simulation(reportIds)],
    flexRuns: [],
    exRuns: [],
    mexRuns: [],
    analyses: {},
    reports: REPORTS,
  };
  const group = outputsTreeFor("ernie", data).groups.find((g) => g.kind === "simulation");
  expect(group?.nodes).toHaveLength(1);
  return group!.nodes[0];
}

describe("a simulation's preview", () => {
  it("shows its NIfTIs and meshes when no report is linked, never another report", () => {
    const node = simulationNode([]);
    expect(node.preview.type).toBe("artifacts");
    if (node.preview.type !== "artifacts") return;
    expect(node.preview.artifacts.map((a) => [a.kind, a.label])).toEqual([
      ["nifti", "TI_max · subject · grey"],
      ["nifti", "magnE · subject"],
      ["mesh", "field mesh"],
    ]);
    expect(node.preview.artifacts.map((a) => a.path)).toEqual([
      `${SIM_DIR}/TI/niftis/grey_AF3_PO10_and_AF4_Oz_TI_subject_TI_max.nii.gz`,
      `${SIM_DIR}/high_Frequency/niftis/ernie_TDCS_1_vn_subject_magnE.nii.gz`,
      `${SIM_DIR}/TI/mesh/AF3_PO10_and_AF4_Oz_TI.msh`,
    ]);
  });

  it("opens the first linked report, which the server lists newest first", () => {
    const node = simulationNode(["ernie/simulation_report_20260923_184500", "ernie/simulation_report_20260101_000000"]);
    expect(node.preview).toEqual({ type: "report", reportId: "ernie/simulation_report_20260923_184500" });
  });

  it("does not borrow a report of the subject that the simulation does not link", () => {
    // The subject has a charm report and a simulation report; neither is this run's.
    const node = simulationNode([]);
    expect(JSON.stringify(node.preview)).not.toContain("report_");
  });
});

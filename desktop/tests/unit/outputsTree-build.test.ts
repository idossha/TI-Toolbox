/**
 * `pages/results/outputsTree.ts` — the grouping, the badges, the counts and the preview routing of
 * the Results tree (U4, DESIGN.md §2 shape B). The fixtures the mock server serves are the input,
 * so a change to `tests/fixtures/*.json` that would move a node shows up here rather than in a
 * screenshot nobody diffs.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { components } from "../../src/renderer/api/schema";
import {
  analysisArtifacts,
  filterOutputs,
  GROUP_SUBJECT,
  groupOutputsFor,
  matchesFilter,
  matchesQuery,
  outputsStatusValue,
  outputsTreeFor,
  truncatePathLeft,
  treeRows,
  type SubjectCatalog,
} from "../../src/renderer/pages/results/outputsTree";

type Sim = components["schemas"]["SimulationDetail"];
type Flex = components["schemas"]["FlexRun"];
type Ex = components["schemas"]["ExRun"];
type Ana = components["schemas"]["Analysis"];
type Rep = components["schemas"]["Report"];
type Group = components["schemas"]["GroupCatalog"];

const FIXTURES = join(__dirname, "..", "fixtures");
const load = <T>(name: string): T => JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as T;

const simulations = load<Record<string, Sim[]>>("simulations.json");
const flexRuns = load<Record<string, Flex[]>>("flex_runs.json");
const exRuns = load<Record<string, { ex: Ex[]; mex: Ex[] }>>("ex_runs.json");
const analyses = load<Record<string, Record<string, Ana[]>>>("analyses.json");
const reports = load<Record<string, Rep[]>>("reports.json");
const groupCatalog = load<Group>("group_catalog.json");

function catalogFor(subject: string): SubjectCatalog {
  return {
    simulations: simulations[subject] ?? [],
    flexRuns: flexRuns[subject] ?? [],
    exRuns: exRuns[subject]?.ex ?? [],
    mexRuns: exRuns[subject]?.mex ?? [],
    analyses: analyses[subject] ?? {},
    reports: reports[subject] ?? [],
  };
}

describe("outputsTreeFor", () => {
  const ernie = outputsTreeFor("ernie", catalogFor("ernie"));

  it("groups ernie's fixture outputs in wireframe order, with the counts the headings print", () => {
    expect(ernie.groups.map((g) => [g.label, g.count])).toEqual([
      ["Simulations", 3],
      ["Flex runs", 1],
      ["Ex / mEx runs", 2],
      ["Analyses", 3],
      ["Reports", 3],
    ]);
    // The subject list's count is the sum of the headings — one number, computed once.
    expect(ernie.total).toBe(12);
    expect(ernie.total).toBe(ernie.groups.reduce((n, g) => n + g.count, 0));
  });

  it("drops empty groups rather than printing a heading with a zero (U1)", () => {
    const mni = outputsTreeFor("MNI152", catalogFor("MNI152"));
    expect(mni.total).toBe(0);
    expect(mni.groups).toEqual([]);

    const s101 = outputsTreeFor("101", catalogFor("101"));
    expect(s101.groups.map((g) => g.label)).toEqual(["Simulations", "Analyses", "Reports"]);
  });

  it("badges every node from the fixed vocabulary and nothing else", () => {
    const allowed = new Set(["TI", "mTI", "flex", "ex", "mex", "analysis", "report"]);
    const badges = ernie.groups.flatMap((g) => g.nodes.flatMap((n) => n.badges));
    expect(badges.length).toBeGreaterThan(0);
    for (const b of badges) expect(allowed.has(b)).toBe(true);

    const sims = ernie.groups[0]!.nodes;
    expect(sims.find((n) => n.label === "Thalamus")!.badges).toEqual(["TI"]);
    expect(sims.find((n) => n.label === "docs_example")!.badges).toEqual(["mTI"]);
  });

  it("gives every node a stable id keyed on kind, subject and name", () => {
    const ids = ernie.groups.flatMap((g) => g.nodes.map((n) => n.id));
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain("simulation:ernie:Thalamus");
    expect(ids).toContain("mex:ernie:mex_Thalamus_20260814_140000");
    expect(ids).toContain("analysis:ernie:Thalamus/cortical_2regions_DK40_71a9008a");
    // A second build of the same data yields the same ids, so selection survives a refetch.
    expect(outputsTreeFor("ernie", catalogFor("ernie")).groups.flatMap((g) => g.nodes.map((n) => n.id))).toEqual(ids);
  });

  it("routes each node's preview to the read that renders it", () => {
    const byId = new Map(ernie.groups.flatMap((g) => g.nodes.map((n) => [n.id, n] as const)));
    // A simulation with a report previews the report; the report id is the one the fixture names.
    expect(byId.get("simulation:ernie:Thalamus")!.preview).toEqual({
      type: "report",
      reportId: "ernie/simulation_report_20260801_110000",
    });
    // A simulation with no report previews its artifacts instead.
    expect(byId.get("simulation:ernie:L_Insula")!.preview.type).toBe("artifacts");
    expect(byId.get("ex:ernie:ex_L_Insula_20260812_090000")!.preview).toEqual({
      type: "exRun",
      subject: "ernie",
      run: "ex_L_Insula_20260812_090000",
      kind: "ex",
    });
    expect(byId.get("analysis:ernie:Thalamus/cortical_2regions_DK40_71a9008a")!.preview).toEqual({
      type: "analysis",
      subject: "ernie",
      simulation: "Thalamus",
      name: "cortical_2regions_DK40_71a9008a",
    });
    const flex = byId.get("flex:ernie:flex_Thalamus_20260810_101500")!;
    expect(flex.preview.type).toBe("artifacts");
    expect(flex.preview.type === "artifacts" && flex.preview.artifacts).toHaveLength(2);
  });

  it("falls back to the simulation's own files when it has no report", () => {
    const noReport = outputsTreeFor("x", {
      ...catalogFor("MNI152"),
      simulations: [
        {
          name: "Draft",
          path: "/p/Draft",
          has_ti: true,
          has_mti: false,
          montages: [],
          fields: [],
          space: ["subject"],
          report_ids: [],
          niftis: [{ path: "/p/Draft/TI_max.nii.gz", field: "TI_max", space: "subject", tissue: null }],
          meshes: [{ path: "/p/Draft/TI.msh", kind: "ti" }],
        } satisfies Sim,
      ],
    });
    const node = noReport.groups[0]!.nodes[0]!;
    expect(node.preview).toEqual({
      type: "artifacts",
      artifacts: [
        { path: "/p/Draft/TI_max.nii.gz", kind: "nifti", label: "TI_max · subject" },
        { path: "/p/Draft/TI.msh", kind: "mesh", label: "ti mesh" },
      ],
    });
  });
});

describe("groupOutputsFor", () => {
  const group = groupOutputsFor(groupCatalog);

  it("turns the project catalog into the same tree shape under the Group pseudo-subject", () => {
    expect(group.subject).toBe(GROUP_SUBJECT);
    // The fixture lists a NIfTI group average, as the real group catalog does since p11.
    expect(group.total).toBe(4);
    expect(group.groups.map((g) => [g.label, g.count])).toEqual([
      ["Group statistics", 1],
      ["Nilearn visuals", 1],
      ["Group analyses", 1],
      ["NIfTI group averages", 1],
    ]);
    expect(group.groups[0]!.nodes[0]!.label).toBe("group_comparison_Thalamus_TI_max_20260815");
  });
});

describe("filtering", () => {
  const ernie = outputsTreeFor("ernie", catalogFor("ernie"));

  it("puts ex and mex behind one segment, as the toolbar does", () => {
    const exmex = filterOutputs(ernie, "exmex", "");
    expect(exmex.total).toBe(2);
    expect(exmex.groups.map((g) => g.label)).toEqual(["Ex / mEx runs"]);
    const ex = exmex.groups[0]!.nodes;
    expect(ex.map((n) => n.kind).sort()).toEqual(["ex", "mex"]);
  });

  it("narrows by substring over the label, the path and the badges", () => {
    // Thalamus simulation, flex_Thalamus…, mex_Thalamus…, the Thalamus analysis, and its report:
    // the real catalog lists a report by its page title, "Thalamus simulation" (c1_5), so the
    // filter finds a report by the simulation it reports on.
    const thalamus = filterOutputs(ernie, "all", "thalamus");
    expect(thalamus.total).toBe(5);
    expect(thalamus.groups.find((g) => g.kind === "report")?.nodes.map((n) => [n.id, n.label])).toEqual([
      ["report:ernie:ernie/simulation_report_20260801_110000", "Thalamus simulation"],
    ]);
    expect(filterOutputs(ernie, "all", "simulation_report").total).toBe(2);
    expect(filterOutputs(ernie, "all", "no-such-thing").total).toBe(0);
    expect(filterOutputs(ernie, "all", "no-such-thing").groups).toEqual([]);
    const node = ernie.groups[0]!.nodes[0]!;
    expect(matchesQuery(node, "")).toBe(true);
    expect(matchesQuery(node, "TI")).toBe(true);
    expect(matchesFilter(node, "report")).toBe(false);
    expect(matchesFilter(node, "all")).toBe(true);
  });
});

describe("treeRows", () => {
  const ernie = outputsTreeFor("ernie", catalogFor("ernie"));

  it("emits one heading per group and, expanded, its nodes under it", () => {
    const rows = treeRows(ernie, new Set());
    expect(rows.filter((r) => r.type === "group")).toHaveLength(5);
    expect(rows.filter((r) => r.type === "node")).toHaveLength(12);
    expect(rows[0]!.type).toBe("group");
    expect(rows[1]!.type).toBe("node");
  });

  it("hides a collapsed group's nodes but keeps its heading", () => {
    const rows = treeRows(ernie, new Set(["Simulations"]));
    expect(rows.filter((r) => r.type === "group")).toHaveLength(5);
    expect(rows.filter((r) => r.type === "node")).toHaveLength(9);
    expect(rows[0]).toMatchObject({ type: "group", expanded: false });
  });
});

describe("outputsStatusValue", () => {
  it("is the §11.1 counts cell, pluralised from the numbers it carries", () => {
    expect(outputsStatusValue(outputsTreeFor("ernie", catalogFor("ernie")))).toBe(
      "ernie · 3 simulations · 1 flex run · 2 search runs · 3 analyses · 3 reports",
    );
    expect(outputsStatusValue(outputsTreeFor("101", catalogFor("101")))).toBe(
      "101 · 1 simulation · 1 analysis · 1 report",
    );
  });

  it("says so rather than printing an empty string when a subject has nothing", () => {
    expect(outputsStatusValue(outputsTreeFor("MNI152", catalogFor("MNI152")))).toBe("MNI152 · no outputs");
    expect(outputsStatusValue(undefined)).toBeUndefined();
  });
});

describe("truncatePathLeft", () => {
  const path = "/mnt/example/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus";

  it("keeps the informative tail and marks the cut with a leading ellipsis", () => {
    const short = truncatePathLeft(path, 30);
    expect(short).toHaveLength(30);
    expect(short.startsWith("…")).toBe(true);
    expect(path.endsWith(short.slice(1))).toBe(true);
    // No trailing slash invented, which is what the `direction: rtl` CSS trick did to this string.
    expect(short.endsWith("/")).toBe(false);
  });

  it("leaves a path that already fits exactly as it is", () => {
    expect(truncatePathLeft("/p/Draft", 40)).toBe("/p/Draft");
    expect(truncatePathLeft(path, path.length)).toBe(path);
  });
});

describe("analysisArtifacts", () => {
  it("lists only the files an analysis actually has", () => {
    const withAll = analyses.ernie!.Thalamus![0]!;
    expect(analysisArtifacts(withAll).map((a) => a.kind)).toEqual(["csv", "json", "nifti", "pdf"]);
    const sparse = analyses.ernie!.L_Insula![0]!;
    expect(analysisArtifacts(sparse).map((a) => a.kind)).toEqual(["csv", "json"]);
  });
});

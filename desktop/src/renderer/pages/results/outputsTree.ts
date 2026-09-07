/**
 * The Results outputs tree (program U4, `docs/dev/DESIGN.md` Appendix A).
 *
 * Pure functions only: the page fetches the catalog endpoints, hands the raw responses in, and
 * gets back the grouped tree the middle column renders. Nothing here touches React or the network,
 * which is why the grouping, the badges, the counts and the preview routing are unit-testable
 * without a browser — the numbers in `tests/unit/outputsTree-*.test.ts` are read, not estimated.
 *
 * `pages/results/api.ts` is untouched by design: this module sits beside it and consumes what it
 * returns.
 */
import type { Analysis, Artifact, ExRun, FlexRun, GroupCatalog, Report, SimulationDetail } from "./api";

export type OutputKind = "simulation" | "flex" | "ex" | "mex" | "analysis" | "report";

/** How the preview pane renders the selected node. One variant per catalog read. */
export type PreviewRef =
  | { type: "report"; reportId: string }
  | { type: "analysis"; subject: string; simulation: string; name: string }
  | { type: "exRun"; subject: string; run: string; kind: "ex" | "mex" }
  | { type: "artifacts"; artifacts: Artifact[] };

export interface OutputNode {
  /** `${kind}:${subject}:${name}` — stable across refetches, so selection survives a poll. */
  id: string;
  kind: OutputKind;
  label: string;
  /** Chip text, from the fixed vocabulary: TI · mTI · flex · ex · mex · analysis · report. */
  badges: string[];
  /** Absolute container path. Rendered mono and truncated from the left (checklist item 4). */
  path: string;
  /** ISO timestamp; the `CREATED` column the tree gains at 1440. */
  created?: string;
  preview: PreviewRef;
  /**
   * Reserved by the u0 §3.7 contract. Deliberately left unset: the wireframe gives analyses their
   * own group, so nesting them under their simulation as well would put the same node id on screen
   * twice and make the group counts disagree with the rows.
   */
  children?: OutputNode[];
}

export interface OutputGroup {
  kind: OutputKind | "group";
  label: string;
  count: number;
  nodes: OutputNode[];
}

export interface SubjectOutputs {
  subject: string;
  total: number;
  groups: OutputGroup[];
}

/** Everything `outputsTreeFor` needs, one field per catalog endpoint. */
export interface SubjectCatalog {
  simulations: SimulationDetail[];
  flexRuns: FlexRun[];
  exRuns: ExRun[];
  mexRuns: ExRun[];
  /** Keyed by simulation name — `GET /api/catalog/analyses?subject=&simulation=` is per simulation. */
  analyses: Record<string, Analysis[]>;
  reports: Report[];
}

/** The `Group` pseudo-subject's id. Pinned under a rule at the bottom of the subject list. */
export const GROUP_SUBJECT = "Group";

/** The filter segments over the tree; `all` is the default. */
export type OutputFilter = "all" | "simulation" | "flex" | "exmex" | "analysis" | "report";

function nifti(path: string, label: string): Artifact {
  return { path, kind: "nifti", label };
}

function simulationArtifacts(sim: SimulationDetail): Artifact[] {
  return [
    ...sim.niftis.map((n) => nifti(n.path, `${n.field} · ${n.space}${n.tissue ? ` · ${n.tissue}` : ""}`)),
    ...sim.meshes.map((m) => ({ path: m.path, kind: "mesh", label: `${m.kind} mesh` })),
  ];
}

/** Artifacts of an analysis: whichever of its four optional files exist. */
export function analysisArtifacts(a: Analysis): Artifact[] {
  const out: Artifact[] = [];
  if (a.csv) out.push({ path: a.csv, kind: "csv", label: "Summary table" });
  if (a.json) out.push({ path: a.json, kind: "json", label: "Summary JSON" });
  if (a.nifti) out.push(nifti(a.nifti, "Masked field"));
  if (a.msh) out.push({ path: a.msh, kind: "mesh", label: "Masked mesh" });
  if (a.pdf) out.push({ path: a.pdf, kind: "pdf", label: "PDF report" });
  return out;
}

function simulationNode(subject: string, sim: SimulationDetail): OutputNode {
  const badges: string[] = [];
  if (sim.has_ti) badges.push("TI");
  if (sim.has_mti) badges.push("mTI");
  const reportId = sim.report_ids[0];
  return {
    id: `simulation:${subject}:${sim.name}`,
    kind: "simulation",
    label: sim.name,
    badges,
    path: sim.path,
    preview: reportId ? { type: "report", reportId } : { type: "artifacts", artifacts: simulationArtifacts(sim) },
  };
}

function flexNode(subject: string, run: FlexRun): OutputNode {
  return {
    id: `flex:${subject}:${run.name}`,
    kind: "flex",
    label: run.name,
    badges: ["flex"],
    path: run.path,
    created: run.created,
    preview: { type: "artifacts", artifacts: run.artifacts },
  };
}

function exNode(subject: string, run: ExRun, kind: "ex" | "mex"): OutputNode {
  return {
    id: `${kind}:${subject}:${run.run_name}`,
    kind,
    label: run.run_name,
    badges: [kind],
    path: run.path,
    created: run.created,
    preview: { type: "exRun", subject, run: run.run_name, kind },
  };
}

function analysisNode(subject: string, simulation: string, a: Analysis): OutputNode {
  return {
    id: `analysis:${subject}:${simulation}/${a.name}`,
    kind: "analysis",
    label: `${simulation} / ${a.name}`,
    badges: ["analysis"],
    // An analysis has no directory of its own in the schema; its summary table is the anchor the
    // user reveals, and every other file sits beside it.
    path: a.csv ?? a.json ?? a.pdf ?? a.nifti ?? a.msh ?? "",
    preview: { type: "analysis", subject, simulation, name: a.name },
  };
}

function reportNode(subject: string, r: Report): OutputNode {
  return {
    id: `report:${subject}:${r.id}`,
    kind: "report",
    label: r.title,
    badges: ["report"],
    path: r.path,
    created: r.created,
    preview: { type: "report", reportId: r.id },
  };
}

function group(kind: OutputGroup["kind"], label: string, nodes: OutputNode[]): OutputGroup {
  return { kind, label, count: nodes.length, nodes };
}

/**
 * The five groups of one subject's outputs, in the wireframe's order. Empty groups are dropped —
 * a heading reading "Flex runs 0" is a row of chrome carrying no output (U1).
 */
export function outputsTreeFor(subject: string, data: SubjectCatalog): SubjectOutputs {
  const simulations = data.simulations.map((s) => simulationNode(subject, s));
  const flex = data.flexRuns.map((r) => flexNode(subject, r));
  const exmex = [...data.exRuns.map((r) => exNode(subject, r, "ex")), ...data.mexRuns.map((r) => exNode(subject, r, "mex"))];
  const analyses = Object.entries(data.analyses).flatMap(([simulation, list]) =>
    list.map((a) => analysisNode(subject, simulation, a)),
  );
  const reports = data.reports.map((r) => reportNode(subject, r));

  const groups = [
    group("simulation", "Simulations", simulations),
    group("flex", "Flex runs", flex),
    group("ex", "Ex / mEx runs", exmex),
    group("analysis", "Analyses", analyses),
    group("report", "Reports", reports),
  ].filter((g) => g.count > 0);

  return { subject, total: groups.reduce((n, g) => n + g.count, 0), groups };
}

/**
 * The `Group` pseudo-subject: the project-level catalog under the same tree shape, so the preview
 * pane, the filter and the keyboard navigation need no second code path.
 */
export function groupOutputsFor(catalog: GroupCatalog): SubjectOutputs {
  const rows = (list: { [key: string]: unknown }[], label: string): OutputNode[] =>
    list.map((row, i) => {
      const name = typeof row.name === "string" ? row.name : `${label} ${i + 1}`;
      const path = typeof row.path === "string" ? row.path : "";
      const created = typeof row.created === "string" ? row.created : undefined;
      return {
        id: `analysis:${GROUP_SUBJECT}:${label}/${name}`,
        kind: "analysis" as const,
        label: name,
        badges: ["analysis"],
        path,
        created,
        preview: { type: "artifacts" as const, artifacts: path ? [{ path, kind: "group", label: name }] : [] },
      };
    });

  const groups = [
    group("group", "Group statistics", rows(catalog.stats, "stats")),
    group("group", "Nilearn visuals", rows(catalog.nilearn, "nilearn")),
    group("group", "Group analyses", rows(catalog.group_analyses, "analyses")),
  ].filter((g) => g.count > 0);

  return { subject: GROUP_SUBJECT, total: groups.reduce((n, g) => n + g.count, 0), groups };
}

/**
 * A container path shortened from the LEFT (checklist item 4), because the informative end of
 * `/mnt/example/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus` is its tail.
 *
 * Done in JS rather than with `direction: rtl` + `text-overflow: ellipsis`: the CSS trick reorders
 * the leading `/` to the end of the visible run (bidi), so the path rendered as
 * `…e/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/` — a trailing slash that is not in the
 * path, on a string the user may copy.
 */
export function truncatePathLeft(path: string, max = 40): string {
  if (path.length <= max) return path;
  return `…${path.slice(path.length - (max - 1))}`;
}

/** Does this node belong in the segment the user picked? `ex` and `mex` share one segment. */
export function matchesFilter(node: OutputNode, filter: OutputFilter): boolean {
  if (filter === "all") return true;
  if (filter === "exmex") return node.kind === "ex" || node.kind === "mex";
  return node.kind === filter;
}

/** Substring match over the label, the badges and the path — what the filter box searches. */
export function matchesQuery(node: OutputNode, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    node.label.toLowerCase().includes(q) ||
    node.path.toLowerCase().includes(q) ||
    node.badges.some((b) => b.toLowerCase().includes(q))
  );
}

/** Applies the segment and the query, dropping groups that end up empty. */
export function filterOutputs(outputs: SubjectOutputs, filter: OutputFilter, query: string): SubjectOutputs {
  const groups = outputs.groups
    .map((g) => group(g.kind, g.label, g.nodes.filter((n) => matchesFilter(n, filter) && matchesQuery(n, query))))
    .filter((g) => g.count > 0);
  return { subject: outputs.subject, total: groups.reduce((n, g) => n + g.count, 0), groups };
}

/**
 * The left column: one row per subject with its total output count, `Group` last.
 *
 * `loaded` is keyed by subject and is sparse while the per-subject queries are in flight; a subject
 * whose outputs have not arrived reports `total: 0` and `pending: true`, so the row can omit the
 * count rather than print a `0` it has not measured (U8's no-placeholder rule, applied to a table).
 */
export function subjectOutputCounts(
  subjects: string[],
  loaded: Record<string, SubjectOutputs | undefined>,
): { subject: string; total: number; pending: boolean }[] {
  return subjects.map((subject) => {
    const outputs = loaded[subject];
    return { subject, total: outputs?.total ?? 0, pending: outputs === undefined };
  });
}

/**
 * The `counts` status cell for this page (§11.1): `ernie · 3 simulations · 2 analyses · 1 report`.
 * Only non-zero kinds appear, and the words are pluralised from the number they carry.
 */
export function outputsStatusValue(outputs: SubjectOutputs | undefined): string | undefined {
  if (!outputs) return undefined;
  const plural = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`;
  const parts: string[] = [];
  for (const g of outputs.groups) {
    if (g.kind === "simulation") parts.push(plural(g.count, "simulation"));
    else if (g.kind === "flex") parts.push(plural(g.count, "flex run"));
    else if (g.kind === "ex" || g.kind === "mex") parts.push(plural(g.count, "search run"));
    else if (g.kind === "analysis") parts.push(plural(g.count, "analysis", "analyses"));
    else if (g.kind === "report") parts.push(plural(g.count, "report"));
    else parts.push(plural(g.count, "group output"));
  }
  return parts.length ? [outputs.subject, ...parts].join(" · ") : `${outputs.subject} · no outputs`;
}

/** Flattened rows the tree renders and the keyboard walks: a group heading, then its visible nodes. */
export type TreeRow =
  | { type: "group"; key: string; group: OutputGroup; expanded: boolean }
  | { type: "node"; key: string; node: OutputNode; groupLabel: string };

export function treeRows(outputs: SubjectOutputs, collapsed: ReadonlySet<string>): TreeRow[] {
  const rows: TreeRow[] = [];
  for (const g of outputs.groups) {
    const expanded = !collapsed.has(g.label);
    rows.push({ type: "group", key: `g:${g.label}`, group: g, expanded });
    if (expanded) for (const node of g.nodes) rows.push({ type: "node", key: node.id, node, groupLabel: g.label });
  }
  return rows;
}

/**
 * The pipeline graph, client side — a deliberate mirror of `tit/pipeline/{document,validate}.py`.
 *
 * The server is the authority: `POST /api/pipelines/validate` is what the receipt and the Run
 * button read. What *cannot* wait for a round trip is the refusal reason shown while a wire is
 * being dragged, so `canConnect` lives here too. `tests/test_pipeline_graph.py` and
 * `desktop/tests/unit/pipeline-graph.test.ts` assert the same table of refusals on both sides, so
 * the two cannot drift into disagreeing about which wire is legal.
 */

import {
  BarChart3,
  Crosshair,
  Grid3x3,
  Radio,
  Sigma,
  SquareStack,
  Target,
  Waypoints,
  Zap,
  type LucideIcon,
} from "lucide-react";

export type PortType = "subjects" | "montages" | "simulation" | "roi" | "leadfield";

export type NodeKind =
  | "pre"
  | "leadfield"
  | "flex"
  | "ex"
  | "mex"
  | "sim"
  | "analyzer"
  | "source"
  | "stats";

export interface KindPorts {
  inputs: PortType[];
  outputs: PortType[];
  /** Inputs that must be wired *or* satisfied by the node's own config. */
  required: PortType[];
}

/** Mirrors `tit.pipeline.document.PORTS`. Fetched at runtime too (`GET /api/pipelines/kinds`);
 *  this copy is the offline default so the palette renders before the first response. */
export const PORTS: Record<NodeKind, KindPorts> = {
  pre: { inputs: [], outputs: ["subjects"], required: [] },
  leadfield: { inputs: ["subjects"], outputs: ["subjects", "leadfield"], required: [] },
  flex: { inputs: ["subjects", "roi"], outputs: ["subjects", "montages", "roi"], required: [] },
  ex: { inputs: ["subjects", "roi", "leadfield"], outputs: ["subjects", "montages", "roi"], required: [] },
  mex: { inputs: ["subjects", "roi", "leadfield"], outputs: ["subjects", "montages", "roi"], required: [] },
  sim: { inputs: ["subjects", "montages"], outputs: ["subjects", "simulation"], required: ["subjects"] },
  analyzer: { inputs: ["subjects", "simulation", "roi"], outputs: ["subjects"], required: ["subjects", "simulation"] },
  source: { inputs: ["subjects"], outputs: ["subjects"], required: ["subjects"] },
  stats: { inputs: ["subjects"], outputs: [], required: ["subjects"] },
};

/** Palette order — the workflow order, not alphabetical. */
export const NODE_KINDS: NodeKind[] = ["pre", "leadfield", "flex", "ex", "mex", "sim", "analyzer", "source", "stats"];

export const PORT_LABEL: Record<PortType, string> = {
  subjects: "Subjects",
  montages: "Montage names",
  simulation: "Simulation name",
  roi: "ROI",
  leadfield: "Leadfield",
};

export const KIND_TITLE: Record<NodeKind, string> = {
  pre: "Pre-processing",
  leadfield: "Leadfield",
  flex: "Flex-search",
  ex: "Ex-search",
  mex: "mEx-search",
  sim: "Simulator",
  analyzer: "Analyzer",
  source: "Source model",
  stats: "Group statistics",
};

/** The rail icon of the page each kind belongs to, so a card is recognisable before it is read. */
export const KIND_ICON: Record<NodeKind, LucideIcon> = {
  pre: SquareStack,
  leadfield: Grid3x3,
  flex: Target,
  ex: Crosshair,
  mex: Waypoints,
  sim: Zap,
  analyzer: BarChart3,
  source: Radio,
  stats: Sigma,
};

export interface PipelineNode {
  id: string;
  kind: NodeKind;
  label?: string;
  config: Record<string, unknown>;
  position: { x: number; y: number };
}

export interface PipelineEdge {
  from: string;
  to: string;
  port: PortType;
}

export interface PipelineDoc {
  version: 1;
  name: string;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

export const emptyPipeline = (name = "untitled"): PipelineDoc => ({ version: 1, name, nodes: [], edges: [] });

export const nodeById = (doc: PipelineDoc, id: string): PipelineNode | undefined => doc.nodes.find((n) => n.id === id);
export const incoming = (doc: PipelineDoc, id: string): PipelineEdge[] => doc.edges.filter((e) => e.to === id);
export const outgoing = (doc: PipelineDoc, id: string): PipelineEdge[] => doc.edges.filter((e) => e.from === id);

export function displayName(node: PipelineNode): string {
  return node.label || `${node.kind} (${node.id})`;
}

/** A node id that is unique in *this* document — `sim1`, `sim2`, … so labels stay readable. */
export function nextNodeId(doc: PipelineDoc, kind: NodeKind): string {
  const taken = new Set(doc.nodes.map((n) => n.id));
  for (let i = 1; ; i += 1) {
    const candidate = `${kind}${i}`;
    if (!taken.has(candidate)) return candidate;
  }
}

function reaches(doc: PipelineDoc, start: string, goal: string): boolean {
  const seen = new Set<string>();
  const stack = [start];
  while (stack.length) {
    const current = stack.pop()!;
    if (current === goal) return true;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const edge of outgoing(doc, current)) stack.push(edge.to);
  }
  return false;
}

/** May this wire be drawn? Mirrors `tit.pipeline.validate.can_connect` reason for reason. */
export function canConnect(
  doc: PipelineDoc,
  source: string,
  target: string,
  port: PortType,
): { ok: true } | { ok: false; reason: string } {
  const src = nodeById(doc, source);
  const dst = nodeById(doc, target);
  if (!src) return { ok: false, reason: `no such node: ${source}` };
  if (!dst) return { ok: false, reason: `no such node: ${target}` };
  if (source === target) return { ok: false, reason: "a node cannot feed itself" };
  if (!PORTS[src.kind].outputs.includes(port)) return { ok: false, reason: `${src.kind} does not produce ${PORT_LABEL[port]}` };
  if (!PORTS[dst.kind].inputs.includes(port)) return { ok: false, reason: `${dst.kind} does not take ${PORT_LABEL[port]}` };
  for (const edge of incoming(doc, target)) {
    if (edge.port !== port) continue;
    if (edge.from === source) return { ok: false, reason: `${PORT_LABEL[port]} is already wired from this node` };
    const from = nodeById(doc, edge.from);
    return { ok: false, reason: `${PORT_LABEL[port]} is already wired from ${from ? displayName(from) : edge.from}` };
  }
  if (reaches(doc, target, source)) return { ok: false, reason: "that would make a cycle" };
  return { ok: true };
}

/** Dependency-first node ids, or `null` for a cycle. Mirrors `validate.topological_order`. */
export function topologicalOrder(doc: PipelineDoc): string[] | null {
  const ids = doc.nodes.map((n) => n.id);
  const indegree = new Map(ids.map((id) => [id, 0]));
  for (const edge of doc.edges) {
    if (indegree.has(edge.to) && indegree.has(edge.from)) indegree.set(edge.to, indegree.get(edge.to)! + 1);
  }
  const ready = ids.filter((id) => indegree.get(id) === 0);
  const order: string[] = [];
  while (ready.length) {
    const current = ready.shift()!;
    order.push(current);
    for (const edge of outgoing(doc, current)) {
      if (!indegree.has(edge.to)) continue;
      indegree.set(edge.to, indegree.get(edge.to)! - 1);
      if (indegree.get(edge.to) === 0) {
        ready.push(edge.to);
        ready.sort((a, b) => ids.indexOf(a) - ids.indexOf(b));
      }
    }
  }
  return order.length === ids.length ? order : null;
}

/** The subject list a node runs over: its bound upstream set, else its own config. */
export function subjectsOf(doc: PipelineDoc, id: string, seen = new Set<string>()): string[] {
  if (seen.has(id)) return [];
  seen.add(id);
  for (const edge of incoming(doc, id)) {
    if (edge.port === "subjects") return subjectsOf(doc, edge.from, seen);
  }
  return configSubjects(nodeById(doc, id)?.config);
}

export function configSubjects(config: Record<string, unknown> | undefined): string[] {
  const list = config?.subject_ids;
  if (Array.isArray(list)) {
    const cleaned = list.map((s) => String(s).trim()).filter(Boolean);
    if (cleaned.length) return cleaned;
  }
  const one = String(config?.subject_id ?? "").trim();
  return one ? [one] : [];
}

/** The one line a node card prints under its title. */
export function nodeSummary(doc: PipelineDoc, node: PipelineNode): string {
  const parts: string[] = [];
  const subjects = subjectsOf(doc, node.id);
  const wiredSubjects = incoming(doc, node.id).some((e) => e.port === "subjects");
  if (subjects.length) {
    parts.push(
      subjects.length === 1 ? String(subjects[0]) : `${subjects.length} subjects${wiredSubjects ? " (wired)" : ""}`,
    );
  }
  const montages = node.config.montages;
  if (node.kind === "sim") {
    if (incoming(doc, node.id).some((e) => e.port === "montages")) parts.push("montages from optimizer");
    else if (Array.isArray(montages) && montages.length) {
      const names = montages.map((m) => String((m as { name?: unknown })?.name ?? "")).filter(Boolean);
      parts.push(names.length ? names.join(", ") : `${montages.length} montages`);
    }
  }
  if (node.kind === "analyzer") {
    if (incoming(doc, node.id).some((e) => e.port === "simulation")) parts.push("simulation from Simulator");
    else if (node.config.simulation) parts.push(String(node.config.simulation));
    const analysisType = node.config.analysis_type;
    if (analysisType) parts.push(String(analysisType));
  }
  if (node.kind === "flex" || node.kind === "ex" || node.kind === "mex") {
    const goal = node.config.goal;
    if (goal) parts.push(String(goal));
  }
  return parts.join(" · ") || "not configured yet";
}

/**
 * A worked example the empty canvas can offer: pre → flex → sim → analyzer, wired the way the
 * four steps actually depend on each other, on whichever subject the project has.
 *
 * It is the same graph the D6 gate submits, which is deliberate: the button hands a first-time
 * user a pipeline that is known to validate and run, rather than four unconfigured cards.
 */
export function samplePipeline(subject: string): PipelineDoc {
  return {
    version: 1,
    name: "sample",
    nodes: [
      { id: "pre1", kind: "pre", label: "Head model", config: { subject_ids: [subject], create_m2m: true }, position: { x: 0, y: 80 } },
      { id: "flex1", kind: "flex", label: "Find a montage", config: { goal: "mean", postproc: "max_TI" }, position: { x: 280, y: 0 } },
      { id: "sim1", kind: "sim", label: "Simulate it", config: { conductivity: "scalar" }, position: { x: 560, y: 80 } },
      {
        id: "an1",
        kind: "analyzer",
        label: "Measure the ROI",
        config: { space: "mesh", analysis_type: "spherical", center: [0, 0, 0], radius: 5 },
        position: { x: 840, y: 160 },
      },
    ],
    edges: [
      { from: "pre1", to: "flex1", port: "subjects" },
      { from: "pre1", to: "sim1", port: "subjects" },
      { from: "flex1", to: "sim1", port: "montages" },
      { from: "sim1", to: "an1", port: "subjects" },
      { from: "sim1", to: "an1", port: "simulation" },
    ],
  };
}

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
  Users,
  Waypoints,
  Zap,
  type LucideIcon,
} from "lucide-react";

export type PortType = "subjects" | "montages" | "simulation" | "roi" | "leadfield";

export type NodeKind =
  | "subjects"
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
  subjects: { inputs: [], outputs: ["subjects"], required: [] },
  pre: { inputs: ["subjects"], outputs: ["subjects"], required: ["subjects"] },
  leadfield: { inputs: ["subjects"], outputs: ["subjects", "leadfield"], required: ["subjects"] },
  flex: { inputs: ["subjects", "roi"], outputs: ["subjects", "montages", "roi"], required: ["subjects"] },
  ex: { inputs: ["subjects", "roi", "leadfield"], outputs: ["subjects", "montages", "roi"], required: ["subjects"] },
  mex: { inputs: ["subjects", "roi", "leadfield"], outputs: ["subjects", "montages", "roi"], required: ["subjects"] },
  sim: { inputs: ["subjects", "montages"], outputs: ["subjects", "simulation"], required: ["subjects"] },
  analyzer: { inputs: ["subjects", "simulation", "roi"], outputs: ["subjects"], required: ["subjects"] },
  source: { inputs: ["subjects"], outputs: ["subjects"], required: ["subjects"] },
  stats: { inputs: ["subjects"], outputs: [], required: ["subjects"] },
};

/**
 * What a subject can already have, and what each kind needs of one. Mirrors
 * `tit.pipeline.validate.KIND_READINESS`, and fetched at runtime from `GET /api/pipelines/kinds`;
 * this copy is the offline default so a drag can be judged before the first response.
 *
 * This is the second half of "may this wire be drawn?". The first half is the port *type*, which
 * says what the wire carries and nothing about whether the subjects on it are ready for the
 * target — which is how `Subjects(raw data only) → Analyzer` used to be a graph you could build,
 * submit, and watch fail one job per subject twenty minutes later.
 */
export type Capability = "raw" | "m2m" | "leadfield" | "simulation";

export const CAPABILITY_LABEL: Record<Capability, string> = {
  raw: "raw MRI",
  m2m: "head model",
  leadfield: "leadfield",
  simulation: "simulations",
};

export interface KindReadiness {
  requires: Capability[];
  produces: Capability[];
}

export const READINESS: Record<NodeKind, KindReadiness> = {
  subjects: { requires: [], produces: [] },
  pre: { requires: ["raw"], produces: ["m2m"] },
  leadfield: { requires: ["m2m"], produces: ["leadfield"] },
  flex: { requires: ["m2m"], produces: [] },
  ex: { requires: ["m2m", "leadfield"], produces: [] },
  mex: { requires: ["m2m", "leadfield"], produces: [] },
  sim: { requires: ["m2m"], produces: ["simulation"] },
  analyzer: { requires: ["simulation"], produces: [] },
  source: { requires: ["m2m"], produces: [] },
  stats: { requires: ["simulation"], produces: [] },
};

/** subject id -> what the project says it already has. */
export type Readiness = Record<string, Capability[]>;

/** Palette order — the cohort first, then the workflow. */
export const NODE_KINDS: NodeKind[] = ["subjects", "pre", "leadfield", "flex", "ex", "mex", "sim", "analyzer", "source", "stats"];

export const PORT_LABEL: Record<PortType, string> = {
  subjects: "Subjects",
  montages: "Montage names",
  simulation: "Simulation name",
  roi: "ROI",
  leadfield: "Leadfield",
};

export const KIND_TITLE: Record<NodeKind, string> = {
  subjects: "Subjects",
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
  subjects: Users,
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

/**
 * What each subject reaching *id* has by the time the graph gets there: the project's own facts at
 * the cohort node, plus whatever every node on the way produces. Mirrors
 * `tit.pipeline.validate.capabilities_at`.
 */
export function capabilitiesAt(
  doc: PipelineDoc,
  id: string,
  readiness: Readiness,
  seen = new Set<string>(),
): Record<string, Set<Capability>> {
  const node = nodeById(doc, id);
  if (!node || seen.has(id)) return {};
  seen.add(id);

  const upstream = incoming(doc, id).find((e) => e.port === "subjects")?.from;
  if (upstream === undefined) {
    const out: Record<string, Set<Capability>> = {};
    for (const subject of configSubjects(node.config)) out[subject] = new Set(readiness[subject] ?? []);
    return out;
  }

  const inherited = capabilitiesAt(doc, upstream, readiness, seen);
  const produced = READINESS[nodeById(doc, upstream)?.kind ?? "subjects"]?.produces ?? [];
  const out: Record<string, Set<Capability>> = {};
  for (const [subject, caps] of Object.entries(inherited)) out[subject] = new Set([...caps, ...produced]);
  return out;
}

/**
 * The subjects that are not ready for *kind*, and what each is missing. Mirrors
 * `tit.pipeline.validate.readiness_reason` — including the wording, because the sentence a user
 * sees while dragging has to be the sentence the receipt shows once the wire is there.
 */
export function readinessReason(kind: NodeKind, caps: Record<string, Set<Capability>>): string | null {
  const parts: string[] = [];
  for (const capability of READINESS[kind]?.requires ?? []) {
    const missing = Object.entries(caps)
      .filter(([, have]) => !have.has(capability))
      .map(([subject]) => subject)
      .sort();
    if (!missing.length) continue;
    parts.push(`${missing.join(", ")} ${missing.length === 1 ? "has" : "have"} no ${CAPABILITY_LABEL[capability]}`);
  }
  return parts.length ? parts.join("; ") : null;
}

/**
 * May this wire be drawn? Mirrors `tit.pipeline.validate.can_connect` reason for reason.
 *
 * `readiness` is optional and is what turns the *type* check into the real one: without it a wire
 * is judged only on what it carries, which is the check that let `Subjects(raw) → Analyzer` be
 * drawn at all.
 */
export function canConnect(
  doc: PipelineDoc,
  source: string,
  target: string,
  port: PortType,
  readiness?: Readiness,
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
  if (port === "subjects" && readiness) {
    // Type-legal; the question left is whether these particular subjects have what the target
    // needs. Judged on the graph the drop *would* make, so a chain that produces the missing
    // capability upstream is accepted.
    const hypothetical: PipelineDoc = { ...doc, edges: [...doc.edges, { from: source, to: target, port }] };
    const reason = readinessReason(dst.kind, capabilitiesAt(hypothetical, target, readiness));
    if (reason) return { ok: false, reason };
  }
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
  if (node.kind === "subjects") {
    const ids = configSubjects(node.config);
    if (!ids.length) return "no subjects chosen";
    return ids.length <= 3 ? ids.join(", ") : `${ids.slice(0, 3).join(", ")} +${ids.length - 3}`;
  }

  const parts: string[] = [];
  const subjects = subjectsOf(doc, node.id);
  if (subjects.length) parts.push(`${subjects.length} ${subjects.length === 1 ? "subject" : "subjects"}`);

  // Only a real edge earns the phrase. A node is never configured from the node upstream of it,
  // so "montages from optimizer" is printed when — and only when — that port is actually wired.
  const bound = new Set(incoming(doc, node.id).map((e) => e.port));

  if (node.kind === "sim") {
    if (bound.has("montages")) parts.push("montages from optimizer");
    else {
      const montages = node.config.montages;
      if (Array.isArray(montages) && montages.length) {
        const names = montages.map((m) => String((m as { name?: unknown })?.name ?? "")).filter(Boolean);
        parts.push(names.length ? names.join(", ") : `${montages.length} montages`);
      }
    }
  }
  if (node.kind === "analyzer") {
    if (bound.has("simulation")) parts.push("simulation from Simulator");
    else if (node.config.simulation) parts.push(String(node.config.simulation));
    if (node.config.analysis_type) parts.push(String(node.config.analysis_type));
  }
  if (node.kind === "flex" || node.kind === "ex" || node.kind === "mex") {
    if (node.config.goal) parts.push(String(node.config.goal));
  }
  return parts.join(" · ") || "not configured yet";
}

export function samplePipeline(subject: string): PipelineDoc {
  return {
    version: 1,
    name: "sample",
    nodes: [
      // The cohort, once. Every step after it is configured on its own and handed these subjects.
      { id: "sub1", kind: "subjects", label: "Subjects", config: { subject_ids: [subject] }, position: { x: 0, y: 95 } },
      { id: "pre1", kind: "pre", label: "Head model", config: { create_m2m: true }, position: { x: 260, y: 0 } },
      { id: "flex1", kind: "flex", label: "Find a montage", config: { goal: "mean", postproc: "max_TI" }, position: { x: 260, y: 190 } },
      { id: "sim1", kind: "sim", label: "Simulate it", config: { conductivity: "scalar" }, position: { x: 520, y: 95 } },
      {
        id: "an1",
        kind: "analyzer",
        label: "Measure the ROI",
        config: { space: "mesh", analysis_type: "spherical", center: [0, 0, 0], radius: 5 },
        position: { x: 780, y: 95 },
      },
    ],
    edges: [
      { from: "sub1", to: "pre1", port: "subjects" },
      { from: "sub1", to: "flex1", port: "subjects" },
      { from: "pre1", to: "sim1", port: "subjects" },
      { from: "flex1", to: "sim1", port: "montages" },
      { from: "sim1", to: "an1", port: "subjects" },
      { from: "sim1", to: "an1", port: "simulation" },
    ],
  };
}

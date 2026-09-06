/**
 * The client mirror of `tit/pipeline/{document,validate}.py`.
 *
 * The refusal table below is the **same table** `tests/test_pipeline_graph.py::REFUSALS` asserts on
 * the Python side, case for case and phrase for phrase. That is the point of the file: the canvas
 * refuses a wire without a round trip, so the only thing keeping it from disagreeing with the
 * server about which wire is legal is that both are tested against the same list.
 */
import { describe, expect, it } from "vitest";
import {
  NODE_KINDS,
  PORTS,
  canConnect,
  configSubjects,
  nextNodeId,
  nodeSummary,
  subjectsOf,
  topologicalOrder,
  type NodeKind,
  type PipelineDoc,
  type PortType,
} from "../../src/renderer/pages/pipeline/graph";

function doc(
  nodes: [string, NodeKind, Record<string, unknown>][],
  edges: [string, string, PortType][] = [],
): PipelineDoc {
  return {
    version: 1,
    name: "p",
    nodes: nodes.map(([id, kind, config]) => ({ id, kind, config, position: { x: 0, y: 0 } })),
    edges: edges.map(([from, to, port]) => ({ from, to, port })),
  };
}

const FOUR_NODE = doc(
  [
    ["sub1", "subjects", { subject_ids: ["ernie"] }],
    ["pre1", "pre", { create_m2m: true }],
    ["flex1", "flex", { goal: "mean" }],
    ["sim1", "sim", { montages: [{ name: "M1" }] }],
    ["an1", "analyzer", { space: "mesh", analysis_type: "spherical", radius: 5 }],
  ],
  [
    ["sub1", "pre1", "subjects"],
    ["pre1", "flex1", "subjects"],
    ["pre1", "sim1", "subjects"],
    ["flex1", "sim1", "montages"],
    ["sim1", "an1", "subjects"],
    ["sim1", "an1", "simulation"],
  ],
);

describe("the port table", () => {
  it("gives every node kind inputs, outputs and a required subset of its inputs", () => {
    for (const kind of NODE_KINDS) {
      const ports = PORTS[kind];
      expect(ports).toBeDefined();
      for (const port of ports.required) expect(ports.inputs).toContain(port);
    }
  });
});

describe("canConnect refuses with the same reason the server gives", () => {
  const cases: [string, string, PortType, string][] = [
    ["an1", "sim1", "montages", "does not produce"],
    ["pre1", "an1", "montages", "does not produce"],
    ["an1", "flex1", "montages", "does not produce"],
    ["sim1", "sim1", "subjects", "cannot feed itself"],
    ["pre1", "sim1", "subjects", "already wired"],
  ];
  it.each(cases)("%s -> %s (%s) is refused: %s", (source, target, port, fragment) => {
    const verdict = canConnect(FOUR_NODE, source, target, port);
    expect(verdict.ok).toBe(false);
    if (!verdict.ok) expect(verdict.reason).toContain(fragment);
  });

  it("refuses a wire that would close a cycle", () => {
    const graph = doc(
      [
        ["flex1", "flex", { subject_ids: ["e"] }],
        ["sim1", "sim", { subject_ids: ["e"], montages: [{ name: "M" }] }],
      ],
      [["flex1", "sim1", "montages"]],
    );
    const verdict = canConnect(graph, "sim1", "flex1", "subjects");
    expect(verdict).toEqual({ ok: false, reason: "that would make a cycle" });
  });

  it("allows a legal new wire", () => {
    const graph = doc([
      ["flex1", "flex", { subject_ids: ["e"] }],
      ["sim1", "sim", { subject_ids: ["e"], montages: [{ name: "M" }] }],
    ]);
    expect(canConnect(graph, "flex1", "sim1", "montages")).toEqual({ ok: true });
  });
});

describe("topologicalOrder", () => {
  it("orders the four-node pipeline dependency-first", () => {
    expect(topologicalOrder(FOUR_NODE)).toEqual(["sub1", "pre1", "flex1", "sim1", "an1"]);
  });

  it("returns null for a cycle", () => {
    const graph = doc(
      [
        ["a", "sim", {}],
        ["b", "analyzer", {}],
      ],
      [
        ["a", "b", "subjects"],
        ["b", "a", "subjects"],
      ],
    );
    expect(topologicalOrder(graph)).toBeNull();
  });
});

describe("subjects flow down the graph", () => {
  it("a node with no subjects of its own inherits the wired upstream set", () => {
    expect(subjectsOf(FOUR_NODE, "an1")).toEqual(["ernie"]);
  });

  it("a node's own config wins when nothing is wired", () => {
    expect(configSubjects({ subject_ids: ["a", " b "] })).toEqual(["a", "b"]);
    expect(configSubjects({ subject_id: "solo" })).toEqual(["solo"]);
    expect(configSubjects({})).toEqual([]);
  });

  it("does not hang on a cycle", () => {
    const graph = doc(
      [
        ["a", "sim", {}],
        ["b", "analyzer", {}],
      ],
      [
        ["a", "b", "subjects"],
        ["b", "a", "subjects"],
      ],
    );
    expect(subjectsOf(graph, "a")).toEqual([]);
  });
});

describe("node cards", () => {
  it("say where a bound value comes from rather than showing an empty field", () => {
    // Indices shift by one now that the cohort node leads the document.
    expect(nodeSummary(FOUR_NODE, FOUR_NODE.nodes[3]!)).toContain("montages from optimizer");
    expect(nodeSummary(FOUR_NODE, FOUR_NODE.nodes[4]!)).toContain("simulation from Simulator");
  });

  it("names an unconfigured node honestly", () => {
    // The summary says what the node *has*, not what it is missing: an unbound required input is
    // now a chip on the card (from the server's `missing_input` issues), so repeating "no
    // subjects" in the summary line said the same thing twice and left no room for the config.
    const graph = doc([["sim1", "sim", {}]]);
    expect(nodeSummary(graph, graph.nodes[0]!)).toBe("not configured yet");
  });

  it("summarises what a configured node has, and never mentions what it lacks", () => {
    const graph = doc([["sim1", "sim", { subject_ids: ["ernie", "101"], montages: [{ name: "L_Insula" }] }]]);
    const summary = nodeSummary(graph, graph.nodes[0]!);
    expect(summary).toBe("2 subjects · L_Insula");
    expect(summary).not.toContain("no ");
  });
});

describe("nextNodeId", () => {
  it("never collides with an id already on the canvas", () => {
    const graph = doc([
      ["sim1", "sim", {}],
      ["sim2", "sim", {}],
    ]);
    expect(nextNodeId(graph, "sim")).toBe("sim3");
  });
});


describe("the readiness table gates a subjects wire, with the same sentence as the server", () => {
  // The same project `tests/test_pipeline_readiness.py` uses: ernie is finished, 102 and test have
  // been converted and nothing else.
  const PROJECT = {
    ernie: ["raw", "m2m", "simulation"],
    "102": ["raw"],
    test: ["raw"],
  } as const;

  const cohort = (...ids: string[]): [string, NodeKind, Record<string, unknown>] => [
    "s1",
    "subjects",
    { subject_ids: ids },
  ];

  it("lets raw-only subjects reach Pre-processing and nothing else", () => {
    for (const [kind, accepted] of [
      ["pre", true],
      ["sim", false],
      ["flex", false],
      ["analyzer", false],
      ["leadfield", false],
    ] as [NodeKind, boolean][]) {
      const graph = doc([cohort("102", "test"), ["n1", kind, {}]]);
      expect(canConnect(graph, "s1", "n1", "subjects", PROJECT as never).ok).toBe(accepted);
    }
  });

  it("names the subjects that are not ready, and only those", () => {
    const graph = doc([cohort("ernie", "102", "test"), ["a1", "analyzer", {}]]);
    const verdict = canConnect(graph, "s1", "a1", "subjects", PROJECT as never);
    expect(verdict.ok).toBe(false);
    if (!verdict.ok) {
      expect(verdict.reason).toBe("102, test have no simulations");
      expect(verdict.reason).not.toContain("ernie");
    }
  });

  it("says 'has' for one subject and 'have' for several", () => {
    const one = doc([cohort("ernie", "102"), ["m1", "sim", {}]]);
    const verdict = canConnect(one, "s1", "m1", "subjects", PROJECT as never);
    expect(verdict.ok).toBe(false);
    if (!verdict.ok) expect(verdict.reason).toBe("102 has no head model");
  });

  it("accepts a wire whose missing capability is produced upstream", () => {
    // Subjects(raw) -> Pre -> Simulator: `pre` makes the head model the Simulator needs, so by the
    // time the wire reaches it those subjects have one. This is the whole point of `produces`.
    const graph = doc(
      [cohort("102"), ["p1", "pre", {}], ["m1", "sim", {}]],
      [["s1", "p1", "subjects"]],
    );
    expect(canConnect(graph, "p1", "m1", "subjects", PROJECT as never).ok).toBe(true);
    // ...and the same Simulator wired straight to the cohort is still refused.
    expect(canConnect(graph, "s1", "m1", "subjects", PROJECT as never).ok).toBe(false);
  });

  it("checks shape only when the project's readiness is not known yet", () => {
    const graph = doc([cohort("102"), ["m1", "sim", {}]]);
    expect(canConnect(graph, "s1", "m1", "subjects").ok).toBe(true);
    expect(canConnect(graph, "s1", "m1", "subjects", PROJECT as never).ok).toBe(false);
  });

  it("gives a subject the project has never heard of nothing", () => {
    const graph = doc([cohort("ghost"), ["m1", "sim", {}]]);
    const verdict = canConnect(graph, "s1", "m1", "subjects", PROJECT as never);
    expect(verdict.ok).toBe(false);
    if (!verdict.ok) expect(verdict.reason).toBe("ghost has no head model");
  });
});

describe("a node card states what it has, never what the node upstream configured", () => {
  it("prints the cohort's own subjects on the cohort node", () => {
    const graph = doc([["s1", "subjects", { subject_ids: ["ernie", "102"] }]]);
    expect(nodeSummary(graph, graph.nodes[0]!)).toBe("ernie, 102");
  });

  it("counts the subjects that reach a processing node", () => {
    const graph = doc(
      [
        ["s1", "subjects", { subject_ids: ["ernie", "102"] }],
        ["m1", "sim", { montages: [{ name: "L_Insula" }] }],
      ],
      [["s1", "m1", "subjects"]],
    );
    expect(nodeSummary(graph, graph.nodes[1]!)).toBe("2 subjects · L_Insula");
  });

  it("says 'montages from optimizer' only when that port is actually wired", () => {
    const unwired = doc([
      ["s1", "subjects", { subject_ids: ["ernie"] }],
      ["m1", "sim", {}],
    ]);
    expect(nodeSummary(unwired, unwired.nodes[1]!)).not.toContain("from optimizer");

    const wired = doc(
      [
        ["s1", "subjects", { subject_ids: ["ernie"] }],
        ["f1", "flex", { goal: "mean" }],
        ["m1", "sim", {}],
      ],
      [
        ["s1", "m1", "subjects"],
        ["f1", "m1", "montages"],
      ],
    );
    expect(nodeSummary(wired, wired.nodes[2]!)).toContain("montages from optimizer");
  });
});

import { expect, it } from "vitest";
import { expandAnalysisTargets } from "../../src/renderer/pages/pipeline/expandAnalysis";
import type { PipelineDoc } from "../../src/renderer/pages/pipeline/graph";

it("keeps target inputs and makes downstream jobs wait for every analysis", () => {
  const doc: PipelineDoc = { version: 1, name: "targets", nodes: [
    { id: "sim", kind: "sim", config: {}, position: { x: 0, y: 0 } },
    { id: "an", kind: "analyzer", config: { radius: 5 }, position: { x: 300, y: 0 } },
    { id: "stats", kind: "stats", config: {}, position: { x: 600, y: 0 } },
  ], edges: [{ from: "sim", to: "an", port: "subjects" }, { from: "sim", to: "an", port: "simulation" }, { from: "an", to: "stats", port: "subjects" }] };
  const configs = [{ center: [1, 2, 3], radius: 5 }, { center: [4, 5, 6], radius: 8 }];
  const next = expandAnalysisTargets(doc, "an", configs);
  const other = next.nodes.find((node) => node.kind === "analyzer" && node.id !== "an")!;
  expect(next.nodes.find((node) => node.id === "an")!.config).toEqual(configs[0]);
  expect(other.config).toEqual(configs[1]);
  expect(next.edges).toContainEqual({ from: "an", to: other.id, port: "subjects" });
  expect(next.edges).toContainEqual({ from: "sim", to: other.id, port: "simulation" });
  expect(next.edges).toContainEqual({ from: other.id, to: "stats", port: "subjects" });
  expect(next.edges).not.toContainEqual({ from: "an", to: "stats", port: "subjects" });
  expect(doc.nodes).toHaveLength(3);
  expect(doc.nodes[1]!.config).toEqual({ radius: 5 });
});

import { nextNodeId, type PipelineDoc } from "./graph";

/** Each target is an ordinary Analyzer job; downstream steps wait for all targets. */
export function expandAnalysisTargets(doc: PipelineDoc, nodeId: string, configs: Record<string, unknown>[]): PipelineDoc {
  const source = doc.nodes.find((node) => node.id === nodeId);
  if (!source || source.kind !== "analyzer" || configs.length < 2) return doc;
  const nodes = doc.nodes.map((node) => node.id === nodeId ? { ...node, config: configs[0]! } : node);
  const extraInputs = doc.edges.filter((edge) => edge.to === nodeId && edge.port !== "subjects");
  const addedEdges: PipelineDoc["edges"] = [];
  let previous = nodeId;
  for (let index = 1; index < configs.length; index++) {
    const id = nextNodeId({ ...doc, nodes }, "analyzer");
    nodes.push({ ...source, id, label: `${source.label || "Analyzer"} · target ${index + 1}`, config: configs[index]!, position: { x: source.position.x, y: source.position.y + index * 150 } });
    addedEdges.push({ from: previous, to: id, port: "subjects" }, ...extraInputs.map((edge) => ({ ...edge, to: id })));
    previous = id;
  }
  return { ...doc, nodes, edges: [...doc.edges.map((edge) => edge.from === nodeId ? { ...edge, from: previous } : edge), ...addedEdges] };
}

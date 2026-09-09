/** Saved flags cannot authorize replacement; only independently planned destinations enable it. */
import { describe, expect, it, vi } from "vitest";
import { api } from "../../src/renderer/api/client";
import { pipelineWithOverwrite, planPipelineOutputs, runPipeline } from "../../src/renderer/pages/pipeline/api";
import type { PipelineDoc } from "../../src/renderer/pages/pipeline/graph";

const doc: PipelineDoc = {
  version: 1, name: "fixture", edges: [], nodes: [
    { id: "source", kind: "source", position: { x: 0, y: 0 }, config: { subject_ids: ["ernie"], forward: { overwrite: true } } },
    { id: "pre", kind: "pre", position: { x: 1, y: 0 }, config: { subject_ids: ["ernie"], replace_existing_outputs: true, skip_existing_outputs: false } },
  ],
};

function clientWith(body: unknown, ok = true) {
  const POST = vi.fn().mockResolvedValue({ data: body, response: { ok, status: ok ? 200 : 422 } });
  return { client: { POST } as unknown as typeof api, POST };
}

describe("pipeline overwrite policy", () => {
  it("clears saved nested replacement flags for a normal run without mutating the canvas", async () => {
    const { client, POST } = clientWith({ group_id: "g", jobs: [] });
    await runPipeline(doc, 1, {}, client);
    const submitted = POST.mock.calls[0]?.[1].body.pipeline;
    expect(submitted.nodes[0].config.forward.overwrite).toBe(false);
    expect(submitted.nodes[1].config).toMatchObject({ replace_existing_outputs: false, skip_existing_outputs: true });
    expect(doc.nodes[0]?.config.forward).toEqual({ overwrite: true });
    expect(POST.mock.calls[0]?.[1].body.overwrite).toBeUndefined();
  });

  it("clears coercible saved flags too", () => {
    const saved: PipelineDoc = { ...doc, nodes: [{ ...doc.nodes[0]!, config: { overwrite: "true", replace_existing_outputs: 1, skip_existing_outputs: 0 } }] };
    expect(pipelineWithOverwrite(saved, false).nodes[0]?.config).toEqual({ overwrite: false, replace_existing_outputs: false, skip_existing_outputs: true });
  });

  it("allows replacement only through the current explicit decision", () => {
    expect(pipelineWithOverwrite(doc, true).nodes[1]?.config).toMatchObject({ replace_existing_outputs: true, skip_existing_outputs: false });
  });

  it("counts existing outputs from server plans without inventing output paths", async () => {
    const { client, POST } = clientWith({ jobs: [{ exists: true }, { exists: false }] });
    expect(await planPipelineOutputs(doc, client)).toEqual({ existing: 2, total: 4, complete: true });
    expect(POST).toHaveBeenCalledTimes(2);
    expect(POST.mock.calls[0]?.[1].body.subject_ids).toEqual(["ernie"]);
    expect(POST.mock.calls[0]?.[1].body.overwrite).toBe(false);
  });

  it("marks runtime bindings incomplete and never guesses their paths", async () => {
    const { client, POST } = clientWith({ jobs: [{ exists: true }] });
    const dynamic: PipelineDoc = { ...doc, edges: [{ from: "pre", to: "source", port: "simulation" }] };
    expect(await planPipelineOutputs(dynamic, client)).toEqual({ existing: 1, total: 1, complete: false });
    expect(POST).toHaveBeenCalledTimes(1);
  });

  it("does not claim a complete preview if a node cannot be planned", async () => {
    const { client } = clientWith(undefined, false);
    expect(await planPipelineOutputs(doc, client)).toEqual({ existing: 0, total: 0, complete: false });
  });
});

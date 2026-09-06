/**
 * `/api/pipelines*` — the only place the canvas talks to the server.
 *
 * Everything here goes through the generated contract types, so a schema change breaks the build
 * rather than a screen. Note what is *not* here: there is no per-node submit. Running a pipeline
 * is one `POST /api/pipelines/run`, which is one `submit_plan` on the server, which is one job
 * group — the whole point of D2.
 */
import { api, unwrap, ApiError } from "../../api/client";
import type { components } from "../../api/schema";
import type { PipelineDoc } from "./graph";

export type PipelineValidation = components["schemas"]["PipelineValidation"];
export type PipelineIssue = components["schemas"]["PipelineIssue"];
export type PipelineJobPreview = components["schemas"]["PipelineJobPreview"];
export type PipelineRunResult = components["schemas"]["PipelineRunResult"];
export type PipelineListEntry = components["schemas"]["PipelineListEntry"];
export type PipelineKinds = components["schemas"]["PipelineKinds"];

type WirePipeline = components["schemas"]["Pipeline"];

/** The canvas document as the contract spells it (our `PipelineDoc` is the same shape, narrowed). */
const wire = (doc: PipelineDoc): WirePipeline => doc as unknown as WirePipeline;

export async function getPipelineKinds(client = api): Promise<PipelineKinds> {
  return unwrap(await client.GET("/api/pipelines/kinds"), "/api/pipelines/kinds");
}

export async function listPipelines(client = api): Promise<PipelineListEntry[]> {
  return unwrap(await client.GET("/api/pipelines"), "/api/pipelines");
}

export async function loadPipeline(name: string, client = api): Promise<PipelineDoc> {
  const loaded = unwrap(
    await client.GET("/api/pipelines/{name}", { params: { path: { name } } }),
    `/api/pipelines/${name}`,
  );
  return loaded as unknown as PipelineDoc;
}

export async function savePipeline(name: string, doc: PipelineDoc, client = api): Promise<void> {
  unwrap(
    await client.PUT("/api/pipelines/{name}", { params: { path: { name } }, body: wire(doc) }),
    `/api/pipelines/${name}`,
  );
}

export async function deletePipeline(name: string, client = api): Promise<void> {
  const { response } = await client.DELETE("/api/pipelines/{name}", { params: { path: { name } } });
  if (!response.ok) throw new ApiError(response.status, `/api/pipelines/${name}`);
}

export async function validatePipeline(doc: PipelineDoc, client = api): Promise<PipelineValidation> {
  return unwrap(await client.POST("/api/pipelines/validate", { body: wire(doc) }), "/api/pipelines/validate");
}

export async function runPipeline(
  doc: PipelineDoc,
  parallelSubjects: number,
  options: { overwrite?: boolean; tags?: string[] } = {},
  client = api,
): Promise<PipelineRunResult> {
  const result = await client.POST("/api/pipelines/run", {
    body: {
      pipeline: wire(doc),
      parallel_subjects: Math.max(1, parallelSubjects),
      ...(options.overwrite ? { overwrite: true } : {}),
      ...(options.tags?.length ? { tags: options.tags } : {}),
    },
  });
  return unwrap(result, "/api/pipelines/run");
}

/**
 * The notebook, as `.ipynb` text. `openapi-fetch` parses `text/plain` for us, but the generated
 * type for a `text/plain` body is `string`, so this returns exactly what the file should contain.
 */
export async function exportNotebook(doc: PipelineDoc, client = api): Promise<string> {
  const result = await client.POST("/api/pipelines/export", {
    params: { query: { format: "ipynb" } },
    body: wire(doc),
    parseAs: "text",
  });
  if (!result.response.ok) throw new ApiError(result.response.status, "/api/pipelines/export");
  return (result.data as unknown as string) ?? "";
}

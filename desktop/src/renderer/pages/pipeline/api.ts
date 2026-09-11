/**
 * Canvas pipeline requests and project notebook export storage.
 *
 * Everything here goes through the generated contract types, so a schema change breaks the build
 * rather than a screen. Note what is *not* here: there is no per-node submit. Running a pipeline
 * is one `POST /api/pipelines/run`, which is one `submit_plan` on the server, which is one job
 * group — the whole point of D2.
 */
import { api, unwrap, ApiError } from "../../api/client";
import type { components } from "../../api/schema";
import { subjectsOf, type PipelineDoc } from "./graph";

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

/** Apply this press's decision to nested runner flags, never a saved destructive default. */
export function pipelineWithOverwrite(doc: PipelineDoc, overwrite: boolean): PipelineDoc {
  function config(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(config);
    if (!value || typeof value !== "object") return value;
    return Object.fromEntries(Object.entries(value).map(([key, field]) => [key,
      ["overwrite", "replace_existing_outputs"].includes(key) ? overwrite
        : key === "skip_existing_outputs" ? !overwrite : config(field),
    ]));
  }
  return { ...doc, nodes: doc.nodes.map((node) => ({ ...node, config: config(node.config) as Record<string, unknown> })) };
}

/** Only the server resolves output paths. Dynamic input bindings cannot be previewed here. */
export async function planPipelineOutputs(doc: PipelineDoc, client = api): Promise<{ existing: number; total: number; complete: boolean }> {
  let existing = 0;
  let total = 0;
  let complete = true;
  for (const node of doc.nodes) {
    if (node.kind === "subjects") continue;
    if (doc.edges.some((edge) => edge.to === node.id && edge.port !== "subjects")) { complete = false; continue; }
    const result = await client.POST("/api/plan/{kind}", {
      params: { path: { kind: node.kind } },
      body: { config: node.config as components["schemas"]["PipelineConfig"], subject_ids: subjectsOf(doc, node.id), overwrite: false },
    });
    if (!result.response.ok || !result.data) { complete = false; continue; }
    existing += result.data.jobs.filter((job) => job.exists).length;
    total += result.data.jobs.length;
  }
  return { existing, total, complete };
}

export async function runPipeline(
  doc: PipelineDoc,
  parallelSubjects: number,
  options: { overwrite?: boolean; tags?: string[] } = {},
  client = api,
): Promise<PipelineRunResult> {
  const result = await client.POST("/api/pipelines/run", {
    body: {
      pipeline: wire(pipelineWithOverwrite(doc, options.overwrite === true)),
      parallel_subjects: Math.max(1, parallelSubjects),
      ...(options.overwrite ? { overwrite: true } : {}),
      ...(options.tags?.length ? { tags: options.tags } : {}),
    },
  });
  if (!result.response.ok) {
    const detail = (result.error as { detail?: unknown } | undefined)?.detail;
    let message: string | undefined;
    if (typeof detail === "string") message = detail;
    else if (detail && typeof detail === "object") {
      const problem = detail as { message?: unknown; issues?: { message?: unknown }[] };
      const issues = Array.isArray(problem.issues) ? problem.issues.map((issue) => issue.message).filter((value): value is string => typeof value === "string") : [];
      message = issues.length ? issues.join("; ") : typeof problem.message === "string" ? problem.message : undefined;
    }
    throw new ApiError(result.response.status, "/api/pipelines/run", message);
  }
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

/** Store exports alongside the project's other notebooks, without replacing user edits. */
export async function exportNotebookToProject(doc: PipelineDoc, client = api): Promise<string> {
  const content = JSON.parse(await exportNotebook(doc, client)) as Record<string, never>;
  const listing = unwrap(await client.GET("/api/notebooks"), "/api/notebooks");
  const existing = new Set(listing.notebooks.map((entry) => entry.name));
  const base = (doc.name || "pipeline").replace(/[^A-Za-z0-9 ._-]/g, "-").replace(/^[^A-Za-z0-9]+/, "").slice(0, 110) || "pipeline";
  let name = `${base}.ipynb`;
  let suffix = 2;
  while (existing.has(name)) name = `${base}-${suffix++}.ipynb`;
  const saved = unwrap(await client.POST("/api/notebooks", { body: { name, content } }), "/api/notebooks");
  return saved.name;
}

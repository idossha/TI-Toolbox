/**
 * The example-data catalogue, and the job that installs one sample.
 *
 * `GET /api/project/example-data` answers the four samples `tit/examples/catalog.json` lists with a
 * per-sample `installed`/`bytes` read off the project's disk (no network), and `POST` submits a
 * `project_init` job running `tit.examples.fetch` — the download happens in the container, which is
 * where the project is, never in Electron main.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type ExampleSample = components["schemas"]["ExampleDataSample"];
export type ExampleStatus = components["schemas"]["ExampleDataStatus"];
export type ExampleCatalog = components["schemas"]["ExampleDataCatalog"];

export const EXAMPLE_DATA_QUERY_KEY = ["example-data"] as const;

export async function getExampleData(): Promise<ExampleCatalog> {
  return unwrap(await api.GET("/api/project/example-data"), "/api/project/example-data");
}

export async function startExampleData(sampleId: string): Promise<{ id: string }> {
  return unwrap(
    await api.POST("/api/project/example-data", { body: { sample_id: sampleId } }),
    "/api/project/example-data",
  );
}

/** `627045804` → `627 MB`; a sample is never small enough for kB to be the useful unit. */
export function formatBytes(n: number): string {
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} kB`;
  const mb = n / (1024 * 1024);
  return mb < 1024 ? `${Math.round(mb)} MB` : `${(mb / 1024).toFixed(1)} GB`;
}

/** The tag a row carries: what the sample lets you do the moment it lands. */
export function layoutTag(layout: string): string {
  return layout === "headmodel" ? "ready to simulate" : "needs pre-processing";
}

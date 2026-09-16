/**
 * The example-data catalogue, and starting the download of one sample.
 *
 * **Not a job.** `GET /api/example-data` answers the samples `tit/examples/catalog.json` lists with
 * a per-sample `installed`/`bytes` read off the project's disk *and* the live progress of whichever
 * sample is downloading right now; `POST /api/example-data/{id}` starts one on a background thread
 * in the container — which is where the project is, never in Electron main — and returns at once.
 * Progress therefore comes from polling this one endpoint, not from the `/ws/jobs` stream: a
 * download is not a pipeline, and wiring it as a `project_init` job made asking an established
 * project for a sample reprint the initializer's "New project detected" banner.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type ExampleSample = components["schemas"]["ExampleDataSample"];
export type ExampleStatus = components["schemas"]["ExampleDataStatus"];
export type ExampleCatalog = components["schemas"]["ExampleDataCatalog"];

export const EXAMPLE_DATA_QUERY_KEY = ["example-data"] as const;

/** How often the catalogue is re-read while a download is in flight. */
export const EXAMPLE_DATA_POLL_MS = 1000;

export async function getExampleData(): Promise<ExampleCatalog> {
  return unwrap(await api.GET("/api/example-data"), "/api/example-data");
}

export async function startExampleData(sampleId: string): Promise<ExampleStatus> {
  return unwrap(
    await api.POST("/api/example-data/{sample_id}", { params: { path: { sample_id: sampleId } } }),
    "/api/example-data/{sample_id}",
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

/** The line a downloading row shows: `42% · 265 MB / 627 MB`, or `Starting…` before any bytes. */
export function progressText(status: ExampleStatus | undefined): string | undefined {
  if (!status?.downloading) return undefined;
  if (!status.total) return "Starting…";
  const pct = Math.min(100, Math.round((status.received / status.total) * 100));
  return `${pct}% · ${formatBytes(status.received)} / ${formatBytes(status.total)}`;
}

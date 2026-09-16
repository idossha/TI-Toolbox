/**
 * The example-data catalogue, and starting the download of one **part**.
 *
 * **Not a job.** `GET /api/example-data` answers the datasets `tit/examples/catalog.json` lists —
 * each with its independently downloadable parts — plus a per-part `installed`/`bytes` read off the
 * project's disk *and* the live progress of whichever part is downloading right now;
 * `POST /api/example-data/{dataset}/{part}` starts one on a background worker in the container —
 * which is where the project is, never in Electron main — and returns at once, queueing it behind
 * anything already in flight. Progress therefore comes from polling this one endpoint, not from the
 * `/ws/jobs` stream: a download is not a pipeline, and wiring it as a `project_init` job made asking
 * an established project for a sample reprint the initializer's "New project detected" banner.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type ExampleDataset = components["schemas"]["ExampleDataset"];
export type ExamplePart = components["schemas"]["ExampleDataPart"];
export type ExampleStatus = components["schemas"]["ExampleDataStatus"];
export type ExampleCatalog = components["schemas"]["ExampleDataCatalog"];

export const EXAMPLE_DATA_QUERY_KEY = ["example-data"] as const;

/** How often the catalogue is re-read while a download is in flight. */
export const EXAMPLE_DATA_POLL_MS = 1000;

export async function getExampleData(): Promise<ExampleCatalog> {
  return unwrap(await api.GET("/api/example-data"), "/api/example-data");
}

/** `partId` is the catalogue's own `dataset/part` id, e.g. `ernie/headmodel`. */
export async function startExampleData(partId: string, force = false): Promise<ExampleStatus> {
  const [dataset_id, part_id] = splitPartId(partId);
  return unwrap(
    await api.POST("/api/example-data/{dataset_id}/{part_id}", {
      params: { path: { dataset_id, part_id }, query: force ? { force: true } : undefined },
    }),
    "/api/example-data/{dataset_id}/{part_id}",
  );
}

/** `"ernie/headmodel"` → `["ernie", "headmodel"]`. */
export function splitPartId(partId: string): [string, string] {
  const at = partId.indexOf("/");
  return at < 0 ? [partId, ""] : [partId.slice(0, at), partId.slice(at + 1)];
}

/** `627045804` → `598 MB`; a part is never small enough for kB to be the useful unit. */
export function formatBytes(n: number): string {
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} kB`;
  const mb = n / (1024 * 1024);
  return mb < 1024 ? `${Math.round(mb)} MB` : `${(mb / 1024).toFixed(1)} GB`;
}

/**
 * The slim caption under a downloading row's bar: `433 / 455 MB` — one unit, named once, so the
 * eye compares two numbers rather than parsing two labels. No percentage: the bar is the
 * percentage, and `95% · 433 MB / 455 MB` in a grey box said the same thing three times.
 */
export function progressText(status: ExampleStatus | undefined): string | undefined {
  if (!status) return undefined;
  if (status.queued) return "Queued";
  if (!status.downloading) return undefined;
  if (!status.total) return "Starting…";
  const unit = formatBytes(status.total).split(" ")[1];
  const scale = unit === "GB" ? 1024 ** 3 : unit === "MB" ? 1024 ** 2 : 1024;
  const round = (n: number) => (unit === "GB" ? (n / scale).toFixed(1) : Math.round(n / scale));
  return `${round(Math.min(status.received, status.total))} / ${round(status.total)} ${unit}`;
}

/** 0–100 for the bar, or `undefined` while the total is still unknown (an indeterminate bar). */
export function progressPercent(status: ExampleStatus | undefined): number | undefined {
  if (!status?.downloading || !status.total) return undefined;
  return Math.min(100, Math.round((status.received / status.total) * 100));
}

/** True while this part occupies the worker or its queue — the row shows a bar, not a button. */
export function isBusy(status: ExampleStatus | undefined): boolean {
  return status?.downloading === true || status?.queued === true;
}

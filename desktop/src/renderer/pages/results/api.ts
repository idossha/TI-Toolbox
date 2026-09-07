/**
 * Page-scoped API calls for the Results screen. Kept local rather than added to the shared
 * `api/client.ts` (owned across many pages) — see PARITY.md and the final report. Mirrors the
 * pattern in `pages/simulator/api.ts` and `pages/viewer/api.ts`.
 *
 * v3 (D3, `docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)`): `launchFreeview`/`launchGmsh` and the
 * `kind=custom` ViewSpec fetch that fed them are gone — `POST /api/viewers/{freeview,gmsh}` no
 * longer exists (no X11 in this runtime) and "Open in viewer" is an in-app navigation to
 * `/viewer`, not a server call. Nothing in this module launches anything any more.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type SimulationDetail = components["schemas"]["SimulationDetail"];
export type FlexRun = components["schemas"]["FlexRun"];
export type ExRun = components["schemas"]["ExRun"];
export type Artifact = components["schemas"]["Artifact"];
export type Analysis = components["schemas"]["Analysis"];
export type Report = components["schemas"]["Report"];
export type GroupCatalog = components["schemas"]["GroupCatalog"];
export type TableData = components["schemas"]["TableData"];

export async function getSimulationsFor(subject: string): Promise<SimulationDetail[]> {
  return unwrap(await api.GET("/api/catalog/simulations", { params: { query: { subject } } }), "/api/catalog/simulations").simulations;
}

export async function getFlexRuns(subject: string): Promise<FlexRun[]> {
  return unwrap(await api.GET("/api/catalog/flex-runs", { params: { query: { subject } } }), "/api/catalog/flex-runs");
}

export async function getExRuns(subject: string, kind: "ex" | "mex"): Promise<ExRun[]> {
  return unwrap(await api.GET("/api/catalog/ex-runs", { params: { query: { subject, kind } } }), "/api/catalog/ex-runs");
}

export async function getExRunResults(run: string, subject: string, kind: "ex" | "mex"): Promise<TableData> {
  return unwrap(
    await api.GET("/api/catalog/ex-runs/{run}/results", { params: { path: { run }, query: { subject, kind } } }),
    `/api/catalog/ex-runs/${run}/results`,
  );
}

export async function getAnalyses(subject: string, simulation: string): Promise<Analysis[]> {
  return unwrap(await api.GET("/api/catalog/analyses", { params: { query: { subject, simulation } } }), "/api/catalog/analyses");
}

export async function getAnalysisSummary(name: string, subject: string, simulation: string): Promise<TableData> {
  return unwrap(
    await api.GET("/api/catalog/analyses/{name}/summary", { params: { path: { name }, query: { subject, simulation } } }),
    `/api/catalog/analyses/${name}/summary`,
  );
}

export async function getReports(subject: string): Promise<Report[]> {
  return unwrap(await api.GET("/api/catalog/reports", { params: { query: { subject } } }), "/api/catalog/reports");
}

export async function getGroupCatalog(): Promise<GroupCatalog> {
  return unwrap(await api.GET("/api/catalog/group"), "/api/catalog/group");
}

/** Artifact route URL, used directly as an <iframe>/<embed>/<a> src — the browser sends the
 * session cookie on a normal navigation, so no fetch/credentials wiring is needed here. */
export function artifactUrl(path: string): string {
  return `/api/files/artifact?path=${encodeURIComponent(path)}`;
}

export function reportUrl(id: string): string {
  return `/api/files/report/${encodeURIComponent(id)}`;
}

/**
 * One small text/JSON file inside the project jail, through `GET /api/files/text`
 * (`tit/server/routes/files.py::text`) — the route that already exists for log tails and is not
 * restricted to an extension allow-list.
 *
 * This is how U14's preview reads the three run manifests the catalog does not inline:
 * `<simulation>/documentation/config.json`, a flex run's `summary.txt` and its
 * `electrode_positions.json`, and an ex/mEx run's `run_config.json`. `/api/files/raw` would also
 * serve them, but it needs the file's absolute path *in the URL* and returns opaque bytes; this
 * route returns the text and is the one the rest of the app already speaks.
 *
 * Written with `fetch` rather than the typed client for the same reason `pages/_shared/run/
 * logCatalog.ts` is: the response is `text/plain`, not JSON, so `openapi-fetch` would have to be
 * told to skip its own parsing on every call.
 */
export async function getTextFile(path: string): Promise<string> {
  const res = await fetch(`/api/files/text?path=${encodeURIComponent(path)}`, {
    credentials: "same-origin",
    headers: { accept: "text/plain" },
  });
  if (!res.ok) throw new Error(`GET /api/files/text (${path}) failed with HTTP ${res.status}`);
  return res.text();
}

/** One group-statistics run's detail — its inputs, its outcome, its cluster table and its files. */
export interface GroupStatsDetail {
  type: string;
  name: string;
  path: string;
  created: string;
  /** `"ok"` once the run wrote something besides its log; `"empty"` when it did not. */
  status: "ok" | "empty";
  /** Why an `empty` run produced nothing — the log's own ERROR line where there is one. */
  reason: string | null;
  config: { label: string; value: string }[];
  results: { label: string; value: string }[];
  groups: { name: string; n: number; subjects: string[] }[];
  image_shape: string | null;
  clusters: TableData | null;
  log: string | null;
  artifacts: Artifact[];
}

/**
 * `GET /api/catalog/group/stats/{name}?type=` (`tit/catalog.py::group_stats_detail`).
 *
 * Read with `fetch` rather than the typed client for the reason `getTextFile` below is: the route
 * is newer than the checked-in `contracts/generated/openapi.json`, and regenerating that file —
 * and `api/schema.d.ts` with it — touches contracts another lane owns. The response shape is
 * pinned by `GroupStatsDetail` above and by the catalog's own pytest.
 */
export async function getGroupStats(type: string, name: string): Promise<GroupStatsDetail> {
  const res = await fetch(
    `/api/catalog/group/stats/${encodeURIComponent(name)}?type=${encodeURIComponent(type)}`,
    { credentials: "same-origin", headers: { accept: "application/json" } },
  );
  if (!res.ok) throw new Error(`GET /api/catalog/group/stats/${name} failed with HTTP ${res.status}`);
  return (await res.json()) as GroupStatsDetail;
}

/**
 * The pictures a simulation run saved of itself — today the montage visualisation
 * `tit.tools.montage_visualizer` writes as
 * `<sim>/<TI|mTI>/montage_imgs/<name>_highlighted_visualization.png`.
 *
 * A separate read rather than a field on `SimulationDetail`, and read with `fetch` rather than the
 * typed client, for the reason `getGroupStats` above is: `/api/catalog/simulations` has a Pydantic
 * `response_model` generated from the frozen v1 contract, so a new field there is a contract
 * change owned by another lane.
 */
export async function getSimulationFigures(subject: string, name: string): Promise<Artifact[]> {
  const res = await fetch(
    `/api/catalog/simulations/${encodeURIComponent(name)}/figures?subject=${encodeURIComponent(subject)}`,
    { credentials: "same-origin", headers: { accept: "application/json" } },
  );
  if (!res.ok) throw new Error(`GET /api/catalog/simulations/${name}/figures failed with HTTP ${res.status}`);
  return (await res.json()) as Artifact[];
}

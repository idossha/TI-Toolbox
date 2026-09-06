/**
 * Typed wrappers for the endpoints the Analyzer page needs beyond what `api/client.ts` already
 * exports (getSubjects/getSimulations/version/capabilities). Deliberately local to this page
 * rather than added to the shared client — many pages need many different catalog endpoints in
 * parallel and `api/client.ts` has no declared owner in the build plan's ownership map, so adding
 * to it risks colliding with other lanes' concurrent edits. These call the same shared `api`
 * (openapi-fetch) instance and reuse its `unwrap`/`ApiError`, just typed from the generated
 * `schema.d.ts` directly.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Atlas = components["schemas"]["Atlas"];
export type Region = components["schemas"]["Region"];
export type Analysis = components["schemas"]["Analysis"];
export type TableData = components["schemas"]["TableData"];
export type PlanResult = components["schemas"]["PlanResult"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type ViewSpec = components["schemas"]["ViewSpec"];
export type AnalyzerConfig = components["schemas"]["AnalyzerConfig"];
export type SimulationDetail = components["schemas"]["SimulationDetail"];

/**
 * `api/client.ts`'s own `getSimulations()` is typed `Promise<Simulation[]>` (the v0 base shape) —
 * stale against the v1 `SimulationList` response it actually unwraps (`SimulationDetail[]`,
 * carrying `fields`/`montages`/`space`/etc.). Rather than edit that shared, unowned file (risking
 * a collision with whichever lane gets to it first — reported as a gap), this calls the same
 * endpoint typed correctly from `schema.d.ts` directly.
 */
export async function getSimulationDetails(
  subject: string,
  client = api,
): Promise<SimulationDetail[]> {
  const result = unwrap(
    await client.GET("/api/catalog/simulations", {
      params: { query: { subject } },
    }),
    "/api/catalog/simulations",
  );
  return result.simulations;
}

export async function getAtlases(
  subject: string,
  opts: { space?: "subject" | "mni"; kind?: "cortical" | "subcortical" } = {},
  client = api,
): Promise<Atlas[]> {
  return unwrap(
    await client.GET("/api/catalog/atlases", {
      params: { query: { subject, ...opts } },
    }),
    "/api/catalog/atlases",
  );
}

export async function getAtlasRegions(
  subject: string,
  atlas: string,
  hemi?: "lh" | "rh" | "both",
  client = api,
): Promise<Region[]> {
  return unwrap(
    await client.GET("/api/catalog/atlases/regions", {
      params: { query: { subject, atlas, hemi } },
    }),
    "/api/catalog/atlases/regions",
  );
}

export async function getAnalyses(
  subject: string,
  simulation: string,
  client = api,
): Promise<Analysis[]> {
  return unwrap(
    await client.GET("/api/catalog/analyses", {
      params: { query: { subject, simulation } },
    }),
    "/api/catalog/analyses",
  );
}

export async function getAnalysisSummary(
  name: string,
  subject: string,
  simulation: string,
  client = api,
): Promise<TableData> {
  return unwrap(
    await client.GET("/api/catalog/analyses/{name}/summary", {
      params: { path: { name }, query: { subject, simulation } },
    }),
    "/api/catalog/analyses/{name}/summary",
  );
}

export async function validateAnalyzerConfig(
  config: AnalyzerConfig,
  client = api,
): Promise<ValidateResult> {
  return unwrap(
    await client.POST("/api/validate/{kind}", {
      params: { path: { kind: "analyzer" } },
      body: { config },
    }),
    "/api/validate/{kind}",
  );
}

export async function planAnalyzer(
  config: AnalyzerConfig,
  subjectIds: string[],
  overwrite: boolean,
  client = api,
): Promise<PlanResult> {
  return unwrap(
    await client.POST("/api/plan/{kind}", {
      params: { path: { kind: "analyzer" } },
      body: { config, subject_ids: subjectIds, overwrite },
    }),
    "/api/plan/{kind}",
  );
}

/**
 * Plans every config in one call and merges the results — used for a multi-sphere batch (one
 * `AnalyzerConfig` per sphere row), which submits as N separate jobs on Run.
 */
export async function planAnalyzerBatch(
  configs: AnalyzerConfig[],
  subjectIds: string[],
  overwrite: boolean,
  client = api,
): Promise<PlanResult> {
  const results = await Promise.all(
    configs.map((c) => planAnalyzer(c, subjectIds, overwrite, client)),
  );
  const merged: PlanResult = {
    jobs: results.flatMap((r) => r.jobs),
    lock_conflicts: results.flatMap((r) => r.lock_conflicts),
    cost: results.reduce(
      (acc, r) => ({
        cpus: acc.cpus + r.cost.cpus,
        mem_gb: acc.mem_gb + r.cost.mem_gb,
      }),
      { cpus: 0, mem_gb: 0 },
    ),
    warnings: Array.from(new Set(results.flatMap((r) => r.warnings))),
    resolved: results[0]?.resolved ?? null,
  };
  return merged;
}

export async function submitAnalyzerJob(
  config: AnalyzerConfig,
  subjectIds: string[],
  overwrite: boolean,
  tags: string[] = [],
  client = api,
): Promise<JobStatus> {
  return unwrap(
    await client.POST("/api/jobs", {
      body: {
        kind: "analyzer",
        config,
        subject_ids: subjectIds,
        tags,
        overwrite,
      },
    }),
    "/api/jobs",
  );
}

export async function getViewSpec(
  kind: "subject" | "simulation" | "analysis" | "group" | "custom",
  query: {
    subject?: string;
    simulation?: string;
    space?: "subject" | "mni";
    field?: string;
    analysis?: string;
    roi?: string;
    path?: string;
  },
  client = api,
): Promise<ViewSpec> {
  return unwrap(
    await client.GET("/api/view/{kind}", { params: { path: { kind }, query } }),
    "/api/view/{kind}",
  );
}

/** Origin-relative URL for a jailed artifact file (pdf/png/csv/json/txt); safe to `window.open`. */
export function artifactUrl(path: string): string {
  return `/api/files/artifact?path=${encodeURIComponent(path)}`;
}

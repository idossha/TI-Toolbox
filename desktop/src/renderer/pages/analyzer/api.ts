/**
 * Typed wrappers for the endpoints the Analyzer page calls: the simulation catalog, plan and job
 * submission. They use the shared `api` (openapi-fetch) instance and its `unwrap`, typed from the
 * generated `schema.d.ts`.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { mergePlanResults, type PlanResult as SharedPlanResult } from "../_shared/run/planModel";

export type PlanResult = components["schemas"]["PlanResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type AnalyzerConfig = components["schemas"]["AnalyzerConfig"];
export type SimulationDetail = components["schemas"]["SimulationDetail"];

/** One subject's simulations as the v1 catalog describes them (`fields`, `montages`, `space`, ...). */
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

/** One planned/submitted analysis: a config and the subjects it runs over. */
export interface AnalyzerJobSpec {
  config: AnalyzerConfig;
  subjectIds: string[];
  /** How the page names this job's row in a blocked sentence ("Job 2"); never sent. */
  label?: string;
}

/** `planAnalyzerBatch`'s refusal: which item's plan request failed, and what it failed with. */
export class AnalyzerPlanError extends Error {
  constructor(
    public readonly index: number,
    public readonly reason: unknown,
  ) {
    super(reason instanceof Error ? reason.message : String(reason));
    this.name = "AnalyzerPlanError";
  }
}

/** The merged plan of a batch, plus each item's own plan in item order (what the page reads to
 *  tell which job writes which folder). */
export type AnalyzerBatchPlan = PlanResult & { items?: PlanResult[] };

/**
 * Plans every job in one call and merges the results — used for the Jobs table's batch (one
 * `AnalyzerConfig` per row × sphere), which submits as N separate jobs on Run.
 *
 * Each item carries **its own** subject ids: since the 2026-09-06 jobs rework a row names its own
 * subject, so a single page-level `subject_ids` would plan every config against every subject.
 *
 * Every item is planned whatever the others do (`allSettled`), and a refused item rejects the
 * batch with an `AnalyzerPlanError` naming WHICH item, so the page can quote the server against
 * the right row. The merge is the shared `mergePlanResults`: CPUs/memory are one job's (max), the
 * ETA is the batch's (sum) — the numbers every other run page's tiles read.
 */
export async function planAnalyzerBatch(
  items: AnalyzerJobSpec[],
  overwrite: boolean,
  client = api,
): Promise<AnalyzerBatchPlan> {
  const settled = await Promise.allSettled(
    items.map((i) => planAnalyzer(i.config, i.subjectIds, overwrite, client)),
  );
  const failed = settled.findIndex((s) => s.status === "rejected");
  if (failed >= 0) throw new AnalyzerPlanError(failed, (settled[failed] as PromiseRejectedResult).reason);
  const results = settled.map((s) => (s as PromiseFulfilledResult<PlanResult>).value);
  const merged = mergePlanResults(results as unknown as SharedPlanResult[]) as unknown as PlanResult;
  return { ...merged, items: results };
}

/**
 * The tag every job of one Run press shares, so the Results panel can group them.
 *
 * A module function rather than an inline `Date.now()` in the page: since the jobs rework the
 * page's submit closure is render-scope (its inputs are derived from the rows each render), and
 * React Compiler rejects an impure call there — correctly, since a value read during render is a
 * value that can differ between renders.
 */
export function newAnalysisTag(): string {
  return `analysis:${Date.now()}`;
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

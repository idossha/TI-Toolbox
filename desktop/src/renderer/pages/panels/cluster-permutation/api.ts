/** Page-scoped API calls for the Cluster Permutation panel. Kept local — see pages/simulator/api.ts. */
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";

export type Simulation = components["schemas"]["Simulation"];
export type PlanResult = components["schemas"]["PlanResult"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type GroupComparisonConfig = components["schemas"]["GroupComparisonConfig"];
export type CorrelationConfig = components["schemas"]["CorrelationConfig"];
type PipelineConfig = components["schemas"]["PipelineConfig"];

export async function getSimulationsFor(subject: string): Promise<Simulation[]> {
  return unwrap(await api.GET("/api/catalog/simulations", { params: { query: { subject } } }), "/api/catalog/simulations").simulations;
}

export async function validateStats(config: GroupComparisonConfig | CorrelationConfig): Promise<ValidateResult> {
  return unwrap(
    await api.POST("/api/validate/{kind}", { params: { path: { kind: "stats" } }, body: { config: config as PipelineConfig } }),
    "/api/validate/stats",
  );
}

export async function planStats(config: GroupComparisonConfig | CorrelationConfig, subjectIds: string[]): Promise<PlanResult> {
  return unwrap(
    await api.POST("/api/plan/{kind}", { params: { path: { kind: "stats" } }, body: { config: config as PipelineConfig, subject_ids: subjectIds } }),
    "/api/plan/stats",
  );
}

export async function createStatsJob(config: GroupComparisonConfig | CorrelationConfig, subjectIds: string[]): Promise<JobStatus> {
  return unwrap(await api.POST("/api/jobs", { body: { kind: "stats", config: config as PipelineConfig, subject_ids: subjectIds } }), "/api/jobs");
}

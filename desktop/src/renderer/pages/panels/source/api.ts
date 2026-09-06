/**
 * Page-scoped API calls for the Source panel. Kept local — see pages/simulator/api.ts.
 *
 * `SourceConfig` is a real `$defs` entry (ra_13 finding #10) — typed directly, with
 * `/api/validate/source` called before submit.
 */
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";

export type SubjectDetail = components["schemas"]["SubjectDetail"];
export type Simulation = components["schemas"]["Simulation"];
export type PlanResult = components["schemas"]["PlanResult"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type SourceConfig = components["schemas"]["SourceConfig"];
type PipelineConfig = components["schemas"]["PipelineConfig"];

/** The plan/job endpoints are typed over the whole `PipelineConfig` union — this is the one place
 * that widens back to the request shape, same pattern as `pages/simulator/api.ts`'s `asPipelineConfig`. */
function asPipelineConfig(config: SourceConfig): PipelineConfig {
  return config as unknown as PipelineConfig;
}

export async function getSubjectDetail(id: string): Promise<SubjectDetail> {
  return unwrap(await api.GET("/api/catalog/subjects/{id}", { params: { path: { id } } }), `/api/catalog/subjects/${id}`);
}

export async function getSimulationsFor(subject: string): Promise<Simulation[]> {
  return unwrap(await api.GET("/api/catalog/simulations", { params: { query: { subject } } }), "/api/catalog/simulations").simulations;
}

export async function validateSource(config: SourceConfig): Promise<ValidateResult> {
  return unwrap(
    await api.POST("/api/validate/{kind}", { params: { path: { kind: "source" } }, body: { config: asPipelineConfig(config) } }),
    "/api/validate/source",
  );
}

export async function planSource(config: SourceConfig, subjectIds: string[], overwrite: boolean): Promise<PlanResult> {
  return unwrap(
    await api.POST("/api/plan/{kind}", { params: { path: { kind: "source" } }, body: { config: asPipelineConfig(config), subject_ids: subjectIds, overwrite } }),
    "/api/plan/source",
  );
}

export async function createSourceJob(config: SourceConfig, subjectIds: string[], overwrite: boolean): Promise<JobStatus> {
  return unwrap(
    await api.POST("/api/jobs", { body: { kind: "source", config: asPipelineConfig(config), subject_ids: subjectIds, overwrite } }),
    "/api/jobs",
  );
}

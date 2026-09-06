/**
 * Page-scoped API calls for the NIfTI Group Averaging panel. Kept local — see
 * pages/simulator/api.ts.
 *
 * `NiftiAverageConfig` is a real `contracts/schema.json` `$def` now (ra_13 finding #10 — the
 * PARITY.md "no schema entry, cast through PipelineConfig" note was stale); typed directly here
 * instead of the `Record<string, unknown>` escape hatch, with `/api/validate/nifti_average`
 * called before submit.
 */
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";

export type Subject = components["schemas"]["Subject"];
export type Simulation = components["schemas"]["Simulation"];
export type PlanResult = components["schemas"]["PlanResult"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type NiftiAverageConfig = components["schemas"]["NiftiAverageConfig"];
type PipelineConfig = components["schemas"]["PipelineConfig"];

function asPipelineConfig(config: NiftiAverageConfig): PipelineConfig {
  return config as unknown as PipelineConfig;
}

export async function getSimulationsFor(subject: string): Promise<Simulation[]> {
  return unwrap(await api.GET("/api/catalog/simulations", { params: { query: { subject } } }), "/api/catalog/simulations").simulations;
}

export async function validateNiftiAverage(config: NiftiAverageConfig): Promise<ValidateResult> {
  return unwrap(
    await api.POST("/api/validate/{kind}", { params: { path: { kind: "nifti_average" } }, body: { config: asPipelineConfig(config) } }),
    "/api/validate/nifti_average",
  );
}

export async function planNiftiAverage(config: NiftiAverageConfig, subjectIds: string[]): Promise<PlanResult> {
  return unwrap(
    await api.POST("/api/plan/{kind}", { params: { path: { kind: "nifti_average" } }, body: { config: asPipelineConfig(config), subject_ids: subjectIds } }),
    "/api/plan/nifti_average",
  );
}

export async function createNiftiAverageJob(config: NiftiAverageConfig, subjectIds: string[]): Promise<JobStatus> {
  return unwrap(await api.POST("/api/jobs", { body: { kind: "nifti_average", config: asPipelineConfig(config), subject_ids: subjectIds } }), "/api/jobs");
}

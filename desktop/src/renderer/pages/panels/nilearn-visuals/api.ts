/**
 * Page-scoped API calls for the Nilearn Visuals panel. Kept local — see pages/simulator/api.ts.
 *
 * `NilearnConfig` is a real `contracts/schema.json` `$def` now (ra_13 finding #10 — the PARITY.md
 * "no schema entry" note was stale); typed directly here with `/api/validate/nilearn` called
 * before submit.
 */
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";

export type Simulation = components["schemas"]["Simulation"];
export type PlanResult = components["schemas"]["PlanResult"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type NilearnConfig = components["schemas"]["NilearnConfig"];
type PipelineConfig = components["schemas"]["PipelineConfig"];

function asPipelineConfig(config: NilearnConfig): PipelineConfig {
  return config as unknown as PipelineConfig;
}

export async function getSimulationsFor(subject: string): Promise<Simulation[]> {
  return unwrap(await api.GET("/api/catalog/simulations", { params: { query: { subject } } }), "/api/catalog/simulations").simulations;
}

export async function validateNilearn(config: NilearnConfig): Promise<ValidateResult> {
  return unwrap(
    await api.POST("/api/validate/{kind}", { params: { path: { kind: "nilearn" } }, body: { config: asPipelineConfig(config) } }),
    "/api/validate/nilearn",
  );
}

export async function planNilearn(config: NilearnConfig, subjectIds: string[]): Promise<PlanResult> {
  return unwrap(
    await api.POST("/api/plan/{kind}", { params: { path: { kind: "nilearn" } }, body: { config: asPipelineConfig(config), subject_ids: subjectIds } }),
    "/api/plan/nilearn",
  );
}

export async function createNilearnJob(config: NilearnConfig, subjectIds: string[]): Promise<JobStatus> {
  return unwrap(await api.POST("/api/jobs", { body: { kind: "nilearn", config: asPipelineConfig(config), subject_ids: subjectIds } }), "/api/jobs");
}

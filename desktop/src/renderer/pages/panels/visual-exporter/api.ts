/**
 * Page-scoped API calls for the 3D Visual Exporter panel. Kept local — see `pages/simulator/api.ts`.
 *
 * All four modes are the one `blender` job kind, discriminated by the config's own `_type`
 * (`tit/server/routes/validate.py`'s `AMBIGUOUS_KIND_CLASSES["blender"]`, `tit/blender/__main__.py`'s
 * dispatch) — which is why every call below takes the union rather than one config type.
 */
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";

export type Simulation = components["schemas"]["Simulation"];
export type PlanResult = components["schemas"]["PlanResult"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type MontageConfig = components["schemas"]["MontageConfig"];
export type VectorConfig = components["schemas"]["VectorConfig"];
export type RegionConfig = components["schemas"]["RegionConfig"];
export type SubcorticalConfig = components["schemas"]["SubcorticalConfig"];
export type Region = components["schemas"]["Region"];
type PipelineConfig = components["schemas"]["PipelineConfig"];

export type BlenderConfig = MontageConfig | VectorConfig | RegionConfig | SubcorticalConfig;

function asPipelineConfig(config: BlenderConfig): PipelineConfig {
  return config as unknown as PipelineConfig;
}

export async function getSimulationsFor(subject: string): Promise<Simulation[]> {
  const path = "/api/catalog/simulations";
  return unwrap(await api.GET(path, { params: { query: { subject } } }), path).simulations;
}

/** Cortical regions of one atlas, per hemisphere — the list Qt built by calling
 * `atlas2subject(..., split_labels=True)` in the widget itself. */
export async function getAtlasRegions(subject: string, atlas: string): Promise<Region[]> {
  const path = "/api/catalog/atlases/regions";
  return unwrap(await api.GET(path, { params: { query: { subject, atlas, hemi: "both" } } }), path);
}

export async function validateBlender(config: BlenderConfig): Promise<ValidateResult> {
  return unwrap(
    await api.POST("/api/validate/{kind}", { params: { path: { kind: "blender" } }, body: { config: asPipelineConfig(config) } }),
    "/api/validate/blender",
  );
}

export async function planBlender(config: BlenderConfig, subjectIds: string[]): Promise<PlanResult> {
  return unwrap(
    await api.POST("/api/plan/{kind}", { params: { path: { kind: "blender" } }, body: { config: asPipelineConfig(config), subject_ids: subjectIds } }),
    "/api/plan/blender",
  );
}

export async function createBlenderJob(config: BlenderConfig, subjectIds: string[]): Promise<JobStatus> {
  return unwrap(await api.POST("/api/jobs", { body: { kind: "blender", config: asPipelineConfig(config), subject_ids: subjectIds } }), "/api/jobs");
}

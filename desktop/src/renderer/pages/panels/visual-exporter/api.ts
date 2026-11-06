/**
 * Page-scoped API calls for the 3D Visual Exporter panel. Kept local — see `pages/simulator/api.ts`.
 *
 * All five modes are the one `blender` job kind, discriminated by the config's own `_type`
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
export type TractVisualConfig = components["schemas"]["TractVisualConfig"];
export type TractConfig = components["schemas"]["TractConfig"];
export type MissingInput = components["schemas"]["MissingInput"];
export type SimulationNetworks = components["schemas"]["SimulationNetworks"];
export type OwnNetwork = components["schemas"]["TractOwnNetwork"];
export type Region = components["schemas"]["Region"];
export type NiftiLabel = components["schemas"]["NiftiLabel"];
type PipelineConfig = components["schemas"]["PipelineConfig"];

export type BlenderConfig = MontageConfig | VectorConfig | RegionConfig | SubcorticalConfig | TractVisualConfig;

function asPipelineConfig(config: BlenderConfig | TractConfig): PipelineConfig {
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

/** The integer labels of one segmentation volume — the sub-cortical mode's label browser, and
 * the v3 replacement for the Qt `AtlasRegionFinderDialog` that parsed a FreeSurfer LUT itself.
 * An empty `path` means the subject's own `<m2m>/segmentation/labeling.nii.gz`. */
export async function getNiftiLabels(subject: string, path?: string): Promise<NiftiLabel[]> {
  const p = "/api/catalog/nifti/labels";
  return unwrap(await api.GET(p, { params: { query: { subject, path: path || undefined } } }), p);
}

/** The streamline files the user has loaded for this head model (`tit/tract/own.py`). */
export async function getOwnNetworks(subject: string): Promise<OwnNetwork[]> {
  const path = "/api/tract/own";
  return unwrap(await api.GET(path, { params: { query: { subject } } }), path).networks;
}

/** Sends a file to be checked and kept; a file that does not fit is refused in the server's words. */
export async function loadOwnNetwork(file: File, subject: string): Promise<OwnNetwork> {
  const response = await fetch(`/api/tract/own?name=${encodeURIComponent(file.name)}&subject=${encodeURIComponent(subject)}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof error?.detail === "string" ? error.detail : `Could not load this file (${response.status}).`);
  }
  return (await response.json()) as OwnNetwork;
}

/** The simulation's `tract/*.trx` stems and the PNG and MP4 files rendered from them. */
export async function getSimulationNetworks(subject: string, name: string): Promise<SimulationNetworks> {
  const path = "/api/catalog/simulations/{name}/networks";
  return unwrap(await api.GET(path, { params: { path: { name }, query: { subject } } }), path);
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

/** `overwrite` is the user's "Replace and rerun"; without it the server refuses (409) an existing export. */
export async function createBlenderJob(config: BlenderConfig, subjectIds: string[], overwrite = false, after: string[] = []): Promise<JobStatus> {
  return unwrap(await api.POST("/api/jobs", { body: { kind: "blender", config: asPipelineConfig(config), subject_ids: subjectIds, overwrite, after } }), "/api/jobs");
}

/** What the assess stage needs and does not have (`tit/jobs/preflight.py::_check_tract`), in the server's words. */
export async function preflightTract(config: TractConfig, subjectId: string): Promise<MissingInput[]> {
  const body = { kind: "tract" as const, config: asPipelineConfig(config), subject_ids: [subjectId] };
  return unwrap(await api.POST("/api/jobs/preflight", { body }), "/api/jobs/preflight").missing;
}

export async function planTract(config: TractConfig, subjectId: string): Promise<PlanResult> {
  return unwrap(
    await api.POST("/api/plan/{kind}", { params: { path: { kind: "tract" } }, body: { config: asPipelineConfig(config), subject_ids: [subjectId] } }),
    "/api/plan/tract",
  );
}

/** `overwrite` is the user's "Replace and rerun"; without it the server refuses (409) an existing `tract/` folder. */
export async function createTractJob(config: TractConfig, subjectId: string, overwrite = false): Promise<JobStatus> {
  return unwrap(await api.POST("/api/jobs", { body: { kind: "tract", config: asPipelineConfig(config), subject_ids: [subjectId], overwrite } }), "/api/jobs");
}

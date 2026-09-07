/**
 * Page-scoped API calls for the Simulator screen. Kept local rather than added to the shared
 * `api/client.ts` (owned across many pages; every lane needing catalog v1/jobs/plan endpoints
 * would otherwise collide editing the same file) — see PARITY.md and the final report for the
 * gap this leaves (a shared v1 client belongs in a later pass, owned by one lane).
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type SubjectDetail = components["schemas"]["SubjectDetail"];
export type Montages = components["schemas"]["Montages"];
export type MontagePairs = components["schemas"]["MontagePairs"];
export type EegNet = components["schemas"]["EegNet"];
export type FlexRun = components["schemas"]["FlexRun"];
export type FlexMapping = components["schemas"]["FlexMapping"];
export type FreehandConfig = components["schemas"]["FreehandConfig"];
export type ElectrodePosition = components["schemas"]["ElectrodePosition"];
export type PlanResult = components["schemas"]["PlanResult"];
export type MontageSources = components["schemas"]["MontageSources"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type JobKind = components["schemas"]["JobKind"];
export type Simulation = components["schemas"]["Simulation"];
type PipelineConfig = components["schemas"]["PipelineConfig"];

/**
 * The generated `PipelineConfig` union does not (and should not) know about the plan-only `name`
 * convenience field or the not-yet-shipped `tissue_conductivities` field (see `planSim` below) —
 * this is the one place that widens back to the real request shape.
 */
function asPipelineConfig(config: Record<string, unknown>): PipelineConfig {
  return config as unknown as PipelineConfig;
}

export async function getSubjectDetail(id: string): Promise<SubjectDetail> {
  return unwrap(await api.GET("/api/catalog/subjects/{id}", { params: { path: { id } } }), `/api/catalog/subjects/${id}`);
}

export async function getMontages(): Promise<Montages> {
  return unwrap(await api.GET("/api/catalog/montages"), "/api/catalog/montages");
}

export async function putMontage(net: string, kind: "uni_polar" | "multi_polar", name: string, pairs: MontagePairs): Promise<MontagePairs> {
  return unwrap(
    await api.PUT("/api/catalog/montages/{net}/{kind}/{name}", {
      params: { path: { net, kind, name } },
      body: { pairs },
    }),
    `/api/catalog/montages/${net}/${kind}/${name}`,
  );
}

export async function deleteMontage(net: string, kind: "uni_polar" | "multi_polar", name: string): Promise<void> {
  const { response } = await api.DELETE("/api/catalog/montages/{net}/{kind}/{name}", { params: { path: { net, kind, name } } });
  if (!response.ok) throw new Error(`Could not delete montage ${name} (HTTP ${response.status}).`);
}

export async function getEegNets(subject: string): Promise<EegNet[]> {
  return unwrap(await api.GET("/api/catalog/eeg-nets", { params: { query: { subject } } }), "/api/catalog/eeg-nets");
}

export async function getFlexRuns(subject: string): Promise<FlexRun[]> {
  return unwrap(await api.GET("/api/catalog/flex-runs", { params: { query: { subject } } }), "/api/catalog/flex-runs");
}

/**
 * The run's electrodes as one EEG net's labels, mapping them if the run has never been mapped onto
 * that net: the server maps the optimiser's XYZ onto *any* net the subject has (Hungarian
 * assignment in `tit/sim/montage_sources.py`) and caches the result beside the run, so a net the
 * user picks here is as usable as one the optimiser pre-mapped.
 */
export async function getFlexMapping(subject: string, run: string, eegNet: string): Promise<FlexMapping> {
  return unwrap(
    await api.GET("/api/catalog/flex-runs/{run}/mapping", { params: { path: { run }, query: { subject, eeg_net: eegNet } } }),
    `/api/catalog/flex-runs/${run}/mapping`,
  );
}

export async function getFreehand(subject: string): Promise<FreehandConfig[]> {
  return unwrap(await api.GET("/api/catalog/freehand", { params: { query: { subject } } }), "/api/catalog/freehand");
}

export async function putFreehand(subject: string, name: string, config: FreehandConfig): Promise<FreehandConfig> {
  return unwrap(
    await api.PUT("/api/catalog/freehand/{name}", { params: { query: { subject }, path: { name } }, body: config }),
    `/api/catalog/freehand/${name}`,
  );
}

export async function getSimulationsFor(subject: string): Promise<Simulation[]> {
  return unwrap(await api.GET("/api/catalog/simulations", { params: { query: { subject } } }), "/api/catalog/simulations").simulations;
}

/**
 * `config` is `Record<string, unknown>` at the call boundary only (typed-client friction, not a
 * widened wire shape) — `buildSimulationConfig`'s output is a real, schema-conformant
 * `SimulationConfig` with no extra keys (`contracts/generated/config.schema.json` sets `additionalProperties:
 * false` on it, ra_11 finding 3). A previous revision of this page added a plan-only top-level
 * `name` field so the mock's `planFor("sim", ...)` could resolve a nicer `output_dir` than its
 * "NewRun" fallback; that stopped validating once `additionalProperties: false` landed, so it was
 * removed (see `buildConfig.ts`'s doc comment and PARITY.md). The real server never needed it —
 * `tit/server/routes/plan.py`'s `_plan_sim` already resolves `output_dir`/`exists` from
 * `config.montages[i].name` directly.
 */
/**
 * `montageSources` is the request's own `PlanRequest.montage_sources` field (a sibling of
 * `config`, per `contracts/openapi.yaml`) for flex/freehand rows — not a key inside `config`.
 * `tit/server/routes/plan.py`'s current implementation still reads an equivalent, differently-
 * shaped value from `config["montage_sources"]` (`subject_id`/`run_name`, not this schema's
 * `subject`/`run`) — a known B3-side gap (`contracts/CHANGES.md`'s fix:contract entry,
 * item 7); this call follows the frozen contract, which is what the mock implements today and
 * what the real route needs to converge on. Harmless either way: the mock ignores
 * `montage_sources` entirely, and a real server that doesn't read it yet just plans the
 * `config.montages` sent alongside — see `buildConfig.ts`'s `buildSimulationConfig`, which is
 * unaffected by this and still embeds a fully-resolved `Montage` for every row (required for job
 * submission regardless, since `POST /api/jobs`'s `JobSpec` has no `montage_sources` field at all).
 */
export async function planSim(
  config: Record<string, unknown>,
  subjectIds: string[],
  overwrite: boolean,
  montageSources?: MontageSources,
): Promise<PlanResult> {
  return unwrap(
    await api.POST("/api/plan/{kind}", {
      params: { path: { kind: "sim" } },
      body: {
        config: asPipelineConfig(config),
        subject_ids: subjectIds,
        overwrite,
        ...(montageSources ? { montage_sources: montageSources } : {}),
      },
    }),
    "/api/plan/sim",
  );
}

export async function validateSim(config: Record<string, unknown>): Promise<ValidateResult> {
  return unwrap(await api.POST("/api/validate/{kind}", { params: { path: { kind: "sim" } }, body: { config: asPipelineConfig(config) } }), "/api/validate/sim");
}

export async function createSimJob(config: Record<string, unknown>, subjectIds: string[], overwrite: boolean): Promise<JobStatus> {
  return unwrap(
    await api.POST("/api/jobs", { body: { kind: "sim", config: asPipelineConfig(config), subject_ids: subjectIds, overwrite } }),
    "/api/jobs",
  );
}

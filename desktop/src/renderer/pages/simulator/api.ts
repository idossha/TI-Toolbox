/**
 * Page-scoped API calls for the Simulator screen (catalog v1 and plan endpoints), on the shared
 * `api` client.
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
type PipelineConfig = components["schemas"]["PipelineConfig"];

/**
 * The generated `PipelineConfig` union does not (and should not) know about the plan-only `name`
 * convenience field (see `planSim` below) — this is the one place that widens back to the real
 * request shape.
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

export async function deleteFreehand(subject: string, name: string): Promise<void> {
  const { response } = await api.DELETE("/api/catalog/freehand/{name}", { params: { query: { subject }, path: { name } } });
  if (!response.ok) throw new Error(`Could not delete placement ${name} (HTTP ${response.status}).`);
}

/**
 * Plans one resolved row. `config` is `Record<string, unknown>` at the call boundary only
 * (typed-client friction, not a widened wire shape): `buildSimulationConfig`'s output is a
 * schema-conformant `SimulationConfig` with no extra keys (`additionalProperties: false`), and
 * `tit/server/routes/plan.py`'s `_plan_sim` resolves `output_dir`/`exists` from
 * `config.montages[i].name`.
 *
 * `PlanRequest.montage_sources` is never sent. Every row is already resolved into the config's
 * one `Montage` (job submission needs that anyway: `JobSpec` has no `montage_sources`), and the
 * server plans `montage_sources` *in addition to* `config.montages`, so a row sending both would
 * be planned twice, under two output folders. The field stays in the frozen contract.
 */
export async function planSim(config: Record<string, unknown>, subjectIds: string[], overwrite: boolean): Promise<PlanResult> {
  return unwrap(
    await api.POST("/api/plan/{kind}", {
      params: { path: { kind: "sim" } },
      body: { config: asPipelineConfig(config), subject_ids: subjectIds, overwrite },
    }),
    "/api/plan/sim",
  );
}

export interface CandidateMapping {
  eeg_net: string;
  pairs: string[][];
  optimized_positions: number[][];
  mapped_positions: number[][];
  distances: number[];
}

/** Resolve the selected candidate, never the run's final winner. */
export async function getCandidateMapping(subject: string, run: string, candidateId: string, eegNet: string): Promise<CandidateMapping> {
  return unwrap(await api.GET("/api/catalog/optimization-candidates/{candidate_id}/mapping", {
    params: { path: { candidate_id: candidateId }, query: { subject, run, eeg_net: eegNet } },
  }), "Candidate cap mapping");
}

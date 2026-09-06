/**
 * Every network call the merged Optimizer page makes — the union of `optimizer-flex/api.ts` and
 * `optimizer-ex/queries.ts`, which is the whole reason they can be one page: the three methods
 * differ in their config body and their `kind`, not in the endpoints they talk to.
 *
 * Kept here rather than in `src/renderer/api/client.ts` for the same reason the two predecessors
 * did: that file has no declared owner and several page lanes need endpoints concurrently.
 */
import { api, unwrap, ApiError } from "../../api/client";
import type { components } from "../../api/schema";

export type EegNet = components["schemas"]["EegNet"];
export type Leadfield = components["schemas"]["Leadfield"];
export type PlanResult = components["schemas"]["PlanResult"];
export type JobStatus = components["schemas"]["JobStatus"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type PipelineKind = components["schemas"]["PipelineKind"];
export type ExConfigBody = components["schemas"]["ExConfig"];
export type MExConfigBody = components["schemas"]["MExConfig"];
export type LeadfieldConfigBody = components["schemas"]["LeadfieldConfig"];
/** Flex configs are built field-by-field in `flexConfig.ts`; the schema type is a closed dataclass
 *  mirror that does not admit the two provisional `adaptive`/`pareto` blocks (see PARITY.md). */
export type FlexConfigWire = Record<string, unknown>;

export async function getEegNets(subject: string): Promise<EegNet[]> {
  const path = "/api/catalog/eeg-nets";
  return unwrap(await api.GET(path, { params: { query: { subject } } }), path);
}

export async function getLeadfields(subject: string): Promise<Leadfield[]> {
  const path = "/api/catalog/leadfields";
  return unwrap(await api.GET(path, { params: { query: { subject } } }), path);
}

/** `POST /api/plan/{kind}` for one resolved config. Thrown errors surface as the plan's error. */
export async function planFor(kind: string, config: unknown, subjectIds: string[], overwrite = false): Promise<PlanResult> {
  const path = "/api/plan/{kind}";
  return unwrap(
    await api.POST(path, {
      params: { path: { kind: kind as PipelineKind } },
      body: { config: config as never, subject_ids: subjectIds, overwrite },
    }),
    path,
  );
}

export async function validateFor(kind: string, config: unknown): Promise<ValidateResult> {
  const path = "/api/validate/{kind}";
  return unwrap(
    await api.POST(path, { params: { path: { kind: kind as PipelineKind } }, body: { config: config as never } }),
    path,
  );
}

export async function submitJob(
  kind: string,
  config: unknown,
  subjectId: string,
  tags: string[],
  overwrite: boolean,
): Promise<JobStatus> {
  const path = "/api/jobs";
  return unwrap(
    await api.POST(path, {
      body: {
        kind: kind as components["schemas"]["JobKind"],
        config: config as never,
        subject_ids: [subjectId],
        tags,
        overwrite,
      },
    }),
    path,
  );
}

/** Queues leadfield generation for a net that has none — the Ex/mEx precondition strip's action. */
export async function submitLeadfieldJob(subjectId: string, net: string): Promise<JobStatus> {
  const config: LeadfieldConfigBody = { subject_id: subjectId, eeg_net: net, tissues: [1, 2], interpolation: null, overwrite: false };
  const path = "/api/jobs";
  return unwrap(
    await api.POST(path, { body: { kind: "leadfield", config: config as never, subject_ids: [subjectId] } }),
    path,
  );
}

export { ApiError };

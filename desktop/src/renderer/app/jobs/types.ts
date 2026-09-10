/** Types mirror plan §3 ("Jobs") and `contracts/events.schema.json` exactly — keep in sync with them. */
import type { components } from "../../api/schema";

/**
 * `kind ∈ pre | sim | flex | flex_adaptive | flex_pareto | ex | mex | leadfield | analyzer |
 * stats | source | blender | nifti_average | nilearn | viewer | project_init | tools | report`
 * (plan §3) — left as `string` (not the generated literal union) because the server is the
 * source of truth for the set and new kinds must not require a type change here to compile.
 */
export type JobKind = string;

export type JobState = components["schemas"]["JobState"];

/**
 * A direct alias of the schema-generated type, not a hand-written mirror: the contract marks
 * `group_id`, `started_at`, `finished_at`, `progress`, `liveness`, `exit_code`, `error`,
 * `cpu_percent` and `rss` as `T | null`; re-deriving them by hand previously modelled the same
 * optionality as `T | undefined` (no `null`), which diverged from the contract (see
 * `pages/jobs/PARITY.md` gap 7) and forced `pages/jobs/api.ts` to bridge the mismatch with an
 * `as unknown as JobStatus` cast at every REST call that returns one — that cast can now be
 * dropped (harmless to leave; just redundant) since this type *is* `components["schemas"]
 * ["JobStatus"]`, not a shape that merely resembles it.
 */
export type JobStatus = components["schemas"]["JobStatus"];
export type JobProgress = components["schemas"]["JobProgress"];
export type JobArtifact = components["schemas"]["Artifact"];
export type JobErrorInfo = components["schemas"]["JobError"];
export type JobWaitingOn = components["schemas"]["WaitingOn"];

export type JobEventType = "log" | "stage" | "progress" | "marker" | "artifact" | "result" | "exit";

export interface JobEvent {
  seq: number;
  ts: number;
  type: JobEventType;
  level?: string;
  logger?: string;
  msg?: string;
  stage?: string;
  i?: number;
  n?: number;
  pct?: number;
  outputs?: unknown;
}

export type JobsWsServerMessage = { type: "job"; job: JobStatus } | { type: "event"; job_id: string; event: JobEvent };

export type JobsWsClientMessage = { subscribe: Record<string, number> } | { unsubscribe: string[] };

/** Types mirror plan §3 ("Jobs") and `contracts/events.schema.json` exactly — keep in sync with them. */
import type { components } from "../../api/schema";

export type JobState = components["schemas"]["JobState"];

/**
 * A direct alias of the schema-generated type, not a hand-written mirror: the contract marks
 * `group_id`, `started_at`, `finished_at`, `progress`, `liveness`, `exit_code`, `error`,
 * `cpu_percent` and `rss` as `T | null`; re-deriving them by hand previously modelled the same
 * optionality as `T | undefined` (no `null`), which diverged from the contract.
 */
export type JobStatus = components["schemas"]["JobStatus"];

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

/** An agent's plan awaiting (or past) the user's approval — `tit.server.proposals`. */
export type Proposal = components["schemas"]["Proposal"];

export type JobsWsServerMessage =
  | { type: "job"; job: JobStatus }
  | { type: "event"; job_id: string; event: JobEvent }
  | { type: "proposal"; proposal: Proposal };

export type JobsWsClientMessage = { subscribe: Record<string, number> } | { unsubscribe: string[] };

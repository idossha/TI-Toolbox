/**
 * `POST /api/jobs/groups` — the one way a page submits a batch (IMPLEMENTATION_PLAN.md R3).
 *
 * One request creates the whole group: one job per selected subject (or per `(subject, config)`
 * entry, for the Simulator's one job per montage), all queued, sharing a `group_id`, carrying the
 * `parallel_subjects` cap the scheduler enforces. The pages used to loop `POST /api/jobs` per
 * subject and call the loop "sequential" — which it was not: the server admitted whatever its
 * budget allowed, and a cap of 1 meant nothing. There is deliberately no batching helper here
 * that fans out several requests; if a page needs different configs per subject it sends them in
 * `subject_configs`, in the same one request.
 *
 * The server forces each generated config's `subject_id` to its own subject, so the isolation
 * guarantee does not depend on any caller getting the template right.
 */
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";

export type JobGroupResult = components["schemas"]["JobGroupResult"];
type JobGroupRequest = components["schemas"]["JobGroupRequest"];
export type GroupKind = JobGroupRequest["kind"];
type PipelineConfig = components["schemas"]["PipelineConfig"];

/** One planned job of a group whose config depends on the subject. */
export interface SubjectConfig {
  subject_id: string;
  config: unknown;
}

export interface SubmitJobGroupOptions {
  /** Per-subject configs; a subject with no entry uses the template `config`. */
  subjectConfigs?: SubjectConfig[];
  tags?: string[];
  /** Replace existing output instead of skipping it, for every job in the group. */
  overwrite?: boolean;
}

export async function submitJobGroup(
  kind: GroupKind,
  config: unknown,
  subjectIds: string[],
  parallelSubjects: number,
  options: SubmitJobGroupOptions = {},
  /** Injectable for tests, exactly like `api/client.ts`'s own helpers. */
  client = api,
): Promise<JobGroupResult> {
  const body: JobGroupRequest = {
    kind,
    config: config as PipelineConfig,
    subject_ids: subjectIds,
    parallel_subjects: Math.max(1, parallelSubjects),
  };
  if (options.subjectConfigs?.length) {
    body.subject_configs = options.subjectConfigs.map((entry) => ({
      subject_id: entry.subject_id,
      config: entry.config as PipelineConfig,
    }));
  }
  if (options.tags?.length) body.tags = options.tags;
  if (options.overwrite) body.overwrite = true;
  return unwrap(await client.POST("/api/jobs/groups", { body }), "/api/jobs/groups");
}

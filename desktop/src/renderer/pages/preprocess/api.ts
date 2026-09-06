/**
 * Local request helpers for this page — built on the shared `api`/`unwrap` from
 * `src/renderer/api/client.ts` (owned by F2). Endpoints not already wrapped there (validate, plan,
 * job groups, subject detail) get small typed helpers here rather than growing the shared client.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type SubjectDetail = components["schemas"]["SubjectDetail"];
export type PreprocessConfig = components["schemas"]["PreprocessConfig"];
/** Settings-only shape `PreprocessConfig.qsiprep_config` actually holds — no `subject_id`, flat resource fields. */
export type QsiPrepSettings = components["schemas"]["QSIPrepSettings"];
/** Settings-only shape `PreprocessConfig.qsi_recon_config` actually holds — no `subject_id`, flat resource fields. */
export type QsiReconSettings = components["schemas"]["QSIReconSettings"];
export type ValidateResult = components["schemas"]["ValidateResult"];
export type JobGroupResult = components["schemas"]["JobGroupResult"];

/**
 * `PlanJob` widened with `stage`/`label`, not yet in `contracts/openapi.v1.yaml` (ra_13 finding
 * 12) — `tit/jobs/plans.py`'s `PlannedJob.label` (e.g. `"sub-01:G2a"`) already exists server-side,
 * but `tit/server/routes/plan.py`'s wire-shape `PlanJob` pydantic model doesn't carry it yet. Both
 * fields are optional so this page reads them when a future contract adds them and falls back to
 * `describePreStageDir`'s directory-name guess otherwise (see its own doc comment).
 */
export type PlanJob = components["schemas"]["PlanJob"] & { stage?: string; label?: string };
export type PlanResult = Omit<components["schemas"]["PlanResult"], "jobs"> & { jobs: PlanJob[] };

export async function getSubjectDetail(id: string): Promise<SubjectDetail> {
  return unwrap(
    await api.GET("/api/catalog/subjects/{id}", { params: { path: { id } } }),
    `/api/catalog/subjects/${id}`,
  );
}

export async function validatePre(
  config: PreprocessConfig,
): Promise<ValidateResult> {
  return unwrap(
    await api.POST("/api/validate/{kind}", {
      params: { path: { kind: "pre" } },
      body: { config },
    }),
    "/api/validate/pre",
  );
}

export async function planPre(
  config: PreprocessConfig,
  subjectIds: string[],
  overwrite: boolean,
): Promise<PlanResult> {
  return unwrap(
    await api.POST("/api/plan/{kind}", {
      params: { path: { kind: "pre" } },
      body: { config, subject_ids: subjectIds, overwrite },
    }),
    "/api/plan/pre",
  );
}

export async function submitPreGroup(
  config: PreprocessConfig,
  subjectIds: string[],
  parallelSubjects: number,
): Promise<JobGroupResult> {
  return unwrap(
    await api.POST("/api/jobs/groups", {
      body: {
        kind: "pre",
        config,
        subject_ids: subjectIds,
        parallel_subjects: parallelSubjects,
      },
    }),
    "/api/jobs/groups",
  );
}

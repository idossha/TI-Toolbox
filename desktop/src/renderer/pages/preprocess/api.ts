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
export type JobGroupResult = components["schemas"]["JobGroupResult"];
export type PlanResult = components["schemas"]["PlanResult"];

export async function getSubjectDetail(id: string): Promise<SubjectDetail> {
  return unwrap(
    await api.GET("/api/catalog/subjects/{id}", { params: { path: { id } } }),
    `/api/catalog/subjects/${id}`,
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
): Promise<JobGroupResult> {
  return unwrap(
    await api.POST("/api/jobs/groups", {
      body: {
        kind: "pre",
        config,
        subject_ids: subjectIds,
      },
    }),
    "/api/jobs/groups",
  );
}

/**
 * REST calls for the jobs component family (rail / panel / page) and the Host tab. They live
 * beside the components that make them rather than in the shared `api/client.ts`, which is owned
 * across many lanes — the same reason `pages/results/api.ts` and `pages/viewer/api.ts` exist.
 *
 * `JobStatus`/`JobEvent` are re-exported from `app/jobs/types` (the shared `/ws/jobs` store's
 * types), not re-derived from `components["schemas"]` — this page merges a REST `GET /api/jobs`
 * page with that store's live map (`app/jobs/README.md`), and the two must be the exact same
 * type to merge without a cast at every call site. `app/jobs/types.ts::JobStatus` is now a direct
 * alias of `components["schemas"]["JobStatus"]` (its own header comment: the nullability mismatch
 * PARITY.md gap 7 flagged — `T | null` vs `T | undefined` — is resolved by aliasing rather than
 * re-deriving), so the REST calls below need no cast any more; the ones this file used to carry
 * are gone.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import type { JobEvent, JobState, JobStatus } from "../jobs/types";

export type { JobEvent, JobState, JobStatus } from "../jobs/types";
export type JobKind = components["schemas"]["JobKind"];
export type Settings = components["schemas"]["Settings"];
export type Project = components["schemas"]["Project"];
export type Subject = components["schemas"]["Subject"];

/**
 * Every `JobKind` in the v1 contract, for the kind filter's option list. `tools`/`report` were
 * added by the fix:contract reconciliation (CHANGES.md item 1 — `tit/jobs/spec.py::JOB_KINDS`
 * already had them; only the frozen contract's enum was missing them) — kept in sync with
 * `components["schemas"]["JobKind"]`'s enum by hand since this is a plain string-literal array,
 * not a place a generated type can be spread into.
 */
export const JOB_KINDS: JobKind[] = [
  "pre",
  "sim",
  "flex",
  "flex_adaptive",
  "flex_pareto",
  "ex",
  "mex",
  "leadfield",
  "analyzer",
  "stats",
  "source",
  "blender",
  "nifti_average",
  "nilearn",
  "project_init",
  "tools",
  "report",
];

export const JOB_STATES: JobState[] = ["queued", "running", "succeeded", "failed", "cancelled", "skipped", "lost"];

export const TERMINAL_STATES: JobState[] = ["succeeded", "failed", "cancelled", "skipped", "lost"];

export async function listJobs(filters: { state?: JobState; subject?: string; kind?: JobKind } = {}): Promise<JobStatus[]> {
  return unwrap(await api.GET("/api/jobs", { params: { query: filters } }), "/api/jobs");
}

/** Full event history for a job (`since: -1` = from the start) — used by the console's "load earlier". */
export async function getJobEvents(id: string, since = -1): Promise<JobEvent[]> {
  return unwrap(await api.GET("/api/jobs/{id}/events", { params: { path: { id }, query: { since } } }), `/api/jobs/${id}/events`);
}

export async function getJobLog(id: string, tail?: number): Promise<string> {
  return unwrap(
    await api.GET("/api/jobs/{id}/log", { params: { path: { id }, query: tail ? { tail } : {} }, parseAs: "text" }),
    `/api/jobs/${id}/log`,
  );
}

export async function cancelJob(id: string): Promise<JobStatus> {
  return unwrap(await api.POST("/api/jobs/{id}/cancel", { params: { path: { id } } }), `/api/jobs/${id}/cancel`);
}

export type RerunSpec = components["schemas"]["JobSpec"];

/** Read the old spec, but never inherit its destructive decision or execution dependencies. */
export function withRerunPolicy(spec: RerunSpec, overwrite: boolean): RerunSpec {
  function config(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(config);
    if (!value || typeof value !== "object") return value;
    return Object.fromEntries(Object.entries(value).map(([key, field]) => [key,
      ["overwrite", "replace_existing_outputs"].includes(key) ? overwrite
        : key === "skip_existing_outputs" ? !overwrite : config(field),
    ]));
  }
  return { kind: spec.kind, config: config(spec.config) as RerunSpec["config"], subject_ids: spec.subject_ids, tags: spec.tags, overwrite };
}

export async function prepareJobRerun(id: string, client = api): Promise<{ spec: RerunSpec; existing: number }> {
  const detail = unwrap(await client.GET("/api/jobs/{id}", { params: { path: { id } } }), `/api/jobs/${id}`);
  const spec = withRerunPolicy(detail.spec as unknown as RerunSpec, false);
  // Reports write into their new job directory; they have no shared output plan.
  if (spec.kind === "report") return { spec, existing: 0 };
  if (spec.kind === "project_init" || spec.kind === "tools") throw new Error("This job has no output preview. Use its original run page to start it again.");
  const plan = unwrap(await client.POST("/api/plan/{kind}", {
    params: { path: { kind: spec.kind } }, body: { config: spec.config, subject_ids: spec.subject_ids, overwrite: false },
  }), `/api/plan/${spec.kind}`);
  return { spec, existing: plan.jobs.filter((job) => job.exists).length };
}

export async function rerunJob(spec: RerunSpec, overwrite: boolean, client = api): Promise<JobStatus> {
  return unwrap(await client.POST("/api/jobs", { body: withRerunPolicy(spec, overwrite) }), "/api/jobs");
}

export async function forceJob(id: string): Promise<JobStatus> {
  return unwrap(await api.POST("/api/jobs/{id}/force", { params: { path: { id } } }), `/api/jobs/${id}/force`);
}

export async function deleteJob(id: string): Promise<void> {
  const { response } = await api.DELETE("/api/jobs/{id}", { params: { path: { id } } });
  if (!response.ok) throw new Error(`DELETE /api/jobs/${id} failed with HTTP ${response.status}`);
}

export async function getSettings(): Promise<Settings> {
  return unwrap(await api.GET("/api/settings"), "/api/settings");
}

export async function getProject(): Promise<Project> {
  return unwrap(await api.GET("/api/project"), "/api/project");
}

export async function getSubjects(): Promise<Subject[]> {
  return unwrap(await api.GET("/api/catalog/subjects"), "/api/catalog/subjects").subjects;
}

/** Artifact route URL for "View" (PDF/CSV/JSON/text), matching `pages/results/api.ts`. */
export function artifactUrl(path: string): string {
  return `/api/files/artifact?path=${encodeURIComponent(path)}`;
}

/**
 * Submit a synthetic job against the mock's fake job engine (dev-only "Submit test job" button —
 * see PARITY.md). `__mock_fast`/`__mock_fail` are mock-only escape hatches on the config body; a
 * real `tit.server` ignores unknown keys the same way `deserialize_config` ignores unrelated dict
 * entries, so this stays harmless once wired to the real backend. The cast is deliberate: this
 * body is not a valid `SimulationConfig`.
 */
export async function submitTestJob(subjectId = "ernie", fail = false): Promise<JobStatus> {
  const body = {
    kind: "sim" as const,
    config: { __mock_fast: true, __mock_fail: fail } as unknown as components["schemas"]["SimulationConfig"],
    subject_ids: [subjectId],
    tags: ["dev-test"],
  };
  return unwrap(await api.POST("/api/jobs", { body }), "/api/jobs");
}

export type Report = components["schemas"]["Report"];

/** Reports the server knows about for one subject — the Report tab resolves a job to one of these. */
export async function getReports(subject: string): Promise<Report[]> {
  return unwrap(await api.GET("/api/catalog/reports", { params: { query: { subject } } }), "/api/catalog/reports");
}

/** Same route `pages/results` embeds. Served as a full HTML document, so it needs an iframe. */
export function reportUrl(id: string): string {
  return `/api/files/report/${encodeURIComponent(id)}`;
}

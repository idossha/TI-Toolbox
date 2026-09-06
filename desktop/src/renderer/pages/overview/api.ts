/**
 * The Overview page's one catalog read.
 *
 * R1 (`desktop/IMPLEMENTATION_PLAN.md`): a single `GET /api/catalog/overview` owns every display
 * fact this page renders — presence per subject, EEG nets and leadfields, output counts, and
 * workflow readiness — so the page's request count does not grow with the project. What it
 * replaced was one `/api/catalog/subjects/{id}` per subject plus five output lists per subject
 * plus one analyses list per simulation, capped in the renderer at 25 subjects, which meant a
 * larger project rendered no counts at all.
 *
 * Detailed output discovery stays lazy and stays in Results (`pages/results/useOutputs.ts`): this
 * page carries counts, never trees or previews.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Overview = components["schemas"]["Overview"];
export type OverviewSubject = components["schemas"]["OverviewSubject"];
export type PresenceState = components["schemas"]["PresenceState"];

export async function getOverview(): Promise<Overview> {
  return unwrap(await api.GET("/api/catalog/overview"), "/api/catalog/overview");
}

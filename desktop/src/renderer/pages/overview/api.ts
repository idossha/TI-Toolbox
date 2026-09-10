/** Aggregate subject presence and output counts; project identity/storage load separately. */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Overview = components["schemas"]["Overview"];
export type OverviewSubject = components["schemas"]["OverviewSubject"];
export type PresenceState = components["schemas"]["PresenceState"];

export async function getOverview(): Promise<Overview> {
  return unwrap(await api.GET("/api/catalog/overview"), "/api/catalog/overview");
}

/**
 * Page-scoped API calls for the Settings screen. Kept local rather than added to the shared
 * `api/client.ts` (owned across many pages) — mirrors the pattern in `pages/simulator/api.ts`.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Settings = components["schemas"]["Settings"];
export type Project = components["schemas"]["Project"];
export type Capabilities = components["schemas"]["Capabilities"];
export type Version = components["schemas"]["Version"];
export async function getSettings(): Promise<Settings> {
  return unwrap(await api.GET("/api/settings"), "/api/settings");
}

export async function putSettings(settings: Settings): Promise<Settings> {
  return unwrap(await api.PUT("/api/settings", { body: settings }), "/api/settings");
}

export async function getProject(): Promise<Project> {
  return unwrap(await api.GET("/api/project"), "/api/project");
}

export async function getCapabilities(): Promise<Capabilities> {
  return unwrap(await api.GET("/api/capabilities"), "/api/capabilities");
}

export async function getVersion(): Promise<Version> {
  return unwrap(await api.GET("/api/version"), "/api/version");
}

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

export type SurferPreferences = components["schemas"]["SurferPreferences"];
export type SurferSettings = components["schemas"]["SurferSettings"];
export async function getSurferSettings(): Promise<SurferSettings> {
  return unwrap(await api.GET("/api/surfer-settings"), "/api/surfer-settings");
}
export async function putSurferSettings(settings: SurferPreferences): Promise<SurferSettings> {
  return unwrap(await api.PUT("/api/surfer-settings", { body: settings }), "/api/surfer-settings");
}

/** Optional administrator override; the toolbox supplies its bundled license automatically. */
export async function putFreeSurferLicense(text: string): Promise<SurferSettings> {
  return unwrap(await api.PUT("/api/surfer-settings/freesurfer-license", { body: { text } }), "/api/surfer-settings/freesurfer-license");
}
export async function deleteFreeSurferLicense(): Promise<SurferSettings> {
  return unwrap(await api.DELETE("/api/surfer-settings/freesurfer-license"), "/api/surfer-settings/freesurfer-license");
}

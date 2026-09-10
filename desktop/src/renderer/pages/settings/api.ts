/**
 * Page-scoped API calls for the Settings screen. Kept local rather than added to the shared
 * `api/client.ts` (owned across many pages) — mirrors the pattern in `pages/simulator/api.ts`.
 */
import { ApiError, api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Settings = components["schemas"]["Settings"];
export type Project = components["schemas"]["Project"];
export type Capabilities = components["schemas"]["Capabilities"];
export type Version = components["schemas"]["Version"];
export type TetravoxState = components["schemas"]["TetravoxState"];
export type TetravoxRelease = components["schemas"]["TetravoxRelease"];
export type TetravoxUpdates = components["schemas"]["TetravoxUpdates"];
export type TetravoxUpdateOutcome = components["schemas"]["TetravoxUpdateOutcome"];

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

// ── the embedded viewer bundle (docs/dev/HISTORY.md § 2026-09-04 (embed convergence), E1-E4) ────────────────
//
// These use `unwrapDetail`, not the shared `unwrap`: every refusal here is a sentence written for
// the person reading it ("sha256 mismatch: the download is …, expected …. Nothing was installed.",
// "That bundle speaks embed protocol 3; this version of TI-Toolbox supports protocol 1-2"), and
// `unwrap` throws them away in favour of "POST /api/tetravox/install failed with HTTP 400".

/** `unwrap`, keeping the server's own `detail` sentence as the error message. */
function unwrapDetail<T>(result: { data?: T; error?: unknown; response: Response }, path: string): T {
  if (result.response.ok && result.data !== undefined) return result.data;
  const detail = (result.error as { detail?: unknown } | undefined)?.detail;
  throw new ApiError(result.response.status, path, typeof detail === "string" ? detail : undefined);
}

//
// `/api/tetravox` is the whole picture in one read (active bundle + why, everything installed,
// the baked floor, the supported protocol range); the three mutations all answer with that same
// state, so a caller never has to re-read to know what happened.

export async function getTetravox(): Promise<TetravoxState> {
  return unwrapDetail(await api.GET("/api/tetravox"), "/api/tetravox");
}

/**
 * Never throws for "no network": the server answers 200 with `available: false` and a sentence.
 *
 * Without `refresh` this reads the cache the server's own 24 h check writes — rendering the card
 * costs no GitHub request, which matters because an unauthenticated IP gets 60 per hour.
 * `refresh: true` is what the "Check now" button sends.
 */
export async function getTetravoxUpdates(refresh = false): Promise<TetravoxUpdates> {
  return unwrapDetail(await api.GET("/api/tetravox/updates", { params: { query: { refresh } } }), "/api/tetravox/updates");
}

/** A3's switch. Off means the server still checks and reports; it just stops installing. */
export async function setTetravoxPolicy(autoUpdate: boolean): Promise<TetravoxState> {
  return unwrapDetail(await api.POST("/api/tetravox/policy", { body: { auto_update: autoUpdate } }), "/api/tetravox/policy");
}

/** Either `{ url, sha256 }` or `{ version }` resolved from the release index. */
export async function installTetravox(body: { url?: string; sha256?: string; version?: string }): Promise<TetravoxState> {
  return unwrapDetail(await api.POST("/api/tetravox/install", { body }), "/api/tetravox/install");
}

/** An installed version, or `"baked"` to roll back to the copy in the image. */
export async function activateTetravox(version: string): Promise<TetravoxState> {
  return unwrapDetail(await api.POST("/api/tetravox/activate", { body: { version } }), "/api/tetravox/activate");
}

export async function removeTetravox(version: string): Promise<TetravoxState> {
  return unwrapDetail(await api.DELETE("/api/tetravox/{version}", { params: { path: { version } } }), "/api/tetravox/{version}");
}

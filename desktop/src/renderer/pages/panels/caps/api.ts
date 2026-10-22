/** Page-scoped calls for the EEG caps panel (`/api/caps/*`, `tit/server/routes/caps.py`). */
import { api, ApiError, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";

export type CapStatus = components["schemas"]["CapStatus"];
export type CapInspection = components["schemas"]["CapInspection"];
export type CapElectrode = components["schemas"]["CapElectrode"];

export async function getAvailableCaps(subject: string): Promise<CapStatus[]> {
  const path = "/api/caps/available";
  return unwrap(await api.GET(path, { params: { query: { subject } } }), path).caps;
}

export async function warpCaps(subject: string, caps: string[], overwrite: boolean): Promise<string[]> {
  const path = "/api/caps/warp";
  const out = unwrap(await api.POST(path, { body: { subject, caps, overwrite } }), path);
  return out.written.map((w) => w.name);
}

export async function inspectNet(subject: string, net: string, compare?: string): Promise<CapInspection> {
  const path = "/api/caps/inspect";
  return unwrap(await api.GET(path, { params: { query: { subject, net, compare: compare || undefined } } }), path);
}

/**
 * The sentence a refused upload carries: the route's string `detail`, or — for a file name the
 * server's name rule refuses — FastAPI's list of rule violations, each `msg` without pydantic's
 * "Value error, " prefix. `undefined` leaves ApiError's "failed with HTTP n".
 */
function refusalDetail(body: unknown): string | undefined {
  const detail = typeof body === "object" && body !== null ? (body as { detail?: unknown }).detail : undefined;
  if (typeof detail === "string") return detail.trim() ? detail : undefined;
  if (!Array.isArray(detail)) return undefined;
  const rules = detail
    .map((item) => (typeof item === "object" && item !== null ? (item as { msg?: unknown }).msg : undefined))
    .filter((msg): msg is string => typeof msg === "string" && msg.trim() !== "")
    .map((msg) => msg.replace(/^Value error, /, ""));
  return rules.length > 0 ? rules.join("; ") : undefined;
}

/**
 * A raw-body upload, like `uploadMask` (`pages/_shared/roi/api.ts`): openapi-fetch would JSON-encode it.
 * `overwrite` replaces a project cap of the same name (the route's 409 otherwise).
 */
export async function uploadCap(file: File, overwrite = false): Promise<{ name: string; electrodes: number }> {
  const path = "/api/caps/upload";
  const response = await fetch(`${path}?name=${encodeURIComponent(file.name)}${overwrite ? "&overwrite=true" : ""}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "text/csv" },
    body: file,
  });
  if (!response.ok) {
    throw new ApiError(response.status, path, refusalDetail(await response.json().catch(() => null)));
  }
  return (await response.json()) as { name: string; electrodes: number };
}

/**
 * Whether a refused upload of `name` can be replaced: the route's 409 for a name the project's own
 * caps already use. Its other 409 — a cap the image ships — cannot be (overwrite never replaces an
 * image cap), and the panel's caps list says which of the two it was; a name the list does not know
 * yet is the project's own (an upload the list has not caught up with).
 */
export function canReplaceUpload(error: unknown, name: string, caps: readonly CapStatus[]): boolean {
  if (!(error instanceof ApiError) || error.status !== 409) return false;
  const source = caps.find((c) => c.name === name)?.source;
  return source !== "simnibs" && source !== "ti-toolbox";
}

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

/** A raw-body upload, like `uploadMask` (`pages/_shared/roi/api.ts`): openapi-fetch would JSON-encode it. */
export async function uploadCap(file: File): Promise<{ name: string; electrodes: number }> {
  const path = "/api/caps/upload";
  const response = await fetch(`${path}?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "text/csv" },
    body: file,
  });
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new ApiError(response.status, path, typeof error?.detail === "string" ? error.detail : undefined);
  }
  return (await response.json()) as { name: string; electrodes: number };
}

/**
 * Typed fetchers the ROI picker needs, kept local to `pages/_shared/roi/` rather than added to
 * `src/renderer/api/client.ts` — that file has no declared owner in the build plan's ownership
 * map and several page lanes need new endpoints concurrently, so each lane calls the shared
 * `api` (openapi-fetch) client directly instead of racing edits to a common wrapper file.
 */
import { api, unwrap, type ApiError } from "../../../api/client";
import type { components } from "../../../api/schema";

export type Atlas = components["schemas"]["Atlas"];
export type Region = components["schemas"]["Region"];

export async function getAtlases(subject: string, kind: "cortical" | "subcortical", space?: "subject" | "mni"): Promise<Atlas[]> {
  const path = "/api/catalog/atlases";
  return unwrap(await api.GET(path, { params: { query: { subject, kind, space } } }), path);
}

export async function getAtlasRegions(subject: string, atlas: string, hemi?: "lh" | "rh" | "both"): Promise<Region[]> {
  const path = "/api/catalog/atlases/regions";
  return unwrap(await api.GET(path, { params: { query: { subject, atlas, hemi } } }), path);
}

export type { ApiError };

export type Roi = components["schemas"]["Roi"];

/** Saved ROI CSVs for a subject — the `saved` picker mode's list (ex/mEx targets). */
export async function getRois(subject: string): Promise<Roi[]> {
  const path = "/api/catalog/rois";
  return unwrap(await api.GET(path, { params: { query: { subject } } }), path);
}

export async function saveRoi(subject: string, roi: Roi): Promise<Roi> {
  const path = "/api/catalog/rois";
  return unwrap(await api.POST(path, { params: { query: { subject } }, body: roi }), path);
}

export async function deleteRoi(subject: string, name: string): Promise<void> {
  const path = "/api/catalog/rois/{name}";
  const { error, response } = await api.DELETE(path, { params: { path: { name }, query: { subject } } });
  if (error || !response.ok) throw new Error(`DELETE ${path} failed (${response.status})`);
}

export async function uploadMask(file: File, subject: string, signal?: AbortSignal): Promise<string> {
  if (!/\.nii(\.gz)?$/i.test(file.name)) throw new Error("Choose a .nii or .nii.gz mask.");
  const response = await fetch(`/api/files/mask?name=${encodeURIComponent(file.name)}&subject=${encodeURIComponent(subject)}`, {
    method: "POST", signal, credentials: "same-origin", headers: { "Content-Type": "application/octet-stream" }, body: file,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof error?.detail === "string" ? error.detail : `Could not import mask (${response.status}).`);
  }
  const result = await response.json() as { path: string };
  return result.path;
}

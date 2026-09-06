/** Page-scoped API calls for the Help screen. Kept local — see pages/simulator/api.ts. */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Version = components["schemas"]["Version"];

export async function getVersion(): Promise<Version> {
  return unwrap(await api.GET("/api/version"), "/api/version");
}

/** True if the offline docs bundle is present at `/docs` (release-build.yml copies it into the
 * image next to the UI bundle; not present in `npm run dev` or against the mock server). */
export async function docsAvailable(): Promise<boolean> {
  try {
    const res = await fetch("/docs/", { method: "GET" });
    return res.ok;
  } catch {
    return false;
  }
}

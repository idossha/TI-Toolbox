/** Page-scoped API calls for the Help screen. Kept local — see pages/simulator/api.ts. */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Version = components["schemas"]["Version"];

export async function getVersion(): Promise<Version> {
  return unwrap(await api.GET("/api/version"), "/api/version");
}

/** The published documentation website (`docs/_config.yml`: `url` + `baseurl`, capital-T repo
 * name). The Docs tab frames this, never a path on the app's own origin — the server's static
 * route is an SPA catch-all, so `/docs/` would answer with the app's own `index.html`. */
export const DOCS_SITE = "https://idossha.github.io/TI-Toolbox/";

/** True if the docs website answers. `no-cors` because we only need reachability, not the body;
 * an opaque response resolves, an offline machine (or a blocked origin) rejects. */
export async function docsSiteReachable(timeoutMs = 5_000): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    await fetch(DOCS_SITE, { mode: "no-cors", cache: "no-store", signal: ctrl.signal });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

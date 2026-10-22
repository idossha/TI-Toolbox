/**
 * Page-scoped API calls for the Viewer screen. Kept local rather than added to the shared
 * `api/client.ts` (owned across many pages; every lane needing catalog v1/viewer/jobs endpoints
 * would otherwise collide editing the same file) — mirrors `pages/simulator/api.ts`.
 *
 * `openView` resolves a selection and saves a native scene in the project. The desktop main
 * process maps its container path to the host and launches TetraVox separately.
 */
import { api, ApiError, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type ViewerOpen = components["schemas"]["ViewerOpen"];

export type ViewKind = "subject" | "simulation" | "analysis" | "group" | "custom";
export type Space = "subject" | "mni";

export interface ViewQuery {
  subject?: string;
  simulation?: string;
  space?: Space;
  field?: string;
  analysis?: string;
  /**
   * Which atlas to overlay (R5). Optional on the wire and optional here: absent means the server
   * keeps choosing, which is exactly what every caller before this parameter existed did.
   */
  atlas?: string;
  roi?: string;
  path?: string;
}

/**
 * Resolve this selection into a scene, and write the scene file beside the project.
 *
 * `scene` uses native file paths; `path` identifies the saved scene inside the container and
 * `host_path` identifies it on the host. Native launches use `path` through the desktop bridge.
 */
export interface OpenOptions {
  /**
   * VM2 — the scene's datasets, in order, as container paths. **Authoritative when given.**
   * Absent means the view type decides, exactly as it did before this parameter existed.
   */
  files?: string[];
  /** Resolve and answer; write nothing. The list's whole mechanism. */
  dry_run?: boolean;
  /**
   * Abort this resolve when it is superseded.
   *
   * A person changing Field walks through the intermediate values of a `<select>`, and each one
   * used to start a resolve that nobody could stop. The last one to *answer* won, which is not
   * the same as the last one asked — a slow earlier request could land after a fast later one and
   * repaint the card with a list for a selection no longer on screen.
   */
  signal?: AbortSignal;
}

export async function openView(kind: ViewKind, query: ViewQuery, options: OpenOptions = {}): Promise<ViewerOpen> {
  const body: Record<string, unknown> = { kind, ...query };
  // Absent, not empty: the server's compatibility guarantee is stated about an *absent* file
  // list, and sending one on every Open would step outside the guarantee for no gain.
  if (options.files) body.files = options.files;
  if (options.dry_run) body.dry_run = true;
  return unwrap(await api.POST("/api/view/open", { body: body as never, signal: options.signal }), "/api/view/open");
}

/**
 * What this selection resolves to — the same endpoint an Open uses, with `dry_run`.
 *
 * Deliberately the *same* route rather than a second read-only one: a list built by different
 * code from the thing it opens is a list that can be wrong, and the one moment this page must not
 * be wrong is the moment before another application's window covers someone's work.
 */
export async function previewView(
  kind: ViewKind,
  query: ViewQuery,
  files?: string[],
  signal?: AbortSignal,
): Promise<ViewerOpen> {
  return openView(kind, query, { files, dry_run: true, signal });
}

export type ViewerCandidate = components["schemas"]["ViewerCandidate"];

/** Everything the subject (and simulation) offers the "+ Add…" picker. A read. */
export async function getCandidates(subject?: string, simulation?: string, space?: Space): Promise<ViewerCandidate[]> {
  return unwrap(await api.GET("/api/viewer/candidates", { params: { query: { subject, simulation, space } } }), "/api/viewer/candidates")
    .candidates;
}

// ── the composition tree and saved scenes ───────────────────────────────────────────────────────
//
// The tree is "a continuous integrated thing" (maintainer, 2026-09-07) — subject, then branches for
// anatomy, simulations and analyses. A saved scene is what a person was looking at, in TetraVox's
// own format; the TetraVox app writes it through the desktop bridge, and this page lists, reads
// and deletes it.

export type ViewerTree = components["schemas"]["ViewerTree"];
export type SavedScene = components["schemas"]["SavedScene"];

/** What this subject offers the tree. `simulations` narrows which analyses are listed. */
export async function getTree(subject?: string, space?: Space, simulations?: string[]): Promise<ViewerTree> {
  return unwrap(
    await api.GET("/api/viewer/tree", { params: { query: { subject, space, simulations } } }),
    "/api/viewer/tree",
  );
}

export async function getSavedScenes(): Promise<SavedScene[]> {
  return unwrap(await api.GET("/api/viewer/scenes", {}), "/api/viewer/scenes").scenes;
}

export async function readSavedScene(name: string): Promise<Record<string, unknown>> {
  const body = unwrap(await api.GET("/api/viewer/scenes/{name}", { params: { path: { name } } }), `/api/viewer/scenes/${name}`);
  return body.scene as Record<string, unknown>;
}

export async function deleteSavedScene(name: string): Promise<void> {
  const result = await api.DELETE("/api/viewer/scenes/{name}", { params: { path: { name } } });
  if (!result.response.ok) {
    const error: unknown = result.error;
    const detail = error && typeof error === "object" && "detail" in error && typeof error.detail === "string" ? error.detail : "Could not delete the saved scene. Try again.";
    throw new ApiError(result.response.status, `/api/viewer/scenes/${name}`, detail);
  }
}

/** `<subject>_<sim>_<field>_<date>` — what the Save field is pre-filled with. */
export async function suggestSceneName(subject?: string, simulation?: string, field?: string): Promise<string> {
  return unwrap(
    await api.GET("/api/viewer/scenes/suggest/name", { params: { query: { subject, simulation, field } } }),
    "/api/viewer/scenes/suggest/name",
  ).name;
}

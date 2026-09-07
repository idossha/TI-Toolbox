/**
 * Page-scoped API calls for the Viewer screen. Kept local rather than added to the shared
 * `api/client.ts` (owned across many pages; every lane needing catalog v1/viewer/jobs endpoints
 * would otherwise collide editing the same file) — mirrors `pages/simulator/api.ts`.
 *
 * v3 (D3, `docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)`): `POST /api/viewers/{freeview,gmsh}` are gone
 * from the server along with X11 itself.
 *
 * VE (`docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)`): `openView` resolves the scene once and
 * answers with both addressings of it — `view`, whose dataset paths are `/api/files/raw/...` URLs
 * and which is what the page posts into the embed's iframe, and `scene`, whose paths are the
 * host's and which is the document written to disk. There is no launch and no bridge: the viewer
 * is served by the same origin that served this page.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Subject = components["schemas"]["Subject"];
export type SubjectDetail = components["schemas"]["SubjectDetail"];
export type SimulationDetail = components["schemas"]["SimulationDetail"];
export type Analysis = components["schemas"]["Analysis"];
export type Atlas = components["schemas"]["Atlas"];
export type ViewSpec = components["schemas"]["ViewSpec"];
export type ViewLayer = components["schemas"]["ViewLayer"];
export type Capabilities = components["schemas"]["Capabilities"];
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

export async function getView(kind: ViewKind, query: ViewQuery): Promise<ViewSpec> {
  return unwrap(await api.GET("/api/view/{kind}", { params: { path: { kind }, query } }), `/api/view/${kind}`);
}

/**
 * Resolve this selection into a scene, and write the scene file beside the project.
 *
 * `view` is posted to the iframe; `scene` and `host_path` describe the file on disk, which is the
 * export path and the sentence the page shows a person. Both come from one resolution, so the
 * picture on screen and the file cannot describe different sets of datasets.
 */
export interface OpenOptions {
  /**
   * VM2 — the scene's datasets, in order, as container paths. **Authoritative when given.**
   * Absent means the view type decides, exactly as it did before this parameter existed.
   */
  files?: string[];
  /** Resolve and answer; write nothing. The list's whole mechanism. */
  dry_run?: boolean;
}

export async function openView(kind: ViewKind, query: ViewQuery, options: OpenOptions = {}): Promise<ViewerOpen> {
  const body: Record<string, unknown> = { kind, ...query };
  // Absent, not empty: the server's compatibility guarantee is stated about an *absent* file
  // list, and sending one on every Open would step outside the guarantee for no gain.
  if (options.files) body.files = options.files;
  if (options.dry_run) body.dry_run = true;
  return unwrap(await api.POST("/api/view/open", { body: body as never }), "/api/view/open");
}

/**
 * What this selection resolves to — the same endpoint an Open uses, with `dry_run`.
 *
 * Deliberately the *same* route rather than a second read-only one: a list built by different
 * code from the thing it opens is a list that can be wrong, and the one moment this page must not
 * be wrong is the moment before another application's window covers someone's work.
 */
export async function previewView(kind: ViewKind, query: ViewQuery, files?: string[]): Promise<ViewerOpen> {
  return openView(kind, query, { files, dry_run: true });
}

export type ViewerCandidate = components["schemas"]["ViewerCandidate"];

/** Everything the subject (and simulation) offers the "+ Add…" picker. A read. */
export async function getCandidates(subject?: string, simulation?: string, space?: Space): Promise<ViewerCandidate[]> {
  return unwrap(await api.GET("/api/viewer/candidates", { params: { query: { subject, simulation, space } } }), "/api/viewer/candidates")
    .candidates;
}

export type ViewerPreset = components["schemas"]["ViewerPreset"];

export async function getPresets(): Promise<ViewerPreset[]> {
  return unwrap(await api.GET("/api/viewer/presets", {}), "/api/viewer/presets").presets;
}

export async function savePreset(preset: ViewerPreset): Promise<ViewerPreset> {
  return unwrap(
    await api.PUT("/api/viewer/presets/{name}", { params: { path: { name: preset.name } }, body: preset }),
    `/api/viewer/presets/${preset.name}`,
  );
}

export async function deletePreset(name: string): Promise<void> {
  await api.DELETE("/api/viewer/presets/{name}", { params: { path: { name } } });
}

export async function getSimulationsFor(subject: string): Promise<SimulationDetail[]> {
  return unwrap(await api.GET("/api/catalog/simulations", { params: { query: { subject } } }), "/api/catalog/simulations").simulations;
}

export async function getAnalyses(subject: string, simulation: string): Promise<Analysis[]> {
  return unwrap(await api.GET("/api/catalog/analyses", { params: { query: { subject, simulation } } }), "/api/catalog/analyses");
}

/**
 * Atlases the Viewer can actually overlay.
 *
 * `kind: "subcortical"` is not a neuroanatomical statement here, it is the catalog's own word for
 * the **voxel** atlases (`tit/catalog.py::atlases`) — the ones that are a NIfTI/MGZ volume and can
 * therefore become a ViewSpec layer. The cortical entries are FreeSurfer `.annot` surface
 * parcellations; offering them in this menu would give a person a choice that silently resolves
 * back to the server's default, which is worse than not offering it.
 */
export async function getAtlases(subject: string, space?: Space): Promise<Atlas[]> {
  return unwrap(
    await api.GET("/api/catalog/atlases", { params: { query: { subject, space, kind: "subcortical" } } }),
    "/api/catalog/atlases",
  );
}

export async function getSubjectDetail(id: string): Promise<SubjectDetail> {
  return unwrap(await api.GET("/api/catalog/subjects/{id}", { params: { path: { id } } }), `/api/catalog/subjects/${id}`);
}

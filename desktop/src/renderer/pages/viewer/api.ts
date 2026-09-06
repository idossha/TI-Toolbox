/**
 * Page-scoped API calls for the Viewer screen. Kept local rather than added to the shared
 * `api/client.ts` (owned across many pages; every lane needing catalog v1/viewer/jobs endpoints
 * would otherwise collide editing the same file) — mirrors `pages/simulator/api.ts`.
 *
 * v3 (D3, `dev/notes/v3-docker-streamline-plan.md`): `POST /api/viewers/{freeview,gmsh}` are gone
 * from the server along with X11 itself.
 *
 * V1/V2 (`dev/notes/v3-native-panes-external-viewer-plan.md`): nor is there an embed to post a
 * scene to. There are two calls here now — `getView` (what would be shown, for the page's own
 * summary) and `openView` (write the scene file the host-installed Tetravox app opens). The
 * launch itself is not an HTTP call at all: it is `window.tit.viewer.open`, through the Electron
 * main process, because starting an application on the host is not something a page can do and
 * not something a container can do either.
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
 * Write the scene file for this selection and answer where it went.
 *
 * The container path in `path` is what `window.tit.viewer.open` takes: the renderer never handles
 * a host path, and main maps this one through the known project mount exactly as `openPath` does.
 * `host_path` is for the sentence the page shows a person, and for browser mode, where there is
 * no main process to map anything and the file is offered as a download instead.
 */
export async function openView(kind: ViewKind, query: ViewQuery): Promise<ViewerOpen> {
  return unwrap(await api.POST("/api/view/open", { body: { kind, ...query } }), "/api/view/open");
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

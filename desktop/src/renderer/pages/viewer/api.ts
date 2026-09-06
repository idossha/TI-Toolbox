/**
 * Page-scoped API calls for the Viewer screen. Kept local rather than added to the shared
 * `api/client.ts` (owned across many pages; every lane needing catalog v1/viewer/jobs endpoints
 * would otherwise collide editing the same file) — mirrors `pages/simulator/api.ts`.
 *
 * v3 (D3, `dev/notes/v3-docker-streamline-plan.md`): there is no launch route here any more.
 * `POST /api/viewers/{freeview,gmsh}` are gone from the server along with X11 itself; the page
 * fetches a scene and hands it to the embed over `postMessage`. The only thing this module does is
 * ask the server what to show.
 */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import type { EmbedViewSpec } from "../../viewer";

export type Subject = components["schemas"]["Subject"];
export type SubjectDetail = components["schemas"]["SubjectDetail"];
export type SimulationDetail = components["schemas"]["SimulationDetail"];
export type Analysis = components["schemas"]["Analysis"];
export type Atlas = components["schemas"]["Atlas"];
export type ViewSpec = components["schemas"]["ViewSpec"];
export type ViewLayer = components["schemas"]["ViewLayer"];
export type Capabilities = components["schemas"]["Capabilities"];

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
 * The server's answer, with `scene` typed as what it actually is.
 *
 * `openapi-typescript` renders the contract's untyped `scene` object as `Record<string, never>`
 * (its rendering of "an object with no declared properties"), which is unusable — the cast is at
 * this one boundary rather than smeared through the page. The shape is real and validated
 * server-side against `contracts/tetravox-viewspec-v2.schema.json`; see
 * `dev/notes/v3-docker-streamline/w3a-server-notes.md` for the emitted document.
 */
export interface ViewResult extends Omit<ViewSpec, "scene"> {
  scene: EmbedViewSpec | null;
}

export async function getView(kind: ViewKind, query: ViewQuery): Promise<ViewResult> {
  const result = unwrap(await api.GET("/api/view/{kind}", { params: { path: { kind }, query } }), `/api/view/${kind}`);
  return { ...result, scene: (result.scene as EmbedViewSpec | null | undefined) ?? null };
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

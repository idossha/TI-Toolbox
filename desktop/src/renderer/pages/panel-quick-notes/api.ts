/** `GET|PUT /api/catalog/notes` — the same two calls the Quick notes panel made. */
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Notes = components["schemas"]["Notes"];

export async function getNotes(): Promise<Notes> {
  return unwrap(await api.GET("/api/catalog/notes"), "/api/catalog/notes");
}

export async function putNotes(text: string): Promise<Notes> {
  return unwrap(await api.PUT("/api/catalog/notes", { body: { text } }), "/api/catalog/notes");
}

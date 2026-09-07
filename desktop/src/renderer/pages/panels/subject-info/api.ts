/** Page-scoped API calls for the Subject Info panel. Kept local — see pages/simulator/api.ts. */
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";

export type SubjectInfo = components["schemas"]["SubjectInfo"];
export type FileRef = components["schemas"]["FileRef"];
export type SubjectSimulationInfo = components["schemas"]["SubjectSimulationInfo"];

/**
 * One request for the whole picture (`tit/server/routes/subject_info.py`). The Qt extension walked
 * the project directory in the GUI process; this asks the server, which is where the files are.
 */
export async function getSubjectInfo(id: string): Promise<SubjectInfo> {
  return unwrap(await api.GET("/api/subjects/{id}/info", { params: { path: { id } } }), `/api/subjects/${id}/info`);
}

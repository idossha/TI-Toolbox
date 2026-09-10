/**
 * Host-tab REST. `POST /api/system/terminate` is the only write the Host tab makes; the live
 * numbers all arrive over `ws/useSystemStream`, which this lane imports and never edits.
 */
import { ApiError, api } from "../../../api/client";

export async function terminateProcess(pid: number): Promise<void> {
  const { response } = await api.POST("/api/system/terminate", { body: { pid } });
  if (!response.ok) throw new ApiError(response.status, "/api/system/terminate");
}

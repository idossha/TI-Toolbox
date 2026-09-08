/**
 * `GET /api/system/storage` — the project's own disk usage, by output kind.
 *
 * A separate query from the `/ws/system` stream on purpose: the stream is a
 * one-second sample and this is a full walk of the project, cached on disk and
 * refreshed in a background thread. So it is polled slowly, refetched when the
 * page is opened, and kept polling only while the server says a scan is running.
 */
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, type ProjectStorage } from "../../api/client";

export type { ProjectStorage };

export async function getStorage(refresh = false): Promise<ProjectStorage> {
  const { data, response } = await api.GET("/api/system/storage", {
    params: { query: { refresh } },
  });
  if (!response.ok || !data) throw new ApiError(response.status, "/api/system/storage");
  return data as ProjectStorage;
}

/**
 * While a scan is running the answer changes; the rest of the time it changes
 * about as often as a job finishes. So the poll interval follows `scanning`
 * rather than being a compromise between the two.
 */
export function useStorage() {
  return useQuery({
    queryKey: ["system-storage"],
    queryFn: () => getStorage(false),
    refetchInterval: (query) => (query.state.data?.scanning ? 2000 : 60_000),
    staleTime: 30_000,
  });
}

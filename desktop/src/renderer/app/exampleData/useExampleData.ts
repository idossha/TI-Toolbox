/**
 * Starting an example-data download, and the error if it would not start.
 *
 * Progress is **not** here: `ExampleDataList` polls `GET /api/example-data` while anything is
 * downloading and reads each row's state straight off that one answer, so there is no per-sample
 * bookkeeping to keep in sync. All this hook owns is the POST (of one `dataset/part` id) and
 * its failure message.
 */
import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { EXAMPLE_DATA_QUERY_KEY, startExampleData } from "./api";

export function useExampleData() {
  const queryClient = useQueryClient();
  const [error, setError] = useState("");

  const start = useCallback(
    async (partId: string, force = false) => {
      setError("");
      try {
        await startExampleData(partId, force);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Could not start the download.");
        throw cause;
      } finally {
        // Pick the new `downloading` flag up at once, which is what arms the poll.
        void queryClient.invalidateQueries({ queryKey: EXAMPLE_DATA_QUERY_KEY });
      }
    },
    [queryClient],
  );

  return { start, error };
}

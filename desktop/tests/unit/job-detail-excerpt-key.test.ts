/**
 * The Summary tab's console excerpt polls `GET /api/jobs/{id}/log?tail=40` every 3 s while a job
 * runs and stops polling once it is terminal. Stopping is only correct if the excerpt is refetched
 * at that moment: otherwise the pane keeps showing the last tick's text — up to three seconds older
 * than the job — and the lines a reader opens the pane for (the final ones, the traceback) never
 * arrive, for as long as the pane stays open.
 *
 * react-query refetches on a key change, so the key must carry the live/final distinction. The Raw
 * log tab's query already did (`JobRawLog.tsx`'s `running ? "live" : "final"`); this one did not.
 */
import { describe, expect, it } from "vitest";
import { EXCERPT_LINES, excerptQueryKey } from "../../src/renderer/app/jobs-rail/JobDetailPane";

describe("Summary console excerpt key", () => {
  it("changes when the job reaches a terminal state, so the final lines are fetched once", () => {
    expect(excerptQueryKey("j1", false)).not.toEqual(excerptQueryKey("j1", true));
  });

  it("is stable while the job runs, so the 3 s poll is not restarted on every render", () => {
    expect(excerptQueryKey("j1", false)).toEqual(excerptQueryKey("j1", false));
  });

  it("is per job, and asks for the number of lines the pane says it shows", () => {
    expect(excerptQueryKey("j1", true)).not.toEqual(excerptQueryKey("j2", true));
    expect(excerptQueryKey("j1", true)).toContain(EXCERPT_LINES);
    // Still under the `job-log` prefix the delete mutation removes.
    expect(excerptQueryKey("j1", true)[0]).toBe("job-log");
    expect(excerptQueryKey("j1", true)[1]).toBe("j1");
  });
});

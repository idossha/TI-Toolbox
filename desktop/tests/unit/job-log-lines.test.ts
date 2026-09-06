import { describe, expect, it } from "vitest";
import { jobEventsToLogLines, mergeJobEvents } from "../../src/renderer/app/jobs/logLines";
import type { JobEvent } from "../../src/renderer/app/jobs/types";

function event(seq: number, overrides: Partial<JobEvent> = {}): JobEvent {
  return { seq, ts: seq, type: "log", level: "info", msg: `line ${seq}`, ...overrides };
}

describe("job log lines", () => {
  it("merges history and live events by sequence with the latest copy winning", () => {
    const history = [event(1), event(2, { msg: "stale" })];
    const live = [event(2, { msg: "live" }), event(3)];

    expect(mergeJobEvents(history, live)).toEqual([event(1), event(2, { msg: "live" }), event(3)]);
  });

  it("converts only terminal event types without mutating its input", () => {
    const events = [
      event(3, { type: "progress", msg: "not terminal output" }),
      event(1, { level: "warning" }),
      event(2, { type: "marker", level: "debug", msg: undefined }),
    ];
    const before = structuredClone(events);

    expect(jobEventsToLogLines(events)).toEqual([
      { seq: 1, level: "warning", text: "line 1" },
      { seq: 2, level: "debug", text: "" },
    ]);
    expect(events).toEqual(before);
  });
});

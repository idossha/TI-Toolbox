import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { jobEventsToLogLines, mergeJobEvents, splitLogText } from "../../src/renderer/app/jobs/logLines";
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
      { seq: 1, key: "1:0", level: "warning", text: "line 1" },
      { seq: 2, key: "2:0", level: "debug", text: "" },
    ]);
    expect(events).toEqual(before);
  });
});

/**
 * The overlap bug (maintainer's screenshot of a live `sim · 101`): "Placing Electrode:" and the
 * eight lines that follow it are ONE server event whose `msg` holds embedded newlines. The console
 * draws one item per virtual row at a fixed 18 px, so that single item painted nine lines of text
 * over the rows below it — every visual line has to be its own item.
 *
 * `tests/fixtures/simnibs_sim_events.json` is a real capture from job `abf9e53bf9b04f06` of the
 * maintainer's Dataset 000 (a TI simulation on sub-101), not a hand-written imitation.
 */
describe("one item per visual line", () => {
  const captured = JSON.parse(readFileSync(join(__dirname, "../fixtures/simnibs_sim_events.json"), "utf8")) as JobEvent[];

  it("splits a real multi-line SimNIBS event into one line each", () => {
    const electrode = captured.find((e) => (e.msg ?? "").startsWith("Placing Electrode:"));
    expect(electrode, "the capture contains the multi-line electrode chunk").toBeTruthy();
    const lines = jobEventsToLogLines([electrode as JobEvent]);
    expect(lines.map((l) => l.text)).toEqual([
      "Placing Electrode:",
      "definition: plane",
      "shape: ellipse",
      "centre: E034",
      "pos_ydir: []",
      "dimensions: [8, 8]",
      "thickness:[4, 2.0]",
      "channelnr: 1",
      "number of holes: 0",
    ]);
    // The trailing newline of the chunk is not a tenth, blank line.
    expect(lines).toHaveLength(9);
  });

  it("gives every line of the whole captured transcript its own row, and no text holds a newline", () => {
    const lines = jobEventsToLogLines(captured);
    expect(lines.length).toBeGreaterThan(captured.length);
    for (const line of lines) expect(line.text).not.toMatch(/[\n\r]/);
  });

  it("keys are unique across a transcript even though several lines share one seq", () => {
    const lines = jobEventsToLogLines(captured);
    const keys = lines.map((l) => l.key);
    expect(new Set(keys).size).toBe(lines.length);
    // The seq is deliberately NOT unique: it is the event's, and the Clear watermark compares it.
    expect(new Set(lines.map((l) => l.seq)).size).toBeLessThan(lines.length);
  });

  it("carries the event's level onto every line it produced", () => {
    const lines = jobEventsToLogLines([{ seq: 7, ts: 7, type: "log", level: "error", msg: "Traceback:\n  File \"x.py\"\nBoom" }]);
    expect(lines.map((l) => l.level)).toEqual(["error", "error", "error"]);
  });
});

describe("splitLogText", () => {
  it("treats CRLF as one break", () => {
    expect(splitLogText("a\r\nb\r\n")).toEqual(["a", "b"]);
  });

  it("collapses a bare-CR progress counter to what a terminal would have left on screen", () => {
    // charm, dcm2niix and QSIPrep all redraw a counter in place; 400 rows of "12 %" is not a log.
    expect(splitLogText("progress 1 %\rprogress 2 %\rprogress 100 %")).toEqual(["progress 100 %"]);
    expect(splitLogText("meshing\nprogress 5 %\rprogress 99 %\ndone")).toEqual(["meshing", "progress 99 %", "done"]);
  });

  it("keeps a blank line INSIDE a chunk — a traceback's separators are part of the log", () => {
    expect(splitLogText("a\n\nb\n")).toEqual(["a", "", "b"]);
  });

  it("never returns an empty list, so an empty event still occupies its row", () => {
    expect(splitLogText("")).toEqual([""]);
    expect(splitLogText("\n")).toEqual([""]);
  });

  it("leaves a long single line alone — the console scrolls sideways, it does not wrap", () => {
    const long = `/mnt/000/derivatives/SimNIBS/sub-101/${"very-long-segment/".repeat(30)}101_TDCS_1_scalar.msh`;
    expect(splitLogText(long)).toEqual([long]);
  });
});

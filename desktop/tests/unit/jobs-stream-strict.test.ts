/**
 * The jobs stream applies a failed flex run's result event, and never drops a frame silently.
 *
 * What it pins (package p08, 2026-10-22): a flex run whose every restart failed reports
 * `best_value: inf`. The server used to forward that as the bare token `Infinity`, which
 * `JSON.parse` rejects (RFC 8259 has no Infinity), and `JobsStream` swallowed the parse error, so
 * the job's result event vanished. The server now writes `null` (tests/test_flex_strict_json.py);
 * this file checks the desktop half: a result event whose outputs carry `null` lands in
 * `eventsByJob`, and a frame that is not JSON is counted in `malformedFrames` and logged.
 *
 * Expected values: the frames the test sends. The `Infinity` frame is the exact text Python's
 * `json.dumps` produced for that event before the fix.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/jobs-stream-strict.test.ts`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { JobsStream, type WebSocketLike } from "../../src/renderer/app/jobs/jobsStream";

class FakeSocket implements WebSocketLike {
  static instances: FakeSocket[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  readyState = 1;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  send() {}
  close() {}
  raw(text: string) {
    this.onmessage?.({ data: text });
  }
}

const RESULT_BEFORE_FIX =
  '{"type": "event", "job_id": "j1", "event": {"seq": 4, "ts": 1.0, "type": "result", "outputs": {"success": false, "best_value": Infinity, "best_run_index": -1}}}';

describe("JobsStream and strict JSON", () => {
  let warn: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    FakeSocket.instances = [];
    warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => warn.mockRestore());

  function started(): { stream: JobsStream; ws: FakeSocket } {
    const stream = new JobsStream({ url: "ws://x/ws/jobs", WebSocketImpl: FakeSocket });
    stream.start();
    const ws = FakeSocket.instances[0]!;
    ws.onopen?.({});
    stream.subscribeJob("j1", 0);
    return { stream, ws };
  }

  // A guard, not a red-before test: JSON.parse already read null before the fix. It pins that the
  // shape the server now sends for a failed run (null, not Infinity) is applied, not dropped.
  it("applies a failed flex result whose best_value is null", () => {
    const { stream, ws } = started();
    ws.raw(RESULT_BEFORE_FIX.replace("Infinity", "null"));
    const events = stream.getState().eventsByJob["j1"] ?? [];
    expect(events).toHaveLength(1);
    expect(events[0]!.type).toBe("result");
    expect(events[0]!.outputs).toEqual({ success: false, best_value: null, best_run_index: -1 });
    expect(stream.getState().malformedFrames ?? 0).toBe(0);
    stream.stop();
  });

  it("counts and logs a frame that is not JSON instead of dropping it silently", () => {
    const { stream, ws } = started();
    ws.raw(RESULT_BEFORE_FIX);
    expect(stream.getState().eventsByJob["j1"] ?? []).toHaveLength(0);
    expect(stream.getState().malformedFrames).toBe(1);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0]![0])).toContain("/ws/jobs: dropped a frame that is not JSON");
    // The stream keeps working: the next valid frame (same seq, resent) still lands.
    ws.raw(RESULT_BEFORE_FIX.replace("Infinity", "null"));
    expect(stream.getState().eventsByJob["j1"] ?? []).toHaveLength(1);
    expect(stream.getState().malformedFrames).toBe(1);
    stream.stop();
  });
});

/**
 * A live console must not lose the middle of a transcript.
 *
 * `useJobLogEvents` merges ONE REST snapshot of a job's events (taken when the console opened) with
 * the socket store's per-job ring. While that ring held only the last 500 events, a job that wrote
 * more than 500 further events after the snapshot left a hole between the two — every line in
 * between was gone from the console until the job finished and the final fetch healed it. Real jobs
 * are much longer than 500 events: `code/ti-toolbox/jobs/987ec23a26b4400c/events.jsonl` in Dataset
 * 000 is 7851 lines.
 */
import { describe, expect, it } from "vitest";
import { JobsStream, MAX_EVENTS_PER_JOB, type WebSocketLike } from "../../src/renderer/app/jobs/jobsStream";

class FakeSocket implements WebSocketLike {
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  readyState = 1;
  static last: FakeSocket | null = null;
  constructor() { FakeSocket.last = this; }
  send(): void {}
  close(): void {}
}

function streamOf(events: number): JobsStream {
  const stream = new JobsStream({ url: "ws://test/ws/jobs", WebSocketImpl: FakeSocket });
  stream.start();
  FakeSocket.last!.onopen?.({});
  stream.subscribeJob("j1", 0);
  for (let seq = 0; seq < events; seq++) {
    FakeSocket.last!.onmessage?.({ data: JSON.stringify({ type: "event", job_id: "j1", event: { seq, ts: seq, type: "log", msg: `line ${seq}` } }) });
  }
  return stream;
}

describe("JobsStream event retention", () => {
  it("keeps a whole real-sized transcript, so the console can bridge it to its REST snapshot", () => {
    const stream = streamOf(7851);
    const events = stream.getState().eventsByJob.j1 ?? [];
    expect(events.length).toBe(7851);
    expect(events[0]?.seq).toBe(0);
    expect(events[events.length - 1]?.seq).toBe(7850);
    stream.stop();
  });

  it("still bounds memory: the oldest events go once the cap is reached", () => {
    const stream = new JobsStream({ url: "ws://test/ws/jobs", WebSocketImpl: FakeSocket, maxEventsPerJob: 10 });
    stream.start();
    FakeSocket.last!.onopen?.({});
    stream.subscribeJob("j1", 0);
    for (let seq = 0; seq < 25; seq++) {
      FakeSocket.last!.onmessage?.({ data: JSON.stringify({ type: "event", job_id: "j1", event: { seq, ts: seq, type: "log", msg: "x" } }) });
    }
    const events = stream.getState().eventsByJob.j1 ?? [];
    expect(events.length).toBe(10);
    expect(events[0]?.seq).toBe(15);
    stream.stop();
  });

  it("caps well above any transcript a job is expected to write", () => {
    expect(MAX_EVENTS_PER_JOB).toBeGreaterThan(7851);
  });
});

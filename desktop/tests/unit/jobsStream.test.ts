import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { JobsStream, type WebSocketLike } from "../../src/renderer/app/jobs/jobsStream";
import type { JobStatus } from "../../src/renderer/app/jobs/types";

class FakeSocket implements WebSocketLike {
  static instances: FakeSocket[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  readyState = 1;
  sent: string[] = [];
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
  }
  open() {
    this.onopen?.({});
  }
  message(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
  drop() {
    this.onclose?.({});
  }
}

function job(id: string, state: JobStatus["state"] = "running"): JobStatus {
  return { id, kind: "sim", state, subject_ids: ["ernie"], created_at: "2026-01-01T00:00:00Z", artifacts: [] };
}

describe("JobsStream — REST seed on connect (ra_12 #4)", () => {
  beforeEach(() => {
    FakeSocket.instances = [];
  });
  afterEach(() => vi.useRealTimers());

  it("fills the store from the seed once the socket opens, so a job that predates the connection still shows up", async () => {
    const seed = vi.fn().mockResolvedValue([job("pre-existing")]);
    const stream = new JobsStream({ url: "ws://x/ws/jobs", WebSocketImpl: FakeSocket, seed });
    stream.start();
    expect(seed).not.toHaveBeenCalled();
    FakeSocket.instances[0]!.open();
    expect(seed).toHaveBeenCalledTimes(1);
    // seedFromRest awaits a microtask before the store updates.
    await Promise.resolve();
    await Promise.resolve();
    expect(stream.getState().jobs["pre-existing"]).toBeDefined();
    stream.stop();
  });

  it("never overwrites a job id the store already learned from a live WS message", async () => {
    let resolveSeed!: (jobs: JobStatus[]) => void;
    const seed = vi.fn(() => new Promise<JobStatus[]>((resolve) => (resolveSeed = resolve)));
    const stream = new JobsStream({ url: "ws://x/ws/jobs", WebSocketImpl: FakeSocket, seed });
    stream.start();
    const ws = FakeSocket.instances[0]!;
    ws.open();
    // A live transition arrives before the (slow) REST seed resolves.
    ws.message({ type: "job", job: job("j1", "succeeded") });
    resolveSeed([job("j1", "queued"), job("j2", "queued")]);
    await Promise.resolve();
    await Promise.resolve();
    expect(stream.getState().jobs["j1"]!.state).toBe("succeeded"); // WS wins, not clobbered
    expect(stream.getState().jobs["j2"]!.state).toBe("queued"); // gap filled from REST
    stream.stop();
  });

  it("a failed seed leaves the store untouched instead of throwing", async () => {
    const seed = vi.fn().mockRejectedValue(new Error("network down"));
    const stream = new JobsStream({ url: "ws://x/ws/jobs", WebSocketImpl: FakeSocket, seed });
    stream.start();
    FakeSocket.instances[0]!.open();
    await Promise.resolve();
    await Promise.resolve();
    expect(stream.getState().jobs).toEqual({});
    stream.stop();
  });

  it("with no seed configured, behaves exactly as before (WS-only)", () => {
    const stream = new JobsStream({ url: "ws://x/ws/jobs", WebSocketImpl: FakeSocket });
    stream.start();
    FakeSocket.instances[0]!.open();
    expect(stream.getState().jobs).toEqual({});
    stream.stop();
  });
});

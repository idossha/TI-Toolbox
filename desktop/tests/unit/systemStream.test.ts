import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SystemStream, type WebSocketLike } from "../../src/renderer/ws/systemStream";

class FakeSocket implements WebSocketLike {
  static instances: FakeSocket[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
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

const snap = (cpu: number) => ({
  ts: 1,
  cpu_percent: cpu,
  cpu_count: 4,
  mem: { total: 1, available: 1, used: 0, percent: 10 },
  disk: { total: 1, free: 1, percent: 0 },
  processes: [],
});

describe("SystemStream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeSocket.instances = [];
  });
  afterEach(() => vi.useRealTimers());

  const make = (maxSamples = 120) =>
    new SystemStream({ url: "ws://x/ws/system", WebSocketImpl: FakeSocket, maxSamples, baseDelayMs: 1000, maxDelayMs: 8000 });

  it("connects, receives samples and keeps at most maxSamples", () => {
    const stream = make(3);
    stream.start();
    const ws = FakeSocket.instances[0]!;
    expect(ws.url).toBe("ws://x/ws/system");
    expect(stream.getState().status).toBe("connecting");
    ws.open();
    expect(stream.getState().status).toBe("open");
    for (const cpu of [1, 2, 3, 4, 5]) ws.message(snap(cpu));
    expect(stream.getState().samples.map((s) => s.cpu_percent)).toEqual([3, 4, 5]);
    stream.stop();
  });

  it("reconnects with exponential backoff and resets after a successful open", () => {
    const stream = make();
    const listener = vi.fn();
    stream.subscribe(listener);
    stream.start();
    FakeSocket.instances[0]!.open();
    FakeSocket.instances[0]!.drop();
    expect(stream.getState().status).toBe("reconnecting");
    expect(stream.getState().attempt).toBe(1);
    expect(FakeSocket.instances).toHaveLength(1);

    vi.advanceTimersByTime(999);
    expect(FakeSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.instances).toHaveLength(2); // after 1 s

    FakeSocket.instances[1]!.drop();
    expect(stream.getState().attempt).toBe(2);
    vi.advanceTimersByTime(2000);
    expect(FakeSocket.instances).toHaveLength(3); // after 2 s

    FakeSocket.instances[2]!.drop();
    vi.advanceTimersByTime(4000);
    expect(FakeSocket.instances).toHaveLength(4); // after 4 s

    FakeSocket.instances[3]!.drop();
    // attempt 4 -> capped at 8 s
    vi.advanceTimersByTime(8000);
    expect(FakeSocket.instances).toHaveLength(5);
    FakeSocket.instances[4]!.drop(); // attempt 5 -> still 8 s (cap)
    vi.advanceTimersByTime(7999);
    expect(FakeSocket.instances).toHaveLength(5);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.instances).toHaveLength(6);

    FakeSocket.instances[5]!.open();
    expect(stream.getState().status).toBe("open");
    expect(stream.getState().attempt).toBe(0);
    FakeSocket.instances[5]!.drop();
    vi.advanceTimersByTime(1000); // back to the base delay
    expect(FakeSocket.instances).toHaveLength(7);
    expect(listener).toHaveBeenCalled();
    stream.stop();
  });

  it("stop closes the socket and cancels pending reconnects", () => {
    const stream = make();
    stream.start();
    FakeSocket.instances[0]!.drop();
    stream.stop();
    expect(stream.getState().status).toBe("closed");
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);

    stream.start();
    expect(FakeSocket.instances).toHaveLength(2);
    stream.stop();
    expect(FakeSocket.instances[1]!.closed).toBe(true);
  });

  it("ignores malformed messages", () => {
    const stream = make();
    stream.start();
    const ws = FakeSocket.instances[0]!;
    ws.open();
    ws.onmessage?.({ data: "{not json" });
    ws.onmessage?.({ data: new ArrayBuffer(2) });
    expect(stream.getState().samples).toHaveLength(0);
    stream.stop();
  });
});

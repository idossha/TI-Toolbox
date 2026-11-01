/**
 * The main-process job notifier reconnects after its `/ws/jobs` socket drops (G3-6).
 *
 * A bare close (server restart, sleep, a network blip) used to end notifications for the rest of
 * the session. Now the notifier reopens the same URL with a growing delay for as long as it is the
 * current session's notifier; `stopNotifyingJobCompletions` (a disconnect or a new session) ends
 * it, and a successful open resets the delay.
 *
 * Fakes: a global `WebSocket` that records every instance, and `electron` / log / settings stubs.
 * Expected values: the URL `notifyJobCompletions` builds for the session (`/ws/jobs?token=`) and
 * the rule above; delays are only bounded ("within 2 s, then later"), not retyped. Dated 2026-10-31.
 *
 * Reproduce: cd desktop && npx vitest run tests/unit/jobs-notifier-reconnect.test.ts
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("electron", () => ({ app: { isPackaged: false }, Notification: class {}, net: { fetch: vi.fn() } }));
vi.mock("../../src/main/log", () => ({ log: vi.fn() }));
vi.mock("../../src/main/settings", () => ({ readSettings: () => ({}) }));
vi.mock("../../src/main/window", () => ({ mayShowSystemUi: () => false }));

class FakeSocket {
  static instances: FakeSocket[] = [];
  listeners = new Map<string, ((ev: unknown) => void)[]>();
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  addEventListener(type: string, cb: (ev: unknown) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), cb]);
  }
  fire(type: string, ev: unknown = {}) {
    for (const cb of this.listeners.get(type) ?? []) cb(ev);
  }
  close() {
    queueMicrotask(() => this.fire("close", { code: 1000 }));
  }
}

// Imported through a variable, as main-ipc-fakes.ts imports index.ts: main/ is outside tsconfig.web.json.
const NOTIFIER = "../../src/main/jobsNotifier";
const { notifyJobCompletions, stopNotifyingJobCompletions } = (await import(/* @vite-ignore */ NOTIFIER)) as {
  notifyJobCompletions: (origin: string, token: string) => void;
  stopNotifyingJobCompletions: () => void;
};
const URL_FOR = "ws://127.0.0.1:18765/ws/jobs?token=tok";

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.stubEnv("TIT_SKIP_JOB_NOTIFICATIONS", "");
  FakeSocket.instances = [];
});

afterEach(() => {
  stopNotifyingJobCompletions();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

it("reopens the session's socket after a bare close, with a growing delay", async () => {
  notifyJobCompletions("http://127.0.0.1:18765", "tok");
  expect(FakeSocket.instances.map((s) => s.url)).toEqual([URL_FOR]);

  FakeSocket.instances[0]!.fire("close", { code: 1006 });
  await vi.advanceTimersByTimeAsync(2000);
  expect(FakeSocket.instances.map((s) => s.url), "reconnected once").toEqual([URL_FOR, URL_FOR]);

  // A second drop without an open in between waits longer than the first.
  FakeSocket.instances[1]!.fire("close", { code: 1006 });
  await vi.advanceTimersByTimeAsync(1000);
  expect(FakeSocket.instances).toHaveLength(2);
  await vi.advanceTimersByTimeAsync(60_000);
  expect(FakeSocket.instances).toHaveLength(3);

  // A successful open resets the delay.
  FakeSocket.instances[2]!.fire("open");
  FakeSocket.instances[2]!.fire("close", { code: 1006 });
  await vi.advanceTimersByTimeAsync(2000);
  expect(FakeSocket.instances).toHaveLength(4);
});

it("does not reconnect once the session's notifier is stopped or replaced", async () => {
  notifyJobCompletions("http://127.0.0.1:18765", "tok");
  const first = FakeSocket.instances[0]!;
  stopNotifyingJobCompletions();
  first.fire("close", { code: 1006 });
  await vi.advanceTimersByTimeAsync(120_000);
  expect(FakeSocket.instances).toHaveLength(1);

  // A drop, then a stop while the retry is pending: the retry never fires.
  notifyJobCompletions("http://127.0.0.1:18765", "tok");
  FakeSocket.instances[1]!.fire("close", { code: 1006 });
  stopNotifyingJobCompletions();
  await vi.advanceTimersByTimeAsync(120_000);
  expect(FakeSocket.instances).toHaveLength(2);
});

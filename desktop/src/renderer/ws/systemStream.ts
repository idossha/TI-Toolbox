/**
 * /ws/system consumer with reconnect + exponential backoff and a bounded sample ring.
 * Timer and WebSocket implementations are injectable so it is unit-testable with fake timers.
 */
import type { SystemSnapshot } from "../api/client";

export type StreamStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface SystemStreamState {
  status: StreamStatus;
  samples: SystemSnapshot[];
  /** Consecutive failed attempts since the last successful open. */
  attempt: number;
  lastError?: string;
}

export interface WebSocketLike {
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: unknown) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  close(): void;
}

export interface SystemStreamOptions {
  url: string;
  maxSamples?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  WebSocketImpl?: new (url: string) => WebSocketLike;
}

export class SystemStream {
  private readonly url: string;
  private readonly maxSamples: number;
  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly WebSocketImpl: new (url: string) => WebSocketLike;
  private socket: WebSocketLike | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;
  private state: SystemStreamState = { status: "idle", samples: [], attempt: 0 };
  private readonly listeners = new Set<() => void>();

  constructor(opts: SystemStreamOptions) {
    this.url = opts.url;
    this.maxSamples = opts.maxSamples ?? 120;
    this.baseDelayMs = opts.baseDelayMs ?? 1000;
    this.maxDelayMs = opts.maxDelayMs ?? 30_000;
    this.WebSocketImpl = opts.WebSocketImpl ?? (WebSocket as unknown as new (url: string) => WebSocketLike);
  }

  getState(): SystemStreamState {
    return this.state;
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Delay before reconnect attempt number `attempt` (1-based). */
  delayFor(attempt: number): number {
    return Math.min(this.baseDelayMs * 2 ** Math.max(0, attempt - 1), this.maxDelayMs);
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.open();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const s = this.socket;
    this.socket = null;
    if (s) {
      s.onclose = null;
      s.onerror = null;
      s.onmessage = null;
      s.onopen = null;
      s.close();
    }
    this.set({ status: "closed" });
  }

  private set(patch: Partial<SystemStreamState>): void {
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l();
  }

  private open(): void {
    this.set({ status: this.state.attempt === 0 ? "connecting" : "reconnecting" });
    let socket: WebSocketLike;
    try {
      socket = new this.WebSocketImpl(this.url);
    } catch (err) {
      this.scheduleReconnect(err instanceof Error ? err.message : String(err));
      return;
    }
    this.socket = socket;
    socket.onopen = () => this.set({ status: "open", attempt: 0, lastError: undefined });
    socket.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      let snapshot: SystemSnapshot;
      try {
        snapshot = JSON.parse(ev.data) as SystemSnapshot;
      } catch {
        return;
      }
      const samples = [...this.state.samples, snapshot];
      if (samples.length > this.maxSamples) samples.splice(0, samples.length - this.maxSamples);
      this.set({ samples });
    };
    socket.onerror = () => {
      /* the close event that follows carries the reconnect */
    };
    socket.onclose = () => {
      if (this.socket === socket) this.socket = null;
      this.scheduleReconnect("connection closed");
    };
  }

  private scheduleReconnect(reason: string): void {
    if (this.stopped) return;
    const attempt = this.state.attempt + 1;
    this.set({ status: "reconnecting", attempt, lastError: reason });
    this.timer = setTimeout(() => {
      this.timer = null;
      if (!this.stopped) this.open();
    }, this.delayFor(attempt));
  }
}

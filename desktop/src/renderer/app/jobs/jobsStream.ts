/**
 * `/ws/jobs` consumer with reconnect + exponential backoff, mirroring
 * `renderer/ws/systemStream.ts`'s tested shape (same constructor/timer injection points, same
 * backoff formula) so the two streams behave identically to a user watching the connection dot.
 */
import type { JobEvent, JobStatus, JobsWsClientMessage, JobsWsServerMessage } from "./types";

export type JobsStreamStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface JobsStreamState {
  status: JobsStreamStatus;
  jobs: Record<string, JobStatus>;
  eventsByJob: Record<string, JobEvent[]>;
  attempt: number;
  lastError?: string;
}

export interface WebSocketLike {
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: unknown) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  readyState: number;
  send(data: string): void;
  close(): void;
}

export interface JobsStreamOptions {
  url: string;
  maxEventsPerJob?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  WebSocketImpl?: new (url: string) => WebSocketLike;
  /**
   * `GET /api/jobs` (or an equivalent), called once per successful connect so jobs that existed
   * before this socket opened (and so never earned a `job` WS message this session) still show
   * up — otherwise the rail and any other consumer of this store start empty even when the
   * server already has running jobs (ra_12 #4). REST never overwrites a job id the store already
   * has from a live WS message; it only fills in ids the store doesn't know about yet.
   */
  seed?: () => Promise<JobStatus[]>;
}

const OPEN = 1;

export class JobsStream {
  private readonly url: string;
  private readonly maxEventsPerJob: number;
  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly WebSocketImpl: new (url: string) => WebSocketLike;
  private readonly seed?: () => Promise<JobStatus[]>;
  private socket: WebSocketLike | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;
  /** Jobs the app currently wants events for (job id -> next seq to resume from). Re-sent as one
   * `subscribe` message on every (re)connect, since the server does not remember subscriptions
   * across a dropped socket. */
  private readonly wanted = new Map<string, number>();
  private state: JobsStreamState = { status: "idle", jobs: {}, eventsByJob: {}, attempt: 0 };
  private readonly listeners = new Set<() => void>();

  constructor(opts: JobsStreamOptions) {
    this.url = opts.url;
    this.maxEventsPerJob = opts.maxEventsPerJob ?? 500;
    this.baseDelayMs = opts.baseDelayMs ?? 1000;
    this.maxDelayMs = opts.maxDelayMs ?? 30_000;
    this.WebSocketImpl = opts.WebSocketImpl ?? (WebSocket as unknown as new (url: string) => WebSocketLike);
    this.seed = opts.seed;
  }

  getState(): JobsStreamState {
    return this.state;
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

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

  /** Start (or resume, from `sinceSeq`) receiving events for one job. */
  subscribeJob(jobId: string, sinceSeq = 0): void {
    this.wanted.set(jobId, sinceSeq);
    this.send({ subscribe: { [jobId]: sinceSeq } });
  }

  /** Stop receiving events for one job and drop its buffered event ring. */
  unsubscribeJob(jobId: string): void {
    this.wanted.delete(jobId);
    this.send({ unsubscribe: [jobId] });
    const eventsByJob = { ...this.state.eventsByJob };
    delete eventsByJob[jobId];
    this.set({ eventsByJob });
  }

  private send(msg: JobsWsClientMessage): void {
    if (this.socket && this.socket.readyState === OPEN) this.socket.send(JSON.stringify(msg));
  }

  private set(patch: Partial<JobsStreamState>): void {
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
    socket.onopen = () => {
      this.set({ status: "open", attempt: 0, lastError: undefined });
      if (this.wanted.size > 0) this.send({ subscribe: Object.fromEntries(this.wanted) });
      void this.seedFromRest();
    };
    socket.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      let msg: JobsWsServerMessage;
      try {
        msg = JSON.parse(ev.data) as JobsWsServerMessage;
      } catch {
        return;
      }
      if (msg.type === "job") {
        this.set({ jobs: { ...this.state.jobs, [msg.job.id]: msg.job } });
      } else if (msg.type === "event") {
        const existing = this.state.eventsByJob[msg.job_id] ?? [];
        const events = [...existing, msg.event];
        if (events.length > this.maxEventsPerJob) events.splice(0, events.length - this.maxEventsPerJob);
        this.set({ eventsByJob: { ...this.state.eventsByJob, [msg.job_id]: events } });
      }
    };
    socket.onerror = () => {
      /* the close event that follows carries the reconnect */
    };
    socket.onclose = () => {
      if (this.socket === socket) this.socket = null;
      this.scheduleReconnect("connection closed");
    };
  }

  /** Best-effort: a failed seed leaves the store exactly as it was (the WS stream is still the
   * source of truth once messages arrive), so errors are swallowed rather than surfaced. */
  private async seedFromRest(): Promise<void> {
    if (!this.seed) return;
    let fetched: JobStatus[];
    try {
      fetched = await this.seed();
    } catch {
      return;
    }
    const jobs = { ...this.state.jobs };
    let changed = false;
    for (const job of fetched) {
      if (!(job.id in jobs)) {
        jobs[job.id] = job;
        changed = true;
      }
    }
    if (changed) this.set({ jobs });
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

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
   * server already has running jobs (ra_12 #4).
   *
   * The response is treated as the AUTHORITATIVE snapshot, not as a set of gap-fillers: known
   * ids are replaced and ids missing from it are dropped. Only adding unknown ids left a job
   * that finished while the socket was down stuck on "running" forever, and a job deleted in
   * the meantime visible forever, because no WS message for either was ever going to arrive.
   * The one thing the snapshot does not overwrite is a job the live stream touched while the
   * request was in flight — that message is strictly newer than the snapshot.
   */
  seed?: () => Promise<JobStatus[]>;
}

const OPEN = 1;

/** Reference-equal per id, so an unchanged snapshot does not wake every subscriber. */
function sameJobs(a: Record<string, JobStatus>, b: Record<string, JobStatus>): boolean {
  const keys = Object.keys(a);
  if (keys.length !== Object.keys(b).length) return false;
  return keys.every((k) => a[k] === b[k]);
}

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
  /** Job ids the WS stream touched since the in-flight seed request was issued; null when no
   * seed is in flight. These are newer than the snapshot and survive reconciliation. */
  private liveSinceSeed: Set<string> | null = null;
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
        this.liveSinceSeed?.add(msg.job.id);
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
    const live = new Set<string>();
    this.liveSinceSeed = live;
    let fetched: JobStatus[];
    try {
      fetched = await this.seed();
    } catch {
      return;
    } finally {
      if (this.liveSinceSeed === live) this.liveSinceSeed = null;
    }
    const jobs: Record<string, JobStatus> = {};
    for (const job of fetched) jobs[job.id] = job;
    // A job the stream reported while the request was in flight is newer than the snapshot,
    // whether or not the snapshot mentions it (it may have been submitted after the query ran).
    for (const id of live) {
      const known = this.state.jobs[id];
      if (known) jobs[id] = known;
    }
    if (!sameJobs(this.state.jobs, jobs)) this.set({ jobs });
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

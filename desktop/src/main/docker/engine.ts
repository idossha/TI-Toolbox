/**
 * A small, dependency-free, typed Docker Engine API client — Node stdlib `http` over the Unix
 * socket / Windows named pipe `discover.ts` resolves, never dockerode and never the `docker` CLI
 * (D4, `docs/dev/DECISIONS.md § 2026-09-03 (One Docker image and a real development loop)`: `discover.ts`'s own `docker context inspect`
 * call is the only CLI use left anywhere in the app -- the `dockerCli.ts` module this comment
 * used to point at is deleted). `http.request({ socketPath })`
 * speaks HTTP/1.1 over a Unix domain socket with no extra dependency (Node's own long-standing
 * `net`/`http` support), and the same option accepts a Windows named-pipe path — this is exactly
 * the mechanism dockerode's own transport (`docker-modem`) is built on (r5-docker-integration.md
 * §3(a)), so building it by hand here removes dockerode's dependency surface (`docker-modem`,
 * `tar-fs`, `protobufjs` — the last one exists only for BuildKit support this client never uses)
 * without losing anything this program needs.
 *
 * Covers exactly what the stack lifecycle (`../stack.ts`, `scripts/devStack.ts`) and the GPU probe
 * call on it: `/version`, `POST /images/create` (NDJSON pull progress), container
 * start/stop/remove, and `GET .../logs` (8-byte-multiplexed demux, via `frames.ts`). Creating,
 * inspecting and listing containers, images, networks and volumes go through `./stackApi.ts` on the
 * same connection. No `exec`/attach-hijack — v3 dropped the in-container GUI exec entirely
 * (r5 §1.2), so nothing in this program needs it.
 *
 * API version negotiation: `version()` hits the always-unversioned `GET /version`, reads
 * `ApiVersion` from the response, and every subsequent call is prefixed `/v<ApiVersion>/...`
 * (Docker negotiates the highest mutually-supported version this way — docs.docker.com/reference/
 * api/engine/ — so trusting the daemon's own reported `ApiVersion` string verbatim is correct,
 * not a guess; r5's "target API ≥ 1.41, don't chase 1.55 exactly" advice is about what floor to
 * *require*, not what to request, which negotiation already handles).
 */

import * as http from "node:http";
import type { DockerConnection } from "./discover";
import { LogFrameDecoder, NdjsonDecoder, type LogFrame } from "./frames";
import { IMAGE_PLATFORM } from "../../shared/composeFile";

export type { DockerConnection } from "./discover";
export type { LogFrame, LogStreamName } from "./frames";

const DEFAULT_TIMEOUT_MS = 10_000;
/** `0` means "no timeout" — used for long-lived streaming/blocking calls (pull, logs follow, stop). */
const NO_TIMEOUT = 0;

export type DockerErrorKind =
  | "not-installed"
  | "not-running"
  | "socket-permission"
  | "unsupported-engine"
  | "timeout"
  | "not-found" // HTTP 404
  | "conflict" // HTTP 409
  | "bad-request" // HTTP 400
  | "server-error" // HTTP 5xx
  | "unknown";

export class DockerEngineError extends Error {
  readonly kind: DockerErrorKind;
  readonly statusCode: number | undefined;

  constructor(kind: DockerErrorKind, message: string, statusCode?: number) {
    super(message);
    this.name = "DockerEngineError";
    this.kind = kind;
    this.statusCode = statusCode;
  }
}

function classifyNodeError(err: NodeJS.ErrnoException, conn: DockerConnection): DockerErrorKind {
  switch (err.code) {
    case "ENOENT":
      // A Unix socket file that does not exist means no engine was ever installed here (discovery
      // already checked the well-known paths). A Windows named pipe that does not exist means
      // Docker Desktop is not running: the pipe is created by its backend at start and removed at
      // quit, and discovery only hands over a pipe that answered `/_ping` moments earlier.
      return conn.kind === "npipe" ? "not-running" : "not-installed";
    case "ECONNREFUSED":
      return "not-running";
    case "EACCES":
      return "socket-permission";
    case "ETIMEDOUT":
      return "timeout";
    default:
      return "unknown";
  }
}

function classifyStatusCode(statusCode: number): DockerErrorKind {
  if (statusCode === 404) return "not-found";
  if (statusCode === 409) return "conflict";
  if (statusCode === 400) return "bad-request";
  if (statusCode >= 500) return "server-error";
  return "unknown";
}

async function readAll(stream: NodeJS.ReadableStream): Promise<Buffer> {
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks);
}

function apiErrorFromBody(statusCode: number, body: string): DockerEngineError {
  let message = body || `HTTP ${statusCode}`;
  try {
    const parsed = JSON.parse(body) as { message?: string };
    if (parsed?.message) message = parsed.message;
  } catch {
    // body wasn't JSON — keep the raw text, still useful in an error message.
  }
  return new DockerEngineError(classifyStatusCode(statusCode), message, statusCode);
}

interface RequestOptions {
  method: string;
  path: string;
  query?: Record<string, string | number | boolean | undefined>;
  headers?: Record<string, string>;
  body?: Buffer | string;
  /** 0 disables the request timeout entirely (long-lived streams). Default `DEFAULT_TIMEOUT_MS`. */
  timeoutMs?: number;
}

interface RawResponse {
  statusCode: number;
  headers: http.IncomingHttpHeaders;
  stream: http.IncomingMessage;
}

function buildQuery(query?: RequestOptions["query"]): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined) continue;
    params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

/** One raw HTTP round trip over the connection; resolves as soon as headers arrive (body streams). */
function rawRequest(conn: DockerConnection, opts: RequestOptions): Promise<RawResponse> {
  return new Promise((resolve, reject) => {
    const path = opts.path + buildQuery(opts.query);
    const headers: http.OutgoingHttpHeaders = { ...opts.headers };
    let bodyBuf: Buffer | undefined;
    if (opts.body !== undefined) {
      bodyBuf = Buffer.isBuffer(opts.body) ? opts.body : Buffer.from(opts.body);
      headers["Content-Type"] = headers["Content-Type"] ?? "application/json";
      headers["Content-Length"] = String(bodyBuf.length);
    }

    const base: http.RequestOptions =
      conn.kind === "tcp" ? { host: conn.host, port: conn.port } : { socketPath: conn.socketPath };
    const req = http.request({ ...base, method: opts.method, path, headers }, (res) => {
      resolve({ statusCode: res.statusCode ?? 0, headers: res.headers, stream: res });
    });

    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    if (timeoutMs !== NO_TIMEOUT) {
      req.setTimeout(timeoutMs, () => req.destroy(Object.assign(new Error(`Docker request timed out after ${timeoutMs}ms: ${opts.method} ${path}`), { code: "ETIMEDOUT" })));
    }
    req.on("error", (err) => {
      const kind = classifyNodeError(err as NodeJS.ErrnoException, conn);
      reject(new DockerEngineError(kind, `${opts.method} ${path}: ${err.message}`));
    });

    if (bodyBuf) req.end(bodyBuf);
    else req.end();
  });
}

/** Buffers the whole response and JSON-parses it; throws `DockerEngineError` on 4xx/5xx or non-JSON bodies. */
async function jsonRequest<T>(conn: DockerConnection, opts: RequestOptions): Promise<T> {
  const res = await rawRequest(conn, opts);
  const body = (await readAll(res.stream)).toString("utf8");
  if (res.statusCode >= 400) throw apiErrorFromBody(res.statusCode, body);
  if (!body.trim()) return undefined as T;
  try {
    return JSON.parse(body) as T;
  } catch {
    throw new DockerEngineError("unsupported-engine", `Non-JSON response from ${opts.method} ${opts.path} (status ${res.statusCode}): ${body.slice(0, 200)}`);
  }
}

// ---------------------------------------------------------------------------------------------
// Wire types (only the fields this client actually reads — not the full Engine API schema).
// ---------------------------------------------------------------------------------------------

export interface DockerVersionInfo {
  Version: string;
  ApiVersion: string;
  MinAPIVersion?: string;
  Os: string;
  Arch: string;
  [key: string]: unknown;
}

export interface PullProgressEvent {
  id?: string;
  status: string;
  progressDetail?: { current?: number; total?: number };
  progress?: string;
  error?: string;
  errorDetail?: { message?: string };
}

// ---------------------------------------------------------------------------------------------

export class DockerEngineClient {
  private conn: DockerConnection;
  private timeoutMs: number;
  private apiVersion: string | null = null;

  constructor(conn: DockerConnection, opts: { timeoutMs?: number } = {}) {
    this.conn = conn;
    this.timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  /** Path prefixed with the negotiated API version once known; unprefixed before the first `version()` call. */
  private vpath(path: string): string {
    return this.apiVersion ? `/v${this.apiVersion}${path}` : path;
  }

  private async ensureNegotiated(): Promise<void> {
    if (!this.apiVersion) await this.version();
  }

  /** `GET /version` — always unversioned. Also negotiates `apiVersion` for every later call. */
  async version(): Promise<DockerVersionInfo> {
    const info = await jsonRequest<DockerVersionInfo>(this.conn, { method: "GET", path: "/version", timeoutMs: this.timeoutMs });
    if (info?.ApiVersion) this.apiVersion = info.ApiVersion;
    return info;
  }

  /**
   * `POST /images/create?fromImage=...&tag=...&platform=...` — streams NDJSON pull-progress objects to
   * `onProgress` as they arrive; resolves once the stream ends. Throws `DockerEngineError` on a
   * non-2xx response *or* a `{"error": "..."}` object appearing mid-stream (Docker reports pull
   * failures — e.g. unknown tag — inside a 200-status NDJSON stream, not as an HTTP error status;
   * an HTTP-status-only check would silently swallow this).
   */
  async pullImage(image: string, tag: string, onProgress?: (event: PullProgressEvent) => void, platform = IMAGE_PLATFORM): Promise<void> {
    await this.ensureNegotiated();
    const res = await rawRequest(this.conn, {
      method: "POST",
      path: this.vpath("/images/create"),
      query: { fromImage: image, tag, platform },
      timeoutMs: NO_TIMEOUT,
    });
    if (res.statusCode >= 400) throw apiErrorFromBody(res.statusCode, (await readAll(res.stream)).toString("utf8"));

    const decoder = new NdjsonDecoder<PullProgressEvent>();
    for await (const chunk of res.stream) {
      for (const event of decoder.push(chunk as Buffer)) {
        if (event.error) throw new DockerEngineError("unknown", event.error);
        onProgress?.(event);
      }
    }
  }

  async startContainer(id: string): Promise<void> {
    await this.ensureNegotiated();
    await jsonRequest<void>(this.conn, { method: "POST", path: this.vpath(`/containers/${encodeURIComponent(id)}/start`), timeoutMs: this.timeoutMs });
  }

  async stopContainer(id: string, graceSeconds?: number): Promise<void> {
    await this.ensureNegotiated();
    await jsonRequest<void>(this.conn, {
      method: "POST",
      path: this.vpath(`/containers/${encodeURIComponent(id)}/stop`),
      query: graceSeconds !== undefined ? { t: graceSeconds } : undefined,
      timeoutMs: NO_TIMEOUT,
    });
  }

  async removeContainer(id: string, opts: { force?: boolean; volumes?: boolean } = {}): Promise<void> {
    await this.ensureNegotiated();
    await jsonRequest<void>(this.conn, {
      method: "DELETE",
      path: this.vpath(`/containers/${encodeURIComponent(id)}`),
      query: { force: opts.force, v: opts.volumes },
      timeoutMs: this.timeoutMs,
    });
  }

  /**
   * `GET /containers/{id}/logs` — demultiplexed via `LogFrameDecoder`. `follow: true` keeps the
   * generator alive until the container stops producing output and the connection closes.
   */
  async *logs(id: string, opts: { follow?: boolean; stdout?: boolean; stderr?: boolean; tail?: string; timestamps?: boolean } = {}): AsyncGenerator<LogFrame, void, void> {
    await this.ensureNegotiated();
    const res = await rawRequest(this.conn, {
      method: "GET",
      path: this.vpath(`/containers/${encodeURIComponent(id)}/logs`),
      query: {
        follow: opts.follow ?? false,
        stdout: opts.stdout ?? true,
        stderr: opts.stderr ?? true,
        tail: opts.tail,
        timestamps: opts.timestamps ?? false,
      },
      timeoutMs: NO_TIMEOUT,
    });
    if (res.statusCode >= 400) throw apiErrorFromBody(res.statusCode, (await readAll(res.stream)).toString("utf8"));

    const decoder = new LogFrameDecoder();
    for await (const chunk of res.stream) {
      for (const frame of decoder.push(chunk as Buffer)) yield frame;
    }
  }
}

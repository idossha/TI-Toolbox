/**
 * The Engine API endpoints the *stack* lifecycle needs and `engine.ts` (the N0.3 spike's job-runner
 * client) does not have: listing containers by label, creating one with a `platform` query and a
 * full `HostConfig`, inspecting one for its health state and published ports, and ensuring the
 * network and named volumes the compose file declares exist.
 *
 * A separate file rather than new methods on `DockerEngineClient` because `docker/engine.ts`,
 * `docker/discover.ts` and `docker/frames.ts` are frozen as the N0.3 spike delivered them (this
 * lane may extend `docker/` with new files, not rewrite those three). `stack.ts` therefore holds
 * both objects over the same `DockerConnection`: `DockerEngineClient` for the streaming pieces
 * already proven live against Docker 29.1.3 (`pullImage`, `logs`, start/stop/remove) and `StackApi`
 * for everything here. Folding the two together — one client, one request helper — is the obvious
 * follow-up once the spike files are unfrozen; until then the duplicated ~60 lines of transport
 * below is the cost of not editing another lane's owned files.
 *
 * Error handling matches `engine.ts` exactly: every failure is a `DockerEngineError` with the same
 * `kind` vocabulary, so `stack.ts` has one classifier to map into launcher copy.
 */

import * as http from "node:http";
import type { DockerConnection } from "./discover";
import { DockerEngineError, type DockerErrorKind } from "./engine";

const DEFAULT_TIMEOUT_MS = 10_000;

function classifyNodeError(err: NodeJS.ErrnoException): DockerErrorKind {
  switch (err.code) {
    case "ENOENT":
      return "not-installed";
    case "ECONNREFUSED":
      return "not-running";
    case "EACCES":
    case "EPERM":
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

interface RequestOptions {
  method: string;
  path: string;
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  timeoutMs?: number;
}

function buildQuery(query: RequestOptions["query"]): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined) continue;
    params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

async function request<T>(conn: DockerConnection, opts: RequestOptions): Promise<T> {
  const path = opts.path + buildQuery(opts.query);
  const payload = opts.body === undefined ? undefined : Buffer.from(JSON.stringify(opts.body));
  const raw = await new Promise<{ statusCode: number; body: string }>((resolve, reject) => {
    const base: http.RequestOptions = conn.kind === "tcp" ? { host: conn.host, port: conn.port } : { socketPath: conn.socketPath };
    const headers: http.OutgoingHttpHeaders = payload ? { "Content-Type": "application/json", "Content-Length": String(payload.length) } : {};
    const req = http.request({ ...base, method: opts.method, path, headers }, (res) => {
      const chunks: Buffer[] = [];
      res.on("data", (c: Buffer) => chunks.push(c));
      res.on("end", () => resolve({ statusCode: res.statusCode ?? 0, body: Buffer.concat(chunks).toString("utf8") }));
      res.on("error", reject);
    });
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    if (timeoutMs > 0) {
      req.setTimeout(timeoutMs, () => req.destroy(Object.assign(new Error(`Docker request timed out after ${timeoutMs}ms: ${opts.method} ${path}`), { code: "ETIMEDOUT" })));
    }
    req.on("error", (err) => reject(new DockerEngineError(classifyNodeError(err as NodeJS.ErrnoException), `${opts.method} ${path}: ${err.message}`)));
    if (payload) req.end(payload);
    else req.end();
  });

  if (raw.statusCode >= 400) {
    let message = raw.body || `HTTP ${raw.statusCode}`;
    try {
      const parsed = JSON.parse(raw.body) as { message?: string };
      if (parsed?.message) message = parsed.message;
    } catch {
      // Not JSON — the raw text is still the most useful thing to report.
    }
    throw new DockerEngineError(classifyStatusCode(raw.statusCode), message, raw.statusCode);
  }
  if (!raw.body.trim()) return undefined as T;
  try {
    return JSON.parse(raw.body) as T;
  } catch {
    throw new DockerEngineError("unsupported-engine", `Non-JSON response from ${opts.method} ${path}: ${raw.body.slice(0, 200)}`);
  }
}

// ---------------------------------------------------------------------------------------------
// Wire types (only the fields this module reads).
// ---------------------------------------------------------------------------------------------

export interface ContainerSummary {
  Id: string;
  Names: string[];
  Image: string;
  State: string;
  Status: string;
  Labels: Record<string, string>;
  Ports?: { IP?: string; PrivatePort: number; PublicPort?: number; Type: string }[];
}

export interface ContainerState {
  Id: string;
  Name: string;
  /** The reference supplied at creation (Config.Image), not the resolved image content ID. */
  image: string;
  running: boolean;
  status: string;
  exitCode: number;
  /** Docker's own healthcheck verdict, when the image/compose declares one. */
  health: "starting" | "healthy" | "unhealthy" | "none";
  /** Published host port for `containerPort/tcp` when asked for, else the first published port. */
  publishedPort: number | null;
  labels: Record<string, string>;
  /**
   * The container's own environment, parsed. This is how attaching to an already-running stack
   * recovers its port and bearer token: the container is the source of truth, so no copy of the
   * token has to be written to disk on the host at all.
   */
  env: Record<string, string>;
  /** Actual Docker mounts; environment markers alone cannot prove checkout identity. */
  mounts: { Type: string; Source: string; Destination: string }[];
}

interface InspectResponse {
  Id: string;
  Name: string;
  State: { Status: string; Running: boolean; ExitCode: number; Health?: { Status?: string } };
  Config: { Image: string; Labels?: Record<string, string>; Env?: string[] };
  Mounts?: ContainerState["mounts"];
  NetworkSettings?: { Ports?: Record<string, { HostIp: string; HostPort: string }[] | null> };
}

export class StackApi {
  private conn: DockerConnection;
  private apiVersion: string | null;

  constructor(conn: DockerConnection, apiVersion?: string) {
    this.conn = conn;
    this.apiVersion = apiVersion ?? null;
  }

  /** Every call after `version()` is prefixed with the daemon's own reported API version. */
  setApiVersion(version: string): void {
    this.apiVersion = version;
  }

  private vpath(path: string): string {
    return this.apiVersion ? `/v${this.apiVersion}${path}` : path;
  }

  /** `GET /containers/json?all=1&filters={"label":[...]}`. */
  async listContainers(labels: Record<string, string>, all = true): Promise<ContainerSummary[]> {
    const filters = { label: Object.entries(labels).map(([k, v]) => `${k}=${v}`) };
    return (
      (await request<ContainerSummary[]>(this.conn, {
        method: "GET",
        path: this.vpath("/containers/json"),
        query: { all, filters: JSON.stringify(filters) },
      })) ?? []
    );
  }

  /**
   * `POST /containers/create?name=&platform=`. `platform` has to be a query parameter — the
   * daemon ignores a `Platform` field in the body — and it is what makes an `linux/amd64` image
   * run under emulation on an Apple Silicon host without the user pre-pulling it by digest.
   */
  async createContainer(body: unknown, opts: { name: string; platform?: string }): Promise<{ Id: string; Warnings?: string[] }> {
    return request<{ Id: string; Warnings?: string[] }>(this.conn, {
      method: "POST",
      path: this.vpath("/containers/create"),
      query: { name: opts.name, platform: opts.platform },
      body,
      timeoutMs: 60_000,
    });
  }

  /** `GET /containers/{id}/json`, flattened to the handful of fields the stack cares about. */
  async inspect(id: string, containerPort?: number): Promise<ContainerState> {
    const res = await request<InspectResponse>(this.conn, { method: "GET", path: this.vpath(`/containers/${encodeURIComponent(id)}/json`) });
    const ports = res.NetworkSettings?.Ports ?? {};
    const bindings = containerPort === undefined ? Object.values(ports).find((b) => b && b.length) : ports[`${containerPort}/tcp`];
    const first = bindings?.[0];
    const env: Record<string, string> = {};
    for (const entry of res.Config.Env ?? []) {
      const eq = entry.indexOf("=");
      if (eq > 0) env[entry.slice(0, eq)] = entry.slice(eq + 1);
    }
    return {
      Id: res.Id,
      Name: res.Name.replace(/^\//, ""),
      image: res.Config.Image,
      running: res.State.Running,
      status: res.State.Status,
      exitCode: res.State.ExitCode,
      health: (res.State.Health?.Status as ContainerState["health"] | undefined) ?? "none",
      publishedPort: first ? Number(first.HostPort) : null,
      labels: res.Config.Labels ?? {},
      env,
      mounts: res.Mounts ?? [],
    };
  }

  /**
   * `DELETE /containers/{id}`. Named volumes are never removed with it — they hold cached
   * derivatives the next run wants. `force` kills a still-running container first.
   */
  async removeContainerById(id: string, force = false): Promise<void> {
    await request<unknown>(this.conn, {
      method: "DELETE",
      path: this.vpath(`/containers/${encodeURIComponent(id)}`),
      query: { force, v: false },
      timeoutMs: 60_000,
    });
  }

  /** True when the image already exists locally, so a pull can be skipped entirely (offline start). */
  async imageExists(image: string): Promise<boolean> {
    try {
      await request<unknown>(this.conn, { method: "GET", path: this.vpath(`/images/${encodeURIComponent(image)}/json`) });
      return true;
    } catch (err) {
      if (err instanceof DockerEngineError && err.kind === "not-found") return false;
      throw err;
    }
  }

  /** Creates the network if it does not already exist; returns its id. Idempotent by name. */
  async ensureNetwork(name: string, driver: string): Promise<string> {
    const existing = await request<{ Id: string; Name: string }[]>(this.conn, {
      method: "GET",
      path: this.vpath("/networks"),
      query: { filters: JSON.stringify({ name: [name] }) },
    });
    const match = (existing ?? []).find((n) => n.Name === name);
    if (match) return match.Id;
    try {
      const created = await request<{ Id: string }>(this.conn, { method: "POST", path: this.vpath("/networks/create"), body: { Name: name, Driver: driver } });
      return created.Id;
    } catch (err) {
      // A concurrent create (two windows, one project) races here; the loser sees 409 and the
      // network it wanted exists, which is the outcome it asked for.
      if (err instanceof DockerEngineError && err.kind === "conflict") return name;
      throw err;
    }
  }

  /** `POST /volumes/create` is itself idempotent by name — it returns the existing volume. */
  async ensureVolume(name: string): Promise<void> {
    await request<unknown>(this.conn, { method: "POST", path: this.vpath("/volumes/create"), body: { Name: name } });
  }
}

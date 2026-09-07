/**
 * Docker Engine endpoint discovery: `DOCKER_HOST`, then `docker context inspect --format json`
 * (the ONLY use of the `docker` CLI anywhere in this module — see `engine.ts`'s docstring for why
 * everything past this point talks the Engine API directly over the resolved socket/pipe, never
 * the CLI again), then platform well-known socket/pipe candidates in precedence order.
 *
 * Classifies a failure to find a usable endpoint into one of the kinds a future onboarding UI
 * needs distinct remediation copy for: `not-installed` (no `docker` CLI on PATH and no known
 * socket file exists — "install Docker Desktop"), `not-running` (the CLI resolves but no context/
 * socket could be found — "start Docker Desktop"), `socket-permission` and the actual liveness
 * check are necessarily surfaced later, by `engine.ts`'s own connection attempt (`EACCES`/
 * `ECONNREFUSED` on the real HTTP request) — discovery here only picks a *candidate* endpoint, it
 * never itself opens a connection to it. `unsupported-engine` covers a `DOCKER_HOST`/context value
 * this module doesn't recognize as unix/npipe/tcp at all.
 */

import { existsSync } from "node:fs";
import { execFile } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export type DockerConnectionKind = "unix" | "npipe" | "tcp";

export interface DockerConnection {
  kind: DockerConnectionKind;
  /** unix/npipe: the socket/pipe path (forward-slash form on Windows — see parseDockerHostUrl). */
  socketPath?: string;
  /** tcp only. */
  host?: string;
  port?: number;
}

export type DockerDiscoveryErrorKind = "not-installed" | "not-running" | "socket-permission" | "unsupported-engine";

export type DiscoverResult =
  | { available: true; connection: DockerConnection; source: string }
  | { available: false; kind: DockerDiscoveryErrorKind; message: string };

const DOCKER_CLI_CANDIDATES = ["/usr/local/bin/docker", "/opt/homebrew/bin/docker", "/usr/bin/docker", "/Applications/Docker.app/Contents/Resources/bin/docker"];

/**
 * Well-known `docker` CLI locations, else bare `docker` if `which`/`where` resolves it on PATH,
 * else `null`. `TIT_DOCKER_BIN_FOR_DISCOVERY` is a test-only override -- `docker context inspect`
 * (below) is the only `docker` CLI invocation left anywhere in the app (D4,
 * `docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)`; the former `dockerCli.ts` that shelled out for
 * everything else is deleted), so this module no longer shares its override env var with a
 * sibling CLI-spawning module the way it once did.
 */
export async function findDockerCli(env: NodeJS.ProcessEnv = process.env): Promise<string | null> {
  if (env.TIT_DOCKER_BIN_FOR_DISCOVERY) return env.TIT_DOCKER_BIN_FOR_DISCOVERY;
  for (const c of DOCKER_CLI_CANDIDATES) if (existsSync(c)) return c;
  try {
    await execFileAsync(process.platform === "win32" ? "where" : "which", ["docker"], { timeout: 3000 });
    return "docker";
  } catch {
    return null;
  }
}

/**
 * Parses a `DOCKER_HOST`-shaped value (`unix:///path`, `npipe://./pipe/name`, `tcp://host:port`).
 * `null` if the scheme isn't recognized. The npipe case is intentionally a plain string-strip
 * (`hostValue.replace(/^npipe:/, "")`), matching `package/src/backend/docker-manager.js:88-90`'s
 * existing `parseDockerHost` — that file fed the result straight into dockerode's `socketPath`,
 * which is Node's own `http.request({ socketPath })`/`net.connect({ path })`, i.e. the same
 * transport this client uses; keeping the identical string shape (forward slashes preserved, e.g.
 * `//./pipe/docker_engine`) means the two codebases have already validated this exact form works
 * with Node's stdlib (dockerode is not reimplementing the connect — see r5-docker-integration.md
 * §3(a)/§3(b)). UNVERIFIED here specifically: no Windows machine was available this session (see
 * REPORT.md); this parses correctly, it has not been connected on a real npipe.
 */
export function parseDockerHostUrl(value: string): DockerConnection | null {
  const trimmed = value.trim();
  if (trimmed.startsWith("npipe://")) return { kind: "npipe", socketPath: trimmed.replace(/^npipe:/, "") };
  if (trimmed.startsWith("unix://")) return { kind: "unix", socketPath: trimmed.slice("unix://".length) || "/var/run/docker.sock" };
  const tcp = trimmed.match(/^tcp:\/\/([^/:]+):(\d+)\/?$/);
  if (tcp) return { kind: "tcp", host: tcp[1] as string, port: Number(tcp[2]) };
  return null;
}

/**
 * Platform well-known candidates, in the precedence order a client should try them (r5 §3(d)):
 * Docker Desktop's own default context socket, the classic/Linux-native path, then Colima and
 * OrbStack, then Podman's two socket shapes. The Podman/rootless-Linux and Podman-machine paths
 * are included for discovery completeness only — per skeptic-3 claim #5, Podman's compat socket
 * is NOT enabled by default (`systemctl --user start podman.socket` is required first on Linux),
 * so these two entries will correctly find nothing on a stock Podman install; that is documented
 * behavior, not a bug (see REPORT.md's Podman/Colima section).
 */
export function wellKnownCandidates(platform: NodeJS.Platform = process.platform): DockerConnection[] {
  if (platform === "win32") {
    return [
      { kind: "npipe", socketPath: "//./pipe/docker_engine" },
      // Podman Desktop on Windows reportedly reuses this same pipe name (r5 §3(d), REPORTED not
      // verified) — listed for discovery completeness; classified UNVERIFIED in REPORT.md.
      { kind: "npipe", socketPath: "//./pipe/podman-machine-default" },
    ];
  }
  const home = homedir();
  const uid = typeof process.getuid === "function" ? process.getuid() : undefined;
  return [
    { kind: "unix", socketPath: join(home, ".docker", "run", "docker.sock") },
    { kind: "unix", socketPath: "/var/run/docker.sock" },
    { kind: "unix", socketPath: join(home, ".colima", "default", "docker.sock") },
    { kind: "unix", socketPath: join(home, ".orbstack", "run", "docker.sock") },
    ...(uid !== undefined ? [{ kind: "unix" as const, socketPath: `/run/user/${uid}/podman/podman.sock` }] : []),
    { kind: "unix", socketPath: join(home, ".local", "share", "containers", "podman", "machine", "podman.sock") },
  ];
}

async function contextInspect(dockerBin: string): Promise<string | null> {
  try {
    const { stdout } = await execFileAsync(dockerBin, ["context", "inspect", "--format", "json"], { timeout: 5000 });
    const parsed: unknown = JSON.parse(stdout.trim());
    const ctx = Array.isArray(parsed) ? parsed[0] : parsed;
    const host = (ctx as { Endpoints?: { docker?: { Host?: string } } } | undefined)?.Endpoints?.docker?.Host;
    return typeof host === "string" ? host : null;
  } catch {
    return null;
  }
}

/**
 * Resolves the Docker Engine endpoint for this host: `DOCKER_HOST` env var first (honored even
 * if unreachable — an explicit override always wins, matching `docker-manager.js`'s existing
 * behavior), else `docker context inspect` if a `docker` CLI is found, else the first well-known
 * socket that exists on disk (win32: the first named-pipe candidate, since a pipe can't be probed
 * with `existsSync` the way a Unix socket file can — the real liveness check happens when
 * `engine.ts` actually connects).
 */
export async function discover(env: NodeJS.ProcessEnv = process.env, platform: NodeJS.Platform = process.platform): Promise<DiscoverResult> {
  if (env.DOCKER_HOST) {
    const conn = parseDockerHostUrl(env.DOCKER_HOST);
    if (!conn) return { available: false, kind: "unsupported-engine", message: `Unrecognized DOCKER_HOST scheme: ${env.DOCKER_HOST}` };
    return { available: true, connection: conn, source: "DOCKER_HOST" };
  }

  const dockerBin = await findDockerCli(env);
  if (dockerBin) {
    const host = await contextInspect(dockerBin);
    if (host) {
      const conn = parseDockerHostUrl(host);
      if (conn) return { available: true, connection: conn, source: "docker context inspect" };
    }
  }

  if (platform === "win32") {
    const first = wellKnownCandidates(platform)[0];
    if (first) return { available: true, connection: first, source: "well-known:default-npipe" };
  } else {
    for (const candidate of wellKnownCandidates(platform)) {
      if (candidate.socketPath && existsSync(candidate.socketPath)) {
        return { available: true, connection: candidate, source: `well-known:${candidate.socketPath}` };
      }
    }
  }

  if (!dockerBin) {
    return { available: false, kind: "not-installed", message: "No `docker` CLI on PATH and no known Docker/Podman/Colima/OrbStack socket file exists on this machine." };
  }
  return { available: false, kind: "not-running", message: "`docker` CLI is installed but no Docker context or known socket resolved. Is Docker Desktop (or your engine) running?" };
}

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
 * `ECONNREFUSED` on the real HTTP request) — on macOS/Linux discovery only picks a *candidate*
 * endpoint (a Unix socket file either exists or it does not) and never opens a connection to it.
 * Windows is the exception: a named pipe cannot be probed with `existsSync`, so the win32 path
 * sends one `GET /_ping` to the context-derived pipe and, if that does not answer, to each
 * well-known Docker Desktop pipe in turn (`pingEndpoint`). Measured 2026-09-22 on a Windows 11 /
 * Docker Desktop 4.60 / WSL2 machine: the active context was `desktop-linux`
 * (`npipe:////./pipe/dockerDesktopLinuxEngine`), the old `npipe:`-only strip left a four-slash
 * pipe path Node rejects with ENOENT, and the app told the user Docker was not installed — while
 * both `//./pipe/dockerDesktopLinuxEngine` and `//./pipe/docker_engine` answered `/_ping` with 200.
 * `unsupported-engine` covers a `DOCKER_HOST`/context value this module doesn't recognize as
 * unix/npipe/tcp at all.
 */

import { existsSync } from "node:fs";
import { execFile } from "node:child_process";
import * as http from "node:http";
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
 * Where Docker Desktop for Windows puts `docker.exe`: its install directory and the per-version
 * shim directory it adds to the *machine* PATH. Checked explicitly because a Start-Menu-launched
 * Electron inherits the PATH Explorer had at logon — install Docker Desktop, then launch the app
 * without signing out, and `where docker` fails although the CLI is right there. v2's launcher
 * (`package/src/backend/env.js`'s `ensurePathEnv`) appended exactly these two directories for the
 * same reason.
 */
export function windowsDockerCliCandidates(env: NodeJS.ProcessEnv = process.env): string[] {
  const programFiles = env.ProgramFiles || env.PROGRAMFILES || "C:\\Program Files";
  const programData = env.ProgramData || env.PROGRAMDATA || "C:\\ProgramData";
  return [`${programFiles}\\Docker\\Docker\\resources\\bin\\docker.exe`, `${programData}\\DockerDesktop\\version-bin\\docker.exe`];
}

/**
 * Well-known `docker` CLI locations, else bare `docker` if `which`/`where` resolves it on PATH,
 * else `null`. `TIT_DOCKER_BIN_FOR_DISCOVERY` is a test-only override -- `docker context inspect`
 * (below) is the only `docker` CLI invocation left anywhere in the app (D4,
 * `docs/dev/DECISIONS.md § 2026-09-03 (One Docker image and a real development loop)`; the former `dockerCli.ts` that shelled out for
 * everything else is deleted), so this module no longer shares its override env var with a
 * sibling CLI-spawning module the way it once did.
 */
export async function findDockerCli(env: NodeJS.ProcessEnv = process.env, platform: NodeJS.Platform = process.platform): Promise<string | null> {
  if (env.TIT_DOCKER_BIN_FOR_DISCOVERY) return env.TIT_DOCKER_BIN_FOR_DISCOVERY;
  const candidates = platform === "win32" ? windowsDockerCliCandidates(env) : DOCKER_CLI_CANDIDATES;
  for (const c of candidates) if (existsSync(c)) return c;
  try {
    // `env` is the environment the lookup answers for (the caller's PATH), not just a source of
    // overrides — so a test can hand in an empty PATH and get "no CLI" on a machine that has one.
    await execFileAsync(platform === "win32" ? "where" : "which", ["docker"], { timeout: 3000, env: { ...env } });
    return "docker";
  } catch {
    return null;
  }
}

/**
 * Parses a `DOCKER_HOST`-shaped value (`unix:///path`, `npipe://./pipe/name`, `tcp://host:port`).
 * `null` if the scheme isn't recognized.
 *
 * npipe: Docker writes its Windows endpoints as `npipe:////./pipe/docker_engine` — FOUR slashes
 * after the colon (the scheme's `//` plus the pipe path's own `//./pipe/...`), and that is what
 * `docker context inspect` returns for Docker Desktop's `desktop-linux` context too. The path
 * handed to Node's `http.request({ socketPath })` must be `//./pipe/<name>` (equivalently
 * `\\\\.\\pipe\\<name>`): whatever the scheme carried, the run of leading slashes is collapsed to
 * exactly two. The previous implementation stripped only the literal `npipe:` and shipped the
 * four-slash remainder, which Node rejects with `ENOENT` — classified as "Docker is not installed"
 * (verified on a real Windows 11 / Docker Desktop 4.60 host, 2026-09-22; the two-slash forms of
 * both Docker Desktop pipes answer `/_ping` with 200). Forward slashes are kept, as dockerode
 * did in v2 (`package/src/backend/docker-manager.js` fed `//./pipe/docker_engine` to
 * `socketPath` in production).
 */
export function parseDockerHostUrl(value: string): DockerConnection | null {
  const trimmed = value.trim();
  if (trimmed.startsWith("npipe:")) {
    const rest = trimmed.slice("npipe:".length).replace(/\\/g, "/").replace(/^\/+/, "");
    if (!rest) return null;
    return { kind: "npipe", socketPath: `//${rest}` };
  }
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
      // Docker Desktop's Linux engine — the `desktop-linux` context's own pipe, and the one that
      // still runs Linux containers when the user has switched Docker Desktop to Windows
      // containers (which repoints `docker_engine`). Observed live 2026-09-22.
      { kind: "npipe", socketPath: "//./pipe/dockerDesktopLinuxEngine" },
      // The classic compatibility pipe every Docker-for-Windows install exposes (the `default`
      // context). v2 talked to this one exclusively.
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
    // A `.cmd`/`.bat` here can only be a test stub (Docker ships `docker.exe`); Windows refuses to
    // spawn batch files without a shell, so give those — and only those — one.
    const batch = /\.(cmd|bat)$/i.test(dockerBin);
    const { stdout } = await execFileAsync(batch ? `"${dockerBin}"` : dockerBin, ["context", "inspect", "--format", "json"], { timeout: 5000, shell: batch });
    const parsed: unknown = JSON.parse(stdout.trim());
    const ctx = Array.isArray(parsed) ? parsed[0] : parsed;
    const host = (ctx as { Endpoints?: { docker?: { Host?: string } } } | undefined)?.Endpoints?.docker?.Host;
    return typeof host === "string" ? host : null;
  } catch {
    return null;
  }
}

/**
 * One `GET /_ping` over the connection; `true` on any HTTP answer at all (the engine's own
 * version/identity checks come later in `stack.ts`). This is the only place discovery opens a
 * connection, and it exists for named pipes, which have no file to `existsSync`. Exported for
 * tests; `pingEndpoint` is what the win32 branch of `discover` uses.
 */
export function pingEndpoint(conn: DockerConnection, timeoutMs = 2000): Promise<boolean> {
  return new Promise((resolve) => {
    const base: http.RequestOptions = conn.kind === "tcp" ? { host: conn.host, port: conn.port } : { socketPath: conn.socketPath };
    const req = http.request({ ...base, method: "GET", path: "/_ping" }, (res) => {
      res.resume();
      resolve(true);
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error("ping timeout")));
    req.on("error", () => resolve(false));
    req.end();
  });
}

export interface DiscoverOptions {
  /** Liveness probe used on win32; injectable so the fallback order is testable without pipes. */
  ping?: (conn: DockerConnection) => Promise<boolean>;
}

const WINDOWS_NOT_RUNNING =
  "Docker Desktop is installed but none of its named pipes answered. Start Docker Desktop (with the WSL 2 backend enabled) and wait until it reports that the engine is running, then try again.";
const WINDOWS_NOT_INSTALLED =
  "No `docker.exe` was found and no Docker Desktop named pipe answered. Install Docker Desktop for Windows with its WSL 2 backend, start it, then try again.";

/**
 * Resolves the Docker Engine endpoint for this host: `DOCKER_HOST` env var first (honored even
 * if unreachable — an explicit override always wins, matching `docker-manager.js`'s existing
 * behavior), else `docker context inspect` if a `docker` CLI is found, else the first well-known
 * socket that exists on disk. On win32 the context-derived pipe and then each well-known pipe are
 * probed with `/_ping` (a pipe can't be probed with `existsSync` the way a Unix socket file can),
 * and the first one that answers wins — so a stale PATH, a renamed pipe or a context pointing at
 * an engine that is not running all still find Docker Desktop if it is up at all.
 */
export async function discover(env: NodeJS.ProcessEnv = process.env, platform: NodeJS.Platform = process.platform, options: DiscoverOptions = {}): Promise<DiscoverResult> {
  if (env.DOCKER_HOST) {
    const conn = parseDockerHostUrl(env.DOCKER_HOST);
    if (!conn) return { available: false, kind: "unsupported-engine", message: `Unrecognized DOCKER_HOST scheme: ${env.DOCKER_HOST}` };
    return { available: true, connection: conn, source: "DOCKER_HOST" };
  }

  const dockerBin = await findDockerCli(env, platform);
  const ping = options.ping ?? pingEndpoint;
  let contextConn: DockerConnection | null = null;
  if (dockerBin) {
    const host = await contextInspect(dockerBin);
    if (host) {
      contextConn = parseDockerHostUrl(host);
      if (contextConn && platform !== "win32") return { available: true, connection: contextConn, source: "docker context inspect" };
    }
  }

  if (platform === "win32") {
    if (contextConn && (await ping(contextConn))) return { available: true, connection: contextConn, source: "docker context inspect" };
    for (const candidate of wellKnownCandidates(platform)) {
      if (contextConn && candidate.kind === contextConn.kind && candidate.socketPath === contextConn.socketPath) continue;
      if (await ping(candidate)) return { available: true, connection: candidate, source: `well-known:${candidate.socketPath}` };
    }
    return dockerBin
      ? { available: false, kind: "not-running", message: WINDOWS_NOT_RUNNING }
      : { available: false, kind: "not-installed", message: WINDOWS_NOT_INSTALLED };
  }

  for (const candidate of wellKnownCandidates(platform)) {
    if (candidate.socketPath && existsSync(candidate.socketPath)) {
      return { available: true, connection: candidate, source: `well-known:${candidate.socketPath}` };
    }
  }

  if (!dockerBin) {
    return { available: false, kind: "not-installed", message: "No `docker` CLI on PATH and no known Docker/Podman/Colima/OrbStack socket file exists on this machine." };
  }
  return { available: false, kind: "not-running", message: "`docker` CLI is installed but no Docker context or known socket resolved. Is Docker Desktop (or your engine) running?" };
}

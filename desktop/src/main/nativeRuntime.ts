/**
 * Native (bundled Python runtime) lifecycle — the N0.4 packaging spike's counterpart to
 * `stack.ts`'s Docker lifecycle. Locates a python-build-standalone runtime tree shipped as
 * electron-builder `extraResources` (or pointed at by `TIT_NATIVE_RUNTIME_DIR` for dev/e2e),
 * spawns `python -m tit.server` directly as a local child process with the exact CLI/env contract
 * `docker-compose.v3.yml` already uses (r4-python-in-electron.md §1.1), waits for `/api/health`
 * (reusing `./health.ts`, transport-agnostic already — no changes needed there), and hands back
 * the same `{url, token}` shape `stack.start` does so `index.ts`'s existing `connect()` needs no
 * redesign.
 *
 * Scope note: unlike `stack.ts`'s Docker path -- which attaches across app restarts by finding
 * its own project-labelled container and reading its port/token back out of its environment,
 * now that the file-based `stackState.ts` this comment used to reference is deleted -- there is
 * no persisted attach-across-app-restart here at all. A native child never survives this app
 * quitting (`stop()` always kills its whole process tree), so a fresh launch has nothing to
 * attach to. "attach" below only means: a second `start()` call while this process already has
 * one running reuses it instead of spawning a duplicate.
 */
import { type ChildProcess, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { generateToken } from "../shared/compose";
import { waitForHealth } from "./health";
import { log } from "./log";
import { findFreePort } from "./port";

export type NativePlatformArch = "darwin-arm64" | "linux-x64" | "win32-x64";

/**
 * `process.platform`/`process.arch` -> the `extraResources/runtime/<dir>` name this app bundles,
 * matching python-build-standalone's own per-target release naming (r4 §2.1/§5.1). `null` for a
 * combination this app does not ship a runtime for — notably macOS x86_64 (Intel): `bpy`, `torch`
 * and SimNIBS's own `petsc4py` fork all currently lack an Intel-Mac wheel (r4 §4.1-§4.3), so it is
 * not a packaging target; that host keeps the existing Docker path.
 */
export function nativePlatformArch(platform: NodeJS.Platform, arch: string): NativePlatformArch | null {
  if (platform === "darwin" && arch === "arm64") return "darwin-arm64";
  if (platform === "linux" && arch === "x64") return "linux-x64";
  if (platform === "win32" && arch === "x64") return "win32-x64";
  return null;
}

/** python-build-standalone's `install_only` layout: `bin/python3.11` on POSIX, `python.exe` at the
 * tree root on Windows (VERIFIED against the tree this spike built under `native/packaging/runtime/`). */
export function pythonExecutablePath(runtimeDir: string, platform: NodeJS.Platform): string {
  return platform === "win32" ? join(runtimeDir, "python.exe") : join(runtimeDir, "bin", "python3.11");
}

export interface ResolveRuntimeOptions {
  env?: NodeJS.ProcessEnv;
  resourcesPath?: string;
  platform?: NodeJS.Platform;
  arch?: string;
}

export type ResolveRuntimeResult =
  | { ok: true; runtimeDir: string; pythonPath: string; source: "env" | "packaged" }
  | { ok: false; reason: string };

/**
 * `TIT_NATIVE_RUNTIME_DIR` (this spike's e2e "point at an unpacked runtime directly" leg, and any
 * future dev workflow) wins over the packaged `resourcesPath/runtime/<platform-arch>` layout
 * `electron-builder.yml`'s `extraResources` produces, so a developer or a test never needs a full
 * `electron-builder --dir` pass just to exercise the spawn path.
 */
export function resolveRuntime(opts: ResolveRuntimeOptions = {}): ResolveRuntimeResult {
  const env = opts.env ?? process.env;
  const platform = opts.platform ?? process.platform;
  const arch = opts.arch ?? process.arch;

  const override = env.TIT_NATIVE_RUNTIME_DIR;
  if (override) {
    const pythonPath = pythonExecutablePath(override, platform);
    if (!existsSync(pythonPath)) return { ok: false, reason: `TIT_NATIVE_RUNTIME_DIR is set but no interpreter at ${pythonPath}` };
    return { ok: true, runtimeDir: override, pythonPath, source: "env" };
  }

  const resourcesPath = opts.resourcesPath ?? process.resourcesPath;
  if (!resourcesPath) return { ok: false, reason: "no TIT_NATIVE_RUNTIME_DIR set and no packaged resourcesPath available" };
  const platformArch = nativePlatformArch(platform, arch);
  if (!platformArch) return { ok: false, reason: `no bundled native runtime for ${platform}-${arch}` };
  const runtimeDir = join(resourcesPath, "runtime", platformArch);
  const pythonPath = pythonExecutablePath(runtimeDir, platform);
  if (!existsSync(pythonPath)) return { ok: false, reason: `no interpreter at ${pythonPath}` };
  return { ok: true, runtimeDir, pythonPath, source: "packaged" };
}

export interface ServerArgsOptions {
  projectDir: string;
  port: number;
  host?: string;
  staticDir?: string;
}

/** The exact `-m tit.server` CLI contract `docker-compose.v3.yml` already uses (r4 §1.1), minus the
 * Docker-only `0.0.0.0` bind — a native spawn always binds loopback only. */
export function buildServerArgs(opts: ServerArgsOptions): string[] {
  const args = ["-m", "tit.server", "--project", opts.projectDir, "--host", opts.host ?? "127.0.0.1", "--port", String(opts.port)];
  if (opts.staticDir) args.push("--static-dir", opts.staticDir);
  return args;
}

export interface ServerEnvOptions {
  token: string;
  base?: NodeJS.ProcessEnv;
}

/**
 * A clean child environment. `PYTHONHOME`/`PYTHONPATH` are stripped so a relocated
 * python-build-standalone interpreter never picks up a system Python's stdlib or an unrelated
 * project's path (r4 §5.2 point 3: "must be cleared/set explicitly for a relocated standalone
 * interpreter to not accidentally pick up a system Python's stdlib"). `PYTHONNOUSERSITE=1` stops a
 * developer's own `~/.local`/`~/Library/Python` site-packages from shadowing the bundled ones.
 * `MPLBACKEND=Agg` — this app never has a display for the child to draw to. `KMP_AFFINITY=disabled`
 * + `OMP_NUM_THREADS=1` are the exact pair `docker-compose.v3.yml` sets today for the container path,
 * load-bearing not cosmetic (`Dockerfile.simnibs`'s own comment: "Avoid OpenMP affinity crash during
 * postinstall", r4 §1.1/§8 risk 4) — dropping them here would reproduce a known crash class outside
 * the container's protection.
 */
export function buildServerEnv(opts: ServerEnvOptions): NodeJS.ProcessEnv {
  const base = { ...(opts.base ?? process.env) };
  delete base.PYTHONHOME;
  delete base.PYTHONPATH;
  return {
    ...base,
    TIT_SERVER_TOKEN: opts.token,
    PYTHONNOUSERSITE: "1",
    MPLBACKEND: "Agg",
    KMP_AFFINITY: "disabled",
    OMP_NUM_THREADS: "1",
  };
}

export type KillPlan = { mode: "process-group"; pid: number; signal: NodeJS.Signals } | { mode: "taskkill"; pid: number; args: string[] };

/**
 * Pure description of how this platform kills a spawned server's WHOLE process tree — a leaked
 * uvicorn worker, or a SimNIBS subprocess the server itself spawned (`meshfix`, `mmg3d_O3`, r4
 * §2.3), must not survive the app quitting (r4 §5.2 point 5). `executeKillPlan` below is what
 * actually runs it; kept separate so the platform choice is unit-testable without spawning or
 * killing a real process.
 *
 * POSIX: the child is spawned with `detached: true`, which makes it the leader of its own process
 * group (pgid === its own pid); signalling the *negative* pid signals every process in that group,
 * not just the direct child — the "genuinely recursive" kill r4 asks for.
 *
 * Windows has no process-group signal at all; `taskkill /PID <p> /T /F` (`/T` = tree, `/F` = force)
 * is the tree-kill primitive there. This is the same platform split
 * `tit/jobs/runner.py:213`'s `signal.SIGKILL` (AttributeError on Windows, tracked as Stage N0.6's
 * job) needs — kept here as one clearly-named function rather than a `process.platform` check
 * inlined at each call site.
 */
export function killPlan(pid: number, platform: NodeJS.Platform, signal: NodeJS.Signals = "SIGTERM"): KillPlan {
  if (platform === "win32") return { mode: "taskkill", pid, args: ["/PID", String(pid), "/T", "/F"] };
  return { mode: "process-group", pid, signal };
}

export function executeKillPlan(plan: KillPlan): void {
  if (plan.mode === "taskkill") {
    spawn("taskkill", plan.args, { stdio: "ignore" }).on("error", (err) => log("warn", `taskkill failed: ${String(err)}`));
    return;
  }
  try {
    process.kill(-plan.pid, plan.signal);
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code;
    if (code !== "ESRCH") log("warn", `kill(-${plan.pid}, ${plan.signal}) failed: ${String(err)}`);
  }
}

export interface CurrentNativeRuntime {
  hostProjectDir: string;
  origin: string;
  token: string;
  port: number;
  pid: number;
}

export type NativeStartResult = { ok: true; url: string; token: string; attached: boolean } | { ok: false; error: string };

/** How long `stop()` waits for a graceful SIGTERM exit before escalating to SIGKILL/`taskkill /F`. */
const STOP_GRACE_MS = 1500;

class NativeRuntimeManager {
  private current: CurrentNativeRuntime | null = null;
  private child: ChildProcess | null = null;
  private starting: Promise<NativeStartResult> | null = null;

  getCurrent(): CurrentNativeRuntime | null {
    return this.current;
  }

  /** Attach-or-spawn: a second call while this process already has one running reuses it (see the
   * module doc for why there is nothing to attach to *across* app restarts). Concurrent callers
   * during startup share the one in-flight attempt rather than racing two spawns. */
  async start(hostProjectDir: string, staticDir?: string): Promise<NativeStartResult> {
    if (this.current) return { ok: true, url: this.current.origin, token: this.current.token, attached: true };
    if (this.starting) return this.starting;
    const attempt = this.doStart(hostProjectDir, staticDir).finally(() => {
      this.starting = null;
    });
    this.starting = attempt;
    return attempt;
  }

  private async doStart(hostProjectDir: string, staticDir?: string): Promise<NativeStartResult> {
    const resolved = resolveRuntime();
    if (!resolved.ok) return { ok: false, error: resolved.reason };

    const port = await findFreePort(8765);
    const token = generateToken();
    const args = buildServerArgs({ projectDir: hostProjectDir, port, staticDir });
    const env = buildServerEnv({ token });

    log("info", `[native] spawning ${resolved.pythonPath} ${args.join(" ")}`);
    const child = spawn(resolved.pythonPath, args, {
      env,
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    });
    child.stdout?.on("data", (chunk: Buffer) => log("info", `[native:out] ${chunk.toString("utf8").trim()}`));
    child.stderr?.on("data", (chunk: Buffer) => log("info", `[native:err] ${chunk.toString("utf8").trim()}`));
    child.on("exit", (code, signal) => {
      log("warn", `[native] server process exited (code=${String(code)}, signal=${String(signal)})`);
      if (this.child === child) {
        this.current = null;
        this.child = null;
      }
    });
    child.on("error", (err) => log("error", `[native] spawn error: ${String(err)}`));

    const origin = `http://127.0.0.1:${port}`;
    try {
      await waitForHealth(origin);
    } catch (err) {
      if (typeof child.pid === "number") executeKillPlan(killPlan(child.pid, process.platform, "SIGKILL"));
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
    if (typeof child.pid !== "number") return { ok: false, error: "spawn did not return a pid" };

    this.child = child;
    this.current = { hostProjectDir, origin, token, port, pid: child.pid };
    return { ok: true, url: origin, token, attached: false };
  }

  /** Kills the whole process tree and clears `getCurrent()`. Safe to call when nothing is running. */
  async stop(): Promise<void> {
    const current = this.current;
    const child = this.child;
    this.current = null;
    this.child = null;
    if (!current || !child || typeof child.pid !== "number") return;
    const pid = child.pid;
    executeKillPlan(killPlan(pid, process.platform, "SIGTERM"));
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        if (child.exitCode === null && child.signalCode === null) executeKillPlan(killPlan(pid, process.platform, "SIGKILL"));
        resolve();
      }, STOP_GRACE_MS);
      child.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
  }
}

export const nativeRuntime = new NativeRuntimeManager();

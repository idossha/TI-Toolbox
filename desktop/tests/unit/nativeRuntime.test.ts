/**
 * Unit-tests only the PURE parts of `nativeRuntime.ts` (N0.4 spike): platform-arch naming, runtime
 * resolution, argv/env building, and per-platform kill-plan selection. `NativeRuntimeManager`
 * itself (spawn/wait-for-health/stop) is exercised by `tests/e2e/native-launch.spec.ts` instead —
 * it needs a real interpreter and a real process tree, which is an e2e concern, not a unit one.
 *
 * Importing `nativeRuntime.ts` here is safe even though it (transitively, via `./health`) imports
 * `"electron"`: outside an Electron runtime that module resolves to a plain string
 * (`node_modules/electron/index.js`'s CJS export), so named imports like `{ net }` come back
 * `undefined` rather than throwing — confirmed empirically before relying on it. Nothing in this
 * file calls a function that touches `net`/`app`, so that never matters here.
 */
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  buildServerArgs,
  buildServerEnv,
  executeKillPlan,
  killPlan,
  nativePlatformArch,
  pythonExecutablePath,
  resolveRuntime,
} from "../../src/main/nativeRuntime";

describe("nativePlatformArch", () => {
  it("maps the three bundled targets", () => {
    expect(nativePlatformArch("darwin", "arm64")).toBe("darwin-arm64");
    expect(nativePlatformArch("linux", "x64")).toBe("linux-x64");
    expect(nativePlatformArch("win32", "x64")).toBe("win32-x64");
  });

  it("returns null for macOS x86_64 (r4 §4.1-§4.3: no bpy/torch/petsc4py Intel-Mac wheel)", () => {
    expect(nativePlatformArch("darwin", "x64")).toBeNull();
  });

  it("returns null for an unbuilt combination (e.g. linux arm64)", () => {
    expect(nativePlatformArch("linux", "arm64")).toBeNull();
  });
});

describe("pythonExecutablePath", () => {
  it("is bin/python3.11 on POSIX", () => {
    expect(pythonExecutablePath("/opt/runtime", "darwin")).toBe("/opt/runtime/bin/python3.11");
    expect(pythonExecutablePath("/opt/runtime", "linux")).toBe("/opt/runtime/bin/python3.11");
  });

  it("is python.exe at the tree root on win32", () => {
    expect(pythonExecutablePath("C:\\runtime", "win32")).toBe(join("C:\\runtime", "python.exe"));
  });
});

describe("resolveRuntime", () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "tit-native-runtime-"));
  });
  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("prefers TIT_NATIVE_RUNTIME_DIR over the packaged layout when the interpreter exists", () => {
    mkdirSync(join(dir, "bin"), { recursive: true });
    writeFileSync(join(dir, "bin", "python3.11"), "#!/bin/sh\n");
    const result = resolveRuntime({ env: { TIT_NATIVE_RUNTIME_DIR: dir }, platform: "darwin", arch: "arm64" });
    expect(result).toEqual({ ok: true, runtimeDir: dir, pythonPath: join(dir, "bin", "python3.11"), source: "env" });
  });

  it("fails clearly when TIT_NATIVE_RUNTIME_DIR points at a tree with no interpreter", () => {
    const result = resolveRuntime({ env: { TIT_NATIVE_RUNTIME_DIR: dir }, platform: "darwin", arch: "arm64" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toContain(dir);
  });

  it("falls back to resourcesPath/runtime/<platform-arch> (packaged mode) when the env is unset", () => {
    mkdirSync(join(dir, "runtime", "darwin-arm64", "bin"), { recursive: true });
    writeFileSync(join(dir, "runtime", "darwin-arm64", "bin", "python3.11"), "#!/bin/sh\n");
    const result = resolveRuntime({ env: {}, resourcesPath: dir, platform: "darwin", arch: "arm64" });
    expect(result).toEqual({
      ok: true,
      runtimeDir: join(dir, "runtime", "darwin-arm64"),
      pythonPath: join(dir, "runtime", "darwin-arm64", "bin", "python3.11"),
      source: "packaged",
    });
  });

  it("fails with the unsupported-target reason on macOS x86_64, even with a resourcesPath", () => {
    const result = resolveRuntime({ env: {}, resourcesPath: dir, platform: "darwin", arch: "x64" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/darwin-x64/);
  });

  it("fails when neither the env override nor a resourcesPath is available", () => {
    const result = resolveRuntime({ env: {}, resourcesPath: undefined, platform: "linux", arch: "x64" });
    expect(result.ok).toBe(false);
  });
});

describe("buildServerArgs", () => {
  it("reproduces the docker-compose.v3.yml CLI contract, loopback-bound", () => {
    expect(buildServerArgs({ projectDir: "/data/proj", port: 18765 })).toEqual([
      "-m",
      "tit.server",
      "--project",
      "/data/proj",
      "--host",
      "127.0.0.1",
      "--port",
      "18765",
    ]);
  });

  it("appends --static-dir only when given one", () => {
    const args = buildServerArgs({ projectDir: "/data/proj", port: 18765, staticDir: "/app/renderer" });
    expect(args.slice(-2)).toEqual(["--static-dir", "/app/renderer"]);
  });

  it("honours an explicit host override", () => {
    const args = buildServerArgs({ projectDir: "/data/proj", port: 18765, host: "0.0.0.0" });
    expect(args).toContain("0.0.0.0");
  });
});

describe("buildServerEnv", () => {
  it("sets the token and the load-bearing threading/headless vars", () => {
    const env = buildServerEnv({ token: "tok-123", base: { PATH: "/usr/bin", UNRELATED: "kept" } });
    expect(env.TIT_SERVER_TOKEN).toBe("tok-123");
    expect(env.MPLBACKEND).toBe("Agg");
    expect(env.KMP_AFFINITY).toBe("disabled");
    expect(env.OMP_NUM_THREADS).toBe("1");
    expect(env.PYTHONNOUSERSITE).toBe("1");
    expect(env.PATH).toBe("/usr/bin");
    expect(env.UNRELATED).toBe("kept");
  });

  it("strips PYTHONHOME and PYTHONPATH from the base environment", () => {
    const env = buildServerEnv({ token: "t", base: { PYTHONHOME: "/usr", PYTHONPATH: "/usr/lib/python", PATH: "/bin" } });
    expect(env.PYTHONHOME).toBeUndefined();
    expect(env.PYTHONPATH).toBeUndefined();
  });

  it("does not mutate the base object passed in", () => {
    const base = { PYTHONHOME: "/usr" };
    buildServerEnv({ token: "t", base });
    expect(base.PYTHONHOME).toBe("/usr");
  });
});

describe("killPlan", () => {
  it("is a process-group signal on POSIX", () => {
    expect(killPlan(4242, "darwin", "SIGTERM")).toEqual({ mode: "process-group", pid: 4242, signal: "SIGTERM" });
    expect(killPlan(4242, "linux")).toEqual({ mode: "process-group", pid: 4242, signal: "SIGTERM" });
  });

  it("is taskkill /T /F on win32", () => {
    expect(killPlan(4242, "win32")).toEqual({ mode: "taskkill", pid: 4242, args: ["/PID", "4242", "/T", "/F"] });
  });

  it("defaults to SIGTERM when no signal is given", () => {
    const plan = killPlan(1, "linux");
    expect(plan.mode === "process-group" && plan.signal).toBe("SIGTERM");
  });
});

describe("executeKillPlan", () => {
  it("silently no-ops a process-group signal to an already-dead pid (ESRCH)", () => {
    // A pid this large is virtually guaranteed not to exist; process.kill throws ESRCH for it,
    // which executeKillPlan must swallow rather than propagate.
    expect(() => executeKillPlan({ mode: "process-group", pid: 2_000_000_000, signal: "SIGTERM" })).not.toThrow();
  });
});

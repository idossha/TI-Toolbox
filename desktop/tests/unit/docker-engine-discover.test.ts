import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { discover, findDockerCli, parseDockerHostUrl, wellKnownCandidates, windowsDockerCliCandidates, type DockerConnection } from "../../src/main/docker/discover";

describe("parseDockerHostUrl", () => {
  it("parses a unix:// URL", () => {
    expect(parseDockerHostUrl("unix:///var/run/docker.sock")).toEqual({ kind: "unix", socketPath: "/var/run/docker.sock" });
  });

  it("collapses the leading slashes of an npipe:// URL to exactly two — the form Node's socketPath accepts", () => {
    // Docker's own spelling carries four slashes after the colon: `npipe:////./pipe/docker_engine`
    // (`docker context inspect` on Windows returns exactly this for both the `default` and the
    // `desktop-linux` context). Node's `http.request({ socketPath })` needs `//./pipe/<name>`;
    // the four-slash remainder the old `npipe:`-only strip produced fails with ENOENT on a real
    // Windows 11 / Docker Desktop 4.60 host (2026-09-22), which the app then reported as
    // "Docker was not found on this machine".
    expect(parseDockerHostUrl("npipe:////./pipe/docker_engine")).toEqual({ kind: "npipe", socketPath: "//./pipe/docker_engine" });
    expect(parseDockerHostUrl("npipe:////./pipe/dockerDesktopLinuxEngine")).toEqual({ kind: "npipe", socketPath: "//./pipe/dockerDesktopLinuxEngine" });
    expect(parseDockerHostUrl("npipe://./pipe/docker_engine")).toEqual({ kind: "npipe", socketPath: "//./pipe/docker_engine" });
    expect(parseDockerHostUrl("npipe:////./pipe/docker_engine")).toEqual(parseDockerHostUrl("npipe://./pipe/docker_engine"));
  });

  it("accepts a backslash-spelled npipe path and rejects an empty one", () => {
    expect(parseDockerHostUrl("npipe:\\\\\\\\.\\pipe\\docker_engine")).toEqual({ kind: "npipe", socketPath: "//./pipe/docker_engine" });
    expect(parseDockerHostUrl("npipe://")).toBeNull();
  });

  it("parses a tcp:// URL into host/port", () => {
    expect(parseDockerHostUrl("tcp://192.168.1.5:2375")).toEqual({ kind: "tcp", host: "192.168.1.5", port: 2375 });
  });

  it("returns null for an unrecognized scheme", () => {
    expect(parseDockerHostUrl("ftp://nope")).toBeNull();
    expect(parseDockerHostUrl("not-a-url-at-all")).toBeNull();
  });
});

describe("wellKnownCandidates", () => {
  it("returns unix-socket candidates on darwin/linux, in precedence order, /var/run/docker.sock second", () => {
    const candidates = wellKnownCandidates("darwin");
    expect(candidates.every((c) => c.kind === "unix")).toBe(true);
    expect(candidates[1]).toEqual({ kind: "unix", socketPath: "/var/run/docker.sock" });
  });

  it("returns npipe candidates on win32: Docker Desktop's Linux engine pipe, then the classic docker_engine pipe", () => {
    const candidates = wellKnownCandidates("win32");
    expect(candidates.every((c) => c.kind === "npipe")).toBe(true);
    expect(candidates.slice(0, 2)).toEqual([
      { kind: "npipe", socketPath: "//./pipe/dockerDesktopLinuxEngine" },
      { kind: "npipe", socketPath: "//./pipe/docker_engine" },
    ]);
  });
});

describe("windowsDockerCliCandidates", () => {
  it("names Docker Desktop's install dir and its version-bin shim dir, from the Windows env", () => {
    expect(windowsDockerCliCandidates({ ProgramFiles: "D:\\PF", ProgramData: "D:\\PD" })).toEqual([
      "D:\\PF\\Docker\\Docker\\resources\\bin\\docker.exe",
      "D:\\PD\\DockerDesktop\\version-bin\\docker.exe",
    ]);
    expect(windowsDockerCliCandidates({})).toEqual([
      "C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe",
      "C:\\ProgramData\\DockerDesktop\\version-bin\\docker.exe",
    ]);
  });

  it("findDockerCli on win32 finds docker.exe at a well-known path even when PATH does not carry it", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tit-discover-"));
    try {
      // The candidate is a Windows-spelled path; on the Linux host running this test that is one
      // file whose *name* contains backslashes, which is enough to exercise the existsSync branch.
      const exe = `${dir}\\Docker\\Docker\\resources\\bin\\docker.exe`;
      mkdirSync(dirname(exe), { recursive: true }); // a no-op on Linux (dirname is `dir`), the real tree on Windows
      writeFileSync(exe, "");
      expect(await findDockerCli({ ProgramFiles: dir, ProgramData: join(dir, "none"), PATH: "" }, "win32")).toBe(exe);
      expect(await findDockerCli({ ProgramFiles: join(dir, "none"), ProgramData: join(dir, "none"), PATH: "", Path: "" }, "win32")).toBeNull();
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("discover()", () => {
  const OLD_ENV = process.env;

  beforeEach(() => {
    process.env = { ...OLD_ENV };
  });
  afterEach(() => {
    process.env = OLD_ENV;
  });

  it("honors DOCKER_HOST when set, without validating reachability", async () => {
    const result = await discover({ DOCKER_HOST: "unix:///tmp/definitely-does-not-exist-9f3a.sock" }, "darwin");
    expect(result).toEqual({ available: true, connection: { kind: "unix", socketPath: "/tmp/definitely-does-not-exist-9f3a.sock" }, source: "DOCKER_HOST" });
  });

  it("reports unsupported-engine for an unrecognized DOCKER_HOST scheme", async () => {
    const result = await discover({ DOCKER_HOST: "ftp://nope" }, "darwin");
    expect(result).toEqual({ available: false, kind: "unsupported-engine", message: expect.stringContaining("DOCKER_HOST") });
  });

  it("DOCKER_HOST always wins even if a working docker-CLI stub is also configured", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tit-discover-"));
    const stub = writeContextInspectStub(dir, { Endpoints: { docker: { Host: "unix:///should-not-be-used.sock" } } });
    try {
      const result = await discover({ DOCKER_HOST: "unix:///used.sock", TIT_DOCKER_BIN_FOR_DISCOVERY: stub }, "darwin");
      expect(result).toEqual({ available: true, connection: { kind: "unix", socketPath: "/used.sock" }, source: "DOCKER_HOST" });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("resolves via `docker context inspect` when no DOCKER_HOST is set", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tit-discover-"));
    const stub = writeContextInspectStub(dir, { Endpoints: { docker: { Host: "unix:///tmp/context-resolved-9f3a.sock" } } });
    try {
      const result = await discover({ TIT_DOCKER_BIN_FOR_DISCOVERY: stub }, "darwin");
      expect(result).toEqual({
        available: true,
        connection: { kind: "unix", socketPath: "/tmp/context-resolved-9f3a.sock" },
        source: "docker context inspect",
      });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("falls through to well-known-socket discovery when `docker context inspect` fails", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tit-discover-"));
    const stub = writeFailingStub(dir);
    try {
      // findDockerCli() itself must still report the (failing) stub as "found" — this is the
      // deterministic, hermetic half of the claim; whether a *specific* well-known socket exists
      // on the machine running this test is host-state-dependent and is instead exercised by the
      // live verification in docs/dev/DECISIONS.md § 2026-09-03 (One Docker image and a real development loop), not asserted here.
      expect(await findDockerCli({ TIT_DOCKER_BIN_FOR_DISCOVERY: stub })).toBe(stub);
      const result = await discover({ TIT_DOCKER_BIN_FOR_DISCOVERY: stub }, "darwin");
      // Either a real well-known socket was found (available:true) or none was (kind:"not-running",
      // since a CLI *was* found) — both are consistent with the discovery contract; what must never
      // happen is misclassifying this as "not-installed" (a CLI was in fact found).
      if (!result.available) expect(result.kind).toBe("not-running");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("win32: uses the context-derived pipe when it answers /_ping", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tit-discover-"));
    const stub = writeContextInspectStub(dir, { Endpoints: { docker: { Host: "npipe:////./pipe/dockerDesktopLinuxEngine" } } });
    const pinged: string[] = [];
    try {
      const result = await discover({ TIT_DOCKER_BIN_FOR_DISCOVERY: stub }, "win32", { ping: async (c) => { pinged.push(c.socketPath!); return true; } });
      expect(result).toEqual({ available: true, connection: { kind: "npipe", socketPath: "//./pipe/dockerDesktopLinuxEngine" }, source: "docker context inspect" });
      expect(pinged).toEqual(["//./pipe/dockerDesktopLinuxEngine"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("win32: falls through the well-known pipes, skipping the one the context already named, when the context pipe is dead", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tit-discover-"));
    const stub = writeContextInspectStub(dir, { Endpoints: { docker: { Host: "npipe:////./pipe/dockerDesktopLinuxEngine" } } });
    const pinged: string[] = [];
    try {
      const alive = (c: DockerConnection) => c.socketPath === "//./pipe/docker_engine";
      const result = await discover({ TIT_DOCKER_BIN_FOR_DISCOVERY: stub }, "win32", { ping: async (c) => { pinged.push(c.socketPath!); return alive(c); } });
      expect(result).toEqual({ available: true, connection: { kind: "npipe", socketPath: "//./pipe/docker_engine" }, source: "well-known://./pipe/docker_engine" });
      expect(pinged).toEqual(["//./pipe/dockerDesktopLinuxEngine", "//./pipe/docker_engine"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("win32: with a CLI but no pipe answering, reports not-running and names Docker Desktop's WSL 2 backend", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tit-discover-"));
    const stub = writeFailingStub(dir);
    try {
      const result = await discover({ TIT_DOCKER_BIN_FOR_DISCOVERY: stub }, "win32", { ping: async () => false });
      expect(result).toEqual({ available: false, kind: "not-running", message: expect.stringMatching(/Start Docker Desktop.*WSL 2/) });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("win32: with no CLI and no pipe answering, reports not-installed (never a bare ENOENT)", async () => {
    // No override, empty PATH, ProgramFiles/ProgramData pointed at nothing: no CLI can be found.
    const result = await discover({ PATH: "", Path: "", ProgramFiles: "/nonexistent-9f3a", ProgramData: "/nonexistent-9f3a" }, "win32", { ping: async () => false });
    expect(result).toEqual({ available: false, kind: "not-installed", message: expect.stringMatching(/Install Docker Desktop.*WSL 2/) });
  });

  it("win32: probes the well-known pipes in order when no CLI exists, and takes the first live one", async () => {
    const pinged: string[] = [];
    const result = await discover({ PATH: "", Path: "", ProgramFiles: "/nonexistent-9f3a", ProgramData: "/nonexistent-9f3a" }, "win32", {
      ping: async (c) => { pinged.push(c.socketPath!); return c.socketPath === "//./pipe/docker_engine"; },
    });
    expect(result).toEqual({ available: true, connection: { kind: "npipe", socketPath: "//./pipe/docker_engine" }, source: "well-known://./pipe/docker_engine" });
    expect(pinged).toEqual(["//./pipe/dockerDesktopLinuxEngine", "//./pipe/docker_engine"]);
  });
});

/**
 * A fake `docker` CLI: a shebang'd Node script on POSIX, and on a Windows host a `.cmd` wrapper
 * that runs the same script (Windows cannot exec a `.mjs` directly), so this suite runs on the
 * machine that actually has the named pipes too.
 */
function writeCliStub(dir: string, baseName: string, body: string): string {
  const script = join(dir, `${baseName}.mjs`);
  writeFileSync(script, `#!/usr/bin/env node\n${body}`, { mode: 0o755 });
  chmodSync(script, 0o755);
  if (process.platform !== "win32") return script;
  const cmd = join(dir, `${baseName}.cmd`);
  writeFileSync(cmd, `@echo off\r\nnode "${script}" %*\r\n`);
  return cmd;
}

function writeContextInspectStub(dir: string, contextJson: unknown): string {
  return writeCliStub(
    dir,
    "fake-docker-context",
    `if (process.argv[2] === "context" && process.argv[3] === "inspect") { process.stdout.write(${JSON.stringify(JSON.stringify([contextJson]))}); process.exit(0); }\nprocess.exit(1);\n`,
  );
}

function writeFailingStub(dir: string): string {
  return writeCliStub(dir, "fake-docker-failing", `process.stderr.write("no such context\\n");\nprocess.exit(1);\n`);
}

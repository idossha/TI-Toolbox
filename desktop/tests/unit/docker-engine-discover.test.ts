import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { discover, findDockerCli, parseDockerHostUrl, wellKnownCandidates } from "../../src/main/docker/discover";

describe("parseDockerHostUrl", () => {
  it("parses a unix:// URL", () => {
    expect(parseDockerHostUrl("unix:///var/run/docker.sock")).toEqual({ kind: "unix", socketPath: "/var/run/docker.sock" });
  });

  it("parses an npipe:// URL via a plain 'npipe:' string-strip (not a full scheme strip) — matching docker-manager.js's parseDockerHost exactly, four slashes and all", () => {
    // Docker Desktop's actual default DOCKER_HOST value is "npipe:////./pipe/docker_engine" —
    // four slashes after the colon. `docker-manager.js:88-90` does `hostValue.replace('npipe:', '')`,
    // a single-occurrence *string* replace of the 6-character "npipe:" substring, which leaves
    // "////./pipe/docker_engine" (still four slashes) — and that four-slash form is exactly what
    // v2 fed dockerode's `socketPath` in production. Mirroring it byte-for-byte here, rather than
    // "cleaning up" to two slashes, is deliberate: it's the one form already proven to work.
    expect(parseDockerHostUrl("npipe:////./pipe/docker_engine")).toEqual({ kind: "npipe", socketPath: "////./pipe/docker_engine" });
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

  it("returns npipe candidates on win32, default docker_engine pipe first", () => {
    const candidates = wellKnownCandidates("win32");
    expect(candidates.every((c) => c.kind === "npipe")).toBe(true);
    expect(candidates[0]).toEqual({ kind: "npipe", socketPath: "//./pipe/docker_engine" });
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
      // live verification in dev/spikes/native/docker/REPORT.md, not asserted here.
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

  it("win32: falls back to the default docker_engine pipe once CLI/context discovery is exhausted", async () => {
    // A docker-CLI stub that *fails* context inspect (rather than an absent CLI) — this Mac's
    // real Docker Desktop CLI/context would otherwise resolve first regardless of the simulated
    // `platform` argument, since `findDockerCli`/`contextInspect` run against the real host; using
    // the failing-stub override is what actually makes this assertion hermetic across machines.
    const dir = mkdtempSync(join(tmpdir(), "tit-discover-"));
    const stub = writeFailingStub(dir);
    try {
      const result = await discover({ TIT_DOCKER_BIN_FOR_DISCOVERY: stub }, "win32");
      expect(result).toEqual({
        available: true,
        connection: { kind: "npipe", socketPath: "//./pipe/docker_engine" },
        source: "well-known:default-npipe",
      });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

function writeContextInspectStub(dir: string, contextJson: unknown): string {
  const path = join(dir, "fake-docker-context.mjs");
  writeFileSync(
    path,
    `#!/usr/bin/env node\nif (process.argv[2] === "context" && process.argv[3] === "inspect") { process.stdout.write(${JSON.stringify(JSON.stringify([contextJson]))}); process.exit(0); }\nprocess.exit(1);\n`,
    { mode: 0o755 },
  );
  chmodSync(path, 0o755);
  return path;
}

function writeFailingStub(dir: string): string {
  const path = join(dir, "fake-docker-failing.mjs");
  writeFileSync(path, `#!/usr/bin/env node\nprocess.stderr.write("no such context\\n");\nprocess.exit(1);\n`, { mode: 0o755 });
  chmodSync(path, 0o755);
  return path;
}

/**
 * Ports and wait times the launchers hand the app as environment strings (2026-10-22).
 *
 * Spec: a TCP port is an integer 1–65535 (port 0 asks the OS for "any port", which nothing then
 * knows); a timeout is a positive number. Unset or blank falls back to the documented default:
 * port 8765, start health 120 s (`TIT_LAUNCH_TIMEOUT` seconds, or `TIT_STACK_HEALTH_TIMEOUT_MS`),
 * attach health 45 s. Before this, `findFreePort(0)` returned 0 (the container published
 * 127.0.0.1:0 and the start ended in a 120 s health timeout), `TIT_STACK_HEALTH_TIMEOUT_MS=""` gave
 * 0 and `TIT_LAUNCH_TIMEOUT=abc` gave NaN ("did not answer /api/health within NaNs").
 */
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as discovery from "../../src/main/docker/discover";
import { findFreePort, portFromEnv, positiveFromEnv } from "../../src/main/port";
import { attachHealthTimeoutMs, createStackManager, startHealthTimeoutMs } from "../../src/main/stack";
import { parsePort, StackError } from "../../src/shared/composeFile";

describe("portFromEnv", () => {
  it.each(["0", "NaN", "-1", "65536", "1.5", "abc", "8765x", "1e3"])("refuses %j, naming the variable", (raw) => {
    expect(() => portFromEnv("TIT_LAUNCH_PORT", 8765, { TIT_LAUNCH_PORT: raw })).toThrow(/^TIT_LAUNCH_PORT must be a port number from 1 to 65535/);
  });

  it.each([
    [undefined, 8765],
    ["", 8765],
    ["  ", 8765],
    ["1", 1],
    ["9000", 9000],
    ["09000", 9000],
    ["65535", 65535],
  ] as const)("reads %j as %d", (raw, port) => {
    const env = raw === undefined ? {} : { TIT_DEV_PORT: raw };
    expect(portFromEnv("TIT_DEV_PORT", 8765, env)).toBe(port);
  });
});

describe("positiveFromEnv", () => {
  it.each(["0", "-5", "abc", "NaN", "Infinity"])("refuses %j, naming the variable", (raw) => {
    expect(() => positiveFromEnv("TIT_LAUNCH_TIMEOUT", 120, { TIT_LAUNCH_TIMEOUT: raw })).toThrow(/^TIT_LAUNCH_TIMEOUT must be a positive number/);
  });

  it("falls back when unset or blank and reads fractions", () => {
    expect(positiveFromEnv("X", 120, {})).toBe(120);
    expect(positiveFromEnv("X", 120, { X: "" })).toBe(120);
    expect(positiveFromEnv("X", 120, { X: "30.5" })).toBe(30.5);
  });
});

describe("health timeouts", () => {
  it("start: 120 s by default, the launcher's seconds, or the explicit milliseconds", () => {
    expect(startHealthTimeoutMs({})).toBe(120_000);
    expect(startHealthTimeoutMs({ TIT_STACK_HEALTH_TIMEOUT_MS: "", TIT_LAUNCH_TIMEOUT: "" })).toBe(120_000);
    expect(startHealthTimeoutMs({ TIT_LAUNCH_TIMEOUT: "31" })).toBe(31_000);
    expect(startHealthTimeoutMs({ TIT_LAUNCH_TIMEOUT: "31", TIT_STACK_HEALTH_TIMEOUT_MS: "2500" })).toBe(2_500);
  });

  it("start: a bad value is an error naming its variable, not 0 or NaN", () => {
    expect(() => startHealthTimeoutMs({ TIT_LAUNCH_TIMEOUT: "abc" })).toThrow(/TIT_LAUNCH_TIMEOUT/);
    expect(() => startHealthTimeoutMs({ TIT_STACK_HEALTH_TIMEOUT_MS: "0" })).toThrow(/TIT_STACK_HEALTH_TIMEOUT_MS/);
  });

  it("attach: 45 s by default; blank is the default, not 0", () => {
    expect(attachHealthTimeoutMs({})).toBe(45_000);
    expect(attachHealthTimeoutMs({ TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS: "" })).toBe(45_000);
    expect(attachHealthTimeoutMs({ TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS: "90000" })).toBe(90_000);
    expect(() => attachHealthTimeoutMs({ TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS: "-1" })).toThrow(/TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS/);
  });
});

describe("StackManager.start with a bad timeout in the environment", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it.each([
    ["TIT_LAUNCH_TIMEOUT", "abc"],
    ["TIT_STACK_HEALTH_TIMEOUT_MS", "0"],
    ["TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS", "-1"],
  ])("%s=%j fails the start, naming it, before Docker is looked for", async (name, value) => {
    vi.stubEnv(name, value);
    const lookedForDocker = vi.spyOn(discovery, "discover").mockRejectedValue(new Error("must not look for Docker"));
    const project = mkdtempSync(join(tmpdir(), "tit-timeout-env-"));
    try {
      const host = { isPackaged: true, appPath: project, log: vi.fn(), waitForHealth: vi.fn() };
      const result = await createStackManager(host).start(project);
      expect(result.ok).toBe(false);
      expect(result.ok ? "" : result.error).toContain(name);
      expect(lookedForDocker).not.toHaveBeenCalled();
    } finally {
      rmSync(project, { recursive: true, force: true });
    }
  });
});

describe("findFreePort", () => {
  it.each([0, -1, 65536, 1.5, Number.NaN])("refuses %d as the first port to try", async (preferred) => {
    await expect(findFreePort(preferred)).rejects.toThrow(/must be a port number from 1 to 65535/);
  });

  it("skips a port that is taken and returns the next one", async () => {
    const holder = createServer();
    await new Promise<void>((resolve) => holder.listen(0, "127.0.0.1", resolve));
    const taken = (holder.address() as { port: number }).port;
    try {
      const found = await findFreePort(taken, "127.0.0.1", 50);
      expect(found).toBeGreaterThan(taken);
      expect(found).toBeLessThanOrEqual(65535);
    } finally {
      await new Promise((resolve) => holder.close(resolve));
    }
  });
});

describe("parsePort (compose ports)", () => {
  it.each(["127.0.0.1:0:8765", "127.0.0.1:8765:0", "127.0.0.1:65536:8765", "127.0.0.1::8765"])("refuses %j", (value) => {
    expect(() => parsePort(value, "services.tit.ports[0]")).toThrow(StackError);
  });

  it("keeps a valid mapping", () => {
    expect(parsePort("127.0.0.1:8799:8799", "k")).toEqual({ hostIp: "127.0.0.1", hostPort: 8799, containerPort: 8799, protocol: "tcp" });
  });
});

describe("index.ts reads the launchers' ports through portFromEnv", () => {
  // A source scan: index.ts starts Electron itself, so no unit test can import it. Before
  // 2026-10-22 it passed Number(process.env.TIT_LAUNCH_PORT) to the stack unchecked.
  const source = readFileSync(new URL("../../src/main/index.ts", import.meta.url), "utf-8");

  it.each(["TIT_LAUNCH_PORT", "TIT_DEV_PORT"])("%s", (name) => {
    expect(source).toContain(`portFromEnv("${name}"`);
    expect(source).not.toMatch(new RegExp(`(Number|parseInt|parseFloat)\\(\\s*process\\.env(\\.|\\[["'])${name}`));
  });
});

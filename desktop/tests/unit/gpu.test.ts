/**
 * The GPU probe's cleanup can never turn an optional GPU check into a failed stack start
 * (desktop/src/main/docker/gpu.ts; spec: stack.ts "CPU remains available" when the GPU is not).
 *
 * Before the fix, a rejected `removeContainerById` in the probe's `finally` replaced the probe's
 * verdict with a throw, so `startFresh` failed with "Starting the Docker stack failed". The 409
 * "removal already in progress" text is the Docker Engine's own wording for a concurrent remove.
 * Run: cd desktop && npx vitest run tests/unit/gpu.test.ts (no Docker; fakes stand in for the engine).
 */
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { probeContainerGpu } from "../../src/main/docker/gpu";
import { DockerEngineError, type DockerEngineClient } from "../../src/main/docker/engine";
import type { StackApi } from "../../src/main/docker/stackApi";
import { StackManager, type StackHost } from "../../src/main/stack";

type ProbeApi = Pick<StackApi, "createContainer" | "inspect" | "removeContainerById">;
const REMOVAL_IN_PROGRESS = "(HTTP code 409) unexpected - removal of container probe-id is already in progress";

function api(exitCode: number, removal: Error) {
  return {
    createContainer: vi.fn(async () => ({ Id: "probe-id" })),
    inspect: vi.fn(async () => ({ running: false, exitCode })),
    removeContainerById: vi.fn(async () => { throw removal; }),
  };
}
const client = () => ({ startContainer: vi.fn(async () => {}) });

describe("GPU probe cleanup failure", () => {
  it.each([
    [0, true, "CUDA computation passed"],
    [3, false, "CUDA probe exited 3"],
  ])("keeps the probe's own verdict (exit %i) when removing the probe container rejects", async (exitCode, available, reason) => {
    const fake = api(exitCode, new Error(REMOVAL_IN_PROGRESS));
    const warn = vi.fn();
    await expect(probeContainerGpu(fake as unknown as ProbeApi, client(), "test:image", "linux/amd64", 60_000, warn)).resolves.toEqual({ available, reason });
    expect(fake.removeContainerById).toHaveBeenCalledExactlyOnceWith("probe-id", true);
    expect(warn).toHaveBeenCalledExactlyOnceWith(`GPU probe container probe-id was not removed: ${REMOVAL_IN_PROGRESS}`);
  });

  it("resolves even with no warn sink (the parameter's default)", async () => {
    const fake = api(0, new Error(REMOVAL_IN_PROGRESS));
    await expect(probeContainerGpu(fake as unknown as ProbeApi, client(), "test:image", undefined)).resolves.toEqual({ available: true, reason: "CUDA computation passed" });
  });

  it("keeps the start-failure reason when both the start and the cleanup reject", async () => {
    const fake = api(0, new Error(REMOVAL_IN_PROGRESS));
    const engine = client();
    engine.startContainer.mockRejectedValue(new Error('could not select device driver "nvidia"'));
    const warn = vi.fn();
    await expect(probeContainerGpu(fake as unknown as ProbeApi, engine, "test:image", undefined, 60_000, warn)).resolves.toEqual({ available: false, reason: 'could not select device driver "nvidia"' });
    expect(warn).toHaveBeenCalledExactlyOnceWith(expect.stringContaining(REMOVAL_IN_PROGRESS));
  });

  it("warns about nothing when the cleanup succeeds", async () => {
    const fake = { ...api(0, new Error("unused")), removeContainerById: vi.fn(async () => {}) };
    const warn = vi.fn();
    await expect(probeContainerGpu(fake as unknown as ProbeApi, client(), "test:image", undefined, 60_000, warn)).resolves.toMatchObject({ available: true });
    expect(warn).not.toHaveBeenCalled();
  });
});

describe("a fresh stack start whose GPU probe cannot be removed", () => {
  let root: string | undefined;
  afterEach(() => {
    vi.unstubAllEnvs();
    if (root) rmSync(root, { recursive: true, force: true });
  });

  it("starts the container on the CPU path and logs the cleanup error as a warning", async () => {
    root = mkdtempSync(join(tmpdir(), "tit-gpu-cleanup-"));
    writeFileSync(join(root, "docker-compose.yml"), readFileSync(join(__dirname, "../../../docker-compose.yml")));
    vi.stubEnv("HOME", join(root, "home")); // the user-config dir prepareFresh creates lands here
    vi.stubEnv("TIT_IMAGE_TAG", "");
    const log = vi.fn();
    const host: StackHost = { isPackaged: true, appPath: join(root, "desktop"), log, waitForHealth: vi.fn().mockResolvedValue(undefined), fetchJson: vi.fn() };
    const created: unknown[] = [];
    const fakeApi = {
      imageExists: vi.fn(async () => true),
      createContainer: vi.fn(async (body: unknown, options: { name: string }) => {
        created.push(body);
        return { Id: options.name.startsWith("ti-gpu-probe-") ? "probe-id" : "stack-id" };
      }),
      inspect: vi.fn(async (id: string) => {
        if (id === "probe-id") return { running: false, exitCode: 1 };
        if (id === "stack-id") return { running: true, status: "running", exitCode: 0 };
        throw new DockerEngineError("not-found", `No such container: ${id}`, 404);
      }),
      removeContainerById: vi.fn(async (id: string) => {
        if (id === "probe-id") throw new Error(REMOVAL_IN_PROGRESS);
      }),
    };
    const fakeClient = {
      startContainer: vi.fn(async () => {}),
      pullImage: vi.fn(async () => {}),
      logs: vi.fn(async function* () {}),
    };
    const manager = new StackManager(host);
    const result = await manager["startFresh"](fakeClient as unknown as DockerEngineClient, fakeApi as unknown as StackApi, "ti-toolbox-test", root, { image: "custom:dev" });
    expect(result).toMatchObject({ ok: true, attached: false });
    expect(manager.getCurrent()?.containerId).toBe("stack-id");
    // Two creates: the probe, then the real container with no GPU request (the probe exited 1).
    expect(created).toHaveLength(2);
    expect((created[1] as { HostConfig: { DeviceRequests?: unknown[] } }).HostConfig.DeviceRequests ?? []).toEqual([]);
    expect(log).toHaveBeenCalledWith("warn", `[stack] GPU probe container probe-id was not removed: ${REMOVAL_IN_PROGRESS}`);
  });
});

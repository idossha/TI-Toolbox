/** Actual StackManager attach branch against synthetic Docker replies; no Docker or window. */
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as discovery from "../../src/main/docker/discover";
import { DockerEngineClient } from "../../src/main/docker/engine";
import { StackApi, type ContainerState } from "../../src/main/docker/stackApi";
import { StackManager, type StackHost } from "../../src/main/stack";
import { LABEL_HOST_DIR } from "../../src/shared/compose";

let root: string;
let state: ContainerState;
let host: StackHost;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "tit-image-attach-"));
  writeFileSync(join(root, "docker-compose.yml"), "services:\n  tit:\n    image: idossha/ti-toolbox:${TIT_IMAGE_TAG:-internal-fixture}\n");
  vi.stubEnv("TIT_IMAGE_TAG", "");
  host = { isPackaged: true, appPath: join(root, "desktop"), log: vi.fn(), waitForHealth: vi.fn().mockResolvedValue(undefined), fetchJson: vi.fn() };
  state = { Id: "existing", Name: "existing", image: "idossha/ti-toolbox:internal-fixture", running: true, status: "running", exitCode: 0, health: "healthy", publishedPort: 8765, labels: {}, mounts: [], env: { TIT_SERVER_TOKEN: "fixture-token", TIT_SERVER_PORT: "8765" } };
  vi.spyOn(discovery, "discover").mockResolvedValue({ available: true, connection: { kind: "unix", socketPath: "/unused" }, source: "fixture" });
  vi.spyOn(DockerEngineClient.prototype, "version").mockResolvedValue({ Version: "29.0.0", ApiVersion: "1.51", MinAPIVersion: "1.24", Os: "linux", Arch: "amd64" });
  vi.spyOn(StackApi.prototype, "listContainers").mockResolvedValue([{ Id: "existing", Names: ["/existing"], Image: "sha256:" + "a".repeat(64), State: "running", Status: "Up", Labels: { [LABEL_HOST_DIR]: root } }]);
  vi.spyOn(StackApi.prototype, "inspect").mockImplementation(async () => state);
  vi.spyOn(StackApi.prototype, "removeContainerById").mockRejectedValue(new Error("must not remove"));
  vi.spyOn(StackApi.prototype, "createContainer").mockRejectedValue(new Error("must not create"));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  rmSync(root, { recursive: true, force: true });
});

describe("image pairing on attach", () => {
  it("uses Config.Image rather than the list's resolved image ID", async () => {
    const manager = new StackManager(host);
    expect(await manager.start(root)).toMatchObject({ ok: true, attached: true });
    expect(manager.getCurrent()?.image).toBe(state.image);
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
  });

  it.each([{}, { requireMatch: true, forceRecreate: true }])("refuses an old cohort without removing it, options %j", async (options) => {
    state.image = "idossha/ti-toolbox:internal-old";
    const result = await new StackManager(host).start(root, options);
    expect(result).toMatchObject({ ok: false, error: expect.stringContaining("requires idossha/ti-toolbox:internal-fixture") });
    expect(result).toMatchObject({ error: expect.stringContaining("Wait for its jobs to finish") });
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
    expect(StackApi.prototype.createContainer).not.toHaveBeenCalled();
    expect(host.waitForHealth).not.toHaveBeenCalled();
  });

  it("accepts an explicit dev tag and preserves the existing dev attachment", async () => {
    state.image = "idossha/ti-toolbox:dev";
    expect(await new StackManager(host).start(root, { imageTag: "dev", requireMatch: true })).toMatchObject({ ok: true, attached: true });
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
  });

  it("honours ambient image override in the same way as fresh creation", async () => {
    vi.stubEnv("TIT_IMAGE_TAG", "dev");
    state.image = "idossha/ti-toolbox:dev";
    expect(await new StackManager(host).start(root)).toMatchObject({ ok: true, attached: true });
  });

  it("accepts an exact digest reference configured in compose", async () => {
    state.image = "idossha/ti-toolbox@sha256:" + "b".repeat(64);
    writeFileSync(join(root, "docker-compose.yml"), `services:\n  tit:\n    image: ${state.image}\n`);
    expect(await new StackManager(host).start(root)).toMatchObject({ ok: true, attached: true });
  });
});


describe("dev recreation preserves work", () => {
  const options = { requireMatch: true, repoDir: "/current/checkout", serverReload: true };

  it.each([
    ["running", [{ id: "run", kind: "sim", state: "running" }]],
    ["unknown state", [{ id: "run", kind: "sim", state: "cancelling" }]],
    ["invalid body", { detail: "Unauthorized" }],
    ["invalid job", [{}]],
  ])("does not remove a mismatched container with %s", async (_name, body) => {
    vi.mocked(host.fetchJson).mockResolvedValue(body);
    expect(await new StackManager(host).start(root, options)).toMatchObject({ ok: false });
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
  });

  it("does not remove a mismatched container when the jobs request times out", async () => {
    vi.mocked(host.fetchJson).mockRejectedValue(new Error("timeout"));
    expect(await new StackManager(host).start(root, options)).toMatchObject({ ok: false, error: expect.stringContaining("left unchanged") });
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
  });

  it("does not remove a mismatched container when credentials are missing", async () => {
    delete state.env.TIT_SERVER_TOKEN;
    expect(await new StackManager(host).start(root, options)).toMatchObject({ ok: false, error: expect.stringContaining("left unchanged") });
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
    expect(host.fetchJson).not.toHaveBeenCalled();
  });

  it("recreates a stale checkout only after verifying it is idle", async () => {
    vi.mocked(host.fetchJson).mockResolvedValue([]);
    vi.mocked(StackApi.prototype.removeContainerById).mockResolvedValue(undefined);
    vi.spyOn(StackApi.prototype, "imageExists").mockRejectedValue(new Error("stop before creation"));
    await new StackManager(host).start(root, options);
    expect(host.fetchJson).toHaveBeenCalled();
    expect(StackApi.prototype.removeContainerById).toHaveBeenCalledWith("existing", true);
  });
});

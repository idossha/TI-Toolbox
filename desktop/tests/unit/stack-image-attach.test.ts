/** Actual StackManager attach branch against synthetic Docker replies; no Docker or window. */
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as discovery from "../../src/main/docker/discover";
import { DockerEngineClient } from "../../src/main/docker/engine";
import { StackApi, type ContainerState } from "../../src/main/docker/stackApi";
import { StackManager, isToolboxContainer, type StackHost } from "../../src/main/stack";
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

describe("explicit running-container selection", () => {
  it("invalid replacement YAML leaves the selected container running", async () => {
    host.chooseRunningContainer = vi.fn().mockResolvedValue({ action: "replace", containerId: "existing" });
    writeFileSync(join(root, "docker-compose.yml"), "services: [invalid");
    const stop = vi.spyOn(DockerEngineClient.prototype, "stopContainer");
    expect(await new StackManager(host).start(root)).toMatchObject({ ok: false });
    expect(stop).not.toHaveBeenCalled();
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
  });

  it("cancels without inspecting, removing or reconnecting", async () => {
    host.chooseRunningContainer = vi.fn().mockResolvedValue(null);
    expect(await new StackManager(host).start(root)).toMatchObject({ ok: false, error: expect.stringContaining("cancelled") });
    expect(StackApi.prototype.inspect).not.toHaveBeenCalled();
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
    expect(host.waitForHealth).not.toHaveBeenCalled();
  });

  it("requires a choice even when no host prompt is configured", async () => {
    expect(await new StackManager(host).start(root)).toMatchObject({ ok: false });
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
  });

  it("attaches the explicitly selected different project and image without replacement", async () => {
    host.chooseRunningContainer = vi.fn().mockResolvedValue({ action: "attach", containerId: "existing" });
    state.image = "idossha/ti-toolbox:older";
    state.labels[LABEL_HOST_DIR] = "/other/project";
    const manager = new StackManager(host);
    expect(await manager.start(root, { requireMatch: true, forceRecreate: true })).toMatchObject({ ok: true, attached: true });
    expect(manager.getCurrent()).toMatchObject({ image: state.image, hostProjectDir: "/other/project" });
    expect(StackApi.prototype.listContainers).toHaveBeenCalledWith({});
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
  });

  it("only removes the explicitly selected candidate on replacement", async () => {
    host.chooseRunningContainer = vi.fn().mockResolvedValue({ action: "replace", containerId: "existing" });
    vi.mocked(StackApi.prototype.listContainers).mockResolvedValue([
      { Id: "other", Names: ["/ti-toolbox-other"], Image: "idossha/ti-toolbox:dev", State: "running", Status: "Up", Labels: {} },
      { Id: "existing", Names: ["/ti-toolbox-selected"], Image: "idossha/ti-toolbox:dev", State: "running", Status: "Up", Labels: {} },
    ]);
    writeFileSync(join(root, "docker-compose.yml"), readFileSync(join(__dirname, "../../../docker-compose.yml")));
    vi.spyOn(DockerEngineClient.prototype, "stopContainer").mockResolvedValue(undefined);
    await new StackManager(host).start(root);
    expect(DockerEngineClient.prototype.stopContainer).toHaveBeenCalledExactlyOnceWith("existing", 10);
    expect(StackApi.prototype.removeContainerById).toHaveBeenCalledExactlyOnceWith("existing");
    expect(host.waitForHealth).not.toHaveBeenCalled();
  });

  it("leaves a legacy container unchanged when it has no server credentials", async () => {
    host.chooseRunningContainer = vi.fn().mockResolvedValue({ action: "attach", containerId: "existing" });
    delete state.env.TIT_SERVER_TOKEN;
    expect(await new StackManager(host).start(root)).toMatchObject({ ok: false, error: expect.stringContaining("port and token") });
    expect(StackApi.prototype.removeContainerById).not.toHaveBeenCalled();
  });

  it("adopts an already selected dev container without a second prompt", async () => {
    host.chooseRunningContainer = vi.fn();
    const manager = new StackManager(host);
    expect(await manager.adopt("existing")).toMatchObject({ ok: true, attached: true });
    expect(manager.getCurrent()?.containerId).toBe("existing");
    expect(host.chooseRunningContainer).not.toHaveBeenCalled();
  });
});

it("does not offer sibling preprocessing services even when they carry project labels", () => {
  expect(isToolboxContainer({ Id: "sibling", Names: ["/ti-toolbox-qsiprep"], Image: "pennlinc/qsiprep", State: "running", Status: "Up", Labels: { [LABEL_HOST_DIR]: root, "tit.service": "qsiprep" } })).toBe(false);
});

it("keeps container ownership when Docker cannot stop it", async () => {
  const manager = new StackManager(host);
  await manager.adopt("existing");
  vi.spyOn(DockerEngineClient.prototype, "stopContainer").mockRejectedValue(new Error("engine unavailable"));
  expect(await manager.stop()).toMatchObject({ ok: false });
  expect(manager.getCurrent()?.containerId).toBe("existing");
});

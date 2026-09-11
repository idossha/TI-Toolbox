import { describe, expect, it, vi } from "vitest";
import { probeContainerGpu } from "./gpu";
import type { StackApi } from "./stackApi";

type ProbeApi = Pick<StackApi, "createContainer" | "inspect" | "removeContainerById">;
function fake(exitCode = 0) {
  return {
    createContainer: vi.fn(async () => ({ Id: "probe" })),
    inspect: vi.fn(async () => ({ running: false, exitCode })),
    removeContainerById: vi.fn(async () => {}),
  };
}
const client = () => ({ startContainer: vi.fn(async () => {}) });
describe("container GPU selection", () => {
  it("enables GPU only after an isolated CUDA computation succeeds", async () => {
    const api = fake();
    expect((await probeContainerGpu(api as unknown as ProbeApi, client(), "test:image", "linux/amd64")).available).toBe(true);
    const body = (api.createContainer.mock.calls as unknown[][])[0]?.[0];
    expect(body).toMatchObject({ Image: "test:image", Entrypoint: ["simnibs_python"], HostConfig: { Binds: [], NetworkMode: "none", DeviceRequests: [{ Driver: "nvidia", Count: -1, Capabilities: [["gpu"]] }] } });
    expect(api.removeContainerById).toHaveBeenCalledWith("probe", true);
  });
  it("falls back when the image cannot execute CUDA", async () => {
    const api = fake(1);
    expect((await probeContainerGpu(api as unknown as ProbeApi, client(), "test:image", undefined)).available).toBe(false);
    expect(api.removeContainerById).toHaveBeenCalledWith("probe", true);
  });
  it("cleans up when the engine rejects GPU access at start", async () => {
    const api = fake(); const engine = client(); engine.startContainer.mockRejectedValue(new Error("no NVIDIA runtime"));
    expect(await probeContainerGpu(api as unknown as ProbeApi, engine, "test:image", undefined)).toEqual({ available: false, reason: "no NVIDIA runtime" });
    expect(api.removeContainerById).toHaveBeenCalledWith("probe", true);
  });
  it("kills a probe that exceeds the time budget", async () => {
    const api = fake();
    expect(await probeContainerGpu(api as unknown as ProbeApi, client(), "test:image", undefined, 0)).toEqual({ available: false, reason: "CUDA probe timed out" });
    expect(api.removeContainerById).toHaveBeenCalledWith("probe", true);
  });
});

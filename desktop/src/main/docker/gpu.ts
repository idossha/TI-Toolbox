import { randomUUID } from "node:crypto";
import type { ContainerCreateBody } from "../../shared/composeFile";
import type { DockerEngineClient } from "./engine";
import type { StackApi } from "./stackApi";

export const CUDA_PROBE = "import torch; assert torch.cuda.is_available(); x=torch.ones((32,32),device='cuda'); y=x@x; torch.cuda.synchronize(); assert y[0,0].item()==32";
export const GPU_REQUEST = { Driver: "nvidia", Count: -1, Capabilities: [["gpu"]] };

/** Verify the selected image can execute CUDA without granting access to project data. */
export async function probeContainerGpu(
  api: Pick<StackApi, "createContainer" | "inspect" | "removeContainerById">,
  client: Pick<DockerEngineClient, "startContainer">,
  image: string,
  platform: string | undefined,
  timeoutMs = 60_000,
): Promise<{ available: boolean; reason: string }> {
  let id: string | undefined;
  try {
    const body: ContainerCreateBody = {
      Image: image, Entrypoint: ["simnibs_python"], Cmd: ["-c", CUDA_PROBE],
      Env: ["NVIDIA_DRIVER_CAPABILITIES=compute,utility"],
      Labels: { "tit.gpu-probe": "true" }, ExposedPorts: {},
      HostConfig: { Binds: [], PortBindings: {}, NetworkMode: "none", DeviceRequests: [GPU_REQUEST] },
    };
    id = (await api.createContainer(body, { name: `ti-gpu-probe-${randomUUID()}`, platform })).Id;
    await client.startContainer(id);
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const state = await api.inspect(id);
      if (!state.running) return { available: state.exitCode === 0, reason: state.exitCode === 0 ? "CUDA computation passed" : `CUDA probe exited ${state.exitCode}` };
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    return { available: false, reason: "CUDA probe timed out" };
  } catch (error) {
    return { available: false, reason: error instanceof Error ? error.message : String(error) };
  } finally {
    if (id) await api.removeContainerById(id, true);
  }
}

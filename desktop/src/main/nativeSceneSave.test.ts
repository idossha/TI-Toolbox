/**
 * Main-process regression for the real native save orchestration used by index.ts.
 * Run with `npx vitest run src/main/nativeSceneSave.test.ts`.
 */
import { mkdtemp, mkdir, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createNativeSceneSession, type NativeSceneRequest } from "./nativeSceneBridge";
import {
  orchestrateNativeSceneSave,
  type NativeSceneSaveDependencies,
} from "./nativeSceneSave";

const roots: string[] = [];
const viewer = {
  supported: true,
  installed: true,
  installing: false,
  version: "fixture",
  directory: "/fixture",
  executable: "/fixture/TetraVox",
};

async function project() {
  const root = await realpath(await mkdtemp(join(tmpdir(), "ti-main-native-save-")));
  roots.push(root);
  const scenes = join(root, "code/ti-toolbox/viewer/scenes");
  await mkdir(scenes, { recursive: true });
  const source = join(scenes, "source.tetravox.json");
  const destination = join(scenes, "live.tetravox.json");
  await writeFile(source, '{"source":true}');
  return { root, source, destination };
}

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("index native-scene save orchestration", () => {
  it("sends the mapped host destination to native TetraVox but returns the server-jailed path", async () => {
    const fixture = await project();
    const requests: NativeSceneRequest[] = [];
    const nativeSession = createNativeSceneSession(async (request) => {
      requests.push(request);
      if (request.action === "save-scene") {
        await writeFile(request.path, '{"camera":{"zoom":2}}', { flag: "wx" });
      }
      return request.path;
    });
    await nativeSession.open(fixture.source, fixture.root, viewer);

    const backendSession = { origin: "http://127.0.0.1:8765", token: "secret" };
    const jailedPath = "/mnt/project/code/ti-toolbox/viewer/scenes/live.tetravox.json";
    const fetchDestination = vi.fn(async () => ({
      ok: true,
      json: async () => ({ scene_path: jailedPath }),
    }));
    const handoff = vi.fn(async (request: Parameters<NativeSceneSaveDependencies["handoff"]>[0]) => {
      await request.launch();
      return { ok: true as const };
    });

    const result = await orchestrateNativeSceneSave("live", {
      trusted: () => true,
      session: () => backendSession,
      projectRoot: async () => fixture.root,
      fetchDestination,
      resolveHostPath: async (path) => {
        expect(path).toBe(jailedPath);
        return { ok: true, path: fixture.destination };
      },
      saveNativeScene: (destination, root) => nativeSession.save(destination, root),
      handoff,
    });

    expect(result).toEqual({ ok: true, path: jailedPath });
    expect(requests[1]).toMatchObject({
      action: "save-scene",
      path: fixture.destination,
      expectedScenePath: fixture.source,
    });
    expect(fetchDestination).toHaveBeenCalledWith(
      `${backendSession.origin}/api/viewer/scenes/live/native-destination`,
      expect.objectContaining({
        method: "POST",
        headers: { authorization: `Bearer ${backendSession.token}` },
      }),
    );
    expect(handoff).toHaveBeenCalledOnce();
  });

  it("propagates cancellation without allocating or saving a destination", async () => {
    const fetchDestination = vi.fn();
    const saveNativeScene = vi.fn();
    const result = await orchestrateNativeSceneSave("live", {
      trusted: () => true,
      session: () => ({ origin: "http://127.0.0.1:8765", token: "secret" }),
      projectRoot: async () => "/host/project",
      fetchDestination,
      resolveHostPath: async () => ({ ok: true, path: "/host/project/live.tetravox.json" }),
      saveNativeScene,
      handoff: async () => ({ ok: false, cancelled: true }),
    });

    expect(result).toEqual({ ok: false, cancelled: true });
    expect(fetchDestination).not.toHaveBeenCalled();
    expect(saveNativeScene).not.toHaveBeenCalled();
  });
});

/** Authored filesystem fixtures pin correlation, cleanup and live-session boundaries.
 * Run npx vitest run src/main/nativeSceneBridge.test.ts; native rendering is verified separately. */
import { mkdtemp, mkdir, readFile, readdir, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { createNativeSceneSession, exchangeNativeSceneRequest, type NativeSceneRequest } from "./nativeSceneBridge";
import { supportsNativeSceneApi } from "./tetravoxNative";
const roots: string[] = [];
async function temporary() { const root = await realpath(await mkdtemp(join(tmpdir(), "ti-native-scene-"))); roots.push(root); return root; }
afterEach(async () => { await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true }))); });
const request: NativeSceneRequest = { protocol: 1, id: "authored-request", action: "open-scene", path: "/project/input.tetravox.json" };
const receipt = { protocol: 1, id: request.id, ok: true, path: request.path };
const viewer = { supported: true, installed: true, supportsSceneSave: true, installing: false, version: "1.0.0", directory: "/fixture", executable: "/fixture/Tetravox" };

describe("filesystem receipt exchange", () => {
  it("writes the request, accepts a bound receipt and cleans up", async () => {
    const root = await temporary();
    expect(await exchangeNativeSceneRequest(root, request, async (path) => {
      expect(JSON.parse(await readFile(path, "utf8"))).toEqual(request);
      await writeFile(`${path}.receipt.json`, JSON.stringify(receipt));
    })).toBe(request.path);
    expect(await readdir(root)).toEqual([]);
  });
  it.each([{ id: "stale" }, { protocol: 2 }, { path: "/other.tetravox.json" }])("rejects mismatched receipt %j", async (mismatch) => {
    const root = await temporary();
    await expect(exchangeNativeSceneRequest(root, request, async (path) => {
      await writeFile(`${path}.receipt.json`, JSON.stringify({ ...receipt, ...mismatch }));
    })).rejects.toThrow(/does not match|different scene path/);
    expect(await readdir(root)).toEqual([]);
  });
  it("rejects a null receipt and cleans up", async () => {
    const root = await temporary();
    await expect(exchangeNativeSceneRequest(root, request, async (path) => { await writeFile(`${path}.receipt.json`, "null"); })).rejects.toThrow();
    expect(await readdir(root)).toEqual([]);
  });
  it("surfaces failure receipts", async () => {
    const root = await temporary();
    await expect(exchangeNativeSceneRequest(root, request, async (path) => {
      await writeFile(`${path}.receipt.json`, JSON.stringify({ ...receipt, ok: false, error: "Save cancelled" }));
    })).rejects.toThrow("Save cancelled");
    expect(await readdir(root)).toEqual([]);
  });
  it("times out and cleans up", async () => {
    const root = await temporary();
    await expect(exchangeNativeSceneRequest(root, request, async () => undefined, 1)).rejects.toThrow("did not acknowledge");
    expect(await readdir(root)).toEqual([]);
  });
  it("cleans up failed dispatch", async () => {
    const root = await temporary();
    await expect(exchangeNativeSceneRequest(root, request, async () => { throw new Error("launch denied"); })).rejects.toThrow("launch denied");
    expect(await readdir(root)).toEqual([]);
  });
  it("rejects oversized receipt", async () => {
    const root = await temporary();
    await expect(exchangeNativeSceneRequest(root, request, async (path) => { await writeFile(`${path}.receipt.json`, " ".repeat(16 * 1024 + 1)); })).rejects.toThrow(/Invalid|too large/);
    expect(await readdir(root)).toEqual([]);
  });
  it.runIf(process.platform !== "win32")("rejects receipt symlinks and preserves target", async () => {
    const root = await temporary(); const target = join(await temporary(), "receipt.json");
    await writeFile(target, JSON.stringify(receipt));
    await expect(exchangeNativeSceneRequest(root, request, async (path) => { await symlink(target, `${path}.receipt.json`); })).rejects.toThrow("Invalid");
    expect(JSON.parse(await readFile(target, "utf8"))).toEqual(receipt);
    expect(await readdir(root)).toEqual([]);
  });
});
async function project() {
  const root = await temporary(); const scenes = join(root, "code/ti-toolbox/viewer/scenes"); await mkdir(scenes, { recursive: true });
  const scene = join(scenes, "source.tetravox.json"); await writeFile(scene, '{"fixture":"original"}');
  return { root, scene, destination: join(scenes, "live.tetravox.json") };
}
describe("acknowledged live session", () => {
  it("saves a scene loaded directly in TetraVox without a preceding TI open", async () => {
    const f = await project(); const requests: NativeSceneRequest[] = [];
    const live = { camera: { zoom: 3 }, layers: [{ opacity: 0.4 }] };
    const session = createNativeSceneSession(async (next) => {
      requests.push(next);
      await writeFile(next.path, JSON.stringify(live), { flag: "wx" });
      return next.path;
    });
    await expect(session.save(f.destination, f.root, viewer)).resolves.toBe(f.destination);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({ action: "save-scene", path: f.destination });
    expect(requests[0]).not.toHaveProperty("expectedScenePath");
    expect(JSON.parse(await readFile(f.destination, "utf8"))).toEqual(live);
  });
  it("rejects a viewer without the live capture capability", async () => {
    const f = await project();
    const session = createNativeSceneSession(async () => { throw new Error("must not dispatch"); });
    await expect(session.save(f.destination, f.root, { ...viewer, supportsSceneSave: false })).rejects.toThrow("does not support");
  });
  it("captures the active attachment after a previous TI open into the canonical scenes directory", async () => {
    const f = await project(); const requests: NativeSceneRequest[] = []; const live = { camera: { zoom: 2.5 }, layers: [{ opacity: 0.25 }] };
    const session = createNativeSceneSession(async (next, selected) => {
      requests.push(next); expect(selected).toBe(viewer);
      if (next.action === "save-scene") await writeFile(next.path, JSON.stringify(live), { flag: "wx" });
      return next.path;
    });
    await session.open(f.scene, f.root, viewer);
    expect(await session.save(f.destination, f.root, viewer)).toBe(f.destination);
    expect(JSON.parse(await readFile(f.destination, "utf8"))).toEqual(live);
    expect(requests[1]).toMatchObject({ action: "save-scene", path: f.destination });
    expect(requests[1]!.id).not.toBe(requests[0]!.id);
    expect(requests[1]).not.toHaveProperty("expectedScenePath");
    expect(JSON.parse(await readFile(f.scene, "utf8"))).toEqual({ fixture: "original" });
  });
  it.runIf(process.platform !== "win32")("canonicalizes a destination reached through a symlinked project root", async () => {
    const f = await project(); const aliasParent = await temporary(); const alias = join(aliasParent, "project-link");
    await symlink(f.root, alias, "dir");
    const session = createNativeSceneSession(async (next) => {
      if (next.action === "save-scene") await writeFile(next.path, '{"saved":true}', { flag: "wx" });
      return next.path;
    });
    await session.open(join(alias, "code/ti-toolbox/viewer/scenes/source.tetravox.json"), alias, viewer);
    await expect(session.save(join(alias, "code/ti-toolbox/viewer/scenes/live.tetravox.json"), alias, viewer)).resolves.toBe(f.destination);
    expect(JSON.parse(await readFile(f.destination, "utf8"))).toEqual({ saved: true });
  });
  it("captures into the newly active project after clearing a previous project", async () => {
    const f = await project(); const other = await project();
    const session = createNativeSceneSession(async (next) => {
      if (next.action === "save-scene") await writeFile(next.path, '{"live":true}', { flag: "wx" });
      return next.path;
    });
    await session.open(f.scene, f.root, viewer);
    session.clear();
    await expect(session.save(other.destination, other.root, viewer)).resolves.toBe(other.destination);
    expect(JSON.parse(await readFile(other.destination, "utf8"))).toEqual({ live: true });
  });
  it("rejects a save outside the canonical scenes directory", async () => {
    const f = await project(); const session = createNativeSceneSession(async (next) => next.path);
    await session.open(f.scene, f.root, viewer);
    await expect(session.save(join(f.root, "other.tetravox.json"), f.root, viewer)).rejects.toThrow();
  });
  it("refuses an existing destination without dispatching save", async () => {
    const f = await project(); const actions: string[] = [];
    const session = createNativeSceneSession(async (next) => { actions.push(next.action); return next.path; });
    await session.open(f.scene, f.root, viewer); await writeFile(f.destination, "preserve");
    await expect(session.save(f.destination, f.root, viewer)).rejects.toThrow("already exists");
    expect(actions).toEqual(["open-scene"]); expect(await readFile(f.destination, "utf8")).toBe("preserve");
  });
  it("clear during pending open rejects the obsolete acknowledgment", async () => {
    const f = await project(); let acknowledge!: (path: string) => void; let started!: () => void;
    const ready = new Promise<void>((resolve) => { started = resolve; });
    const session = createNativeSceneSession(async () => new Promise<string>((resolve) => { acknowledge = resolve; started(); }));
    const opening = session.open(f.scene, f.root, viewer); await ready;
    session.clear(); acknowledge(f.scene);
    await expect(opening).rejects.toThrow("active scene changed");
  });
});
it("requires explicit protocol capability rather than newer version", async () => {
  const root = await temporary(); await mkdir(join(root, "resources/app.asar"), { recursive: true });
  const metadata = join(root, "resources/app.asar/package.json"); const executable = join(root, "Tetravox");
  await writeFile(metadata, JSON.stringify({ version: "99.0.0" })); expect(await supportsNativeSceneApi(executable, "linux")).toBe(false);
  await writeFile(metadata, JSON.stringify({ sceneApiProtocol: 1 })); expect(await supportsNativeSceneApi(executable, "linux")).toBe(true);
});

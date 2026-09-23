/** Authored PNG fixture tests thumbnail publication; real renderer coverage runs separately. */
import { mkdir, mkdtemp, readFile, readdir, realpath, rm, stat, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createScenePreviewQueue, renderNativeScenePreview, type ScenePreviewOptions } from "./nativeScenePreview";
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN1sAAAAASUVORK5CYII=", "base64");
const roots: string[] = [];
afterEach(async () => { await Promise.all(roots.splice(0).map((path) => rm(path, { recursive: true, force: true }))); });
async function fixture(): Promise<ScenePreviewOptions> {
  const root = await realpath(await mkdtemp(join(tmpdir(), "ti-preview-")));
  roots.push(root);
  const scene = join(root, "code/ti-toolbox/viewer/scenes/live.tetravox.json");
  await mkdir(dirname(scene), { recursive: true });
  await writeFile(scene, '{"datasets":[],"layers":[],"camera":{"zoom":3}}');
  return { root, scene, userData: root, executable: "/fixture/TetraVox", current: () => true, resize: (bytes) => bytes,
    run: async (_, args, home) => {
      // Its own TETRAVOX_HOME inside the throwaway directory, never the user's ~/.tetravox.
      expect(home).toBe(join(args[3]!, "tetravox-home"));
      expect((await stat(home)).isDirectory()).toBe(true);
      const job = JSON.parse(await readFile(args[1]!, "utf8"));
      expect(job.scene.path).toBe(scene);
      expect(job.actions).toEqual([{ type: "screenshot", out: "preview.png", view: "grid", background: "scene" }]);
      expect(args).toContainEqual(expect.stringMatching(/^--user-data-dir=/));
      await writeFile(join(args[3]!, "preview.png"), png);
      return 0;
    },
  };
}
describe("native saved-scene previews", () => {
  it("publishes a sibling PNG, preserves the original and removes temporary outputs", async () => {
    const options = await fixture(); const original = await readFile(options.scene);
    await renderNativeScenePreview(options);
    expect(await readFile(options.scene.replace(".tetravox.json", ".png"))).toEqual(png);
    expect(await readFile(options.scene)).toEqual(original);
    expect((await readdir(options.root)).filter((name) => name.startsWith(".scene-preview"))).toEqual([]);
  });
  it("reuses an existing thumbnail without another render", async () => {
    const options = await fixture(); await renderNativeScenePreview(options);
    options.run = vi.fn(); await renderNativeScenePreview(options);
    expect(options.run).not.toHaveBeenCalled();
  });
  it("replaces a preview older than a scene re-saved in TetraVox", async () => {
    const options = await fixture(); const path = options.scene.replace(".tetravox.json", ".png");
    await writeFile(path, Buffer.concat([png, Buffer.from("old")]));
    const past = new Date(Date.now() - 60_000); await utimes(path, past, past);
    await renderNativeScenePreview(options);
    expect(await readFile(path)).toEqual(png);
    expect((await readdir(dirname(path))).filter((name) => name.endsWith(".tmp"))).toEqual([]);
  });
  it("does not overwrite an invalid existing sidecar", async () => {
    const options = await fixture(); const path = options.scene.replace(".tetravox.json", ".png");
    await writeFile(path, "user file");
    await expect(renderNativeScenePreview(options)).rejects.toThrow("preserved");
    expect(await readFile(path, "utf8")).toBe("user file");
  });
  it("does not publish after the project changes during capture", async () => {
    const options = await fixture(); const run = options.run!;
    let current = true;
    options.current = () => current;
    options.run = async (...args) => { const result = await run(...args); current = false; return result; };
    await expect(renderNativeScenePreview(options)).rejects.toThrow("changed");
    await expect(readFile(options.scene.replace(".tetravox.json", ".png"))).rejects.toMatchObject({ code: "ENOENT" });
  });
  it("refuses paths outside the saved-scene directory", async () => {
    const options = await fixture(); options.scene = join(options.root, "other.tetravox.json");
    await writeFile(options.scene, "{}");
    await expect(renderNativeScenePreview(options)).rejects.toThrow("saved scenes");
  });
  it("reports rendering failure without publishing a PNG or changing the scene", async () => {
    const options = await fixture(); const original = await readFile(options.scene);
    options.run = async () => 1;
    await expect(renderNativeScenePreview(options)).rejects.toThrow("exit 1");
    expect(await readFile(options.scene)).toEqual(original);
    await expect(readFile(options.scene.replace(".tetravox.json", ".png"))).rejects.toMatchObject({ code: "ENOENT" });
  });
  it("serializes captures and coalesces duplicate paths", async () => {
    const queue = createScenePreviewQueue(); const calls: string[] = []; let finish!: () => void;
    const first = queue("one", async () => { calls.push("one"); await new Promise<void>((resolve) => { finish = resolve; }); });
    expect(queue("one", async () => { calls.push("duplicate"); })).toBe(first);
    const second = queue("two", async () => { calls.push("two"); });
    await Promise.resolve(); expect(calls).toEqual(["one"]);
    finish(); await Promise.all([first, second]); expect(calls).toEqual(["one", "two"]);
  });
});

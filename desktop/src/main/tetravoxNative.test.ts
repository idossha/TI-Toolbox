import { createHash } from "node:crypto";
import { chmod, mkdtemp, mkdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { checkViewerScene, downloadViewer, installNativeViewer, nativeViewerPaths, nativeViewerStatus, openNativeViewer, viewerCommand } from "./tetravoxNative";
const dirs: string[] = [];
async function temporary() { const dir = await mkdtemp(join(tmpdir(), "ti-native-viewer-test-")); dirs.push(dir); return dir; }
afterEach(async () => { vi.unstubAllGlobals(); await Promise.all(dirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true }))); });
describe("native TetraVox", () => {
  it("selects native platform archives without substituting another architecture", () => {
    expect(nativeViewerPaths("/user", "darwin", "arm64").release?.asset).toMatch(/mac-arm64.zip$/);
    expect(nativeViewerPaths("/user", "linux", "x64").release?.asset).toMatch(/linux-x64.tar.gz$/);
    expect(nativeViewerPaths("/user", "win32", "x64").release).toBeUndefined();
    expect(nativeViewerPaths("/user", "linux", "arm64").release).toBeUndefined();
  });
  it("verifies download bytes and rejects changed bytes before installation", async () => {
    const dir = await temporary(); const bytes = Buffer.from("official bytes");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(bytes)));
    await downloadViewer("https://example.invalid", join(dir, "verified"), createHash("sha256").update(bytes).digest("hex"));
    await expect(downloadViewer("https://example.invalid", join(dir, "bad"), "0".repeat(64))).rejects.toThrow("checksum mismatch");
  });
  it("surfaces failed downloads", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));
    await expect(downloadViewer("https://example.invalid", join(await temporary(), "bad"), "0".repeat(64))).rejects.toThrow("503");
  });
  it("an unsuccessful install stays unready and can be retried", async () => {
    const dir = await temporary(); const fetch = vi.fn(async () => new Response("wrong archive")); vi.stubGlobal("fetch", fetch);
    await expect(installNativeViewer(dir)).rejects.toThrow("checksum");
    expect(await nativeViewerStatus(dir)).toMatchObject({ installed: false, installing: false });
    await expect(installNativeViewer(dir)).rejects.toThrow("checksum");
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("does not trust a missing binary or a binary modified after install", async () => {
    const dir = await temporary(); const paths = nativeViewerPaths(dir);
    expect((await nativeViewerStatus(dir)).installed).toBe(false);
    if (!paths.executable || !paths.release) return;
    await mkdir(join(paths.executable, ".."), { recursive: true });
    await writeFile(paths.executable, "original");
    await writeFile(join(paths.directory, "ready.json"), JSON.stringify({ archiveHash: paths.release.sha256, executableHash: createHash("sha256").update("original").digest("hex") }));
    expect((await nativeViewerStatus(dir)).installed).toBe(true);
    await writeFile(paths.executable, "modified");
    expect((await nativeViewerStatus(dir)).installed).toBe(false);
  });
  it("opens only an existing scene inside the real project root", async () => {
    const root = await temporary(); const outside = await temporary();
    const scene = join(root, "subject.tetravox.json"); await writeFile(scene, "{}");
    expect(await checkViewerScene(scene, root)).toContain("subject.tetravox.json");
    const external = join(outside, "external.tetravox.json"); await writeFile(external, "{}");
    await symlink(external, join(root, "escape.tetravox.json"));
    await expect(checkViewerScene(join(root, "escape.tetravox.json"), root)).rejects.toThrow("outside");
    await expect(checkViewerScene(external, root)).rejects.toThrow("outside");
    await expect(checkViewerScene(join(root, "data.nii"), root)).rejects.toThrow(".tetravox.json");
  });
  it.runIf(process.platform !== "win32")("reports an immediate native launch failure", async () => {
    const dir = await temporary(); const paths = nativeViewerPaths(dir);
    if (!paths.executable || !paths.release) throw new Error("Unsupported test platform");
    const program = "#!/bin/sh\necho missing-library >&2\nexit 1\n";
    await mkdir(join(paths.executable, ".."), { recursive: true });
    await writeFile(paths.executable, program); await chmod(paths.executable, 0o755);
    await writeFile(join(paths.directory, "ready.json"), JSON.stringify({ archiveHash: paths.release.sha256, executableHash: createHash("sha256").update(program).digest("hex") }));
    await expect(openNativeViewer(dir, "")).rejects.toThrow("missing-library");
  });
  it("reports a failed installer executable instead of claiming readiness", async () => {
    await expect(viewerCommand(join(await temporary(), "not-an-executable"), [])).rejects.toThrow();
  });
});

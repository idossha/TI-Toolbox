import { createHash } from "node:crypto";
import { chmod, mkdtemp, mkdir, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { compareViewerVersions, compatibleViewerVersion, feedChecksum, findSystemViewer, identifyViewerPath, latestViewerRelease, managedInstalls, parseReleaseFeed, pathViewerCandidates, pruneManagedViewers, selectViewer, setConfiguredViewerPathProvider, systemViewerCandidates, viewerProcessMatches, checkViewerScene, checkViewerUpdate, downloadViewer, installNativeViewer, nativeViewerPaths, nativeViewerStatus, openNativeViewer, viewerCommand, TETRAVOX_VERSION } from "./tetravoxNative";
// Do not let an application installed on the test machine shadow fixture-managed installs.
vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:child_process")>();
  const wrapped = (...args: unknown[]) => {
    const commandArgs = args[1] as string[];
    if (args[0] === "/usr/bin/plutil" && !commandArgs.at(-1)?.includes("ti-native-viewer-test-")) {
      const callback = args.at(-1) as (error: Error) => void;
      callback(new Error("No test-machine installation"));
      return undefined;
    }
    return (actual.execFile as (...values: unknown[]) => unknown)(...args);
  };
  Object.defineProperty(wrapped, Symbol.for("nodejs.util.promisify.custom"), { value: (...args: unknown[]) => new Promise((resolve, reject) => {
    wrapped(...args, (error: Error | null, stdout: string, stderr: string) => error ? reject(error) : resolve({ stdout, stderr }));
  }) });
  return { ...actual, execFile: wrapped };
});
const dirs: string[] = [];
async function temporary() { const dir = await mkdtemp(join(tmpdir(), "ti-native-viewer-test-")); dirs.push(dir); return dir; }
afterEach(async () => { vi.unstubAllGlobals(); await Promise.all(dirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true }))); });
describe("native TetraVox", () => {
  it("discovers an identified installed package without running its executable", async () => {
    const dir = await temporary();
    const exe = join(dir, "tetravox");
    await writeFile(exe, "#!/bin/sh\nexit 93\n"); await chmod(exe, 0o755);
    await mkdir(join(dir, "resources/app.asar"), { recursive: true });
    const metadata = join(dir, "resources/app.asar/package.json");
    await writeFile(metadata, JSON.stringify({ name: "@tetravox/app", version: "0.4.0" }));
    expect(await findSystemViewer([exe], "linux")).toMatchObject({ executable: await realpath(exe), version: "0.4.0" });
    await writeFile(metadata, JSON.stringify({ name: "other-app", version: "0.4.0" }));
    expect(await findSystemViewer([exe], "linux")).toBeUndefined();
    await writeFile(metadata, JSON.stringify({ name: "@tetravox/app", version: "0.3.9" }));
    expect(await findSystemViewer([exe], "linux")).toBeUndefined();
  });
  it.runIf(process.platform === "darwin")("requires an identified compatible Mac bundle", async () => {
    const dir = await temporary(); const bundle = join(dir, "Tetravox.app");
    await mkdir(join(bundle, "Contents/MacOS"), { recursive: true });
    await writeFile(join(bundle, "Contents/MacOS/Tetravox"), "fixture"); await chmod(join(bundle, "Contents/MacOS/Tetravox"), 0o755);
    const plist = (id: string) => `<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>${id}</string><key>CFBundleShortVersionString</key><string>0.4.0</string></dict></plist>`;
    await writeFile(join(bundle, "Contents/Info.plist"), plist("dev.tetravox.viewer"));
    expect(await findSystemViewer([bundle], "darwin")).toMatchObject({ directory: bundle, version: "0.4.0" });
    await writeFile(join(bundle, "Contents/Info.plist"), plist("other.app"));
    expect(await findSystemViewer([bundle], "darwin")).toBeUndefined();
  });
  it("does not confuse helper processes or similarly named applications with the viewer", () => {
    const executable = "/Applications/Tetravox.app/Contents/MacOS/Tetravox";
    expect(viewerProcessMatches(`${executable} /project/scene.tetravox.json`, executable, "darwin")).toBe(true);
    expect(viewerProcessMatches(`${executable}Helper`, executable, "darwin")).toBe(false);
    expect(viewerProcessMatches(`other ${executable}`, executable, "darwin")).toBe(false);
    expect(viewerProcessMatches(JSON.stringify({ ExecutablePath: "C:\\Tetravox.exe" }), "c:\\tetravox.exe", "win32")).toBe(true);
    expect(() => viewerProcessMatches("invalid", "viewer", "win32")).toThrow("Could not check");
    expect(() => viewerProcessMatches('{"ExecutablePath":null}', "viewer", "win32")).toThrow("Could not check");
  });
  it("restricts discovery to known installation roots and compatible scene versions", () => {
    expect(systemViewerCandidates("darwin", "/home/example")).toEqual(["/home/example/Applications/Tetravox.app", "/Applications/Tetravox.app"]);
    expect(compatibleViewerVersion("0.4.0")).toBe(true);
    expect(compatibleViewerVersion("0.3.11")).toBe(false);
    expect(compatibleViewerVersion("1.0.0")).toBe(false);
  });
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
  it.runIf(process.platform !== "win32")("launches a system app in its existing profile without managed environment", async () => {
    const dir = await temporary(); const executable = join(dir, "system-viewer");
    await writeFile(executable, '#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\nprintf "%s" "${TETRAVOX_MANAGED_BY-unset}" > "$0.env"\n');
    await chmod(executable, 0o755);
    await openNativeViewer(dir, "/project/example.tetravox.json", { supported: true, installed: true, installing: false, source: "system", executable, directory: dir, version: "0.4.0" });
    expect(await readFile(`${executable}.args`, "utf8")).toBe("/project/example.tetravox.json\n");
    expect(await readFile(`${executable}.env`, "utf8")).toBe("unset");
  });
  it("reports a failed installer executable instead of claiming readiness", async () => {
    await expect(viewerCommand(join(await temporary(), "not-an-executable"), [])).rejects.toThrow();
  });
});

describe("TetraVox resolution, updates and checksums", () => {
  /** A managed install fixture: the layout `managedInstalls` trusts, with a real executable digest. */
  async function managed(userData: string, version: string) {
    const paths = nativeViewerPaths(userData, process.platform, process.arch, version);
    if (!paths.executable) return undefined;
    await mkdir(join(paths.executable, ".."), { recursive: true });
    await writeFile(paths.executable, `binary-${version}`);
    await writeFile(join(paths.directory, "ready.json"), JSON.stringify({ version, executableHash: createHash("sha256").update(`binary-${version}`).digest("hex") }));
    return paths;
  }

  it("prefers a configured path, then the managed copy, then a system install, then PATH", () => {
    const viewer = (name: string) => ({ executable: `/${name}`, directory: "/", version: "0.4.0" });
    expect(selectViewer({})).toBeUndefined();
    expect(selectViewer({ path: viewer("p") })).toMatchObject({ source: "path", executable: "/p" });
    expect(selectViewer({ system: viewer("s"), path: viewer("p") })).toMatchObject({ source: "system" });
    expect(selectViewer({ managed: viewer("m"), system: viewer("s"), path: viewer("p") })).toMatchObject({ source: "managed" });
    expect(selectViewer({ configured: viewer("c"), managed: viewer("m"), system: viewer("s") })).toMatchObject({ source: "configured", executable: "/c" });
  });

  it("looks for the viewer on every PATH entry without trusting the name alone", async () => {
    expect(pathViewerCandidates("linux", { PATH: "/a:/b" })).toEqual(["/a/tetravox", "/b/tetravox"]);
    expect(pathViewerCandidates("linux", {})).toEqual([]);
    const dir = await temporary();
    const impostor = join(dir, "tetravox");
    await writeFile(impostor, "not the viewer"); await chmod(impostor, 0o755);
    expect(await findSystemViewer(pathViewerCandidates("linux", { PATH: dir }), "linux")).toBeUndefined();
  });

  it("rejects a located application that is not a compatible TetraVox", async () => {
    const dir = await temporary();
    const exe = join(dir, "tetravox");
    await writeFile(exe, "fixture"); await chmod(exe, 0o755);
    await expect(identifyViewerPath(exe, "linux")).rejects.toThrow("not a compatible TetraVox");
    await mkdir(join(dir, "resources/app.asar"), { recursive: true });
    await writeFile(join(dir, "resources/app.asar/package.json"), JSON.stringify({ name: "@tetravox/app", version: "0.5.1" }));
    expect(await identifyViewerPath(exe, "linux")).toMatchObject({ version: "0.5.1" });
  });

  it("uses a configured path ahead of anything else it could find", async () => {
    const userData = await temporary();
    const paths = await managed(userData, TETRAVOX_VERSION);
    if (!paths?.executable) return;
    expect(await nativeViewerStatus(userData)).toMatchObject({ installed: true, source: "managed" });

    const chosen = await temporary();
    const exe = join(chosen, "tetravox");
    await writeFile(exe, "fixture"); await chmod(exe, 0o755);
    await mkdir(join(chosen, "resources/app.asar"), { recursive: true });
    await writeFile(join(chosen, "resources/app.asar/package.json"), JSON.stringify({ name: "@tetravox/app", version: "0.6.0" }));
    setConfiguredViewerPathProvider(() => exe);
    try {
      const status = await nativeViewerStatus(userData);
      if (process.platform === "linux") expect(status).toMatchObject({ source: "configured", version: "0.6.0", configuredPathValid: true });
      setConfiguredViewerPathProvider(() => join(chosen, "gone"));
      expect(await nativeViewerStatus(userData)).toMatchObject({ source: "managed", configuredPathValid: false });
    } finally { setConfiguredViewerPathProvider(() => undefined); }
  });

  it("selects the newest managed install and can prune the rest", async () => {
    const userData = await temporary();
    if (!await managed(userData, "0.4.0")) return;
    await managed(userData, "0.5.2");
    expect((await managedInstalls(userData)).map((entry) => entry.version)).toEqual(["0.5.2", "0.4.0"]);
    expect(await nativeViewerStatus(userData)).toMatchObject({ source: "managed", version: "0.5.2" });
    await pruneManagedViewers(userData, "0.5.2");
    expect((await managedInstalls(userData)).map((entry) => entry.version)).toEqual(["0.5.2"]);
  });

  it("orders versions and only offers an update for the copy it owns", async () => {
    expect(compareViewerVersions("0.5.0", "0.4.9")).toBeGreaterThan(0);
    expect(compareViewerVersions("0.4.0", "0.4.0")).toBe(0);
    const userData = await temporary();
    const paths = nativeViewerPaths(userData, process.platform, process.arch, "0.5.0");
    if (!paths.release) return;
    await managed(userData, TETRAVOX_VERSION);
    const fetch = vi.fn(async () => new Response(JSON.stringify({ tag_name: "v0.5.0", assets: [{ name: paths.release!.asset }] }), { status: 200 }));
    expect(await checkViewerUpdate(userData, fetch as unknown as typeof globalThis.fetch)).toMatchObject({ source: "managed", updateAvailable: "0.5.0" });
    // A release with no package for this platform is not an available update.
    const barren = vi.fn(async () => new Response(JSON.stringify({ tag_name: "v0.6.0", assets: [{ name: "Tetravox-0.6.0-other.zip" }] }), { status: 200 }));
    expect((await checkViewerUpdate(userData, barren as unknown as typeof globalThis.fetch)).updateAvailable).toBeUndefined();
  });

  it("refuses a release feed that is absent, stale or silent about this asset", () => {
    const feed = parseReleaseFeed("version: 0.5.0\nfiles:\n  - url: Tetravox-0.5.0-mac-arm64.zip\n    sha512: AAAA==\n    size: 12\npath: Tetravox-0.5.0-mac-arm64.zip\n");
    expect(feed).toMatchObject({ version: "0.5.0" });
    expect(feedChecksum(feed, "Tetravox-0.5.0-mac-arm64.zip")).toBe("AAAA==");
    expect(feedChecksum(feed, "Tetravox-0.5.0-linux-x64.tar.gz")).toBeUndefined();
    expect(feedChecksum(undefined, "anything")).toBeUndefined();
    expect(parseReleaseFeed("files: []")).toBeUndefined();
  });

  it("verifies SHA512 download bytes as published by the update feed", async () => {
    const dir = await temporary();
    const bytes = Buffer.from("release bytes");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(bytes)));
    const sha512 = createHash("sha512").update(bytes).digest("base64");
    await downloadViewer("https://example.invalid", join(dir, "ok"), { algorithm: "sha512", value: sha512 });
    await expect(downloadViewer("https://example.invalid", join(dir, "bad"), { algorithm: "sha512", value: "AAAA==" })).rejects.toThrow("checksum mismatch");
  });

  it("installs nothing when a newer release publishes no checksum for this platform", async () => {
    const userData = await temporary();
    if (!nativeViewerPaths(userData, process.platform, process.arch, "0.5.0").release) return;
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 404 })));
    await expect(installNativeViewer(userData, "0.5.0")).rejects.toThrow("no update feed");
    expect(await managedInstalls(userData)).toEqual([]);
  });

  it("rejects an incompatible release outright", async () => {
    await expect(installNativeViewer(await temporary(), "1.0.0")).rejects.toThrow("not compatible");
  });

  it("reports a release lookup that names no version", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ tag_name: "nightly" }), { status: 200 }));
    await expect(latestViewerRelease(fetch as unknown as typeof globalThis.fetch)).rejects.toThrow("did not name a version");
    const failed = vi.fn(async () => new Response(null, { status: 403 }));
    await expect(latestViewerRelease(failed as unknown as typeof globalThis.fetch)).rejects.toThrow("403");
  });
});

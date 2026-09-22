import { createHash } from "node:crypto";
import { chmod, mkdtemp, mkdir, readFile, realpath, rename, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MANAGED_BY, compatibleViewerVersion, identifyViewer, identifyViewerPath, latestViewerRelease, managedInstalls, readAsarText, viewerProcessMatches, checkViewerScene, downloadViewer, installNativeViewer, nativeViewerPaths, nativeViewerStatus, openNativeViewer, updateNativeViewer, viewerCommand } from "./tetravoxNative";
const macOpen = vi.hoisted(() => ({ calls: [] as { args: string[]; env: NodeJS.ProcessEnv }[], error: undefined as Error | undefined }));
// Do not let an application installed on the test machine shadow fixture-managed installs.
vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:child_process")>();
  const wrapped = (...args: unknown[]) => {
    const commandArgs = args[1] as string[];
    if (args[0] === "/usr/bin/open") {
      macOpen.calls.push({ args: commandArgs, env: (args[2] as { env: NodeJS.ProcessEnv }).env });
      const callback = args.at(-1) as (error: Error | undefined, stdout: string, stderr: string) => void;
      callback(macOpen.error, "", "");
      return undefined;
    }
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
afterEach(async () => { macOpen.calls = []; macOpen.error = undefined; vi.unstubAllGlobals(); await Promise.all(dirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true }))); });
const status = (executable: string, directory: string) => ({ supported: true, installed: true, installing: false, source: "managed" as const, executable, directory, version: "0.4.0" });
/** What the non-mac launcher prepends on this platform (Linux runs the tarball without a setuid sandbox). */
const platformArgs = process.platform === "linux" ? ["--no-sandbox"] : [];

describe("native TetraVox", () => {
  it("identifies an installed package by its metadata without running its executable", async () => {
    const dir = await temporary();
    const exe = join(dir, "tetravox");
    await writeFile(exe, "#!/bin/sh\nexit 93\n"); await chmod(exe, 0o755);
    await mkdir(join(dir, "resources/app.asar"), { recursive: true });
    const metadata = join(dir, "resources/app.asar/package.json");
    await writeFile(metadata, JSON.stringify({ name: "@tetravox/app", version: "0.4.0" }));
    expect(await identifyViewer([exe], "linux")).toMatchObject({ executable: await realpath(exe), version: "0.4.0" });
    await writeFile(metadata, JSON.stringify({ name: "other-app", version: "0.4.0" }));
    expect(await identifyViewer([exe], "linux")).toBeUndefined();
    await writeFile(metadata, JSON.stringify({ name: "@tetravox/app", version: "0.3.9" }));
    expect(await identifyViewer([exe], "linux")).toBeUndefined();
  });
  it.runIf(process.platform === "darwin")("requires an identified compatible Mac bundle", async () => {
    const dir = await temporary(); const bundle = join(dir, "Tetravox.app");
    await mkdir(join(bundle, "Contents/MacOS"), { recursive: true });
    await writeFile(join(bundle, "Contents/MacOS/Tetravox"), "fixture"); await chmod(join(bundle, "Contents/MacOS/Tetravox"), 0o755);
    const plist = (id: string) => `<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>${id}</string><key>CFBundleShortVersionString</key><string>0.4.0</string></dict></plist>`;
    await writeFile(join(bundle, "Contents/Info.plist"), plist("dev.tetravox.viewer"));
    expect(await identifyViewer([bundle], "darwin")).toMatchObject({ directory: await realpath(bundle), version: "0.4.0" });
    const link = join(dir, "tetravox");
    await symlink(join(bundle, "Contents/MacOS/Tetravox"), link);
    expect(await identifyViewer([link], "darwin")).toMatchObject({ directory: await realpath(bundle), version: "0.4.0" });
    await writeFile(join(bundle, "Contents/Info.plist"), plist("other.app"));
    expect(await identifyViewer([bundle], "darwin")).toBeUndefined();
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
  it("detects a different installed binary sharing the default profile before replacement", () => {
    const selected = "/Applications/Tetravox.app/Contents/MacOS/Tetravox";
    expect(viewerProcessMatches("/Users/example/TI runtimes/Tetravox.app/Contents/MacOS/Tetravox /project/scene.tetravox.json", selected, "darwin")).toBe(true);
    expect(viewerProcessMatches("/opt/tetravox/tetravox --job /project/export.json", "/usr/bin/tetravox", "linux")).toBe(true);
    expect(viewerProcessMatches(JSON.stringify({ ExecutablePath: "D:\\Other install\\Tetravox.exe" }), "C:\\Tetravox.exe", "win32")).toBe(true);
    expect(viewerProcessMatches("/opt/tetravox/tetravox-helper", "/usr/bin/tetravox", "linux")).toBe(false);
    expect(viewerProcessMatches("", selected, "darwin")).toBe(false);
  });
  it("accepts 0.4 and newer scene versions", () => {
    expect(compatibleViewerVersion("0.4.0")).toBe(true);
    expect(compatibleViewerVersion("0.3.11")).toBe(false);
    expect(compatibleViewerVersion("1.0.0")).toBe(true);
  });
  it("names the official archive for every supported platform and none for the rest", () => {
    expect(nativeViewerPaths("/user", "darwin", "arm64", "0.6.1").release).toMatchObject({ asset: "Tetravox-0.6.1-mac-arm64.zip", strip: 0 });
    expect(nativeViewerPaths("/user", "darwin", "x64", "0.6.1").release?.asset).toBe("Tetravox-0.6.1-mac-x64.zip");
    expect(nativeViewerPaths("/user", "linux", "x64", "0.6.1").release).toMatchObject({ asset: "Tetravox-0.6.1-linux-x64.tar.gz", executable: "tetravox", strip: 1 });
    expect(nativeViewerPaths("/user", "win32", "x64", "0.6.1")).toMatchObject({ release: { asset: "Tetravox-0.6.1-win-x64.zip", executable: "Tetravox.exe", strip: 0 }, executable: join("/user", "runtimes", "tetravox-win32-x64", "Tetravox.exe") });
    expect(nativeViewerPaths("/user", "linux", "arm64").release).toBeUndefined();
    expect(nativeViewerPaths("/user", "win32", "arm64").release).toBeUndefined();
  });
  it("verifies download bytes against the published SHA-256 and rejects changed bytes", async () => {
    const dir = await temporary(); const bytes = Buffer.from("official bytes");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(bytes)));
    await downloadViewer("https://example.invalid", join(dir, "verified"), createHash("sha256").update(bytes).digest("hex").toUpperCase());
    await expect(downloadViewer("https://example.invalid", join(dir, "bad"), "0".repeat(64))).rejects.toThrow("checksum mismatch");
  });
  it("surfaces failed downloads", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));
    await expect(downloadViewer("https://example.invalid", join(await temporary(), "bad"), "0".repeat(64))).rejects.toThrow("503");
  });
  it("an unsuccessful install stays unready and can be retried", async () => {
    const dir = await temporary(); const fetch = vi.fn(async () => new Response("not json")); vi.stubGlobal("fetch", fetch);
    await expect(installNativeViewer(dir)).rejects.toThrow();
    expect(await nativeViewerStatus(dir)).toMatchObject({ installed: false, installing: false });
    await expect(installNativeViewer(dir)).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(nativeViewerPaths(dir).release ? 2 : 0);
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
    const dir = await temporary(); const executable = join(dir, "failing-viewer");
    await writeFile(executable, "#!/bin/sh\necho missing-library >&2\nexit 1\n"); await chmod(executable, 0o755);
    await expect(openNativeViewer(dir, "", status(executable, dir))).rejects.toThrow("missing-library");
  });
  it.runIf(process.platform !== "win32")("launches TI's copy with the managed-by flag so the viewer leaves updates to TI", async () => {
    const dir = await temporary(); const executable = join(dir, "managed-viewer");
    await writeFile(executable, '#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\nprintf "%s" "${TETRAVOX_MANAGED_BY-unset}" > "$0.env"\n');
    await chmod(executable, 0o755);
    await openNativeViewer(dir, "/project/example.tetravox.json", status(executable, dir));
    expect(await readFile(`${executable}.args`, "utf8")).toBe([...platformArgs, "/project/example.tetravox.json"].join("\n") + "\n");
    expect(await readFile(`${executable}.env`, "utf8")).toBe(MANAGED_BY);
  });
  it.runIf(process.platform !== "win32")("keeps using an earlier layout's profile directory", async () => {
    const dir = await temporary(); const executable = join(dir, "legacy-viewer");
    await mkdir(join(dir, "tetravox-profile"));
    await writeFile(executable, '#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\n');
    await chmod(executable, 0o755);
    await openNativeViewer(dir, "/project/example.tetravox.json", status(executable, dir));
    expect(await readFile(`${executable}.args`, "utf8")).toBe([...platformArgs, `--user-data-dir=${join(dir, "tetravox-profile")}`, "/project/example.tetravox.json"].join("\n") + "\n");
  });
  it.runIf(process.platform === "darwin")("reopens a Dock-only app through LaunchServices and delivers its scene only once", async () => {
    const dir = await temporary();
    const bundle = join(dir, "Tetravox.app");
    const executable = join(bundle, "Contents/MacOS/Tetravox");
    await mkdir(join(dir, "tetravox-profile"));
    await openNativeViewer(dir, "/project/a scene.tetravox.json", { ...status(executable, dir), version: "1.0.0" });
    const profile = ["--args", `--user-data-dir=${join(dir, "tetravox-profile")}`];
    expect(macOpen.calls.map((call) => call.args)).toEqual([
      ["-a", bundle, "/project/a scene.tetravox.json", ...profile],
      ["-a", bundle, ...profile],
    ]);
    expect(macOpen.calls.every((call) => call.env.TETRAVOX_MANAGED_BY === MANAGED_BY && call.env.ELECTRON_RUN_AS_NODE === undefined)).toBe(true);
  });
  it.runIf(process.platform === "darwin")("delivers protocol request through argv before scene-free activation", async () => {
    const dir = await temporary(); const bundle = join(dir, "Tetravox.app"); const executable = join(bundle, "Contents/MacOS/Tetravox");
    await mkdir(join(bundle, "Contents/MacOS"), { recursive: true });
    await writeFile(executable, '#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\n'); await chmod(executable, 0o755);
    const requestPath = join(dir, "request.json");
    await openNativeViewer(dir, "/project/scene.tetravox.json", { ...status(executable, bundle), version: "1.0.0" }, requestPath);
    expect(await readFile(`${executable}.args`, "utf8")).toBe(`--scene-request=${requestPath}\n`);
    expect(macOpen.calls.map((call) => call.args)).toEqual([["-a", bundle]]);
  });
  it.runIf(process.platform === "darwin")("blank Mac launch only requests activation of the bundle", async () => {
    const dir = await temporary(); const bundle = join(dir, "Tetravox.app");
    await openNativeViewer(dir, "", { ...status(join(bundle, "Contents/MacOS/Tetravox"), bundle), version: "1.0.0" });
    expect(macOpen.calls.map((call) => call.args)).toEqual([["-a", bundle]]);
  });
  it.runIf(process.platform === "darwin")("surfaces LaunchServices rejection without replaying the scene", async () => {
    const dir = await temporary(); macOpen.error = new Error("LaunchServices rejected application");
    await expect(openNativeViewer(dir, "/project/scene.tetravox.json", { ...status(join(dir, "Tetravox.app/Contents/MacOS/Tetravox"), dir), version: "1.0.0" })).rejects.toThrow("LaunchServices rejected");
    expect(macOpen.calls).toHaveLength(1);
  });
  it("reports a failed installer executable instead of claiming readiness", async () => {
    await expect(viewerCommand(join(await temporary(), "not-an-executable"), [])).rejects.toThrow();
  });
});

describe("TI's own TetraVox: setup, update and checksums", () => {
  /** A managed install fixture: the layout `managedInstalls` trusts. */
  async function managed(userData: string, version: string) {
    const paths = nativeViewerPaths(userData, process.platform, process.arch, version);
    if (!paths.executable) return undefined;
    await mkdir(join(paths.executable, ".."), { recursive: true });
    await writeFile(paths.executable, `binary-${version}`);
    await chmod(paths.executable, 0o755);
    if (process.platform === "darwin") {
      await writeFile(join(paths.directory, "Tetravox.app/Contents/Info.plist"), `<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>dev.tetravox.viewer</string><key>CFBundleShortVersionString</key><string>${version}</string></dict></plist>`);
    } else {
      await mkdir(join(paths.directory, "resources/app.asar"), { recursive: true });
      await writeFile(join(paths.directory, "resources/app.asar/package.json"), JSON.stringify({ name: "@tetravox/app", version }));
    }
    return paths;
  }
  /** An official-looking archive of a managed fixture, in this platform's release format. */
  async function archiveOf(version: string): Promise<{ bytes: Buffer; asset: string }> {
    const source = await temporary();
    const paths = await managed(source, version);
    if (!paths) throw new Error("Fixture needs a supported platform");
    const { release } = paths;
    const archive = join(source, release!.asset);
    if (process.platform === "darwin") await viewerCommand("/usr/bin/ditto", ["-c", "-k", "--keepParent", join(paths.directory, "Tetravox.app"), archive]);
    else if (process.platform === "linux") {
      // The Linux tarball wraps the tree in one versioned directory (strip: 1).
      const wrapped = join(source, "wrapped", `Tetravox-${version}-linux-x64`);
      await mkdir(join(source, "wrapped"), { recursive: true });
      await rename(paths.directory, wrapped);
      await viewerCommand("tar", ["-czf", archive, "-C", join(source, "wrapped"), `Tetravox-${version}-linux-x64`]);
    } else {
      await viewerCommand(join(process.env.SystemRoot ?? "C:\\Windows", "System32", "tar.exe"), ["-a", "-cf", archive, "-C", paths.directory, "."]);
    }
    return { bytes: await readFile(archive), asset: release!.asset };
  }
  /** GitHub's release answer for one version, with the digest it publishes per asset. */
  const releaseJson = (version: string, asset: string, bytes?: Buffer, digest?: string) =>
    JSON.stringify({ tag_name: `v${version}`, assets: [{ name: asset, ...(digest !== undefined ? { digest } : bytes ? { digest: `sha256:${createHash("sha256").update(bytes).digest("hex")}` } : {}) }] });
  function serve(version: string, archive: { bytes: Buffer; asset: string }, beforeArchive?: () => Promise<void>) {
    const network = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/releases/latest")) return new Response(releaseJson(version, archive.asset, archive.bytes));
      await beforeArchive?.();
      return new Response(archive.bytes);
    });
    vi.stubGlobal("fetch", network);
    return network;
  }
  const supported = !!nativeViewerPaths("/x").release && process.platform !== "win32";

  it("only ever reports TI's own copy; nothing on the machine is consulted", async () => {
    const userData = await temporary();
    const empty = await nativeViewerStatus(userData);
    expect(empty).toMatchObject({ installed: false, supported: !!nativeViewerPaths(userData).release });
    expect(empty.source).toBeUndefined();
    const paths = await managed(userData, "0.4.0");
    if (!paths) return;
    expect(await nativeViewerStatus(userData)).toMatchObject({ installed: true, source: "managed", version: "0.4.0", executable: await realpath(paths.executable!) });
  });

  it("reads a file out of a real asar archive by its header, and out of an unpacked directory", async () => {
    // Build the archive the way `@electron/asar` lays it out: [u32 4][u32 header pickle size]
    // [u32 json payload size][u32 json length][json, padded to 4] then file data.
    const files = { "package.json": JSON.stringify({ name: "@tetravox/app", version: "0.6.1" }), "nested/hello.txt": "hi" };
    const directory: { files: Record<string, unknown> } = { files: {} };
    const blobs: Buffer[] = [];
    let offset = 0;
    for (const [name, text] of Object.entries(files)) {
      const data = Buffer.from(text);
      let node = directory;
      const parts = name.split("/");
      for (const part of parts.slice(0, -1)) node = (node.files[part] ??= { files: {} }) as typeof directory;
      node.files[parts.at(-1)!] = { size: data.length, offset: String(offset) };
      offset += data.length; blobs.push(data);
    }
    const json = Buffer.from(JSON.stringify(directory));
    const padded = json.length + ((4 - (json.length % 4)) % 4);
    const head = Buffer.alloc(16);
    head.writeUInt32LE(4, 0); head.writeUInt32LE(8 + padded, 4); head.writeUInt32LE(4 + padded, 8); head.writeUInt32LE(json.length, 12);
    const dir = await temporary();
    const archive = join(dir, "app.asar");
    await writeFile(archive, Buffer.concat([head, json, Buffer.alloc(padded - json.length), ...blobs]));
    expect(JSON.parse(await readAsarText(archive, "package.json"))).toEqual({ name: "@tetravox/app", version: "0.6.1" });
    expect(await readAsarText(archive, "nested/hello.txt")).toBe("hi");
    await expect(readAsarText(archive, "missing.txt")).rejects.toThrow("not in");
    await writeFile(archive, "not an archive at all, just text");
    await expect(readAsarText(archive, "package.json")).rejects.toThrow();
    const unpacked = join(dir, "unpacked.asar");
    await mkdir(unpacked); await writeFile(join(unpacked, "package.json"), "{}");
    expect(await readAsarText(unpacked, "package.json")).toBe("{}");
  });

  it("identifies an unpacked archive by path and rejects anything else", async () => {
    const dir = await temporary();
    const exe = join(dir, "tetravox");
    await writeFile(exe, "fixture"); await chmod(exe, 0o755);
    await expect(identifyViewerPath(exe, "linux")).rejects.toThrow("not a compatible TetraVox");
    await mkdir(join(dir, "resources/app.asar"), { recursive: true });
    await writeFile(join(dir, "resources/app.asar/package.json"), JSON.stringify({ name: "@tetravox/app", version: "0.5.1" }));
    expect(await identifyViewerPath(exe, "linux")).toMatchObject({ version: "0.5.1" });
  });

  it.runIf(supported)("coalesces first setup, verifies the archive digest and requires application identity", async () => {
    const archive = await archiveOf("1.1.0");
    const network = serve("1.1.0", archive);
    const userData = await temporary();
    const results = await Promise.all([installNativeViewer(userData), installNativeViewer(userData)]);
    expect(results).toMatchObject([{ installed: true, installing: false, version: "1.1.0", source: "managed" }, { installed: true, installing: false, version: "1.1.0" }]);
    expect(network.mock.calls.filter(([url]) => String(url).includes("/releases/download/"))).toHaveLength(1);
    expect(JSON.parse(await readFile(join(results[0]!.directory, "ready.json"), "utf8"))).toMatchObject({ version: "1.1.0", managedBy: MANAGED_BY });
    // A completed download is insufficient if the app identity has disappeared.
    await rm(process.platform === "darwin" ? join(results[0]!.directory, "Tetravox.app/Contents/Info.plist") : join(results[0]!.directory, "resources/app.asar/package.json"));
    expect(await managedInstalls(userData)).toEqual([]);
  });

  it.runIf(supported)("refuses a release that publishes no digest for this platform's package", async () => {
    const userData = await temporary();
    const asset = nativeViewerPaths(userData, process.platform, process.arch, "1.1.0").release!.asset;
    const network = vi.fn(async (input: string | URL | Request) => String(input).endsWith("/releases/latest")
      ? new Response(releaseJson("1.1.0", asset, undefined, "md5:abc"))
      : new Response("never fetched"));
    vi.stubGlobal("fetch", network);
    await expect(installNativeViewer(userData)).rejects.toThrow("publishes no checksum");
    expect(await managedInstalls(userData)).toEqual([]);
    expect(network.mock.calls.some(([url]) => String(url).includes("/releases/download/"))).toBe(false);
  });

  it.runIf(supported)("refuses an archive whose bytes differ from the published digest", async () => {
    const archive = await archiveOf("1.1.0");
    const userData = await temporary();
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => String(input).endsWith("/releases/latest")
      ? new Response(releaseJson("1.1.0", archive.asset, Buffer.from("other bytes")))
      : new Response(archive.bytes)));
    await expect(installNativeViewer(userData)).rejects.toThrow("checksum mismatch");
    expect(await managedInstalls(userData)).toEqual([]);
  });

  it.runIf(supported)("does not replace an installation that appears while downloading", async () => {
    const archive = await archiveOf("1.1.0");
    const userData = await temporary();
    serve("1.1.0", archive, async () => { await managed(userData, "2.0.0"); });
    const result = await installNativeViewer(userData);
    expect(result).toMatchObject({ installed: true, installing: false, version: "2.0.0" });
    expect(await readFile(result.executable!, "utf8")).toBe("binary-2.0.0");
  });

  it.runIf(supported)("preserves existing files when the archive identifies another version", async () => {
    const archive = await archiveOf("2.0.0");
    const userData = await temporary();
    const target = nativeViewerPaths(userData, process.platform, process.arch, "1.1.0");
    await mkdir(target.directory, { recursive: true });
    await writeFile(join(target.directory, "user-file"), "preserve existing contents");
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => String(input).endsWith("/releases/latest")
      ? new Response(releaseJson("1.1.0", archive.asset.replace("2.0.0", "1.1.0"), archive.bytes))
      : new Response(archive.bytes)));
    await expect(installNativeViewer(userData)).rejects.toThrow("archive identifies version");
    expect(await readFile(join(target.directory, "user-file"), "utf8")).toBe("preserve existing contents");
    expect(await managedInstalls(userData)).toEqual([]);
  });

  it.runIf(supported)("updates TI's copy to a newer release and leaves nothing of the old one behind", async () => {
    const userData = await temporary();
    const old = await managed(userData, "0.5.0");
    const archive = await archiveOf("0.6.1");
    const network = serve("0.6.1", archive);
    const result = await updateNativeViewer(userData);
    expect(result).toMatchObject({ installed: true, version: "0.6.1", directory: old!.directory });
    expect(await managedInstalls(userData)).toHaveLength(1);
    expect(network.mock.calls.filter(([url]) => String(url).includes("/releases/download/"))).toHaveLength(1);
    await expect(readFile(`${old!.directory}.previous`)).rejects.toThrow();
  });

  it.runIf(supported)("an update that is already current downloads nothing", async () => {
    const userData = await temporary();
    await managed(userData, "0.6.1");
    const network = vi.fn(async () => new Response(releaseJson("0.6.1", nativeViewerPaths(userData, process.platform, process.arch, "0.6.1").release!.asset, Buffer.from("x"))));
    vi.stubGlobal("fetch", network);
    expect(await updateNativeViewer(userData)).toMatchObject({ installed: true, version: "0.6.1" });
    expect(network).toHaveBeenCalledTimes(1);
  });

  it("discovers earlier version-addressed directories and a swap's `.previous` directory", async () => {
    const userData = await temporary();
    const paths = await managed(userData, "2.0.0");
    if (!paths) throw new Error("Fixture needs supported layout");
    const historical = join(userData, "runtimes", `tetravox-0.4.0-${process.platform}-${process.arch}`);
    await rename(paths.directory, historical);
    expect(await managedInstalls(userData)).toMatchObject([{ version: "2.0.0", directory: historical }]);
    await rename(historical, `${paths.directory}.previous`);
    expect(await managedInstalls(userData)).toMatchObject([{ version: "2.0.0", directory: `${paths.directory}.previous` }]);
  });

  it("reuses an installed copy on launch without any network request", async () => {
    const userData = await temporary();
    const paths = await managed(userData, "1.2.0");
    if (!paths?.executable) throw new Error("Fixture needs supported layout");
    const network = vi.fn(() => { throw new Error("Must not check releases"); });
    vi.stubGlobal("fetch", network);
    expect(await installNativeViewer(userData)).toMatchObject({ installed: true, version: "1.2.0" });
    expect(network).not.toHaveBeenCalled();
    expect(nativeViewerPaths(userData, process.platform, process.arch, "9.0.0").directory).toBe(paths.directory);
  });

  it("reads the version and per-asset SHA-256 digests from the release lookup", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ tag_name: "v0.6.1", assets: [{ name: "a.zip", digest: "sha256:" + "A".repeat(64) }, { name: "b.zip" }, { name: "c.zip", digest: "sha512:zz" }] })));
    expect(await latestViewerRelease(fetch as unknown as typeof globalThis.fetch)).toEqual({ version: "0.6.1", assets: { "a.zip": "a".repeat(64), "b.zip": undefined, "c.zip": undefined } });
    const nightly = vi.fn(async () => new Response(JSON.stringify({ tag_name: "nightly" }), { status: 200 }));
    await expect(latestViewerRelease(nightly as unknown as typeof globalThis.fetch)).rejects.toThrow("did not name a version");
    const failed = vi.fn(async () => new Response(null, { status: 403 }));
    await expect(latestViewerRelease(failed as unknown as typeof globalThis.fetch)).rejects.toThrow("403");
  });
});

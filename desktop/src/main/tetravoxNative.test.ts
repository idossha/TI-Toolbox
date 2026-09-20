import { createHash } from "node:crypto";
import { chmod, mkdtemp, mkdir, readFile, realpath, rename, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { compatibleViewerVersion, feedChecksum, findSystemViewer, identifyViewerPath, latestViewerRelease, managedInstalls, parseReleaseFeed, pathViewerCandidates, selectViewer, setConfiguredViewerPathProvider, systemViewerCandidates, viewerProcessMatches, checkViewerScene, downloadViewer, installNativeViewer, nativeViewerPaths, nativeViewerStatus, openNativeViewer, viewerCommand } from "./tetravoxNative";
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
    expect(await findSystemViewer([bundle], "darwin")).toMatchObject({ directory: await realpath(bundle), version: "0.4.0" });
    const link = join(dir, "tetravox");
    await symlink(join(bundle, "Contents/MacOS/Tetravox"), link);
    expect(await findSystemViewer([link], "darwin")).toMatchObject({ directory: await realpath(bundle), version: "0.4.0" });
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
  it("detects a different installed binary sharing the default profile before replacement", () => {
    const selected = "/Applications/Tetravox.app/Contents/MacOS/Tetravox";
    expect(viewerProcessMatches("/Users/example/TI runtimes/Tetravox.app/Contents/MacOS/Tetravox /project/scene.tetravox.json", selected, "darwin")).toBe(true);
    expect(viewerProcessMatches("/opt/tetravox/tetravox --job /project/export.json", "/usr/bin/tetravox", "linux")).toBe(true);
    expect(viewerProcessMatches(JSON.stringify({ ExecutablePath: "D:\\Other install\\Tetravox.exe" }), "C:\\Tetravox.exe", "win32")).toBe(true);
    expect(viewerProcessMatches("/opt/tetravox/tetravox-helper", "/usr/bin/tetravox", "linux")).toBe(false);
    expect(viewerProcessMatches("", selected, "darwin")).toBe(false);
  });
  it("restricts discovery to known installation roots and compatible scene versions", () => {
    expect(systemViewerCandidates("darwin", "/home/example")).toEqual(["/home/example/Applications/Tetravox.app", "/Applications/Tetravox.app"]);
    expect(compatibleViewerVersion("0.4.0")).toBe(true);
    expect(compatibleViewerVersion("0.3.11")).toBe(false);
    expect(compatibleViewerVersion("1.0.0")).toBe(true);
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
    await expect(installNativeViewer(dir)).rejects.toThrow();
    expect(await nativeViewerStatus(dir)).toMatchObject({ installed: false, installing: false });
    await expect(installNativeViewer(dir)).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(process.platform === "darwin" ? 2 : 0);
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
    const dir = await temporary(); const paths = { ...nativeViewerPaths(dir), executable: join(dir, "failing-viewer") };
    const program = "#!/bin/sh\necho missing-library >&2\nexit 1\n";
    await mkdir(join(paths.executable, ".."), { recursive: true });
    await writeFile(paths.executable, program); await chmod(paths.executable, 0o755);
    await expect(openNativeViewer(dir, "", { supported: true, installed: true, installing: false, source: "managed", executable: paths.executable, directory: dir, version: "0.4.0" })).rejects.toThrow("missing-library");
  });
  it.runIf(process.platform !== "win32")("launches a system app in its existing profile without managed environment", async () => {
    const dir = await temporary(); const executable = join(dir, "system-viewer");
    await writeFile(executable, '#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\nprintf "%s" "${TETRAVOX_MANAGED_BY-unset}" > "$0.env"\n');
    await chmod(executable, 0o755);
    await openNativeViewer(dir, "/project/example.tetravox.json", { supported: true, installed: true, installing: false, source: "system", executable, directory: dir, version: "0.4.0" });
    expect(await readFile(`${executable}.args`, "utf8")).toBe("/project/example.tetravox.json\n");
    expect(await readFile(`${executable}.env`, "utf8")).toBe("unset");
  });
  it.runIf(process.platform !== "win32")("preserves an existing managed profile without suppressing viewer updates", async () => {
    const dir = await temporary(); const executable = join(dir, "legacy-viewer");
    await mkdir(join(dir, "tetravox-profile"));
    await writeFile(executable, '#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\nprintf "%s" "${TETRAVOX_MANAGED_BY-unset}" > "$0.env"\n');
    await chmod(executable, 0o755);
    await openNativeViewer(dir, "/project/example.tetravox.json", { supported: true, installed: true, installing: false, source: "managed", executable, directory: dir, version: "0.4.0" });
    expect(await readFile(`${executable}.args`, "utf8")).toBe(`--user-data-dir=${join(dir, "tetravox-profile")}\n/project/example.tetravox.json\n`);
    expect(await readFile(`${executable}.env`, "utf8")).toBe("unset");
  });
  it.runIf(process.platform === "darwin")("reopens a Dock-only app through LaunchServices and delivers its scene only once", async () => {
    const dir = await temporary();
    const bundle = join(dir, "Tetravox.app");
    const executable = join(bundle, "Contents/MacOS/Tetravox");
    await mkdir(join(dir, "tetravox-profile"));
    await openNativeViewer(dir, "/project/a scene.tetravox.json", { supported: true, installed: true, installing: false, version: "1.0.0", source: "managed", executable, directory: dir });
    const profile = ["--args", `--user-data-dir=${join(dir, "tetravox-profile")}`];
    expect(macOpen.calls.map((call) => call.args)).toEqual([
      ["-a", bundle, "/project/a scene.tetravox.json", ...profile],
      ["-a", bundle, ...profile],
    ]);
    expect(macOpen.calls.every((call) => call.env.TETRAVOX_MANAGED_BY === undefined && call.env.ELECTRON_RUN_AS_NODE === undefined)).toBe(true);
  });
  it.runIf(process.platform === "darwin")("delivers protocol request through argv before scene-free activation", async () => {
    const dir = await temporary(); const bundle = join(dir, "Tetravox.app"); const executable = join(bundle, "Contents/MacOS/Tetravox");
    await mkdir(join(bundle, "Contents/MacOS"), { recursive: true });
    await writeFile(executable, '#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\n'); await chmod(executable, 0o755);
    const requestPath = join(dir, "request.json");
    await openNativeViewer(dir, "/project/scene.tetravox.json", { supported: true, installed: true, installing: false, version: "1.0.0", source: "system", executable, directory: bundle }, requestPath);
    expect(await readFile(`${executable}.args`, "utf8")).toBe(`--scene-request=${requestPath}\n`);
    expect(macOpen.calls.map((call) => call.args)).toEqual([["-a", bundle]]);
  });
  it.runIf(process.platform === "darwin")("blank Mac launch only requests activation of the selected bundle", async () => {
    const dir = await temporary(); const bundle = join(dir, "Chosen.app");
    await openNativeViewer(dir, "", { supported: true, installed: true, installing: false, version: "1.0.0", source: "configured", executable: join(bundle, "Contents/MacOS/Tetravox"), directory: bundle });
    expect(macOpen.calls.map((call) => call.args)).toEqual([["-a", bundle]]);
  });
  it.runIf(process.platform === "darwin")("surfaces LaunchServices rejection without replaying the scene", async () => {
    const dir = await temporary(); macOpen.error = new Error("LaunchServices rejected application");
    await expect(openNativeViewer(dir, "/project/scene.tetravox.json", { supported: true, installed: true, installing: false, version: "1.0.0", source: "system", executable: join(dir, "Tetravox.app/Contents/MacOS/Tetravox"), directory: dir })).rejects.toThrow("LaunchServices rejected");
    expect(macOpen.calls).toHaveLength(1);
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
    await chmod(paths.executable, 0o755);
    if (process.platform === "darwin") {
      await writeFile(join(paths.directory, "Tetravox.app/Contents/Info.plist"), `<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>dev.tetravox.viewer</string><key>CFBundleShortVersionString</key><string>${version}</string></dict></plist>`);
    } else {
      await mkdir(join(paths.directory, "resources/app.asar"), { recursive: true });
      await writeFile(join(paths.directory, "resources/app.asar/package.json"), JSON.stringify({ name: "@tetravox/app", version }));
    }
    return paths;
  }

  it("prefers a configured path, then a system install, then PATH, then the managed copy", () => {
    const viewer = (name: string) => ({ executable: `/${name}`, directory: "/", version: "0.4.0" });
    expect(selectViewer({})).toBeUndefined();
    expect(selectViewer({ path: viewer("p") })).toMatchObject({ source: "path", executable: "/p" });
    expect(selectViewer({ system: viewer("s"), path: viewer("p") })).toMatchObject({ source: "system" });
    expect(selectViewer({ managed: viewer("m"), system: viewer("s"), path: viewer("p") })).toMatchObject({ source: "system" });
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
    const paths = await managed(userData, "0.4.0");
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

  it.each(["linux", "win32"] as const)("does not download on unsupported %s bootstrap", async (platform) => {
    const original = Object.getOwnPropertyDescriptor(process, "platform")!;
    Object.defineProperty(process, "platform", { value: platform });
    const network = vi.fn(() => { throw new Error("No unsupported download"); });
    vi.stubGlobal("fetch", network);
    try {
      await expect(installNativeViewer(await temporary())).rejects.toThrow("Automatic TetraVox setup requires");
      expect(network).not.toHaveBeenCalled();
    } finally { Object.defineProperty(process, "platform", original); }
  });

  it.each(["linux", "win32"] as const)("reuses an identified %s installation despite unavailable automatic setup", async (platform) => {
    const userData = await temporary();
    const directory = await temporary();
    const executable = join(directory, platform === "win32" ? "Tetravox.exe" : "tetravox");
    await writeFile(executable, "existing application");
    await chmod(executable, 0o755);
    await mkdir(join(directory, "resources/app.asar"), { recursive: true });
    await writeFile(join(directory, "resources/app.asar/package.json"), JSON.stringify({ name: "@tetravox/app", version: "1.0.0" }));
    const original = Object.getOwnPropertyDescriptor(process, "platform")!;
    Object.defineProperty(process, "platform", { value: platform });
    setConfiguredViewerPathProvider(() => executable);
    const network = vi.fn(() => { throw new Error("Must reuse application"); });
    vi.stubGlobal("fetch", network);
    try {
      expect(await installNativeViewer(userData)).toMatchObject({ installed: true, source: "configured", version: "1.0.0", error: undefined });
      expect(network).not.toHaveBeenCalled();
      expect(await readFile(executable, "utf8")).toBe("existing application");
    } finally {
      setConfiguredViewerPathProvider(() => undefined);
      Object.defineProperty(process, "platform", original);
    }
  });

  it.runIf(process.platform === "darwin")("coalesces first setup, verifies latest archive and requires application identity", async () => {
    const source = await temporary();
    const paths = await managed(source, "1.1.0");
    if (!paths) throw new Error("Fixture needs Mac layout");
    const archive = join(source, "fixture.zip");
    await viewerCommand("/usr/bin/ditto", ["-c", "-k", "--keepParent", join(paths.directory, "Tetravox.app"), archive]);
    const bytes = await readFile(archive);
    const asset = nativeViewerPaths(source, process.platform, process.arch, "1.1.0").release!.asset;
    const network = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/releases/latest")) return new Response(JSON.stringify({ tag_name: "v1.1.0", assets: [{ name: asset }] }));
      if (url.endsWith("latest-mac.yml")) return new Response(`version: 1.1.0\nfiles:\n  - url: ${asset}\n    sha512: ${createHash("sha512").update(bytes).digest("base64")}\n`);
      return new Response(bytes);
    });
    vi.stubGlobal("fetch", network);
    const userData = await temporary();
    const results = await Promise.all([installNativeViewer(userData), installNativeViewer(userData)]);
    expect(results).toMatchObject([{ installed: true, installing: false, version: "1.1.0" }, { installed: true, installing: false, version: "1.1.0" }]);
    expect(network.mock.calls.filter(([url]) => String(url).endsWith(".zip"))).toHaveLength(1);
    // A completed download is insufficient if the app identity has disappeared.
    await rm(join(results[0]!.directory, "Tetravox.app/Contents/Info.plist"));
    expect(await managedInstalls(userData)).toEqual([]);
  });

  it.runIf(process.platform === "darwin")("does not replace an installation that appears while downloading", async () => {
    const source = await temporary();
    const paths = await managed(source, "1.1.0");
    if (!paths) throw new Error("Fixture needs Mac layout");
    const archive = join(source, "fixture.zip");
    await viewerCommand("/usr/bin/ditto", ["-c", "-k", "--keepParent", join(paths.directory, "Tetravox.app"), archive]);
    const bytes = await readFile(archive);
    const userData = await temporary();
    const asset = nativeViewerPaths(source, process.platform, process.arch, "1.1.0").release!.asset;
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/releases/latest")) return new Response(JSON.stringify({ tag_name: "v1.1.0", assets: [{ name: asset }] }));
      if (url.endsWith("latest-mac.yml")) return new Response(`version: 1.1.0\nfiles:\n  - url: ${asset}\n    sha512: ${createHash("sha512").update(bytes).digest("base64")}\n`);
      await managed(userData, "2.0.0");
      return new Response(bytes);
    }));
    const result = await installNativeViewer(userData);
    expect(result).toMatchObject({ installed: true, installing: false, version: "2.0.0" });
    expect(await readFile(result.executable!, "utf8")).toBe("binary-2.0.0");
  });

  it.runIf(process.platform === "darwin").each(["mismatched version", "incomplete destination"])("preserves existing files when setup encounters %s", async (failure) => {
    const source = await temporary();
    const paths = await managed(source, failure === "mismatched version" ? "2.0.0" : "1.1.0");
    if (!paths) throw new Error("Fixture needs Mac layout");
    const archive = join(source, "fixture.zip");
    await viewerCommand("/usr/bin/ditto", ["-c", "-k", "--keepParent", join(paths.directory, "Tetravox.app"), archive]);
    const bytes = await readFile(archive);
    const userData = await temporary();
    const target = nativeViewerPaths(userData, process.platform, process.arch, "1.1.0");
    await mkdir(target.directory, { recursive: true });
    await writeFile(join(target.directory, "user-file"), "preserve existing contents");
    await mkdir(`${target.directory}.previous`);
    await writeFile(join(`${target.directory}.previous`, "recovery"), "preserve crash recovery");
    const asset = target.release!.asset;
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/releases/latest")) return new Response(JSON.stringify({ tag_name: "v1.1.0", assets: [{ name: asset }] }));
      if (url.endsWith("latest-mac.yml")) return new Response(`version: 1.1.0\nfiles:\n  - url: ${asset}\n    sha512: ${createHash("sha512").update(bytes).digest("base64")}\n`);
      return new Response(bytes);
    }));
    await expect(installNativeViewer(userData)).rejects.toThrow(failure === "mismatched version" ? "archive identifies version" : "incomplete installation");
    expect(await readFile(join(target.directory, "user-file"), "utf8")).toBe("preserve existing contents");
    expect(await readFile(join(`${target.directory}.previous`, "recovery"), "utf8")).toBe("preserve crash recovery");
    expect(await managedInstalls(userData)).toEqual([]);
  });

  it.runIf(process.platform === "darwin")("fails first setup when latest release has no verification feed", async () => {
    const userData = await temporary();
    const asset = nativeViewerPaths(userData, process.platform, process.arch, "1.1.0").release!.asset;
    const network = vi.fn(async (input: string | URL | Request) => String(input).endsWith("/releases/latest")
      ? new Response(JSON.stringify({ tag_name: "v1.1.0", assets: [{ name: asset }] }))
      : new Response(null, { status: 404 }));
    vi.stubGlobal("fetch", network);
    await expect(installNativeViewer(userData)).rejects.toThrow("no update feed");
    expect(await managedInstalls(userData)).toEqual([]);
    expect(network.mock.calls.some(([url]) => String(url).endsWith(".zip"))).toBe(false);
  });

  it("discovers historical managed directories after TetraVox updates itself", async () => {
    const userData = await temporary();
    const paths = await managed(userData, "2.0.0");
    if (!paths) throw new Error("Fixture needs supported layout");
    const historical = join(userData, "runtimes", `tetravox-0.4.0-${process.platform}-${process.arch}`);
    await rename(paths.directory, historical);
    expect(await managedInstalls(userData)).toMatchObject([{ version: "2.0.0", directory: historical }]);
  });

  it("reuses a self-updated bootstrap without network or replacement", async () => {
    const userData = await temporary();
    const paths = await managed(userData, "1.2.0");
    if (!paths?.executable) throw new Error("Fixture needs supported layout");
    await writeFile(paths.executable, "self-updated bytes");
    const network = vi.fn(() => { throw new Error("Must not check updates"); });
    vi.stubGlobal("fetch", network);
    expect(await installNativeViewer(userData)).toMatchObject({ installed: true, version: "1.2.0" });
    expect(network).not.toHaveBeenCalled();
    expect(await readFile(paths.executable, "utf8")).toBe("self-updated bytes");
    expect(nativeViewerPaths(userData, process.platform, process.arch, "9.0.0").directory).toBe(paths.directory);
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

  it("reports a release lookup that names no version", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ tag_name: "nightly" }), { status: 200 }));
    await expect(latestViewerRelease(fetch as unknown as typeof globalThis.fetch)).rejects.toThrow("did not name a version");
    const failed = vi.fn(async () => new Response(null, { status: 403 }));
    await expect(latestViewerRelease(failed as unknown as typeof globalThis.fetch)).rejects.toThrow("403");
  });
});

/** Native discovery and verified first-use bootstrap. TetraVox owns all subsequent updates. */
import { supportsNativeSceneApi } from "./nativeSceneBridge";
import { createHash } from "node:crypto";
import { execFile, spawn } from "node:child_process";
import { closeSync, createWriteStream, openSync } from "node:fs";
import { access, chmod, mkdir, mkdtemp, readdir, readFile, realpath, rename, rm, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { promisify } from "node:util";
import { basename, delimiter, dirname, isAbsolute, join, relative, sep } from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { TitNativeTetravoxStatus, TitNativeTetravoxProgress } from "../shared/tit-bridge";

export const TETRAVOX_REPO = "idossha/Tetravox";

interface PlatformRelease {
  /** `${version}` is substituted with the release version. */
  asset: string;
  /** Path of the executable inside the extracted archive. */
  executable: string;
  /** electron-builder update feed published alongside the release. */
  feed: string;
}

const RELEASES: Record<string, PlatformRelease> = {
  "darwin-arm64": { asset: "Tetravox-${version}-mac-arm64.zip", feed: "latest-mac.yml", executable: "Tetravox.app/Contents/MacOS/Tetravox" },
  "darwin-x64": { asset: "Tetravox-${version}-mac-x64.zip", feed: "latest-mac.yml", executable: "Tetravox.app/Contents/MacOS/Tetravox" },
  "linux-x64": { asset: "Tetravox-${version}-linux-x64.tar.gz", feed: "latest-linux.yml", executable: "tetravox" },
};

export function nativeViewerPaths(userData: string, platform = process.platform, arch: string = process.arch, version = "") {
  const entry = RELEASES[`${platform}-${arch}`];
  const release = entry ? { ...entry, asset: entry.asset.replace("${version}", version) } : undefined;
  const directory = join(userData, "runtimes", `tetravox-${platform}-${arch}`);
  return { directory, release, version, executable: release ? join(directory, release.executable) : undefined };
}

const execFileAsync = promisify(execFile);

export function compatibleViewerVersion(version: string): boolean {
  const parts = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  return !!parts && (Number(parts[1]) > 0 || Number(parts[2]) >= 4);
}

/** Newest-first comparison of two `x.y.z` versions. */
export function compareViewerVersions(a: string, b: string): number {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let index = 0; index < 3; index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference) return difference;
  }
  return 0;
}

export type ViewerSourceKind = "configured" | "managed" | "system" | "path";
export interface SystemViewer { executable: string; directory: string; version: string }

export function systemViewerCandidates(platform = process.platform, home = homedir(), env = process.env): string[] {
  if (platform === "darwin") return [join(home, "Applications/Tetravox.app"), "/Applications/Tetravox.app"];
  if (platform === "win32") return [env.LOCALAPPDATA && join(env.LOCALAPPDATA, "Programs/Tetravox/Tetravox.exe"), env.ProgramFiles && join(env.ProgramFiles, "Tetravox/Tetravox.exe"), env["ProgramFiles(x86)"] && join(env["ProgramFiles(x86)"], "Tetravox/Tetravox.exe")].filter((path): path is string => !!path);
  return [join(home, ".local/bin/tetravox"), "/usr/local/bin/tetravox", "/usr/bin/tetravox", "/opt/Tetravox/tetravox", "/opt/tetravox/tetravox"];
}

/** Executables named like TetraVox on the user's PATH; identity is still checked before use. */
export function pathViewerCandidates(platform = process.platform, env = process.env): string[] {
  const name = platform === "win32" ? "Tetravox.exe" : "tetravox";
  return (env.PATH ?? "").split(platform === "win32" ? ";" : delimiter).filter((entry) => entry.trim()).map((entry) => join(entry, name));
}

/** Only conventional installed locations are considered; never execute a candidate to identify it. */
export async function findSystemViewer(candidates = systemViewerCandidates(), platform = process.platform): Promise<SystemViewer | undefined> {
  for (const candidate of candidates) {
    try {
      const executable = await realpath(platform === "darwin" && candidate.endsWith(".app") ? join(candidate, "Contents/MacOS/Tetravox") : candidate);
      const bundle = platform === "darwin" ? executable.replace(/\/Contents\/MacOS\/[^/]+$/, "") : undefined;
      if (platform === "darwin" && !bundle?.endsWith(".app")) continue;
      if (!(await stat(executable)).isFile()) continue;
      await access(executable, platform === "win32" ? 0 : 1);
      let version = "system";
      if (platform === "darwin") {
        const { stdout } = await execFileAsync("/usr/bin/plutil", ["-convert", "json", "-o", "-", join(bundle!, "Contents/Info.plist")], { timeout: 3000, maxBuffer: 65536 });
        const info = JSON.parse(stdout) as { CFBundleIdentifier?: string; CFBundleShortVersionString?: string };
        version = info.CFBundleShortVersionString ?? "";
        if (info.CFBundleIdentifier !== "dev.tetravox.viewer" || !compatibleViewerVersion(version)) continue;
      } else {
        // Electron resolves app.asar transparently; no foreign executable is run for discovery.
        const metadata = JSON.parse(await readFile(join(dirname(executable), "resources/app.asar/package.json"), "utf8")) as { name?: string; version?: string };
        version = metadata.version ?? "";
        if (metadata.name !== "@tetravox/app" || !compatibleViewerVersion(version)) continue;
      }
      return { executable, directory: bundle ?? dirname(executable), version };
    } catch { /* Uninstalled, incompatible or unreadable candidates do not shadow managed setup. */ }
  }
  return undefined;
}

export interface ViewerCandidates {
  configured?: SystemViewer;
  managed?: SystemViewer;
  system?: SystemViewer;
  path?: SystemViewer;
}

/**
 * Prefer the user choice and existing native installations before the TI bootstrapped copy.
 */
export function selectViewer(candidates: ViewerCandidates): (SystemViewer & { source: ViewerSourceKind }) | undefined {
  for (const source of ["configured", "system", "path", "managed"] as const) {
    const candidate = candidates[source];
    if (candidate) return { ...candidate, source };
  }
  return undefined;
}

/** Process inspection is conservative: an open app may contain unsaved work. */
export function viewerProcessMatches(output: string, executable: string, platform = process.platform): boolean {
  if (platform === "win32") {
    try {
      const entries: unknown = JSON.parse(output || "[]");
      const processes = Array.isArray(entries) ? entries : [entries];
      if (processes.some((entry) => typeof entry !== "object" || entry === null || !("ExecutablePath" in entry) || typeof entry.ExecutablePath !== "string" || !entry.ExecutablePath)) throw new Error("Process path unavailable");
      return processes.some((entry: { ExecutablePath: string }) =>
        entry.ExecutablePath.toLowerCase() === executable.toLowerCase() || /(?:^|[\\/])tetravox\.exe$/i.test(entry.ExecutablePath));
    } catch { throw new Error("Could not check whether TetraVox is already running."); }
  }
  // Different installations can share Electron's default profile and single-instance
  // lock. Probe all viewer binaries, not just the selected one, so a handoff to an
  // already-running copy cannot bypass replacement consent. False positives are safe.
  return output.split("\n").some((line) => {
    const command = line.trim();
    return command === executable || command.startsWith(`${executable} `) ||
      /^(?:\/.*\/)?tetravox(?:\s|$)/i.test(command);
  });
}

async function viewerProcessList(): Promise<string> {
  const { stdout } = process.platform === "win32"
    ? await execFileAsync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='Tetravox.exe'\" | Select-Object ExecutablePath | ConvertTo-Json -Compress"], { timeout: 5000, maxBuffer: 1024 * 1024, windowsHide: true })
    : await execFileAsync("/bin/ps", ["-ax", "-o", "args="], { timeout: 5000, maxBuffer: 4 * 1024 * 1024 });
  return stdout;
}

export async function nativeViewerRunning(userData: string, selected?: TitNativeTetravoxStatus): Promise<boolean> {
  const status = selected ?? await nativeViewerStatus(userData);
  if (!status.installed || !status.executable) return false;
  return viewerProcessMatches(await viewerProcessList(), status.executable);
}

/* ------------------------------------------------------------------ user configuration */

let configuredPathProvider: () => string | undefined = () => undefined;
/** Injected by the main process so this module never imports Electron (and stays unit-testable). */
export function setConfiguredViewerPathProvider(provider: () => string | undefined): void {
  configuredPathProvider = provider;
}

/** Validate a path the user picked. Accepts a `.app` bundle, a bundle executable, or a binary. */
export async function identifyViewerPath(path: string, platform = process.platform): Promise<SystemViewer> {
  let candidate = path;
  if (platform === "darwin" && !candidate.endsWith(".app")) {
    const bundle = candidate.replace(/\/Contents\/MacOS\/[^/]+$/, "");
    if (bundle.endsWith(".app")) candidate = bundle;
  }
  const viewer = await findSystemViewer([candidate], platform);
  if (!viewer) throw new Error("That is not a compatible TetraVox application (0.4 or newer is required).");
  return viewer;
}

/* --------------------------------------------------------------------- managed installs */

/** Discover stable and historical TI installs by application identity, allowing native self-updates. */
export async function managedInstalls(userData: string, platform = process.platform, arch: string = process.arch): Promise<SystemViewer[]> {
  const root = join(userData, "runtimes");
  let entries: string[];
  try { entries = await readdir(root); } catch { return []; }
  const stable = `tetravox-${platform}-${arch}`;
  const suffix = `-${platform}-${arch}`;
  const found: SystemViewer[] = [];
  for (const entry of entries.sort((a, b) => Number(b === stable) - Number(a === stable))) {
    if (entry !== stable && (!entry.startsWith("tetravox-") || !entry.endsWith(suffix))) continue;
    const directory = join(root, entry);
    const release = RELEASES[`${platform}-${arch}`];
    if (!release) continue;
    const candidate = platform === "darwin" ? join(directory, "Tetravox.app") : join(directory, release.executable);
    const viewer = await findSystemViewer([candidate], platform);
    if (viewer) found.push({ ...viewer, directory });
  }
  return found;
}

/* ------------------------------------------------------------------------- release feed */

export interface ReleaseFeed { version: string; files: { url: string; sha512: string }[] }

/**
 * Minimal reader for electron-builder's `latest-*.yml`. Deliberately not a general YAML parser:
 * only the two fields that gate an install are read, and anything unexpected yields no checksum.
 */
export function parseReleaseFeed(text: string): ReleaseFeed | undefined {
  const version = /^version:\s*'?"?([0-9]+\.[0-9]+\.[0-9]+)'?"?\s*$/m.exec(text)?.[1];
  if (!version) return undefined;
  const files: { url: string; sha512: string }[] = [];
  const block = /^\s*-\s+url:\s*(\S+)\s*\n\s+sha512:\s*(\S+)\s*$/gm;
  for (let match = block.exec(text); match; match = block.exec(text)) files.push({ url: match[1]!, sha512: match[2]! });
  return { version, files };
}

/** The base64 SHA512 the release publishes for one asset, or undefined when it publishes none. */
export function feedChecksum(feed: ReleaseFeed | undefined, asset: string): string | undefined {
  return feed?.files.find((file) => basename(file.url) === asset)?.sha512;
}

export interface ReleaseLookup { version: string; assets: string[] }

/** Ask GitHub for the newest published TetraVox release. Never called from tests unmocked. */
export async function latestViewerRelease(fetchImpl: typeof fetch = fetch): Promise<ReleaseLookup> {
  const response = await fetchImpl(`https://api.github.com/repos/${TETRAVOX_REPO}/releases/latest`, {
    headers: { Accept: "application/vnd.github+json", "User-Agent": "TI-Toolbox" },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error(`Could not check for TetraVox updates (HTTP ${response.status}).`);
  const body = await response.json() as { tag_name?: string; assets?: { name?: string }[] };
  const version = /^v?([0-9]+\.[0-9]+\.[0-9]+)$/.exec(body.tag_name ?? "")?.[1];
  if (!version) throw new Error("The TetraVox release feed did not name a version.");
  return { version, assets: (body.assets ?? []).map((asset) => asset.name ?? "").filter(Boolean) };
}

function assetUrl(version: string, asset: string): string {
  return `https://github.com/${TETRAVOX_REPO}/releases/download/v${version}/${asset}`;
}

async function releaseChecksum(version: string, release: PlatformRelease, fetchImpl: typeof fetch = fetch): Promise<{ algorithm: "sha256" | "sha512"; value: string }> {
  const response = await fetchImpl(assetUrl(version, release.feed), { signal: AbortSignal.timeout(20_000) });
  if (!response.ok) throw new Error(`TetraVox ${version} publishes no update feed for this platform.`);
  const feed = parseReleaseFeed(await response.text());
  const sha512 = feed?.version === version ? feedChecksum(feed, release.asset) : undefined;
  if (!sha512) throw new Error(`TetraVox ${version} publishes no checksum for ${release.asset}; nothing was installed.`);
  return { algorithm: "sha512", value: sha512 };
}

/* ---------------------------------------------------------------------------- progress */

let progressListener: ((progress: TitNativeTetravoxProgress) => void) | undefined;
export function setViewerProgressListener(listener?: (progress: TitNativeTetravoxProgress) => void): void {
  progressListener = listener;
}
function report(progress: TitNativeTetravoxProgress): void {
  try { progressListener?.(progress); } catch { /* Progress reporting must never fail an install. */ }
}

/* ------------------------------------------------------------------------------ status */

let installing: Promise<TitNativeTetravoxStatus> | undefined;
let lastError: string | undefined;

export async function nativeViewerStatus(userData: string): Promise<TitNativeTetravoxStatus> {
  const configuredPath = configuredPathProvider();
  const [configured, managed, system, onPath] = await Promise.all([
    configuredPath ? identifyViewerPath(configuredPath).catch(() => undefined) : Promise.resolve(undefined),
    managedInstalls(userData).then((installs) => installs[0]),
    findSystemViewer(),
    findSystemViewer(pathViewerCandidates()),
  ]);
  const selected = selectViewer({ configured, managed, system, path: onPath });
  const { directory, release, executable } = nativeViewerPaths(userData);
  const base: TitNativeTetravoxStatus = {
    supported: !!release && process.platform === "darwin",
    installed: false,
    installing: !!installing,
    version: "",
    directory,
    executable,
    configuredPath,
    configuredPathValid: configuredPath ? !!configured : undefined,
    error: lastError ?? (process.platform === "linux" ? "Automatic TetraVox setup requires a Linux package that supports native updates without adding FUSE. Install TetraVox independently or choose an existing application." : !release ? "Automatic TetraVox setup requires an official updater-compatible package for this platform. Choose an existing TetraVox installation." : undefined),
  };
  if (!selected) return base;
  lastError = undefined;
  return {
    ...base,
    source: selected.source,
    executable: selected.executable,
    directory: selected.directory,
    version: selected.version,
    installed: true,
    supportsSceneSave: await supportsNativeSceneApi(selected.executable),
    error: undefined,
  };
}

/* ---------------------------------------------------------------------------- download */

export async function downloadViewer(url: string, target: string, expected: string | { algorithm: "sha256" | "sha512"; value: string }): Promise<void> {
  const want = typeof expected === "string" ? { algorithm: "sha256" as const, value: expected } : expected;
  const response = await fetch(url, { signal: AbortSignal.timeout(300_000) });
  if (!response.ok || !response.body) throw new Error(`TetraVox download failed (HTTP ${response.status}).`);
  const total = Number(response.headers.get("content-length")) || undefined;
  const hash = createHash(want.algorithm);
  let size = 0;
  let announced = 0;
  const verify = new Transform({ transform(chunk: Buffer, _encoding, callback) {
    size += chunk.length;
    if (size > 500 * 1024 * 1024) { callback(new Error("TetraVox download exceeds the supported package size.")); return; }
    hash.update(chunk);
    if (size - announced >= 1024 * 1024) { announced = size; report({ phase: "download", received: size, total }); }
    callback(null, chunk);
  } });
  report({ phase: "download", received: 0, total });
  await pipeline(Readable.fromWeb(response.body as never), verify, createWriteStream(target, { mode: 0o600, flags: "wx" }));
  const digest = want.algorithm === "sha512" ? hash.digest("base64") : hash.digest("hex");
  if (digest !== want.value) throw new Error("TetraVox download checksum mismatch. Nothing was installed.");
}

export function viewerCommand(command: string, args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    let output = "";
    const collect = (chunk: Buffer) => { output = (output + chunk.toString()).slice(-2000); };
    child.stdout.on("data", collect); child.stderr.on("data", collect);
    const timer = setTimeout(() => { child.kill(); reject(new Error("TetraVox installation timed out.")); }, 300_000);
    child.once("error", (error) => { clearTimeout(timer); reject(error); });
    child.once("close", (code) => { clearTimeout(timer); if (code === 0) resolve(); else reject(new Error(`TetraVox installation failed (${code}): ${output}`)); });
  });
}

export function installNativeViewer(userData: string): Promise<TitNativeTetravoxStatus> {
  if (installing) return installing;
  lastError = undefined;
  installing = install(userData).catch((error: unknown) => { lastError = error instanceof Error ? error.message : String(error); throw error; }).finally(() => { installing = undefined; report({ phase: "idle" }); }).then((status) => ({ ...status, installing: false }));
  return installing;
}

async function install(userData: string): Promise<TitNativeTetravoxStatus> {
  const existing = await nativeViewerStatus(userData);
  if (existing.installed) return existing;
  if (!existing.supported) throw new Error(existing.error ?? "This platform has no supported native TetraVox release.");
  const { version, assets } = await latestViewerRelease();
  if (!compatibleViewerVersion(version)) throw new Error(`TetraVox ${version} is not compatible with this TI-Toolbox release.`);
  const paths = nativeViewerPaths(userData, process.platform, process.arch, version);
  const { release, directory } = paths;

  if (!release || !paths.executable) throw new Error("This platform has no supported native TetraVox release.");
  if (!assets.includes(release.asset)) throw new Error(`TetraVox ${version} has no package for this platform.`);
  const expected = await releaseChecksum(version, release);
  await mkdir(dirname(directory), { recursive: true, mode: 0o700 });
  const staging = await mkdtemp(join(dirname(directory), ".tetravox-install-"));
  try {
    const archive = join(staging, release.asset);
    await downloadViewer(assetUrl(version, release.asset), archive, expected);
    const extracted = join(staging, "app");
    await mkdir(extracted, { mode: 0o700 });
    report({ phase: "install" });
    {
      if (process.platform === "darwin") await viewerCommand("/usr/bin/ditto", ["-x", "-k", archive, extracted]);
      else await viewerCommand("tar", ["-xzf", archive, "-C", extracted, "--strip-components=1"]);
      const identified = await identifyViewerPath(process.platform === "darwin" ? join(extracted, "Tetravox.app") : join(extracted, release.executable));
      if (identified.version !== version) throw new Error(`TetraVox archive identifies version ${identified.version}, but the verified release is ${version}. Nothing was installed.`);
      await chmod(join(extracted, release.executable), 0o755);
      await writeFile(join(extracted, "ready.json"), JSON.stringify({ version, archiveHash: expected.value }), { mode: 0o600 });
      // Another launch or the user may have installed TetraVox during the download.
      const discovered = await nativeViewerStatus(userData);
      if (discovered.installed) return discovered;
      // A directory rename cannot replace a nonempty installation. Never move a
      // competing process's winner aside or delete a historical recovery backup.
      try { await rename(extracted, directory); } catch (error) {
        if (!["EEXIST", "ENOTEMPTY", "ENOTDIR", "EISDIR"].includes((error as NodeJS.ErrnoException).code ?? "")) throw error;
        const winner = await nativeViewerStatus(userData);
        if (winner.installed) return winner;
        throw new Error(`TetraVox setup found an incomplete installation at ${directory}. Move that directory aside and retry; its contents were preserved.`, { cause: error });
      }
    }
    return nativeViewerStatus(userData);
  } finally { await rm(staging, { recursive: true, force: true }); }
}

/** Resolve symlinks as well as lexical traversal before handing a project scene to the app. */
export async function checkViewerScene(path: string, projectRoot: string): Promise<string> {
  if (!path.toLowerCase().endsWith(".tetravox.json")) throw new Error("TetraVox requires a .tetravox.json scene.");
  const [root, scene] = await Promise.all([realpath(projectRoot), realpath(path)]);
  const rel = relative(root, scene);
  if (!rel || isAbsolute(rel) || rel === ".." || rel.startsWith(`..${sep}`)) throw new Error("Viewer scene is outside the active project.");
  if (!(await stat(scene)).isFile()) throw new Error("Viewer scene is not a file.");
  return scene;
}

export async function openNativeViewer(userData: string, scene: string, selected?: TitNativeTetravoxStatus, requestPath?: string): Promise<void> {
  const status = selected ?? await nativeViewerStatus(userData);
  if (!status.installed || !status.executable) throw new Error("Install native TetraVox in Settings → Viewer first.");
  const { executable } = status;
  // Existing managed sessions hold Electron's lock in this legacy profile. Keep
  // routing to it when it exists; changing profiles would open a second instance.
  const legacyProfile = join(userData, "tetravox-profile");
  const useLegacyProfile = status.source === "managed" && await stat(legacyProfile).then((entry) => entry.isDirectory(), () => false);
  const env: NodeJS.ProcessEnv = { ...process.env };
  delete env.TETRAVOX_MANAGED_BY;
  delete env.ELECTRON_RUN_AS_NODE;
  const bundle = process.platform === "darwin" ? /^(.*\.app)\/Contents\/MacOS\/[^/]+$/.exec(executable)?.[1] : undefined;
  if (bundle && !requestPath) {
    const profileArgs = useLegacyProfile ? ["--args", `--user-data-dir=${legacyProfile}`] : [];
    // LaunchServices sends open-file, which existing viewers queue even without a
    // window. Direct executable launches send second-instance and lose that scene.
    await execFileAsync("/usr/bin/open", ["-a", bundle, ...(scene ? [scene] : []), ...profileArgs], { env, timeout: 15_000, maxBuffer: 65536 });
    // Explicit reopen requests activate after open-file queued the scene. The
    // existing activate handler recreates a Dock-only app's guarded window.
    // Never send the scene twice, or use -n/-F (new instance / discard restoration).
    if (scene) await execFileAsync("/usr/bin/open", ["-a", bundle, ...profileArgs], { env, timeout: 15_000, maxBuffer: 65536 });
    return; // LaunchServices accepted the request; scene loading is not acknowledged.
  }
  await new Promise<void>((resolve, reject) => {
    const logPath = join(userData, "tetravox-launch.log");
    const descriptor = openSync(logPath, "w", 0o600);
    const child = spawn(executable!, [...(useLegacyProfile ? [`--user-data-dir=${legacyProfile}`] : []), ...(requestPath ? [`--scene-request=${requestPath}`] : scene ? [scene] : [])], { env, detached: true, stdio: ["ignore", "ignore", descriptor], windowsHide: false });
    closeSync(descriptor);
    const timer = setTimeout(() => { child.unref(); resolve(); }, 1500);
    child.once("error", (error) => { clearTimeout(timer); reject(error); });
    child.once("exit", (code, signal) => {
      clearTimeout(timer);
      if (code === 0) resolve(); // Process success is only a launch receipt; no scene-load acknowledgment.
      else void readFile(logPath, "utf8").then(
        (output) => reject(new Error(`TetraVox could not start (${signal ?? code}): ${output.slice(-2000)}`)),
        () => reject(new Error(`TetraVox could not start (${signal ?? code}).`)),
      );
    });
  });
  if (bundle && requestPath) await execFileAsync("/usr/bin/open", ["-a", bundle], { env, timeout: 15_000, maxBuffer: 65536 });
}

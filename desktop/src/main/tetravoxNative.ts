/**
 * Native TetraVox resolution: a user-configured path, a managed download TI-Toolbox owns, a
 * conventional system installation, or one on PATH — in that order. Managed installs only ever
 * write bytes whose digest was published by the official release (pinned SHA256 for the baseline
 * version, the release's own electron-builder update feed for later ones), so a TetraVox update
 * never requires a TI-Toolbox release.
 */
import { createHash } from "node:crypto";
import { execFile, spawn } from "node:child_process";
import { closeSync, createReadStream, createWriteStream, openSync } from "node:fs";
import { access, chmod, mkdir, mkdtemp, readdir, readFile, realpath, rename, rm, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { promisify } from "node:util";
import { basename, delimiter, dirname, isAbsolute, join, relative, sep } from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { TitNativeTetravoxStatus, TitNativeTetravoxProgress } from "../shared/tit-bridge";

/** The baseline version whose bytes are pinned in this repository; later versions come from the feed. */
export const TETRAVOX_VERSION = "0.4.0";
export const TETRAVOX_REPO = "idossha/Tetravox";

interface PlatformRelease {
  /** `${version}` is substituted with the release version. */
  asset: string;
  /** Path of the executable inside the extracted archive. */
  executable: string;
  /** electron-builder update feed published alongside the release. */
  feed: string;
  /** SHA256 of the pinned baseline asset; other versions are verified against the feed. */
  sha256: string;
}

const RELEASES: Record<string, PlatformRelease> = {
  "darwin-arm64": { asset: "Tetravox-${version}-mac-arm64.zip", feed: "latest-mac.yml", executable: "Tetravox.app/Contents/MacOS/Tetravox", sha256: "19d1f8d304a6d5b632ad17197bf3edf5469921695f7969f35b52d39c537182aa" },
  "darwin-x64": { asset: "Tetravox-${version}-mac-x64.zip", feed: "latest-mac.yml", executable: "Tetravox.app/Contents/MacOS/Tetravox", sha256: "f7d1eb9d7ebfd12998c169e1893e03137ee8e407ef405eba4837cefb5693e5b0" },
  "linux-x64": { asset: "Tetravox-${version}-linux-x64.tar.gz", feed: "latest-linux.yml", executable: "tetravox", sha256: "0ca9ed64947d2a242cb3ba809c7d99ece10fa99e445b02c80122ced37f5e7306" },
};

export function nativeViewerPaths(userData: string, platform = process.platform, arch: string = process.arch, version: string = TETRAVOX_VERSION) {
  const entry = RELEASES[`${platform}-${arch}`];
  const release = entry ? { ...entry, asset: entry.asset.replace("${version}", version) } : undefined;
  const directory = join(userData, "runtimes", `tetravox-${version}-${platform}-${arch}`);
  return { directory, release, version, executable: release ? join(directory, release.executable) : undefined };
}

const execFileAsync = promisify(execFile);

export function compatibleViewerVersion(version: string): boolean {
  const parts = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  return !!parts && Number(parts[1]) === 0 && Number(parts[2]) >= 4;
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
  return (env.PATH ?? "").split(delimiter).filter((entry) => entry.trim()).map((entry) => join(entry, name));
}

/** Only conventional installed locations are considered; never execute a candidate to identify it. */
export async function findSystemViewer(candidates = systemViewerCandidates(), platform = process.platform): Promise<SystemViewer | undefined> {
  for (const candidate of candidates) {
    try {
      const executable = await realpath(platform === "darwin" ? join(candidate, "Contents/MacOS/Tetravox") : candidate);
      if (!(await stat(executable)).isFile()) continue;
      await access(executable, platform === "win32" ? 0 : 1);
      let version = "system";
      if (platform === "darwin") {
        const { stdout } = await execFileAsync("/usr/bin/plutil", ["-convert", "json", "-o", "-", join(candidate, "Contents/Info.plist")], { timeout: 3000, maxBuffer: 65536 });
        const info = JSON.parse(stdout) as { CFBundleIdentifier?: string; CFBundleShortVersionString?: string };
        version = info.CFBundleShortVersionString ?? "";
        if (info.CFBundleIdentifier !== "dev.tetravox.viewer" || !compatibleViewerVersion(version)) continue;
      } else {
        // Electron resolves app.asar transparently; no foreign executable is run for discovery.
        const metadata = JSON.parse(await readFile(join(dirname(executable), "resources/app.asar/package.json"), "utf8")) as { name?: string; version?: string };
        version = metadata.version ?? "";
        if (metadata.name !== "@tetravox/app" || !compatibleViewerVersion(version)) continue;
      }
      return { executable, directory: platform === "darwin" ? candidate : dirname(executable), version };
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
 * The single resolution rule. A path the user chose wins outright; then the copy TI-Toolbox
 * installed and can keep updated; then an installation the user maintains themselves.
 */
export function selectViewer(candidates: ViewerCandidates): (SystemViewer & { source: ViewerSourceKind }) | undefined {
  for (const source of ["configured", "managed", "system", "path"] as const) {
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
      return processes.some((entry: { ExecutablePath: string }) => entry.ExecutablePath.toLowerCase() === executable.toLowerCase());
    } catch { throw new Error("Could not check whether TetraVox is already running."); }
  }
  return output.split("\n").some((line) => line.trim() === executable || line.trim().startsWith(`${executable} `));
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

async function digestFile(path: string, algorithm: "sha256" | "sha512" = "sha256"): Promise<string> {
  const hash = createHash(algorithm);
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return algorithm === "sha512" ? hash.digest("base64") : hash.digest("hex");
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

/** Every managed install of this platform, newest first. */
export async function managedInstalls(userData: string, platform = process.platform, arch: string = process.arch): Promise<SystemViewer[]> {
  const root = join(userData, "runtimes");
  let entries: string[];
  try { entries = await readdir(root); } catch { return []; }
  const suffix = `-${platform}-${arch}`;
  const found: SystemViewer[] = [];
  for (const entry of entries) {
    if (!entry.startsWith("tetravox-") || !entry.endsWith(suffix)) continue;
    const version = entry.slice("tetravox-".length, entry.length - suffix.length);
    if (!compatibleViewerVersion(version)) continue;
    const paths = nativeViewerPaths(userData, platform, arch, version);
    if (!paths.executable || !paths.release) continue;
    try {
      const manifest = JSON.parse(await readFile(join(paths.directory, "ready.json"), "utf8")) as { archiveHash?: string; executableHash?: string };
      if (!manifest.executableHash || await digestFile(paths.executable) !== manifest.executableHash) continue;
      found.push({ executable: paths.executable, directory: paths.directory, version });
    } catch { /* A missing or incomplete installation is simply not ready. */ }
  }
  return found.sort((a, b) => compareViewerVersions(b.version, a.version));
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
  if (version === TETRAVOX_VERSION) return { algorithm: "sha256", value: release.sha256 };
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
let latestKnown: string | undefined;

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
    supported: !!release,
    installed: false,
    installing: !!installing,
    version: TETRAVOX_VERSION,
    directory,
    executable,
    configuredPath,
    configuredPathValid: configuredPath ? !!configured : undefined,
    latestVersion: latestKnown,
    error: lastError ?? (!release ? "No verified portable TetraVox package is configured for this platform. Windows managed setup requires an official ZIP release; its system installer is not used." : undefined),
  };
  if (!selected) return base;
  return {
    ...base,
    source: selected.source,
    executable: selected.executable,
    directory: selected.directory,
    version: selected.version,
    installed: true,
    // Only a copy TI-Toolbox owns can be replaced by TI-Toolbox.
    updateAvailable: selected.source === "managed" && !!latestKnown && compareViewerVersions(latestKnown, selected.version) > 0 ? latestKnown : undefined,
  };
}

/** Refresh the cached "newest published release" used by `updateAvailable`. */
export async function checkViewerUpdate(userData: string, fetchImpl: typeof fetch = fetch): Promise<TitNativeTetravoxStatus> {
  const { version, assets } = await latestViewerRelease(fetchImpl);
  const { release } = nativeViewerPaths(userData, process.platform, process.arch, version);
  latestKnown = release && (assets.length === 0 || assets.includes(release.asset)) && compatibleViewerVersion(version) ? version : undefined;
  return nativeViewerStatus(userData);
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

export function installNativeViewer(userData: string, version: string = TETRAVOX_VERSION): Promise<TitNativeTetravoxStatus> {
  if (installing) return installing;
  lastError = undefined;
  installing = install(userData, version).catch((error: unknown) => { lastError = error instanceof Error ? error.message : String(error); throw error; }).finally(() => { installing = undefined; report({ phase: "idle" }); });
  return installing.then(() => nativeViewerStatus(userData));
}

async function install(userData: string, version: string): Promise<TitNativeTetravoxStatus> {
  if (!compatibleViewerVersion(version)) throw new Error(`TetraVox ${version} is not compatible with this TI-Toolbox release.`);
  const paths = nativeViewerPaths(userData, process.platform, process.arch, version);
  const { release, directory } = paths;
  if ((await managedInstalls(userData)).some((entry) => entry.version === version)) return nativeViewerStatus(userData);
  if (!release || !paths.executable) throw new Error("This platform has no supported native TetraVox release.");
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
      await access(join(extracted, release.executable));
      // Only this version's incomplete managed installation is replaced. Other versions survive.
      const backup = `${directory}.previous`;
      await rm(backup, { recursive: true, force: true });
      try { await rename(directory, backup); } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
      try { await rename(extracted, directory); } catch (error) {
        try { await rename(backup, directory); } catch { /* No previous install existed. */ }
        throw error;
      }
      await rm(backup, { recursive: true, force: true });
      await chmod(paths.executable, 0o755);
    }
    const executableHash = await digestFile(paths.executable);
    await writeFile(join(directory, "ready.json"), JSON.stringify({ version, archiveHash: expected.value, executableHash }), { mode: 0o600 });
    return nativeViewerStatus(userData);
  } finally { await rm(staging, { recursive: true, force: true }); }
}

/** Remove managed installs older than the one now in use, so updates do not accumulate copies. */
export async function pruneManagedViewers(userData: string, keep: string): Promise<void> {
  for (const entry of await managedInstalls(userData)) {
    if (entry.version === keep) continue;
    await rm(entry.directory, { recursive: true, force: true }).catch(() => undefined);
  }
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

export async function openNativeViewer(userData: string, scene: string, selected?: TitNativeTetravoxStatus): Promise<void> {
  const status = selected ?? await nativeViewerStatus(userData);
  if (!status.installed || !status.executable) throw new Error("Install native TetraVox in Settings → Viewer first.");
  const { executable } = status;
  await new Promise<void>((resolve, reject) => {
    const env: NodeJS.ProcessEnv = { ...process.env };
    if (status.source === "managed") env.TETRAVOX_MANAGED_BY = "TI-Toolbox";
    else delete env.TETRAVOX_MANAGED_BY;
    delete env.ELECTRON_RUN_AS_NODE;
    const logPath = join(userData, "tetravox-launch.log");
    const descriptor = openSync(logPath, "w", 0o600);
    const child = spawn(executable!, [...(status.source === "managed" ? [`--user-data-dir=${join(userData, "tetravox-profile")}`] : []), ...(scene ? [scene] : [])], { env, detached: true, stdio: ["ignore", "ignore", descriptor], windowsHide: false });
    closeSync(descriptor);
    const timer = setTimeout(() => { child.unref(); resolve(); }, 1500);
    child.once("error", (error) => { clearTimeout(timer); reject(error); });
    child.once("exit", (code, signal) => {
      clearTimeout(timer);
      if (code === 0) resolve(); // The existing application accepted a second-instance handoff.
      else void readFile(logPath, "utf8").then(
        (output) => reject(new Error(`TetraVox could not start (${signal ?? code}): ${output.slice(-2000)}`)),
        () => reject(new Error(`TetraVox could not start (${signal ?? code}).`)),
      );
    });
  });
}

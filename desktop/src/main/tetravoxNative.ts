/**
 * TI-Toolbox's own TetraVox.
 *
 * One rule: the viewer TI launches is the copy TI installed under its user-data directory, on every
 * platform. Nothing on the machine is consulted — not a copy in /Applications or Program Files, not
 * one on PATH, not a path the user picked — because every one of those was a way for the wrong
 * TetraVox to open a scene (decision 2026-09-22). Setup downloads the official release package for
 * this platform, verifies it against the SHA-256 digest GitHub publishes for that asset, unpacks it
 * into a private staging directory and renames it into place. "Update" does the same into a fresh
 * directory and swaps. TetraVox's own updater is told it is managed (`TETRAVOX_MANAGED_BY`).
 */
import { supportsNativeSceneApi } from "./nativeSceneBridge";
import { createHash } from "node:crypto";
import { execFile, spawn } from "node:child_process";
import { closeSync, createWriteStream, openSync } from "node:fs";
import * as nodeFs from "node:fs/promises";
import { createRequire } from "node:module";
import { promisify } from "node:util";
import { dirname, isAbsolute, join, relative, sep } from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { TitNativeTetravoxStatus, TitNativeTetravoxProgress } from "../shared/tit-bridge";

/**
 * Plain file operations. Electron patches `fs` so that every `*.asar` looks like a directory and
 * keeps each archive it touches open; on Windows that made the freshly unpacked viewer impossible
 * to rename into place or delete (`EBUSY … app.asar`, measured 2026-09-22). `original-fs` is the
 * unpatched module Electron ships; under plain Node (tests) the ordinary one is the same thing.
 */
const fs: typeof nodeFs = (() => {
  try { return (createRequire(import.meta.url)("original-fs") as { promises: typeof nodeFs }).promises; } catch { return nodeFs; }
})();
const { access, chmod, mkdir, mkdtemp, readdir, readFile, realpath, rename, rm, stat, writeFile } = fs;

export const TETRAVOX_REPO = "idossha/Tetravox";
/** Value TetraVox reads to leave updates to whoever installed it. */
export const MANAGED_BY = "ti-toolbox";

interface PlatformRelease {
  /** `${version}` is substituted with the release version. */
  asset: string;
  /** Path of the executable inside the unpacked archive. */
  executable: string;
  /** Leading path components to drop when unpacking (the Linux tarball wraps everything in one directory). */
  strip: number;
}

/**
 * The official release packages TI installs. All three are plain archives of the unpacked
 * application: the macOS zips hold `Tetravox.app`, the Windows zip is the `win-unpacked` tree
 * with `Tetravox.exe` at its root, the Linux tarball is the unpacked tree inside one directory.
 * Verified against v0.6.1 on 2026-09-22.
 */
const RELEASES: Record<string, PlatformRelease> = {
  "darwin-arm64": { asset: "Tetravox-${version}-mac-arm64.zip", executable: "Tetravox.app/Contents/MacOS/Tetravox", strip: 0 },
  "darwin-x64": { asset: "Tetravox-${version}-mac-x64.zip", executable: "Tetravox.app/Contents/MacOS/Tetravox", strip: 0 },
  "linux-x64": { asset: "Tetravox-${version}-linux-x64.tar.gz", executable: "tetravox", strip: 1 },
  "win32-x64": { asset: "Tetravox-${version}-win-x64.zip", executable: "Tetravox.exe", strip: 0 },
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

export interface InstalledViewer { executable: string; directory: string; version: string }

/**
 * Identify a TetraVox at one of the given locations by reading its application metadata; the
 * candidate is never executed. Used for the managed directory and for the archive just unpacked.
 */
export async function identifyViewer(candidates: string[], platform = process.platform): Promise<InstalledViewer | undefined> {
  for (const candidate of candidates) {
    try {
      const executable = await realpath(platform === "darwin" && candidate.endsWith(".app") ? join(candidate, "Contents/MacOS/Tetravox") : candidate);
      const bundle = platform === "darwin" ? executable.replace(/\/Contents\/MacOS\/[^/]+$/, "") : undefined;
      if (platform === "darwin" && !bundle?.endsWith(".app")) continue;
      if (!(await stat(executable)).isFile()) continue;
      await access(executable, platform === "win32" ? 0 : 1);
      let version = "";
      if (platform === "darwin") {
        const { stdout } = await execFileAsync("/usr/bin/plutil", ["-convert", "json", "-o", "-", join(bundle!, "Contents/Info.plist")], { timeout: 3000, maxBuffer: 65536 });
        const info = JSON.parse(stdout) as { CFBundleIdentifier?: string; CFBundleShortVersionString?: string };
        version = info.CFBundleShortVersionString ?? "";
        if (info.CFBundleIdentifier !== "dev.tetravox.viewer" || !compatibleViewerVersion(version)) continue;
      } else {
        // Read straight out of the archive; no foreign executable is run for discovery.
        const metadata = JSON.parse(await readAsarText(join(dirname(executable), "resources/app.asar"), "package.json")) as { name?: string; version?: string };
        version = metadata.version ?? "";
        if (metadata.name !== "@tetravox/app" || !compatibleViewerVersion(version)) continue;
      }
      return { executable, directory: bundle ?? dirname(executable), version };
    } catch { /* Missing, incomplete or foreign: not a TetraVox. */ }
  }
  return undefined;
}

/**
 * One text file out of an asar archive, read through the archive's own header (an 8-byte pickle
 * prefix, the UTF-8 JSON directory, then the file data) so nothing keeps the archive open.
 */
export async function readAsarText(archive: string, inner: string): Promise<string> {
  // An unpacked application (or a test fixture) has a real directory in the archive's place.
  if ((await stat(archive)).isDirectory()) return readFile(join(archive, inner), "utf8");
  const handle = await fs.open(archive, "r");
  try {
    const head = Buffer.alloc(16);
    await handle.read(head, 0, 16, 0);
    const headerSize = head.readUInt32LE(4);
    const jsonSize = head.readUInt32LE(12);
    if (headerSize < 8 || jsonSize > headerSize || jsonSize > 64 * 1024 * 1024) throw new Error(`${archive} is not an asar archive`);
    const json = Buffer.alloc(jsonSize);
    await handle.read(json, 0, jsonSize, 16);
    let node = JSON.parse(json.toString("utf8")) as { files?: Record<string, unknown>; size?: number; offset?: string } | undefined;
    for (const part of inner.split("/")) node = node?.files?.[part] as typeof node;
    if (!node || typeof node.size !== "number" || typeof node.offset !== "string") throw new Error(`${inner} is not in ${archive}`);
    const data = Buffer.alloc(node.size);
    await handle.read(data, 0, node.size, 8 + headerSize + Number(node.offset));
    return data.toString("utf8");
  } finally { await handle.close(); }
}

/** Identify the application at `path` (a `.app` bundle, a bundle executable or a binary) or throw. */
export async function identifyViewerPath(path: string, platform = process.platform): Promise<InstalledViewer> {
  let candidate = path;
  if (platform === "darwin" && !candidate.endsWith(".app")) {
    const bundle = candidate.replace(/\/Contents\/MacOS\/[^/]+$/, "");
    if (bundle.endsWith(".app")) candidate = bundle;
  }
  const viewer = await identifyViewer([candidate], platform);
  if (!viewer) throw new Error("That is not a compatible TetraVox application (0.4 or newer is required).");
  return viewer;
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

/* --------------------------------------------------------------------- managed installs */

/**
 * The TI-installed copies, stable directory first. Older version-addressed directories
 * (`tetravox-<version>-<platform>-<arch>`, from earlier layouts) still count so an existing
 * installation keeps working after an upgrade of TI-Toolbox.
 */
export async function managedInstalls(userData: string, platform = process.platform, arch: string = process.arch): Promise<InstalledViewer[]> {
  const root = join(userData, "runtimes");
  let entries: string[];
  try { entries = await readdir(root); } catch { return []; }
  const stable = `tetravox-${platform}-${arch}`;
  const suffix = `-${platform}-${arch}`;
  const found: InstalledViewer[] = [];
  for (const entry of entries.sort((a, b) => Number(b === stable) - Number(a === stable))) {
    if (entry !== stable && entry !== `${stable}.previous` && (!entry.startsWith("tetravox-") || !entry.endsWith(suffix))) continue;
    const directory = join(root, entry);
    const release = RELEASES[`${platform}-${arch}`];
    if (!release) continue;
    const candidate = platform === "darwin" ? join(directory, "Tetravox.app") : join(directory, release.executable);
    const viewer = await identifyViewer([candidate], platform);
    if (viewer) found.push({ ...viewer, directory });
  }
  return found;
}

/* ------------------------------------------------------------------------- release lookup */

export interface ReleaseLookup {
  version: string;
  /** Asset file name → the SHA-256 GitHub publishes for it (hex), or undefined when it publishes none. */
  assets: Record<string, string | undefined>;
}

/** Ask GitHub for the newest published TetraVox release and its asset digests. Never called from tests unmocked. */
export async function latestViewerRelease(fetchImpl: typeof fetch = fetch): Promise<ReleaseLookup> {
  const response = await fetchImpl(`https://api.github.com/repos/${TETRAVOX_REPO}/releases/latest`, {
    headers: { Accept: "application/vnd.github+json", "User-Agent": "TI-Toolbox" },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error(`Could not check for TetraVox releases (HTTP ${response.status}).`);
  const body = await response.json() as { tag_name?: string; assets?: { name?: string; digest?: string }[] };
  const version = /^v?([0-9]+\.[0-9]+\.[0-9]+)$/.exec(body.tag_name ?? "")?.[1];
  if (!version) throw new Error("The TetraVox release feed did not name a version.");
  const assets: Record<string, string | undefined> = {};
  for (const asset of body.assets ?? []) {
    if (!asset.name) continue;
    assets[asset.name] = /^sha256:([0-9a-f]{64})$/i.exec(asset.digest ?? "")?.[1]?.toLowerCase();
  }
  return { version, assets };
}

function assetUrl(version: string, asset: string): string {
  return `https://github.com/${TETRAVOX_REPO}/releases/download/v${version}/${asset}`;
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
  const managed = (await managedInstalls(userData))[0];
  const { directory, release, executable } = nativeViewerPaths(userData);
  const base: TitNativeTetravoxStatus = {
    supported: !!release,
    installed: false,
    installing: !!installing,
    version: "",
    directory,
    executable,
    error: lastError ?? (!release ? `TI-Toolbox has no TetraVox package for ${process.platform}/${process.arch}.` : undefined),
  };
  if (!managed) return base;
  lastError = undefined;
  return {
    ...base,
    source: "managed",
    executable: managed.executable,
    directory: managed.directory,
    version: managed.version,
    installed: true,
    supportsSceneSave: await supportsNativeSceneApi(managed.executable),
    error: undefined,
  };
}

/* ---------------------------------------------------------------------------- download */

/** Download `url` to `target`, verifying its SHA-256 (hex) as it streams; a mismatch leaves nothing usable. */
export async function downloadViewer(url: string, target: string, sha256: string): Promise<void> {
  const response = await fetch(url, { signal: AbortSignal.timeout(300_000) });
  if (!response.ok || !response.body) throw new Error(`TetraVox download failed (HTTP ${response.status}).`);
  const total = Number(response.headers.get("content-length")) || undefined;
  const hash = createHash("sha256");
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
  if (hash.digest("hex") !== sha256.toLowerCase()) throw new Error("TetraVox download checksum mismatch. Nothing was installed.");
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

/**
 * Unpack the release archive into `into`. macOS uses `ditto` so the bundle's signature and
 * extended attributes survive; Linux and Windows use `tar`, which ships with both (Windows 10+
 * carries bsdtar as `System32\tar.exe`, and it reads zip files).
 */
export async function unpackViewerArchive(archive: string, into: string, release: PlatformRelease, platform = process.platform): Promise<void> {
  if (platform === "darwin") { await viewerCommand("/usr/bin/ditto", ["-x", "-k", archive, into]); return; }
  const tar = platform === "win32" ? join(process.env.SystemRoot ?? "C:\\Windows", "System32", "tar.exe") : "tar";
  await viewerCommand(tar, ["-xf", archive, "-C", into, ...(release.strip ? [`--strip-components=${release.strip}`] : [])]);
}

/* ------------------------------------------------------------------------------ install */

/** First-time setup, or a no-op when TI's copy already exists. One in-flight install is shared. */
export function installNativeViewer(userData: string): Promise<TitNativeTetravoxStatus> {
  return runInstall(userData, false);
}

/** Replace TI's copy with the newest release. Refused while that copy is open. */
export function updateNativeViewer(userData: string): Promise<TitNativeTetravoxStatus> {
  return runInstall(userData, true);
}

function runInstall(userData: string, replace: boolean): Promise<TitNativeTetravoxStatus> {
  if (installing) return installing;
  lastError = undefined;
  installing = install(userData, replace)
    .catch((error: unknown) => { lastError = error instanceof Error ? error.message : String(error); throw error; })
    .finally(() => { installing = undefined; report({ phase: "idle" }); })
    .then((status) => ({ ...status, installing: false }));
  return installing;
}

async function install(userData: string, replace: boolean): Promise<TitNativeTetravoxStatus> {
  const existing = await nativeViewerStatus(userData);
  if (existing.installed && !replace) return existing;
  if (!existing.supported) throw new Error(existing.error ?? "TI-Toolbox has no TetraVox package for this platform.");
  if (existing.installed && await nativeViewerRunning(userData, existing)) throw new Error("Close TetraVox before updating it.");

  const { version, assets } = await latestViewerRelease();
  if (!compatibleViewerVersion(version)) throw new Error(`TetraVox ${version} is not compatible with this TI-Toolbox release.`);
  if (existing.installed && compareViewerVersions(existing.version, version) >= 0) return existing;
  const paths = nativeViewerPaths(userData, process.platform, process.arch, version);
  const { release, directory } = paths;
  if (!release || !paths.executable) throw new Error("TI-Toolbox has no TetraVox package for this platform.");
  if (!(release.asset in assets)) throw new Error(`TetraVox ${version} has no package for this platform.`);
  const sha256 = assets[release.asset];
  if (!sha256) throw new Error(`TetraVox ${version} publishes no checksum for ${release.asset}; nothing was installed.`);

  await mkdir(dirname(directory), { recursive: true, mode: 0o700 });
  // Staging left behind by an interrupted or failed attempt is ours to remove; two TI-Toolbox
  // processes installing at the same instant is not a case worth a lock file.
  for (const entry of await readdir(dirname(directory)).catch(() => [] as string[])) {
    if (entry.startsWith(".tetravox-install-")) await rm(join(dirname(directory), entry), { recursive: true, force: true }).catch(() => undefined);
  }
  const staging = await mkdtemp(join(dirname(directory), ".tetravox-install-"));
  try {
    const archive = join(staging, release.asset);
    await downloadViewer(assetUrl(version, release.asset), archive, sha256);
    const unpacked = join(staging, "app");
    await mkdir(unpacked, { mode: 0o700 });
    report({ phase: "install" });
    await unpackViewerArchive(archive, unpacked, release);
    const identified = await identifyViewerPath(process.platform === "darwin" ? join(unpacked, "Tetravox.app") : join(unpacked, release.executable));
    if (identified.version !== version) throw new Error(`TetraVox archive identifies version ${identified.version}, but the verified release is ${version}. Nothing was installed.`);
    await chmod(join(unpacked, release.executable), 0o755);
    await writeFile(join(unpacked, "ready.json"), JSON.stringify({ version, sha256, managedBy: MANAGED_BY }), { mode: 0o600 });

    // Swap: the previous copy moves aside first so a crash between the two renames still leaves
    // one identifiable installation (`managedInstalls` also accepts the `.previous` name).
    const previous = `${directory}.previous`;
    await rm(previous, { recursive: true, force: true });
    if (existing.installed && existing.directory === directory) await rename(directory, previous);
    try { await rename(unpacked, directory); } catch (error) {
      if (!["EEXIST", "ENOTEMPTY", "ENOTDIR", "EISDIR", "EPERM"].includes((error as NodeJS.ErrnoException).code ?? "")) throw error;
      const winner = await nativeViewerStatus(userData);
      if (winner.installed) return winner;
      throw new Error(`TetraVox setup found an incomplete installation at ${directory}. Move that directory aside and retry; its contents were preserved.`, { cause: error });
    }
    await rm(previous, { recursive: true, force: true });
    return nativeViewerStatus(userData);
  } finally { await rm(staging, { recursive: true, force: true }); }
}

/* --------------------------------------------------------------------------------- open */

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
  if (!status.installed || !status.executable) throw new Error("TetraVox is not installed yet. Open Settings → Viewer and retry its setup.");
  const { executable } = status;
  // Earlier layouts gave TI's copy its own profile; keep using it where it exists so an open
  // viewer's single-instance lock is the one this launch reaches.
  const legacyProfile = join(userData, "tetravox-profile");
  const useLegacyProfile = await stat(legacyProfile).then((entry) => entry.isDirectory(), () => false);
  const env: NodeJS.ProcessEnv = { ...process.env, TETRAVOX_MANAGED_BY: MANAGED_BY };
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
  // The Linux tarball's chrome-sandbox cannot be made setuid-root without administrator rights,
  // so Chromium's SUID sandbox is off there; the viewer only ever opens local files.
  const platformArgs = process.platform === "linux" ? ["--no-sandbox"] : [];
  await new Promise<void>((resolve, reject) => {
    const logPath = join(userData, "tetravox-launch.log");
    const descriptor = openSync(logPath, "w", 0o600);
    const child = spawn(executable!, [...platformArgs, ...(useLegacyProfile ? [`--user-data-dir=${legacyProfile}`] : []), ...(requestPath ? [`--scene-request=${requestPath}`] : scene ? [scene] : [])], { env, detached: true, stdio: ["ignore", "ignore", descriptor], windowsHide: false });
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

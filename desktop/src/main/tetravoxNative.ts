/** Managed native viewer. Only pinned official release bytes may become executable. */
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { closeSync, createReadStream, createWriteStream, openSync } from "node:fs";
import { access, chmod, mkdir, mkdtemp, readFile, realpath, rename, rm, stat, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, sep } from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { TitNativeTetravoxStatus } from "../shared/tit-bridge";

export const TETRAVOX_VERSION = "0.4.0";
// SHA256 from the official GitHub release asset metadata; changing versions requires review.
const RELEASES: Record<string, { asset: string; sha256: string; executable: string }> = {
  "darwin-arm64": { asset: "Tetravox-0.4.0-mac-arm64.zip", sha256: "19d1f8d304a6d5b632ad17197bf3edf5469921695f7969f35b52d39c537182aa", executable: "Tetravox.app/Contents/MacOS/Tetravox" },
  "darwin-x64": { asset: "Tetravox-0.4.0-mac-x64.zip", sha256: "f7d1eb9d7ebfd12998c169e1893e03137ee8e407ef405eba4837cefb5693e5b0", executable: "Tetravox.app/Contents/MacOS/Tetravox" },
  "linux-x64": { asset: "Tetravox-0.4.0-linux-x64.tar.gz", sha256: "0ca9ed64947d2a242cb3ba809c7d99ece10fa99e445b02c80122ced37f5e7306", executable: "tetravox" },
};
export function nativeViewerPaths(userData: string, platform = process.platform, arch: string = process.arch) {
  const release = RELEASES[`${platform}-${arch}`];
  const directory = join(userData, "runtimes", `tetravox-${TETRAVOX_VERSION}-${platform}-${arch}`);
  return { directory, release, executable: release ? join(directory, release.executable) : undefined };
}
async function digestFile(path: string): Promise<string> {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}
let installing: Promise<TitNativeTetravoxStatus> | undefined;
let lastError: string | undefined;
export async function nativeViewerStatus(userData: string): Promise<TitNativeTetravoxStatus> {
  const { directory, release, executable } = nativeViewerPaths(userData);
  let installed = false;
  if (release && executable) {
    try {
      const manifest = JSON.parse(await readFile(join(directory, "ready.json"), "utf8")) as { archiveHash?: string; executableHash?: string };
      installed = manifest.archiveHash === release.sha256 && !!manifest.executableHash && await digestFile(executable) === manifest.executableHash;
    } catch { /* A missing/incomplete installation is not ready; the install action can retry. */ }
  }
  return { version: TETRAVOX_VERSION, directory, supported: !!release, installed, installing: !!installing, error: lastError ?? (!release ? "No verified portable TetraVox package is configured for this platform. Windows managed setup requires an official ZIP release; its system installer is not used." : undefined) };
}
export async function downloadViewer(url: string, target: string, expectedHash: string): Promise<void> {
  const response = await fetch(url, { signal: AbortSignal.timeout(300_000) });
  if (!response.ok || !response.body) throw new Error(`TetraVox download failed (HTTP ${response.status}).`);
  const hash = createHash("sha256");
  let size = 0;
  const verify = new Transform({ transform(chunk: Buffer, _encoding, callback) {
    size += chunk.length;
    if (size > 500 * 1024 * 1024) { callback(new Error("TetraVox download exceeds the supported package size.")); return; }
    hash.update(chunk); callback(null, chunk);
  } });
  await pipeline(Readable.fromWeb(response.body as never), verify, createWriteStream(target, { mode: 0o600, flags: "wx" }));
  if (hash.digest("hex") !== expectedHash) throw new Error("TetraVox download checksum mismatch. Nothing was installed.");
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
  installing = install(userData).catch((error: unknown) => { lastError = error instanceof Error ? error.message : String(error); throw error; }).finally(() => { installing = undefined; });
  return installing.then(() => nativeViewerStatus(userData));
}
async function install(userData: string): Promise<TitNativeTetravoxStatus> {
  const paths = nativeViewerPaths(userData);
  const { release, directory } = paths;
  if (!release || !paths.executable) throw new Error("This platform has no supported native TetraVox release.");
  if ((await nativeViewerStatus(userData)).installed) return nativeViewerStatus(userData);
  await mkdir(dirname(directory), { recursive: true, mode: 0o700 });
  const staging = await mkdtemp(join(dirname(directory), ".tetravox-install-"));
  try {
    const archive = join(staging, release.asset);
    await downloadViewer(`https://github.com/idossha/Tetravox/releases/download/v${TETRAVOX_VERSION}/${release.asset}`, archive, release.sha256);
    const extracted = join(staging, "app");
    await mkdir(extracted, { mode: 0o700 });
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
    await writeFile(join(directory, "ready.json"), JSON.stringify({ version: TETRAVOX_VERSION, archiveHash: release.sha256, executableHash }), { mode: 0o600 });
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
export async function openNativeViewer(userData: string, scene: string): Promise<void> {
  if (!(await nativeViewerStatus(userData)).installed) throw new Error("Install native TetraVox in Settings → Viewer first.");
  const { executable } = nativeViewerPaths(userData);
  await new Promise<void>((resolve, reject) => {
    const env: NodeJS.ProcessEnv = { ...process.env, TETRAVOX_MANAGED_BY: "TI-Toolbox" };
    delete env.ELECTRON_RUN_AS_NODE;
    const logPath = join(userData, "tetravox-launch.log");
    const descriptor = openSync(logPath, "w", 0o600);
    const child = spawn(executable!, [`--user-data-dir=${join(userData, "tetravox-profile")}`, ...(scene ? [scene] : [])], { env, detached: true, stdio: ["ignore", "ignore", descriptor], windowsHide: false });
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

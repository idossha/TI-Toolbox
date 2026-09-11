import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile, rm, stat } from "node:fs/promises";
import { join } from "node:path";

export const FASTSURFER_VERSION = "2.5.4";
const SOURCE_COMMIT = "cdfccea89e6c2bdbd6a2abb3f033f2e618a54538";
const SOURCE_HASH = "0059a33da3a7b8cca2bd202af33e4c0b9455353044185df7beb3f1ca63baae1d";
const UV_HASH = "7e6ddb9316acc00f2296c82ff4d99977870ee34b2f0ddcae9444d714db9364ed";
const CHECKPOINTS = {
  axial: "81ab25ccbfc432cc41fb6089d11ff2a45b5a88e659092096cb1e067269f806b8",
  coronal: "73813957e83ec99d2c4e22f7854308916ec276d66ab7ed8ef8bf3998ba05e289",
  sagittal: "edae6262d69526fea39a019f2dfd8df75eb705f8f025b9b97166e3e17b917414",
};
export interface FastSurferRuntime { sourceDir: string; pythonPath: string }
export function runtimePaths(userData: string): FastSurferRuntime & { directory: string } {
  const directory = join(userData, "runtimes", `fastsurfer-${FASTSURFER_VERSION}-arm64`);
  return { directory, sourceDir: join(directory, `FastSurfer-${SOURCE_COMMIT}`), pythonPath: join(directory, "venv", "bin", "python") };
}
export function verifyDigest(bytes: Uint8Array, expected: string): void {
  if (createHash("sha256").update(bytes).digest("hex") !== expected) throw new Error("FastSurfer download checksum mismatch.");
}
async function download(url: string, target: string, hash: string): Promise<void> {
  const response = await fetch(url, { signal: AbortSignal.timeout(300_000) });
  if (!response.ok) throw new Error(`Download failed (${response.status}): ${new URL(url).hostname}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  verifyDigest(bytes, hash);
  await writeFile(target, bytes, { mode: 0o600 });
}
export function runInstallCommand(command: string, args: string[], env: NodeJS.ProcessEnv, log: (text: string) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { env, stdio: ["ignore", "pipe", "pipe"] });
    let output = "";
    const collect = (chunk: Buffer) => { const text = chunk.toString(); output = (output + text).slice(-16000); log(text); };
    child.stdout.on("data", collect);
    child.stderr.on("data", collect);
    const timer = setTimeout(() => { child.kill("SIGKILL"); reject(new Error("FastSurfer setup timed out.")); }, 20 * 60_000);
    child.once("error", (error) => { clearTimeout(timer); reject(error); });
    child.once("close", (code) => { clearTimeout(timer); if (code === 0) resolve(output); else reject(new Error(`FastSurfer setup failed: ${output.slice(-1500)}`)); });
  });
}
function setupEnvironment(directory: string): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env, UV_PYTHON_INSTALL_DIR: join(directory, "python"), UV_CACHE_DIR: join(directory, "cache"), PYTHONNOUSERSITE: "1" };
  delete env.PYTHONPATH;
  delete env.PYTHONHOME;
  return env;
}
export async function probeFastSurfer(userData: string): Promise<boolean> {
  const paths = runtimePaths(userData);
  try {
    const manifest = JSON.parse(await readFile(join(paths.directory, "ready.json"), "utf8")) as { version?: string };
    if (manifest.version !== FASTSURFER_VERSION) return false;
    await stat(join(paths.sourceDir, "run_fastsurfer.sh"));
    for (const plane of Object.keys(CHECKPOINTS)) await stat(join(paths.sourceDir, "checkpoints", `aparc_vinn_${plane}_v2.0.0.pkl`));
    await runInstallCommand(paths.pythonPath, ["-c", "import platform,torch,nibabel,scipy; assert platform.machine()=='arm64'; assert torch.backends.mps.is_available()"], setupEnvironment(paths.directory), () => {});
    return true;
  } catch { return false; }
}
let installing: Promise<FastSurferRuntime> | undefined;
export function installFastSurfer(userData: string, log: (text: string) => void = () => {}): Promise<FastSurferRuntime> {
  if (process.platform !== "darwin" || process.arch !== "arm64") return Promise.reject(new Error("Native FastSurfer requires Apple Silicon."));
  if (installing) return installing;
  installing = install(userData, log).finally(() => { installing = undefined; });
  return installing;
}
async function install(userData: string, log: (text: string) => void): Promise<FastSurferRuntime> {
  const paths = runtimePaths(userData);
  if (await probeFastSurfer(userData)) return paths;
  await mkdir(paths.directory, { recursive: true, mode: 0o700 });
  const env = setupEnvironment(paths.directory);
  const sourceArchive = join(paths.directory, "source.tar.gz");
  const uvArchive = join(paths.directory, "uv.tar.gz");
  log("Downloading verified FastSurfer source and installer tools.\n");
  await download(`https://codeload.github.com/Deep-MI/FastSurfer/tar.gz/${SOURCE_COMMIT}`, sourceArchive, SOURCE_HASH);
  await download("https://github.com/astral-sh/uv/releases/download/0.12.13/uv-aarch64-apple-darwin.tar.gz", uvArchive, UV_HASH);
  await runInstallCommand("/usr/bin/tar", ["-xzf", sourceArchive, "-C", paths.directory], env, log);
  await runInstallCommand("/usr/bin/tar", ["-xzf", uvArchive, "-C", paths.directory], env, log);
  const uv = join(paths.directory, "uv-aarch64-apple-darwin", "uv");
  log("Installing the managed Python environment.\n");
  let hasInterpreter = false;
  try { await stat(paths.pythonPath); hasInterpreter = true; } catch { /* Incomplete installs can be retried. */ }
  if (!hasInterpreter) await runInstallCommand(uv, ["venv", "--python", "3.12.12", join(paths.directory, "venv")], env, log);
  await runInstallCommand(uv, ["pip", "sync", "--python", paths.pythonPath, join(paths.sourceDir, "requirements.txt")], env, log);
  await mkdir(join(paths.sourceDir, "checkpoints"), { recursive: true });
  for (const [plane, hash] of Object.entries(CHECKPOINTS)) {
    const filename = `aparc_vinn_${plane}_v2.0.0.pkl`;
    log(`Downloading ${plane} checkpoint.\n`);
    await download(`https://b2share.fz-juelich.de/api/files/a423a576-220d-47b0-9e0c-b5b32d45fc59/${filename}`, join(paths.sourceDir, "checkpoints", filename), hash);
  }
  await runInstallCommand(paths.pythonPath, ["-c", "import platform,torch,nibabel,scipy; assert platform.machine()=='arm64'; assert torch.backends.mps.is_available()"], env, log);
  await writeFile(join(paths.directory, "ready.json"), JSON.stringify({ version: FASTSURFER_VERSION, source: SOURCE_COMMIT }), { mode: 0o600 });
  await rm(sourceArchive); await rm(uvArchive);
  return paths;
}

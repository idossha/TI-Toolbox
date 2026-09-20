/** Versioned native scene requests; capture the active native viewer into a project-owned destination. */
import { constants } from "node:fs";
import { randomBytes } from "node:crypto";
import { execFile } from "node:child_process";
import { chmod, lstat, mkdtemp, open, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, sep } from "node:path";
import { userInfo } from "node:os";
import { promisify } from "node:util";
import type { TitNativeTetravoxStatus } from "../shared/tit-bridge";

const MAX_RECEIPT_BYTES = 16 * 1024;
export interface NativeSceneRequest {
  protocol: 1;
  id: string;
  action: "open-scene" | "save-scene";
  path: string;
  expectedScenePath?: string;
  overwrite?: boolean;
}

/** Capability is declared by the installed application, never guessed from its version. */
export async function supportsNativeSceneApi(executable: string, platform = process.platform): Promise<boolean> {
  const resources = platform === "darwin" ? join(dirname(dirname(executable)), "Resources") : join(dirname(executable), "resources");
  try {
    const metadata = JSON.parse(await readFile(join(resources, "app.asar/package.json"), "utf8")) as { sceneApiProtocol?: unknown };
    return metadata.sceneApiProtocol === 1;
  } catch { return false; }
}

export async function exchangeNativeSceneRequest(
  userData: string,
  request: NativeSceneRequest,
  send: (path: string) => Promise<void>,
  timeoutMs = 30_000,
): Promise<string> {
  const directory = await mkdtemp(join(userData, ".tetravox-request-"));
  const requestPath = join(directory, "request.json");
  const receiptPath = `${requestPath}.receipt.json`;
  try {
    if (process.platform === "win32") {
      // Restrict inheritance to the current host user; no elevated installer or network listener.
      await promisify(execFile)("icacls.exe", [directory, "/inheritance:r", "/grant:r", `${userInfo().username}:(OI)(CI)F`], { windowsHide: true, timeout: 5000 });
    } else await chmod(directory, 0o700);
    await writeFile(requestPath, JSON.stringify(request), { mode: 0o600, flag: "wx" });
    await send(requestPath);
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        const info = await lstat(receiptPath);
        if (!info.isFile() || info.isSymbolicLink() || info.size > MAX_RECEIPT_BYTES) throw new Error("Invalid TetraVox scene receipt.");
        const handle = await open(receiptPath, constants.O_RDONLY | (process.platform === "win32" ? 0 : constants.O_NOFOLLOW));
        let text: string;
        try {
          const buffer = Buffer.alloc(MAX_RECEIPT_BYTES + 1);
          const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
          if (bytesRead > MAX_RECEIPT_BYTES) throw new Error("TetraVox scene receipt is too large.");
          text = buffer.subarray(0, bytesRead).toString("utf8");
        } finally { await handle.close(); }
        const receipt = JSON.parse(text) as { protocol?: unknown; id?: unknown; ok?: unknown; path?: unknown; error?: unknown };
        if (!receipt || receipt.protocol !== 1 || receipt.id !== request.id) throw new Error("TetraVox scene receipt does not match this request.");
        if (receipt.ok !== true) throw new Error(typeof receipt.error === "string" ? receipt.error : "TetraVox could not complete the scene request.");
        const expected = request.path;
        if (receipt.path !== expected) throw new Error("TetraVox saved a different scene path than requested.");
        return expected;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("TetraVox did not acknowledge the scene request. Check its window before retrying.");
  } finally { await rm(directory, { recursive: true, force: true }); }
}

async function withinProject(path: string, root: string): Promise<string> {
  const canonical = await realpath(path);
  const rel = relative(await realpath(root), canonical);
  if (!rel || isAbsolute(rel) || rel === ".." || rel.startsWith(`..${sep}`)) throw new Error("The native scene must remain inside the active project.");
  return canonical;
}

export function createNativeSceneSession(exchange: (request: NativeSceneRequest, viewer: TitNativeTetravoxStatus) => Promise<string>) {
  let generation = 0;
  return {
    clear() { generation++; },
    async open(scene: string, root: string, viewer: TitNativeTetravoxStatus): Promise<void> {
      const pending = ++generation;
      const canonicalRoot = await realpath(root);
      const canonical = await withinProject(scene, canonicalRoot);
      await exchange({ protocol: 1, id: randomBytes(16).toString("hex"), action: "open-scene", path: canonical }, viewer);
      if (pending !== generation) throw new Error("The active scene changed while TetraVox was opening.");
    },
    async save(destination: string, root: string, viewer: TitNativeTetravoxStatus): Promise<string> {
      const pending = generation;
      if (!viewer.supportsSceneSave) throw new Error("The selected TetraVox does not support saving its live scene. Select a compatible installation in Settings.");
      const canonicalRoot = await realpath(root);
      const parent = await withinProject(dirname(destination), root);
      const canonicalDestination = join(parent, basename(destination));
      if (parent !== join(canonicalRoot, "code/ti-toolbox/viewer/scenes") || !canonicalDestination.endsWith(".tetravox.json")) throw new Error("Invalid native scene destination.");
      try { await lstat(canonicalDestination); throw new Error("A scene with this name already exists."); }
      catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
      if (pending !== generation) throw new Error("The active scene changed before saving.");
      const path = await exchange({ protocol: 1, id: randomBytes(16).toString("hex"), action: "save-scene", path: canonicalDestination }, viewer);
      const info = await lstat(path);
      if (!info.isFile() || info.isSymbolicLink()) throw new Error("TetraVox did not save a regular scene file.");
      return path;
    },
  };
}

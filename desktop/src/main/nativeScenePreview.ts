/** Photograph a saved scene offscreen; publish only a validated, bounded project thumbnail. */
import { lstat, mkdtemp, readFile, realpath, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { runNativeCapture } from "./roiPlates";

export interface ScenePreviewOptions {
  scene: string;
  root: string;
  userData: string;
  executable: string;
  current(): boolean | Promise<boolean>;
  resize(png: Buffer): Buffer;
  run?: typeof runNativeCapture;
}

export async function renderNativeScenePreview(options: ScenePreviewOptions): Promise<void> {
  const { root, userData, executable, current, resize } = options;
  const scene = await realpath(options.scene);
  const directory = join(await realpath(root), "code/ti-toolbox/viewer/scenes");
  if (dirname(scene) !== directory || !scene.endsWith(".tetravox.json")) throw new Error("Preview must belong to the active project's saved scenes.");
  const source = await stat(scene);
  if (!source.isFile()) throw new Error("Scene is not a file.");
  const destination = scene.replace(/\.tetravox\.json$/, ".png");
  try {
    const existing = await lstat(destination);
    if (!existing.isFile() || existing.isSymbolicLink() || existing.size > 1024 * 1024) throw new Error("Existing scene preview is invalid; its file was preserved.");
    const header = (await readFile(destination)).subarray(0, 8);
    if (!header.equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) throw new Error("Existing scene preview is invalid; its file was preserved.");
    return;
  }
  catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
  if (!await current()) throw new Error("The active project changed before generating the preview.");
  const temporary = await mkdtemp(join(userData, ".scene-preview-"));
  try {
    const job = join(temporary, "job.json");
    await writeFile(job, JSON.stringify({
      version: 1,
      scene: { path: scene },
      window: { width: 1200, height: 900 },
      actions: [{ type: "screenshot", out: "preview.png", view: "grid", background: "scene" }],
    }), { mode: 0o600, flag: "wx" });
    if (!await current()) throw new Error("The active project changed before generating the preview.");
    const code = await (options.run ?? runNativeCapture)(executable, ["--job", job, "--out", temporary, "--quiet", `--user-data-dir=${join(temporary, "profile")}`]);
    if (code !== 0) throw new Error(`TetraVox could not render this saved scene (exit ${code}).`);
    const pngPath = join(temporary, "preview.png");
    if ((await stat(pngPath)).size > 16 * 1024 * 1024) throw new Error("Scene preview is too large.");
    const png = resize(await readFile(pngPath));
    if (!png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) || png.length > 1024 * 1024) throw new Error("TetraVox produced an invalid preview.");
    const unchanged = await stat(await realpath(scene));
    if (!await current() || await realpath(scene) !== scene || unchanged.mtimeMs !== source.mtimeMs || unchanged.size !== source.size || await realpath(dirname(scene)) !== directory) throw new Error("The scene or project changed while generating the preview.");
    await writeFile(destination, png, { flag: "wx", mode: 0o600 });
  } finally { await rm(temporary, { recursive: true, force: true }); }
}

/** Bound GPU work and coalesce visible rows requesting the same thumbnail. */
export function createScenePreviewQueue() {
  const pending = new Map<string, Promise<void>>();
  let tail = Promise.resolve();
  return (path: string, run: () => Promise<void>): Promise<void> => {
    const existing = pending.get(path);
    if (existing) return existing;
    if (pending.size >= 8) return Promise.reject(new Error("Preview queue is busy. Refresh saved scenes to retry."));
    const task = tail.then(run);
    pending.set(path, task);
    tail = task.catch(() => undefined).finally(() => { pending.delete(path); });
    return task;
  };
}

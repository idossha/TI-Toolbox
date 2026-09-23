/**
 * The optional host-side picture of a finished job's scenes.
 *
 * The job itself writes one small `*.tetravox.json` scene: an optimizer's `roi.tetravox.json`
 * (`tit/roi_confirmation.py`: the subject's T1, the ROI layer, the cursor and the zoom) or an
 * analysis's `scene.tetravox.json` (`tit/analyzer/scene.py`: the field masked to the ROI over the
 * anatomy), all pointing at files that already exist. That scene is the artefact. This module is
 * the *extra*: when Tetravox is installed on this machine, each scene is photographed once into a
 * PNG of the same name beside it (`scene.png`, `roi.png`), so a person scrolling the job's folder
 * sees the result without opening anything.
 *
 * No Tetravox, a refusal or a timeout: one log line, and nothing is lost — the scene is still there
 * and **Open in Tetravox** still works. A picture never fails a job and never blanks one.
 *
 * The `--job` document is built here, from the scene, at the moment of the run and **never
 * persisted**: it is three lines of JSON that say "open this scene and photograph it", and a file of
 * it beside the scene would be one more artefact for the person to wonder about — which is exactly
 * what this change removed. The same goes for the `job-result.json` Tetravox writes into `--out`:
 * it is read for the log line and removed, so the folder holds the data, the scene and the picture
 * and nothing else. The scene addresses its data with paths relative to itself, so there is nothing
 * to re-root either: the same file works in the container that wrote it and on this host.
 */
import { mkdir, mkdtemp, readFile, rm, writeFile, unlink } from "node:fs/promises";
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { log } from "./log";

/** How long one capture may take. A 1600x1200 three-panel figure is ~8-10 s on a warm app. */
export const PLATE_TIMEOUT_MS = 120_000;

/** At most this many scenes per job, so a 40-target batch cannot occupy the GPU for an hour. */
export const PLATE_LIMIT = 8;

const SCENE_SUFFIX = ".tetravox.json";

export interface PlateRunnerDeps {
  /** Absolute container paths of everything the job produced. */
  artifactPaths(jobId: string): Promise<string[]>;
  /** A container path mapped into the host filesystem, or `null` when it does not map. */
  toHostPath(containerPath: string): Promise<string | null>;
  /** The resolved Tetravox executable, or `undefined` when there is none. */
  viewerExecutable(): Promise<string | undefined>;
  /** Run it. Resolves with the exit code; rejects only on a spawn failure. */
  run?(executable: string, args: string[], home: string): Promise<number>;
  writeFileText?(path: string, text: string): Promise<void>;
  readFileText?(path: string): Promise<string>;
  removeFile?(path: string): Promise<void>;
  logLine?(level: "info" | "warn", message: string): void;
}

/** The scenes among a job's artifacts, de-duplicated and capped. */
export function roiScenes(paths: string[]): string[] {
  const seen = new Set<string>();
  for (const path of paths) {
    if (path.endsWith(SCENE_SUFFIX)) seen.add(path);
  }
  return [...seen].sort().slice(0, PLATE_LIMIT);
}

/** The PNG a scene is photographed into: its own name with the suffix swapped. */
export function pngFor(scenePath: string): string {
  return basename(scenePath).slice(0, -SCENE_SUFFIX.length) + ".png";
}

/**
 * The `--job` document that photographs one saved scene.
 *
 * `scene.path` restores everything the scene carries — layers, colours, thresholds, the cursor and
 * the camera (Tetravox `docs/AUTOMATION.md` §2.1) — so this document decides nothing about how the
 * scene looks. It only says which panels to lay out and how big. The 3D pane is in the figure only
 * when the scene has a mesh or surface to draw in it (an analysis's cortex, a cortical target);
 * a scene of volumes alone would put an empty pane on the page. `out` is a bare name under
 * `--out`, which is the scene's own directory.
 */
export function buildJob(scenePath: string, sceneText?: string): unknown {
  const has3d = sceneHasMesh(sceneText);
  return {
    version: 1,
    scene: { path: scenePath },
    window: { width: 1600, height: 1200 },
    actions: [
      {
        type: "screenshot",
        out: pngFor(scenePath),
        view: "figure",
        width: 533,
        dpi: 300,
        background: "white",
        include: {
          colorbar: true,
          orientationLabels: true,
          crosshair: true,
          scaleBar: true,
          cornerInfo: true,
        },
        figure: {
          panels: has3d ? ["view3d", "axial", "coronal", "sagittal"] : ["axial", "coronal", "sagittal"],
          columns: has3d ? 2 : 3,
          gutterMm: 3,
          labels: "upper",
          background: "white",
        },
      },
    ],
  };
}

/** Whether a scene file (its JSON text) lists a mesh or surface dataset. */
export function sceneHasMesh(sceneText: string | undefined): boolean {
  if (!sceneText) return false;
  try {
    const parsed = JSON.parse(sceneText) as { datasets?: { kind?: string }[] };
    return (parsed.datasets ?? []).some((d) => d.kind === "mesh" || d.kind === "surface");
  } catch {
    return false;
  }
}

/** One line from Tetravox's `job-result.json`, for the log; `null` when it is not readable. */
export function summariseResult(text: string): string | null {
  try {
    const parsed = JSON.parse(text) as {
      ok?: boolean;
      outputs?: { files?: string[] }[];
      timings?: { totalMs?: number };
      warnings?: unknown[];
      errors?: unknown[];
    };
    const files = (parsed.outputs ?? []).flatMap((o) => o.files ?? []);
    const parts = [
      parsed.ok ? "ok" : "failed",
      files.length ? files.join(", ") : "no file",
      `${parsed.timings?.totalMs ?? "?"} ms`,
    ];
    if (parsed.warnings?.length) parts.push(`${parsed.warnings.length} warning(s): ${JSON.stringify(parsed.warnings)}`);
    if (parsed.errors?.length) parts.push(`${parsed.errors.length} error(s): ${JSON.stringify(parsed.errors)}`);
    return parts.join("; ");
  } catch {
    return null;
  }
}

/** `home` is the capture's own TETRAVOX_HOME, so it never reads or writes the user's `~/.tetravox`. */
export function runNativeCapture(executable: string, args: string[], home: string): Promise<number> {
  return new Promise((resolve, reject) => {
    // `--job` forces offscreen and is exempt from the single-instance lock, so this never takes
    // focus and never disturbs a window the user has open.
    const env: NodeJS.ProcessEnv = { ...process.env, TETRAVOX_HOME: home };
    delete env.TETRAVOX_MODULE_DIR; // would override `<home>/modules` with the user's extensions
    const child = spawn(executable, args, { stdio: "ignore", windowsHide: true, detached: false, env });
    const timer = setTimeout(() => {
      try {
        child.kill();
      } catch {
        // Already gone.
      }
    }, PLATE_TIMEOUT_MS);
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve(code ?? 1);
    });
  });
}

export interface PlateRunResult {
  rendered: string[];
  skipped: string[];
}

/** Photograph every scene a finished job left behind. Never throws. */
export async function renderPlatesForJob(jobId: string, deps: PlateRunnerDeps): Promise<PlateRunResult> {
  const say = deps.logLine ?? ((level: "info" | "warn", message: string) => log(level, message));
  const write = deps.writeFileText ?? ((path: string, text: string) => writeFile(path, text, "utf8"));
  const read = deps.readFileText ?? ((path: string) => readFile(path, "utf8"));
  const remove = deps.removeFile ?? ((path: string) => unlink(path));
  const run = deps.run ?? runNativeCapture;
  const result: PlateRunResult = { rendered: [], skipped: [] };

  let scenes: string[];
  try {
    scenes = roiScenes(await deps.artifactPaths(jobId));
  } catch (error) {
    say("warn", `roi scenes: could not list job ${jobId}'s artifacts: ${String(error)}`);
    return result;
  }
  if (!scenes.length) return result;

  const executable = await deps.viewerExecutable();
  if (!executable) {
    say("info", `roi scenes: no Tetravox on this machine; ${scenes.length} scene(s) get no picture`);
    return { rendered: [], skipped: scenes };
  }

  for (const scene of scenes) {
    const hostScene = await deps.toHostPath(scene);
    if (!hostScene) {
      result.skipped.push(scene);
      say("warn", `roi scenes: ${basename(scene)} is outside the mounted project`);
      continue;
    }
    const outDir = dirname(hostScene);
    // The document is a temporary beside the scene, removed whatever happens: it is derived from
    // the scene in one line and is not something anybody should find in a results folder.
    const documentPath = join(outDir, `.${basename(hostScene)}.job.json`);
    // Tetravox writes its trace here; it is logged and removed, never left in a results folder.
    const resultPath = join(outDir, "job-result.json");
    try {
      let sceneText: string | undefined;
      try {
        sceneText = await read(hostScene);
      } catch {
        sceneText = undefined;
      }
      await write(documentPath, JSON.stringify(buildJob(hostScene, sceneText), null, 1));
      // A throwaway profile: `--job` skips the single-instance lock, so without one the capture
      // would write into Electron's default TetraVox profile — the one a user's own copy uses.
      const profile = await mkdtemp(join(tmpdir(), "tit-tetravox-plate-"));
      let code: number;
      try {
        const home = join(profile, "tetravox-home");
        await mkdir(home);
        code = await run(executable, ["--job", documentPath, "--out", outDir, "--quiet", `--user-data-dir=${profile}`], home);
      } finally {
        await rm(profile, { recursive: true, force: true });
      }
      if (code === 0) {
        result.rendered.push(scene);
      } else {
        result.skipped.push(scene);
        say("warn", `roi scenes: Tetravox exited ${code} for ${basename(scene)}; no picture, the scene stands`);
      }
      try {
        const trace = summariseResult(await read(resultPath));
        if (trace) say("info", `roi scenes: ${basename(scene)} -> ${trace}`);
      } catch {
        // No trace was written (a spawn failure, or an older Tetravox).
      }
    } catch (error) {
      result.skipped.push(scene);
      say("warn", `roi scenes: ${basename(scene)} could not be photographed: ${String(error)}`);
    } finally {
      for (const path of [documentPath, resultPath]) {
        try {
          await remove(path);
        } catch {
          // Nothing was written, or it is already gone.
        }
      }
    }
  }
  if (result.rendered.length) {
    say("info", `roi scenes: Tetravox photographed ${result.rendered.length} scene(s) for job ${jobId}`);
  }
  return result;
}

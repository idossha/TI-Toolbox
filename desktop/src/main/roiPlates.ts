/**
 * The host-side Tetravox pass over a finished job's ROI plates (options doc § O1).
 *
 * The container that runs `tit` cannot run Tetravox — it is a host GPU application. So the job
 * writes its ROI plate with matplotlib the moment it starts (`tit/figures/roi_plate.py`), and drops
 * two files beside it: a `*.plate-request.json` saying what was drawn, and a `*.tetravox-job.json`
 * — the finished `--job` document, written by the same Python that decided the framing, so nothing
 * here has a second opinion about what the plate looks like.
 *
 * This module does exactly three things per request: map the document's absolute **container**
 * paths to host paths, run Tetravox offscreen, and let it overwrite the PNG in place. The scene
 * twin the document's `save-scene` writes lands beside it. If Tetravox is absent, or refuses, or
 * times out, the matplotlib plate that is already on disk stays and one line goes to the log — a
 * picture never fails a job, and it never blanks one either.
 */
import { readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { basename, dirname, join } from "node:path";
import { log } from "./log";

/** How long one plate may take. A 1600x1200 three-panel capture is ~8-10 s on a warm app. */
export const PLATE_TIMEOUT_MS = 120_000;

/** At most this many plates per job, so a 40-target batch cannot occupy the GPU for an hour. */
export const PLATE_LIMIT = 8;

export interface TetravoxJobDocument {
  scene?: { files?: string[] };
  actions?: unknown[];
}

export interface PlateRunnerDeps {
  /** Absolute container paths of everything the job produced. */
  artifactPaths(jobId: string): Promise<string[]>;
  /** A container path mapped into the host filesystem, or `null` when it does not map. */
  toHostPath(containerPath: string): Promise<string | null>;
  /** The resolved Tetravox executable, or `undefined` when there is none. */
  viewerExecutable(): Promise<string | undefined>;
  /** Run it. Resolves with the exit code; rejects only on a spawn failure. */
  run?(executable: string, args: string[]): Promise<number>;
  readFileText?(path: string): Promise<string>;
  writeFileText?(path: string, text: string): Promise<void>;
  logLine?(level: "info" | "warn", message: string): void;
}

const REQUEST_SUFFIX = ".plate-request.json";
const JOB_SUFFIX = ".tetravox-job.json";

/** The plate requests among a job's artifacts, de-duplicated and capped. */
export function plateRequests(paths: string[]): string[] {
  const seen = new Set<string>();
  for (const path of paths) {
    if (path.endsWith(REQUEST_SUFFIX)) seen.add(path);
  }
  return [...seen].sort().slice(0, PLATE_LIMIT);
}

/** The job document that belongs to a request, by construction of the Python side's names. */
export function jobDocumentFor(requestPath: string): string {
  return requestPath.slice(0, -REQUEST_SUFFIX.length) + JOB_SUFFIX;
}

/**
 * Every absolute path in *document* mapped to the host, or `null` when one of them does not map.
 *
 * All or nothing: a document with one unmapped dataset would render a plate missing a layer, which
 * is worse than the matplotlib plate it would have overwritten.
 */
export async function toHostDocument(
  document: TetravoxJobDocument,
  toHostPath: (path: string) => Promise<string | null>,
): Promise<TetravoxJobDocument | null> {
  const files = document.scene?.files ?? [];
  const mapped: string[] = [];
  for (const file of files) {
    const host = await toHostPath(file);
    if (!host) return null;
    mapped.push(host);
  }
  return { ...document, scene: { ...document.scene, files: mapped } };
}

function defaultRun(executable: string, args: string[]): Promise<number> {
  return new Promise((resolve, reject) => {
    // `--job` forces offscreen and is exempt from the single-instance lock, so this never takes
    // focus and never disturbs a window the user has open.
    const child = spawn(executable, args, { stdio: "ignore", windowsHide: true, detached: false });
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

/**
 * Render every ROI plate request a finished job left behind. Never throws.
 */
export async function renderPlatesForJob(jobId: string, deps: PlateRunnerDeps): Promise<PlateRunResult> {
  const say = deps.logLine ?? ((level: "info" | "warn", message: string) => log(level, message));
  const read = deps.readFileText ?? ((path: string) => readFile(path, "utf8"));
  const write = deps.writeFileText ?? ((path: string, text: string) => writeFile(path, text, "utf8"));
  const run = deps.run ?? defaultRun;
  const result: PlateRunResult = { rendered: [], skipped: [] };

  let requests: string[];
  try {
    requests = plateRequests(await deps.artifactPaths(jobId));
  } catch (error) {
    say("warn", `roi plates: could not list job ${jobId}'s artifacts: ${String(error)}`);
    return result;
  }
  if (!requests.length) return result;

  const executable = await deps.viewerExecutable();
  if (!executable) {
    say("info", `roi plates: no Tetravox on this machine; ${requests.length} plate(s) stay as drawn`);
    return { rendered: [], skipped: requests };
  }

  for (const request of requests) {
    const documentPath = await deps.toHostPath(jobDocumentFor(request));
    if (!documentPath) {
      result.skipped.push(request);
      say("warn", `roi plates: ${basename(request)} is outside the mounted project`);
      continue;
    }
    try {
      const document = JSON.parse(await read(documentPath)) as TetravoxJobDocument;
      const hosted = await toHostDocument(document, deps.toHostPath);
      if (!hosted) {
        result.skipped.push(request);
        say("warn", `roi plates: ${basename(request)} names a file outside the mounted project`);
        continue;
      }
      const outDir = dirname(documentPath);
      const hostedPath = join(outDir, basename(documentPath).replace(JOB_SUFFIX, ".tetravox-job.host.json"));
      await write(hostedPath, JSON.stringify(hosted, null, 1));
      const code = await run(executable, ["--job", hostedPath, "--out", outDir, "--quiet"]);
      if (code === 0) {
        result.rendered.push(request);
      } else {
        result.skipped.push(request);
        say("warn", `roi plates: Tetravox exited ${code} for ${basename(request)}; the drawn plate stands`);
      }
    } catch (error) {
      result.skipped.push(request);
      say("warn", `roi plates: ${basename(request)} could not be rendered: ${String(error)}`);
    }
  }
  if (result.rendered.length) {
    say("info", `roi plates: Tetravox redrew ${result.rendered.length} plate(s) for job ${jobId}`);
  }
  return result;
}

/** Desktop development opens the project home; --web and --host retain live reload. */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { DEV_ENV_EXAMPLE, DEV_ENV_FILE, DevConfigError, loadDevConfig, mergeDevEnv, parseDotenv } from "./devEnv";

const USAGE = `Usage: tsx scripts/dev.ts [--web] [--host] [--project PATH] [--down] [--force]

  With no flags, build and open the desktop project home. Choose a project in the app.
  Rerun after source changes; use --web for renderer live reload.

  --host   run the API on the host (Python dependencies required); no Docker
  --web    the renderer dev server only, no Electron window (http://127.0.0.1:5173/)
  --project PATH  prefill the desktop project path; select the project for --web/--host/--down
  --down   stop and remove this project's dev container, then exit
  --force  deprecated; running containers still require an explicit attach/replace choice

Web/host/container configuration comes from desktop/${DEV_ENV_FILE} (see ${DEV_ENV_EXAMPLE}); any of its variables can
be overridden for one run from the shell, e.g. TIT_DEV_PORT=8766 npm run dev:web.`;

/**
 * `src/main/stack.ts` reads `TIT_STACK_HEALTH_TIMEOUT_MS` once, at module load, so this default has
 * to be in place *before* that module is first reached. A static `import` of `./devStack` would be
 * hoisted above every statement here, so the import is dynamic and lives behind this function.
 */
async function loadDevStack(): Promise<typeof import("./devStack")> {
  process.env.TIT_STACK_HEALTH_TIMEOUT_MS ??= "180000";
  return import("./devStack");
}

/** Relay terminal signals and remove handlers between the build and Electron processes. */
async function runChild(bin: string, args: string[], cwd: string, env: NodeJS.ProcessEnv): Promise<number> {
  const child = spawn(bin, args, { cwd, env, stdio: "inherit" });
  const interrupt = (): void => { child.kill("SIGINT"); };
  const terminate = (): void => { child.kill("SIGTERM"); };
  process.on("SIGINT", interrupt);
  process.on("SIGTERM", terminate);
  try {
    return await new Promise<number>((settle) => {
      child.once("exit", (code, signal) => settle(signal === "SIGINT" ? 130 : signal ? 143 : (code ?? 1)));
      child.once("error", (err) => {
        console.error(`[dev] could not run ${bin}: ${err.message}`);
        settle(1);
      });
    });
  } finally {
    process.off("SIGINT", interrupt);
    process.off("SIGTERM", terminate);
  }
}

async function main(argv: string[]): Promise<number> {
  if (argv.includes("--help") || argv.includes("-h")) {
    console.log(USAGE);
    return 0;
  }
  const web = argv.includes("--web");
  const host = argv.includes("--host");
  const down = argv.includes("--down");
  const force = argv.includes("--force");

  const { DESKTOP_DIR, REPO_DIR, ensureDevStack, stopDevStack } = await loadDevStack();

  let projectDir: string | undefined;
  try {
    const projectIndex = argv.indexOf("--project");
    projectDir = projectIndex >= 0 ? argv[projectIndex + 1] : undefined;
    if (projectIndex >= 0 && (!projectDir || projectDir.startsWith("--"))) throw new DevConfigError("--project requires a BIDS project directory");
  } catch (err) {
    if (err instanceof DevConfigError) {
      console.error(`[dev] ${err.message}`);
      return 2;
    }
    throw err;
  }

  if (!web && !host && !down) {
    const env = { ...process.env };
    const envFile = join(DESKTOP_DIR, DEV_ENV_FILE);
    const defaults = mergeDevEnv(existsSync(envFile) ? parseDotenv(readFileSync(envFile, "utf8")) : {}, process.env);
    // Optional development defaults do not require a project to exist before the home screen opens.
    for (const key of ["TIT_DEV_IMAGE_TAG", "TIT_DEV_PORT", "TIT_DEV_PROJECT_DIR"]) {
      if (defaults[key]?.trim()) env[key] = defaults[key].trim();
    }
    // No inherited connection may bypass the welcome screen or bind the new project to an old session.
    for (const key of Object.keys(env)) {
      if (key.startsWith("TIT_LAUNCH_") || ["TIT_DEV_SERVER_URL", "TIT_DEV_SERVER_TOKEN", "ELECTRON_RENDERER_URL"].includes(key)) delete env[key];
    }
    env.TIT_DEV_LAUNCHER = "1";
    env.TIT_DEV_REPO_DIR = REPO_DIR;
    env.TIT_STATIC_DIR = "/ti-toolbox/desktop/out/renderer";
    const initialProjectDir = projectDir || env.TIT_DEV_PROJECT_DIR;
    if (initialProjectDir) env.TIT_DEV_PROJECT_DIR = resolve(DESKTOP_DIR, initialProjectDir);
    console.log("[dev] Building the desktop app. Select a project in Overview; rerun after source changes.");
    const buildCode = await runChild(join(DESKTOP_DIR, "node_modules", ".bin", "electron-vite"), ["build"], DESKTOP_DIR, env);
    if (buildCode !== 0) return buildCode;
    const exitCode = await runChild(join(DESKTOP_DIR, "node_modules", ".bin", "electron"), ["."], DESKTOP_DIR, env);
    if (exitCode === 0) console.log("[dev] TI-Toolbox closed.");
    return exitCode;
  }

  let config;
  try {
    config = loadDevConfig(DESKTOP_DIR, projectDir ? { ...process.env, TIT_DEV_PROJECT_DIR: projectDir } : process.env);
  } catch (err) {
    if (err instanceof DevConfigError) {
      console.error(`[dev] ${err.message}`);
      return 2;
    }
    throw err;
  }

  if (host && (down || force)) throw new DevConfigError("--host cannot be combined with --down or --force; Ctrl-C stops the host server.");

  if (down) {
    const { removed } = await stopDevStack(config);
    console.log(removed.length ? `[dev] stopped and removed ${removed.join(", ")}` : "[dev] nothing to stop for this project");
    return 0;
  }

  console.log(`[dev] project ${config.projectDir}`);
  const hostServer = host
    ? await (await import("./devHost")).startHostServer(REPO_DIR, config.projectDir, config.port)
    : undefined;
  const stack = hostServer ?? await ensureDevStack(config, { forceRecreate: force });
  if (hostServer) {
    process.once("exit", hostServer.stop);
    for (const signal of ["SIGINT", "SIGTERM"] as const) {
      process.once(signal, () => { hostServer.stop(); process.exit(0); });
    }
  }
  console.log(`[dev] ${stack.attached ? "attached to" : "started"} ${stack.origin}`);

  // The token reaches Vite and Electron here and nowhere else: not on the command line (where `ps`
  // would show it), not in a file, not on the terminal. `electron.vite.config.ts` reads these at
  // config-load time, which for `--web` happens in *this* process, so they go on `process.env`
  // rather than only into the child's environment.
  if ("containerId" in stack && stack.containerId) process.env.TIT_LAUNCH_CONTAINER_ID = stack.containerId;
  process.env.TIT_DEV_SERVER_URL = stack.origin;
  process.env.TIT_DEV_SERVER_TOKEN = stack.token;
  process.env.TIT_DEV_PROJECT_DIR = config.projectDir;

  if (web) {
    // In-process, and no Electron: see scripts/devWeb.ts for why `--rendererOnly` is not that.
    const { runRendererDevServer } = await import("./devWeb");
    await runRendererDevServer(DESKTOP_DIR);
    // The Vite server keeps the event loop alive; Ctrl-C ends it.
    return await new Promise<number>(() => {});
  }

  const bin = join(DESKTOP_DIR, "node_modules", ".bin", "electron-vite");
  const args = ["dev"];
  console.log(`[dev] electron-vite ${args.join(" ")}`);

  const child = spawn(bin, args, { cwd: DESKTOP_DIR, env: process.env, stdio: "inherit" });
  // Ctrl-C in a terminal already reaches the whole process group; forwarding explicitly means the
  // child still gets its chance to shut Vite down cleanly when this process alone is signalled.
  for (const signal of ["SIGINT", "SIGTERM"] as const) {
    process.on(signal, () => child.kill(signal));
  }
  const exitCode = await new Promise<number>((settle) => {
    child.on("exit", (code, signal) => settle(signal ? 0 : (code ?? 1)));
    child.on("error", (err) => {
      console.error(`[dev] could not run ${bin}: ${err.message}`);
      settle(1);
    });
  });
  hostServer?.stop();
  return exitCode;
}

void main(process.argv.slice(2)).then(
  (code) => {
    if (code !== 0) process.exitCode = code;
  },
  (err: unknown) => {
    console.error(`[dev] ${err instanceof Error ? err.message : String(err)}`);
    process.exitCode = 1;
  },
);

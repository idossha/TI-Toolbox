/**
 * `npm run dev` — the whole system, from one command (P1, `docs/dev/HISTORY.md § 2026-09-03 (pipelines program)` §2).
 *
 *   npm run dev        container (attach / recreate / start) → Vite → Electron, already connected
 *   npm run dev:web    the same without Electron; open http://127.0.0.1:5173/
 *   npm run dev:down   stop and remove this project's container
 *
 * What it replaces: a hand-written `docker run` with eight flags and four labels, `docker inspect`
 * to read the token out of the container, `TIT_DEV_ORIGINS=<vite origin>` exported on the server so
 * the CSRF check would accept the tab, and `/auth/session?token=…` pasted into the address bar
 * after every restart. None of those steps is in the loop any more, and the developer never sees
 * the token: it is recovered from the container, handed to Vite and Electron in the child
 * environment, and stamped onto every proxied request as a bearer header (`scripts/devProxy.ts`).
 *
 * Ctrl-C stops Vite and Electron and leaves the container running, so the next `npm run dev`
 * attaches in a second or two. `npm run dev:down` is the one that stops it.
 */
import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { join } from "node:path";
import { DEV_ENV_EXAMPLE, DEV_ENV_FILE, DevConfigError, loadDevConfig } from "./devEnv";

const USAGE = `Usage: tsx scripts/dev.ts [--web] [--down] [--force]

  --web    the renderer dev server only, no Electron window (http://127.0.0.1:5173/)
  --down   stop and remove this project's dev container, then exit
  --force  recreate a mismatched container even if it has jobs in flight (they are killed)

Configuration comes from desktop/${DEV_ENV_FILE} (see ${DEV_ENV_EXAMPLE}); any of its variables can
be overridden for one run from the shell, e.g. TIT_DEV_PORT=8766 npm run dev.`;

/**
 * `src/main/stack.ts` reads `TIT_STACK_HEALTH_TIMEOUT_MS` once, at module load, so this default has
 * to be in place *before* that module is first reached. A static `import` of `./devStack` would be
 * hoisted above every statement here, so the import is dynamic and lives behind this function.
 */
async function loadDevStack(): Promise<typeof import("./devStack")> {
  process.env.TIT_STACK_HEALTH_TIMEOUT_MS ??= "180000";
  return import("./devStack");
}

async function main(argv: string[]): Promise<number> {
  if (argv.includes("--help") || argv.includes("-h")) {
    console.log(USAGE);
    return 0;
  }
  const web = argv.includes("--web");
  const down = argv.includes("--down");
  const force = argv.includes("--force");

  const { DESKTOP_DIR, REPO_DIR, ensureDevStack, stopDevStack } = await loadDevStack();

  let config;
  try {
    config = loadDevConfig(DESKTOP_DIR);
  } catch (err) {
    if (err instanceof DevConfigError) {
      console.error(`[dev] ${err.message}`);
      return 2;
    }
    throw err;
  }

  if (down) {
    const { removed } = await stopDevStack(config);
    console.log(removed.length ? `[dev] stopped and removed ${removed.join(", ")}` : "[dev] nothing to stop for this project");
    return 0;
  }

  console.log(`[dev] project   ${config.projectDir}`);
  console.log(`[dev] image     idossha/ti-toolbox:${config.imageTag}`);
  console.log(`[dev] port      ${config.port}`);
  console.log(`[dev] repo      ${config.mountRepo ? `${REPO_DIR} -> /ti-toolbox (server runs with --reload)` : "not mounted (the image's own tit)"}`);

  // The container's own UI bundle is the one baked into the image (`--static-dir /opt/ti-toolbox/ui`),
  // which is whatever the last image build carried — not what this worktree has built. Anything that
  // loads the page from the SERVER's origin rather than from Vite therefore tests stale renderer code:
  // that is every `--project=real` Playwright run (the built Electron app has no ELECTRON_RENDERER_URL,
  // so `connect()` loads `<server origin>/auth/session`), and it cost lane S2 a `docker cp` to work
  // around. With the worktree mounted at /ti-toolbox the live bundle is already inside the container,
  // so point the server at it — but only when it exists, since a missing --static-dir serves the
  // "no UI bundle" fallback page to anyone who opens the port directly.
  if (config.mountRepo && existsSync(join(DESKTOP_DIR, "out", "renderer", "index.html"))) {
    process.env.TIT_STATIC_DIR ??= "/ti-toolbox/desktop/out/renderer";
    console.log(`[dev] static    ${process.env.TIT_STATIC_DIR} (this worktree's npm run build output)`);
  }

  const stack = await ensureDevStack(config, { forceRecreate: force });
  console.log(`[dev] ${stack.attached ? "attached to" : "started"} ${stack.origin}`);

  // The token reaches Vite and Electron here and nowhere else: not on the command line (where `ps`
  // would show it), not in a file, not on the terminal. `electron.vite.config.ts` reads these at
  // config-load time, which for `--web` happens in *this* process, so they go on `process.env`
  // rather than only into the child's environment.
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
  return await new Promise<number>((settle) => {
    child.on("exit", (code, signal) => settle(signal ? 0 : (code ?? 1)));
    child.on("error", (err) => {
      console.error(`[dev] could not run ${bin}: ${err.message}`);
      settle(1);
    });
  });
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

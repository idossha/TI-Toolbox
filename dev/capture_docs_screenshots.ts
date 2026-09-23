/**
 * Re-take the documentation website's app screenshots from the real app on a real project.
 *
 *   cd desktop && TIT_DEV_IMAGE_TAG=v3.0.1 npx tsx ../dev/capture_docs_screenshots.ts [--project DIR] [-g TITLE]
 *
 * 1. Starts (or attaches to) the dev container for the project, exactly as `npm run dev` does
 *    (desktop/.env.dev and TIT_DEV_* apply), and keeps its token in this process only.
 * 2. Builds the app with scene hooks, runs `tests/e2e/real/docs-shots.spec.ts` offscreen under
 *    /tmp/tit-e2e.lock, then restores the plain build (the dev container serves desktop/out).
 * 3. Stops the container only if this run started it.
 *
 * The spec writes PNGs into docs/assets/imgs/v3/ at the window's own scale; downscale anything
 * wider than 1600 px with `sips --resampleWidth 1600` before committing. Extra arguments (e.g.
 * `-g "Settings"`) are passed to Playwright to re-take a subset.
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { loadDevConfig } from "../desktop/scripts/devEnv";
import { DESKTOP_DIR, ensureDevStack, stopDevStack } from "../desktop/scripts/devStack";

function run(cmd: string[], env: NodeJS.ProcessEnv = process.env): number {
  const res = spawnSync(cmd[0], cmd.slice(1), { cwd: DESKTOP_DIR, env, stdio: "inherit" });
  return res.status ?? 1;
}

async function main(argv: string[]): Promise<number> {
  const i = argv.indexOf("--project");
  const shell = i >= 0 ? { ...process.env, TIT_DEV_PROJECT_DIR: argv[i + 1] } : process.env;
  const extra = i >= 0 ? [...argv.slice(0, i), ...argv.slice(i + 2)] : argv;
  const config = loadDevConfig(DESKTOP_DIR, shell);
  const stack = await ensureDevStack(config);
  const bin = (name: string) => join(DESKTOP_DIR, "node_modules", ".bin", name);
  // Nonblocking, like dev/verify_release.py: a held lock means another lane is mid-run.
  const lock = existsSync("/usr/bin/flock") ? ["flock", "-n"] : ["lockf", "-t", "0"];
  let code = 1;
  try {
    code = run([bin("electron-vite"), "build"], { ...process.env, VITE_SCENE_HOOKS: "1" });
    if (code === 0) {
      code = run(
        [...lock, "/tmp/tit-e2e.lock", bin("playwright"), "test", "--project=real", "tests/e2e/real/docs-shots.spec.ts", ...extra],
        {
          ...process.env,
          TIT_E2E_SERVER_URL: stack.origin,
          TIT_E2E_TOKEN: stack.token,
          TIT_E2E_PROJECT_HOST: config.projectDir,
          TIT_E2E_OFFSCREEN: "1",
        },
      );
    }
  } finally {
    run([bin("electron-vite"), "build"]);
    if (!stack.attached) await stopDevStack(config);
  }
  return code;
}

void main(process.argv.slice(2)).then(
  (code) => process.exit(code),
  (err: unknown) => {
    console.error(`[docs-shots] ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  },
);

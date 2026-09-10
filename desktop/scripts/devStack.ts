/** Docker development uses the same explicit attach/replace selection as the desktop app. */
import { createInterface } from "node:readline/promises";
import { join, resolve } from "node:path";
import { LABEL_HOST_DIR, LABEL_PROJECT, computeProjectName } from "../src/shared/compose";
import { discover } from "../src/main/docker/discover";
import { DockerEngineClient, DockerEngineError } from "../src/main/docker/engine";
import { StackApi } from "../src/main/docker/stackApi";
import { createStackManager, sameHostDir, type StackEvent, type StackHost } from "../src/main/stack";
import type { DevConfig } from "./devEnv";

/**
 * `desktop/` — the Node host's `appPath`; the run spec is the root `docker-compose.yml` one
 * level up, which `src/main/stack.ts#resolveComposeFile` finds from it.
 * `__dirname`, not `import.meta.url`: `desktop/package.json` has no `"type": "module"`, so tsx
 * runs these scripts as CommonJS and `import.meta` is not available in them.
 */
export const DESKTOP_DIR = resolve(__dirname, "..");
/** The repository worktree, bind-mounted at `/ti-toolbox` when `TIT_DEV_MOUNT_REPO=1`. */
export const REPO_DIR = resolve(DESKTOP_DIR, "..");

/**
 * How long a freshly created dev container gets to answer `/api/health`. Read by `src/main/stack.ts`
 * at module load from `TIT_STACK_HEALTH_TIMEOUT_MS`, which is why `dev.ts` sets the default before
 * it imports this file: the manager's own 120 s is short for a cold emulated amd64 start plus the
 * compose healthcheck's 20 s `start_period`, and a timeout at 2 minutes for a container that comes
 * up at 2m10s reports the wrong cause.
 */
export const DEV_HEALTH_TIMEOUT_MS = 180_000;

/**
 * `/api/health` polling on plain Node — the Electron host uses `net.fetch` for the same job.
 * Same shape as `src/main/health.ts`: poll until `{status:"ok"}`, and report the last failure in
 * the timeout message, because "did not answer" without the reason is unactionable.
 */
export async function waitForHealth(origin: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError = "no response";
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${origin}/api/health`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) {
        const body = (await res.json()) as { status?: string };
        if (body.status === "ok") return;
        lastError = `health status ${String(body.status)}`;
      } else {
        lastError = `HTTP ${res.status}`;
      }
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Server at ${origin} did not answer /api/health within ${timeoutMs / 1000}s (${lastError})`);
}

/**
 * The Node half of the injected host. `log` prints only warnings and errors: every `info` line the
 * manager logs is also emitted as a `progress` event, which `ensureDevStack` prints — logging both
 * would double every line of the start-up transcript.
 */
export const nodeStackHost: StackHost = {
  async chooseRunningContainer(containers) {
    const action = process.env.TIT_LAUNCH_EXISTING;
    const selector = process.env.TIT_LAUNCH_CONTAINER;
    if (action) {
      if (!["attach", "recreate"].includes(action)) throw new Error("TIT_LAUNCH_EXISTING must be attach or recreate.");
      const matches = selector ? containers.filter((c) => c.Id === selector || c.Names.some((name) => name.replace(/^\//, "") === selector)) : containers;
      if (matches.length !== 1) throw new Error("Select exactly one running container with TIT_LAUNCH_CONTAINER.");
      return { action: action === "attach" ? "attach" : "replace", containerId: matches[0]!.Id };
    }
    if (!process.stdin.isTTY) throw new Error("A running TI-Toolbox container requires an interactive attach/replace choice.");
    const prompt = createInterface({ input: process.stdin, output: process.stdout });
    try {
      console.log("\nRunning TI-Toolbox containers");
      containers.forEach((c, i) => console.log(`  ${i + 1}. ${c.Image}`));
      const selected = containers.length === 1 ? 0 : Number(await prompt.question("Select container number: ")) - 1;
      const container = containers[selected];
      if (!container) return null;
      console.log("\nAvailable actions\n-----------------\n  1. Recreate (default)\n  2. Attach\n\nRecreate stops this container and its jobs.");
      const answer = (await prompt.question("Choose [1]: ")).trim().toLowerCase();
      if (["", "1", "r", "recreate"].includes(answer)) return { action: "replace", containerId: container.Id };
      if (["2", "a", "attach"].includes(answer)) return { action: "attach", containerId: container.Id };
      return null;
    } finally { prompt.close(); }
  },
  isPackaged: false,
  appPath: DESKTOP_DIR,
  resourcesPath: undefined,
  log(level, message) {
    if (level !== "info") console.error(`[dev] ${level}: ${message}`);
  },
  waitForHealth,
  async fetchJson(url, headers) {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`GET ${url} failed with HTTP ${res.status}`);
    return (await res.json()) as unknown;
  },
};

export interface DevStackResult {
  containerId?: string;
  origin: string;
  token: string;
  attached: boolean;
}

/** Return credentials and ownership for the explicitly selected or freshly created dev container. */
export async function ensureDevStack(config: DevConfig, options: { forceRecreate?: boolean } = {}): Promise<DevStackResult> {
  const stack = createStackManager(nodeStackHost);
  const off = stack.onEvent((event: StackEvent) => {
    if (event.type === "progress") console.log(`[dev] ${event.message}`);
    if (event.type === "error") console.error(`[dev] ${event.message}`);
  });
  try {
    const result = await stack.start(config.projectDir, {
      preferredPort: config.port,
      imageTag: config.imageTag,
      repoDir: config.mountRepo ? REPO_DIR : undefined,
      serverReload: config.mountRepo,
      // Keep the selected UI independent of build timing and stray shell settings.
      staticDir: config.mountRepo ? "/ti-toolbox/desktop/out/renderer" : "/opt/ti-toolbox/ui",
      requireMatch: true,
      forceRecreate: options.forceRecreate ?? false,
    });
    if (!result.ok) throw new Error(result.error);
    // TIT_DEV_PORT is where `findFreePort` starts, not a guarantee: another process (or another
    // checkout's container) may already hold it. Say so rather than letting the developer wonder
    // why their configured port is not the one in the printed URL.
    const actual = Number(new URL(result.url).port);
    if (actual !== config.port) console.log(`[dev] port ${config.port} was taken; the container publishes ${actual}`);
    return { origin: result.url, token: result.token, attached: result.attached, containerId: stack.getCurrent()?.containerId };
  } finally {
    off();
  }
}

export interface DevStackDownResult {
  /** Container names that were stopped and removed; empty means there was nothing to stop. */
  removed: string[];
}

/**
 * `npm run dev:down` — stop and remove this project's container.
 *
 * By label, not by anything this process remembers, so it works from a fresh shell. Both labels
 * are checked for the same reason attach does (`decideAttach`): `tit.project` is a 32-bit hash, so
 * matching on it alone could remove another directory's stack.
 */
export async function stopDevStack(config: DevConfig): Promise<DevStackDownResult> {
  const found = await discover();
  if (!found.available) throw new Error(found.message);
  const client = new DockerEngineClient(found.connection);
  const version = await client.version();
  const api = new StackApi(found.connection, version.ApiVersion);
  const projectName = computeProjectName(config.projectDir);
  const containers = await api.listContainers({ [LABEL_PROJECT]: projectName });
  const removed: string[] = [];
  for (const container of containers) {
    if (!sameHostDir(container.Labels?.[LABEL_HOST_DIR], config.projectDir)) continue;
    const name = container.Names[0]?.replace(/^\//, "") ?? container.Id.slice(0, 12);
    try {
      if (container.State === "running") await client.stopContainer(container.Id, 10);
      await client.removeContainer(container.Id, { volumes: false });
      removed.push(name);
    } catch (err) {
      // Already gone is the state this function exists to reach, not a failure.
      if (!(err instanceof DockerEngineError && err.kind === "not-found")) throw err;
      removed.push(name);
    }
  }
  return { removed };
}

/** The root `docker-compose.yml`, for the message that names what dev will realise. */
export const COMPOSE_FILE = join(REPO_DIR, "docker-compose.yml");

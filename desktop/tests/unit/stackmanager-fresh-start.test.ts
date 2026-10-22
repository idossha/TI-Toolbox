/**
 * `StackManager.start/stop/status` realise the shipped root `docker-compose.yml` exactly, through a
 * fake Docker Engine API on a real Unix socket (`tests/e2e/fixtures/fake-engine-api.mjs`) — the
 * same fake `tests/e2e/launcher.spec.ts` drives, but here under vitest, so the contract runs in
 * CI's desktop job (which runs vitest and no Playwright).
 *
 * Where the expected values come from (never from `stack.ts` itself):
 * - the root `docker-compose.yml` (`services.tit`: the four volumes, the environment block, the
 *   `127.0.0.1:${TIT_SERVER_PORT}` publish, `platform: linux/amd64`), read here as text;
 * - the label set every launcher stamps (`tests/fixtures/launch_contract.json`, `labels`);
 * - `buildStackEnv`'s documented rule that `TIT_REPO_DIR`/`TIT_SERVER_RELOAD` are always present
 *   and empty unless this app asks for them (a packaged app never does);
 * - `node:path` (`basename`, `join`) as the reader of the host directory, and `index.ts`'s
 *   `knownProjectRoots` rule (`/mnt/<name>` of the started stack) for the host-path mapping;
 * - `stack.ts`'s own file doc: "Closing Electron stops its selected stack" — stop() stops and
 *   removes exactly that container and nothing a launcher did not label.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/stackmanager-fresh-start.test.ts`.
 */
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DockerEngineClient } from "../../src/main/docker/engine";
import { StackApi } from "../../src/main/docker/stackApi";
import { StackManager, type StackHost } from "../../src/main/stack";
import { containerToHostPath, projectDirName, type HostPlatform } from "../../src/shared/paths";
import { startFakeEngineApi, type FakeEngineApi, type FakeEngineApiContainer } from "../e2e/fixtures/fake-engine-api.mjs";

const REPO = join(__dirname, "..", "..", "..");
const COMPOSE_TEXT = readFileSync(join(REPO, "docker-compose.yml"), "utf8");
/** The release image the shipped compose file names by default (`image: ...:${TIT_IMAGE_TAG:-<tag>}`). */
const RELEASE_IMAGE = (() => {
  const match = /image:\s*(\S+):\$\{TIT_IMAGE_TAG:-([^}]+)\}/.exec(COMPOSE_TEXT);
  if (!match) throw new Error("docker-compose.yml no longer names its image as <name>:${TIT_IMAGE_TAG:-<tag>}");
  return { name: match[1]!, tag: match[2]!, ref: `${match[1]}:${match[2]}` };
})();
const CONTRACT = JSON.parse(readFileSync(join(REPO, "tests", "fixtures", "launch_contract.json"), "utf8")) as {
  cases: { expected: { labels: Record<string, string> } }[];
};
const LABEL_KEYS = Object.keys(CONTRACT.cases[0]!.expected.labels).sort();

let fake: FakeEngineApi;

/**
 * Where the free-port search starts. The packaged app passes no options (8765 upwards); a random
 * base keeps parallel vitest workers, whose fake servers really listen, from racing for 8765.
 */
function startOptions(): { preferredPort: number } {
  return { preferredPort: 20000 + Math.floor(Math.random() * 30000) };
}

/** Container stop/remove/create/start requests answered since `index` (reads such as a late log follow are not actions). */
function containerMutationsSince(index: number): string[] {
  return fake.requests.slice(index).filter((r) => /^(POST|DELETE) \/containers\//.test(r));
}
let root: string;
let home: string;

/** A plain fetch poll, standing in for Electron's `net`-based `waitForHealth`. */
async function pollHealth(origin: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${origin}/api/health`);
      if (res.ok && ((await res.json()) as { status?: string }).status === "ok") return;
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 25));
  }
  throw new Error(`no health from ${origin}`);
}

function host(): StackHost {
  return { isPackaged: true, appPath: join(REPO, "desktop"), log: () => {}, waitForHealth: pollHealth, fetchJson: async () => ({}) };
}

function envOf(container: FakeEngineApiContainer): Record<string, string> {
  return Object.fromEntries(container.Env.map((entry) => [entry.slice(0, entry.indexOf("=")), entry.slice(entry.indexOf("=") + 1)]));
}

function binds(container: FakeEngineApiContainer): string[] {
  return (container.HostConfig?.Binds as string[] | undefined) ?? [];
}

/** The one stack container (GPU probes are created and removed during start). */
function stackContainer(): FakeEngineApiContainer {
  const stacks = [...fake.containers.values()].filter((c) => c.Labels["tit.stack"] !== undefined);
  expect(stacks).toHaveLength(1);
  return stacks[0]!;
}

beforeEach(async () => {
  root = mkdtempSync(join(tmpdir(), "tit-fresh-start-"));
  home = join(root, "home");
  mkdirSync(home);
  fake = await startFakeEngineApi({ autoExit: false, serveTitServer: true, images: [RELEASE_IMAGE.ref] });
  vi.stubEnv("DOCKER_HOST", `unix://${fake.socketPath}`);
  vi.stubEnv("HOME", home);
  // Everything a developer's or user's shell might carry that the compose file interpolates.
  for (const name of ["XDG_CONFIG_HOME", "TIT_COMPOSE_FILE", "TIT_IMAGE_TAG", "TIT_STATIC_DIR", "TIT_DEV_REPO_DIR", "TIT_REPO_DIR", "TIT_SERVER_RELOAD", "TIT_NO_TELEMETRY", "TIT_LAUNCH_EXISTING", "TIT_LAUNCH_CONTAINER", "TIT_STACK_HEALTH_TIMEOUT_MS", "TIT_LAUNCH_TIMEOUT", "TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS"]) {
    vi.stubEnv(name, "");
  }
});

afterEach(async () => {
  vi.unstubAllEnvs();
  // A running container's followed log stream would otherwise hold the socket server open.
  fake.server.closeAllConnections();
  await fake.close();
  rmSync(root, { recursive: true, force: true });
});

describe("a packaged fresh start realises docker-compose.yml", () => {
  it("creates one container whose env, binds, labels, platform and port are the compose file's", async () => {
    const dir = join(root, "project");
    mkdirSync(dir);
    const manager = new StackManager(host());
    const result = await manager.start(dir, startOptions());
    expect(result).toMatchObject({ ok: true, attached: false });
    if (!result.ok) return;
    const port = Number(new URL(result.url).port);
    expect(new URL(result.url).hostname).toBe("127.0.0.1");

    const container = stackContainer();
    const env = envOf(container);
    expect(env.TIT_SERVER_TOKEN).toBe(result.token);
    expect(env.TIT_SERVER_PORT).toBe(String(port));
    expect(env.LOCAL_PROJECT_DIR).toBe(dir);
    expect(env.PROJECT_DIR_NAME).toBe(basename(dir));
    // Packaged: no dev mount, no reload, the image's own UI bundle.
    expect(env.TIT_REPO_DIR).toBe("");
    expect(env.TIT_SERVER_RELOAD).toBe("");
    expect(env.TIT_STATIC_DIR).toBe("");

    // Three of the compose file's four volumes; the fourth (`${TIT_REPO_DIR:-}:/ti-toolbox`) is
    // dropped because its source is empty.
    expect(binds(container).sort()).toEqual(
      [`${dir}:/mnt/${basename(dir)}`, `${join(home, ".config", "ti-toolbox")}:/root/.config/ti-toolbox`, "/var/run/docker.sock:/var/run/docker.sock"].sort(),
    );

    expect(Object.keys(container.Labels).sort()).toEqual(LABEL_KEYS);
    expect(container.Labels["tit.stack"]).toBe("ti-toolbox-v3");
    expect(container.Labels["tit.service"]).toBe("tit");
    expect(container.Labels["tit.host_project_dir"]).toBe(dir);
    expect(container.Labels["tit.project"]).toMatch(/^ti-toolbox-[0-9a-f]{8}$/);
    // Compose's own container name rule: <project>-<service>-1.
    expect(container.Name).toBe(`${container.Labels["tit.project"]}-tit-1`);
    expect(container.Platform).toBe("linux/amd64");
    expect(container.HostConfig?.PortBindings).toEqual({ [`${port}/tcp`]: [{ HostIp: "127.0.0.1", HostPort: String(port) }] });
    expect(container.running).toBe(true);

    // The release tag is mutable, so a packaged start refreshes it (for the compose file's own
    // platform) even though it is cached; the refresh is the only pull.
    expect(fake.pulls).toEqual([{ image: RELEASE_IMAGE.name, tag: RELEASE_IMAGE.tag, platform: "linux/amd64" }]);

    const status = await manager.status();
    expect(status).toMatchObject({ running: true, hostProjectDir: dir, port, containerName: container.Name, image: RELEASE_IMAGE.ref });
  });

  it("a cached non-release image is not pulled again", async () => {
    vi.stubEnv("TIT_IMAGE_TAG", "fixture-local");
    await fake.close();
    fake = await startFakeEngineApi({ autoExit: false, serveTitServer: true, images: [`${RELEASE_IMAGE.name}:fixture-local`] });
    vi.stubEnv("DOCKER_HOST", `unix://${fake.socketPath}`);
    const dir = join(root, "project");
    mkdirSync(dir);
    expect(await new StackManager(host()).start(dir, startOptions())).toMatchObject({ ok: true });
    expect(fake.pulls).toEqual([]);
    expect(stackContainer().Image).toBe(`${RELEASE_IMAGE.name}:fixture-local`);
  });

  it("a hostile host environment cannot mount a checkout or turn on reload in a packaged app", async () => {
    vi.stubEnv("TIT_REPO_DIR", "/evil");
    vi.stubEnv("TIT_DEV_REPO_DIR", "/evil-dev");
    vi.stubEnv("TIT_SERVER_RELOAD", "1");
    const dir = join(root, "project");
    mkdirSync(dir);
    expect(await new StackManager(host()).start(dir, startOptions())).toMatchObject({ ok: true });
    const container = stackContainer();
    expect(binds(container).filter((bind) => bind.endsWith(":/ti-toolbox") || bind.includes("evil"))).toEqual([]);
    expect(envOf(container).TIT_SERVER_RELOAD).toBe("");
    expect(envOf(container).TIT_REPO_DIR).toBe("");
  });

  it("the host's telemetry opt-out reaches the container", async () => {
    vi.stubEnv("TIT_NO_TELEMETRY", "1");
    const dir = join(root, "project");
    mkdirSync(dir);
    expect(await new StackManager(host()).start(dir, startOptions())).toMatchObject({ ok: true });
    expect(envOf(stackContainer()).TIT_NO_TELEMETRY).toBe("1");
  });
});

describe("host directory names", () => {
  it("a directory with spaces and non-ASCII letters is mounted where the host-path mapping looks for it", async () => {
    const dir = join(root, "My Données 数据");
    mkdirSync(dir);
    const manager = new StackManager(host());
    expect(await manager.start(dir, startOptions())).toMatchObject({ ok: true });
    const projectBind = binds(stackContainer()).find((bind) => bind.startsWith(`${dir}:`));
    expect(projectBind).toBe(`${dir}:/mnt/My Données 数据`);
    // index.ts knownProjectRoots: the started stack's container root is /mnt/<name of its host dir>.
    const containerRoot = projectBind!.slice(dir.length + 1);
    const platform = (process.platform === "darwin" || process.platform === "win32" ? process.platform : "linux") as HostPlatform;
    expect(`/mnt/${projectDirName(manager.getCurrent()!.hostProjectDir)}`).toBe(containerRoot);
    expect(containerToHostPath(`${containerRoot}/derivatives/x`, containerRoot, dir, platform)).toBe(join(dir, "derivatives", "x"));
  });

  it("a directory containing ':' is refused with a message naming it, before any container exists", async () => {
    const dir = join(root, "a:b");
    mkdirSync(dir);
    const result = await new StackManager(host()).start(dir, startOptions());
    expect(result).toMatchObject({ ok: false });
    expect(result.ok ? "" : result.error).toContain(dir);
    expect(fake.containers.size).toBe(0);
    expect(fake.requests.filter((r) => r.startsWith("POST /containers/create"))).toEqual([]);
  });
});

describe("stop", () => {
  it("stops and removes exactly the container it started, never an unlabelled scratch container", async () => {
    // A user's own `docker run` of the image, running before the app starts.
    const api = new StackApi({ kind: "unix", socketPath: fake.socketPath }, "1.51");
    const scratch = await api.createContainer({ Image: RELEASE_IMAGE.ref, Env: [], Labels: {}, ExposedPorts: {}, HostConfig: { Binds: [], PortBindings: {} } }, { name: "eager_turing" });
    await new DockerEngineClient({ kind: "unix", socketPath: fake.socketPath }).startContainer(scratch.Id);

    const dir = join(root, "project");
    mkdirSync(dir);
    const manager = new StackManager(host());
    expect(await manager.start(dir, startOptions())).toMatchObject({ ok: true, attached: false });
    const id = stackContainer().Id;

    const before = fake.requests.length;
    expect(await manager.stop()).toEqual({ ok: true });
    expect(containerMutationsSince(before)).toEqual([`POST /containers/${id}/stop`, `DELETE /containers/${id}`]);
    expect(fake.containers.has(id)).toBe(false);
    expect(fake.containers.get(scratch.Id)?.running).toBe(true);
    expect(await manager.status()).toEqual({ running: false });
  });
});

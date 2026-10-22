/**
 * A container this process created is owned from the moment it exists, not from the moment its
 * server first answers. `stack.ts`'s file doc is the spec: "Closing Electron stops its selected
 * stack". Two ways a start used to leave a running container nobody would stop:
 *
 * - its health wait gave up (a slow cold amd64 boot): `start()` failed, the container kept running
 *   and `stop()` — the quit path's only Docker call — had nothing to stop;
 * - the app was closed while the launcher said "Waiting for the server to answer…": the quit plan
 *   decided "no Docker stack" from `getCurrent()`, which is set only after health.
 *
 * Driven against the fake Docker Engine API on a real Unix socket
 * (`tests/e2e/fixtures/fake-engine-api.mjs`) with the shipped root `docker-compose.yml`; expected
 * requests are the Engine API's own stop/remove routes. No Docker, no Electron.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/stack-orphan-container.test.ts`.
 */
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StackManager, type StackHost } from "../../src/main/stack";
import { startFakeEngineApi, type FakeEngineApi, type FakeEngineApiContainer } from "../e2e/fixtures/fake-engine-api.mjs";

const REPO = join(__dirname, "..", "..", "..");

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
let dir: string;

function stackContainers(): FakeEngineApiContainer[] {
  return [...fake.containers.values()].filter((c) => c.Labels["tit.stack"] !== undefined);
}

function host(waitForHealth: StackHost["waitForHealth"]): StackHost {
  return { isPackaged: true, appPath: join(REPO, "desktop"), log: () => {}, waitForHealth, fetchJson: async () => ({}) };
}

beforeEach(async () => {
  root = mkdtempSync(join(tmpdir(), "tit-orphan-"));
  dir = join(root, "project");
  mkdirSync(dir);
  mkdirSync(join(root, "home"));
  // The fake tit server is off: nothing ever answers /api/health, like a container still booting.
  fake = await startFakeEngineApi({ autoExit: false, serveTitServer: false, images: ["idossha/ti-toolbox:v3.1.1"] });
  vi.stubEnv("DOCKER_HOST", `unix://${fake.socketPath}`);
  vi.stubEnv("HOME", join(root, "home"));
  for (const name of ["XDG_CONFIG_HOME", "TIT_COMPOSE_FILE", "TIT_IMAGE_TAG", "TIT_STATIC_DIR", "TIT_DEV_REPO_DIR", "TIT_REPO_DIR", "TIT_SERVER_RELOAD", "TIT_LAUNCH_EXISTING", "TIT_LAUNCH_CONTAINER", "TIT_LAUNCH_TIMEOUT", "TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS"]) {
    vi.stubEnv(name, "");
  }
});

afterEach(async () => {
  vi.unstubAllEnvs();
  fake.server.closeAllConnections();
  await fake.close();
  rmSync(root, { recursive: true, force: true });
});

describe("a start whose health wait fails", () => {
  it("keeps the running container owned, so stop() (and quitting) stops and removes it", async () => {
    vi.stubEnv("TIT_STACK_HEALTH_TIMEOUT_MS", "200");
    const manager = new StackManager(host(async () => { throw new Error("no answer"); }));

    const result = await manager.start(dir, startOptions());
    expect(result).toMatchObject({ ok: false, error: expect.stringContaining("never answered") });
    const [container] = stackContainers();
    expect(container?.running).toBe(true);
    // Not a session to connect to, but still this app's container.
    expect(manager.getCurrent()).toBeNull();
    expect(manager.ownsContainer()).toBe(true);

    const before = fake.requests.length;
    expect(await manager.stop()).toEqual({ ok: true });
    expect(containerMutationsSince(before)).toEqual([`POST /containers/${container!.Id}/stop`, `DELETE /containers/${container!.Id}`]);
    expect(stackContainers()).toEqual([]);
    expect(manager.ownsContainer()).toBe(false);
  });
});

describe("stop() while start() waits for the server", () => {
  it("stops and removes the container being started, and that start ends as stopped", async () => {
    // Health that would take far longer than this test may run: only stop() can end the start.
    vi.stubEnv("TIT_STACK_HEALTH_TIMEOUT_MS", "60000");
    let healthAsked!: () => void;
    const asked = new Promise<void>((resolve) => { healthAsked = resolve; });
    const manager = new StackManager(host((_origin, timeoutMs) => {
      healthAsked();
      return new Promise((_resolve, reject) => setTimeout(() => reject(new Error("no answer")), timeoutMs).unref());
    }));
    expect(manager.ownsContainer()).toBe(false);

    const starting = manager.start(dir, startOptions());
    await asked; // the launcher now says "Waiting for the server to answer…"
    const [container] = stackContainers();
    expect(container?.running).toBe(true);
    expect(manager.ownsContainer()).toBe(true);

    expect(await manager.stop()).toEqual({ ok: true });
    expect(fake.requests).toContain(`POST /containers/${container!.Id}/stop`);
    expect(fake.requests).toContain(`DELETE /containers/${container!.Id}`);
    expect(stackContainers()).toEqual([]);

    const result = await starting;
    expect(result).toMatchObject({ ok: false, error: expect.stringContaining("stopped while it was starting") });
    expect(manager.getCurrent()).toBeNull();
    expect(manager.ownsContainer()).toBe(false);
  }, 15_000);
});

describe("a start that succeeds", () => {
  it("owns its container as the current stack, and stop() removes it once", async () => {
    await fake.close();
    fake = await startFakeEngineApi({ autoExit: false, serveTitServer: true, images: ["idossha/ti-toolbox:v3.1.1"] });
    vi.stubEnv("DOCKER_HOST", `unix://${fake.socketPath}`);
    const manager = new StackManager(host(async () => {}));
    expect(await manager.start(dir, startOptions())).toMatchObject({ ok: true });
    const [container] = stackContainers();
    expect(manager.getCurrent()?.containerId).toBe(container!.Id);
    expect(manager.ownsContainer()).toBe(true);
    const before = fake.requests.length;
    expect(await manager.stop()).toEqual({ ok: true });
    expect(containerMutationsSince(before)).toEqual([`POST /containers/${container!.Id}/stop`, `DELETE /containers/${container!.Id}`]);
    expect(manager.ownsContainer()).toBe(false);
  });
});

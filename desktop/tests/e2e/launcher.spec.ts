import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { offscreenEnv } from "./_helpers";
import { startFakeEngineApi, type FakeEngineApi, type FakeEngineApiOptions } from "./fixtures/fake-engine-api.mjs";

/**
 * `stack.start`/`stack.stop` end to end against a *fake Docker Engine API*
 * (`tests/e2e/fixtures/fake-engine-api.mjs`, listening on a real Unix socket in this process),
 * never real Docker: `DOCKER_HOST` points the app's discovery at that socket, which
 * `docker/discover.ts` honours ahead of the CLI and every well-known path.
 *
 * The stack definition is `tests/e2e/fixtures/compose-v3.fixture.yml` (via `TIT_COMPOSE_FILE`) —
 * it mirrors the shipped `docker/docker-compose.v3.yml`'s keys while lane W2 rewrites that file.
 *
 * "The container" is real enough to connect to: on `POST /containers/{id}/start` the fake engine
 * listens on the container's own `TIT_SERVER_PORT` and answers `/api/health`, `/api/version`,
 * `/api/jobs` and `/auth/session` with the container's own `TIT_SERVER_TOKEN` — so the whole
 * discover -> version -> parse compose -> network -> volume -> pull -> create -> start -> health ->
 * session-load path runs for real, with only the daemon faked.
 */

const FIXTURE_COMPOSE = join(__dirname, "fixtures", "compose-v3.fixture.yml");

let app: ElectronApplication;
let page: Page;
let fake: FakeEngineApi;
let userDataDir: string;
let projectDir: string;

/** A copy of the fixture compose file with `edit` applied — for the failure-path tests. */
function composeVariant(name: string, edit: (text: string) => string): string {
  const path = join(mkdtempSync(join(tmpdir(), "tit-compose-")), name);
  writeFileSync(path, edit(readFileSync(FIXTURE_COMPOSE, "utf8")));
  return path;
}

async function launchApp(options: { engine?: FakeEngineApiOptions | null; env?: Record<string, string> } = {}): Promise<void> {
  let dockerHost = options.env?.DOCKER_HOST;
  if (options.engine !== null) {
    fake = await startFakeEngineApi({ autoExit: false, serveTitServer: true, ...options.engine });
    dockerHost = `unix://${fake.socketPath}`;
  }
  userDataDir = mkdtempSync(join(tmpdir(), "tit-launcher-e2e-"));
  app = await electron.launch({
    args: [join(__dirname, "..", "..")],
    env: {
      ...process.env,
      TIT_USER_DATA_DIR: userDataDir,
      TIT_COMPOSE_FILE: FIXTURE_COMPOSE,
      ...(dockerHost ? { DOCKER_HOST: dockerHost } : {}),
      ...offscreenEnv(),
      ...options.env,
    },
  });
  page = await app.firstWindow();
}

test.beforeEach(() => {
  projectDir = mkdtempSync(join(tmpdir(), "tit-fake-project-"));
});

test.afterEach(async () => {
  await app?.close();
  await fake?.close();
});

test("starts a fresh stack through the Engine API and loads the session", async () => {
  await launchApp();
  await expect(page).toHaveURL(/^app:\/\/launcher\//);

  const result = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(result).toEqual({ ok: true, attached: false });

  // A successful start reuses `connect()`'s session-load path: the container's own page.
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });
  await expect(page).not.toHaveURL(/^app:\/\/launcher\//);

  const status = await page.evaluate(() => window.tit!.stack.status());
  expect(status.running).toBe(true);
  expect(status.hostProjectDir).toBe(projectDir);

  // The network and the named volume were created before the container, under project-prefixed names.
  expect([...fake.networks.values()].map((n) => n.Name)).toEqual([expect.stringMatching(/^ti-toolbox-[0-9a-f]{8}_ti_network$/)]);
  expect([...fake.volumes.keys()]).toEqual([expect.stringMatching(/^ti-toolbox-[0-9a-f]{8}_tit_cache$/)]);

  // The container carries this app's labels, the compose file's platform, and the project mount.
  const containers = [...fake.containers.values()];
  expect(containers).toHaveLength(1);
  const container = containers[0]!;
  expect(container.Labels["tit.project"]).toMatch(/^ti-toolbox-[0-9a-f]{8}$/);
  expect(container.Labels["tit.stack"]).toBe("ti-toolbox-v3");
  expect(container.Labels["tit.host_project_dir"]).toBe(projectDir);
  expect(container.Platform).toBe("linux/amd64");
  expect(container.HostConfig?.Binds).toContain(`${projectDir}:/mnt/${basename(projectDir)}`);
  // No host directory is mounted over the image's own `/ti-toolbox` — that is where the image
  // checks the repo out and pip-installs `tit` from, so a bind there replaces the toolbox the
  // image ships (D1). It is opt-in via TIT_DEV_REPO_DIR, and nothing here opted in.
  expect(JSON.stringify(container.HostConfig?.Binds)).not.toContain(":/ti-toolbox");
  expect(JSON.stringify(container.HostConfig?.PortBindings)).toContain("127.0.0.1");
  expect(container.Healthcheck).toBeTruthy();
  // X11 is gone from the product (decision D3): nothing in the container mentions it.
  expect(JSON.stringify(container)).not.toMatch(/X11|Xauthority|DISPLAY/i);

  // The image was genuinely absent, so it was pulled — and the whole run went through the Engine
  // API, in the order the lifecycle demands.
  const lifecycle = fake.requests.filter((r) => !r.startsWith("GET /containers/") || r.endsWith("/json"));
  expect(lifecycle).toEqual(
    expect.arrayContaining(["GET /version", "GET /networks", "POST /networks/create", "POST /volumes/create", "POST /images/create", "POST /containers/create"]),
  );
  expect(lifecycle.indexOf("POST /images/create")).toBeLessThan(lifecycle.indexOf("POST /containers/create"));
});

test("a second start for the same project attaches to the running container", async () => {
  await launchApp();
  const first = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(first).toEqual({ ok: true, attached: false });
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });
  expect(fake.containers.size).toBe(1);
  const firstId = [...fake.containers.keys()][0];

  // stack.start is launcher-only (ra_14 finding 4) — return to the launcher first, exactly as the
  // real launcher UI does (it never re-invokes stack.start from server-served content).
  await page.evaluate(() => window.tit!.connect());
  await expect(page).toHaveURL(/^app:\/\/launcher\//, { timeout: 15_000 });

  const second = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(second).toEqual({ ok: true, attached: true });
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });

  // Attach never created a second container — and it recovered the port and token from the first.
  expect(fake.containers.size).toBe(1);
  expect([...fake.containers.keys()][0]).toBe(firstId);
});

test("stop removes the container and keeps the named volume", async () => {
  await launchApp();
  await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });

  // Stop from the launcher, the path the launcher's own Stop button takes.
  await page.evaluate(() => window.tit!.connect());
  await expect(page).toHaveURL(/^app:\/\/launcher\//, { timeout: 15_000 });

  const stopResult = await page.evaluate(() => window.tit!.stack.stop());
  expect(stopResult).toEqual({ ok: true });
  expect(fake.containers.size).toBe(0);
  // The volume holds cached derivatives; tearing the container down must not take it with it.
  expect([...fake.volumes.keys()]).toHaveLength(1);

  const status = await page.evaluate(() => window.tit!.stack.status());
  expect(status).toEqual({ running: false });
});

test("TIT_DEV_REPO_DIR is the only thing that mounts a host directory over /ti-toolbox", async () => {
  const repoDir = mkdtempSync(join(tmpdir(), "tit-fake-repo-"));
  await launchApp({ env: { TIT_DEV_REPO_DIR: repoDir } });
  const result = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(result).toEqual({ ok: true, attached: false });
  const container = [...fake.containers.values()][0]!;
  expect(container.HostConfig?.Binds).toContain(`${repoDir}:/ti-toolbox`);
});

test("an already-pulled image is not pulled again (an offline start of a pulled image works)", async () => {
  await launchApp({ engine: { images: ["idossha/ti-toolbox:v3.0.0-dev"] } });
  const result = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(result).toEqual({ ok: true, attached: false });
  expect(fake.requests.filter((r) => r.startsWith("POST /images/create"))).toEqual([]);
  expect(fake.containers.size).toBe(1);
});

test("stack:start/setSettings/selectDirectory refuse a server-served page (ra_14 finding 4)", async () => {
  await launchApp();
  await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });
  // Now on the container's page, not the launcher — every launcher-only call must be refused.
  // `stack.stop` is deliberately NOT in this list any more (QA engineer finding 6): the page that
  // can call it is served by the container it stops, so it can only end its own session. It is
  // exercised in its own test below.
  const results = await page.evaluate(async (dir) => {
    const [start, settings] = await Promise.all([
      window.tit!.stack.start(dir),
      window.tit!.setSettings({ lastProjectDir: "/should/not/persist" }),
      // selectDirectory would pop a native dialog Playwright can't drive, but it must return
      // `undefined` immediately (before ever showing one) — awaiting it here is safe.
    ]);
    const dir2 = await window.tit!.selectDirectory();
    return { start, settings, dir2 };
  }, projectDir);
  expect(results.start).toEqual({ ok: false, error: "unknown sender" });
  expect(results.settings).toEqual({});
  expect(results.dir2).toBeUndefined();

  // The stack is still running and status is still readable (not launcher-gated) — the refusals
  // above did not tear anything down as a side effect.
  const status = await page.evaluate(() => window.tit!.stack.status());
  expect(status.running).toBe(true);
});

test("the connected app can stop its own stack, and lands back on the launcher", async () => {
  await launchApp();
  await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });

  // What Settings -> Docker shows: the container it would stop, its image and its health.
  const status = await page.evaluate(() => window.tit!.stack.status());
  expect(status.running).toBe(true);
  expect(status.containerName).toMatch(/^ti-toolbox-[0-9a-f]{8}-tit-1$/);
  expect(status.image).toContain("ti-toolbox");
  expect(status.health).toBeDefined();

  const stopResult = await page.evaluate(() => window.tit!.stack.stop());
  expect(stopResult).toEqual({ ok: true });
  expect(fake.containers.size).toBe(0);
  // The page it stopped was served by that container, so the window goes home rather than sitting
  // on a dead UI.
  await expect(page).toHaveURL(/^app:\/\/launcher\//, { timeout: 15_000 });
});

test("openPath and showItemInFolder reject dot-segments and out-of-mount paths (ra_14 finding 3)", async () => {
  await launchApp();
  // No stack started and no session connected yet — there is no mount to resolve against at all.
  const noMount = await page.evaluate(() => window.tit!.openPath("/mnt/anything/file.txt"));
  expect(noMount).toEqual({ ok: false, reason: "no known project mount to resolve this path against" });

  await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });

  const mountName = basename(projectDir);
  const dotSegment = await page.evaluate((name) => window.tit!.openPath(`/mnt/${name}/../etc/passwd`), mountName);
  expect(dotSegment).toEqual({ ok: false, reason: "path contains a '.' or '..' segment" });

  const outsideMount = await page.evaluate(() => window.tit!.openPath("/mnt/some-other-project/file.txt"));
  expect(outsideMount).toEqual({ ok: false, reason: "path is outside the mounted project" });

  // showItemInFolder applies the identical checks and never reaches `shell.showItemInFolder` for a
  // rejected path — no Finder/Explorer window should appear as a side effect of this test.
  const revealDotSegment = await page.evaluate((name) => window.tit!.showItemInFolder(`/mnt/${name}/a/../../escape`), mountName);
  expect(revealDotSegment).toEqual({ ok: false, reason: "path contains a '.' or '..' segment" });
  const revealOutside = await page.evaluate(() => window.tit!.showItemInFolder("/mnt/some-other-project/file.txt"));
  expect(revealOutside).toEqual({ ok: false, reason: "path is outside the mounted project" });
});

test("Docker missing, Podman and a failed image pull each get their own message", async () => {
  // (a) Nothing listening at the socket DOCKER_HOST names.
  await launchApp({ engine: null, env: { DOCKER_HOST: `unix://${join(mkdtempSync(join(tmpdir(), "tit-no-docker-")), "docker.sock")}` } });
  const missing = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(missing).toEqual({ ok: false, error: expect.stringContaining("Install Docker Desktop") });
  await expect(page).toHaveURL(/^app:\/\/launcher\//); // a failed start never navigates
  await app.close();

  // (b) A Podman-flavoured daemon answers, and is refused by name (skeptic-3 claim #5).
  await launchApp({ engine: { podman: true } });
  const podman = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(podman).toEqual({ ok: false, error: expect.stringContaining("Podman is not supported") });
  await app.close();
  await fake.close();

  // (c) The registry reports the image as unknown mid-stream, inside an HTTP 200 pull.
  const badImage = composeVariant("compose-bad-image.yml", (t) => t.replace("image: idossha/ti-toolbox:v3.0.0-dev", "image: fixture/midstream-error:latest"));
  await launchApp({ env: { TIT_COMPOSE_FILE: badImage } });
  const pullFailed = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(pullFailed).toEqual({ ok: false, error: expect.stringContaining("could not be downloaded") });
  expect(fake.containers.size).toBe(0); // nothing was created after the pull failed
});

test("a container that exits while starting reports that, not a health timeout", async () => {
  const exiting = composeVariant("compose-exiting.yml", (t) =>
    t.replace('      org.ti-toolbox.service: "tit"', '      org.ti-toolbox.service: "tit"\n      fixture.execDelayMs: "300"\n      fixture.exitCode: "3"'),
  );
  await launchApp({ engine: { serveTitServer: false }, env: { TIT_COMPOSE_FILE: exiting } });
  const result = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(result).toEqual({ ok: false, error: expect.stringContaining("exited while starting up") });
  expect(result).toEqual({ ok: false, error: expect.stringContaining("exit code 3") });
});

test("the launcher UI's Browse + Start the Docker stack buttons drive the same flow", async () => {
  await launchApp();
  await expect(page.locator("#start-stack")).toBeDisabled();

  // selectDirectory opens a native dialog Playwright cannot drive. The real Browse handler sets
  // both the input's value and the button's disabled state in one step (src/main/launcher.ts); do
  // the same here directly so the click below targets an actionable (enabled) button.
  await page.evaluate((dir) => {
    (document.getElementById("project-dir") as HTMLInputElement).value = dir;
    (document.getElementById("start-stack") as HTMLButtonElement).disabled = false;
  }, projectDir);
  await page.locator("#start-stack").click();

  // The progress text moves through several real states (Looking for Docker…, Downloading the
  // image with per-layer percentages, Creating the container…, Waiting for the server…) before
  // landing on "Docker stack is up…" — match broadly rather than pin one instant, since which
  // state is visible when this polls depends on machine speed.
  await expect(page.locator("#status")).toContainText(
    /Looking for Docker|Starting the Docker stack|Downloading|Creating the|Starting the container|Waiting for the server|Docker stack is up|Pull complete/,
    { timeout: 15_000 },
  );
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 20_000 });
});

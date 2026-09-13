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
 * it mirrors the shipped root `docker-compose.yml`'s keys without depending on that file.
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
      TIT_LAUNCH_IMAGE: "",
      TIT_LAUNCH_PROJECT_DIR: "",
      TIT_LAUNCH_CONTAINER_ID: "",
      TIT_LAUNCH_EXISTING: "",
      TIT_LAUNCH_CONTAINER: "",
      TIT_DEV_SERVER_URL: "",
      TIT_DEV_SERVER_TOKEN: "",
      TIT_USER_DATA_DIR: userDataDir,
      TIT_COMPOSE_FILE: FIXTURE_COMPOSE,
      ...(dockerHost ? { DOCKER_HOST: dockerHost } : {}),
      ...offscreenEnv(),
      ...options.env,
    },
  });
  page = await app.firstWindow();
  if (!options.env?.TIT_LAUNCH_PROJECT_DIR) await expect(page.locator("#project-dir")).toBeVisible();
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
  // The finite GPU probe must finish and be removed even though the fake server stays running.
  expect(container.Labels["tit.gpu-probe"]).toBeUndefined();
  expect(container.HostConfig?.DeviceRequests).toEqual([{ Driver: "nvidia", Count: -1, Capabilities: [["gpu"]] }]);
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

test("a second start asks before attaching to the running container", async () => {
  await launchApp();
  const first = await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  expect(first).toEqual({ ok: true, attached: false });
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });
  expect(fake.containers.size).toBe(1);
  const firstId = [...fake.containers.keys()][0];

  // Simulate arriving at project selection with an independently running session. A real Switch
  // project would stop it, so navigate through the test's main-process fixture instead.
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]!.loadURL("app://launcher/"));
  await expect(page.locator("#project-dir")).toBeVisible();
  await expect(page).toHaveURL(/^app:\/\/launcher\//, { timeout: 15_000 });

  await app.evaluate(({ dialog }) => {
    dialog.showMessageBox = async (...args: unknown[]) => {
      const options = args.at(-1) as { buttons: string[] };
      if (!options.buttons.includes("Attach") || !options.buttons.includes("Recreate")) throw new Error("Expected explicit running-container decision");
      return { response: 0, checkboxChecked: false };
    };
  });
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

  const stopResult = await page.evaluate(() => window.tit!.stack.stop());
  expect(stopResult).toEqual({ ok: true });
  expect(fake.containers.size).toBe(0);
  // The volume holds cached derivatives; tearing the container down must not take it with it.
  expect([...fake.volumes.keys()]).toHaveLength(1);

  await expect(page.locator("#project-dir")).toBeVisible();
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

test("connected pages cannot directly start stacks or change settings but can pick a switch directory", async () => {
  await launchApp();
  await page.evaluate((dir) => window.tit!.stack.start(dir), projectDir);
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });
  // Picking a destination is allowed, but starting a stack still requires the local home or
  // switchProject's main-process confirmation. The native picker is mocked to stay offscreen.
  await app.evaluate(({ dialog }, dir) => {
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [dir] });
  }, projectDir);
  const results = await page.evaluate(async (dir) => {
    const [start, settings] = await Promise.all([
      window.tit!.stack.start(dir),
      window.tit!.setSettings({ lastProjectDir: "/should/not/persist" }),
    ]);
    const dir2 = await window.tit!.selectDirectory();
    return { start, settings, dir2 };
  }, projectDir);
  expect(results.start).toEqual({ ok: false, error: "unknown sender" });
  expect(results.settings).toEqual({});
  expect(results.dir2).toBe(projectDir);

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

test("Overview Browse selects a directory and opens its project", async () => {
  await launchApp();
  await expect(page.locator("#start-stack")).toBeDisabled();
  await app.evaluate(({ dialog }, dir) => {
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [dir] });
  }, projectDir);
  await page.locator("#browse").click();
  await expect(page.locator("#project-dir")).toHaveValue(projectDir);
  await page.locator("#start-stack").click();
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 20_000 });
});


test("switching projects returns to Overview; closing the connected app exits Electron", async () => {
  await launchApp();
  await page.locator("#project-dir").fill(projectDir);
  await page.locator("#start-stack").click();
  await expect(page.getByTestId("fake-server-home")).toBeVisible();
  const id = [...fake.containers.keys()][0]!;
  await page.evaluate(() => {
    localStorage.setItem("tit-subject:sim", "old-subject");
    localStorage.setItem("tit.viewer.recents", "old-files");
    localStorage.setItem("tit.theme", "dark");
  });
  const previousOrigin = new URL(page.url()).origin;
  await page.evaluate(() => window.tit!.stack.switchProject());
  await expect.poll(() => fake.containers.size).toBe(0);
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  expect(fake.requests).toContain(`POST /containers/${id}/stop`);
  expect(fake.requests).toContain(`DELETE /containers/${id}`);
  expect([...fake.volumes.keys()]).toHaveLength(1);
  const nextProject = mkdtempSync(join(tmpdir(), "tit-next-project-"));
  await page.locator("#project-dir").fill(nextProject);
  await page.locator("#project-dir").press("Enter");
  await expect(page.getByTestId("fake-server-home")).toBeVisible();
  expect(await page.evaluate(() => window.tit!.stack.status())).toMatchObject({ hostProjectDir: nextProject });
  expect(new URL(page.url()).origin).toBe(previousOrigin);
  expect(await page.evaluate(() => ({ subject: localStorage.getItem("tit-subject:sim"), recents: localStorage.getItem("tit.viewer.recents"), theme: localStorage.getItem("tit.theme") })))
    .toEqual({ subject: null, recents: null, theme: "dark" });
  const electronProcess = app.process();
  await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0]!.close(); });
  await expect.poll(() => fake.containers.size).toBe(0);
  await expect.poll(() => electronProcess.exitCode).toBe(0);
});

test("regular CLI project handoff opens Electron and owns container shutdown", async () => {
  await launchApp({ env: { TIT_LAUNCH_PROJECT_DIR: projectDir, TIT_LAUNCH_IMAGE: "registry.example.org/research/ti-toolbox:custom", TIT_LAUNCH_EXISTING: "recreate", TIT_LAUNCH_CONTAINER: "" } });
  await expect(page.getByTestId("fake-server-home")).toBeVisible({ timeout: 15_000 });
  const status = await page.evaluate(() => window.tit!.stack.status());
  expect(status).toMatchObject({ running: true, hostProjectDir: projectDir, image: "registry.example.org/research/ti-toolbox:custom" });
  expect(await app.evaluate(() => ({ action: process.env.TIT_LAUNCH_EXISTING ?? null, container: process.env.TIT_LAUNCH_CONTAINER ?? null }))).toEqual({ action: null, container: null });
  const id = [...fake.containers.keys()][0]!;
  const electronProcess = app.process();
  await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0]!.close(); });
  await expect.poll(() => fake.containers.size).toBe(0);
  await expect.poll(() => electronProcess.exitCode).toBe(0);
  expect(fake.requests).toContain(`POST /containers/${id}/stop`);
});


test("disconnected Overview renders without contacting a job server", async () => {
  await launchApp();
  const backendRequests: string[] = [];
  page.on("request", (request) => {
    if (/\/(api|auth)\//.test(request.url())) backendRequests.push(request.url());
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.reload();
  await expect(page.locator("#project-dir")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Open a project", exact: true })).toBeVisible();
  await page.locator("#project-dir").fill(projectDir);
  await expect(page.locator("#start-stack")).toBeEnabled();
  await expect(page.getByTestId("nav-rail")).toHaveAttribute("data-rail-mode", "labels");
  for (const id of ["preprocess", "optimizer", "simulator", "analyzer", "viewer", "results", "notebooks", "jobs"]) {
    await expect(page.getByTestId(`nav-item-${id}`)).toBeVisible();
    await expect(page.getByTestId(`nav-item-${id}`)).toHaveAttribute("aria-disabled", "true");
  }
  await page.getByTestId("nav-item-simulator").dispatchEvent("click");
  await expect(page.locator("#project-dir")).toBeVisible();
  expect(backendRequests).toEqual([]);
  expect(errors).toEqual([]);
  expect(fake.containers.size).toBe(0);
  const electronProcess = app.process();
  await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0]!.close(); });
  await expect.poll(() => electronProcess.exitCode).toBe(0);
});


test("cancelling an active-job project switch keeps its session running", async () => {
  const jobs = [{ id: "active-job", state: "running" }];
  await launchApp({ engine: { jobs } });
  await page.locator("#project-dir").fill(projectDir);
  await page.locator("#start-stack").click();
  await expect(page.getByTestId("fake-server-home")).toBeVisible();
  const connectedUrl = page.url();
  const id = [...fake.containers.keys()][0]!;
  await app.evaluate(({ dialog }) => {
    dialog.showMessageBox = async (...args: unknown[]) => {
      const options = args.at(-1) as { buttons: string[]; message: string };
      if (!options.message.includes("1 active job") || !options.buttons.includes("Stop jobs and close project")) throw new Error("Missing active-job switch confirmation");
      return { response: options.buttons.indexOf("Cancel"), checkboxChecked: false };
    };
  });
  expect(await page.evaluate(() => window.tit!.stack.switchProject())).toMatchObject({ ok: false });
  await expect(page).toHaveURL(connectedUrl);
  expect(fake.containers.get(id)?.running).toBe(true);
  expect(fake.requests).not.toContain(`POST /containers/${id}/stop`);
  expect(fake.requests).not.toContain(`DELETE /containers/${id}`);
  jobs.length = 0; // The fixture job completes before normal test teardown.
});


test("a confirmed destination switches directly to the next project", async () => {
  await launchApp();
  await page.locator("#project-dir").fill(projectDir);
  await page.locator("#start-stack").click();
  await expect(page.getByTestId("fake-server-home")).toBeVisible();
  const oldId = [...fake.containers.keys()][0]!;
  const nextProject = mkdtempSync(join(tmpdir(), "tit-next-project-"));
  await app.evaluate(({ dialog }, target) => {
    dialog.showMessageBox = async (...args: unknown[]) => {
      const options = args.at(-1) as { buttons: string[]; detail: string };
      if (!options.detail.includes(target)) throw new Error("Destination missing from native confirmation");
      return { response: options.buttons.findIndex((label) => /switch/i.test(label)), checkboxChecked: false };
    };
  }, nextProject);
  expect(await page.evaluate((dir) => window.tit!.stack.switchProject(dir), nextProject)).toMatchObject({ ok: true });
  await expect(page.getByTestId("fake-server-home")).toBeVisible();
  await expect.poll(async () => page.evaluate(() => window.tit!.stack.status())).toMatchObject({ running: true, hostProjectDir: nextProject });
  expect(fake.containers.has(oldId)).toBe(false);
  expect(fake.containers.size).toBe(1);
  expect(fake.requests).toContain(`POST /containers/${oldId}/stop`);
  expect(fake.requests).toContain(`DELETE /containers/${oldId}`);
});

test("invalid or cancelled destinations leave the current project running", async () => {
  await launchApp();
  await page.locator("#project-dir").fill(projectDir);
  await page.locator("#start-stack").click();
  await expect(page.getByTestId("fake-server-home")).toBeVisible();
  const oldUrl = page.url();
  const oldId = [...fake.containers.keys()][0]!;
  expect(await page.evaluate((dir) => window.tit!.stack.switchProject(dir), join(projectDir, "missing"))).toMatchObject({ ok: false });
  const nextProject = mkdtempSync(join(tmpdir(), "tit-cancel-project-"));
  const invalidCompose = composeVariant("invalid-switch.yml", () => "services: {}\n");
  await app.evaluate((_electron, path) => { process.env.TIT_COMPOSE_FILE = path; }, invalidCompose);
  expect(await page.evaluate((dir) => window.tit!.stack.switchProject(dir), nextProject)).toMatchObject({ ok: false });
  expect(fake.containers.get(oldId)?.running).toBe(true);
  await app.evaluate((_electron, path) => { process.env.TIT_COMPOSE_FILE = path; }, FIXTURE_COMPOSE);
  await app.evaluate(({ dialog }, target) => {
    dialog.showMessageBox = async (...args: unknown[]) => {
      const options = args.at(-1) as { buttons: string[]; detail: string };
      if (!options.detail.includes(target)) throw new Error("Destination missing from native confirmation");
      return { response: options.buttons.indexOf("Cancel"), checkboxChecked: false };
    };
  }, nextProject);
  expect(await page.evaluate((dir) => window.tit!.stack.switchProject(dir), nextProject)).toMatchObject({ ok: false });
  await expect(page).toHaveURL(oldUrl);
  expect(fake.containers.get(oldId)?.running).toBe(true);
  expect(fake.requests).not.toContain(`POST /containers/${oldId}/stop`);
  expect(fake.requests).not.toContain(`DELETE /containers/${oldId}`);
});

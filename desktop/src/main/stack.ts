/**
 * The Docker stack for one project directory, driven entirely through the Engine API.
 *
 * Compose is still the definition — the repository's root `docker-compose.yml`, parsed by
 * `shared/composeFile.ts` — but nothing here shells out to `docker compose` (or to `docker` at
 * all, beyond the one `docker context inspect` inside `docker/discover.ts`). `start()` discovers
 * the engine, checks its API version, reads the compose file, ensures the network and named
 * volumes exist, pulls the image if it is missing (streaming progress to the launcher), creates
 * and starts the container with this app's own labels and env, streams its log lines while it
 * comes up, waits for `/api/health`, and hands back `{url, token}`.
 *
 * Attach-or-start is by label, not by a file on disk: every container this app creates carries
 * `tit.project=<project name>` *and* `tit.host_project_dir=<the directory it was opened for>`, and
 * a later `start()` for the same directory finds it, checks both, reads its port and bearer token
 * straight out of the container's own environment, and reconnects. Both labels are needed: the
 * project name is a 32-bit hash, so it alone would let a collision attach one project's UI to
 * another project's container. That is why there is no `stacks.json` any more — the container is
 * the source of truth, and the token never has to be written to the host filesystem at all.
 *
 * X11 is gone (decision D3): no `DISPLAY`, no `xhost`, no XQuartz, nothing to revert on quit.
 * The FreeSurfer service and its named volume are gone with it (D2).
 *
 * Returns credentials only; loading the session into the window is the caller's job (`index.ts`
 * reuses the `connect()` used by the manual "Connect" form) — this module never touches
 * `BrowserWindow`.
 *
 * Nothing here imports `electron`, directly or transitively (see `StackHost` below): the same
 * attach-or-start runs inside Electron main (`./stackHost.ts`) and under plain Node
 * (`scripts/dev.ts`), so `npm run dev` brings up the container the product brings up rather than a
 * second, drifting one.
 */
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { stat } from "node:fs/promises";
import {
  LABEL_HOST_DIR,
  LABEL_PROJECT,
  LABEL_SERVICE,
  LABEL_STACK,
  STACK_ID,
  buildStackEnv,
  computeProjectName,
  generateToken,
  stackErrorMessage,
  type StackErrorKind,
} from "../shared/compose";
import { StackError, buildContainerPlan, interpolate, parseComposeFile, type ContainerPlan } from "../shared/composeFile";
import { parse as parseYaml } from "yaml";
import { formatPullEvent, parseProgressLine } from "../shared/pullProgress";
import { discover } from "./docker/discover";
import { DockerEngineClient, DockerEngineError, type DockerVersionInfo } from "./docker/engine";
import { StackApi, type ContainerSummary } from "./docker/stackApi";
import { findFreePort } from "./port";
import { hostOsInfo, timezone } from "./hostInfo";
import { ensureUserConfigDir } from "./userConfig";

const DEFAULT_PORT = 8765;
const SERVICE_NAME = "tit";
/** `POST /containers/create?platform=` — the whole reason an amd64 image runs on an arm64 host. */
const MIN_API_VERSION = "1.41";
/** How long a freshly started container has to answer `/api/health`; a cold amd64 start is slow. */
const START_HEALTH_TIMEOUT_MS = Number(process.env.TIT_STACK_HEALTH_TIMEOUT_MS ?? 120_000);
/**
 * How long an already-running container has to answer `/api/health` before `start()` gives up on
 * attaching to it. It used to be 10 s, on the premise that "a running stack answers immediately or
 * it is not the stack we think it is". That premise is wrong on this hardware: the server is one
 * uvicorn worker, and a CPU-bound request handler (a cold scene build reading a 184 MB head mesh,
 * a catalog scan over a large project) holds Python's GIL and delays every other response,
 * `/api/health` included. Measured 2026-09-04: `pnpm dev` failed twice with "its server never
 * answered" against a container Docker itself reported healthy, while a scene cache was building;
 * seconds later the same endpoint answered in 4 ms. Declaring a live stack dead there costs the
 * developer their whole dev loop, so the probe now waits long enough to outlast a stall and says
 * what it saw when it does give up.
 */
const ATTACH_HEALTH_TIMEOUT_MS = Number(process.env.TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS ?? 45_000);
const EXIT_POLL_MS = 400;

export type StackEvent =
  | { type: "progress"; stage: string; message: string }
  | { type: "started"; origin: string; port: number; attached: boolean }
  | { type: "stopped" }
  | { type: "error"; message: string };

/**
 * Everything the stack lifecycle needs from the process hosting it, injected instead of imported.
 *
 * `stack.ts` used to `import { app } from "electron"` (for `isPackaged`/`getAppPath`), `./log`
 * (which imports `app` too) and `./health` (which imports electron's `net`). That made attach-or-start
 * runnable only inside an Electron main process, so `npm run dev` had no way to bring the same
 * container up the app brings up — and the alternative, a second `docker run` in a shell script,
 * is exactly the duplicate-implementation drift P1 exists to prevent (the dev container and the
 * app's container would differ in labels, mounts and env, and only one of them would be tested).
 * With the four host-shaped needs behind this object, Electron main passes `electronStackHost`
 * (`./stackHost.ts`) and `scripts/dev.ts` passes a plain Node one; the code between them is one copy.
 */
export interface StackHost {
  /** `app.isPackaged`. Always false under the dev script — it is a checkout, by definition. */
  isPackaged: boolean;
  /** `app.getAppPath()` — the base for the `docker-compose.yml` lookup (see `resolveComposeFile`). */
  appPath: string;
  /** `process.resourcesPath` in a packaged app; `undefined` anywhere else. */
  resourcesPath?: string | undefined;
  log(level: "info" | "warn" | "error", message: string): void;
  /** Poll `<origin>/api/health` until it answers `{status:"ok"}` or the timeout expires (throws). */
  waitForHealth(origin: string, timeoutMs: number): Promise<void>;
  /** One authenticated GET returning parsed JSON; throws on anything but a 2xx. */
  fetchJson(url: string, headers: Record<string, string>): Promise<unknown>;
}

/**
 * Per-start overrides. Empty (the packaged app's own call) uses port 8765 upwards, the compose
 * file's default image tag, the repo mount only if the
 * environment asked for one by name, no `--reload`, and attach only when this project's running
 * container uses the requested image reference.
 */
export interface StackStartOptions {
  /** First port to try when creating a container (default `DEFAULT_PORT`). */
  preferredPort?: number;
  /** `${TIT_IMAGE_TAG}` for the compose image reference (default: the compose file's own). */
  imageTag?: string;
  /** Host repo to bind-mount at `/ti-toolbox` (dev only; see `resolveRepoDir`). */
  repoDir?: string | undefined;
  /** `TIT_SERVER_RELOAD=1` — the entrypoint then runs uvicorn `--reload --reload-dir /ti-toolbox/tit`. */
  serverReload?: boolean;
  /**
   * `TIT_STATIC_DIR` — the UI bundle the server serves at `/`. Unset means the image's own baked
   * copy, which is what the last image build carried, not what this worktree has built; the dev
   * script points it at `/ti-toolbox/desktop/out/renderer` so anything loading the page from the
   * server's origin (every `--project=real` e2e run) tests current renderer code. Falls back to
   * `process.env.TIT_STATIC_DIR`.
   */
  staticDir?: string;
  /**
   * Attach only to a running container whose own recorded state already matches the options above;
   * one that differs is removed and recreated, with the reason emitted as a progress line. Off by
   * default: the packaged app has no dev requirements to match, and silently recreating a user's
   * running stack because a field it never sets differs would kill their running jobs.
   */
  requireMatch?: boolean;
  /**
   * Recreate a mismatched container even when it has work in flight. Off by default, and the
   * default is the point: a recreate stops the container and mints a NEW bearer token, so doing it
   * under a running job kills that job (a FEM solve is 16 minutes on this hardware) and logs out
   * every other client that knew the old token. `npm run dev --force` is the deliberate override;
   * `npm run dev:down` first is the other way.
   */
  forceRecreate?: boolean;
}

export type StackStartResult = { ok: true; url: string; token: string; attached: boolean } | { ok: false; error: string };
export type StackStopResult = { ok: true } | { ok: false; error: string };
export interface StackStatusResult {
  running: boolean;
  hostProjectDir?: string;
  origin?: string;
  port?: number;
  /** `docker ps` name of the container, so the in-app Stop control can say what it will stop. */
  containerName?: string;
  /** Image reference the container was created from, tag included. */
  image?: string;
  /** Docker's own healthcheck verdict; `"none"` when the image declares no healthcheck. */
  health?: "starting" | "healthy" | "unhealthy" | "none";
}

export interface CurrentStack {
  projectName: string;
  hostProjectDir: string;
  containerId: string;
  containerName: string;
  image: string;
  origin: string;
  token: string;
  port: number;
}

/** A failure with the launcher copy already chosen. Thrown inside `doStart`, caught once at the top. */
class StackStartError extends Error {
  constructor(kind: StackErrorKind, detail?: string) {
    super(stackErrorMessage(kind, detail));
    this.name = "StackStartError";
  }
}

function compareApiVersions(a: string, b: string): number {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

/**
 * Podman's Docker-compatibility API answers `/version` too, so "it responded" is not proof of a
 * supported engine. Its response names itself — in `Components[].Name` ("Podman Engine") and in
 * `Platform.Name` — and skeptic-3's three primary-source checks (compat socket off by default, API
 * pinned at 1.40, amd64 emulation off by default) are exactly why this app declares it unsupported
 * rather than discovering the difference halfway through a two-hour simulation.
 */
function isUnsupportedEngine(version: DockerVersionInfo): boolean {
  const text = JSON.stringify([version.Components, version.Platform, version.Version]).toLowerCase();
  return text.includes("podman");
}

export class StackManager {
  private current: CurrentStack | null = null;
  private listeners = new Set<(event: StackEvent) => void>();
  private starting = false;
  private host: StackHost;

  constructor(host: StackHost) {
    this.host = host;
  }

  onEvent(cb: (event: StackEvent) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  private emit(event: StackEvent): void {
    for (const cb of this.listeners) cb(event);
  }

  private progress(message: string, stage = "stack"): void {
    this.host.log("info", `[stack] ${message}`);
    this.emit({ type: "progress", stage, message });
  }

  getCurrent(): CurrentStack | null {
    return this.current;
  }

  async start(hostProjectDirRaw: string, options: StackStartOptions = {}): Promise<StackStartResult> {
    if (this.starting) return { ok: false, error: "A stack is already starting." };
    this.starting = true;
    try {
      return await this.doStart(hostProjectDirRaw, options);
    } catch (err) {
      const message = this.describe(err);
      this.emit({ type: "error", message });
      return { ok: false, error: message };
    } finally {
      this.starting = false;
    }
  }

  /** One place that turns anything thrown below into launcher copy — no failure escapes unclassified. */
  private describe(err: unknown): string {
    if (err instanceof StackStartError) return err.message;
    if (err instanceof StackError) return stackErrorMessage("compose-invalid", err.message);
    if (err instanceof DockerEngineError) {
      switch (err.kind) {
        case "not-installed":
        case "not-running":
        case "socket-permission":
        case "unsupported-engine":
          return stackErrorMessage(err.kind);
        default:
          return stackErrorMessage("unknown", err.message);
      }
    }
    return stackErrorMessage("unknown", err instanceof Error ? err.message : String(err));
  }

  private async doStart(hostProjectDirRaw: string, options: StackStartOptions): Promise<StackStartResult> {
    const hostProjectDir = resolve(hostProjectDirRaw);
    try {
      const info = await stat(hostProjectDir);
      if (!info.isDirectory()) return { ok: false, error: `Not a directory: ${hostProjectDir}` };
    } catch {
      return { ok: false, error: `Project directory does not exist: ${hostProjectDir}` };
    }

    this.progress("Looking for Docker…");
    const found = await discover();
    if (!found.available) throw new StackStartError(found.kind);
    const client = new DockerEngineClient(found.connection);

    this.progress("Checking the Docker engine…");
    const version = await client.version();
    if (isUnsupportedEngine(version)) throw new StackStartError("unsupported-engine", `reported ${version.Version}`);
    if (compareApiVersions(version.ApiVersion, MIN_API_VERSION) < 0) {
      throw new StackStartError("unsupported-engine", `this engine speaks API ${version.ApiVersion}; ${MIN_API_VERSION} or newer is required`);
    }
    const api = new StackApi(found.connection, version.ApiVersion);
    const projectName = computeProjectName(hostProjectDir);

    const attached = await this.tryAttach(api, projectName, hostProjectDir, options);
    if (attached) return attached;

    return this.startFresh(client, api, projectName, hostProjectDir, options);
  }

  /**
   * Attach to this project's already-running container, if there is one — the "attach, don't kill"
   * rule (TODO §2.7). Its port and token come out of its own environment, so this works across app
   * restarts with nothing persisted on the host. A container that exists but is not running is
   * removed here so the fresh start below can reuse its name.
   */
  private async tryAttach(api: StackApi, projectName: string, hostProjectDir: string, options: StackStartOptions): Promise<StackStartResult | null> {
    const existing = await api.listContainers({ [LABEL_PROJECT]: projectName });
    const decision = decideAttach(existing, hostProjectDir);
    if (decision.kind === "none") return null;
    if (decision.kind === "refuse") throw new StackStartError("unknown", decision.reason);
    for (const warning of decision.warnings) this.host.log("warn", `[stack] ${warning}`);
    if (decision.kind === "recreate") {
      // Stopped containers hold the name the fresh start below needs, whichever directory they
      // were opened for. Removing one destroys nothing: named volumes are kept, and the project
      // data lives on the host.
      this.progress("Removing this project's stopped container…");
      for (const c of existing) await api.removeContainerById(c.Id).catch((err) => this.host.log("warn", `could not remove ${c.Id}: ${String(err)}`));
      return null;
    }
    const running = decision.container;

    this.progress("Attaching to the running stack…");
    const state = await api.inspect(running.Id);
    // Resolve only the image here: attach reuses the running container's mounts/port/token.
    // The same YAML parser and interpolation rules drive fresh creation below.
    const compose = parseYaml(readFileSync(resolveComposeFile(this.host), "utf8"));
    const imageTemplate: unknown = compose?.services?.[SERVICE_NAME]?.image;
    if (typeof imageTemplate !== "string" || !imageTemplate) throw new StackStartError("compose-invalid", "services.tit.image must be a nonempty string");
    const expectedImage = interpolate(imageTemplate, { ...process.env, ...(options.imageTag ? { TIT_IMAGE_TAG: options.imageTag } : {}) }, "services.tit.image");
    // Config.Image is the original tag/digest; Docker's image ID and list display are not.
    // Even --force must not turn an image mismatch into an automatic job-killing replacement.
    if (state.image !== expectedImage) {
      throw new StackStartError(
        "unknown",
        `The running container uses ${state.image || "(unknown)"}, but this app requires ${expectedImage}. ` +
          `Wait for its jobs to finish, then stop this project's container and launch again. The running container was left unchanged.`,
      );
    }
    if (options.requireMatch) {
      const mismatch = describeMismatch(state, state.image, options);
      if (mismatch) {
        if (!options.forceRecreate) {
          const port = state.publishedPort ?? Number(state.env.TIT_SERVER_PORT);
          const busy = await this.runningJobs(`http://127.0.0.1:${port}`, state.env.TIT_SERVER_TOKEN ?? "");
          if (busy.length) {
            throw new StackStartError(
              "unknown",
              `${mismatch}, but it has ${busy.length} job(s) in flight (${busy.join(", ")}). Recreating would kill them and change the server token. ` +
                `Wait for them, or stop the container yourself (npm run dev:down), or re-run with --force`,
            );
          }
        }
        // One printed line, then a recreate: a dev container that is missing the repo mount or the
        // reload flag looks healthy and serves the image's baked-in Python, so "attached" with no
        // explanation is how an afternoon goes into editing files nothing reads.
        this.progress(`Recreating the container — ${mismatch}`);
        for (const c of existing) await api.removeContainerById(c.Id, true).catch((err) => this.host.log("warn", `could not remove ${c.Id}: ${String(err)}`));
        return null;
      }
    }
    const port = state.publishedPort ?? Number(state.env.TIT_SERVER_PORT);
    const token = state.env.TIT_SERVER_TOKEN;
    if (!port || !token) throw new StackStartError("unknown", "the running container does not carry a server port and token");
    const origin = `http://127.0.0.1:${port}`;
    try {
      await this.host.waitForHealth(origin, ATTACH_HEALTH_TIMEOUT_MS);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      throw new StackStartError(
        "health-timeout",
        `${detail}. Container ${state.Name} is running, so it is most likely busy rather than broken ` +
          `(a cold scene build or a heavy job blocks the single server worker). Try again, raise ` +
          `TIT_STACK_ATTACH_HEALTH_TIMEOUT_MS, or check "docker logs ${state.Name}"`,
      );
    }
    this.current = { projectName, hostProjectDir, containerId: running.Id, containerName: state.Name, image: state.image, origin, token, port };
    this.emit({ type: "started", origin, port, attached: true });
    return { ok: true, url: origin, token, attached: true };
  }

  /** Fail closed: a busy or unreachable server must never be mistaken for an idle one. */
  private async runningJobs(origin: string, token: string): Promise<string[]> {
    try {
      if (!token) throw new Error("the running container has no server token");
      return runningJobLabels(await this.host.fetchJson(`${origin}/api/jobs`, { authorization: `Bearer ${token}` }));
    } catch {
      throw new StackStartError(
        "unknown",
        "Could not verify the running container's jobs. It was left unchanged. Check the server and wait for its jobs to finish before trying again.",
      );
    }
  }

  private async startFresh(
    client: DockerEngineClient,
    api: StackApi,
    projectName: string,
    hostProjectDir: string,
    options: StackStartOptions,
  ): Promise<StackStartResult> {
    this.progress("Finding a free port…");
    const port = await findFreePort(options.preferredPort ?? DEFAULT_PORT);
    const token = generateToken();
    const { os: hostOs, version: hostOsVersion, arch: hostArch } = hostOsInfo();
    const staticDir = options.staticDir ?? process.env.TIT_STATIC_DIR;
    const env = buildStackEnv({
      hostProjectDir,
      projectDirName: basename(hostProjectDir),
      userConfigDir: ensureUserConfigDir(),
      port,
      token,
      timezone: timezone(),
      hostOs,
      hostOsVersion,
      hostArch,
      repoDir: options.repoDir ?? resolveRepoDir(process.env, this.host.isPackaged),
      serverReload: options.serverReload ?? false,
      ...(options.imageTag ? { imageTag: options.imageTag } : {}),
      ...(staticDir ? { staticDir } : {}),
    });

    const composeFile = resolveComposeFile(this.host);
    const stack = parseComposeFile(readFileSync(composeFile, "utf8"), { ...process.env, ...env });
    const plan = buildContainerPlan(stack, {
      serviceName: SERVICE_NAME,
      projectName,
      labels: {
        [LABEL_PROJECT]: projectName,
        [LABEL_STACK]: STACK_ID,
        [LABEL_SERVICE]: SERVICE_NAME,
        [LABEL_HOST_DIR]: hostProjectDir,
      },
    });
    if (plan.hostPort !== port) {
      throw new StackStartError("compose-invalid", `services.${SERVICE_NAME}.ports must publish \${TIT_SERVER_PORT} (got ${plan.hostPort}, expected ${port})`);
    }

    if (plan.networkName) {
      this.progress("Creating the Docker network…");
      await api.ensureNetwork(plan.networkName, plan.networkDriver);
    }
    for (const volume of plan.namedVolumes) {
      this.progress(`Creating the volume ${volume}…`);
      await api.ensureVolume(volume);
    }

    await this.ensureImage(client, api, plan);

    this.progress("Creating the container…");
    await this.removeByName(api, plan.containerName);
    const created = await api.createContainer(plan.body, { name: plan.containerName, platform: plan.platform });
    this.progress("Starting the container…");
    await client.startContainer(created.Id);

    const origin = `http://127.0.0.1:${plan.hostPort}`;
    this.progress("Waiting for the server to answer…");
    const stopLogs = this.pumpLogs(client, created.Id);
    try {
      await this.waitForServer(api, origin, created.Id, plan.containerPort);
    } finally {
      stopLogs();
    }

    this.current = { projectName, hostProjectDir, containerId: created.Id, containerName: plan.containerName, image: plan.image, origin, token, port: plan.hostPort };
    this.emit({ type: "started", origin, port: plan.hostPort, attached: false });
    return { ok: true, url: origin, token, attached: false };
  }

  /** Pulls only when the image is genuinely absent, so an offline start of an already-pulled image works. */
  private async ensureImage(client: DockerEngineClient, api: StackApi, plan: ContainerPlan): Promise<void> {
    if (await api.imageExists(plan.image)) {
      this.progress(`Image ${plan.image} is already present.`);
      return;
    }
    this.progress(`Downloading ${plan.image} — the first run can take a while…`);
    try {
      await client.pullImage(plan.imageName, plan.imageTag, (event) => {
        const parsed = formatPullEvent(event);
        if (parsed.message) this.emit({ type: "progress", stage: "pull", message: parsed.message });
      });
    } catch (err) {
      throw new StackStartError("image-pull-failed", err instanceof Error ? err.message : String(err));
    }
  }

  private async removeByName(api: StackApi, containerName: string): Promise<void> {
    try {
      const state = await api.inspect(containerName);
      await api.removeContainerById(state.Id, true);
    } catch (err) {
      if (err instanceof DockerEngineError && err.kind === "not-found") return;
      throw err;
    }
  }

  /**
   * Streams the container's own stdout/stderr into the launcher while it starts, so a slow or
   * failing boot shows what it is doing instead of a silent spinner. Returns a stop function; the
   * generator's `return()` closes the underlying log request rather than leaving it open.
   */
  private pumpLogs(client: DockerEngineClient, containerId: string): () => void {
    const frames = client.logs(containerId, { follow: true, tail: "20" });
    let stopped = false;
    void (async () => {
      try {
        for await (const frame of frames) {
          if (stopped) break;
          for (const line of frame.payload.toString("utf8").split(/\r?\n/)) {
            const parsed = parseProgressLine(line);
            if (parsed.message && !parsed.isSpinner) this.emit({ type: "progress", stage: "container", message: parsed.message });
          }
        }
      } catch (err) {
        this.host.log("warn", `[stack] log stream ended: ${err instanceof Error ? err.message : String(err)}`);
      }
    })();
    return () => {
      stopped = true;
      void frames.return(undefined).catch(() => {});
    };
  }

  /**
   * Health, or the container dying first. Racing the two matters: a container that exits two
   * seconds in (a bad mount, a missing image entrypoint) would otherwise keep the user staring at
   * "waiting for the server" for the full health timeout and then report the wrong cause.
   */
  private async waitForServer(api: StackApi, origin: string, containerId: string, containerPort: number): Promise<void> {
    let settled = false;
    const health = this.host.waitForHealth(origin, START_HEALTH_TIMEOUT_MS).then(() => "healthy" as const);
    const exited = (async () => {
      const deadline = Date.now() + START_HEALTH_TIMEOUT_MS;
      while (!settled && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, EXIT_POLL_MS));
        if (settled) break;
        const state = await api.inspect(containerId, containerPort).catch(() => null);
        if (state && !state.running && state.status !== "created") return state.exitCode;
      }
      return null;
    })();

    try {
      const outcome = await Promise.race([health, exited]);
      if (outcome === "healthy") return;
      if (typeof outcome === "number") throw new StackStartError("container-exited", `exit code ${outcome} — see the container log lines above`);
      // `exited` gave up at the deadline; let the health promise report its own timeout.
      await health;
    } catch (err) {
      if (err instanceof StackStartError) throw err;
      throw new StackStartError("health-timeout", err instanceof Error ? err.message : String(err));
    } finally {
      settled = true;
      health.catch(() => {});
      exited.catch(() => {});
    }
  }

  /** Stop and remove the container. Named volumes are kept — they hold the user's cached data. */
  async stop(): Promise<StackStopResult> {
    const current = this.current;
    if (!current) return { ok: true };
    this.progress("Stopping the container…");
    try {
      const found = await discover();
      if (!found.available) throw new DockerEngineError(found.kind, found.message);
      const client = new DockerEngineClient(found.connection);
      await client.stopContainer(current.containerId, 10);
      await client.removeContainer(current.containerId, { volumes: false });
    } catch (err) {
      // The container may already be gone (the user ran `docker rm` themselves); that is the state
      // this method exists to reach, so it is a success, not an error.
      if (!(err instanceof DockerEngineError && err.kind === "not-found")) {
        const message = this.describe(err);
        this.current = null;
        this.emit({ type: "error", message });
        return { ok: false, error: message };
      }
    }
    this.current = null;
    this.emit({ type: "stopped" });
    return { ok: true };
  }

  async status(): Promise<StackStatusResult> {
    const current = this.current;
    if (!current) return { running: false };
    let running = false;
    let health: StackStatusResult["health"];
    try {
      const found = await discover();
      if (found.available) {
        const api = new StackApi(found.connection);
        const state = await api.inspect(current.containerId);
        running = state.running;
        health = state.health;
      }
    } catch (err) {
      this.host.log("warn", `[stack] status check failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    return {
      running,
      hostProjectDir: current.hostProjectDir,
      origin: current.origin,
      port: current.port,
      containerName: current.containerName,
      image: current.image,
      ...(health ? { health } : {}),
    };
  }
}

/**
 * The stack definition. `TIT_COMPOSE_FILE` points the app at another one — used by the e2e suite
 * (a fixture that mirrors the shipped file's keys against a fake engine) and by a developer
 * testing a compose change without touching the shipped file.
 */
function resolveComposeFile(host: StackHost): string {
  const override = process.env.TIT_COMPOSE_FILE;
  if (override) {
    if (!existsSync(override)) throw new StackStartError("compose-invalid", `TIT_COMPOSE_FILE does not exist: ${override}`);
    return override;
  }
  // The run spec is the repository's single root `docker-compose.yml`. Three places it can be,
  // in the order they are tried:
  //   1. `appPath/../docker-compose.yml`  — unpackaged: `appPath` is `desktop/`, so `..` is the
  //      repository root. This is the file `tit/launch.py` and the loaders read too.
  //   2. `resourcesPath/docker-compose.yml` — packaged: electron-builder's `extraResources`
  //      copies the root file to `Resources/` (it is outside the app directory, so it cannot be
  //      an asar `files:` entry the way `docker/**` was).
  //   3. `appPath/docker-compose.yml` — a layout that puts it beside the app; kept last so the
  //      two real cases above are what normally matches.
  const candidates = [
    join(host.appPath, "..", "docker-compose.yml"),
    host.resourcesPath ? join(host.resourcesPath, "docker-compose.yml") : null,
    join(host.appPath, "docker-compose.yml"),
  ].filter((c): c is string => Boolean(c));
  const found = candidates.find((c) => existsSync(c));
  if (!found) throw new StackStartError("compose-invalid", `docker-compose.yml not found (looked in: ${candidates.join(", ")})`);
  return found;
}

/**
 * Repo root for the *dev* bind mount (`${TIT_REPO_DIR:-}:/ti-toolbox`), or `undefined` for no
 * mount at all — which is the default, and the only correct answer for a packaged app.
 *
 * The mount is opt-in by name, and only in an unpackaged run. What this replaces —
 * `process.env.TIT_DEV_REPO_DIR || join(app.getAppPath(), "..")` — could never return an empty
 * value, so *every* start bind-mounted some host directory over `/ti-toolbox`. That path is not
 * spare space in the image: `Dockerfile.ti-toolbox` checks the repo out there and pip-installs
 * `tit` from it, so the mount replaces the image's own toolbox for the container's lifetime. In a
 * packaged app `app.getAppPath()/..` is `TI-Toolbox.app/Contents/Resources`, which has no `tit` in
 * it at all, and the container would have died on `ModuleNotFoundError: No module named 'tit'`; in
 * dev it silently ran a worktree's Python instead of the image's, which is how W2's image smoke
 * test came to read a `tit/viewspec.py` the image never baked.
 *
 * `TIT_DEV_REPO_DIR` is the name to set; `TIT_REPO_DIR` is accepted as the same request, because
 * that is the variable the compose file itself names and a developer who exports it means it.
 */
export function resolveRepoDir(env: NodeJS.ProcessEnv, isPackaged: boolean): string | undefined {
  if (isPackaged) return undefined;
  const explicit = (env.TIT_DEV_REPO_DIR ?? env.TIT_REPO_DIR ?? "").trim();
  return explicit === "" ? undefined : explicit;
}

/** `realpath` where possible, plain `resolve` where the path no longer exists. */
function realDir(dir: string): string {
  try {
    return realpathSync(resolve(dir));
  } catch {
    return resolve(dir);
  }
}

/**
 * Whether a container's `tit.host_project_dir` label names the directory we were asked to open.
 *
 * `tit.project` — the label attach filters on — is `ti-toolbox-<32-bit hash of the directory>`
 * (`computeProjectName`), deliberately short and non-cryptographic. That makes it a *name*, not
 * evidence: two directories that collide would otherwise hand project B the running container of
 * project A, along with its port, its bearer token and its mounted data, with nothing on screen
 * saying so. The host directory itself is on the container, so compare that too. A container with
 * no such label is not a match either — it was not created by a version of this app that records
 * what it opened, so there is nothing to compare against.
 */
export function sameHostDir(labelValue: string | undefined, hostProjectDir: string): boolean {
  if (!labelValue) return false;
  return realDir(labelValue) === realDir(hostProjectDir);
}

export type AttachDecision =
  /** Nothing carries this project's name — start fresh. */
  | { kind: "none" }
  /** Only stopped containers: remove them (they hold the name) and start fresh. */
  | { kind: "recreate"; warnings: string[] }
  /** A running container this project genuinely owns. */
  | { kind: "attach"; container: ContainerSummary; warnings: string[] }
  /** A running container with this project's name but somebody else's directory. */
  | { kind: "refuse"; reason: string };

/**
 * What to do about the containers already carrying this project's `tit.project` label.
 *
 * Pure, and separated from the Engine API calls around it, because the interesting case is the one
 * that is hardest to stage live: a 32-bit hash collision, where two host directories produce the
 * same project name (QA engineer finding 5). Attaching on the name alone handed the second project
 * the first one's container — its published port, its bearer token, its mounted data — silently.
 * A running container whose recorded directory is not ours is refused by name instead: removing it
 * would kill a stack another project is actively using, so the user, who can see both, decides.
 */
export function decideAttach(existing: ContainerSummary[], hostProjectDir: string): AttachDecision {
  if (existing.length === 0) return { kind: "none" };
  const mine = existing.filter((c) => sameHostDir(c.Labels?.[LABEL_HOST_DIR], hostProjectDir));
  const foreign = existing.filter((c) => !mine.includes(c));
  const foreignRunning = foreign.find((c) => c.State === "running");
  if (foreignRunning) {
    const name = foreignRunning.Names[0]?.replace(/^\//, "") ?? foreignRunning.Id.slice(0, 12);
    const other = foreignRunning.Labels?.[LABEL_HOST_DIR] ?? "an unrecorded directory";
    return { kind: "refuse", reason: `the container ${name} carries this project's name but was started for ${other}; stop or remove it, then try again` };
  }
  const warnings = foreign.map((c) => `ignoring ${c.Id.slice(0, 12)} — same project name, different host directory (${c.Labels?.[LABEL_HOST_DIR] ?? "unrecorded"})`);
  const running = mine.find((c) => c.State === "running");
  return running ? { kind: "attach", container: running, warnings } : { kind: "recreate", warnings };
}

/**
 * Why a running container cannot serve this `start()`'s options, or `null` when it can.
 *
 * Docker's actual mounts establish checkout identity; a stale TIT_REPO_DIR marker cannot.
 * Environment inspection checks import precedence, reload and the selected UI directory.
 *
 * Pure and exported so `tests/unit/dev-stack.test.ts` can pin every branch without Docker.
 */
export function describeMismatch(
  state: { env: Record<string, string>; mounts?: { Type: string; Source: string; Destination: string }[] },
  image: string,
  want: Pick<StackStartOptions, "imageTag" | "repoDir" | "serverReload" | "staticDir">,
): string | null {
  const show = (value: string): string => value || "(none)";
  const wantRepo = want.repoDir ?? "";
  const repoMount = state.mounts?.find((mount) => mount.Destination === "/ti-toolbox");
  const haveRepo = repoMount?.Source ?? "";
  if (wantRepo && repoMount?.Type !== "bind") return `it mounts ${show(haveRepo)} at /ti-toolbox without the requested checkout bind, this run wants ${wantRepo}`;
  if (!sameHostDir(haveRepo, wantRepo) && haveRepo !== wantRepo) return `it mounts ${show(haveRepo)} at /ti-toolbox, this run wants ${show(wantRepo)}`;
  if (wantRepo && state.env.PYTHONPATH?.split(":")[0] !== "/ti-toolbox")
    return "its PYTHONPATH does not put /ti-toolbox first, so the installed package may shadow this checkout";
  const wantReload = want.serverReload ? "1" : "";
  const haveReload = state.env.TIT_SERVER_RELOAD ?? "";
  if (haveReload !== wantReload) return `it has TIT_SERVER_RELOAD=${show(haveReload)}, this run wants ${show(wantReload)}`;
  const wantStatic = want.staticDir ?? "";
  const haveStatic = state.env.TIT_STATIC_DIR ?? "";
  if (haveStatic !== wantStatic)
    return `it serves its UI from ${show(haveStatic) === "(none)" ? "the image's baked bundle" : show(haveStatic)}, this run wants ${show(wantStatic) === "(none)" ? "the image's baked bundle" : show(wantStatic)}`;
  if (want.imageTag && !image.endsWith(`:${want.imageTag}`)) return `it runs ${image}, this run wants tag ${want.imageTag}`;
  // The published port is deliberately NOT compared. `preferredPort` is where `findFreePort` starts
  // looking, not a promise: measured on 2026-09-03, ports 8766-8780 were held by another agent's
  // mock servers and a start asking for 8766 legitimately landed on 8781. Requiring an exact match
  // would then have recreated that container on every subsequent `npm run dev` — killing the
  // developer's running jobs to move a port number that nothing depends on, since the dev script
  // hands Vite and Electron whatever origin the container actually has.
  return null;
}

/** Names unfinished jobs; malformed replies cannot establish that recreation is safe. */
export function runningJobLabels(body: unknown): string[] {
  if (!Array.isArray(body)) throw new Error("Expected a job list");
  const finished = new Set(["succeeded", "failed", "cancelled"]);
  return body.map((job: unknown) => {
    if (typeof job !== "object" || job === null || !("state" in job) || typeof job.state !== "string")
      throw new Error("Invalid job in server reply");
    if (finished.has(job.state)) return null;
    const record = job as Record<string, unknown>;
    return `${String(record.kind ?? "job")} ${String(record.id ?? "?")}`;
  }).filter((label): label is string => label !== null);
}

/** One manager per host process. Electron main uses `./stackHost.ts`'s; the dev script its own. */
export function createStackManager(host: StackHost): StackManager {
  return new StackManager(host);
}

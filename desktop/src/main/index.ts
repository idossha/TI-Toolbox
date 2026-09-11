import { existsSync } from "node:fs";
import { stat, writeFile } from "node:fs/promises";
import { basename, isAbsolute, join, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { app, BrowserWindow, Notification, dialog, ipcMain, net, protocol, session, shell } from "electron";
import { initLog, log } from "./log";
import { readSettings, updateSettings, setAppleGpuEnabled } from "./settings";
import { LAUNCHER_ORIGIN, resolveRendererDir } from "./launcher";
import { checkToken, waitForHealth } from "./health";
import { nativeRuntime, resolveRuntime } from "./nativeRuntime";
import { FastSurferWorker } from "./fastsurferWorker";
import { installFastSurfer, probeFastSurfer, runtimePaths } from "./fastsurferInstall";
import { stack } from "./stackHost";
import { notifyJobCompletions, stopNotifyingJobCompletions } from "./jobsNotifier";
import {
  containerToHostPath,
  hasDotSegment,
  hostToContainerPath,
  mapContainerToHostViaProjectRoot,
  mapHostToContainerViaProjectRoot,
  type HostPlatform,
  type ProjectMount,
} from "../shared/paths";
import { createQuitGate } from "../shared/quitGate";
import { activeJobIds, runQuitPlan } from "../shared/quitPlan";
import { mayShowSystemUi, windowMode } from "./window";
import type {
  TitConnectArgs,
  TitConnectResult,
  TitSelectFileOptions,
  TitSaveFileOptions,
  TitSaveFileResult,
  TitStackEvent,
  TitStackStartResult,
  TitStackStatus,
  TitStackStopResult,
} from "../shared/tit-bridge";

const EXTERNAL_SCHEMES = new Set(["http:", "https:", "mailto:"]);

// Tests (and multiple dev instances) isolate their settings/log dirs.
if (process.env.TIT_USER_DATA_DIR) app.setPath("userData", process.env.TIT_USER_DATA_DIR);

protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

/** The one origin the main window may navigate within, besides the launcher. */
let serverOrigin: string | null = null;
let mainWindow: BrowserWindow | null = null;
/** The real backend origin + token of whatever we are currently connected to (never the dev-proxy
 * origin) — used for main-process API calls (jobs notifier, close-with-running-jobs check) that
 * do not go through the renderer's Vite proxy. */
let activeSession: { origin: string; token: string } | null = null;
/** See `quitGate.ts` for why this is an object `reset()` on every new window generation rather
 * than a plain boolean (rb_12 NEW issue: macOS `activate` reopening a window after the first
 * window's quit was approved must not inherit that approval). */
const quitGate = createQuitGate();
const fastSurferWorker = new FastSurferWorker();
let fastSurferInstalling = false;
let fastSurferInstalled: boolean | undefined;
let fastSurferProject: string | undefined;
let fastSurferError: string | undefined;
let fastSurferGeneration = 0;

function localFastSurferProject(): string | undefined {
  const current = stack.getCurrent();
  return current && activeSession?.origin === current.origin ? current.hostProjectDir : undefined;
}

async function fastSurferStatus() {
  const project = localFastSurferProject();
  const supported = process.platform === "darwin" && process.arch === "arm64" && !!project;
  if (fastSurferInstalled === undefined) fastSurferInstalled = supported && await probeFastSurfer(app.getPath("userData"));
  return { supported, preferenceEnabled: readSettings().appleGpuEnabled === true, installed: fastSurferInstalled, enabled: !!project && project === fastSurferProject && fastSurferWorker.status().running,
    installing: fastSurferInstalling, directory: runtimePaths(app.getPath("userData")).directory, project,
    error: fastSurferError ?? fastSurferWorker.status().error ?? undefined };
}

async function stopFastSurferWorker() {
  fastSurferGeneration++;
  await fastSurferWorker.stop();
  fastSurferProject = undefined;
}


async function resumeFastSurferWorker() {
  const project = localFastSurferProject();
  const generation = fastSurferGeneration;
  if (!project || !readSettings().appleGpuEnabled || process.platform !== "darwin" || process.arch !== "arm64") return;
  try {
    const ready = await probeFastSurfer(app.getPath("userData"));
    if (generation !== fastSurferGeneration || localFastSurferProject() !== project || !readSettings().appleGpuEnabled) return;
    fastSurferInstalled = ready;
    if (!ready) throw new Error("Apple GPU setup needs attention. Open Settings to enable it again.");
    await fastSurferWorker.start(project, runtimePaths(app.getPath("userData")));
    if (generation !== fastSurferGeneration || localFastSurferProject() !== project || !readSettings().appleGpuEnabled) return;
    fastSurferProject = project;
    fastSurferError = undefined;
  } catch (error) {
    if (generation === fastSurferGeneration) fastSurferError = error instanceof Error ? error.message : String(error);
  }
}

function isSameOrigin(url: string, origin: string | null): boolean {
  if (!origin) return false;
  try {
    return new URL(url).origin === origin;
  } catch {
    return false;
  }
}

function isLauncherUrl(url: string): boolean {
  return url === LAUNCHER_ORIGIN || url.startsWith(LAUNCHER_ORIGIN + "/");
}

/**
 * Strip the query string (and fragment) before a URL ever reaches `main.log`. The only URL this
 * app loads that carries a secret is `<origin>/auth/session?token=...` (`connect()` below) — if
 * that load fails, `did-fail-load` hands the full URL, token included, to its listener; logging it
 * verbatim would write the token to disk (ra_14 finding 8). Applied to every URL this file logs,
 * not only that one call site, since a future addition should not have to remember the rule.
 *
 * Deliberately a plain string split, not `new URL(url).origin + pathname`: for a non-special
 * scheme like this app's own privileged `app:` (`protocol.registerSchemesAsPrivileged`, not
 * something Node's URL parser knows about outside Electron's Chromium-side handling), `.origin`
 * evaluates to the literal string `"null"` per the WHATWG URL spec — that would make a blocked
 * `app://evil/` navigation log as `null/`, throwing away exactly the host a reader needs to see.
 */
function stripQueryForLog(url: string): string {
  return url.split(/[?#]/)[0] ?? url;
}

function openExternalIfWeb(url: string): void {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return;
  }
  if (EXTERNAL_SCHEMES.has(parsed.protocol)) {
    log("info", `openExternal ${parsed.origin}`);
    void shell.openExternal(parsed.href);
  } else {
    log("warn", `refused openExternal for scheme ${parsed.protocol}`);
  }
}

function parseServerUrl(raw: string): URL {
  const url = new URL(raw);
  if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("Server URL must be http(s)");
  return url;
}

async function connect(win: BrowserWindow, args: TitConnectArgs): Promise<TitConnectResult> {
  let url: URL;
  try {
    url = parseServerUrl(args.url);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
  if (!args.token) return { ok: false, error: "A token is required" };
  try {
    await waitForHealth(url.origin);
    await checkToken(url.origin, args.token);
  } catch (err) {
    log("warn", err instanceof Error ? err.message : String(err));
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
  await stopFastSurferWorker();
  fastSurferInstalled = undefined;
  updateSettings({ lastServerUrl: url.origin });
  delete process.env.TIT_DEV_PROJECT_DIR;
  // In dev the page comes from Vite (HMR) which proxies /api, /auth and /ws to the server.
  const pageOrigin = process.env.ELECTRON_RENDERER_URL && !(!app.isPackaged && process.env.TIT_DEV_LAUNCHER === "1") ? new URL(process.env.ELECTRON_RENDERER_URL).origin : url.origin;
  serverOrigin = pageOrigin;
  activeSession = { origin: url.origin, token: args.token };
  projectRootCache = null; // A new session may point at a different project.
  void resumeFastSurferWorker();
  notifyJobCompletions(url.origin, args.token);
  log("info", `connected to ${url.origin}; loading session from ${pageOrigin}`);
  // The server sets the HttpOnly cookie and 303s to "/"; the token is in this URL exactly once.
  void win.loadURL(`${pageOrigin}/auth/session?token=${encodeURIComponent(args.token)}`);
  return { ok: true };
}

/**
 * The renderer bundle for a natively-spawned `tit.server` to serve as `--static-dir` (N0.4 spike).
 * Unlike the Docker path — where the image carries its own copy of the UI — a native child process
 * is a plain OS process with no `asar` access, so the built `out/renderer` tree must be a real
 * directory it can read: `electron-builder.yml`'s `extraResources` copies it to
 * `resourcesPath/renderer` for a packaged app; `app.getAppPath()/out/renderer` covers `electron-vite
 * build` run straight from this worktree (`npm run e2e`'s own `pree2e` step, and this spike's own
 * unpacked-dir e2e leg).
 */
function resolveNativeStaticDir(): string | undefined {
  return resolveRendererDir(process.resourcesPath, __dirname, app.getAppPath());
}

/**
 * N0.4 spike hook: when a bundled/pointed-at native Python runtime is available (packaged
 * `resources/runtime/<platform-arch>`, or `TIT_NATIVE_RUNTIME_DIR` for dev/e2e) AND
 * `TIT_NATIVE_PROJECT_DIR` names a project directory, spawn `tit.server` directly and connect —
 * bypassing the launcher form entirely, the way a native install's first run should feel. Every
 * existing path is untouched: with neither set (every user today, and every other spec in this
 * suite) this is a no-op and `showLauncher` runs exactly as before, Docker button included.
 */
async function tryNativeAutoStart(win: BrowserWindow): Promise<boolean> {
  if (!app.isPackaged && process.env.TIT_DEV_LAUNCHER === "1") return false;
  const projectDir = process.env.TIT_NATIVE_PROJECT_DIR;
  if (!projectDir) return false;
  if (!resolveRuntime().ok) return false;
  const result = await nativeRuntime.start(projectDir, resolveNativeStaticDir());
  if (!result.ok) {
    log("error", `native runtime auto-start failed: ${result.error}`);
    return false;
  }
  const connected = await connect(win, { url: result.url, token: result.token });
  if (!connected.ok) {
    log("error", `native runtime connect failed: ${connected.error}`);
    return false;
  }
  return true;
}

/**
 * `npm run dev` (scripts/dev.ts) has already brought the container up, recovered its token and
 * started Vite with that token stamped onto every proxied request. Explicit host/dev handoffs
 * connect directly; the default desktop development mode opens Overview first.
 *
 * Unpackaged only. A packaged app must never be steerable into an arbitrary server by an
 * environment variable a user's shell happens to carry, and `TIT_DEV_SERVER_URL` is a name a
 * developer might well leave exported.
 */
async function tryDevAutoConnect(win: BrowserWindow): Promise<boolean> {
  if (!app.isPackaged && process.env.TIT_DEV_LAUNCHER === "1") return false;
  const containerId = process.env.TIT_LAUNCH_CONTAINER_ID;
  const projectDir = process.env.TIT_LAUNCH_PROJECT_DIR;
  if (containerId || projectDir) {
    try {
      const result = containerId ? await stack.adopt(containerId) : await stack.start(projectDir!, { ...desktopStartOptions(), ...(process.env.TIT_LAUNCH_IMAGE ? { image: process.env.TIT_LAUNCH_IMAGE } : {}), ...(process.env.TIT_LAUNCH_PORT ? { preferredPort: Number(process.env.TIT_LAUNCH_PORT) } : {}) });
      if (!result.ok) throw new Error(result.error);
      const connected = await connect(win, { url: result.url, token: result.token });
      if (!connected.ok) throw new Error(connected.error);
      return true;
    } catch (error) {
      log("error", `Could not open TI-Toolbox: ${String(error)}`);
      if (mayShowSystemUi(WINDOW_MODE)) await dialog.showMessageBox(win, { type: "error", message: "Could not open TI-Toolbox", detail: String(error) });
      return false;
    } finally {
      // CLI selection applies only to this handoff, never later project switches.
      for (const key of ["TIT_LAUNCH_CONTAINER_ID", "TIT_LAUNCH_PROJECT_DIR", "TIT_LAUNCH_EXISTING", "TIT_LAUNCH_CONTAINER"]) delete process.env[key];
    }
  }
  if (app.isPackaged) return false;
  const url = process.env.TIT_DEV_SERVER_URL;
  const token = process.env.TIT_DEV_SERVER_TOKEN;
  if (!url || !token) return false;
  const connected = await connect(win, { url, token });
  if (!connected.ok) {
    log("error", `dev auto-connect to ${url} failed: ${connected.error}`);
    return false;
  }
  log("info", `dev auto-connect to ${url}`);
  return true;
}

async function clearProjectMirrors(win: BrowserWindow): Promise<void> {
  if (activeSession) {
    // These are project data mirrors; retain theme, layout and editor preferences.
    try {
      await win.webContents.executeJavaScript(`(() => {
        for (const key of Object.keys(localStorage)) {
          if (["tit.viewer.recents", "tit-enabled-panels", "tit-enabled-panels-synced"].includes(key) || key.startsWith("tit-subject:")) localStorage.removeItem(key);
        }
      })()`);
    } catch (error) { log("warn", `Could not clear project selection mirrors: ${String(error)}`); }
  }
}

async function showLauncher(win: BrowserWindow, error?: string): Promise<void> {
  await clearProjectMirrors(win);
  serverOrigin = null;
  activeSession = null;
  projectRootCache = null;
  stopNotifyingJobCompletions();
  void win.loadURL(`${LAUNCHER_ORIGIN}/${error ? `?error=${encodeURIComponent(error)}` : ""}`);
}

/** Narrows `process.platform` (which also allows aix/freebsd/...) to the three `paths.ts` handles. */
function toHostPlatform(platform: NodeJS.Platform): HostPlatform {
  if (platform === "darwin" || platform === "win32") return platform;
  return "linux"; // Every other Unix behaves like Linux for path-mapping purposes (case-sensitive).
}

/**
 * `GET /api/project`, cached per session — fetched through main (never the renderer, R5) with the
 * bearer token, the same way `getRunningJobsCount` reaches the server without going through the
 * renderer's Vite proxy. Used only as `resolveHostPathStrict`/`resolveContainerPathForBrowse`'s
 * fallback when this app did not itself start the stack (no `ProjectMount` from
 * `stack.getCurrent()`), so a manually-connected external server's own `host_path` (when it knows
 * one) can still resolve `openPath`/`showItemInFolder`/`selectFile`.
 */
let projectRootCache: { origin: string; containerPath: string; hostPath: string | null } | null = null;

async function getProjectRoot(): Promise<{ containerPath: string; hostPath: string | null } | null> {
  if (!activeSession) return null;
  if (projectRootCache && projectRootCache.origin === activeSession.origin) return projectRootCache;
  try {
    const res = await net.fetch(`${activeSession.origin}/api/project`, {
      headers: { authorization: `Bearer ${activeSession.token}` },
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    const project = (await res.json()) as { container_path: string; host_path?: string | null };
    projectRootCache = { origin: activeSession.origin, containerPath: project.container_path, hostPath: project.host_path ?? null };
    return projectRootCache;
  } catch (err) {
    log("warn", `could not fetch /api/project for path mapping: ${err instanceof Error ? err.message : String(err)}`);
    return null;
  }
}

export type PathResolveResult = { ok: true; path: string } | { ok: false; reason: string };

/**
 * Container path (as given by the server) -> host path, for `openPath`/`showItemInFolder`
 * (ra_14 finding 3). Rejects outright — never normalises — any path containing a literal `.` or
 * `..` segment, so a traversal can never reach `shell.openPath`/`shell.showItemInFolder`. Only
 * resolves a path that maps into a *known* mount: the one this app itself started
 * (`stack.getCurrent()`, the `/mnt/<name>` convention) or, when there is none — a
 * manually-connected external server, or one launched outside the compose stack — `GET
 * /api/project`'s own `container_path`/`host_path` (`Project.host_path`: "from LOCAL_PROJECT_DIR
 * when known"), fetched through main with the bearer token, never the renderer. Both mapping
 * functions only ever construct the host path by appending the remaining segments onto the
 * mount's own host root, so a path that has already passed the dot-segment check cannot resolve to
 * anything outside that root. Anything that does not map is refused with `{ok:false, reason}`
 * instead of falling back to the unmapped path — the caller must never hand an un-jailed string to
 * the shell.
 */
async function resolveHostPathStrict(pathFromServer: string): Promise<PathResolveResult> {
  if (hasDotSegment(pathFromServer)) return { ok: false, reason: "path contains a '.' or '..' segment" };
  const current = stack.getCurrent();
  if (current) {
    const mount: ProjectMount = { hostDir: current.hostProjectDir, platform: toHostPlatform(process.platform) };
    const mapped = containerToHostPath(pathFromServer, mount);
    if (mapped) return { ok: true, path: mapped };
    return { ok: false, reason: "path is outside the mounted project" };
  }
  const project = await getProjectRoot();
  if (project) {
    const mapped = mapContainerToHostViaProjectRoot(pathFromServer, project.containerPath, project.hostPath, toHostPlatform(process.platform));
    if (mapped) return { ok: true, path: mapped };
    return { ok: false, reason: "path is outside the project" };
  }
  return { ok: false, reason: "no known project mount to resolve this path against" };
}

/**
 * The reverse mapping, for the file/directory picker (`tit:selectFile` — ra_13 finding 8): a host
 * path the user just picked in a native dialog -> the container path a `PathInput` field expects.
 * Same known-mount preference as `resolveHostPathStrict`. Returns `null` (not an error object —
 * the caller logs the reason and falls back to the OS-picker returning nothing, matching
 * `selectDirectory`'s existing "cancelled" contract) when the picked path is outside every known
 * mount, so a page can never receive a host path it has no business seeing.
 */
async function resolveContainerPathForBrowse(hostPath: string): Promise<string | null> {
  const current = stack.getCurrent();
  if (current) {
    const mount: ProjectMount = { hostDir: current.hostProjectDir, platform: toHostPlatform(process.platform) };
    const mapped = hostToContainerPath(hostPath, mount);
    if (mapped) return mapped;
    log("warn", "selectFile: chosen path is outside the mounted project");
    return null;
  }
  const project = await getProjectRoot();
  if (project) {
    const mapped = mapHostToContainerViaProjectRoot(hostPath, project.containerPath, project.hostPath, toHostPlatform(process.platform));
    if (mapped) return mapped;
    log("warn", "selectFile: chosen path is outside the project");
    return null;
  }
  log("warn", "selectFile: no known project mount to map the chosen path into");
  return null;
}

async function getRunningJobIds(): Promise<string[]> {
  if (!activeSession) return [];
  try {
    const res = await net.fetch(`${activeSession.origin}/api/jobs`, {
      headers: { authorization: `Bearer ${activeSession.token}` },
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) throw new Error(`Jobs request failed: HTTP ${res.status}`);
    const jobs = (await res.json()) as unknown;
    return activeJobIds(jobs);
  } catch (err) {
    log("warn", `could not check running jobs before quit: ${err instanceof Error ? err.message : String(err)}`);
    throw err;
  }
}

async function cancelJobOnQuit(id: string): Promise<void> {
  if (!activeSession) return;
  try {
    await net.fetch(`${activeSession.origin}/api/jobs/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
      headers: { authorization: `Bearer ${activeSession.token}` },
      signal: AbortSignal.timeout(5000),
    });
  } catch (err) {
    log("warn", `could not cancel job ${id} on quit: ${err instanceof Error ? err.message : String(err)}`);
  }
}

const QUIT_WATCHDOG_MS = 4000;

/**
 * `app.quit()`, with a hard `app.exit(0)` fallback if the process is still alive after
 * `QUIT_WATCHDOG_MS`. Observed need (with the CLI-based stack this replaced): once `stack.stop()`
 * had run a second `execFile` docker invocation, a subsequent `app.quit()` reliably stopped
 * completing on macOS/Electron 44 even though every window closed and no JS handle kept the event
 * loop alive. That specific trigger is gone with the CLI — the Engine API client spawns no child
 * processes at all — but the watchdog stays: a real user must never be stuck unable to quit
 * because they stopped a stack first, and `app.exit()` skips the graceful `before-quit`/
 * window-close path entirely, which is exactly what "unblock a stuck quit" needs.
 */
function quitWithWatchdog(): void {
  const watchdog = setTimeout(() => {
    log("warn", `app.quit() did not complete within ${QUIT_WATCHDOG_MS}ms; forcing app.exit(0)`);
    app.exit(0);
  }, QUIT_WATCHDOG_MS);
  watchdog.unref();
  app.quit();
}

/** Stop the selected Docker/native runtime before closing; failures keep the window open. */
async function handleQuitRequest(triggerWindow: BrowserWindow | null, proceed: () => void, closeProject = false, confirmedSwitch = false): Promise<void> {
  const current = stack.getCurrent();
  const owner = triggerWindow ?? mainWindow ?? undefined;
  let mayQuit: boolean;
  try { mayQuit = await runQuitPlan(
    { docker: current !== null && current !== undefined, native: nativeRuntime.getCurrent() !== null },
    {
      listRunningJobs: getRunningJobIds,
      cancelJob: cancelJobOnQuit,
      confirm: async (dialogSpec) => {
        if (confirmedSwitch) return 1; // The destination dialog already authorizes stopping jobs.
        const options: Electron.MessageBoxOptions = {
          type: "question", ...dialogSpec,
          ...(closeProject ? {
            buttons: dialogSpec.buttons.map((label) => label === "Stop jobs and quit" ? "Stop jobs and close project" : label),
            detail: "Closing this project stops its container and cancels running and queued jobs, then returns to Overview so you can choose another project. Project files and named volumes are preserved.",
          } : {}),
        };
        const result = owner ? await dialog.showMessageBox(owner, options) : await dialog.showMessageBox(options);
        return result.response;
      },
      stopDocker: async () => {
        const result = await stack.stop();
        if (!result.ok) throw new Error(result.error);
      },
      stopNative: () => nativeRuntime.stop().catch((err) => log("error", `nativeRuntime.stop on quit failed: ${String(err)}`)),
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      now: () => Date.now(),
    },
  );
  } catch (error) {
    log("error", `Could not shut down: ${String(error)}`);
    const options: Electron.MessageBoxOptions = { type: "error", message: "Could not stop TI-Toolbox", detail: `${String(error)}. The app remains open; retry closing after resolving the error.` };
    if (owner) await dialog.showMessageBox(owner, options); else await dialog.showMessageBox(options);
    return;
  }
  if (!mayQuit) return;
  await stopFastSurferWorker();
  stopNotifyingJobCompletions();
  quitGate.approve();
  proceed();
}

function desktopStartOptions() {
  if (process.env.TIT_DEV_REPO_DIR) return { repoDir: process.env.TIT_DEV_REPO_DIR, staticDir: "/ti-toolbox/desktop/out/renderer", serverReload: true };
  if (app.isPackaged || process.env.TIT_DEV_LAUNCHER !== "1") return {};
  const port = Number(process.env.TIT_DEV_PORT || 8765);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("TIT_DEV_PORT must be a port number from 1 to 65535.");
  return {
    ...(process.env.TIT_DEV_IMAGE_TAG ? { imageTag: process.env.TIT_DEV_IMAGE_TAG } : {}),
    ...(process.env.TIT_DEV_PORT ? { preferredPort: Number(process.env.TIT_DEV_PORT) } : {}),
    serverReload: true,
  };
}

let switchingProject = false;
async function switchProject(target?: string): Promise<TitStackStopResult> {
  if (!mainWindow || switchingProject) return { ok: false, error: "A project transition is already in progress." };
  switchingProject = true;
  let switched = false;
  try {
    if (target !== undefined) {
      target = target.trim();
      if (!isAbsolute(target)) return { ok: false, error: "Enter an absolute project directory path." };
      try {
        if (!(await stat(target)).isDirectory()) return { ok: false, error: "Select a project directory, not a file." };
      } catch { return { ok: false, error: `Project directory does not exist: ${target}` }; }
      try { await stack.validateStart(target, desktopStartOptions()); }
      catch (error) { return { ok: false, error: error instanceof Error ? error.message : String(error) }; }
      // A server-rendered page cannot silently request a new host mount. The native dialog
      // confirms the exact destination before granting that capability.
      const choice = await dialog.showMessageBox(mainWindow, {
        type: "question", message: "Switch project?",
        detail: `Open ${target}\n\nThe current project's container and any running or queued jobs will stop. Project files are preserved.`,
        buttons: ["Cancel", "Switch project"], defaultId: 1, cancelId: 0,
      });
      if (choice.response !== 1) return { ok: false, error: "Project switch cancelled." };
    }
    await handleQuitRequest(mainWindow, () => { quitGate.reset(); switched = true; }, true, target !== undefined);
    if (!switched) return { ok: false, error: "Project switch cancelled or the container could not be stopped." };
    if (target === undefined) {
      void showLauncher(mainWindow);
      return { ok: true };
    }
    await clearProjectMirrors(mainWindow);
    updateSettings({ lastProjectDir: target });
    const result = await stack.start(target, desktopStartOptions());
    if (!result.ok) { void showLauncher(mainWindow, result.error); return result; }
    const connected = await connect(mainWindow, { url: result.url, token: result.token });
    if (!connected.ok) { void showLauncher(mainWindow, connected.error); return connected; }
    return { ok: true };
  } finally {
    switchingProject = false;
  }
}

/**
 * Whether this launch may reach the user's screen (`./window.ts`). Read once: the env cannot
 * change under a running process, and every site that asks has to get the same answer.
 */
const WINDOW_MODE = windowMode();

// An offscreen launch is a test run, and a test run must leave the dock alone too — a bouncing
// icon is a monitor hijack even when no window is shown. `dock` exists on darwin only, and
// `hide()` is a no-op if the app never became dock-resident, so this is safe to call unguarded
// beyond the platform check Electron already does by leaving `dock` undefined elsewhere.
if (WINDOW_MODE === "offscreen") app.dock?.hide();

function createWindow(): BrowserWindow {
  // A new window generation starts unapproved, even if an earlier (now-closed) window's quit was
  // already approved — macOS `activate` reopens a window this way after `window-all-closed`
  // leaves the app running with none, and that new window's own close/before-quit must run the
  // running-jobs prompt again, not inherit the previous window's approval.
  quitGate.reset();
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1024,
    minHeight: 680,
    title: "TI-Toolbox",
    show: false,
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  });
  // The one behavioural difference of `'offscreen'`: `show()` is never called, so the window
  // exists, loads the renderer and answers CDP, but never reaches the screen or the window
  // server's focus chain. `ready-to-show` still fires; only the reaction to it is suppressed.
  if (WINDOW_MODE === "normal") win.once("ready-to-show", () => win.show());

  // Navigation guard: only the launcher and the connected server origin, nothing else.
  win.webContents.on("will-navigate", (event, url) => {
    if (isLauncherUrl(url) || isSameOrigin(url, serverOrigin)) return;
    event.preventDefault();
    log("warn", `blocked navigation to ${stripQueryForLog(url)}`);
    openExternalIfWeb(url);
  });
  win.webContents.on("will-redirect", (event, url) => {
    if (isLauncherUrl(url) || isSameOrigin(url, serverOrigin)) return;
    event.preventDefault();
    log("warn", `blocked redirect to ${stripQueryForLog(url)}`);
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    // A same-origin `window.open` (server-served pages open artifact/report URLs this way, e.g.
    // `results/index.tsx`) opens a child window instead of the OS browser (ra_14 finding 13): the
    // system browser has no session cookie, so it would just 401. The child gets the same hardened
    // webPreferences as the main window and no preload — it never needs `window.tit`.
    if (isSameOrigin(url, serverOrigin)) {
      return {
        action: "allow",
        overrideBrowserWindowOptions: {
          webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false, webSecurity: true },
        },
      };
    }
    openExternalIfWeb(url);
    return { action: "deny" };
  });
  win.webContents.on("did-create-window", (child) => guardChildWindow(child));
  win.webContents.on("did-fail-load", (_e, code, desc, url, isMainFrame) => {
    if (isMainFrame && code !== -3) log("error", `did-fail-load ${code} ${desc} ${stripQueryForLog(url)}`);
  });
  win.on("close", (event) => {
    if (quitGate.isApproved()) return;
    event.preventDefault();
    void handleQuitRequest(win, quitWithWatchdog);
  });
  win.on("closed", () => {
    mainWindow = null;
  });
  return win;
}

/**
 * Wires the same navigation guard onto a child window opened via `window.open` (`createWindow`'s
 * `setWindowOpenHandler` "allow" branch, ra_14 finding 13) — it only ever loads one same-origin
 * URL and has no location bar, but nothing stops its own content from trying to navigate further,
 * so it gets the identical origin allowlist rather than none at all.
 */
function guardChildWindow(win: BrowserWindow): void {
  win.webContents.on("will-navigate", (event, url) => {
    if (isLauncherUrl(url) || isSameOrigin(url, serverOrigin)) return;
    event.preventDefault();
    log("warn", `blocked navigation to ${stripQueryForLog(url)} in a child window`);
    openExternalIfWeb(url);
  });
  win.webContents.on("will-redirect", (event, url) => {
    if (isLauncherUrl(url) || isSameOrigin(url, serverOrigin)) return;
    event.preventDefault();
    log("warn", `blocked redirect to ${stripQueryForLog(url)} in a child window`);
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    openExternalIfWeb(url);
    return { action: "deny" };
  });
}

function registerIpc(): void {
  const fromMainWindow = (e: Electron.IpcMainInvokeEvent) => mainWindow !== null && e.sender === mainWindow.webContents;
  /**
   * Restricts a handler to the local launcher page (`app://launcher`), never the server-served
   * page loaded into the same window after `connect()` (ra_14 finding 4). `tit:connect` already
   * did this for the manual-connect path; the same check now also covers everything that can
   * mount an arbitrary host directory + docker.sock (`stack:start`)
   * or seed the next launch's defaults (`setSettings`, e.g. `lastProjectDir`). A
   * server-served page may still call `getSettings`, `openExternal`, `openPath`,
   * `showItemInFolder`, `notify`, `platform`, `appVersion`, `stack:status` and `stack:stop`.
   * Project switching additionally permits the native directory picker; a destination mount
   * requires native confirmation of the exact path before shutdown/start.
   *
   * `stack:stop` is deliberately NOT launcher-only (unlike `stack:start`). The page that can call
   * it is served *by the container it would stop*, so the only thing it can reach is its own
   * lifetime — no other project, no host path, no new mount. Leaving it launcher-only is what left
   * the connected app with no way to stop the stack it is talking to at all (QA engineer finding
   * 6): the running container survived every quit with nothing on screen saying so, and the only
   * remedy was `docker stop` in a terminal.
   */
  const fromLauncherWindow = (e: Electron.IpcMainInvokeEvent) => fromMainWindow(e) && isLauncherUrl(e.senderFrame?.url ?? "");

  ipcMain.handle("tit:fastsurfer:status", async (e) => {
    if (!fromMainWindow(e)) return { supported: false, preferenceEnabled: false, installed: false, enabled: false, installing: false };
    return fastSurferStatus();
  });
  ipcMain.handle("tit:fastsurfer:enable", async (e) => {
    if (!fromMainWindow(e) || !mainWindow) return { supported: false, preferenceEnabled: false, installed: false, enabled: false, installing: false };
    const before = await fastSurferStatus();
    if (!before.supported || !before.project || fastSurferInstalling) return before;
    const project = before.project;
    const generation = fastSurferGeneration;
    const confirmation = await dialog.showMessageBox(mainWindow, {
      type: "question", title: "Enable Apple GPU FastSurfer",
      message: before.installed ? "Enable Apple GPU for your TI-Toolbox user?" : "Install FastSurfer and enable Apple GPU?",
      detail: `FastSurfer will use your Mac’s GPU. Setup is stored in your TI-Toolbox user folder and does not require administrator access.\n\nThis preference applies across your local projects. Each job can access only the active project and its required runtime files. Computation has no network access. You can turn this off in Settings at any time.\n\nInstallation folder:\n${before.directory}`,
      buttons: ["Enable Apple GPU", "Cancel"], defaultId: 1, cancelId: 1,
    });
    if (confirmation.response !== 0 || generation !== fastSurferGeneration || localFastSurferProject() !== project || fastSurferInstalling) return fastSurferStatus();
    fastSurferInstalling = true;
    fastSurferError = undefined;
    try {
      const runtime = await installFastSurfer(app.getPath("userData"), (text) => log("info", `[fastsurfer-install] ${text.trim()}`));
      fastSurferInstalled = true;
      if (generation !== fastSurferGeneration || localFastSurferProject() !== project) throw new Error("Native FastSurfer approval ended during installation. Enable it again for the current project.");
      await fastSurferWorker.start(project, runtime);
      if (generation !== fastSurferGeneration || localFastSurferProject() !== project) { await stopFastSurferWorker(); throw new Error("Native FastSurfer approval ended during startup."); }
      setAppleGpuEnabled(true);
      fastSurferProject = project;
    } catch (error) { fastSurferError = error instanceof Error ? error.message : String(error); }
    finally { fastSurferInstalling = false; }
    return fastSurferStatus();
  });
  ipcMain.handle("tit:fastsurfer:disable", async (e) => {
    if (!fromMainWindow(e)) return { supported: false, preferenceEnabled: false, installed: false, enabled: false, installing: false };
    setAppleGpuEnabled(false);
    await stopFastSurferWorker();
    fastSurferError = undefined;
    return fastSurferStatus();
  });
  ipcMain.handle("tit:appVersion", () => app.getVersion());
  ipcMain.handle("tit:openExternal", (e, url: unknown) => {
    if (!fromMainWindow(e)) return;
    openExternalIfWeb(String(url));
  });
  ipcMain.handle("tit:connect", async (e, args: unknown): Promise<TitConnectResult> => {
    if (!fromMainWindow(e) || !mainWindow) return { ok: false, error: "unknown sender" };
    if (args === null || args === undefined) {
      return switchProject();
    }
    // Only the local launcher page may initiate a connection (it is the only page holding a token).
    if (!isLauncherUrl(e.senderFrame?.url ?? "")) return { ok: false, error: "connect is only allowed from the launcher" };
    const a = args as Partial<TitConnectArgs>;
    return connect(mainWindow, { url: String(a.url ?? ""), token: String(a.token ?? "") });
  });
  ipcMain.handle("tit:getSettings", (e) => {
    if (!fromMainWindow(e)) return {};
    const settings = readSettings();
    return !app.isPackaged && process.env.TIT_DEV_PROJECT_DIR ? { ...settings, lastProjectDir: process.env.TIT_DEV_PROJECT_DIR } : settings;
  });
  ipcMain.handle("tit:setSettings", (e, partial: unknown) => (fromLauncherWindow(e) ? updateSettings(partial) : {}));

  ipcMain.handle("tit:selectDirectory", async (e): Promise<string | undefined> => {
    if (!fromMainWindow(e) || !mainWindow) return undefined;
    const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory", "createDirectory"] });
    if (result.canceled || result.filePaths.length === 0) return undefined;
    void updateSettings({ lastProjectDir: result.filePaths[0] });
    return result.filePaths[0];
  });
  ipcMain.handle("tit:selectFile", async (e, options: unknown): Promise<string | undefined> => {
    // Deliberately still callable from a server-served page (unlike selectDirectory above): pages'
    // `PathInput` "Browse…" (ra_13 finding 8) is a real, in-use feature (`pages/viewer/index.tsx`).
    // What changed here is not who may call it but what it returns — a *container* path mapped
    // through the known project mount, never the raw host path the OS dialog produced.
    if (!fromMainWindow(e) || !mainWindow) return undefined;
    const opts = (options ?? {}) as TitSelectFileOptions;
    const result = await dialog.showOpenDialog(mainWindow, { properties: ["openFile"], filters: opts.filters });
    if (result.canceled || result.filePaths.length === 0) return undefined;
    const hostPath = result.filePaths[0];
    if (hostPath === undefined) return undefined;
    const containerPath = await resolveContainerPathForBrowse(hostPath);
    return containerPath ?? undefined;
  });
  ipcMain.handle(
    "tit:saveFile",
    async (e, text: unknown, options: unknown): Promise<TitSaveFileResult> => {
      // Save-as for renderer-produced text (the Pipeline page's exported notebook). A renderer
      // cannot save a file itself here -- an `<a download>` on a blob: URL needs a download
      // handler this app does not install, so the click silently did nothing.
      //
      // The renderer never names a path. It suggests a *basename*, `basename()` strips any
      // directory out of even that, and the OS dialog is what decides where the bytes go -- so
      // this handler cannot be talked into writing to a path of the page's choosing.
      if (!fromMainWindow(e) || !mainWindow) return { ok: false, reason: "unknown sender" };
      const opts = (options ?? {}) as TitSaveFileOptions;
      const suggested = basename(String(opts.defaultName ?? "untitled.txt")) || "untitled.txt";
      const result = await dialog.showSaveDialog(mainWindow, {
        defaultPath: suggested,
        filters: opts.filters,
      });
      if (result.canceled || !result.filePath) return { ok: false, canceled: true };
      try {
        await writeFile(result.filePath, String(text), "utf8");
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) };
      }
      return { ok: true, path: result.filePath };
    },
  );
  ipcMain.handle("tit:openPath", async (e, path: unknown): Promise<{ ok: boolean; reason?: string }> => {
    if (!fromMainWindow(e)) return { ok: false, reason: "unknown sender" };
    const resolved = await resolveHostPathStrict(String(path));
    if (!resolved.ok) return resolved;
    const err = await shell.openPath(resolved.path);
    return err ? { ok: false, reason: err } : { ok: true };
  });
  ipcMain.handle("tit:showItemInFolder", async (e, path: unknown): Promise<{ ok: boolean; reason?: string }> => {
    if (!fromMainWindow(e)) return { ok: false, reason: "unknown sender" };
    const resolved = await resolveHostPathStrict(String(path));
    if (!resolved.ok) return resolved;
    shell.showItemInFolder(resolved.path);
    return { ok: true };
  });
  ipcMain.handle("tit:notify", (e, title: unknown, body: unknown) => {
    if (!fromMainWindow(e)) return;
    if (!Notification.isSupported()) return;
    // A banner is composited over whatever the developer is doing, so an offscreen run stays
    // silent as well as invisible (`./window.ts`). `jobsNotifier` fires these on a timer, which
    // is precisely the case that would otherwise pepper a long E2E run with notifications.
    if (!mayShowSystemUi(WINDOW_MODE)) return;
    new Notification({ title: String(title ?? "TI-Toolbox"), body: body ? String(body) : undefined }).show();
  });

  ipcMain.handle("tit:stack:start", async (e, hostProjectDir: unknown): Promise<TitStackStartResult> => {
    if (!fromLauncherWindow(e) || !mainWindow) return { ok: false, error: "unknown sender" };
    const result = await stack.start(String(hostProjectDir ?? ""), desktopStartOptions());
    if (!result.ok) return result;
    const connected = await connect(mainWindow, { url: result.url, token: result.token });
    if (!connected.ok) return connected;
    return { ok: true, attached: result.attached };
  });
  ipcMain.handle("tit:stack:switchProject", async (e, target: unknown): Promise<TitStackStopResult> => {
    if (!fromMainWindow(e) || !mainWindow) return { ok: false, error: "unknown sender" };
    if (target !== undefined && typeof target !== "string") return { ok: false, error: "Invalid project directory." };
    return switchProject(target);
  });
  ipcMain.handle("tit:stack:stop", async (e): Promise<TitStackStopResult> => {
    if (!fromMainWindow(e)) return { ok: false, error: "unknown sender" };
    const fromLauncher = isLauncherUrl(e.senderFrame?.url ?? "");
    await stopFastSurferWorker();
    const result = await stack.stop();
    // Stopping from Settings kills the server that served the page making the call, so the window
    // is left showing a page whose backend no longer exists. Send it home rather than leaving the
    // user staring at a dead UI; the launcher path already is home.
    if (result.ok && !fromLauncher && mainWindow) showLauncher(mainWindow);
    return result;
  });
  ipcMain.handle("tit:stack:status", async (e): Promise<TitStackStatus> => {
    if (!fromMainWindow(e)) return { running: false };
    const status = await stack.status();
    return {
      running: status.running,
      hostProjectDir: status.hostProjectDir,
      port: status.port,
      containerName: status.containerName,
      image: status.image,
      health: status.health,
    };
  });
}

function forwardStackEvents(): void {
  stack.onEvent((event: TitStackEvent) => {
    if (mainWindow) mainWindow.webContents.send("tit:stack:event", event);
  });
}

void app.whenReady().then(async () => {
  const logPath = initLog();
  log("info", `log file ${logPath}`);
  process.on("uncaughtException", (err) => log("error", `uncaughtException: ${err.stack ?? err.message}`));
  process.on("unhandledRejection", (reason) => log("error", `unhandledRejection: ${String(reason)}`));

  protocol.handle("app", async (request) => {
    const url = new URL(request.url);
    if (url.host !== "launcher") return new Response("not found", { status: 404 });
    const root = resolveNativeStaticDir();
    if (!root) return new Response("not found", { status: 404 });
    const asset = resolve(root, `.${decodeURIComponent(url.pathname === "/" ? "/index.html" : url.pathname)}`);
    if (!asset.startsWith(`${root}${sep}`) || !existsSync(asset)) return new Response("not found", { status: 404 });
    const response = await net.fetch(pathToFileURL(asset).href);
    const headers = new Headers(response.headers);
    headers.set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'");
    return new Response(response.body, { status: response.status, headers });
  });

  // The UI never needs device/notification permissions in the skeleton; deny everything.
  session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));

  registerIpc();
  forwardStackEvents();
  mainWindow = createWindow();
  if (!(await tryDevAutoConnect(mainWindow)) && !(await tryNativeAutoStart(mainWindow))) showLauncher(mainWindow);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      const win = createWindow();
      mainWindow = win;
      const current = nativeRuntime.getCurrent();
      if (current) void connect(win, { url: current.origin, token: current.token });
      else void tryDevAutoConnect(win).then((connected) => { if (!connected) showLauncher(win); });
    }
  });
});

app.on("web-contents-created", (_e, contents) => {
  // Belt and braces for any webContents we did not create ourselves (there should be none).
  contents.setWindowOpenHandler(({ url }) => {
    openExternalIfWeb(url);
    return { action: "deny" };
  });
});

app.on("window-all-closed", () => {
  // The window's own "close" handler above already ran the running-jobs check before this fires
  // (every window is destroyed by the time "window-all-closed" fires — too late to prevent).
  // The last window owns the session lifetime on every OS, including macOS.
  // Staying dock-resident would keep CLI launchers waiting after Docker has stopped.
  quitWithWatchdog();
});

app.on("before-quit", (event) => {
  // Covers quit paths that do not go through a window close first (Cmd+Q, app.quit() elsewhere —
  // including Electron test harnesses, which call this rather than closing the window directly).
  if (quitGate.isApproved()) return;
  event.preventDefault();
  void handleQuitRequest(mainWindow, quitWithWatchdog);
});

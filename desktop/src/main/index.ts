import { existsSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { basename, join } from "node:path";
import { app, BrowserWindow, Notification, dialog, ipcMain, net, protocol, session, shell } from "electron";
import { initLog, log } from "./log";
import { readSettings, updateSettings } from "./settings";
import { LAUNCHER_HTML, LAUNCHER_JS, LAUNCHER_ORIGIN } from "./launcher";
import { checkToken, waitForHealth } from "./health";
import { nativeRuntime, resolveRuntime } from "./nativeRuntime";
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
  updateSettings({ lastServerUrl: url.origin });
  // In dev the page comes from Vite (HMR) which proxies /api, /auth and /ws to the server.
  const pageOrigin = process.env.ELECTRON_RENDERER_URL ? new URL(process.env.ELECTRON_RENDERER_URL).origin : url.origin;
  serverOrigin = pageOrigin;
  activeSession = { origin: url.origin, token: args.token };
  projectRootCache = null; // A new session may point at a different project.
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
  const candidates = [
    process.resourcesPath ? join(process.resourcesPath, "renderer") : null,
    // electron-vite's layout: this file is out/main/index.js, the renderer is out/renderer. Anchored
    // on __dirname rather than app.getAppPath() because the latter is whatever was handed to the
    // electron binary — `electron .` gives the package dir, `electron out/main/index.js` gives
    // out/main — and the second spelling used to send the server off without a UI bundle.
    join(__dirname, "..", "renderer"),
    join(app.getAppPath(), "out", "renderer"),
  ].filter((c): c is string => Boolean(c));
  return candidates.find((c) => existsSync(c));
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
 * started Vite with that token stamped onto every proxied request. The launcher form's whole job is
 * to ask for a URL and a token — both of which are in this process's environment — so showing it
 * would mean the developer typing in what their own dev script just worked out (P2). Connect
 * straight away instead.
 *
 * Unpackaged only. A packaged app must never be steerable into an arbitrary server by an
 * environment variable a user's shell happens to carry, and `TIT_DEV_SERVER_URL` is a name a
 * developer might well leave exported.
 */
async function tryDevAutoConnect(win: BrowserWindow): Promise<boolean> {
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

function showLauncher(win: BrowserWindow): void {
  serverOrigin = null;
  activeSession = null;
  projectRootCache = null;
  stopNotifyingJobCompletions();
  void win.loadURL(`${LAUNCHER_ORIGIN}/`);
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

async function getRunningJobsCount(): Promise<number> {
  if (!activeSession) return 0;
  try {
    const res = await net.fetch(`${activeSession.origin}/api/jobs?state=running`, {
      headers: { authorization: `Bearer ${activeSession.token}` },
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return 0;
    const jobs = (await res.json()) as unknown[];
    return Array.isArray(jobs) ? jobs.length : 0;
  } catch (err) {
    log("warn", `could not check running jobs before quit: ${err instanceof Error ? err.message : String(err)}`);
    return 0;
  }
}

const QUIT_WATCHDOG_MS = 4000;

/**
 * Quitting with a stack up and nothing running does not stop the container — that is the whole
 * point of attach-or-start (the next launch reconnects in seconds instead of booting an amd64
 * image again). What it used to do was leave it running *silently*: nothing on screen, nothing in
 * the log, no in-app way to reverse it (QA engineer finding 6). Say so, on the way out — a native
 * notification where one may be shown, and always a log line, since a notification fired
 * milliseconds before the process exits is best-effort by nature. Non-blocking on purpose: this
 * must never turn a quit into a question.
 */
function noteStackLeftRunning(containerName: string): void {
  log("info", `quitting with the Docker stack still up: container ${containerName} is left running (Settings -> Docker stops it)`);
  if (!mayShowSystemUi(WINDOW_MODE) || !Notification.isSupported()) return;
  try {
    new Notification({
      title: "TI-Toolbox is still running in Docker",
      body: `The container ${containerName} was left running so the next launch reconnects instantly. Stop it from Settings.`,
    }).show();
  } catch (err) {
    log("warn", `could not show the background-stack notification: ${String(err)}`);
  }
}

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

/**
 * TODO §2.5/§2.9 "keep containers running in the background?" — asked once, on real app quit,
 * and only when this app itself owns a Docker stack (a manually-typed external server connection
 * is not ours to stop, so quitting never blocks on it — this also keeps every existing E2E test,
 * none of which call `stack.start`, on the fast no-dialog path).
 *
 * `proceed` is how the caller actually ends things once we're done deciding: the window's own
 * "close" handler re-closes just that window (macOS convention: closing the window does not quit
 * a dock-resident app), while `before-quit` (Cmd+Q, or Electron/Playwright's own `app.quit()`)
 * must actually call `app.quit()` again — closing only the window there would leave the process
 * running with no window on macOS, which is also exactly why a naive version of this hung every
 * `electronApp.close()` in Playwright for the full test timeout (`window.close()` doesn't end the
 * process on macOS; the harness waits for the process to actually exit).
 */
async function handleQuitRequest(triggerWindow: BrowserWindow | null, proceed: () => void): Promise<void> {
  const current = stack.getCurrent();
  if (current) {
    const count = await getRunningJobsCount();
    if (count === 0) noteStackLeftRunning(current.containerName);
    if (count > 0) {
      const owner = triggerWindow ?? mainWindow ?? undefined;
      const options: Electron.MessageBoxOptions = {
        type: "question",
        buttons: ["Keep running in the background", "Stop containers and quit", "Cancel"],
        defaultId: 0,
        cancelId: 2,
        message: `${count} job${count === 1 ? "" : "s"} still running`,
        detail: "Keep the Docker containers running in the background and reopen the app later, or stop everything now.",
      };
      const choice = owner ? await dialog.showMessageBox(owner, options) : await dialog.showMessageBox(options);
      if (choice.response === 2) return; // Cancel — do not quit.
      if (choice.response === 1) await stack.stop().catch((err) => log("error", `stack.stop on quit failed: ${String(err)}`));
    }
  }
  // A native runtime (N0.4 spike) never survives this app quitting — no persisted attach, no
  // "keep running in the background" concept (unlike the Docker path above, there is nothing a
  // later launch could reattach to) — so it is always killed here, unconditionally, no prompt.
  if (nativeRuntime.getCurrent()) await nativeRuntime.stop().catch((err) => log("error", `nativeRuntime.stop on quit failed: ${String(err)}`));
  stopNotifyingJobCompletions();
  quitGate.approve();
  proceed();
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
    void handleQuitRequest(win, () => win.close());
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
   * mount an arbitrary host directory + docker.sock (`stack:start`), pick a host path
   * (`selectDirectory` — the *project* picker; unlike `selectFile`, its result is never mapped
   * into the current project, so a server-served page getting it back would be a raw, unjailed
   * host path) or seed the next launch's defaults (`setSettings`, e.g. `lastProjectDir`). A
   * server-served page may still call `getSettings`, `openExternal`, `openPath`,
   * `showItemInFolder`, `notify`, `platform`, `appVersion`, `stack:status` and `stack:stop`.
   *
   * `stack:stop` is deliberately NOT launcher-only (unlike `stack:start`). The page that can call
   * it is served *by the container it would stop*, so the only thing it can reach is its own
   * lifetime — no other project, no host path, no new mount. Leaving it launcher-only is what left
   * the connected app with no way to stop the stack it is talking to at all (QA engineer finding
   * 6): the running container survived every quit with nothing on screen saying so, and the only
   * remedy was `docker stop` in a terminal.
   */
  const fromLauncherWindow = (e: Electron.IpcMainInvokeEvent) => fromMainWindow(e) && isLauncherUrl(e.senderFrame?.url ?? "");

  ipcMain.handle("tit:appVersion", () => app.getVersion());
  ipcMain.handle("tit:openExternal", (e, url: unknown) => {
    if (!fromMainWindow(e)) return;
    openExternalIfWeb(String(url));
  });
  ipcMain.handle("tit:connect", async (e, args: unknown): Promise<TitConnectResult> => {
    if (!fromMainWindow(e) || !mainWindow) return { ok: false, error: "unknown sender" };
    if (args === null || args === undefined) {
      showLauncher(mainWindow);
      return { ok: true };
    }
    // Only the local launcher page may initiate a connection (it is the only page holding a token).
    if (!isLauncherUrl(e.senderFrame?.url ?? "")) return { ok: false, error: "connect is only allowed from the launcher" };
    const a = args as Partial<TitConnectArgs>;
    return connect(mainWindow, { url: String(a.url ?? ""), token: String(a.token ?? "") });
  });
  ipcMain.handle("tit:getSettings", (e) => (fromMainWindow(e) ? readSettings() : {}));
  ipcMain.handle("tit:setSettings", (e, partial: unknown) => (fromLauncherWindow(e) ? updateSettings(partial) : {}));

  ipcMain.handle("tit:selectDirectory", async (e): Promise<string | undefined> => {
    if (!fromLauncherWindow(e) || !mainWindow) return undefined;
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
    const result = await stack.start(String(hostProjectDir ?? ""));
    if (!result.ok) return result;
    const connected = await connect(mainWindow, { url: result.url, token: result.token });
    if (!connected.ok) return connected;
    return { ok: true, attached: result.attached };
  });
  ipcMain.handle("tit:stack:stop", async (e): Promise<TitStackStopResult> => {
    if (!fromMainWindow(e)) return { ok: false, error: "unknown sender" };
    const fromLauncher = isLauncherUrl(e.senderFrame?.url ?? "");
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

  protocol.handle("app", (request) => {
    const url = new URL(request.url);
    if (url.host !== "launcher") return new Response("not found", { status: 404 });
    if (url.pathname === "/launcher.js") {
      return new Response(LAUNCHER_JS, { headers: { "content-type": "text/javascript; charset=utf-8" } });
    }
    return new Response(LAUNCHER_HTML, { headers: { "content-type": "text/html; charset=utf-8" } });
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
  if (process.platform !== "darwin") quitWithWatchdog();
});

app.on("before-quit", (event) => {
  // Covers quit paths that do not go through a window close first (Cmd+Q, app.quit() elsewhere —
  // including Electron test harnesses, which call this rather than closing the window directly).
  if (quitGate.isApproved()) return;
  event.preventDefault();
  void handleQuitRequest(mainWindow, quitWithWatchdog);
});

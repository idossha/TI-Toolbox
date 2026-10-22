/**
 * Fakes for `electron` and for the main process's `stackHost`, so a vitest file can import the real
 * `src/main/index.ts` and drive its IPC handlers, protocol handler and quit orchestration without
 * Electron, Docker or a server. Used by `main-ipc-harness.test.ts` and `settings-stop-stack.test.ts`:
 *
 *   vi.mock("electron", async () => (await import("./main-ipc-fakes")).electronModule());
 *   vi.mock("../../src/main/stackHost", async () => (await import("./main-ipc-fakes")).stackHostModule());
 *
 * then `await bootMain()` once per test and `cleanupMain()` after it. State lives on `globalThis` because each test re-imports
 * `index.ts` after `vi.resetModules()`, which also re-instantiates this module; every fake reads
 * `harness()` at call time so it always sees the current test's state.
 *
 * What is real: `index.ts` itself, `settings.ts` (writing `settings.json` under a temp userData),
 * `log.ts` (writing `main.log`), `quitPlan.ts`, `paths.ts`, `health.ts` (over the fake `net`).
 * What is fake: windows, dialogs, shell, the jobs server (`net.fetch`), the Docker stack.
 *
 * Not a test file (no `.test.` in its name), and deliberately imports `index.ts` only through a
 * non-literal dynamic import: `tsconfig.web.json` type-checks `tests/unit/**`, and a static import
 * would pull every main-process module into that project.
 */
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { vi, type Mock } from "vitest";

/** The fake server's origin and token; nothing listens there — `net.fetch` is faked. */
export const ORIGIN = "http://127.0.0.1:18765";
export const TOKEN = "fixture-token";

type Listener = (...args: unknown[]) => void;
/** A recorded fake whose calls and answers each test inspects or overrides. */
type Fake = Mock<(...args: unknown[]) => unknown>;
type Handler = (event: IpcEvent, ...args: unknown[]) => unknown;

export interface IpcEvent {
  sender: unknown;
  senderFrame: { url: string } | null;
}

export class FakeWebContents {
  readonly listeners = new Map<string, Listener[]>();
  readonly mainFrame = { url: "" };
  readonly send = vi.fn();
  readonly executeJavaScript = vi.fn(async () => undefined);
  on(event: string, cb: Listener): this {
    this.listeners.set(event, [...(this.listeners.get(event) ?? []), cb]);
    return this;
  }
  once(event: string, cb: Listener): this {
    return this.on(event, cb);
  }
  emit(event: string, ...args: unknown[]): void {
    for (const cb of this.listeners.get(event) ?? []) cb(...args);
  }
  setWindowOpenHandler(): void {}
  setAudioMuted(): void {}
  isDestroyed(): boolean {
    return false;
  }
}

export class FakeBrowserWindow {
  readonly webContents = new FakeWebContents();
  readonly listeners = new Map<string, Listener[]>();
  constructor() {
    harness().windows.push(this);
  }
  static getAllWindows(): FakeBrowserWindow[] {
    return harness().windows;
  }
  on(event: string, cb: Listener): this {
    this.listeners.set(event, [...(this.listeners.get(event) ?? []), cb]);
    return this;
  }
  once(event: string, cb: Listener): this {
    return this.on(event, cb);
  }
  async loadURL(url: string): Promise<void> {
    this.webContents.mainFrame.url = url;
    harness().loads.push(url);
  }
  isDestroyed(): boolean {
    return false;
  }
  show(): void {}
  close(): void {}
}

export interface FakeStackCurrent {
  projectName: string;
  hostProjectDir: string;
  containerId: string;
  containerName: string;
  image: string;
  origin: string;
  token: string;
  port: number;
}

function newState(): HarnessState {
  const root = mkdtempSync(join(tmpdir(), "tit-main-ipc-"));
  const state: HarnessState = {
    root,
    userData: join(root, "userData"),
    isPackaged: false,
    handlers: new Map(),
    listeners: new Map(),
    appEvents: new Map(),
    protocolHandlers: new Map(),
    windows: [],
    loads: [],
    events: [],
    jobs: [],
    ready: () => {},
    readyPromise: Promise.resolve(),
    dialog: {
      showMessageBox: vi.fn<(...args: unknown[]) => unknown>(async () => ({ response: 0, checkboxChecked: false })),
      showOpenDialog: vi.fn<(...args: unknown[]) => unknown>(async () => ({ canceled: true, filePaths: [] })),
      showSaveDialog: vi.fn<(...args: unknown[]) => unknown>(async () => ({ canceled: true })),
    },
    shell: { openPath: vi.fn<(...args: unknown[]) => unknown>(async () => ""), showItemInFolder: vi.fn<(...args: unknown[]) => unknown>(), openExternal: vi.fn<(...args: unknown[]) => unknown>(async () => undefined) },
    app: { quit: vi.fn<(...args: unknown[]) => unknown>(), exit: vi.fn<(...args: unknown[]) => unknown>() },
    notify: vi.fn<(...args: unknown[]) => unknown>(async () => ({ ok: true })),
    stack: undefined as unknown as HarnessState["stack"],
  };
  state.readyPromise = new Promise<void>((resolve) => {
    state.ready = resolve;
  });
  const stack: HarnessState["stack"] = {
    current: null,
    getCurrent: () => stack.current,
    ownsContainer: () => stack.current !== null,
    start: vi.fn<(...args: unknown[]) => unknown>(async (...args: unknown[]) => {
      const dir = String(args[0]);
      state.events.push(`stack.start ${dir}`);
      stack.current = { projectName: "ti-toolbox-fixture", hostProjectDir: dir, containerId: "c1", containerName: "ti-toolbox-fixture-tit-1", image: "idossha/ti-toolbox:fixture", origin: ORIGIN, token: TOKEN, port: 18765 };
      return { ok: true as const, url: ORIGIN, token: TOKEN, attached: false };
    }),
    stop: vi.fn<(...args: unknown[]) => unknown>(async () => {
      state.events.push("stack.stop");
      stack.current = null;
      return { ok: true as const };
    }),
    status: vi.fn<(...args: unknown[]) => unknown>(async () => (stack.current ? { running: true, hostProjectDir: stack.current.hostProjectDir, port: stack.current.port, containerName: stack.current.containerName, image: stack.current.image } : { running: false })),
    validateStart: vi.fn<(...args: unknown[]) => unknown>(async () => undefined),
    adopt: vi.fn<(...args: unknown[]) => unknown>(),
    onEvent: vi.fn<(...args: unknown[]) => unknown>(() => () => true),
  };
  state.stack = stack;
  return state;
}

export interface HarnessState {
  root: string;
  userData: string;
  isPackaged: boolean;
  handlers: Map<string, Handler>;
  listeners: Map<string, Handler>;
  appEvents: Map<string, Listener[]>;
  protocolHandlers: Map<string, (request: { url: string }) => Promise<Response>>;
  windows: FakeBrowserWindow[];
  /** Every URL a window loaded, in order. */
  loads: string[];
  /** Ordered side effects across the fakes: `fetch <METHOD> <path>`, `stack.start <dir>`, `stack.stop`. */
  events: string[];
  /** What the fake server's `GET /api/jobs` answers; a cancelled job turns `cancelled`. */
  jobs: Array<{ id: string; state: string; kind?: string }>;
  ready: () => void;
  readyPromise: Promise<void>;
  dialog: { showMessageBox: Fake; showOpenDialog: Fake; showSaveDialog: Fake };
  shell: { openPath: Fake; showItemInFolder: Fake; openExternal: Fake };
  app: { quit: Fake; exit: Fake };
  notify: Fake;
  stack: {
    current: FakeStackCurrent | null;
    getCurrent: () => FakeStackCurrent | null;
    ownsContainer: () => boolean;
    start: Fake;
    stop: Fake;
    status: Fake;
    validateStart: Fake;
    adopt: Fake;
    onEvent: Fake;
  };
}

const KEY = "__titMainIpcHarness";

export function harness(): HarnessState {
  const global = globalThis as unknown as Record<string, HarnessState | undefined>;
  return (global[KEY] ??= newState());
}

export function resetHarness(): HarnessState {
  (globalThis as unknown as Record<string, HarnessState>)[KEY] = newState();
  return harness();
}

/** The fake jobs server behind `net.fetch`: `/api/health`, `/api/version`, `/api/jobs`, cancel, `/api/project`. */
async function fakeFetch(input: unknown, init?: { method?: string }): Promise<Response> {
  const state = harness();
  const url = new URL(String(input));
  const method = init?.method ?? "GET";
  if (url.protocol === "file:") return new Response(readFileSync(fileURLToPath(url)), { status: 200, headers: { "content-type": "application/octet-stream" } });
  state.events.push(`fetch ${method} ${url.pathname}`);
  if (url.pathname === "/api/health") return Response.json({ status: "ok" });
  if (url.pathname === "/api/version") return Response.json({ tit_version: "fixture", server_api: "v1" });
  if (url.pathname === "/api/jobs" && method === "GET") return Response.json(state.jobs);
  const cancel = /^\/api\/jobs\/([^/]+)\/cancel$/.exec(url.pathname);
  if (cancel && method === "POST") {
    for (const job of state.jobs) if (job.id === decodeURIComponent(cancel[1]!)) job.state = "cancelled";
    return Response.json({});
  }
  return new Response("not found", { status: 404 });
}

/** The `electron` module as `index.ts` and its imports use it. */
export function electronModule(): Record<string, unknown> {
  const app = {
    get isPackaged() {
      return harness().isPackaged;
    },
    getPath: (name: string) => (name === "userData" ? harness().userData : join(harness().userData, name)),
    setPath: () => {},
    setAppLogsPath: () => {},
    getVersion: () => "3.1.1-fixture",
    getAppPath: () => harness().root,
    whenReady: () => harness().readyPromise,
    on: (event: string, cb: Listener) => {
      const events = harness().appEvents;
      events.set(event, [...(events.get(event) ?? []), cb]);
    },
    quit: (...args: unknown[]) => harness().app.quit(...args),
    exit: (...args: unknown[]) => harness().app.exit(...args),
  };
  return {
    app,
    BrowserWindow: FakeBrowserWindow,
    ipcMain: {
      handle: (channel: string, handler: Handler) => harness().handlers.set(channel, handler),
      on: (channel: string, handler: Handler) => harness().listeners.set(channel, handler),
    },
    protocol: {
      registerSchemesAsPrivileged: () => {},
      handle: (scheme: string, handler: (request: { url: string }) => Promise<Response>) => harness().protocolHandlers.set(scheme, handler),
    },
    dialog: {
      showMessageBox: (...args: unknown[]) => harness().dialog.showMessageBox(...args),
      showOpenDialog: (...args: unknown[]) => harness().dialog.showOpenDialog(...args),
      showSaveDialog: (...args: unknown[]) => harness().dialog.showSaveDialog(...args),
    },
    shell: {
      openPath: (...args: unknown[]) => harness().shell.openPath(...args),
      showItemInFolder: (...args: unknown[]) => harness().shell.showItemInFolder(...args),
      openExternal: (...args: unknown[]) => harness().shell.openExternal(...args),
    },
    net: { fetch: fakeFetch },
    session: { defaultSession: { setPermissionRequestHandler: () => {} } },
    nativeImage: { createFromBuffer: () => ({ isEmpty: () => true }) },
    Notification: class {},
  };
}

/** `jobsNotifier` without its timers or banners; `showNativeNotification` is recorded. */
export function jobsNotifierModule(): Record<string, unknown> {
  return {
    notifyJobCompletions: () => {},
    setJobFinishedListener: () => {},
    stopNotifyingJobCompletions: () => {},
    showNativeNotification: (...args: unknown[]) => harness().notify(...args),
  };
}

/** `stackHost` whose `stack` is always the current test's fake. */
export function stackHostModule(): Record<string, unknown> {
  const stack = new Proxy({}, { get: (_target, prop: string) => (harness().stack as unknown as Record<string, unknown>)[prop] });
  return { stack };
}

const MAIN_INDEX = "../../src/main/index";
const PROCESS_EVENTS = ["uncaughtException", "unhandledRejection"] as const;
const baseline = new Map<string, Set<unknown>>();

/** Remove the process listeners each `index.ts` import adds, so re-importing it per test does not pile them up. */
export function cleanupMain(): void {
  const emitter = process as unknown as NodeJS.EventEmitter;
  for (const event of PROCESS_EVENTS) {
    const before = baseline.get(event);
    if (!before) continue;
    for (const listener of emitter.listeners(event)) if (!before.has(listener)) emitter.removeListener(event, listener as (...args: unknown[]) => void);
  }
}

/**
 * Import a fresh `index.ts`, let `app.whenReady()` resolve, and wait for its startup to settle on
 * a page (the launcher, or a connected session after a CLI handoff). Returns the main window.
 */
export async function bootMain(): Promise<FakeBrowserWindow> {
  const state = harness();
  for (const event of PROCESS_EVENTS) if (!baseline.has(event)) baseline.set(event, new Set((process as unknown as NodeJS.EventEmitter).listeners(event)));
  vi.resetModules();
  const target = MAIN_INDEX;
  await import(/* @vite-ignore */ target);
  state.ready();
  await vi.waitFor(() => {
    if (state.loads.length === 0) throw new Error("index.ts has not loaded a page yet");
  });
  return state.windows[0]!;
}

/** An IPC event from `win`'s main frame, as if it currently showed `url`. */
export function eventFrom(win: FakeBrowserWindow, url = win.webContents.mainFrame.url): IpcEvent {
  win.webContents.mainFrame.url = url;
  return { sender: win.webContents, senderFrame: win.webContents.mainFrame };
}

/** Call a registered `ipcMain.handle` channel the way `ipcRenderer.invoke` would. */
export async function invoke(channel: string, event: IpcEvent, ...args: unknown[]): Promise<unknown> {
  const handler = harness().handlers.get(channel);
  if (!handler) throw new Error(`no handler registered for ${channel}`);
  return handler(event, ...args);
}

/** Connect the launcher to the fake server through `tit:stack:start`, as the Overview form does. */
export async function startProject(win: FakeBrowserWindow, dir: string): Promise<unknown> {
  const result = await invoke("tit:stack:start", eventFrom(win, "app://launcher/"), dir);
  await vi.waitFor(() => {
    if (!win.webContents.mainFrame.url.startsWith(ORIGIN)) throw new Error("the window has not loaded the session yet");
  });
  return result;
}

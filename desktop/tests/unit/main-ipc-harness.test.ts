/**
 * The real `src/main/index.ts` under a faked `electron` (`main-ipc-fakes.ts`): who may call each
 * IPC handler, what the path, save, notify and protocol handlers refuse, what reaches `main.log`,
 * and what the CLI handoff leaves behind.
 *
 * Expected behaviour comes from the security rules documented in `index.ts` itself (ra_14 findings
 * 3, 4 and 8: dot-segment and out-of-mount paths never reach the shell; only the launcher page may
 * start a stack or write anything but `notifications`; no token in the log), the `tit-bridge.d.ts`
 * result shapes, `port.ts` (a port is an integer 1–65535) and the handoff comment ("CLI selection
 * applies only to this handoff"). Every refusal is paired with an accepted call through the same
 * handler, so a refusal cannot pass because the handler refuses everything.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/main-ipc-harness.test.ts`.
 */
import { existsSync, mkdirSync, readFileSync, readdirSync } from "node:fs";
import { basename, join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { bootMain, cleanupMain, eventFrom, harness, invoke, ORIGIN, resetHarness, startProject, type FakeBrowserWindow, type HarnessState } from "./main-ipc-fakes";

vi.mock("electron", async () => (await import("./main-ipc-fakes")).electronModule());
vi.mock("../../src/main/jobsNotifier", async () => (await import("./main-ipc-fakes")).jobsNotifierModule());
vi.mock("../../src/main/stackHost", async () => (await import("./main-ipc-fakes")).stackHostModule());

const DESKTOP = join(__dirname, "..", "..");
const LAUNCH_SELECTION = ["TIT_LAUNCH_CONTAINER_ID", "TIT_LAUNCH_PROJECT_DIR", "TIT_LAUNCH_EXISTING", "TIT_LAUNCH_CONTAINER"];

let state: HarnessState;

function stubQuietEnv(): void {
  vi.stubEnv("TIT_E2E_OFFSCREEN", "1");
  vi.stubEnv("TIT_E2E_HEADED", "");
  for (const name of ["TIT_USER_DATA_DIR", "TIT_DEV_LAUNCHER", "TIT_DEV_PORT", "TIT_DEV_IMAGE_TAG", "TIT_DEV_REPO_DIR", "TIT_DEV_SERVER_URL", "TIT_DEV_SERVER_TOKEN", "TIT_DEV_PROJECT_DIR", "TIT_NATIVE_PROJECT_DIR", "TIT_LAUNCH_IMAGE", "TIT_LAUNCH_PORT", "ELECTRON_RENDERER_URL", ...LAUNCH_SELECTION]) {
    vi.stubEnv(name, "");
    delete process.env[name];
  }
}

function settingsOnDisk(): Record<string, unknown> {
  return JSON.parse(readFileSync(join(state.userData, "settings.json"), "utf8")) as Record<string, unknown>;
}

function projectDir(name = "p"): string {
  const dir = join(state.root, name);
  mkdirSync(dir, { recursive: true });
  return dir;
}

beforeEach(() => {
  state = resetHarness();
  stubQuietEnv();
});

afterEach(() => {
  cleanupMain();
  vi.unstubAllEnvs();
});

describe("sender checks", () => {
  it("a sender that is not the main window gets each handler's refusal and causes nothing", async () => {
    const win = await bootMain();
    const foreign = { sender: { id: "another webContents" }, senderFrame: { url: "app://launcher/" } };
    expect(await invoke("tit:stack:start", foreign, projectDir())).toEqual({ ok: false, error: "unknown sender" });
    expect(await invoke("tit:stack:stop", foreign)).toEqual({ ok: false, error: "unknown sender" });
    expect(await invoke("tit:stack:switchProject", foreign)).toEqual({ ok: false, error: "unknown sender" });
    expect(await invoke("tit:stack:status", foreign)).toEqual({ running: false });
    expect(await invoke("tit:getSettings", foreign)).toEqual({});
    expect(await invoke("tit:setSettings", foreign, { lastProjectDir: "/x" })).toEqual({});
    expect(await invoke("tit:openPath", foreign, "/mnt/p/a.txt")).toEqual({ ok: false, reason: "unknown sender" });
    expect(await invoke("tit:showItemInFolder", foreign, "/mnt/p/a.txt")).toEqual({ ok: false, reason: "unknown sender" });
    expect(await invoke("tit:saveFile", foreign, "text", { defaultName: "a.txt" })).toEqual({ ok: false, reason: "unknown sender" });
    expect(await invoke("tit:notify", foreign, "Title")).toEqual({ ok: false, reason: "unknown sender" });
    expect(await invoke("tit:connect", foreign, { url: ORIGIN, token: "t" })).toEqual({ ok: false, error: "unknown sender" });
    await expect(invoke("tit:tetravox:status", foreign)).rejects.toThrow("Untrusted viewer request.");
    expect(state.stack.start).not.toHaveBeenCalled();
    expect(state.stack.stop).not.toHaveBeenCalled();
    expect(state.dialog.showMessageBox).not.toHaveBeenCalled();
    expect(state.dialog.showSaveDialog).not.toHaveBeenCalled();
    expect(state.notify).not.toHaveBeenCalled();
    expect(existsSync(join(state.userData, "settings.json"))).toBe(false);

    // The same calls from the main window's launcher page are accepted.
    expect(await invoke("tit:setSettings", eventFrom(win, "app://launcher/"), { lastProjectDir: "/from/launcher" })).toMatchObject({ lastProjectDir: "/from/launcher" });
    expect(settingsOnDisk().lastProjectDir).toBe("/from/launcher");
  });

  it("a connected page cannot start a stack and may write only its notification preferences", async () => {
    const win = await bootMain();
    const dir = projectDir();
    await invoke("tit:setSettings", eventFrom(win, "app://launcher/"), { lastProjectDir: dir });
    expect(await startProject(win, dir)).toEqual({ ok: true, attached: false });
    expect(state.stack.start).toHaveBeenCalledTimes(1);
    const connected = eventFrom(win);
    expect(connected.senderFrame!.url.startsWith(ORIGIN)).toBe(true);

    expect(await invoke("tit:stack:start", connected, projectDir("other"))).toEqual({ ok: false, error: "unknown sender" });
    expect(state.stack.start).toHaveBeenCalledTimes(1);

    await invoke("tit:setSettings", connected, { lastProjectDir: "/should/not/persist", lastServerUrl: "http://evil.example", notifications: { enabled: false, events: "failures" } });
    const saved = settingsOnDisk();
    expect(saved.lastProjectDir).toBe(dir);
    expect(saved.lastServerUrl).toBe(ORIGIN); // written by connect(), not by the page
    expect(saved.notifications).toMatchObject({ enabled: false, events: "failures" });
  });
});

describe("paths handed to the shell", () => {
  async function connectedTo(dir: string): Promise<FakeBrowserWindow> {
    const win = await bootMain();
    await startProject(win, dir);
    return win;
  }

  it("openPath and showItemInFolder refuse dot segments, other mounts and TetraVox scenes without calling the shell", async () => {
    const dir = projectDir("p");
    const win = await connectedTo(dir);
    const page = eventFrom(win);
    const mount = `/mnt/${basename(dir)}`;

    expect(await invoke("tit:openPath", page, `${mount}/../x`)).toEqual({ ok: false, reason: "path contains a '.' or '..' segment" });
    expect(await invoke("tit:openPath", page, "/mnt/other/x")).toEqual({ ok: false, reason: "path is outside the project" });
    expect(await invoke("tit:openPath", page, `${mount}/derivatives/scene.TetraVox.json`)).toEqual({ ok: false, reason: "Open TetraVox scenes from the Viewer." });
    expect(await invoke("tit:showItemInFolder", page, `${mount}/a/../../escape`)).toEqual({ ok: false, reason: "path contains a '.' or '..' segment" });
    expect(await invoke("tit:showItemInFolder", page, "/mnt/other/x")).toEqual({ ok: false, reason: "path is outside the project" });
    expect(state.shell.openPath).not.toHaveBeenCalled();
    expect(state.shell.showItemInFolder).not.toHaveBeenCalled();

    // An in-project path reaches the shell as the host path under the project directory.
    expect(await invoke("tit:openPath", page, `${mount}/derivatives/report.html`)).toEqual({ ok: true });
    expect(state.shell.openPath).toHaveBeenCalledExactlyOnceWith(join(dir, "derivatives", "report.html"));
    expect(await invoke("tit:showItemInFolder", page, `${mount}/derivatives`)).toEqual({ ok: true });
    expect(state.shell.showItemInFolder).toHaveBeenCalledExactlyOnceWith(join(dir, "derivatives"));
  });

  it("after a manual connect to another server, the stack this app started no longer maps its paths", async () => {
    // G3-3: the owned stack outlives a manual Connect; its project is not the new session's, and
    // the other server (whose /api/project the fake answers 404) names no host root of its own.
    const dir = projectDir("p");
    const win = await connectedTo(dir);
    expect(await invoke("tit:connect", eventFrom(win, "app://launcher/"), { url: "http://127.0.0.1:18999", token: "other" })).toMatchObject({ ok: true });
    expect(state.stack.current, "the owned stack is still running").not.toBeNull();

    const page = eventFrom(win, "http://127.0.0.1:18999/");
    expect(await invoke("tit:openPath", page, `/mnt/${basename(dir)}/derivatives/report.html`)).toMatchObject({ ok: false });
    expect(state.shell.openPath).not.toHaveBeenCalled();
  });
});

describe("saveFile", () => {
  it("suggests only a basename and writes only to the path the dialog returned", async () => {
    const win = await bootMain();
    const out = join(state.root, "chosen", "export.txt");
    mkdirSync(join(state.root, "chosen"));
    state.dialog.showSaveDialog.mockResolvedValueOnce({ canceled: false, filePath: out });
    const result = await invoke("tit:saveFile", eventFrom(win, `${ORIGIN}/`), "line 1\nline 2", { defaultName: "a/b/../c.txt" });
    expect(result).toEqual({ ok: true, path: out });
    expect(state.dialog.showSaveDialog.mock.calls[0]![1]).toMatchObject({ defaultPath: basename("a/b/../c.txt") });
    expect(basename("a/b/../c.txt")).toBe("c.txt");
    expect(readFileSync(out, "utf8")).toBe("line 1\nline 2");
    expect(readdirSync(join(state.root, "chosen"))).toEqual(["export.txt"]);

    state.dialog.showSaveDialog.mockResolvedValueOnce({ canceled: true });
    expect(await invoke("tit:saveFile", eventFrom(win), "ignored", { defaultName: "x.txt" })).toEqual({ ok: false, canceled: true });
    expect(readdirSync(join(state.root, "chosen"))).toEqual(["export.txt"]);
  });
});

describe("notify", () => {
  it("refuses a title over 200 characters, a body over 500 and a non-boolean sound flag", async () => {
    const win = await bootMain();
    const page = eventFrom(win, `${ORIGIN}/`);
    expect(await invoke("tit:notify", page, "x".repeat(201))).toEqual({ ok: false, reason: "Invalid notification title." });
    expect(await invoke("tit:notify", page, "")).toEqual({ ok: false, reason: "Invalid notification title." });
    expect(await invoke("tit:notify", page, "Done", "y".repeat(501))).toEqual({ ok: false, reason: "Invalid notification body." });
    expect(await invoke("tit:notify", page, "Done", "body", "yes")).toEqual({ ok: false, reason: "Invalid notification sound flag." });
    expect(state.notify).not.toHaveBeenCalled();

    // The limits themselves are allowed.
    expect(await invoke("tit:notify", page, "x".repeat(200), "y".repeat(500), true)).toEqual({ ok: true });
    expect(state.notify).toHaveBeenCalledExactlyOnceWith({ title: "x".repeat(200), body: "y".repeat(500), silent: true }, win);
  });
});

describe("app:// protocol", () => {
  it("serves the launcher bundle and answers 404 for another host or a path that escapes it", async () => {
    await bootMain();
    const handler = state.protocolHandlers.get("app")!;
    // index.ts serves resolveRendererDir(): under vitest, src/main/../renderer.
    const rendererRoot = join(DESKTOP, "src", "renderer");
    expect(existsSync(join(rendererRoot, "index.html"))).toBe(true);
    // The escape target exists, so a 404 can only come from the containment check.
    expect(existsSync(join(DESKTOP, "src", "main", "index.ts"))).toBe(true);

    const ok = await handler({ url: "app://launcher/index.html" });
    expect(ok.status).toBe(200);
    expect(ok.headers.get("Content-Security-Policy")).toContain("default-src 'self'");
    expect(await ok.text()).toBe(readFileSync(join(rendererRoot, "index.html"), "utf8"));

    for (const url of ["app://launcher/..%2Fmain%2Findex.ts", "app://launcher/..%2F..%2F..%2F..%2Fetc%2Fpasswd", "app://evil/index.html"]) {
      expect((await handler({ url })).status, url).toBe(404);
    }
  });
});

describe("main.log", () => {
  it("a failed session load is logged without its token", async () => {
    const win = await bootMain();
    win.webContents.emit("did-fail-load", {}, -105, "ERR_NAME_NOT_RESOLVED", `${ORIGIN}/auth/session?token=SECRET`, true);
    win.webContents.emit("will-navigate", { preventDefault: () => {} }, "https://evil.example/x?token=SECRET#frag");
    const text = readFileSync(join(state.userData, "logs", "main.log"), "utf8");
    expect(text).toContain(`did-fail-load -105 ERR_NAME_NOT_RESOLVED ${ORIGIN}/auth/session`);
    expect(text).toContain("blocked navigation to https://evil.example/x");
    expect(text).not.toContain("SECRET");
  });
});

describe("development port", () => {
  it.each(["0", "70000", "8765.5", "abc"])("TIT_DEV_PORT=%s is refused before any stack starts", async (port) => {
    vi.stubEnv("TIT_DEV_LAUNCHER", "1");
    vi.stubEnv("TIT_DEV_PORT", port);
    const win = await bootMain();
    await expect(invoke("tit:stack:start", eventFrom(win, "app://launcher/"), projectDir())).rejects.toThrow(`TIT_DEV_PORT must be a port number from 1 to 65535 (got "${port}")`);
    expect(state.stack.start).not.toHaveBeenCalled();
  });

  it("a valid TIT_DEV_PORT is where the development stack starts looking", async () => {
    vi.stubEnv("TIT_DEV_LAUNCHER", "1");
    vi.stubEnv("TIT_DEV_PORT", "65535");
    const win = await bootMain();
    const dir = projectDir();
    await startProject(win, dir);
    expect(state.stack.start).toHaveBeenCalledExactlyOnceWith(dir, { preferredPort: 65535, serverReload: true });
  });
});

describe("CLI project handoff", () => {
  it("opens the handed-over project, then forgets the selection so later starts never reuse it", async () => {
    const dir = projectDir();
    vi.stubEnv("TIT_LAUNCH_PROJECT_DIR", dir);
    vi.stubEnv("TIT_LAUNCH_EXISTING", "attach");
    vi.stubEnv("TIT_LAUNCH_CONTAINER", "ti-toolbox-x-tit-1");
    vi.stubEnv("TIT_LAUNCH_IMAGE", "registry.example.org/ti-toolbox:custom");
    vi.stubEnv("TIT_LAUNCH_PORT", "9123");
    await bootMain();
    await vi.waitFor(() => expect(state.loads.at(-1)).toBe(`${ORIGIN}/auth/session?token=fixture-token`));
    expect(state.stack.start).toHaveBeenCalledExactlyOnceWith(dir, { image: "registry.example.org/ti-toolbox:custom", preferredPort: 9123 });
    for (const name of LAUNCH_SELECTION) expect(process.env[name], name).toBeUndefined();
  });

  it("forgets the selection when the handed-over project fails to open", async () => {
    vi.stubEnv("TIT_LAUNCH_PROJECT_DIR", projectDir());
    vi.stubEnv("TIT_LAUNCH_EXISTING", "recreate");
    state.stack.start.mockResolvedValueOnce({ ok: false, error: "Docker is not running" });
    await bootMain();
    expect(state.loads).toEqual(["app://launcher/"]);
    for (const name of LAUNCH_SELECTION) expect(process.env[name], name).toBeUndefined();
    // Offscreen: the failure goes to the log, never to a dialog on the developer's screen.
    expect(state.dialog.showMessageBox).not.toHaveBeenCalled();
    expect(readFileSync(join(state.userData, "logs", "main.log"), "utf8")).toContain("Could not open TI-Toolbox: Error: Docker is not running");
  });

  it("a bad TIT_LAUNCH_PORT fails the handoff by name instead of publishing a wrong port", async () => {
    vi.stubEnv("TIT_LAUNCH_PROJECT_DIR", projectDir());
    vi.stubEnv("TIT_LAUNCH_PORT", "0");
    await bootMain();
    expect(state.stack.start).not.toHaveBeenCalled();
    expect(readFileSync(join(state.userData, "logs", "main.log"), "utf8")).toContain('TIT_LAUNCH_PORT must be a port number from 1 to 65535 (got "0")');
  });
});

// Keep the shared fakes honest: the harness must see the module it mocks.
it("the fake stack is the stack index.ts uses", async () => {
  const win = await bootMain();
  await startProject(win, projectDir());
  expect(harness().stack.current?.hostProjectDir).toBe(join(state.root, "p"));
  expect(await invoke("tit:stack:status", eventFrom(win))).toMatchObject({ running: true, hostProjectDir: join(state.root, "p") });
});

/** Default development entry opens the home before asking Docker to do any work. */
import { EventEmitter } from "node:events";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  spawn: vi.fn(), ensureDevStack: vi.fn(), stopDevStack: vi.fn(), loadDevConfig: vi.fn(),
  envText: undefined as string | undefined,
}));
vi.mock("node:child_process", () => ({ spawn: mocks.spawn }));
vi.mock("../../scripts/devStack", () => ({
  DESKTOP_DIR: "/checkout/desktop", REPO_DIR: "/checkout",
  ensureDevStack: mocks.ensureDevStack, stopDevStack: mocks.stopDevStack,
}));
vi.mock("../../scripts/devEnv", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../scripts/devEnv")>(), loadDevConfig: mocks.loadDevConfig,
}));
vi.mock("node:fs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs")>();
  return {
    ...actual,
    existsSync: (path: string) => path === "/checkout/desktop/.env.dev" ? mocks.envText !== undefined : actual.existsSync(path),
    readFileSync: (path: string, ...args: unknown[]) => path === "/checkout/desktop/.env.dev" ? mocks.envText : Reflect.apply(actual.readFileSync, actual, [path, ...args]),
  };
});

const argv = process.argv;
const exitCode = process.exitCode;
let children: EventEmitter[];

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  mocks.envText = undefined;
  children = [];
  process.argv = ["node", "dev.ts"];
  process.exitCode = undefined;
  for (const key of ["TIT_DEV_PROJECT_DIR", "TIT_DEV_IMAGE_TAG", "TIT_DEV_PORT"]) vi.stubEnv(key, "");
  vi.spyOn(console, "log").mockImplementation(() => {});
  mocks.spawn.mockImplementation(() => {
    const child = Object.assign(new EventEmitter(), { kill: vi.fn() });
    children.push(child);
    return child;
  });
});
afterEach(() => {
  process.argv = argv;
  process.exitCode = exitCode;
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

async function startBuild() {
  await import("../../scripts/dev");
  await vi.waitFor(() => expect(mocks.spawn).toHaveBeenCalledTimes(1));
}
async function finishElectron() {
  children[1]!.emit("exit", 0, null);
  await vi.waitFor(() => expect(console.log).toHaveBeenCalledWith("[dev] TI-Toolbox closed."));
}

describe("npm run dev", () => {
  it("builds then opens the home without configuration or Docker, clearing old handoffs", async () => {
    vi.stubEnv("TIT_LAUNCH_CONTAINER_ID", "old-container");
    vi.stubEnv("TIT_LAUNCH_PROJECT_DIR", "/old-project");
    vi.stubEnv("TIT_DEV_SERVER_URL", "http://old-server");
    vi.stubEnv("TIT_DEV_SERVER_TOKEN", "old-token");
    vi.stubEnv("ELECTRON_RENDERER_URL", "http://old-renderer");
    await startBuild();
    expect(mocks.spawn.mock.calls[0]!.slice(0, 2)).toEqual(["/checkout/desktop/node_modules/.bin/electron-vite", ["build"]]);
    children[0]!.emit("exit", 0, null);
    await vi.waitFor(() => expect(mocks.spawn).toHaveBeenCalledTimes(2));
    expect(mocks.spawn.mock.calls[1]!.slice(0, 2)).toEqual(["/checkout/desktop/node_modules/.bin/electron", ["."]]);
    const env = mocks.spawn.mock.calls[1]![2].env;
    expect(env).toMatchObject({ TIT_DEV_LAUNCHER: "1", TIT_DEV_REPO_DIR: "/checkout", TIT_STATIC_DIR: "/ti-toolbox/desktop/out/renderer" });
    for (const key of ["TIT_LAUNCH_CONTAINER_ID", "TIT_LAUNCH_PROJECT_DIR", "TIT_DEV_SERVER_URL", "TIT_DEV_SERVER_TOKEN", "ELECTRON_RENDERER_URL"]) expect(env).not.toHaveProperty(key);
    expect(mocks.loadDevConfig).not.toHaveBeenCalled();
    expect(mocks.ensureDevStack).not.toHaveBeenCalled();
    expect(mocks.stopDevStack).not.toHaveBeenCalled();
    await finishElectron();
  });

  it("passes optional defaults with shell and explicit project precedence without validating the path", async () => {
    mocks.envText = "TIT_DEV_PROJECT_DIR=../file-project\nTIT_DEV_IMAGE_TAG=fixture-tag\nTIT_DEV_PORT=8765\n";
    vi.stubEnv("TIT_DEV_PORT", "8877");
    process.argv.push("--project", "../not-created-yet");
    await startBuild();
    children[0]!.emit("exit", 0, null);
    await vi.waitFor(() => expect(mocks.spawn).toHaveBeenCalledTimes(2));
    expect(mocks.spawn.mock.calls[1]![2].env).toMatchObject({ TIT_DEV_PROJECT_DIR: "/checkout/not-created-yet", TIT_DEV_IMAGE_TAG: "fixture-tag", TIT_DEV_PORT: "8877" });
    expect(mocks.loadDevConfig).not.toHaveBeenCalled();
    await finishElectron();
  });

  it("does not launch Electron after a failed build", async () => {
    await startBuild();
    children[0]!.emit("exit", 7, null);
    await vi.waitFor(() => expect(process.exitCode).toBe(7));
    expect(mocks.spawn).toHaveBeenCalledTimes(1);
    expect(mocks.ensureDevStack).not.toHaveBeenCalled();
  });
});

/**
 * The preload bridge (`src/preload/index.ts`) and the main process (`src/main/`) agree on every IPC
 * channel between them, in both directions.
 *
 * The two sides are read independently: the preload's channels are what its exposed `window.tit`
 * functions actually pass to a recording `ipcRenderer` when each is called; main's are what the real
 * `src/main/index.ts` registers on `ipcMain` under the `main-ipc-fakes.ts` harness, plus the
 * `webContents.send("tit:…")` channels written in the main sources. A channel on one side only is
 * either a dead handler a renderer can no longer reach but a compromised page still could (the
 * removed `tit:selectFile` chain was one) or a bridge call that rejects with "No handler registered"
 * at runtime.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/ipc-channel-contract.test.ts`.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { bootMain, cleanupMain, harness, resetHarness } from "./main-ipc-fakes";

const preload = vi.hoisted(() => ({
  exposed: new Map<string, unknown>(),
  invoked: new Set<string>(),
  sent: new Set<string>(),
  subscribed: new Set<string>(),
}));

vi.mock("electron", async () => ({
  ...(await import("./main-ipc-fakes")).electronModule(),
  contextBridge: { exposeInMainWorld: (key: string, api: unknown) => preload.exposed.set(key, api) },
  ipcRenderer: {
    invoke: async (channel: string) => {
      preload.invoked.add(channel);
    },
    send: (channel: string) => {
      preload.sent.add(channel);
    },
    on: (channel: string) => {
      preload.subscribed.add(channel);
    },
    removeListener: () => {},
  },
}));
vi.mock("../../src/main/jobsNotifier", async () => (await import("./main-ipc-fakes")).jobsNotifierModule());
vi.mock("../../src/main/stackHost", async () => (await import("./main-ipc-fakes")).stackHostModule());

const MAIN_DIR = join(__dirname, "..", "..", "src", "main");

/** Call every function in the bridge, nested namespaces included, so each records its channel. */
function callEverything(api: Record<string, unknown>): number {
  let calls = 0;
  for (const value of Object.values(api)) {
    if (typeof value === "function") {
      void value("fixture", 80, 24);
      calls += 1;
    } else if (value && typeof value === "object") {
      calls += callEverything(value as Record<string, unknown>);
    }
  }
  return calls;
}

/** `webContents.send("tit:…")` channels written in the main-process sources (tests excluded). */
function mainSendChannels(): string[] {
  const channels = new Set<string>();
  for (const file of readdirSync(MAIN_DIR)) {
    if (!file.endsWith(".ts") || file.endsWith(".test.ts")) continue;
    const text = readFileSync(join(MAIN_DIR, file), "utf8");
    for (const match of text.matchAll(/webContents\.send\(\s*"(tit:[^"]+)"/g)) channels.add(match[1]!);
  }
  return [...channels].sort();
}

beforeEach(() => {
  resetHarness();
  for (const set of [preload.invoked, preload.sent, preload.subscribed]) set.clear();
  preload.exposed.clear();
  vi.stubEnv("TIT_E2E_OFFSCREEN", "1");
});

afterEach(() => {
  cleanupMain();
  vi.unstubAllEnvs();
});

it("every channel the preload invokes or sends is registered by main, and main registers nothing else", async () => {
  vi.resetModules();
  await import("../../src/preload/index");
  const tit = preload.exposed.get("tit") as Record<string, unknown> | undefined;
  expect(tit).toBeDefined();
  // Every bridge function except `platform()` (answered in the preload) reaches main.
  expect(callEverything(tit!)).toBe(preload.invoked.size + preload.sent.size + preload.subscribed.size + 1);

  await bootMain();
  expect([...preload.invoked].sort()).toEqual([...harness().handlers.keys()].sort());
  expect([...preload.sent].sort()).toEqual([...harness().listeners.keys()].sort());
});

it("every event main sends to the window has a preload subscriber, and the preload listens for nothing else", async () => {
  vi.resetModules();
  await import("../../src/preload/index");
  callEverything(preload.exposed.get("tit") as Record<string, unknown>);
  expect([...preload.subscribed].sort()).toEqual(mainSendChannels());
});

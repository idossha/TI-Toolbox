/**
 * The preload bridge (`src/preload/index.ts`) and the main process (`src/main/`) agree on every IPC
 * channel between them, in both directions, and the preload implements all of `TitBridge`.
 *
 * The two sides are read independently: the preload's channels are what its exposed `window.tit`
 * functions actually pass to a recording `ipcRenderer` when each is called; main's are what the real
 * `src/main/index.ts` registers on `ipcMain` under the `main-ipc-fakes.ts` harness, plus the
 * `webContents.send(…)` channels written in the main sources (`src/main/**`, tests excluded). A
 * channel on one side only is either a dead handler a renderer can no longer reach but a compromised
 * page still could (the removed `tit:selectFile` chain was one) or a bridge call that rejects with
 * "No handler registered" at runtime. A channel main registers twice is refused (the harness's map
 * would keep only the last), every listener the preload adds is removed by the function it returns,
 * and every member of `TitBridge` (`src/shared/tit-bridge.d.ts`, the nested `stack`, `fastsurfer`
 * and `assistant` bridges included) exists on the exposed object, optional ones too, which
 * TypeScript does not check. The two source-text readers count what they could not read (a send
 * whose channel is not a string literal) and are self-tested on planted inputs.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/ipc-channel-contract.test.ts`.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { bootMain, cleanupMain, harness, resetHarness } from "./main-ipc-fakes";

const ipc = vi.hoisted(() => ({
  exposed: new Map<string, unknown>(),
  invoked: new Set<string>(),
  sent: new Set<string>(),
  subscribed: new Set<string>(),
  unsubscribed: new Set<string>(),
  /** Every `ipcMain.handle`/`ipcMain.on` call main made, duplicates kept. */
  registered: [] as string[],
}));

vi.mock("electron", async () => {
  const electron = (await import("./main-ipc-fakes")).electronModule();
  const ipcMain = electron.ipcMain as Record<"handle" | "on", (channel: string, handler: unknown) => void>;
  return {
    ...electron,
    ipcMain: {
      handle: (channel: string, handler: unknown) => {
        ipc.registered.push(channel);
        ipcMain.handle(channel, handler);
      },
      on: (channel: string, handler: unknown) => {
        ipc.registered.push(channel);
        ipcMain.on(channel, handler);
      },
    },
    contextBridge: { exposeInMainWorld: (key: string, api: unknown) => ipc.exposed.set(key, api) },
    ipcRenderer: {
      invoke: async (channel: string) => {
        ipc.invoked.add(channel);
      },
      send: (channel: string) => {
        ipc.sent.add(channel);
      },
      on: (channel: string) => {
        ipc.subscribed.add(channel);
      },
      removeListener: (channel: string) => {
        ipc.unsubscribed.add(channel);
      },
    },
  };
});
vi.mock("../../src/main/jobsNotifier", async () => (await import("./main-ipc-fakes")).jobsNotifierModule());
vi.mock("../../src/main/stackHost", async () => (await import("./main-ipc-fakes")).stackHostModule());

const SRC = join(__dirname, "..", "..", "src");

/**
 * Call every function in the bridge, nested namespaces included, so each records its channel; a
 * returned function (a subscription's unsubscribe) is called too, so its removal is recorded.
 */
function callEverything(api: Record<string, unknown>): number {
  let calls = 0;
  for (const value of Object.values(api)) {
    if (typeof value === "function") {
      const result: unknown = value("fixture", 80, 24);
      if (typeof result === "function") result();
      calls += 1;
    } else if (value && typeof value === "object") {
      calls += callEverything(value as Record<string, unknown>);
    }
  }
  return calls;
}

/** Literal channels of `webContents.send(` calls in `source`, and how many such calls had no literal. */
function sendChannels(source: string): { found: string[]; unreadable: number } {
  const found = [...source.matchAll(/\bwebContents\.send\(\s*"([^"]+)"/g)].map((m) => m[1]!);
  return { found, unreadable: [...source.matchAll(/\bwebContents\.send\(/g)].length - found.length };
}

/** The main-process sources under `src/main/` (subdirectories included, tests excluded), concatenated. */
function mainSources(): string {
  const texts: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (name.endsWith(".ts") && !name.endsWith(".test.ts")) texts.push(readFileSync(path, "utf8"));
    }
  };
  walk(join(SRC, "main"));
  return texts.join("\n");
}

/** Member names declared at the top level of `export interface <name> { ... }`, optional ones included. */
function interfaceMembers(dts: string, name: string): string[] {
  const match = new RegExp(`export interface ${name} \\{([\\s\\S]*?)\\n\\}`).exec(dts);
  if (!match) throw new Error(`interface ${name} not found`);
  return [...match[1]!.matchAll(/^ {2}(\w+)\??[(:]/gm)].map((m) => m[1]!);
}

const sorted = (values: Iterable<string>) => [...new Set(values)].sort();

/** Import the real preload and return the object it exposed as `window.tit`. */
async function loadPreload(): Promise<Record<string, unknown>> {
  vi.resetModules();
  await import("../../src/preload/index");
  const tit = ipc.exposed.get("tit") as Record<string, unknown> | undefined;
  expect(tit).toBeDefined();
  return tit!;
}

beforeEach(() => {
  resetHarness();
  for (const set of [ipc.invoked, ipc.sent, ipc.subscribed, ipc.unsubscribed]) set.clear();
  ipc.exposed.clear();
  ipc.registered.length = 0;
  vi.stubEnv("TIT_E2E_OFFSCREEN", "1");
});

afterEach(() => {
  cleanupMain();
  vi.unstubAllEnvs();
});

it("every channel the preload invokes or sends is registered by main, and main registers nothing else", async () => {
  const tit = await loadPreload();
  // Every bridge function except `platform()` (answered in the preload) reaches main.
  expect(callEverything(tit)).toBe(ipc.invoked.size + ipc.sent.size + ipc.subscribed.size + 1);

  await bootMain();
  expect([...ipc.invoked].sort()).toEqual([...harness().handlers.keys()].sort());
  expect([...ipc.sent].sort()).toEqual([...harness().listeners.keys()].sort());
});

it("main registers no channel twice", async () => {
  await bootMain();
  expect(ipc.registered.length).toBeGreaterThan(20);
  expect(ipc.registered.length).toBe(new Set(ipc.registered).size);
});

it("every event main sends to the window has a preload subscriber, and the preload listens for nothing else", async () => {
  callEverything(await loadPreload());
  const sent = sendChannels(mainSources());
  expect(sent.unreadable).toBe(0);
  expect(sent.found.length).toBeGreaterThan(0);
  expect([...ipc.subscribed].sort()).toEqual(sorted(sent.found));
});

it("each listener the preload adds is removed by the function its subscription returns", async () => {
  callEverything(await loadPreload());
  expect(ipc.subscribed.size).toBeGreaterThan(0);
  expect([...ipc.unsubscribed].sort()).toEqual([...ipc.subscribed].sort());
});

describe("the TitBridge interface", () => {
  const bridge = readFileSync(join(SRC, "shared", "tit-bridge.d.ts"), "utf8");

  it.each([
    ["TitBridge", undefined],
    ["TitStackBridge", "stack"],
    ["TitFastSurferBridge", "fastsurfer"],
    ["TitAssistantBridge", "assistant"],
  ] as const)("every member of %s is implemented by the preload, and nothing else is exposed", async (iface, nested) => {
    const tit = await loadPreload();
    const members = interfaceMembers(bridge, iface);
    expect(members.length).toBeGreaterThan(2);
    const exposed = nested ? (tit[nested] as Record<string, unknown>) : tit;
    expect(sorted(Object.keys(exposed))).toEqual(sorted(members));
  });

  it("a member planted in the interface is read (self-test)", () => {
    const planted = bridge.replace("export interface TitStackBridge {", "export interface TitStackBridge {\n  planted?(): void;");
    expect(planted).not.toBe(bridge);
    expect(interfaceMembers(planted, "TitStackBridge")).toContain("planted");
  });
});

it("a send whose channel is a variable is counted as unreadable, not skipped (self-test)", () => {
  expect(sendChannels('win.webContents.send(CHANNEL, 1); win.webContents.send(\n  "tit:x",\n 2);')).toEqual({ found: ["tit:x"], unreadable: 1 });
});

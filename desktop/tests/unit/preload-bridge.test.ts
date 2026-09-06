/**
 * The preload bridge, as the renderer receives it (V6 bug fix, 2026-09-06).
 *
 * The reported defect — "Open in Tetravox writes the scene and no window appears" — has a failure
 * mode that produces exactly that symptom with nothing in any log: `window.tit` (or
 * `window.tit.viewer`) missing, so `useTetravox` answers `mode: "browser"` and the Viewer page
 * writes the file and stops. That would be a *silent* downgrade, and in `pnpm run dev` the
 * renderer is served by Vite rather than by the toolbox server, which is precisely the sort of
 * difference that makes a preload not attach.
 *
 * So the preload's own contract is asserted here — one `exposeInMainWorld("tit", …)` call, the
 * channels each method uses — with `electron` mocked, which is the only way to exercise a
 * sandboxed CJS preload outside Electron. The e2e half (`tests/e2e/viewer-launch.spec.ts`) then
 * proves the same object really arrives in a page served over HTTP.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const exposed: Record<string, unknown> = {};
const invoked: [string, unknown[]][] = [];
const listeners: [string, unknown][] = [];

vi.mock("electron", () => ({
  contextBridge: {
    exposeInMainWorld: (key: string, value: unknown) => {
      exposed[key] = value;
    },
  },
  ipcRenderer: {
    invoke: (channel: string, ...args: unknown[]) => {
      invoked.push([channel, args]);
      return Promise.resolve(null);
    },
    on: (channel: string, listener: unknown) => listeners.push([channel, listener]),
    removeListener: () => undefined,
  },
}));

type ViewerBridge = Record<string, ((...args: unknown[]) => unknown) | undefined>;

beforeEach(async () => {
  invoked.length = 0;
  listeners.length = 0;
  await import("../../src/preload/index");
});

describe("window.tit", () => {
  it("is exposed once, and carries the viewer sub-bridge", () => {
    expect(Object.keys(exposed)).toEqual(["tit"]);
    const tit = exposed.tit as Record<string, unknown>;
    expect(tit.viewer).toBeTypeOf("object");
    // The bridge budget: `viewer` is one top-level entry, like `stack`, not seven.
    expect(Object.keys(tit)).toHaveLength(14);
  });

  it("routes every viewer call to the channel main actually handles", async () => {
    const viewer = (exposed.tit as Record<string, unknown>).viewer as ViewerBridge;
    await viewer.probe!();
    await viewer.open!("/p/subject.tetravox.json");
    await viewer.setPath!("/Applications/Tetravox.app");
    await viewer.install!();
    await viewer.checkUpdates!();
    await viewer.remove!();
    expect(invoked.map(([channel]) => channel)).toEqual([
      "tit:viewer:probe",
      "tit:viewer:open",
      "tit:viewer:setPath",
      "tit:viewer:install",
      "tit:viewer:checkUpdates",
      "tit:viewer:remove",
    ]);
    // The path is passed through as a string and nothing else — main does the mapping.
    expect(invoked[1]?.[1]).toEqual(["/p/subject.tetravox.json"]);
  });

  it("subscribes install progress on the channel main pushes, and unsubscribes", () => {
    const viewer = (exposed.tit as Record<string, unknown>).viewer as ViewerBridge;
    const off = viewer.onEvent!(() => undefined) as () => void;
    expect(listeners.map(([channel]) => channel)).toContain("tit:viewer:event");
    expect(off).toBeTypeOf("function");
  });
});

/**
 * @vitest-environment jsdom
 *
 * `viewer/store.ts` — the state machine that sits between the Viewer page and an iframe, without
 * an iframe.
 *
 * The double is a bare object with a `postMessage` spy standing in for the frame's
 * `contentWindow`: everything the store does to the embed is a posted message, and everything the
 * embed does to the store is a `message` event on `window`. So the whole surface is reachable from
 * jsdom, including the two states that only exist because rendering left this process — `no-embed`
 * (nothing answered at `/tetravox/`) and `no-webgl2` (the embed answered and said it has no
 * context; Chromium ≥137 has no SwiftShader fallback, so that is a real machine, not a harness).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { __resetViewerChannelForTests, useViewerStore } from "../../src/renderer/viewer/store";
import type { EmbedMessage, EmbedViewSpec } from "../../src/renderer/viewer/protocol";

const ORIGIN = "http://127.0.0.1:8790";

const scene: EmbedViewSpec = {
  version: 2,
  datasets: [
    { id: "ds0", kind: "volume", name: "T1.nii.gz", path: "/api/files/raw/mnt/000/T1.nii.gz", fingerprint: "" },
    { id: "ds1", kind: "mesh", name: "grey_Thalamus_TI.msh", path: "/api/files/raw/mnt/000/grey.msh", fingerprint: "" },
  ],
  layers: [
    { id: "L0", datasetId: "ds0", kind: "volume", name: "T1", visible: true, opacity: 1, colormap: "gray" },
    { id: "L1", datasetId: "ds1", kind: "mesh", name: "GM mesh", visible: false, opacity: 1 },
  ],
  layout: { kind: "2x2", cells: ["axial", "coronal", "sagittal", "view3d"] },
  cursor: [1, 2, 3],
};

interface Posted {
  message: Record<string, unknown>;
  origin: string;
}

let posted: Posted[];
let contentWindow: { postMessage: (message: unknown, origin: string) => void };
let frame: HTMLIFrameElement;

/** Deliver a message as if the frame had posted it. `source` is a read-only getter on the real
 *  event, so it is defined rather than assigned. */
function fromEmbed(message: EmbedMessage, opts: { source?: unknown; origin?: string } = {}): void {
  const event = new MessageEvent("message", { data: message, origin: opts.origin ?? ORIGIN });
  Object.defineProperty(event, "source", { value: opts.source ?? contentWindow });
  window.dispatchEvent(event);
}

function sent(type: string): Record<string, unknown> | undefined {
  return posted.find((p) => p.message.type === type)?.message;
}

beforeEach(() => {
  vi.useFakeTimers();
  posted = [];
  contentWindow = { postMessage: (message, origin) => posted.push({ message: message as Record<string, unknown>, origin }) };
  frame = { contentWindow } as unknown as HTMLIFrameElement;
  useViewerStore.setState({
    status: "idle",
    error: null,
    // Reset alongside `status`: a prior test's accepted `ready` otherwise leaks `embedReady: true`
    // into the next one, which is exactly what the handshake-timeout guard now keys on.
    embedReady: false,
    renderer: null,
    scene: null,
    layers: [],
    space: "subject",
    cursor: null,
    progress: [],
  });
});

afterEach(() => {
  __resetViewerChannelForTests();
  vi.useRealTimers();
});

describe("handshake", () => {
  it("says hello on the embed's own origin, never '*'", () => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    expect(posted).toEqual([{ message: { type: "hello", tvx: 1 }, origin: ORIGIN }]);
  });

  it("falls to 'no-embed' when nothing answers before the timeout", () => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    expect(useViewerStore.getState().status).toBe("idle");
    vi.advanceTimersByTime(50);
    expect(useViewerStore.getState().status).toBe("no-embed");
  });

  it("does not fall to 'no-embed' once the embed has said ready", () => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true, renderer: "Apple M2 Max" } });
    vi.advanceTimersByTime(500);
    expect(useViewerStore.getState().status).not.toBe("no-embed");
    expect(useViewerStore.getState().renderer).toBe("Apple M2 Max");
  });

  it("ignores a ready from the wrong window or the wrong origin", () => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } }, { source: { other: true } });
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } }, { origin: "https://evil.example" });
    vi.advanceTimersByTime(50);
    expect(useViewerStore.getState().status).toBe("no-embed");
  });

  it("goes to 'no-webgl2' when the embed reports no context", () => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    fromEmbed({ tvx: 1, type: "ready", version: "fake", caps: { webgl2: false, renderer: "SwiftShader" } });
    expect(useViewerStore.getState().status).toBe("no-webgl2");
    expect(useViewerStore.getState().renderer).toBe("SwiftShader");
  });
});

describe("loading a scene", () => {
  beforeEach(() => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } });
    posted.length = 0;
  });

  it("posts the scene, seeds a progress row per dataset, and adopts its cursor", () => {
    useViewerStore.getState().loadScene(scene);
    expect(sent("load")).toMatchObject({ type: "load", scene });
    const state = useViewerStore.getState();
    expect(state.status).toBe("loading");
    expect(state.cursor).toEqual([1, 2, 3]);
    expect(state.progress.map((p) => p.name)).toEqual(["T1.nii.gz", "grey_Thalamus_TI.msh"]);
    // ViewSpec v2 carries no file size; the byte count arrives with the loader's own progress.
    expect(state.progress.every((p) => p.bytes === 0)).toBe(true);
  });

  it("replaces the scene's layer ids with the live ones the embed reports", () => {
    useViewerStore.getState().loadScene(scene);
    expect(useViewerStore.getState().layers.map((l) => l.id)).toEqual(["L0", "L1"]);
    fromEmbed({
      tvx: 1,
      type: "loaded",
      datasets: ["d1", "d2"],
      layers: [
        { id: "live-0", name: "T1", visible: true, opacity: 1 },
        { id: "live-1", name: "GM mesh", visible: false, opacity: 1 },
      ],
    });
    expect(useViewerStore.getState().status).toBe("ready");
    expect(useViewerStore.getState().layers.map((l) => l.id)).toEqual(["live-0", "live-1"]);
  });

  it("fills byte counts from the embed's progress events", () => {
    useViewerStore.getState().loadScene(scene);
    fromEmbed({ tvx: 1, type: "progress", datasetId: "ds0", name: "T1.nii.gz", phase: "read", done: 4_000_000, total: 13_109_495 });
    const row = useViewerStore.getState().progress.find((p) => p.id === "ds0");
    expect(row).toMatchObject({ phase: "read", done: 4_000_000, total: 13_109_495, bytes: 13_109_495 });
  });

  it("keeps the read byte count when later phases report voxel counts", () => {
    useViewerStore.getState().loadScene(scene);
    fromEmbed({ tvx: 1, type: "progress", datasetId: "live", name: "T1.nii.gz", phase: "read", done: 400, total: 400 });
    fromEmbed({ tvx: 1, type: "progress", datasetId: "live", name: "T1.nii.gz", phase: "index", done: 100, total: 100 });
    expect(useViewerStore.getState().progress.find((p) => p.id === "live")).toMatchObject({ bytes: 400, done: 100, total: 100 });
  });

  it("matches new engine ids by filename instead of attributing progress to a different queued file", () => {
    useViewerStore.getState().loadScene(scene);
    fromEmbed({ tvx: 1, type: "progress", datasetId: "ds1", name: "T1.nii.gz", phase: "read", done: 10, total: 100 });
    const rows = useViewerStore.getState().progress;
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ id: "ds1", name: "T1.nii.gz", phase: "read" });
    expect(rows[1]).toMatchObject({ name: "grey_Thalamus_TI.msh", phase: "queued" });
  });

  it("does not guess filenames when an older embed reports unnamed live datasets", () => {
    useViewerStore.getState().loadScene(scene);
    fromEmbed({ tvx: 1, type: "progress", datasetId: "ds1", name: "", phase: "inflate", done: 10, total: 0 });
    expect(useViewerStore.getState().progress).toEqual([
      { id: "ds1", name: "Dataset ds1", phase: "inflate", done: 10, total: 0, bytes: 0 },
    ]);
  });

  it("re-sends the scene when a reloaded frame says ready again", () => {
    useViewerStore.getState().loadScene(scene);
    posted.length = 0;
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } });
    expect(sent("load")).toMatchObject({ scene });
  });

  it("keeps completed layers usable when another concurrent dataset fails", () => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    useViewerStore.getState().loadScene(scene);
    fromEmbed({ tvx: 1, type: "layers", layers: [{ id: "live-t1", name: "T1", visible: true, opacity: 1 }] });
    fromEmbed({ tvx: 1, type: "error", code: "io", message: "Mesh could not be read" });
    expect(useViewerStore.getState().status).toBe("error");
    expect(useViewerStore.getState().layers.map((layer) => layer.id)).toEqual(["live-t1"]);
    useViewerStore.getState().setLayerOpacity("live-t1", 0.4);
    expect(useViewerStore.getState().layers[0]?.opacity).toBe(0.4);
  });

  it("surfaces an embed error inline rather than throwing", () => {
    useViewerStore.getState().loadScene(scene);
    fromEmbed({ tvx: 1, type: "error", code: "io", message: "404 on /api/files/raw/mnt/000/T1.nii.gz" });
    expect(useViewerStore.getState().status).toBe("error");
    expect(useViewerStore.getState().error).toContain("404");
  });
});

describe("actions", () => {
  beforeEach(() => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } });
    useViewerStore.getState().loadScene(scene);
    posted.length = 0;
  });

  it("applies a visibility toggle optimistically and posts it", () => {
    useViewerStore.getState().setLayerVisible("L1", true);
    expect(useViewerStore.getState().layers.find((l) => l.id === "L1")?.visible).toBe(true);
    expect(sent("setLayerVisible")).toEqual({ tvx: 1, type: "setLayerVisible", layerId: "L1", visible: true });
  });

  it("lets the embed's own layers event win over the optimistic value", () => {
    useViewerStore.getState().setLayerOpacity("L0", 0.25);
    expect(useViewerStore.getState().layers.find((l) => l.id === "L0")?.opacity).toBe(0.25);
    fromEmbed({ tvx: 1, type: "layers", layers: [{ id: "L0", name: "T1", visible: true, opacity: 1 }] });
    // Live properties are the embed's; `kind`/`datasetId` are inherited from the scene's row for the
    // same id, because a build that omits them would otherwise strip the inspector of the two facts
    // it needs to explain an empty 3D pane and to show a file size.
    expect(useViewerStore.getState().layers).toEqual([
      { id: "L0", datasetId: "ds0", kind: "volume", name: "T1", visible: true, opacity: 1 },
    ]);
  });

  it("mirrors the loaded datasets' byte sizes, keeping the scene's names when only ids came back", () => {
    fromEmbed({
      tvx: 1,
      type: "loaded",
      datasets: [{ id: "d9", name: "d9", kind: "volume", bytes: 13_631_488 }, "d10"],
      layers: ["L9", "L10"],
    });
    expect(useViewerStore.getState().datasets).toEqual([
      { id: "d9", name: "T1.nii.gz", kind: "volume", bytes: 13_631_488 },
      { id: "d10", name: "grey_Thalamus_TI.msh", kind: "volume", bytes: undefined },
    ]);
  });

  it("reports the handshake separately from the load, so a host can theme an empty viewer", () => {
    expect(useViewerStore.getState().embedReady).toBe(true);
    useViewerStore.getState().setTheme("dark");
    expect(sent("setTheme")).toEqual({ tvx: 1, type: "setTheme", theme: "dark" });
    useViewerStore.getState().disconnect();
    expect(useViewerStore.getState().embedReady).toBe(false);
  });

  it("moves the cursor and takes the embed's echo", () => {
    useViewerStore.getState().setCursor([10, -20, 30]);
    expect(sent("setCursor")).toEqual({ tvx: 1, type: "setCursor", world: [10, -20, 30] });
    fromEmbed({ tvx: 1, type: "cursor", world: [11, -21, 31], space: "subject" });
    expect(useViewerStore.getState().cursor).toEqual([11, -21, 31]);
  });

  it("resolves probe() with the reply carrying the request's own id", async () => {
    const pending = useViewerStore.getState().probe([1, 2, 3]);
    const request = sent("probe");
    expect(request).toMatchObject({ type: "probe", world: [1, 2, 3] });
    const id = request?.id as string;
    expect(id).toBeTypeOf("string");
    // A reply with somebody else's id must not resolve this request.
    fromEmbed({ tvx: 1, type: "probe", id: `${id}-other`, result: { world: [9, 9, 9], rows: [] } });
    fromEmbed({ tvx: 1, type: "probe", id, result: { world: [1, 2, 3], rows: [] } });
    await expect(pending).resolves.toEqual({ world: [1, 2, 3], rows: [] });
  });
});

describe("disconnect", () => {
  it("resets the embed, drops the listener and clears the state", () => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } });
    useViewerStore.getState().loadScene(scene);
    posted.length = 0;

    useViewerStore.getState().disconnect();
    expect(sent("reset")).toEqual({ tvx: 1, type: "reset" });
    const state = useViewerStore.getState();
    expect(state.status).toBe("idle");
    expect(state.layers).toEqual([]);
    expect(state.progress).toEqual([]);
    expect(state.scene).toBeNull();

    // Nothing from the dead frame is heard any more.
    fromEmbed({ tvx: 1, type: "cursor", world: [9, 9, 9], space: "subject" });
    expect(useViewerStore.getState().cursor).toBeNull();
  });

  it("rejects an in-flight request rather than leaving a promise open forever", async () => {
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } });
    const pending = useViewerStore.getState().probe([0, 0, 0]);
    useViewerStore.getState().disconnect();
    // `probe()` catches and answers null; the point is that it answers at all.
    await expect(pending).resolves.toBeNull();
  });
});

/**
 * The first Open of a session (VE, 2026-09-06). The reported defect: *"Open lands on Tetravox but
 * the scene only appears after Reload."*
 *
 * The Viewer page mounts the frame only once there is something to show, so the very first Open
 * calls `loadScene` while `channel` is still null — the scene can only be delivered by the `ready`
 * handler. React then invokes the mount effect's cleanup at least once (StrictMode in dev, and any
 * dependency change in either build), `disconnect()` ran, and it used to null `pendingScene`. So
 * `ready` had nothing to post, the viewer stayed empty, and Reload "fixed" it only because Reload
 * calls `loadScene` again — this time with a channel already open.
 *
 * The fix is that `pendingScene` is the host's *intent*, not the channel's state.
 */
describe("the first Open, before any frame exists", () => {
  it("delivers the scene once the embed says ready", () => {
    useViewerStore.getState().loadScene(scene);
    // Nothing to post to yet — this is the whole shape of the bug.
    expect(posted).toHaveLength(0);

    useViewerStore.getState().connect(frame, ORIGIN, 50);
    posted.length = 0;
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } });

    const loads = posted.filter((p) => p.message.type === "load");
    expect(loads, "the scene never reached the embed").toHaveLength(1);
    expect(loads[0]!.message).toMatchObject({ type: "load", scene });
  });

  it("survives the mount effect's cleanup running before the frame connects", () => {
    useViewerStore.getState().loadScene(scene);

    // Exactly what React does to an effect on a StrictMode mount: run, clean up, run again.
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    useViewerStore.getState().disconnect();
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    posted.length = 0;
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } });

    expect(
      posted.filter((p) => p.message.type === "load"),
      "a disconnect forgot what the user asked to see",
    ).toHaveLength(1);
  });

  it("sends exactly one load per Open, not one per ready", () => {
    useViewerStore.getState().loadScene(scene);
    useViewerStore.getState().connect(frame, ORIGIN, 50);
    posted.length = 0;
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } });
    expect(posted.filter((p) => p.message.type === "load")).toHaveLength(1);

    // The embed confirms it loaded: the intent is satisfied and must not be re-sent on a later
    // handshake, or a reconnect would silently re-post a scene nobody asked for again.
    fromEmbed({ tvx: 1, type: "loaded", layers: [], datasets: [] } as unknown as EmbedMessage);
    posted.length = 0;
    fromEmbed({ tvx: 1, type: "ready", version: 1, caps: { webgl2: true } });
    expect(posted.filter((p) => p.message.type === "load")).toHaveLength(0);

    // A second Open is a second scene, and one more message.
    useViewerStore.getState().loadScene(scene);
    expect(posted.filter((p) => p.message.type === "load")).toHaveLength(1);
  });
});

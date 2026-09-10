// @vitest-environment jsdom
/** Read-only target preview lifecycle; real geometry is tested in the backend numerical suite. */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TargetPreview } from "../../src/renderer/pages/_shared/scene/TargetPreview";
import { targetPreviewRoi } from "../../src/renderer/pages/_shared/scene/targetPreviewModel";
import type { RoiValue } from "../../src/renderer/pages/_shared/roi";
import type { EmbedMessage } from "../../src/renderer/viewer/protocol";

const channels = vi.hoisted(() => ({ create: vi.fn(), post: vi.fn(), dispose: vi.fn() }));
vi.mock("../../src/renderer/viewer/channel", () => ({
  HANDSHAKE_TIMEOUT_MS: 10000,
  createChannel: channels.create,
}));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const mask: RoiValue = { mode: "mask", path: "/mask.nii.gz", space: "mni", tissues: "GM" };
const sphere: RoiValue = { mode: "spherical", spheres: [{ x: 1, y: 2, z: 3, radius: 4 }], space: "subject", volumetric: false, tissues: "GM" };
const scene = { datasets: [], layers: [], marker: "current" };

describe("target form conversion", () => {
  it("keeps physical centers and radii, mask space, and atlas labels", () => {
    expect(targetPreviewRoi(sphere)).toEqual({ kind: "spherical", spheres: [{ center: [1, 2, 3], radius: 4 }], space: "subject" });
    expect(targetPreviewRoi(mask)).toEqual({ kind: "mask", path: "/mask.nii.gz", space: "mni" });
    expect(targetPreviewRoi({ mode: "subcortical", atlas: "A", atlasSpace: "mni", regions: [{ id: 7, name: "Region" }], tissues: "WM" })).toEqual({ kind: "subcortical", atlas: "A", labels: [7], space: "mni" });
  });
  it("previews saved CSV targets together without changing separate-run selection", () => {
    const saved: RoiValue = { mode: "saved", selected: ["Left", "Right.csv"], combine: false, radius: 3, space: "mni" };
    expect(targetPreviewRoi(saved)).toEqual({ kind: "saved", names: ["Left", "Right.csv"], radius: 3, space: "mni" });
    expect(saved.combine).toBe(false);
    expect(targetPreviewRoi({ ...saved, selected: [] })).toBeNull();
    expect(targetPreviewRoi({ ...saved, radius: 0 })).toBeNull();
  });
  it("refuses incomplete or nonfinite spheres and unsupported cortical targets", () => {
    expect(targetPreviewRoi({ ...sphere, spheres: [{ x: 1, y: undefined, z: 3, radius: 4 }] })).toBeNull();
    expect(targetPreviewRoi({ ...sphere, spheres: [{ x: NaN, y: 2, z: 3, radius: 4 }] })).toBeNull();
    expect(targetPreviewRoi({ ...sphere, spheres: [{ x: 1, y: 2, z: 3, radius: 0 }] })).toBeNull();
    expect(targetPreviewRoi({ mode: "cortical", atlas: "DK40", regions: [] })).toBeNull();
  });
});

describe("target preview lifetime", () => {
  let root: Root;
  let container: HTMLDivElement;
  let client: QueryClient;
  let receive: (message: EmbedMessage) => void;
  const fetcher = vi.fn<typeof fetch>();
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockReset();
    channels.post.mockReset(); channels.dispose.mockReset(); channels.create.mockReset();
    channels.create.mockImplementation((_frame, _origin, callback) => {
      receive = callback;
      return { post: channels.post, dispose: channels.dispose };
    });
    client = new QueryClient();
    container = document.createElement("div"); document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount()); client.clear(); container.remove();
    vi.unstubAllGlobals(); vi.useRealTimers();
  });
  async function render(roi: RoiValue, subject = "ernie") {
    await act(async () => root.render(<QueryClientProvider client={client}><TargetPreview subject={subject} roi={roi} /></QueryClientProvider>));
  }
  async function advance(ms: number) { await act(async () => vi.advanceTimersByTimeAsync(ms)); }
  function respond() { return new Response(JSON.stringify({ scene }), { status: 200 }); }

  it("retains its private viewport across edits while hiding stale geometry", async () => {
    fetcher.mockResolvedValue(respond());
    await render(mask); await advance(260); await advance(1);
    expect(container.querySelector("iframe")?.getAttribute("src")).toContain("presentation=viewport");
    act(() => receive({ type: "ready", caps: { webgl2: true } } as EmbedMessage));
    expect(channels.post.mock.calls).toContainEqual([{ type: "setPickEvents", enabled: false }]);
    expect(channels.post.mock.calls).toContainEqual([{ type: "load", scene, id: "target-1" }]);
    act(() => receive({ type: "loaded", id: "target-1" } as EmbedMessage));
    const frame = container.querySelector("iframe")!;
    expect(frame.parentElement!.style.visibility).toBe("visible");
    const count = channels.post.mock.calls.length;
    act(() => receive({ type: "pick", label: { id: 9 } } as EmbedMessage));
    expect(channels.post).toHaveBeenCalledTimes(count);
    await render({ ...mask, path: "/other.nii" });
    expect(container.querySelector("iframe")).toBe(frame);
    expect(frame.parentElement!.style.visibility).toBe("hidden");
    expect(channels.dispose).not.toHaveBeenCalled();
    expect(fetcher).toHaveBeenCalledTimes(1);
    fetcher.mockResolvedValue(new Response(JSON.stringify({ scene: { ...scene, marker: "new" } }), { status: 200 }));
    await advance(260); await advance(1);
    expect(channels.create).toHaveBeenCalledOnce();
    expect(container.querySelector("iframe")).toBe(frame);
    act(() => receive({ type: "loaded", id: "target-1" } as EmbedMessage));
    expect(frame.parentElement!.style.visibility).toBe("hidden");
    act(() => receive({ type: "loaded", id: "target-2" } as EmbedMessage));
    expect(frame.parentElement!.style.visibility).toBe("visible");
  });

  it("cancels stale requests and never shows their response over an incomplete form", async () => {
    let finish: (response: Response) => void = () => {};
    fetcher.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    await render(mask); await advance(260); await advance(1);
    const signal = fetcher.mock.calls[0]![1]!.signal!;
    await render({ ...mask, path: "" });
    expect(signal.aborted).toBe(true);
    await act(async () => finish(respond())); await advance(300);
    expect(container.querySelector("iframe")?.parentElement?.style.visibility).toBe("hidden");
    expect(container.textContent).toContain("Complete the target");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("debounces typed sphere changes and exposes missing anatomy errors", async () => {
    fetcher.mockResolvedValue(new Response(JSON.stringify({ detail: "Subject T1 is missing" }), { status: 404 }));
    await render(sphere); await advance(150);
    await render({ ...sphere, spheres: [{ x: 5, y: 2, z: 3, radius: 4 }] }); await advance(150);
    expect(fetcher).not.toHaveBeenCalled();
    await advance(110); await advance(1);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetcher.mock.calls[0]![1]!.body as string).roi.spheres[0].center).toEqual([5, 2, 3]);
    expect(container.textContent).toContain("Subject T1 is missing");
    expect(container.querySelector("iframe")?.parentElement?.style.visibility).toBe("hidden");
  });
});

// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { TargetPreview } from "../../src/renderer/pages/_shared/scene/TargetPreview";

it("prepares a target only on explicit native open and hands off the exported file", async () => {
  const scene = { version: 2, datasets: [], layers: [] };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ scene }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ scene_path: "/mnt/project/target.tetravox.json" }) });
  const openNativeTetravox = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetchMock);
  Object.defineProperty(window, "tit", { configurable: true, value: { openNativeTetravox } });
  const container = document.createElement("div");
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  try {
    await act(async () => root.render(<QueryClientProvider client={client}><TargetPreview subject="101" roi={{ mode: "mask", path: "/mnt/target.nii.gz", space: "mni", tissues: "GM" }} /></QueryClientProvider>));
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => container.querySelector("button")!.click());
    await vi.waitFor(() => expect(openNativeTetravox).toHaveBeenCalledWith("/mnt/project/target.tetravox.json"));
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({ subject: "101", roi: { kind: "mask", path: "/mnt/target.nii.gz", space: "mni" } });
    expect(JSON.parse(fetchMock.mock.calls[1]![1].body)).toEqual({ scene, name: "target-preview" });
    expect(container.querySelector("iframe")).toBeNull();
  } finally {
    act(() => root.unmount());
    client.clear();
    Reflect.deleteProperty(window, "tit");
    vi.unstubAllGlobals();
  }
});

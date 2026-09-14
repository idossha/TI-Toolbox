// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { TargetPreview } from "../../src/renderer/pages/_shared/scene/TargetPreview";
const scene = vi.hoisted(() => ({ props: null as Record<string, unknown> | null }));
vi.mock("../../src/renderer/pages/_shared/scene/ScenePane", () => ({ ScenePane: (props: Record<string, unknown>) => { scene.props = props; return <div>Reference atlas</div>; } }));

it("selects a default bundled atlas and synchronizes atlas mode with the form", async () => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  const container = document.createElement("div"); const root = createRoot(container);
  const client = new QueryClient(); const change = vi.fn();
  try {
    await act(async () => root.render(<QueryClientProvider client={client}><TargetPreview subject="101" roi={{ mode: "subcortical", atlas: undefined, atlasSpace: "subject", regions: [], tissues: "GM" }} onRoiChange={change} /></QueryClientProvider>));
    expect(scene.props!.atlas).toBe("labeling.nii.gz");
    expect(scene.props!.subject).toBeUndefined();
    (scene.props!.onAtlasChange as (atlas: string, kind: string) => void)("DK40", "cortical");
    expect(change).toHaveBeenLastCalledWith({ mode: "cortical", atlas: "DK40", regions: [] });
    (scene.props!.onAtlasChange as (atlas: string, kind: string) => void)("labeling.nii.gz", "subcortical");
    expect(change).toHaveBeenLastCalledWith({ mode: "subcortical", atlas: "labeling.nii.gz", atlasSpace: "subject", tissues: "GM", regions: [] });
    expect(fetchMock).not.toHaveBeenCalled();
  } finally { act(() => root.unmount()); client.clear(); vi.unstubAllGlobals(); }
});

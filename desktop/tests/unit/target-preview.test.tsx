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

it("shows the live scene for an atlas target and the native button only for the modes with no anatomy", async () => {
  // Regression: the Optimizer gated the pane on `method === "flex"`, so an Ex or mEx row
  // targeting a subcortical atlas — which `roiModesFor` offers and `tit/opt/ex/roi.py`
  // accepts — got only "Open target in TetraVox". The mode alone decides.
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient();
  const render = async (roi: Parameters<typeof TargetPreview>[0]["roi"]) => {
    const container = document.createElement("div"); const root = createRoot(container);
    await act(async () => root.render(<QueryClientProvider client={client}><TargetPreview subject="101" roi={roi} /></QueryClientProvider>));
    const html = container.innerHTML;
    act(() => root.unmount());
    return html;
  };
  try {
    scene.props = null;
    expect(await render({ mode: "subcortical", atlas: "labeling.nii.gz", atlasSpace: "subject", regions: [], tissues: "GM" })).toContain("Reference atlas");
    expect(scene.props).not.toBeNull();
    expect(await render({ mode: "cortical", atlas: "DK40", regions: [] })).toContain("Reference atlas");
    for (const roi of [
      { mode: "saved", selected: [], combine: false, radius: 10, space: "subject" },
      { mode: "spherical", spheres: [], space: "subject", volumetric: false, tissues: "GM" },
    ] as const) {
      const html = await render(roi as never);
      expect(html).toContain("Open target in TetraVox");
      expect(html).not.toContain("Reference atlas");
    }
  } finally { client.clear(); vi.unstubAllGlobals(); }
});

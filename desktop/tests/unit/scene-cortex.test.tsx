// @vitest-environment jsdom
/**
 * Where a cortex is drawn (user decision, 2026-11-07): the Networks tab of the Visual exporter has
 * one and offers a switch for it; no other pane offers one, and a sub-cortical atlas has none.
 *
 * The atlases come from the packaged guides' own manifests, so a rebuilt guide that aligned a
 * sub-cortical atlas to `gm` fails here. The split into cortical and sub-cortical MNI volumes is
 * authored, from what each atlas parcellates (docs/wiki/atlases.md). The switch itself, on pixels
 * and picks, is in tests/e2e/network-scene-layout.spec.ts.
 *
 * Run: npx vitest run tests/unit/scene-cortex.test.tsx
 */
import React, { act } from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider, type UseQueryResult } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { atlasSurfacePart } from "../../src/renderer/pages/_shared/scene/model";
import { TargetPreview } from "../../src/renderer/pages/_shared/scene/TargetPreview";
import { ExportPreview } from "../../src/renderer/pages/panels/visual-exporter/ExportPreview";
import type { NetworkRoiValue } from "../../src/renderer/pages/_shared/roi/types";

const scene = vi.hoisted(() => ({ props: null as Record<string, unknown> | null }));
vi.mock("../../src/renderer/pages/_shared/scene/ScenePane", () => ({
  ScenePane: (props: Record<string, unknown>) => {
    scene.props = props;
    return null;
  },
}));

const atlases = (guide: string): { id: string; kind?: string; aligned_to?: string }[] =>
  (JSON.parse(readFileSync(resolve(__dirname, `../../../tit/scene/${guide}/manifest.json`), "utf8")) as { atlases: { id: string }[] }).atlases;

const CORTICAL_VOLUME = /^(HarvardOxford-cortl|MNI_Glasser|Schaefer2018)/;

describe("a sub-cortical atlas has no cortex", () => {
  it("has sub-cortical atlases to check on both packaged heads", () => {
    expect(atlases("guide").filter((entry) => entry.kind === "subcortical").length).toBeGreaterThan(0);
    expect(atlases("guide-mni").filter((entry) => !CORTICAL_VOLUME.test(entry.id)).length).toBeGreaterThan(0);
  });

  it("draws each packaged atlas on the surface of what it parcellates", () => {
    for (const entry of atlases("guide")) {
      expect(atlasSurfacePart(entry) === "gm", entry.id).toBe(entry.kind !== "subcortical");
    }
    for (const entry of atlases("guide-mni")) {
      expect(atlasSurfacePart(entry) === "gm", entry.id).toBe(CORTICAL_VOLUME.test(entry.id));
    }
  });

  it("falls back to the cortex only for an atlas no manifest says is sub-cortical", () => {
    expect(atlasSurfacePart({ kind: "subcortical" })).toBe("subcortical");
    expect(atlasSurfacePart({})).toBe("gm");
    expect(atlasSurfacePart(undefined)).toBe("gm");
  });
});

describe("only the Networks tab offers the cortex switch", () => {
  const value: NetworkRoiValue = { mode: "network", space: "subject", seeds: [], pairs: [], minN: 10, minCount: 2, name: "" };
  const roots: (() => void)[] = [];
  afterEach(() => {
    roots.splice(0).forEach((unmount) => unmount());
    vi.unstubAllGlobals();
    scene.props = null;
  });
  const mount = async (node: React.ReactNode) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const root = createRoot(document.createElement("div"));
    await act(async () => root.render(<QueryClientProvider client={client}>{node}</QueryClientProvider>));
    roots.push(() => {
      act(() => root.unmount());
      client.clear();
    });
  };

  it("the Visual exporter's Networks pane offers it", async () => {
    await mount(
      <ExportPreview mode="networks" subjectId="CHN" simulationName="" montage={{} as UseQueryResult<never, Error>} atlas="" regions={[]} onRegionsChange={() => {}} onAtlasChange={() => {}} montageOnly={false} labels={[]} niftiPath="" fieldName="" networkValue={value} />,
    );
    expect(scene.props!.cortexSwitch).toBe(true);
  });

  it("the Optimizer's Network target does not", async () => {
    await mount(<TargetPreview subject="CHN" roi={value} />);
    expect(scene.props).not.toBeNull();
    expect(scene.props!.cortexSwitch).toBeFalsy();
  });

  it("an atlas target does not", async () => {
    await mount(<TargetPreview subject="CHN" roi={{ mode: "subcortical", atlas: "labeling.nii.gz", space: "subject", regions: [], tissues: "GM" }} />);
    expect(scene.props).not.toBeNull();
    expect(scene.props!.cortexSwitch).toBeFalsy();
  });
});

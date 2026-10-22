// @vitest-environment jsdom
/**
 * An Ex/mEx subcortical target offers no "Tissue type" control, because the search cannot honour
 * one (2026-10-22).
 *
 * The control's own help text says it picks the "Tissue compartment(s) to include when evaluating
 * the volume ROI". Ex/mEx never read it: `exTargets`/`buildExConfig` (optimizer/exConfig.ts) drop
 * `value.tissues`, `ExConfig`/`MExConfig` have no tissue field, and `ExSearchEngine` scores every
 * leadfield element (tissues 1 and 2) inside the label. So switching it to WM sent the identical
 * config and gave identical metrics. Flex reads the tissue and keeps the control. The Ex/mEx
 * pickers are the ones that offer saved ROIs (`roiModesFor("ex")`); flex's never do.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/roi-picker-ex-tissue.test.tsx`.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("../../src/renderer/pages/_shared/roi/api", () => ({
  getAtlases: vi.fn(async () => [{ id: "labeling.nii.gz", name: "labeling.nii.gz", path: "/p/labeling.nii.gz" }]),
  getAtlasRegions: vi.fn(async () => [{ id: 17, name: "Left-Hippocampus" }]),
  getRois: vi.fn(async () => []),
  saveRoi: vi.fn(),
  deleteRoi: vi.fn(),
  uploadMask: vi.fn(),
}));
vi.mock("../../src/renderer/pages/_shared/scene/queries", () => ({ useGuideRegions: () => ({ data: undefined }) }));

import { RoiPicker } from "../../src/renderer/pages/_shared/roi/RoiPicker";
import type { RoiValue } from "../../src/renderer/pages/_shared/roi/types";
import { roiModesFor } from "../../src/renderer/pages/optimizer/rows";
import { buildExConfig, buildMExConfig, defaultMExFormState, exTargets, type ExFormState } from "../../src/renderer/pages/optimizer/exConfig";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const cleanups: (() => void)[] = [];
afterEach(() => cleanups.splice(0).forEach((c) => c()));

const HIPPOCAMPUS = (tissues: "GM" | "WM" | "both"): RoiValue => ({
  mode: "subcortical",
  space: "subject",
  atlas: "labeling.nii.gz",
  regions: [{ id: 17, name: "Left-Hippocampus" }],
  tissues,
});

async function render(modes: RoiValue["mode"][], value: RoiValue): Promise<HTMLElement> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(
    <QueryClientProvider client={client}>
      <RoiPicker value={value} onChange={() => {}} modes={modes} subject="ernie" />
    </QueryClientProvider>,
  ));
  cleanups.push(() => { act(() => root.unmount()); container.remove(); });
  return container;
}

it("an Ex/mEx subcortical target shows no Tissue type control", async () => {
  const picker = await render(roiModesFor("ex"), HIPPOCAMPUS("GM"));
  // The panel itself rendered (its atlas and region fields are there) ...
  expect(picker.textContent).toContain("Volume atlas");
  expect(picker.textContent).toContain("Region(s)");
  // ... without the control whose choice the search drops.
  expect(picker.textContent).not.toContain("Tissue type");
  expect(picker.textContent).not.toContain("White matter (WM)");
});

it("a flex subcortical target keeps its Tissue type control", async () => {
  const picker = await render(roiModesFor("flex"), HIPPOCAMPUS("GM"));
  expect(picker.textContent).toContain("Tissue type");
});

it("the tissue never reaches an Ex or mEx config, which is why the control is gone", () => {
  const atlas = () => ({ path: "/p/labeling.nii.gz", name: "labeling.nii.gz" }) as never;
  const ex: ExFormState = {
    electrodeMode: "bucketed",
    buckets: { e1_plus: ["F3"], e1_minus: ["F4"], e2_plus: ["P3"], e2_minus: ["P4"] },
    pool: [],
    totalCurrent: 2,
    currentStep: 0.5,
    channelLimit: 1.5,
  };
  const configs = (["GM", "WM", "both"] as const).map((tissues) => {
    const [target] = exTargets(HIPPOCAMPUS(tissues), atlas);
    return {
      ex: buildExConfig("ernie", "lf.hdf5", ex, target!, "run"),
      mex: buildMExConfig("ernie", "lf.hdf5", defaultMExFormState(), target!, "run"),
    };
  });
  expect(configs[0]!.ex.roi_atlas).toEqual([{ atlas_path: "/p/labeling.nii.gz", label: 17, atlas_space: "subject" }]);
  expect(configs[1]).toEqual(configs[0]);
  expect(configs[2]).toEqual(configs[0]);
  expect(JSON.stringify(configs[0])).not.toMatch(/tissue/i);
});

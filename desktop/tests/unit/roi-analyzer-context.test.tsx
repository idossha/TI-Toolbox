// @vitest-environment jsdom
/**
 * The shared ROI picker in the Analyzer says what the Analyzer does (2026-10-21).
 *
 * The Analyzer runs one analysis per sphere (`rowTargets`; `AnalyzerConfig` has one center) and
 * reads the tissue from the row's Job settings, never the picker's "Volumetric evaluation" or
 * subcortical "Tissue type". The picker told Analyzer users "Multiple rows union into one combined
 * target" and offered those dead controls. Flex/Ex keep the union wording and the controls. The
 * strings are authored in RoiPicker.tsx; the API module is the boundary that is mocked.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("../../src/renderer/pages/_shared/roi/api", () => ({
  getAtlases: vi.fn(async () => []),
  getAtlasRegions: vi.fn(async () => []),
  getRois: vi.fn(async () => []),
  saveRoi: vi.fn(),
  deleteRoi: vi.fn(),
  uploadMask: vi.fn(),
}));
vi.mock("../../src/renderer/pages/_shared/scene/queries", () => ({ useGuideRegions: () => ({ data: undefined }) }));

import { RoiPicker } from "../../src/renderer/pages/_shared/roi/RoiPicker";
import { emptyRoi, type RoiMode } from "../../src/renderer/pages/_shared/roi/types";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const cleanups: (() => void)[] = [];
afterEach(() => cleanups.splice(0).forEach((c) => c()));

async function render(mode: RoiMode, analyzer: boolean): Promise<HTMLElement> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(
    <QueryClientProvider client={client}>
      <RoiPicker value={emptyRoi(mode)} onChange={() => {}} modes={[mode]} subject="ernie" analyzer={analyzer} />
    </QueryClientProvider>,
  ));
  cleanups.push(() => { act(() => root.unmount()); container.remove(); });
  return container;
}

it("Analyzer spheres are one job each and carry no volumetric control", async () => {
  const picker = await render("spherical", true);
  expect(picker.textContent).toContain("Each row is a sphere, analyzed as its own job.");
  expect(picker.textContent).not.toContain("union");
  expect(picker.textContent).not.toContain("Volumetric evaluation");
});

it("Flex/Ex spheres still union, with the volumetric control", async () => {
  const picker = await render("spherical", false);
  expect(picker.textContent).toContain("Multiple rows union into one combined target.");
  expect(picker.textContent).toContain("Volumetric evaluation");
});

it("an Analyzer subcortical target has no tissue control of its own", async () => {
  expect((await render("subcortical", true)).textContent).not.toContain("Tissue type");
  expect((await render("subcortical", false)).textContent).toContain("Tissue type");
});

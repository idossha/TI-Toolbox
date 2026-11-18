// @vitest-environment jsdom
/**
 * The subcortical picker's subject-space default atlas, `labeling.nii.gz`, is never asked for its
 * regions when this subject does not list it (2026-11-17).
 *
 * charm writes `labeling.nii.gz` into `m2m_<id>/segmentation/`; Dataset 000's sub-ernie has no such
 * folder, only FastSurfer's `aparc.DKTatlas+aseg.deep.*`. The picker still requested the default's
 * regions, the server answered 404, and Subcortical opened on "Could not load regions for this
 * atlas." The atlas list here is authored; the API module is the boundary that is mocked.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";

const getAtlases = vi.hoisted(() => vi.fn());
const getAtlasRegions = vi.hoisted(() => vi.fn(async () => [{ id: 10, name: "Left-Thalamus", hemi: null }]));
vi.mock("../../src/renderer/pages/_shared/roi/api", () => ({
  getAtlases,
  getAtlasRegions,
  getRois: vi.fn(async () => []),
  saveRoi: vi.fn(),
  deleteRoi: vi.fn(),
  uploadMask: vi.fn(),
}));
vi.mock("../../src/renderer/pages/_shared/scene/queries", () => ({ useGuideRegions: () => ({ data: undefined }) }));

import { RoiPicker } from "../../src/renderer/pages/_shared/roi/RoiPicker";
import { emptyRoi } from "../../src/renderer/pages/_shared/roi/types";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });

async function render(listed: string[]) {
  getAtlases.mockReset();
  getAtlasRegions.mockClear();
  getAtlases.mockResolvedValue(listed.map((id) => ({ id, name: id, kind: "volume", path: `/p/${id}` })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(
    <QueryClientProvider client={client}>
      <RoiPicker value={emptyRoi("subcortical", "subject")} onChange={() => {}} modes={["subcortical"]} subject="ernie" />
    </QueryClientProvider>,
  ));
  await settle();
  return () => { act(() => root.unmount()); container.remove(); client.clear(); };
}

it("a subject without labeling.nii.gz gets no regions request and no error", async () => {
  const cleanup = await render(["aparc.DKTatlas+aseg.deep.mgz"]);
  try {
    expect(getAtlasRegions).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("Could not load regions");
    expect(document.body.textContent).toContain("Select a volume atlas");
  } finally {
    cleanup();
  }
});

it("a subject that lists labeling.nii.gz still opens on it", async () => {
  const cleanup = await render(["labeling.nii.gz"]);
  try {
    expect(getAtlasRegions).toHaveBeenCalledWith("ernie", "labeling.nii.gz");
  } finally {
    cleanup();
  }
});

// @vitest-environment jsdom
/**
 * A background refetch of the atlas list must not unmount the atlas control (2026-10-09).
 *
 * A finished job invalidates `["atlases"]` (`app/jobs/invalidation.ts`). The pickers used to render
 * a Skeleton whenever the query was *fetching*, so the refetch replaced an open atlas dropdown with
 * a placeholder: the dropdown vanished under the user's pointer, and the Escape meant for it closed
 * the whole row editor instead (the roi-mni-atlas-kind e2e flake). Only the first load may show the
 * placeholder. The atlas list here is authored; the API module is the boundary that is mocked.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";

const getAtlases = vi.hoisted(() => vi.fn());
vi.mock("../../src/renderer/pages/_shared/roi/api", () => ({
  getAtlases,
  getAtlasRegions: vi.fn(async () => []),
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

for (const mode of ["cortical", "subcortical"] as const) {
  it(`${mode}: the atlas control stays mounted while the atlas list refetches`, async () => {
    getAtlases.mockReset();
    getAtlases.mockResolvedValueOnce([{ id: "a.annot", name: "Atlas A", kind: mode === "cortical" ? "cortical" : "subcortical" }]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    try {
      await act(async () => root.render(
        <QueryClientProvider client={client}>
          <RoiPicker value={emptyRoi(mode, "subject")} onChange={() => {}} modes={[mode]} subject="ernie" />
        </QueryClientProvider>,
      ));
      await settle();
      const trigger = container.querySelector(".combobox-trigger");
      expect(trigger).not.toBeNull();
      // A refetch that has not answered yet: the control the user may have open must be the same node.
      getAtlases.mockReturnValueOnce(new Promise(() => {}));
      await act(async () => { void client.invalidateQueries({ queryKey: ["atlases"] }); });
      await settle();
      expect(getAtlases).toHaveBeenCalledTimes(2);
      expect(container.querySelector(".combobox-trigger")).toBe(trigger);
      expect(container.querySelector(".skeleton")).toBeNull();
    } finally {
      act(() => root.unmount());
      container.remove();
      client.clear();
    }
  });
}

it("with no subject the atlas control is shown disabled, not a placeholder that never resolves", async () => {
  getAtlases.mockReset();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(
      <QueryClientProvider client={client}>
        <RoiPicker value={emptyRoi("cortical", "subject")} onChange={() => {}} modes={["cortical"]} subject={undefined} />
      </QueryClientProvider>,
    ));
    await settle();
    expect(getAtlases).not.toHaveBeenCalled();
    expect((container.querySelector(".combobox-trigger") as HTMLButtonElement | null)?.disabled).toBe(true);
    expect(container.querySelector(".skeleton")).toBeNull();
  } finally {
    act(() => root.unmount());
    container.remove();
    client.clear();
  }
});

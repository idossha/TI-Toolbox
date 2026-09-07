// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PageIdContext, clearPageSession } from "../../src/renderer/app/pageSession";
import { FreehandEditor } from "../../src/renderer/pages/simulator/FreehandEditor";
import { FreehandDraftProvider } from "../../src/renderer/pages/simulator/freehandDraft";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("../../src/renderer/pages/simulator/api", () => ({
  getFreehand: vi.fn(async () => []),
  putFreehand: vi.fn(async () => undefined),
}));

describe("Free-hand source draft", () => {
  let container: HTMLDivElement;
  let root: Root;
  let queryClient: QueryClient;

  beforeEach(() => {
    clearPageSession();
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    queryClient.setQueryData(["freehand", "ernie"], []);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    queryClient.clear();
    container.remove();
  });

  function render(show = true) {
    act(() => root.render(
      <QueryClientProvider client={queryClient}>
        <PageIdContext.Provider value="simulator">
          {/* The provider is at the SimulatorPage root and unmounts with it, so it goes inside the
              toggle: this is the page leaving and coming back, not a child re-rendering. */}
          {show && (
            <FreehandDraftProvider>
              <FreehandEditor subjects={["ernie"]} onClose={() => {}} />
            </FreehandDraftProvider>
          )}
        </PageIdContext.Provider>
      </QueryClientProvider>,
    ));
  }

  const input = (selector: string) => container.querySelector<HTMLInputElement>(selector)!;
  function fill(selector: string, value: string) {
    const target = input(selector);
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(target, value);
      target.dispatchEvent(new Event("input", { bubbles: true }));
      target.dispatchEvent(new Event("change", { bubbles: true }));
      target.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
  }

  it("restores name, coordinates, labels and invalid row count after a source-tab unmount", () => {
    render();
    fill("#sim-freehand-name", "unfinished_placement");
    fill('[aria-label="Position 1 label"]', "custom-A");
    fill('[aria-label="Position 1 X"]', "12.5");
    fill('[aria-label="Position 1 Y"]', "-23.5");
    // "Add electrode pair" adds TWO rows: an odd position count is never a valid montage
    // (`isValidPositionCount`), so six is still invalid and the error line still shows.
    const add = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.startsWith("Add electrode"))!;
    act(() => add.click());
    expect(container.querySelectorAll("tbody tr")).toHaveLength(6);
    expect(container.textContent).toContain("Use 4 positions");

    render(false);
    render();
    expect(input("#sim-freehand-name").value).toBe("unfinished_placement");
    expect(input('[aria-label="Position 1 label"]').value).toBe("custom-A");
    expect(input('[aria-label="Position 1 X"]').value).toBe("12.5");
    expect(input('[aria-label="Position 1 Y"]').value).toBe("-23.5");
    expect(container.querySelectorAll("tbody tr")).toHaveLength(6);
    expect(container.textContent).toContain("Use 4 positions");
  });

  it("starts clean after the project session is cleared", () => {
    render();
    fill("#sim-freehand-name", "previous_project");
    fill('[aria-label="Position 1 X"]', "41");
    render(false);
    clearPageSession();
    render();
    expect(input("#sim-freehand-name").value).toBe("");
    expect(input('[aria-label="Position 1 X"]').value).toBe("0");
    expect(container.querySelectorAll("tbody tr")).toHaveLength(4);
  });
});

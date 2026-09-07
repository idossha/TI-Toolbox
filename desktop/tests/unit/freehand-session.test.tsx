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

  it("carries the selection on a radio target, not on a row background", () => {
    // Maintainer, 2026-09-06, with a screenshot of the old accent band: *"we have this weird
    // shading … maybe have a switch to switch between the electrodes … this broken shading is
    // awful."* The swatch IS the switch: one checked radio, no style on the <tr> at all.
    render();
    const targets = () => Array.from(container.querySelectorAll<HTMLButtonElement>('[data-testid^="freehand-target-"]'));
    expect(targets()).toHaveLength(4);
    expect(targets().every((t) => t.getAttribute("role") === "radio")).toBe(true);
    expect(targets().filter((t) => t.getAttribute("aria-checked") === "true")).toHaveLength(0);

    act(() => targets()[1]!.click());
    expect(targets().map((t) => t.getAttribute("aria-checked"))).toEqual(["false", "true", "false", "false"]);
    // The row carries no inline background of its own — the cells paint themselves, so a wash on
    // the row could only ever show in the gaps between the inputs.
    const row = container.querySelector<HTMLTableRowElement>('[data-testid="freehand-row-1"]')!;
    expect(row.style.background).toBe("");
    expect(row.getAttribute("aria-selected")).toBe("true");

    // ArrowDown moves the target to the next electrode; clicking the checked one clears it.
    act(() => {
      targets()[1]!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    });
    expect(targets().map((t) => t.getAttribute("aria-checked"))).toEqual(["false", "false", "true", "false"]);
    act(() => targets()[2]!.click());
    expect(targets().filter((t) => t.getAttribute("aria-checked") === "true")).toHaveLength(0);
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

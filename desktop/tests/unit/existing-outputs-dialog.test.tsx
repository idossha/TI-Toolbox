// @vitest-environment jsdom
/** Replace and rerun is the one control for replacing outputs; every opening still requires an explicit click. */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExistingOutputsDialog } from "../../src/renderer/pages/_shared/run/ExistingOutputsDialog";

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
const decide = vi.fn();

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  decide.mockReset();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  client.clear();
});

function render(open = true, options: Partial<React.ComponentProps<typeof ExistingOutputsDialog>> = {}) {
  act(() => root.render(<QueryClientProvider client={client}><ExistingOutputsDialog open={open} onOpenChange={() => {}} existing={1} total={2} onDecide={decide} {...options} /></QueryClientProvider>));
}
function button(decision: string): HTMLButtonElement {
  return document.querySelector(`[data-testid="existing-outputs-${decision}"]`) as HTMLButtonElement;
}

describe("existing output decision", () => {
  it("requires confirmation on every opening", () => {
    render();
    expect(button("replace").disabled).toBe(false);
    expect(decide).not.toHaveBeenCalled();
    act(() => button("replace").click());
    expect(decide).toHaveBeenCalledExactlyOnceWith("replace");
    render(false);
    render();
    expect(decide).toHaveBeenCalledTimes(1);
    act(() => button("replace").click());
    expect(decide).toHaveBeenCalledTimes(2);
  });

  it("also offers Skip and Cancel", () => {
    render();
    act(() => button("skip").click());
    expect(decide).toHaveBeenCalledWith("skip");
    expect(button("cancel").disabled).toBe(false);
  });
});

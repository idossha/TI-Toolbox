// @vitest-environment jsdom
/** Project settings gate destructive decisions; every opening still requires an explicit click. */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExistingOutputsDialog } from "../../src/renderer/pages/_shared/run/ExistingOutputsDialog";
import { getSettings } from "../../src/renderer/pages/settings/api";

vi.mock("../../src/renderer/pages/settings/api", () => ({ getSettings: vi.fn() }));

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
  vi.mocked(getSettings).mockImplementation(() => new Promise(() => {}));
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

describe("existing output permission", () => {
  it.each([undefined, false])("keeps Replace disabled when project permission is %s", (permission) => {
    if (permission !== undefined) client.setQueryData(["settings"], { allow_unsafe_overrides: permission });
    render();
    expect(button("replace").disabled).toBe(true);
    act(() => button("replace").click());
    expect(decide).not.toHaveBeenCalled();
    expect(button("cancel").disabled).toBe(false);
    act(() => button("skip").click());
    expect(decide).toHaveBeenCalledWith("skip");
  });

  it("requires confirmation on every opening even when project permission is enabled", () => {
    client.setQueryData(["settings"], { allow_unsafe_overrides: true });
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

  it("disables Replace when saved project settings revoke permission while open", async () => {
    client.setQueryData(["settings"], { allow_unsafe_overrides: true });
    render();
    await act(async () => {
      client.setQueryData(["settings"], { allow_unsafe_overrides: false });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(button("replace").disabled).toBe(true);
  });
});

// @vitest-environment jsdom
/**
 * The context bar replaced the v1 top bar (plan §1). v2 pinned the project crumb and the subject
 * switcher here; program U11 removed both — "a second place to pick a subject that no page
 * needed" — leaving the search field (widened into the space the crumb used to occupy), the
 * connection indicator and the running-jobs count. What v2 also pinned and still holds: the theme
 * control stays out (a palette action, not ambient state) and so does the version string (a
 * status-bar cell).
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// jsdom ships no `matchMedia`, and uPlot (reached through the `ui` barrel) calls it at module
// scope. A stub that reports "no media matches" is the honest answer for a headless DOM.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

vi.mock("../../src/renderer/api/client", () => ({
  getVersion: vi.fn(async () => ({ tit_version: "3.0.0-test", server_api: "v1", schema_hash: "" })),
  getProject: vi.fn(async () => ({ name: "example", container_path: "/mnt/example", host_path: null })),
  getSubjects: vi.fn(async () => [{ id: "ernie", has_raw: true, has_freesurfer: true, has_m2m: true }]),
  api: { GET: vi.fn() },
  unwrap: vi.fn((r: unknown) => r),
  logout: vi.fn(async () => {}),
}));

vi.mock("../../src/renderer/ws/useSystemStream", () => ({
  useSystemStream: () => ({ status: "open", samples: [], attempt: 0 }),
}));

vi.mock("../../src/renderer/env", () => ({ isElectron: false }));

const CONNECTED = { status: "connected" as const, degraded: false, label: "connected", reason: null };

describe("AppContextBar", () => {
  let container: HTMLDivElement;
  let root: Root;
  let AppContextBar: typeof import("../../src/renderer/app/AppContextBar").AppContextBar;

  // Transform shared UI imports during setup, outside each behavior test's timeout.
  beforeAll(async () => {
    ({ AppContextBar } = await import("../../src/renderer/app/AppContextBar"));
  }, 30_000);

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function render(props: Partial<{ runningJobs: number; onToggleJobsRail: () => void; onOpenPalette: () => void }> = {}) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <AppContextBar
            connection={CONNECTED}
            runningJobs={props.runningJobs ?? 0}
            onToggleJobsRail={props.onToggleJobsRail ?? (() => {})}
            onOpenPalette={props.onOpenPalette ?? (() => {})}
          />
        </QueryClientProvider>,
      );
    });
  }

  it("carries no project crumb and no subject switcher (U11)", async () => {
    await render();
    expect(container.querySelector("[data-testid=project-crumb]")).toBeNull();
    expect(container.querySelector("[data-testid=subject-switcher]")).toBeNull();
    // Nothing in the bar names the project or a subject any more — the strip's whole text is the
    // search field's own copy, the connection label and the jobs count.
    const text = (container.textContent ?? "").trim();
    expect(text).not.toContain("example");
    expect(text).not.toContain("No subject");
  });

  it("opens the palette from a wide search field carrying the ⌘K hint", async () => {
    const onOpenPalette = vi.fn();
    await render({ onOpenPalette });
    const trigger = container.querySelector<HTMLButtonElement>("[data-testid=palette-trigger]")!;
    expect(trigger).not.toBeNull();
    expect(trigger.className).toContain("palette-trigger-wide");
    act(() => trigger.click());
    expect(onOpenPalette).toHaveBeenCalledOnce();
  });

  it("keeps the jobs count's v1 semantics and toggles the panel", async () => {
    const onToggleJobsRail = vi.fn();
    await render({ runningJobs: 3, onToggleJobsRail });
    const chip = container.querySelector<HTMLButtonElement>("[data-testid=jobs-count]")!;
    expect(chip.textContent).toBe("3 running");
    act(() => chip.click());
    expect(onToggleJobsRail).toHaveBeenCalledOnce();
  });

  it("does not carry the theme control or the version string any more", async () => {
    await render();
    const text = container.textContent ?? "";
    expect(text).not.toContain("Theme");
    expect(text).not.toContain("api ");
    expect(container.querySelector("[data-testid=server-version]")).toBeNull();
  });
});

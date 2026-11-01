// @vitest-environment jsdom
/**
 * Saving an extension toggle in Settings ▸ Extensions applies live, with no window reload.
 *
 * The failure it pins: Save used to call `window.location.reload()` whenever `settings.panels`
 * changed. A reload fires the Notebooks page's `beforeunload` handler, which shuts down every
 * kernel (`notebooks/session.ts::shutdownAllKernelsOnUnload`), so toggling an extension threw away
 * every loaded variable and every retained page's in-memory state. The reload had been stale since
 * the rail went live: `app/registry.ts::useEnabledPages` reads the same `["settings"]` query cache
 * entry that Save writes.
 *
 * Expected values: the panel ids come from the saved `settings.panels` the stubbed `putSettings`
 * echoes back (`panel-<id>` is the page id convention `registry.ts::isPanelPageEnabled` documents);
 * the rail is read through the real registry over the real discovered pages, not a mock. 2026-10-22.
 */
import { MemoryRouter } from "react-router-dom";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearPageSession } from "../../src/renderer/app/pageSession";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
// jsdom ships no `matchMedia`; the registry imports every page module, one of which calls it at module scope.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({ matches: false, media: query, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false }),
});

const server = vi.hoisted(() => ({ settings: { telemetry: { consented: true, enabled: false }, panels: ["source"] as string[], theme: "system" as const } }));

vi.mock("../../src/renderer/pages/settings/api", () => ({
  getSurferSettings: vi.fn(async () => ({ available_threads: 12, default_threads: 9, fastsurfer_threads: null, freesurfer_threads: null, effective_fastsurfer_threads: 9, effective_freesurfer_threads: 9, freesurfer_license: { configured: false, source: null, email: null } })),
  putSurferSettings: vi.fn(),
  getCpuLimit: vi.fn(async () => ({ percent: 70, cores: 8, available_cores: 12, default_percent: 70 })),
  putCpuLimit: vi.fn(),
  getSettings: vi.fn(async () => structuredClone(server.settings)),
  // The server's answer is what it stored: the next GET returns it too.
  putSettings: vi.fn(async (next: typeof server.settings) => {
    server.settings = structuredClone(next);
    return structuredClone(next);
  }),
  getProject: vi.fn(async () => ({ name: "example", container_path: "/mnt/example", host_path: null })),
  getCapabilities: vi.fn(async () => ({ docker_socket: false, bpy: true, jupyter: false, fastsurfer: false })),
  getVersion: vi.fn(async () => ({ tit_version: "3.0.0-test", server_api: "v0", schema_hash: "", python: "3.11", simnibs: null })),
}));
vi.mock("../../src/renderer/env", () => ({ isElectron: false, isProjectHome: false }));

const reload = vi.fn();

/** An in-memory `localStorage` (Node's own global shadows jsdom's and has no working store here). */
function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() {
      return items.size;
    },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (i) => [...items.keys()][i] ?? null,
    removeItem: (key) => void items.delete(key),
    setItem: (key, value) => void items.set(key, String(value)),
  };
}

/** The rail's workflow rows, read exactly as `NavRail` reads them (`useNavSections`). */
async function railProbe(): Promise<() => React.ReactElement> {
  const { useNavSections } = await import("../../src/renderer/app/registry");
  return function RailProbe() {
    const ids = useNavSections().flatMap((section) => section.pages.map((page) => page.id));
    return <ul data-testid="rail">{ids.map((id) => <li key={id}>{id}</li>)}</ul>;
  };
}

function railIds(container: HTMLElement): string[] {
  return [...container.querySelectorAll('[data-testid="rail"] li')].map((li) => li.textContent ?? "");
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0));
  });
}

describe("Settings ▸ Extensions save", () => {
  let root: Root;
  let container: HTMLDivElement;
  let realLocation: Location;

  beforeEach(() => {
    server.settings = { telemetry: { consented: true, enabled: false }, panels: ["source"], theme: "system" };
    Object.defineProperty(window, "localStorage", { configurable: true, value: memoryStorage() });
    reload.mockClear();
    realLocation = window.location;
    // jsdom's own `reload` is a non-configurable "not implemented" stub; a plain object with the
    // same href lets the test see whether the page asked for one.
    Object.defineProperty(window, "location", { configurable: true, value: { ...realLocation, href: realLocation.href, reload } });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    Object.defineProperty(window, "location", { configurable: true, value: realLocation });
    clearPageSession();
    document.body.innerHTML = "";
    vi.useRealTimers();
  });

  it("turns a panel on in the rail without reloading the window", async () => {
    const { default: settingsPage } = await import("../../src/renderer/pages/settings/index");
    const SettingsComponent = settingsPage.Component;
    const RailProbe = await railProbe();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    act(() =>
      root.render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/settings#extensions"]}>
            <RailProbe />
            <SettingsComponent />
          </MemoryRouter>
        </QueryClientProvider>,
      ),
    );
    await settle();

    // Before: the server's one panel is in the rail, Nilearn visuals is not.
    expect(railIds(container)).toContain("panel-source");
    expect(railIds(container)).not.toContain("panel-nilearn-visuals");

    const nilearn = [...container.querySelectorAll("label")].find((label) => label.textContent?.includes("Nilearn visuals"));
    const checkbox = nilearn?.querySelector<HTMLButtonElement>('[role="checkbox"]');
    expect(checkbox, "the Nilearn visuals toggle is on the Extensions tab").toBeTruthy();
    act(() => checkbox!.click());
    const save = [...container.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Save changes");
    expect(save?.disabled).toBe(false);

    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    act(() => save!.click());
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const saved = server.settings.panels;
    expect([...saved].sort()).toEqual(["nilearn-visuals", "source"]);
    // Every saved panel is a rail row now, in this same window: no reload was asked for.
    for (const id of saved) expect(railIds(container)).toContain(`panel-${id}`);
    expect(reload).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toMatch(/reload/i);
    // Saved state reads as clean: nothing left to save.
    expect([...container.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Save changes")?.disabled).toBe(true);

    // And off again: the row leaves the rail, still without a reload.
    act(() => checkbox!.click());
    act(() => [...container.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Save changes")!.click());
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(server.settings.panels).toEqual(["source"]);
    expect(railIds(container)).not.toContain("panel-nilearn-visuals");
    expect(railIds(container)).toContain("panel-source");
    expect(reload).not.toHaveBeenCalled();
    queryClient.clear();
  });

  it("has no page Save on Settings ▸ Simulator, whose changes apply at once (2026-10-30)", async () => {
    const { default: settingsPage } = await import("../../src/renderer/pages/settings/index");
    const SettingsComponent = settingsPage.Component;
    const saveButton = () => [...container.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Save changes");
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    for (const [hash, shown] of [["#simulator", false], ["#extensions", true]] as const) {
      act(() =>
        root.render(
          <QueryClientProvider client={queryClient}>
            <MemoryRouter key={hash} initialEntries={[`/settings${hash}`]}>
              <SettingsComponent />
            </MemoryRouter>
          </QueryClientProvider>,
        ),
      );
      await settle();
      expect(Boolean(saveButton()), hash).toBe(shown);
    }
    queryClient.clear();
  });

  it("never offers a reload when the server's panel list differs from this machine's mirror", async () => {
    // The mirror says a previous session had caps on; the server now says source only.
    window.localStorage.setItem("tit-enabled-panels", JSON.stringify(["caps"]));
    window.localStorage.setItem("tit-enabled-panels-synced", "1");
    const { default: settingsPage } = await import("../../src/renderer/pages/settings/index");
    const SettingsComponent = settingsPage.Component;
    const RailProbe = await railProbe();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    act(() =>
      root.render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/settings#extensions"]}>
            <RailProbe />
            <SettingsComponent />
          </MemoryRouter>
        </QueryClientProvider>,
      ),
    );
    await settle();
    // The rail follows the server, and the page has nothing to ask a person to reload for.
    expect(railIds(container)).toContain("panel-source");
    expect(railIds(container)).not.toContain("panel-caps");
    expect(container.textContent).not.toMatch(/reload/i);
    expect(JSON.parse(window.localStorage.getItem("tit-enabled-panels") ?? "null")).toEqual(["source"]);
    queryClient.clear();
  });
});

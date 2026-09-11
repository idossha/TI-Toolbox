// @vitest-environment jsdom
/**
 * Regression test for ra_12 finding surfaced by the harness lane: when another observer (e.g.
 * `app/registry.ts`'s `useEnabledPages()`) has already warmed the `["settings"]` React Query
 * cache *before* the Settings page mounts, `settingsQuery.data` is populated on the very first
 * render. The old render-time sync (`useState(settingsQuery.data)` as the "previous value"
 * baseline) treated that as "nothing changed" and never seeded `form`, so the Telemetry / Feature
 * panels / Advanced cards silently never rendered their controls (no error, no skeleton — just
 * gone). See settings.spec.ts:55 for the E2E symptom.
 */
import { MemoryRouter } from "react-router-dom";
import React, { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clearPageSession } from "../../src/renderer/app/pageSession";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SETTINGS_FIXTURE = {
  telemetry: { consented: true, enabled: false },
  panels: ["source", "quick-notes", "subject-info"],
  image_tag: null,
  allow_unsafe_overrides: false,
  theme: "system" as const,
};

vi.mock("../../src/renderer/pages/settings/api", () => ({
  getSurferSettings: vi.fn(async () => ({ available_threads: 12, default_threads: 9, fastsurfer_threads: null, freesurfer_threads: null, effective_fastsurfer_threads: 9, effective_freesurfer_threads: 9 })),
  putSurferSettings: vi.fn(),
  getSettings: vi.fn(async () => SETTINGS_FIXTURE),
  putSettings: vi.fn(async (s: unknown) => s),
  getProject: vi.fn(async () => ({ name: "example", container_path: "/mnt/example", host_path: null })),
  // Matches components["schemas"]["Capabilities"] (api/schema.d.ts) and tests/fixtures/capabilities.json
  // — no x11_display/gmsh/freeview: those capability flags are gone server-side (D3), and this
  // fixture drifting from the real shape is exactly what let a stale UI (pages/settings) go
  // unnoticed (see index.tsx's "About the server" card, fixed alongside this).
  getCapabilities: vi.fn(async () => ({
    docker_socket: false,
    bpy: true,
    jupyter: false,
    tetravox_embed: {
      available: true,
      version: "0.3.4",
      protocol: 1,
      source: "baked" as const,
      features: ["cursor", "layers", "meshes", "probe", "screenshot", "volumes"],
      compatible: true,
      supported: { min: 1, max: 2 },
    },
    fastsurfer: false,
  })),
  getVersion: vi.fn(async () => ({ tit_version: "3.0.0-test", server_api: "v0", schema_hash: "", python: "3.11", simnibs: null })),
  // The Viewer engine card (E1-E4) reads the same module. Mocking the whole module means every
  // export the page uses has to exist here, or the page throws "getTetravox is not a function"
  // and this test fails on something that has nothing to do with what it is testing.
  getTetravox: vi.fn(async () => TETRAVOX_FIXTURE),
  getTetravoxUpdates: vi.fn(async () => ({ available: false, message: "Could not reach the release index", index_url: "https://example/releases.json", releases: [], auto_update: true, checked_at: null, from_cache: true })),
  installTetravox: vi.fn(async () => TETRAVOX_FIXTURE),
  activateTetravox: vi.fn(async () => TETRAVOX_FIXTURE),
  removeTetravox: vi.fn(async () => TETRAVOX_FIXTURE),
  setTetravoxPolicy: vi.fn(async () => TETRAVOX_FIXTURE),
}));

vi.mock("../../src/renderer/env", () => ({ isElectron: false }));

/** Matches components["schemas"]["TetravoxState"] — the baked floor, nothing installed. */
const TETRAVOX_BAKED = {
  version: "0.3.4",
  protocol: 1,
  source: "baked" as const,
  path: "/opt/tetravox/embed",
  name: "@tetravox/embed",
  sha: "c56c3c8",
  features: ["cursor", "layers", "meshes", "probe", "screenshot", "volumes"],
  compatible: true,
  active: true,
};
const TETRAVOX_FIXTURE = {
  active: TETRAVOX_BAKED,
  reason: "the version baked into the image",
  installed: [],
  baked: TETRAVOX_BAKED,
  supported: { min: 1, max: 2 },
  install_root: "/root/.config/ti-toolbox/tetravox/embed",
  index_url: "https://example/releases.json",
  auto_update: true,
};

function mount(ui: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { root, container };
}

/** Mirrors `app/registry.ts::useEnabledPages` — an unrelated observer of the same query key. */
function CacheWarmer() {
  useQuery({ queryKey: ["settings"], queryFn: () => import("../../src/renderer/pages/settings/api").then((m) => m.getSettings()) });
  return null;
}

describe("SettingsPage with a pre-warmed [\"settings\"] query cache", () => {
  afterEach(() => {
    clearPageSession();
    document.body.innerHTML = "";
  });

  it("still renders the Telemetry switch once the settings query resolves", async () => {
    const { default: SettingsPageDef } = await import("../../src/renderer/pages/settings/index");
    const Component = SettingsPageDef.Component;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    // Warm the cache exactly like the nav rail does, resolve it, THEN mount the Settings page —
    // so its own `useQuery(["settings"])` observer sees non-undefined `data` on its very first render.
    const { root: warmerRoot } = mount(
      <QueryClientProvider client={queryClient}>
        <CacheWarmer />
      </QueryClientProvider>,
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(queryClient.getQueryData(["settings"])).toEqual(SETTINGS_FIXTURE);
    act(() => warmerRoot.unmount());

    const { container, root } = mount(
      <StrictMode>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter><Component /></MemoryRouter>
        </QueryClientProvider>
      </StrictMode>,
    );

    // The query resolves synchronously from cache, so no further await should even be necessary,
    // but give microtasks a turn in case of a stray refetch.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    const telemetrySwitch = container.querySelector('[aria-label="Send anonymous usage data"]');
    expect(telemetrySwitch, "Telemetry Switch never rendered — settings form was not seeded from the warm cache").not.toBeNull();

    const bodyText = container.textContent ?? "";
    expect(bodyText).toContain("Send anonymous usage data");
    expect(bodyText).toContain("Feature panels");
    expect(bodyText).toContain("Source");
    const replace = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "Replace and rerun");
    expect(replace?.disabled).toBe(true);

    const tabs = [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
    expect(tabs.map((button) => button.textContent)).toEqual(["Project", "Pre-processing", "Extensions", "Viewer", "Server"]);
    expect(container.querySelectorAll('[role="tabpanel"][data-state="active"]')).toHaveLength(1);
    const select = (label: string) => act(() => {
      tabs.find((button) => button.textContent === label)!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 }));
    });
    act(() => (telemetrySwitch as HTMLButtonElement).click());
    expect(telemetrySwitch?.getAttribute("aria-checked")).toBe("true");
    select("Extensions");
    expect(container.querySelector('[role="tabpanel"][data-state="active"]')?.textContent).toContain("Feature panels");
    expect(container.querySelector('[role="tabpanel"][data-state="active"]')?.textContent).not.toContain("Send anonymous usage data");
    select("Project");
    expect(container.querySelector('[aria-label="Send anonymous usage data"]')?.getAttribute("aria-checked")).toBe("true");
    act(() => root.unmount());
    queryClient.clear();
  });
  it("opens the pre-processing tab through the legacy system link", async () => {
    const { default: page } = await import("../../src/renderer/pages/settings/index");
    const Component = page.Component;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { root, container } = mount(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/settings#system"]}><Component /></MemoryRouter>
      </QueryClientProvider>,
    );
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(container.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toBe("Pre-processing");
    expect(container.querySelector('[role="tabpanel"][data-state="active"]')?.textContent).toContain("FastSurfer");
    act(() => root.unmount());
    queryClient.clear();
  });

});

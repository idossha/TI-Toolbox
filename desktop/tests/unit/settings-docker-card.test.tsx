// @vitest-environment jsdom
/**
 * Settings ▸ Server ▸ Docker tells the truth about quitting: the desktop app stops the container it
 * started when it quits (`main/stack.ts`: "Closing Electron stops its selected stack";
 * `main/index.ts` `before-quit` and `window-all-closed` run the quit plan). The card used to say
 * "Quitting leaves this container running so the next launch reconnects instantly". Its Stop
 * button calls `window.tit.stack.stop()`, which now closes the project behind the running-jobs
 * question; a refused or cancelled stop is reported, not swallowed.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/settings-docker-card.test.tsx`.
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

const toast = vi.hoisted(() => ({ error: vi.fn() }));

vi.mock("../../src/renderer/pages/settings/api", () => ({
  getSurferSettings: vi.fn(async () => ({})),
  putSurferSettings: vi.fn(),
  getCpuLimit: vi.fn(async () => ({ percent: 70, cores: 8, available_cores: 12, default_percent: 70 })),
  putCpuLimit: vi.fn(),
  putFreeSurferLicense: vi.fn(),
  deleteFreeSurferLicense: vi.fn(),
  getSettings: vi.fn(async () => ({ telemetry: { consented: true, enabled: false }, panels: [], image_tag: null, theme: "system" })),
  putSettings: vi.fn(async (s: unknown) => s),
  getProject: vi.fn(async () => ({ name: "example", container_path: "/mnt/example", host_path: "/Users/x/example" })),
  getCapabilities: vi.fn(async () => ({ docker_socket: true, bpy: true, jupyter: false, fastsurfer: false })),
  getVersion: vi.fn(async () => ({ tit_version: "3.1.1", server_api: "v1", schema_hash: "", python: "3.11", simnibs: null })),
}));
vi.mock("../../src/renderer/env", () => ({ isElectron: true, isProjectHome: false }));
// Cards with their own bridges and tests; this file is about the Docker card.
vi.mock("../../src/renderer/pages/settings/TetravoxCard", () => ({ TetravoxCard: () => null }));
vi.mock("../../src/renderer/pages/settings/SurferSettingsCard", () => ({ SurferSettingsCard: () => null }));
vi.mock("../../src/renderer/pages/settings/NotificationsCard", () => ({ NotificationsCard: () => null }));
vi.mock("../../src/renderer/app/appUpdate", () => ({ AppUpdateCard: () => null }));
vi.mock("../../src/renderer/ui/Toast", async (importOriginal) => ({ ...(await importOriginal<object>()), notify: { error: toast.error, success: vi.fn(), info: vi.fn(), blocked: vi.fn() } }));

const stop = vi.fn();
let root: Root;
let container: HTMLDivElement;

async function renderSettings(): Promise<HTMLElement> {
  const { default: page } = await import("../../src/renderer/pages/settings/index");
  const Component = page.Component;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  act(() => root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/settings#server"]}><Component /></MemoryRouter></QueryClientProvider>));
  // The card renders once `stack.status()` reports a running container.
  await vi.waitFor(() => {
    if (!container.querySelector('[data-testid="stop-stack"]')) throw new Error("Docker card not rendered");
  });
  return container;
}

beforeEach(() => {
  stop.mockReset();
  toast.error.mockReset();
  (window as unknown as { tit: unknown }).tit = {
    stack: {
      status: async () => ({ running: true, containerName: "ti-toolbox-1a2b3c4d-tit-1", image: "idossha/ti-toolbox:v3.1.1", health: "healthy" }),
      stop,
    },
  };
});

afterEach(() => {
  act(() => root.unmount());
  clearPageSession();
  document.body.innerHTML = "";
  delete (window as unknown as { tit?: unknown }).tit;
});

describe("Settings ▸ Docker", () => {
  it("says quitting stops the container, never that it leaves it running", async () => {
    const page = await renderSettings();
    // Every Settings tab is mounted; the other cards that could mention quitting are mocked out.
    const text = page.textContent ?? "";
    expect(text).toContain("ti-toolbox-1a2b3c4d-tit-1");
    expect(text).not.toMatch(/quit[^.]*\bleaves?\b[^.]*running/i);
    expect(text).not.toMatch(/reconnects instantly/i);
    expect(text).toMatch(/quitting[^.]*\bstops\b[^.]*\bcontainer\b/i);
    // Stopping here asks about running jobs first, as closing the project does.
    expect(text).toMatch(/running or queued[^.]*asked first/i);
  });

  it("reports a stop that was cancelled or refused, and the button works again", async () => {
    stop.mockResolvedValueOnce({ ok: false, error: "Project switch cancelled or the container could not be stopped." });
    const page = await renderSettings();
    const button = page.querySelector<HTMLButtonElement>('[data-testid="stop-stack"]')!;
    await act(async () => {
      button.click();
    });
    expect(stop).toHaveBeenCalledTimes(1);
    expect(toast.error).toHaveBeenCalledExactlyOnceWith("Project switch cancelled or the container could not be stopped.");
    expect(button.disabled).toBe(false);
  });
});

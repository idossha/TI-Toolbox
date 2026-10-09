// @vitest-environment jsdom
// The update notice's three faces (src/renderer/app/appUpdate.tsx) driven by a fake bridge answer:
// the popup appears only for the one `prompt` answer and stays closed after Later; the Settings card
// names each state and Check again forces a new lookup; the nav label always shows the version.
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppUpdateCard, AppUpdatePrompt, AppVersionLabel } from "../../src/renderer/app/appUpdate";
import type { TitAppUpdate, TitBridge } from "../../src/shared/tit-bridge";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
const checkAppUpdate = vi.fn<(force?: boolean) => Promise<TitAppUpdate>>();
const openExternal = vi.fn();

const URL = "https://github.com/idossha/TI-Toolbox/releases/tag/v3.1.0";
const AVAILABLE: TitAppUpdate = { current: "3.0.2", latest: "3.1.0", available: true, url: URL, error: null, prompt: true };
const CURRENT: TitAppUpdate = { current: "3.1.0", latest: "3.1.0", available: false, url: URL, error: null, prompt: false };
const OFFLINE: TitAppUpdate = { current: "3.0.2", latest: null, available: false, url: null, error: "Couldn't reach GitHub to check for updates (offline?).", prompt: false };

beforeEach(() => {
  vi.resetAllMocks();
  window.tit = { checkAppUpdate, openExternal, appVersion: vi.fn() } as unknown as TitBridge;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => {
  act(() => root.unmount());
  client.clear();
  container.remove();
  delete window.tit;
});
async function render(node: React.ReactNode) {
  act(() => root.render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>));
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
}
const dialog = () => document.querySelector('[role="dialog"]');
const button = (text: string) => [...document.querySelectorAll("button")].find((item) => item.textContent?.trim() === text);

it("announces a newer release once, with the versions, and Later closes it", async () => {
  checkAppUpdate.mockResolvedValue(AVAILABLE);
  await render(<AppUpdatePrompt />);
  expect(dialog()?.textContent).toContain("TI-Toolbox 3.1.0 is available (you have 3.0.2).");
  act(() => button("Later")!.click());
  expect(dialog()).toBeNull();
  expect(openExternal).not.toHaveBeenCalled();
});

it("Download opens the release page in the browser and closes the popup", async () => {
  checkAppUpdate.mockResolvedValue(AVAILABLE);
  await render(<AppUpdatePrompt />);
  act(() => button("Download")!.click());
  expect(openExternal).toHaveBeenCalledWith(URL);
  expect(dialog()).toBeNull();
});

it("shows no popup when up to date, offline, or already announced this session", async () => {
  for (const answer of [CURRENT, OFFLINE, { ...AVAILABLE, prompt: false }]) {
    checkAppUpdate.mockResolvedValue(answer);
    client.clear();
    await render(<AppUpdatePrompt />);
    expect(dialog()).toBeNull();
  }
});

it("the Settings card names each state", async () => {
  const card = () => container.querySelector('[data-testid="app-update-card"]')!;
  checkAppUpdate.mockResolvedValue(CURRENT);
  await render(<AppUpdateCard />);
  expect(card().getAttribute("data-status")).toBe("current");
  expect(card().textContent).toContain("Up to date");
  expect(button("Download 3.1.0")).toBeUndefined();

  checkAppUpdate.mockResolvedValue(OFFLINE);
  client.clear();
  await render(<AppUpdateCard />);
  expect(card().getAttribute("data-status")).toBe("error");
  expect(card().textContent).toContain("Couldn't check");
  expect(card().textContent).toContain("(offline?)");

  checkAppUpdate.mockResolvedValue(AVAILABLE);
  client.clear();
  await render(<AppUpdateCard />);
  expect(card().getAttribute("data-status")).toBe("available");
  expect(card().textContent).toContain("Update available");
  act(() => button("Download 3.1.0")!.click());
  expect(openExternal).toHaveBeenCalledWith(URL);
});

it("Check again forces a new lookup and shows its answer", async () => {
  checkAppUpdate.mockResolvedValueOnce(OFFLINE).mockResolvedValueOnce(AVAILABLE);
  await render(<AppUpdateCard />);
  expect(checkAppUpdate).toHaveBeenLastCalledWith(false);
  await act(async () => { button("Check again")!.click(); await new Promise((resolve) => setTimeout(resolve, 20)); });
  expect(checkAppUpdate).toHaveBeenLastCalledWith(true);
  expect(container.querySelector('[data-testid="app-update-card"]')!.getAttribute("data-status")).toBe("available");
});

it("the nav label shows the version, and marks an available update", async () => {
  checkAppUpdate.mockResolvedValue(CURRENT);
  await render(<AppVersionLabel />);
  const label = () => container.querySelector('[data-testid="nav-app-version"]')!;
  expect(label().textContent).toBe("v3.1.0");
  expect(label().getAttribute("data-update")).toBeNull();

  checkAppUpdate.mockResolvedValue(AVAILABLE);
  client.clear();
  await render(<AppVersionLabel />);
  expect(label().textContent).toBe("v3.0.2");
  expect(label().getAttribute("data-update")).toBe("available");
  expect(label().getAttribute("aria-label")).toBe("TI-Toolbox 3.1.0 is available (you have 3.0.2)");
});

// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TetravoxCard } from "../../src/renderer/pages/settings/TetravoxCard";
import type { TitBridge, TitNativeTetravoxStatus } from "../../src/shared/tit-bridge";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
const nativeTetravoxStatus = vi.fn();
const installNativeTetravox = vi.fn();
const updateNativeTetravox = vi.fn();
const checkNativeTetravoxUpdate = vi.fn();
const locateNativeTetravox = vi.fn();
const clearNativeTetravoxPath = vi.fn();
const openNativeTetravox = vi.fn();
const onNativeTetravoxProgress = vi.fn(() => () => {});

function bridge(): TitBridge {
  return {
    nativeTetravoxStatus,
    installNativeTetravox,
    updateNativeTetravox,
    checkNativeTetravoxUpdate,
    locateNativeTetravox,
    clearNativeTetravoxPath,
    onNativeTetravoxProgress,
    openNativeTetravox,
  } as unknown as TitBridge;
}

beforeEach(() => {
  vi.resetAllMocks();
  onNativeTetravoxProgress.mockReturnValue(() => {});
  window.tit = bridge();
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
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}
async function render() {
  act(() => root.render(<QueryClientProvider client={client}><TetravoxCard /></QueryClientProvider>));
  await settle();
}
function button(text: string) {
  return [...document.querySelectorAll("button")].find((item) => item.textContent === text);
}

it("shows a browser-only row with no buttons when there is no desktop bridge", async () => {
  delete window.tit;
  await render();
  expect(container.textContent).toContain("Requires the TI-Toolbox desktop app");
  expect(container.querySelector("button")).toBeNull();
});

it("offers Install and a not-installed pill when nothing is present", async () => {
  const status: TitNativeTetravoxStatus = { supported: true, installed: false, installing: false, version: "", directory: "" };
  nativeTetravoxStatus.mockResolvedValue(status);
  await render();
  expect(container.textContent).toContain("Not installed");
  expect(button("Install TetraVox")).toBeDefined();
  expect(button("Launch TetraVox")).toBeUndefined();
});

it("shows the managed source, version and a Launch action when installed", async () => {
  const status: TitNativeTetravoxStatus = {
    source: "managed",
    supported: true,
    installed: true,
    installing: false,
    version: "0.5.1",
    directory: "/Users/x/Library/Application Support/TI-Toolbox/tetravox",
  };
  nativeTetravoxStatus.mockResolvedValue(status);
  await render();
  expect(container.textContent).toContain("Installed 0.5.1 · managed");
  expect(container.textContent).toContain("Installed for TI-Toolbox");
  expect(button("Launch TetraVox")).toBeDefined();
  expect(button("Check for updates")).toBeDefined();
});

it("shows the system source with its path in the pill", async () => {
  const status: TitNativeTetravoxStatus = {
    source: "system",
    supported: true,
    installed: true,
    installing: false,
    version: "system",
    directory: "/Applications/TetraVox.app",
  };
  nativeTetravoxStatus.mockResolvedValue(status);
  await render();
  expect(container.textContent).toContain("Installed system · system (/Applications/TetraVox.app)");
});

it("shows an Update action and pill when a newer release is known", async () => {
  const status: TitNativeTetravoxStatus = {
    source: "managed",
    supported: true,
    installed: true,
    installing: false,
    version: "0.5.1",
    directory: "/managed",
    updateAvailable: "0.5.2",
  };
  nativeTetravoxStatus.mockResolvedValue(status);
  updateNativeTetravox.mockResolvedValue({ ...status, version: "0.5.2", updateAvailable: undefined });
  await render();
  expect(container.textContent).toContain("Update available 0.5.2");
  const update = button("Update to 0.5.2")!;
  act(() => update.click());
  await settle();
  expect(updateNativeTetravox).toHaveBeenCalledOnce();
});

it("renders a download progress bar while installing", async () => {
  const status: TitNativeTetravoxStatus = { supported: true, installed: false, installing: true, version: "", directory: "" };
  nativeTetravoxStatus.mockResolvedValue(status);
  onNativeTetravoxProgress.mockImplementation((listener: (p: { phase: string; received: number; total: number }) => void) => {
    listener({ phase: "download", received: 42 * 1024 * 1024, total: 130 * 1024 * 1024 });
    return () => {};
  });
  await render();
  expect(container.textContent).toContain("Downloading 42 MB of 130 MB");
  expect(container.querySelector('[role="progressbar"]')).not.toBeNull();
});

it("clears a configured path via Use automatic choice", async () => {
  const status: TitNativeTetravoxStatus = {
    source: "configured",
    supported: true,
    installed: true,
    installing: false,
    version: "0.5.1",
    directory: "/x",
    configuredPath: "/Applications/Chosen.app",
  };
  nativeTetravoxStatus.mockResolvedValue(status);
  clearNativeTetravoxPath.mockResolvedValue({ ...status, source: "managed", configuredPath: undefined });
  await render();
  const link = [...document.querySelectorAll("a")].find((a) => a.textContent === "Use automatic choice")!;
  act(() => link.click());
  await settle();
  expect(clearNativeTetravoxPath).toHaveBeenCalledOnce();
});

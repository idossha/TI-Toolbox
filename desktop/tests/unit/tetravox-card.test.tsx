// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TetravoxCard } from "../../src/renderer/pages/settings/TetravoxCard";
import type { TitBridge, TitNativeTetravoxProgress, TitNativeTetravoxStatus } from "../../src/shared/tit-bridge";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
const nativeTetravoxStatus = vi.fn();
const installNativeTetravox = vi.fn();
const locateNativeTetravox = vi.fn();
const clearNativeTetravoxPath = vi.fn();
const openNativeTetravox = vi.fn();
const onNativeTetravoxProgress = vi.fn<(listener: (progress: TitNativeTetravoxProgress) => void) => () => void>(() => () => {});

function bridge(): TitBridge {
  return {
    nativeTetravoxStatus,
    installNativeTetravox,
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

it("offers setup retry when automatic installation has not completed", async () => {
  const status: TitNativeTetravoxStatus = { supported: true, installed: false, installing: false, version: "", directory: "" };
  nativeTetravoxStatus.mockResolvedValue(status);
  await render();
  expect(container.textContent).toContain("Not installed");
  expect(button("Retry setup")).toBeDefined();
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
  expect(button("Check for updates")).toBeUndefined();
  expect(container.textContent).toContain("Updates are managed in TetraVox.");
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

it("retries failed setup without offering TI-owned version updates", async () => {
  const status: TitNativeTetravoxStatus = { supported: true, installed: false, installing: false, version: "", directory: "", error: "Download failed" };
  nativeTetravoxStatus.mockResolvedValue(status);
  installNativeTetravox.mockImplementation(async () => {
    nativeTetravoxStatus.mockResolvedValue({ ...status, installed: true, source: "managed", version: "0.5.2", error: undefined });
  });
  await render();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("Download failed");
  act(() => button("Retry setup")!.click());
  await settle();
  await settle();
  expect(installNativeTetravox).toHaveBeenCalledOnce();
  expect(button("Launch TetraVox")).toBeDefined();
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect(button("Check for updates")).toBeUndefined();
});

it("refreshes an automatic installation that finishes outside this card", async () => {
  const status: TitNativeTetravoxStatus = { supported: true, installed: false, installing: true, version: "", directory: "" };
  nativeTetravoxStatus.mockResolvedValue(status);
  await render();
  expect(button("Installing…")?.disabled).toBe(true);
  expect(button("Locate…")?.disabled).toBe(true);
  expect(installNativeTetravox).not.toHaveBeenCalled();
  nativeTetravoxStatus.mockResolvedValue({ ...status, installed: true, installing: false, version: "0.6.0", source: "managed" });
  const listener = onNativeTetravoxProgress.mock.calls[0]?.[0];
  expect(listener).toBeDefined();
  act(() => listener!({ phase: "idle" }));
  await settle();
  expect(button("Launch TetraVox")).toBeDefined();
  expect(container.textContent).toContain("0.6.0");
});

it("polls an in-progress setup even when its completion event is missed", async () => {
  onNativeTetravoxProgress.mockImplementation((listener) => {
    listener({ phase: "download", received: 1024 });
    return () => {};
  });
  nativeTetravoxStatus.mockResolvedValue({ supported: true, installed: false, installing: true, version: "", directory: "" });
  await render();
  nativeTetravoxStatus.mockResolvedValue({ supported: true, installed: true, installing: false, version: "0.6.0", directory: "/managed", source: "managed" });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1100)); });
  await settle();
  expect(button("Launch TetraVox")).toBeDefined();
  expect(button("Locate…")?.disabled).toBe(false);
  expect(container.querySelector('[role="progressbar"]')).toBeNull();
  expect(installNativeTetravox).not.toHaveBeenCalled();
});

it("renders a download progress bar while installing", async () => {
  const status: TitNativeTetravoxStatus = { supported: true, installed: false, installing: true, version: "", directory: "" };
  nativeTetravoxStatus.mockResolvedValue(status);
  onNativeTetravoxProgress.mockImplementation((listener: (p: TitNativeTetravoxProgress) => void) => {
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

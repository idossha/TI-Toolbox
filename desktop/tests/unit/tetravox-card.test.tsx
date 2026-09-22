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
const updateNativeTetravox = vi.fn();
const openNativeTetravox = vi.fn();
const onNativeTetravoxProgress = vi.fn<(listener: (progress: TitNativeTetravoxProgress) => void) => () => void>(() => () => {});

function bridge(): TitBridge {
  return {
    nativeTetravoxStatus,
    installNativeTetravox,
    updateNativeTetravox,
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
  expect(container.textContent).toContain("from the official release");
  expect(button("Retry setup")).toBeDefined();
  expect(button("Launch TetraVox")).toBeUndefined();
  expect(button("Update")).toBeUndefined();
  expect(button("Locate…")).toBeUndefined();
});

it("shows TI's own copy, its version, and Launch and Update actions when installed", async () => {
  const status: TitNativeTetravoxStatus = {
    source: "managed",
    supported: true,
    installed: true,
    installing: false,
    version: "0.6.1",
    directory: "/Users/x/Library/Application Support/TI-Toolbox/runtimes/tetravox-darwin-arm64",
    executable: "/Users/x/Library/Application Support/TI-Toolbox/runtimes/tetravox-darwin-arm64/Tetravox.app/Contents/MacOS/Tetravox",
  };
  nativeTetravoxStatus.mockResolvedValue(status);
  await render();
  expect(container.textContent).toContain("Installed 0.6.1");
  expect(container.textContent).toContain("Installed by TI-Toolbox");
  expect(container.textContent).toContain("runtimes/tetravox-darwin-arm64");
  expect(button("Launch TetraVox")).toBeDefined();
  expect(button("Update")).toBeDefined();
  expect(button("Locate…")).toBeUndefined();
  expect(container.textContent).not.toContain("Updates are managed in TetraVox");
});

it("updates TI's copy through the bridge and refreshes the status", async () => {
  const status: TitNativeTetravoxStatus = { source: "managed", supported: true, installed: true, installing: false, version: "0.6.0", directory: "/managed" };
  nativeTetravoxStatus.mockResolvedValue(status);
  updateNativeTetravox.mockImplementation(async () => {
    nativeTetravoxStatus.mockResolvedValue({ ...status, version: "0.6.1" });
    return { ...status, version: "0.6.1" };
  });
  await render();
  act(() => button("Update")!.click());
  await settle();
  await settle();
  expect(updateNativeTetravox).toHaveBeenCalledOnce();
  expect(container.textContent).toContain("Installed 0.6.1");
});

it("retries failed setup", async () => {
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
});

it("refreshes an automatic installation that finishes outside this card", async () => {
  const status: TitNativeTetravoxStatus = { supported: true, installed: false, installing: true, version: "", directory: "" };
  nativeTetravoxStatus.mockResolvedValue(status);
  await render();
  expect(button("Installing…")?.disabled).toBe(true);
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
  expect(button("Update")?.disabled).toBe(false);
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

it("says so when this platform has no package instead of offering a picker", async () => {
  nativeTetravoxStatus.mockResolvedValue({ supported: false, installed: false, installing: false, version: "", directory: "", error: "TI-Toolbox has no TetraVox package for linux/arm64." });
  await render();
  expect(container.textContent).toContain("no TetraVox package for this platform");
  expect(button("Locate…")).toBeUndefined();
  expect(button("Retry setup")).toBeUndefined();
});

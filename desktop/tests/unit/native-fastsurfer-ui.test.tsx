// @vitest-environment jsdom
import { defaultQsiPrepConfig as prepDefaults, defaultQsiReconConfig as reconDefaults, qsiPrepPreferences, qsiReconPreferences } from "../../src/renderer/pages/preprocess/qsi";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NativeFastSurfer } from "../../src/renderer/pages/preprocess/NativeFastSurfer";
import { AppleGpuSettings, SurferSettingsCard } from "../../src/renderer/pages/settings/SurferSettingsCard";
import { getSurferSettings, putSurferSettings } from "../../src/renderer/pages/settings/api";
import type { TitBridge, TitFastSurferStatus } from "../../src/shared/tit-bridge";

vi.mock("../../src/renderer/pages/settings/api", () => ({ getSurferSettings: vi.fn(), putSurferSettings: vi.fn() }));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
const available: TitFastSurferStatus = { supported: true, installed: false, enabled: false, preferenceEnabled: false, installing: false };
const status = vi.fn();
const enable = vi.fn();
const disable = vi.fn();
beforeEach(() => {
  vi.resetAllMocks();
  status.mockResolvedValue(available);
  window.tit = { fastsurfer: { status, enable, disable } } as unknown as TitBridge;
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => { act(() => root.unmount()); client.clear(); container.remove(); delete window.tit; });
async function settle() { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); }); }
async function render(node = <NativeFastSurfer />) {
  act(() => root.render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>)); await settle();
}
function button(text: string) { return [...document.querySelectorAll("button")].find((item) => item.textContent === text)!; }

it("hides Apple installation in a browser or unsupported connection", async () => {
  delete window.tit; await render(); expect(container.textContent).toBe(""); expect(status).not.toHaveBeenCalled();
  window.tit = { fastsurfer: { status, enable, disable } } as unknown as TitBridge;
  status.mockResolvedValue({ ...available, supported: false }); await render(); expect(container.textContent).toBe("");
});
it("preprocessing links to system settings without installation controls", async () => {
  await render(); expect(container.textContent).toContain("Apple Silicon detected");
  expect(container.querySelector("a")?.getAttribute("href")).toBe("/settings#preprocessing");
  expect(container.querySelector("button")).toBeNull(); expect(enable).not.toHaveBeenCalled();
});
it("requires a single explicit consent before enabling and allows user-wide disabling", async () => {
  enable.mockResolvedValue({ ...available, installed: true, enabled: true, preferenceEnabled: true });
  await render(<AppleGpuSettings />); act(() => button("Enable Apple GPU").click()); await settle();
  expect(enable).not.toHaveBeenCalled();
  const dialog = document.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain("across your projects"); expect(dialog.querySelector('svg[role="img"]')).not.toBeNull();
  expect(dialog.textContent).toContain("third-party scientific software");
  expect(dialog.textContent).toContain("pinned official FastSurfer release");
  expect(dialog.textContent).toContain("validating outputs");
  expect([...dialog.querySelectorAll("a")].map((a) => a.href)).toEqual([
    "https://idossha.github.io/TI-Toolbox/wiki/fastsurfer/#enable-apple-gpu",
    "https://idossha.github.io/TI-Toolbox/wiki/fastsurfer/#permissions",
    "https://github.com/Deep-MI/FastSurfer/releases",
  ]);
  act(() => [...dialog.querySelectorAll("button")].find((item) => item.textContent === "Enable Apple GPU")!.click()); await settle(); expect(enable).toHaveBeenCalledOnce();
  disable.mockResolvedValue({ ...available, installed: true });
  act(() => button("Disable Apple GPU").click()); await settle(); expect(disable).toHaveBeenCalledOnce();
});
it("shows a saved enabled preference even while the worker is inactive", async () => {
  status.mockResolvedValue({ ...available, preferenceEnabled: true }); await render(<AppleGpuSettings />);
  expect(button("Disable Apple GPU")).toBeDefined();
});
it("disables changes during installation and displays failure", async () => {
  status.mockResolvedValue({ ...available, installing: true }); await render(<AppleGpuSettings />);
  expect(container.querySelector("button")!.disabled).toBe(true);
  act(() => client.setQueryData(["native-fastsurfer"], { ...available, error: "Download failed" })); await settle();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("Download failed");
});
it("shows automatic thread capacity separately from the preprocessing job", async () => {
  vi.mocked(getSurferSettings).mockResolvedValue({ charm_options: null, qsiprep_config: qsiPrepPreferences(prepDefaults()), qsi_recon_config: qsiReconPreferences(reconDefaults()), charm_threads: null, qsiprep_threads: null, qsirecon_threads: null, qsiprep_memory_gb: null, qsirecon_memory_gb: null, qsiprep_omp_threads: null, qsirecon_omp_threads: null, effective_charm_threads: 9, effective_qsiprep_threads: 9, effective_qsirecon_threads: 9, freesurfer_recon_all: true, freesurfer_subregions: ["thalamus", "hippo-amygdala"], fastsurfer_threads: null, freesurfer_threads: null, available_threads: 12, default_threads: 9, effective_fastsurfer_threads: 9, effective_freesurfer_threads: 9 });
  await render(<SurferSettingsCard />);
  expect(container.textContent).toContain("of 12 available threads");
  expect(container.querySelectorAll('input[placeholder="Auto (9)"]')).toHaveLength(7);
  expect(putSurferSettings).not.toHaveBeenCalled();
});

it("saves a user thread override without changing the other tool", async () => {
  const prefs = { charm_options: null, qsiprep_config: qsiPrepPreferences(prepDefaults()), qsi_recon_config: qsiReconPreferences(reconDefaults()), charm_threads: null, qsiprep_threads: null, qsirecon_threads: null, qsiprep_memory_gb: null, qsirecon_memory_gb: null, qsiprep_omp_threads: null, qsirecon_omp_threads: null, effective_charm_threads: 9, effective_qsiprep_threads: 9, effective_qsirecon_threads: 9, freesurfer_recon_all: true, freesurfer_subregions: ["thalamus", "hippo-amygdala"] as ("thalamus" | "hippo-amygdala")[], fastsurfer_threads: null, freesurfer_threads: null, available_threads: 12, default_threads: 9, effective_fastsurfer_threads: 9, effective_freesurfer_threads: 9 };
  vi.mocked(getSurferSettings).mockResolvedValue(prefs);
  vi.mocked(putSurferSettings).mockResolvedValue({ ...prefs, fastsurfer_threads: 6, effective_fastsurfer_threads: 6 });
  await render(<SurferSettingsCard />);
  const input = container.querySelector<HTMLInputElement>('input[aria-label="FastSurfer threads"]')!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "6");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  act(() => button("Save pre-processing preferences").click()); await settle();
  expect(vi.mocked(putSurferSettings).mock.calls[0]?.[0]).toMatchObject({ fastsurfer_threads: 6, freesurfer_threads: null });
  expect(button("Save pre-processing preferences").disabled).toBe(true);
});

it("keeps GPU explanation discoverable in browser settings without allowing installation", async () => {
  delete window.tit;
  await render(<AppleGpuSettings />);
  act(() => button("Enable Apple GPU").click()); await settle();
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain("desktop app");
  expect([...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find((item) => item.textContent === "Enable Apple GPU")!.disabled).toBe(true);
  expect(enable).not.toHaveBeenCalled();
});

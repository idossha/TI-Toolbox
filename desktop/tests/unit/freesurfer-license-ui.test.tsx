// @vitest-environment jsdom
/** The app supplies licensing; even damaged installs never request a personal key. */
import { defaultQsiPrepConfig as prepDefaults, defaultQsiReconConfig as reconDefaults, qsiPrepPreferences, qsiReconPreferences } from "../../src/renderer/pages/preprocess/qsi";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FreeSurferLicenseField, FreeSurferLicenseNotice } from "../../src/renderer/pages/settings/FreeSurferLicense";
import { getSurferSettings, type SurferSettings } from "../../src/renderer/pages/settings/api";

vi.mock("../../src/renderer/pages/settings/api", () => ({ getSurferSettings: vi.fn(), putFreeSurferLicense: vi.fn(), deleteFreeSurferLicense: vi.fn() }));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const base: SurferSettings = { charm_options: null, qsiprep_config: qsiPrepPreferences(prepDefaults()), qsi_recon_config: qsiReconPreferences(reconDefaults()), charm_threads: null, qsiprep_threads: null, qsirecon_threads: null, qsiprep_memory_gb: null, qsirecon_memory_gb: null, qsiprep_omp_threads: null, qsirecon_omp_threads: null, effective_charm_threads: 9, effective_qsiprep_threads: 9, effective_qsirecon_threads: 9, freesurfer_recon_all: true, freesurfer_subregions: ["thalamus", "hippo-amygdala"], fastsurfer_threads: null, freesurfer_threads: null, available_threads: 12, default_threads: 9, effective_fastsurfer_threads: 9, effective_freesurfer_threads: 9, freesurfer_license: { configured: false, source: null, email: null } };
const stored: SurferSettings = { ...base, freesurfer_license: { configured: true, source: "bundled", email: null } };

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
beforeEach(() => {
  vi.resetAllMocks();
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => { act(() => root.unmount()); client.clear(); container.remove(); });
async function settle() { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); }); }
async function render(node: React.ReactElement) {
  act(() => root.render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>)); await settle();
}

it.each([base, stored])("never offers license entry or registration", async (settings) => {
  vi.mocked(getSurferSettings).mockResolvedValue(settings);
  await render(<FreeSurferLicenseField />);
  expect(container.textContent).toContain("supplies the FreeSurfer license automatically");
  expect(container.textContent).toContain("No personal license or registration is required");
  expect(container.querySelectorAll("textarea, input, button, a")).toHaveLength(0);
  expect(container.textContent?.includes("Repair or update")).toBe(!settings.freesurfer_license.configured);
});

it("reports a damaged install only for a selected step, with repair guidance", async () => {
  vi.mocked(getSurferSettings).mockResolvedValue(base);
  await render(<FreeSurferLicenseNotice selected={false} />);
  expect(container.textContent).toBe("");
  expect(getSurferSettings).not.toHaveBeenCalled();
  await render(<FreeSurferLicenseNotice selected={true} />);
  expect(container.textContent).toContain("TI-Toolbox license unavailable");
  expect(container.textContent).toContain("Repair or update");
  expect(container.querySelectorAll("textarea, input, button, a")).toHaveLength(0);
  act(() => client.setQueryData(["surfer-settings"], stored)); await settle();
  expect(container.textContent).toBe("");
});

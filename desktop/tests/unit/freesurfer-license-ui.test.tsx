// @vitest-environment jsdom
/**
 * The FreeSurfer license is per registered person and never bundled: the app offers exactly one
 * place to paste it, says which stages need it (and that FastSurfer segmentation does not), and
 * points at the registration page when a licensed stage is selected without one.
 */
import { defaultQsiPrepConfig as prepDefaults, defaultQsiReconConfig as reconDefaults, qsiPrepPreferences, qsiReconPreferences } from "../../src/renderer/pages/preprocess/qsi";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FreeSurferLicenseField, FreeSurferLicenseNotice, FS_REGISTRATION_URL } from "../../src/renderer/pages/settings/FreeSurferLicense";
import { deleteFreeSurferLicense, getSurferSettings, putFreeSurferLicense, type SurferSettings } from "../../src/renderer/pages/settings/api";

vi.mock("../../src/renderer/pages/settings/api", () => ({ getSurferSettings: vi.fn(), putFreeSurferLicense: vi.fn(), deleteFreeSurferLicense: vi.fn() }));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const base: SurferSettings = { charm_options: null, qsiprep_config: qsiPrepPreferences(prepDefaults()), qsi_recon_config: qsiReconPreferences(reconDefaults()), charm_threads: null, qsiprep_threads: null, qsirecon_threads: null, qsiprep_memory_gb: null, qsirecon_memory_gb: null, qsiprep_omp_threads: null, qsirecon_omp_threads: null, effective_charm_threads: 9, effective_qsiprep_threads: 9, effective_qsirecon_threads: 9, freesurfer_recon_all: true, freesurfer_subregions: ["thalamus", "hippo-amygdala"], fastsurfer_threads: null, freesurfer_threads: null, available_threads: 12, default_threads: 9, effective_fastsurfer_threads: 9, effective_freesurfer_threads: 9, freesurfer_license: { configured: false, source: null, email: null } };
const stored: SurferSettings = { ...base, freesurfer_license: { configured: true, source: "app", email: "someone@example.org" } };

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
function button(text: string) { return [...document.querySelectorAll("button")].find((item) => item.textContent === text); }

it("with no license stored, names the licensed stages, exempts FastSurfer and links registration", async () => {
  vi.mocked(getSurferSettings).mockResolvedValue(base);
  await render(<FreeSurferLicenseField />);
  const status = container.querySelector('[data-testid="fs-license-status"]')!.textContent!;
  expect(status).toContain("No license stored");
  expect(status).toContain("recon-all");
  expect(status).toContain("FastSurfer segmentation runs without one");
  expect([...container.querySelectorAll("a")].map((a) => a.href)).toContain(FS_REGISTRATION_URL);
  expect(button("Store license")!.disabled).toBe(true);
  expect(button("Forget license")).toBeUndefined();
});

it("stores the pasted text once and then reports the registered email", async () => {
  vi.mocked(getSurferSettings).mockResolvedValue(base);
  vi.mocked(putFreeSurferLicense).mockResolvedValue(stored);
  await render(<FreeSurferLicenseField />);
  const textarea = container.querySelector("textarea")!;
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => { setter.call(textarea, "someone@example.org\n12345\n *key\n FSkey"); textarea.dispatchEvent(new Event("input", { bubbles: true })); });
  await settle();
  act(() => button("Store license")!.click()); await settle();
  expect(vi.mocked(putFreeSurferLicense).mock.calls[0]![0]).toBe("someone@example.org\n12345\n *key\n FSkey");
  expect(container.querySelector('[data-testid="fs-license-status"]')!.textContent).toContain("License stored for someone@example.org");
  expect(container.querySelector("textarea")!.value).toBe("");
  vi.mocked(deleteFreeSurferLicense).mockResolvedValue(base);
  act(() => button("Forget license")!.click()); await settle();
  expect(deleteFreeSurferLicense).toHaveBeenCalledOnce();
  expect(container.querySelector('[data-testid="fs-license-status"]')!.textContent).toContain("No license stored");
});

it("shows a 422 from the server instead of pretending the license was stored", async () => {
  vi.mocked(getSurferSettings).mockResolvedValue(base);
  vi.mocked(putFreeSurferLicense).mockRejectedValue(new Error("The first line of license.txt is the registered email address"));
  await render(<FreeSurferLicenseField />);
  const textarea = container.querySelector("textarea")!;
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => { setter.call(textarea, "not a license"); textarea.dispatchEvent(new Event("input", { bubbles: true })); });
  await settle();
  act(() => button("Store license")!.click()); await settle();
  expect(container.textContent).toContain("registered email address");
  expect(container.querySelector('[data-testid="fs-license-status"]')!.textContent).toContain("No license stored");
});

it("the Pre-processing notice appears only for a selected FreeSurfer step without a license", async () => {
  vi.mocked(getSurferSettings).mockResolvedValue(base);
  await render(<FreeSurferLicenseNotice selected={false} />);
  expect(container.textContent).toBe("");
  expect(getSurferSettings).not.toHaveBeenCalled();
  await render(<FreeSurferLicenseNotice selected={true} />);
  expect(container.textContent).toContain("FreeSurfer needs your license");
  expect(container.textContent).toContain("FastSurfer segmentation does not need one");
  expect([...container.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([FS_REGISTRATION_URL, "/settings#preprocessing"]);
  act(() => client.setQueryData(["surfer-settings"], stored)); await settle();
  expect(container.textContent).toBe("");
});

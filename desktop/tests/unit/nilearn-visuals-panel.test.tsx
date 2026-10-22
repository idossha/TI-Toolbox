// @vitest-environment jsdom
/**
 * Nilearn visuals panel: the cutoffs start empty so the job takes the display range from the
 * field itself (p95 / p99.9, `tit/plotting/nilearn/cutoffs.py`). The former 0.3 / 5 V/m defaults
 * sat above every TI field (sub-LA L_Insula peaks at 0.164 V/m) and drew blank PDFs. Switching
 * units clears both cutoffs, since a number typed as V/m means nothing as a percentile.
 * `nilearn-visuals-defaults.test.ts` covers what an empty cutoff is sent as (null).
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("../../src/renderer/api/client", () => ({ getSubjects: vi.fn(async () => []) }));
vi.mock("../../src/renderer/pages/panels/nilearn-visuals/api", () => ({
  createNilearnJob: vi.fn(),
  getSimulationsFor: vi.fn(async () => []),
  planNilearn: vi.fn(),
  validateNilearn: vi.fn(),
}));
// The run pane (job console) and scroll memory have their own tests; this file tests the form.
vi.mock("../../src/renderer/pages/panels/ExtensionRunPanel", () => ({
  ExtensionRunPanel: () => null,
  useExtensionJobs: () => ({ startedJobIds: [], pinnedJobId: null, setPinnedJobId: () => {}, trackJob: () => {} }),
}));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

import page from "../../src/renderer/pages/panels/nilearn-visuals/index";
import { clearPageSession } from "../../src/renderer/app/pageSession";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
beforeEach(() => {
  clearPageSession();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = page.Component;
  act(() => root.render(<QueryClientProvider client={client}><Panel /></QueryClientProvider>));
});
afterEach(() => {
  act(() => root.unmount());
  client.clear();
  container.remove();
});

/** The units checkbox: the one whose label row names percentiles (the participants table has its own). */
const unitsCheckbox = () =>
  [...container.querySelectorAll<HTMLLabelElement>(".checkbox-label-row")]
    .find((row) => row.textContent?.includes("percentiles"))!
    .querySelector<HTMLButtonElement>('[role="checkbox"]')!;
const input = (id: string) => container.querySelector<HTMLInputElement>(`#${id}`)!;
const unitOf = (id: string) => input(id).parentElement!.querySelector(".number-input-unit")!.textContent;

function type(el: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  act(() => {
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

it("starts with both cutoffs empty, in V/m, labelled as the field's own percentiles", () => {
  expect(input("nilearn-min-cutoff").value).toBe("");
  expect(input("nilearn-max-cutoff").value).toBe("");
  expect(input("nilearn-min-cutoff").placeholder).toBe("auto (p95)");
  expect(input("nilearn-max-cutoff").placeholder).toBe("auto (p99.9)");
  expect(unitOf("nilearn-min-cutoff")).toBe("V/m");

  expect(unitsCheckbox().getAttribute("aria-checked")).toBe("false");
  // The job reads percentiles of the non-zero voxels (cutoffs.resolve_cutoffs), not "% of the maximum".
  expect(container.textContent).toContain("percentiles (0–100) of the field's non-zero voxels");
  expect(container.textContent).not.toContain("of the maximum");
});

it("clears both cutoffs when the unit switches between V/m and percentiles", () => {
  type(input("nilearn-min-cutoff"), "0.05");
  type(input("nilearn-max-cutoff"), "0.15");
  expect(input("nilearn-min-cutoff").value).toBe("0.05");

  act(() => unitsCheckbox().click());
  expect(unitOf("nilearn-min-cutoff")).toBe("%");
  expect(input("nilearn-min-cutoff").value).toBe("");
  expect(input("nilearn-max-cutoff").value).toBe("");
});

// @vitest-environment jsdom
/**
 * Settings ▸ Execution ▸ CPU limit: shows the saved percent and the cores it resolves to, and saves
 * only on Apply. Expected core counts are floor(percent x available / 100), min 1 — the rule stated
 * in docs/dev/ARCHITECTURE.md (scheduler budget) and implemented server-side by `tit.cpu.cpu_limit`.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CpuLimitField, coresFor } from "../../src/renderer/pages/settings/CpuLimitField";
import { getCpuLimit, putCpuLimit } from "../../src/renderer/pages/settings/api";

vi.mock("../../src/renderer/pages/settings/api", () => ({ getCpuLimit: vi.fn(), putCpuLimit: vi.fn() }));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
// jsdom has no ResizeObserver; the Radix slider only uses it to measure its thumb.
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
beforeEach(() => {
  vi.resetAllMocks();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => {
  act(() => root.unmount());
  client.clear();
  container.remove();
});
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

it("resolves a percent to whole cores, never zero", () => {
  expect(coresFor(70, 10)).toBe(7);
  expect(coresFor(70, 12)).toBe(8); // 8.4 floors
  expect(coresFor(10, 4)).toBe(1); // 0.4 would be zero
  expect(coresFor(100, 12)).toBe(12);
});

it("shows the saved limit as percent and cores, and saves a new one only on Apply", async () => {
  vi.mocked(getCpuLimit).mockResolvedValue({ percent: 70, cores: 7, available_cores: 10, default_percent: 70 });
  vi.mocked(putCpuLimit).mockResolvedValue({ percent: 80, cores: 8, available_cores: 10, default_percent: 70 });
  act(() => root.render(<QueryClientProvider client={client}><CpuLimitField /></QueryClientProvider>));
  await settle();
  const summary = () => container.querySelector('[data-testid="cpu-limit-summary"]')?.textContent;
  expect(summary()).toBe("70 % · 7 of 10 cores");

  const apply = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("Apply"))!;
  expect(apply.disabled).toBe(true);

  const thumb = container.querySelector('[role="slider"]') as HTMLElement;
  act(() => thumb.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
  act(() => thumb.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
  expect(summary()).toBe("80 % · 8 of 10 cores");
  expect(putCpuLimit).not.toHaveBeenCalled();

  act(() => apply.click());
  await settle();
  expect(putCpuLimit).toHaveBeenCalledTimes(1);
  expect(vi.mocked(putCpuLimit).mock.calls[0]?.[0]).toBe(80);
  expect(summary()).toBe("80 % · 8 of 10 cores");
});

// @vitest-environment jsdom
/**
 * Applying a cap refreshes every net picker (p32, `pages/panels/caps/index.tsx` `apply`).
 *
 * A warp writes `m2m_<sid>/eeg_positions/<net>.csv` as a request, not a job, so the job-completion
 * invalidation never runs for it. The Simulator (`subject-detail`) and the Optimizer (`eeg-nets`)
 * read their nets with a 60 s staleTime, so before this fix a cap applied and then picked within a
 * minute was missing from both pickers.
 *
 * The queries are seeded in a real QueryClient with the key shapes the pages build, and the test
 * reads each one's `isInvalidated` after Apply: a spy that echoes the call list would pass on a
 * key the pages never use.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider, type QueryKey } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EEG_NET_QUERIES } from "../../src/renderer/app/jobs/invalidation";
import type { CapStatus } from "../../src/renderer/pages/panels/caps/api";

const api = vi.hoisted(() => ({
  uploadCap: vi.fn(),
  getAvailableCaps: vi.fn(),
  inspectNet: vi.fn(),
  warpCaps: vi.fn(),
}));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), blocked: vi.fn() }));

vi.mock("../../src/renderer/api/client", async (original) => ({
  ...(await original<object>()),
  getSubjects: vi.fn(async () => [{ id: "ernie", has_raw: true, has_fastsurfer: false, has_freesurfer: false, has_m2m: true }]),
}));
vi.mock("../../src/renderer/pages/panels/caps/api", async (original) => ({ ...(await original<object>()), ...api }));
vi.mock("../../src/renderer/ui/Toast", async (original) => ({
  ...(await original<object>()),
  notify: toast,
  notifySubmitError: (message: string, error: unknown) => toast.error(message, error instanceof Error ? error.message : undefined),
}));
vi.mock("../../src/renderer/pages/_shared/scene", () => ({ ScenePane: () => null }));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

const { default: page } = await import("../../src/renderer/pages/panels/caps/index");
const { clearPageSession } = await import("../../src/renderer/app/pageSession");

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const NET = "EEG10-10_UI_Jurak_2007.csv";
const cap = (name: string, onSubject: boolean): CapStatus => ({ name, source: "simnibs", on_subject: onSubject, subject_mtime: null });

/**
 * The reads a just-applied net must reach, keyed as the pages key them: the Optimizer's picker
 * (`optimizer/index.tsx`), the Simulator's (`simulator/index.tsx`), the montage editor's electrode
 * list (`simulator/MontageManager.tsx`, net first) and ex-search's leadfield ETA (`ExSections.tsx`).
 */
const NET_READS: QueryKey[] = [
  ["eeg-nets", "ernie"],
  ["subject-detail", "ernie"],
  ["eeg-net-electrodes", NET, "ernie"],
  ["leadfield-eta", "ernie", NET],
];
/** Reads a net does not feed: the atlas picker and the head surfaces stay cached. */
const UNRELATED: QueryKey[] = [
  ["atlases", "ernie"],
  ["scene", "surface", "ernie", "skin"],
];

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

async function settle() {
  for (let i = 0; i < 5; i++) await act(async () => await new Promise((resolve) => setTimeout(resolve, 0)));
}

beforeEach(async () => {
  for (const fn of [...Object.values(api), ...Object.values(toast)]) fn.mockReset();
  api.getAvailableCaps.mockResolvedValue([cap(NET, false)]);
  api.warpCaps.mockResolvedValue([NET]);
  clearPageSession();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const key of [...NET_READS, ...UNRELATED]) client.setQueryData(key, { cached: true });
  const Panel = page.Component;
  act(() => root.render(<QueryClientProvider client={client}><Panel /></QueryClientProvider>));
  await settle();
  expect(api.getAvailableCaps).toHaveBeenCalledWith("ernie");
});

afterEach(() => {
  act(() => root.unmount());
  client.clear();
  container.remove();
});

async function applyNet() {
  const box = container.querySelector<HTMLButtonElement>(`[aria-label="Select EEG10-10_UI_Jurak_2007"]`);
  expect(box, "the cap's row checkbox").not.toBeNull();
  await act(async () => box!.click());
  await act(async () => container.querySelector<HTMLButtonElement>('[data-testid="caps-apply"]')!.click());
  await settle();
  expect(api.warpCaps.mock.calls).toEqual([["ernie", [NET], false]]);
}

const invalidated = (key: QueryKey) => client.getQueryState(key)?.isInvalidated ?? false;

describe("Apply on the EEG caps panel", () => {
  it("marks every net picker's read stale for that subject", async () => {
    for (const key of NET_READS) expect(invalidated(key), JSON.stringify(key)).toBe(false);
    await applyNet();
    for (const key of NET_READS) expect(invalidated(key), JSON.stringify(key)).toBe(true);
  });

  it("covers every key of the shared net list, the one a head-model job invalidates", async () => {
    await applyNet();
    // Each prefix in EEG_NET_QUERIES matches a seeded read, and that read is now stale.
    for (const prefix of EEG_NET_QUERIES) {
      const queries = client.getQueryCache().findAll({ queryKey: prefix });
      expect(queries.length, JSON.stringify(prefix)).toBeGreaterThan(0);
      for (const q of queries) expect(q.state.isInvalidated, JSON.stringify(q.queryKey)).toBe(true);
    }
    expect(EEG_NET_QUERIES.map((k) => JSON.stringify(k))).toContain(JSON.stringify(["subject-detail"]));
  });

  it("leaves reads a net does not feed cached", async () => {
    await applyNet();
    for (const key of UNRELATED) expect(invalidated(key), JSON.stringify(key)).toBe(false);
  });

  it("a refused warp invalidates nothing", async () => {
    api.warpCaps.mockReset().mockRejectedValue(new Error("SimNIBS is not installed"));
    const box = container.querySelector<HTMLButtonElement>(`[aria-label="Select EEG10-10_UI_Jurak_2007"]`)!;
    await act(async () => box.click());
    await act(async () => container.querySelector<HTMLButtonElement>('[data-testid="caps-apply"]')!.click());
    await settle();
    expect(toast.error).toHaveBeenCalledWith("Could not apply the cap.", "SimNIBS is not installed");
    for (const key of NET_READS) expect(invalidated(key), JSON.stringify(key)).toBe(false);
  });
});

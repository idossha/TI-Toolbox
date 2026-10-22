// @vitest-environment jsdom
/**
 * Cluster permutation: re-running an analysis name that already exists (p23).
 *
 * The server refuses a stats job whose `stats/<mode>/<analysis_name>/` folder exists unless the
 * submission says `overwrite: true` (`tit/server/overwrite_policy.py`, HTTP 409). The panel never
 * sent `overwrite`, so a re-run of a name was a dead-end "Could not queue" toast. It now opens the
 * same skip/replace dialog the NIfTI averaging panel shows, and "Replace and rerun" resubmits the
 * same config with `overwrite: true`; "Skip" queues nothing. A refusal that is not a 409 stays an
 * error toast.
 *
 * Expected values: the server's 409 contract and the dialog's own test ids
 * (`ExistingOutputsDialog.tsx`); the submitted config is compared with the first submission, not
 * retyped. The api module is mocked; nothing here reads the disk. Dated 2026-10-22.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../../src/renderer/api/client";
import { clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";

const api = vi.hoisted(() => ({
  getSimulationsFor: vi.fn(),
  validateStats: vi.fn(),
  planStats: vi.fn(),
  createStatsJob: vi.fn(),
}));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), blocked: vi.fn() }));

vi.mock("../../src/renderer/api/client", async (original) => ({ ...(await original<object>()), getSubjects: vi.fn(async () => []) }));
vi.mock("../../src/renderer/pages/panels/cluster-permutation/api", () => api);
vi.mock("../../src/renderer/ui/Toast", async (original) => ({
  ...(await original<object>()),
  notify: toast,
  notifySubmitError: (message: string) => toast.error(message),
}));
vi.mock("../../src/renderer/pages/panels/ExtensionRunPanel", () => ({
  ExtensionRunPanel: () => null,
  useExtensionJobs: () => ({ startedJobIds: [], pinnedJobId: null, setPinnedJobId: () => {}, trackJob: () => {} }),
}));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

const { default: page } = await import("../../src/renderer/pages/panels/cluster-permutation/index");

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const CONFLICT = new ApiError(409, "/api/jobs", "Outputs of this stats job already exist. Explicit overwrite confirmation is required: /p/stats");

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  for (const fn of [...Object.values(api), ...Object.values(toast)]) fn.mockReset();
  api.getSimulationsFor.mockResolvedValue([]);
  api.validateStats.mockResolvedValue({ ok: true, errors: [] });
  api.planStats.mockResolvedValue({ jobs: [{ kind: "stats", subject: "", output_dir: "/p/stats", exists: true, will_overwrite: true }], lock_conflicts: [], cost: { cpus: 1, mem_gb: 1 }, warnings: [] });
  clearPageSession();
  writeSession(sessionSlot("", "mode"), "classification");
  writeSession(sessionSlot("", "analysisName"), "rerun");
  writeSession(sessionSlot("", "rows"), [
    { id: "r1", subjectId: "001", simulationName: "M1", response: 1, effectSize: undefined, weight: 1 },
    { id: "r2", subjectId: "002", simulationName: "M1", response: 0, effectSize: undefined, weight: 1 },
  ]);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = page.Component;
  act(() => root.render(<QueryClientProvider client={client}><Panel /></QueryClientProvider>));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  client.clear();
  vi.useRealTimers();
});

async function settle() {
  for (let i = 0; i < 4; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
  }
}

const byTestId = (id: string) => document.querySelector<HTMLButtonElement>(`[data-testid="${id}"]`);

async function pressRun() {
  await settle();
  const run = byTestId("run-button")!;
  expect(run.disabled, "the 1-vs-1 comparison is runnable").toBe(false);
  await act(async () => run.click());
  await settle();
}

it("asks instead of failing when the analysis name exists, and Replace resubmits with overwrite", async () => {
  api.createStatsJob.mockRejectedValueOnce(CONFLICT).mockResolvedValueOnce({ id: "job-2" });
  await pressRun();

  expect(api.createStatsJob).toHaveBeenCalledTimes(1);
  const [config, subjects, overwrite] = api.createStatsJob.mock.calls[0]!;
  expect(overwrite).toBe(false);
  expect(toast.error).not.toHaveBeenCalled();
  expect(byTestId("existing-outputs-replace")).not.toBeNull();

  await act(async () => byTestId("existing-outputs-replace")!.click());
  await settle();
  expect(api.createStatsJob).toHaveBeenCalledTimes(2);
  expect(api.createStatsJob.mock.calls[1]).toEqual([config, subjects, true]);
  expect(byTestId("existing-outputs-replace")).toBeNull();
  expect(toast.success).toHaveBeenCalledTimes(1);
});

it("Skip leaves the existing analysis alone and queues nothing", async () => {
  api.createStatsJob.mockRejectedValueOnce(CONFLICT);
  await pressRun();

  await act(async () => byTestId("existing-outputs-skip")!.click());
  await settle();
  expect(api.createStatsJob).toHaveBeenCalledTimes(1);
  expect(byTestId("existing-outputs-skip")).toBeNull();
  expect(toast.success).not.toHaveBeenCalled();
});

it("a refusal that is not about existing outputs stays an error, with no dialog", async () => {
  api.createStatsJob.mockRejectedValueOnce(new ApiError(422, "/api/jobs", "Missing inputs"));
  await pressRun();

  expect(toast.error).toHaveBeenCalledTimes(1);
  expect(byTestId("existing-outputs-replace")).toBeNull();
  expect(api.createStatsJob).toHaveBeenCalledTimes(1);
});

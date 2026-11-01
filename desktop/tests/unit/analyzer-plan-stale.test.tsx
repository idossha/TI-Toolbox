// @vitest-environment jsdom
/**
 * Analyzer Run waits for the current plan (G1-4).
 *
 * The plan is debounced 400 ms on the job specs. While it is pending or stale, Run was not
 * blocked: a duplicate row typed a moment before could queue two jobs into one folder (the
 * collision check reads the plan), and a retry keyed on the debounced specs could resubmit stale
 * ones. Run is now blocked with "Resolving the plan…" until the plan of the current specs is in,
 * as the Optimizer's Run is ("Resolving the run folders…").
 *
 * Mocked: the page's api module (the plan never resolves here), the 3-D pane and the run pane.
 * Expected values: the sentence the page prints for an unresolved plan, and that nothing is
 * submitted. Dated 2026-10-31.
 *
 * Reproduce: cd desktop && npx vitest run tests/unit/analyzer-plan-stale.test.tsx
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { PageIdContext, clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";

const api = vi.hoisted(() => ({
  submitAnalyzerJob: vi.fn(),
  planAnalyzer: vi.fn(),
  planAnalyzerBatch: vi.fn(),
  getSimulationDetails: vi.fn(),
}));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), blocked: vi.fn() }));

vi.mock("../../src/renderer/pages/analyzer/api", async (original) => ({ ...(await original<object>()), ...api }));
vi.mock("../../src/renderer/ui/Toast", async (original) => ({ ...(await original<object>()), notify: toast, notifySubmitError: toast.error }));
vi.mock("../../src/renderer/app/subjectContext", () => ({ useSubject: () => ({ id: "001", subjects: [{ id: "001" }] }) }));
vi.mock("../../src/renderer/app/openInViewer", () => ({ useOpenInViewer: () => vi.fn() }));
vi.mock("../../src/renderer/pages/_shared/scene/TargetPreview", () => ({ TargetPreview: () => null }));
vi.mock("../../src/renderer/pages/_shared/run/RunPanel", () => ({ RunPanel: () => null }));

const { AnalyzerPage } = await import("../../src/renderer/pages/analyzer/AnalyzerPage");
const { emptyAnalyzerRow } = await import("../../src/renderer/pages/analyzer/JobRows");

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  for (const fn of [...Object.values(api), ...Object.values(toast)]) fn.mockReset();
  api.getSimulationDetails.mockResolvedValue([{ name: "sim1", fields: ["TI_max"] }]);
  api.planAnalyzerBatch.mockReturnValue(new Promise(() => {}));
  api.submitAnalyzerJob.mockResolvedValue({ id: "job-1" });
  clearPageSession();
  writeSession(sessionSlot("analyzer", "jobRows"), [
    emptyAnalyzerRow({ subjectId: "001", simulation: "sim1", roi: { mode: "spherical", space: "subject", spheres: [{ x: 1, y: 2, z: 3, radius: 5 }] } as never }),
  ]);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  client.clear();
  vi.useRealTimers();
});

it("blocks Run, and queues nothing, while the plan of the current specs has not resolved", async () => {
  act(() =>
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PageIdContext.Provider value="analyzer">
            <AnalyzerPage />
          </PageIdContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
  for (let i = 0; i < 4; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
  }
  expect(api.planAnalyzerBatch, "the plan was asked for").toHaveBeenCalled();
  const run = document.querySelector('[data-testid="run-button"]') as HTMLButtonElement;
  expect(run.disabled).toBe(true);
  expect(run.title).toBe("Resolving the plan…");

  await act(async () => run.click());
  expect(api.submitAnalyzerJob).not.toHaveBeenCalled();
});

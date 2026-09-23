// @vitest-environment jsdom
/**
 * The first Run press on a job whose output already exists (bug 2026-09-23), on the Analyzer and
 * the Simulator.
 *
 * The page's pre-check reads a cached, debounced plan. When that plan still says "no outputs" (a
 * run that just finished, a plan still resolving), the server refuses the submission with HTTP 409
 * (`tit/server/overwrite_policy.py`). That refusal used to surface as an error toast ("Could not
 * queue the analysis: Simulation outputs already exist…") and only the second press opened the
 * skip/replace dialog. The refusal must open the dialog on the first press.
 *
 * The plan, the submission and the simulation list are mocked at the page's api module; nothing
 * here reads the disk.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../src/renderer/api/client";
import { PageIdContext, clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";

const api = vi.hoisted(() => ({
  submitAnalyzerJob: vi.fn(),
  planAnalyzer: vi.fn(),
  planAnalyzerBatch: vi.fn(),
  getSimulationDetails: vi.fn(),
}));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), blocked: vi.fn() }));

vi.mock("../../src/renderer/pages/analyzer/api", async (original) => ({ ...(await original<object>()), ...api }));
vi.mock("../../src/renderer/ui/Toast", async (original) => ({
  ...(await original<object>()),
  notify: toast,
  notifySubmitError: (message: string) => toast.error(message),
}));
vi.mock("../../src/renderer/app/subjectContext", () => ({
  useSubject: () => ({ id: "001", subjects: [{ id: "001" }] }),
}));
vi.mock("../../src/renderer/app/openInViewer", () => ({ useOpenInViewer: () => vi.fn() }));
vi.mock("../../src/renderer/pages/_shared/scene/TargetPreview", () => ({ TargetPreview: () => null }));
vi.mock("../../src/renderer/pages/_shared/run/RunPanel", () => ({ RunPanel: () => null }));
const sim = vi.hoisted(() => ({ planSim: vi.fn(), submitJobGroup: vi.fn() }));
vi.mock("../../src/renderer/pages/simulator/api", async (original) => ({ ...(await original<object>()), planSim: sim.planSim }));
vi.mock("../../src/renderer/pages/simulator/buildConfig", async (original) => ({
  ...(await original<object>()),
  buildMontageSources: () => undefined,
  buildSimulationConfig: (row: { subjectId: string }) => ({ subject_id: row.subjectId }),
}));
vi.mock("../../src/renderer/pages/_shared/run/jobGroups", async (original) => ({
  ...(await original<object>()),
  submitJobGroup: sim.submitJobGroup,
}));

const { AnalyzerPage } = await import("../../src/renderer/pages/analyzer/AnalyzerPage");
const { emptyAnalyzerRow } = await import("../../src/renderer/pages/analyzer/JobRows");
const { RunButton } = await import("../../src/renderer/pages/simulator/RunControls");

function plan(willOverwrite: boolean) {
  return {
    jobs: [{ kind: "analyzer", subject: "001", output_dir: "/p/analysis", exists: willOverwrite, will_overwrite: willOverwrite }],
    lock_conflicts: [],
    cost: { cpus: 1, mem_gb: 1 },
    warnings: [],
    resolved: null,
  };
}

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  for (const fn of [...Object.values(api), ...Object.values(toast), ...Object.values(sim)]) fn.mockReset();
  api.getSimulationDetails.mockResolvedValue([{ name: "sim1", fields: ["TI_max"] }]);
  // The stale pre-check: the cached plan says nothing exists yet ...
  api.planAnalyzerBatch.mockResolvedValue(plan(false));
  // ... while the disk (and so a fresh plan, and the server) says it does.
  api.planAnalyzer.mockResolvedValue(plan(true));
  api.submitAnalyzerJob.mockRejectedValue(
    new ApiError(409, "/api/jobs", "Outputs of this analyzer job already exist. Explicit overwrite confirmation is required: /p/analysis"),
  );
  clearPageSession();
  writeSession(sessionSlot("analyzer", "jobRows"), [
    emptyAnalyzerRow({
      subjectId: "001",
      simulation: "sim1",
      roi: { mode: "spherical", space: "subject", spheres: [{ x: 1, y: 2, z: 3, radius: 5 }] } as never,
    }),
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

async function settle() {
  for (let i = 0; i < 5; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
  }
}

describe("Analyzer Run with existing output", () => {
  it("opens the skip/replace dialog on the first press when the server refuses a stale pre-check", async () => {
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
    await settle();
    const run = document.querySelector('[data-testid="run-button"]') as HTMLButtonElement;
    expect(run.disabled).toBe(false);

    await act(async () => run.click());
    await settle();

    expect(api.submitAnalyzerJob).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
    expect(document.querySelector('[data-testid="existing-outputs-skip"]')).not.toBeNull();

    // Skip queues only the new analyses — here none, so nothing is resubmitted.
    await act(async () => (document.querySelector('[data-testid="existing-outputs-skip"]') as HTMLButtonElement).click());
    await settle();
    expect(api.submitAnalyzerJob).toHaveBeenCalledTimes(1);
    expect(toast.info).toHaveBeenCalledWith(expect.stringContaining("already has output"));
  });
});

describe("Simulator Run with existing output", () => {
  it("opens the dialog when the server refuses a group the cached plan called new", async () => {
    sim.planSim.mockResolvedValue(plan(true));
    sim.submitJobGroup.mockRejectedValue(new ApiError(409, "/api/jobs/groups", "Outputs of this sim job already exist."));
    const stalePlan = { model: null, loading: false, refetching: false, error: undefined, refetch: () => {}, blockedReason: null, existingCount: 0 };
    act(() =>
      root.render(
        <QueryClientProvider client={client}>
          <RunButton rows={[{ subjectId: "001" } as never]} params={{} as never} plan={stalePlan} onSubmitted={() => {}} label="Run" />
        </QueryClientProvider>,
      ),
    );
    await act(async () => (document.querySelector('[data-testid="run-button"]') as HTMLButtonElement).click());
    await settle();

    expect(sim.submitJobGroup).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
    expect(document.querySelector('[data-testid="existing-outputs-skip"]')).not.toBeNull();
  });
});

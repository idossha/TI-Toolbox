// @vitest-environment jsdom
/**
 * Cluster permutation: the Run gate blocks what the server refuses (p23).
 *
 * The server's rules are `GroupComparisonConfig`/`CorrelationConfig.__post_init__`
 * (`tit/stats/config.py`, pinned by `tests/test_stats_config_validation.py`). The page used to
 * let a 2-row correlation run (MIN_PARTICIPANTS was 2 in both modes; CorrelationConfig needs 3)
 * and a paired test with unequal groups, and it never blocked on the server's own
 * `/api/validate/stats` verdict, so a config the server called invalid could still be submitted.
 *
 * Expected values: the counts come from the config rules (>= 3 rows for a correlation, equal
 * group sizes for a paired test); the server message is whatever the mocked validate route
 * returns, and the gate must show it. The corpus (`tests/test_desktop_config_corpus.py`) checks
 * the same verdicts against the real server for the cases it carries. Dated 2026-10-22.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";

const api = vi.hoisted(() => ({
  getSimulationsFor: vi.fn(),
  validateStats: vi.fn(),
  planStats: vi.fn(),
  createStatsJob: vi.fn(),
}));

vi.mock("../../src/renderer/api/client", async (original) => ({ ...(await original<object>()), getSubjects: vi.fn(async () => []) }));
vi.mock("../../src/renderer/pages/panels/cluster-permutation/api", () => api);
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

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  for (const fn of Object.values(api)) fn.mockReset();
  api.getSimulationsFor.mockResolvedValue([]);
  api.validateStats.mockResolvedValue({ ok: true, errors: [] });
  api.planStats.mockResolvedValue({ jobs: [], lock_conflicts: [], cost: { cpus: 1, mem_gb: 1 }, warnings: [] });
});
afterEach(() => {
  vi.useRealTimers();
});

type Row = { subjectId: string; response?: 0 | 1; effectSize?: number };

/** Render the panel with these rows; return the Run button's state after the debounced checks. */
async function gate(mode: "classification" | "correlation", rows: Row[], extra: Record<string, unknown> = {}) {
  clearPageSession();
  writeSession(sessionSlot("", "mode"), mode);
  writeSession(sessionSlot("", "analysisName"), "gates");
  writeSession(
    sessionSlot("", "rows"),
    rows.map((r, i) => ({ id: `g${i}`, simulationName: "M1", response: r.response ?? 1, effectSize: r.effectSize, weight: 1, subjectId: r.subjectId })),
  );
  for (const [key, value] of Object.entries(extra)) writeSession(sessionSlot("", key), value);
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = page.Component;
  act(() => root.render(<QueryClientProvider client={client}><Panel /></QueryClientProvider>));
  for (let i = 0; i < 4; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
  }
  const run = container.querySelector<HTMLButtonElement>('[data-testid="run-button"]')!;
  const state = { disabled: run.disabled, title: run.getAttribute("title") };
  act(() => root.unmount());
  client.clear();
  container.remove();
  return state;
}

it("a correlation needs three rows: two are blocked, three run", async () => {
  expect(await gate("correlation", [{ subjectId: "001", effectSize: 0.4 }, { subjectId: "002", effectSize: 1.2 }])).toEqual({
    disabled: true,
    title: "Add at least 3 subjects with a simulation.",
  });
  expect(
    await gate("correlation", [
      { subjectId: "001", effectSize: 0.4 },
      { subjectId: "002", effectSize: 1.2 },
      { subjectId: "003", effectSize: -0.3 },
    ]),
  ).toEqual({ disabled: false, title: null });
});

it("a two-group comparison still runs with one subject per group", async () => {
  expect(await gate("classification", [{ subjectId: "001", response: 1 }, { subjectId: "002", response: 0 }])).toEqual({ disabled: false, title: null });
});

it("a paired test needs as many responders as non-responders", async () => {
  const twoVsOne: Row[] = [{ subjectId: "001", response: 1 }, { subjectId: "002", response: 1 }, { subjectId: "003", response: 0 }];
  expect(await gate("classification", twoVsOne, { "classification.testType": "paired" })).toEqual({
    disabled: true,
    title: "A paired test needs as many responders as non-responders (2 vs 1).",
  });
  // The same rows unpaired are fine, and so is a balanced paired design.
  expect(await gate("classification", twoVsOne)).toEqual({ disabled: false, title: null });
  expect(
    await gate("classification", [...twoVsOne, { subjectId: "004", response: 0 }], { "classification.testType": "paired" }),
  ).toEqual({ disabled: false, title: null });
});

it("the server's refusal blocks Run with the server's own sentence", async () => {
  api.validateStats.mockResolvedValue({
    ok: false,
    errors: [{ path: "n_permutations", message: "n_permutations must be at least 19 at alpha 0.05, got 5" }],
  });
  expect(await gate("classification", [{ subjectId: "001", response: 1 }, { subjectId: "002", response: 0 }], { "advanced.nPermutations": 5 })).toEqual({
    disabled: true,
    title: "n_permutations: n_permutations must be at least 19 at alpha 0.05, got 5",
  });
  // The config the server judged is the one the user typed.
  expect(api.validateStats.mock.calls.at(-1)![0]).toMatchObject({ n_permutations: 5 });
});

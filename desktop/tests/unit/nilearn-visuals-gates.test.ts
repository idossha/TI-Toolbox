// @vitest-environment jsdom
/**
 * Nilearn visuals: the Run gate blocks what the server refuses, with the server's sentence (p35).
 *
 * What it pins (2026-10-22): `NilearnConfig.__post_init__` (tit/plotting/nilearn/config.py)
 * refuses a sub-directory that is not one folder ("../stats" wrote the group average into
 * derivatives/ti-toolbox/stats/), an empty display range (min_cutoff >= max_cutoff) and a
 * subject/simulation pair listed twice (it would count double in the mean). The panel used to
 * show those refusals in the plan pane but leave Run enabled, so a click queued a job the
 * server then refused. Now the server's verdict is a blocker like the page's own checks: Run is
 * disabled, its title is the server's sentence, and a click submits nothing.
 *
 * Where the expectations come from: `REFUSALS` below is what `POST /api/validate/nilearn`
 * answers for each case; `tests/test_nilearn_config_cross_field.py` reads this table and asserts
 * the real route returns exactly these errors, so the mock cannot drift from the server. The
 * configs the mocked route receives are checked to be the ones the user typed (the panel does
 * not quietly repair them).
 *
 * Reproduce: cd desktop && npx vitest run tests/unit/nilearn-visuals-gates.test.ts
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getSimulationsFor: vi.fn(),
  validateNilearn: vi.fn(),
  planNilearn: vi.fn(),
  createNilearnJob: vi.fn(),
}));

vi.mock("../../src/renderer/api/client", async (original) => ({ ...(await original<object>()), getSubjects: vi.fn(async () => [{ id: "101" }, { id: "LA" }]) }));
vi.mock("../../src/renderer/pages/panels/nilearn-visuals/api", () => api);
vi.mock("../../src/renderer/pages/panels/ExtensionRunPanel", () => ({
  ExtensionRunPanel: () => null,
  useExtensionJobs: () => ({ startedJobIds: [], pinnedJobId: null, setPinnedJobId: () => {}, trackJob: () => {} }),
}));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

import { clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";
import page from "../../src/renderer/pages/panels/nilearn-visuals/index";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

/** What `POST /api/validate/nilearn` answers per case (checked against the real route in Python). */
const REFUSALS = {
  subdir: { path: "subdir_name", message: "invalid subdir_name '../stats': letters, digits, '.', '_', '-' and inner spaces only, not starting with '.', at most 128 characters" },
  cutoffs: { path: "min_cutoff", message: "min_cutoff 0.2 V/m must be below max_cutoff 0.1 V/m: nothing would be drawn" },
  duplicate: { path: "subject_simulation_pairs", message: "subject_simulation_pairs lists sub-101 / L_Insula twice: the group average would count that simulation double" },
};

const INSULA_101 = { id: "p1", subjectId: "101", simulationName: "L_Insula" };
const INSULA_LA = { id: "p2", subjectId: "LA", simulationName: "L_Insula" };

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  for (const fn of Object.values(api)) fn.mockReset();
  api.getSimulationsFor.mockResolvedValue([{ name: "L_Insula", path: "/p/L_Insula" }]);
  api.validateNilearn.mockResolvedValue({ ok: true, errors: [] });
  api.planNilearn.mockResolvedValue({ jobs: [], lock_conflicts: [], cost: { cpus: 1, mem_gb: 1 }, warnings: [] });
  api.createNilearnJob.mockResolvedValue({ id: "job-1" });
});
afterEach(() => {
  vi.useRealTimers();
});

type Form = { pairs?: unknown[]; subdir?: string; minCutoff?: number; maxCutoff?: number };

/** Render the panel with this form, let the debounced validation settle, click Run once. */
async function gate(form: Form) {
  clearPageSession();
  writeSession(sessionSlot("", "pairs"), form.pairs ?? [INSULA_101, INSULA_LA]);
  writeSession(sessionSlot("", "subdir"), form.subdir ?? "insula_group");
  if (form.minCutoff !== undefined) writeSession(sessionSlot("", "minCutoff"), form.minCutoff);
  if (form.maxCutoff !== undefined) writeSession(sessionSlot("", "maxCutoff"), form.maxCutoff);
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = (page as unknown as { Component: () => React.ReactElement }).Component;
  act(() => root.render(React.createElement(QueryClientProvider, { client }, React.createElement(Panel))));
  for (let turn = 0; turn < 4; turn += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
  }
  const run = container.querySelector<HTMLButtonElement>('[data-testid="run-button"]')!;
  const state = { disabled: run.disabled, title: run.getAttribute("title") };
  await act(async () => {
    // A disabled button ignores clicks; dispatching straight to the handler checks the guard too.
    run.disabled = false;
    run.click();
    await vi.advanceTimersByTimeAsync(100);
  });
  const judged = api.validateNilearn.mock.calls.at(-1)?.[0] as Record<string, unknown> | undefined;
  const submitted = api.createNilearnJob.mock.calls.map((call) => call[0] as Record<string, unknown>);
  act(() => root.unmount());
  client.clear();
  container.remove();
  return { ...state, judged, submitted };
}

const refusedWith = (key: keyof typeof REFUSALS) => {
  api.validateNilearn.mockResolvedValue({ ok: false, errors: [REFUSALS[key]] });
  return `${REFUSALS[key].path}: ${REFUSALS[key].message}`;
};

describe("Nilearn visuals Run gate", () => {
  it("a valid config runs: Run is enabled and the click submits what was validated", async () => {
    const { disabled, title, judged, submitted } = await gate({});
    expect({ disabled, title }).toEqual({ disabled: false, title: null });
    expect(submitted).toHaveLength(1);
    expect(submitted[0]).toEqual(judged);
    expect(submitted[0]).toMatchObject({ subdir_name: "insula_group" });
  });

  it("a sub-directory that is not one folder is blocked with the server's sentence", async () => {
    const reason = refusedWith("subdir");
    const { disabled, title, judged, submitted } = await gate({ subdir: "../stats" });
    expect(judged).toMatchObject({ subdir_name: "../stats" });
    expect({ disabled, title }).toEqual({ disabled: true, title: reason });
    expect(submitted).toEqual([]);
  });

  it("a minimum cutoff above the maximum is blocked with the server's sentence", async () => {
    const reason = refusedWith("cutoffs");
    const { disabled, title, judged, submitted } = await gate({ minCutoff: 0.2, maxCutoff: 0.1 });
    expect(judged).toMatchObject({ min_cutoff: 0.2, max_cutoff: 0.1, use_percentiles: false });
    expect({ disabled, title }).toEqual({ disabled: true, title: reason });
    expect(submitted).toEqual([]);
  });

  it("the same subject and simulation twice is blocked with the server's sentence", async () => {
    const reason = refusedWith("duplicate");
    const { disabled, title, judged, submitted } = await gate({ pairs: [INSULA_101, { ...INSULA_101, id: "p3" }] });
    // Both rows reach the server: the panel neither drops nor merges the repeat on its own.
    expect(judged?.subject_simulation_pairs).toEqual([
      { subject_id: "101", simulation_name: "L_Insula" },
      { subject_id: "101", simulation_name: "L_Insula" },
    ]);
    expect({ disabled, title }).toEqual({ disabled: true, title: reason });
    expect(submitted).toEqual([]);
  });

  it("the page's own check still comes first: an empty sub-directory never reaches the server", async () => {
    const { disabled, title, submitted } = await gate({ subdir: "  " });
    expect({ disabled, title }).toEqual({ disabled: true, title: "Enter a sub-directory name for the output files." });
    expect(api.validateNilearn).not.toHaveBeenCalled();
    expect(submitted).toEqual([]);
  });
});

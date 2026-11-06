// @vitest-environment jsdom
/**
 * What Run does with a chosen network: a network this simulation cannot draw yet is assessed first
 * by a tract job the render waits for; one already assessed goes straight to the render; and a run
 * that would replace a bundle or a render asks before anything is queued.
 *
 * The panel is rendered for real with its API mocked; expectations are the wire bodies this file
 * authors from the request. Reproduce: cd desktop && npx vitest run tests/unit/visual-exporter-network-run.test.tsx
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

const PAIRS = [["Left-Thalamus-Proper", "lh.lingual"]];
const SELECTION = { name: "posterior_thalamocortical", kind: "edges", regions: ["Left-Thalamus-Proper"], pairs: PAIRS };
const outputs = vi.hoisted(() => ({ networks: [] as string[], assessed: [] as unknown[], has_edges: false, renders: [] as unknown[] }));
const plan = vi.hoisted(() => ({ overwrite: false }));

vi.mock("../../src/renderer/api/client", async (original) => ({ ...(await original<object>()), getSubjects: vi.fn(async () => [{ id: "101" }]) }));
vi.mock("../../src/renderer/pages/panels/visual-exporter/api", () => ({
  getSimulationsFor: vi.fn(async () => [{ name: "sim", path: "/p/sim" }]),
  getAtlasRegions: vi.fn(async () => []),
  getNiftiLabels: vi.fn(async () => []),
  getSimulationNetworks: vi.fn(async () => outputs),
  validateBlender: vi.fn(async () => ({ ok: true, errors: [] })),
  planBlender: vi.fn(async () => ({ jobs: [{ will_overwrite: plan.overwrite, exists: plan.overwrite, subject: "101", output_dir: "/o" }], lock_conflicts: [], cost: { cpus: 1, mem_gb: 1 }, warnings: [] })),
  createBlenderJob: vi.fn(async () => ({ id: "render" })),
  createTractJob: vi.fn(async () => ({ id: "assess" })),
  planTract: vi.fn(async () => ({ jobs: [] })),
  preflightTract: vi.fn(async () => []),
}));
vi.mock("../../src/renderer/pages/_shared/roi/tract", async (original) => ({
  ...(await original<object>()),
  getTractManifest: vi.fn(async () => ({ available: true, fingerprint: "f", atlas: "DK40", regions: [] })),
  getTractPresets: vi.fn(async () => [{ id: "posterior_thalamocortical", label: "P", seeds: [], same_side: true, pairs: PAIRS, n_edges: 1, n_streamlines: 7, opposite_pairs: [], n_opposite: 0, right_thalamus_to_left_cortex: 0, left_thalamus_to_right_cortex: 0, missing: [], reason: null }]),
  getTractEdges: vi.fn(async () => []),
}));
vi.mock("../../src/renderer/pages/panels/ExtensionRunPanel", () => ({
  ExtensionRunPanel: () => null,
  useExtensionJobs: () => ({ startedJobIds: [], pinnedJobId: null, setPinnedJobId: () => {}, trackJob: () => {} }),
}));
vi.mock("../../src/renderer/pages/panels/visual-exporter/ExportPreview", () => ({ ExportPreview: () => null }));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

import { clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";
import * as api from "../../src/renderer/pages/panels/visual-exporter/api";
import blenderPage from "../../src/renderer/pages/panels/visual-exporter/index";

const VALUE = { mode: "network", space: "subject", how: "preset", preset: "posterior_thalamocortical", presetSameSide: true, seeds: ["Left-Thalamus-Proper"], pairs: PAIRS, minN: 1, minCount: 1, name: "posterior_thalamocortical" };

async function press() {
  clearPageSession();
  for (const [key, value] of Object.entries({ mode: "networks", subjectId: "101", simulationName: "sim", networkValue: VALUE })) writeSession(sessionSlot("", key), value);
  vi.useFakeTimers();
  vi.mocked(api.createBlenderJob).mockClear();
  vi.mocked(api.createTractJob).mockClear();
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = (blenderPage as unknown as { Component: () => React.ReactElement }).Component;
  act(() => root.render(React.createElement(QueryClientProvider, { client }, React.createElement(Panel))));
  for (let turn = 0; turn < 6; turn += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
  }
  const button = container.querySelector<HTMLButtonElement>('[data-testid="run-button"]')!;
  await act(async () => {
    button.click();
    await vi.advanceTimersByTimeAsync(100);
  });
  const asked = !!document.querySelector('[data-testid="existing-outputs-replace"]');
  return {
    asked,
    replace: async () => {
      await act(async () => {
        document.querySelector<HTMLButtonElement>('[data-testid="existing-outputs-replace"]')!.click();
        await vi.advanceTimersByTimeAsync(100);
      });
    },
    done: () => {
      act(() => root.unmount());
      client.clear();
      container.remove();
    },
  };
}

afterEach(() => {
  vi.useRealTimers();
  outputs.networks = [];
  outputs.assessed = [];
  plan.overwrite = false;
});

describe("Run on a chosen network", () => {
  it("assesses a network this simulation cannot draw, and the render waits for that job", async () => {
    const run = await press();
    expect(vi.mocked(api.createTractJob).mock.calls).toEqual([
      [{ _type: "TractConfig", subject_id: "101", stages: ["assess"], assess: { simulations: ["sim"], selections: [SELECTION] } }, "101", false],
    ]);
    const [config, subjects, overwrite, after] = vi.mocked(api.createBlenderJob).mock.calls[0]!;
    expect(config).toMatchObject({ _type: "TractVisualConfig", selection: SELECTION, preset: "posterior_thalamocortical" });
    expect([subjects, overwrite, after]).toEqual([["101"], false, ["assess"]]);
    run.done();
  });

  it("goes straight to the render when its own bundle holds these edges", async () => {
    outputs.networks = ["posterior_thalamocortical"];
    outputs.assessed = [{ name: "posterior_thalamocortical", pairs: PAIRS, n_streamlines: 7 }];
    const run = await press();
    expect(api.createTractJob).not.toHaveBeenCalled();
    expect(vi.mocked(api.createBlenderJob).mock.calls[0]![3]).toEqual([]);
    run.done();
  });

  it("goes straight to the render when all.trx can be cut to it", async () => {
    outputs.networks = ["all"];
    const run = await press();
    expect(api.createTractJob).not.toHaveBeenCalled();
    expect(api.createBlenderJob).toHaveBeenCalledTimes(1);
    run.done();
  });

  it("a bundle of this name holding other edges is left alone: the selection takes a name of its own", async () => {
    outputs.networks = ["posterior_thalamocortical"];
    outputs.assessed = [{ name: "posterior_thalamocortical", pairs: [["a", "b"]], n_streamlines: 7 }];
    const run = await press();
    expect(run.asked).toBe(false);
    expect(vi.mocked(api.createTractJob).mock.calls[0]![0].assess!.selections![0]!.name).toBe("posterior_thalamocortical_2");
    expect(vi.mocked(api.createBlenderJob).mock.calls[0]!.slice(2)).toEqual([false, ["assess"]]);
    run.done();
  });

  it("reuses the assessed bundle that holds these edges, whatever it is called", async () => {
    outputs.networks = ["an_older_name"];
    outputs.assessed = [{ name: "an_older_name", pairs: PAIRS, n_streamlines: 7 }];
    const run = await press();
    expect(api.createTractJob).not.toHaveBeenCalled();
    expect(vi.mocked(api.createBlenderJob).mock.calls[0]![0]).toMatchObject({ selection: { name: "an_older_name" } });
    run.done();
  });

  it("asks before replacing its own bundle when the network was rebuilt under it, and queues nothing until Replace", async () => {
    outputs.networks = ["posterior_thalamocortical"];
    outputs.assessed = [{ name: "posterior_thalamocortical", pairs: PAIRS, n_streamlines: 6 }];
    const run = await press();
    expect(run.asked).toBe(true);
    expect(api.createTractJob).not.toHaveBeenCalled();
    expect(api.createBlenderJob).not.toHaveBeenCalled();
    await run.replace();
    expect(vi.mocked(api.createTractJob).mock.calls[0]![2]).toBe(true);
    run.done();
  });
});

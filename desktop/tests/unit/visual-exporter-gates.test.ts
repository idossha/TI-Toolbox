// @vitest-environment jsdom
/**
 * The 3D Visual Exporter refuses a montage export of a simulation with no recorded EEG net.
 *
 * What it pins (2026-10-22): a simulation placed by coordinates (free-hand, flex_free) records
 * `eeg_net: null` in its `documentation/config.json` — Dataset 000 `sub-101/20260919_131736_879_1`
 * is one. `tit.blender.montage_publication` refuses it ("This simulation has no recorded EEG
 * net."), and so does the server's preflight; before this the panel let Run queue the job and
 * only the preview said why it would fail. Now the Run button carries that sentence as its
 * reason and a click submits nothing, while the same simulation still exports regions and
 * vectors (neither reads a net), and a simulation with a recorded net still exports a montage.
 *
 * The same file pins the magnitude-scale percentile gate: `VectorConfig` refuses thresholds that
 * do not rise (blue ≤ green ≤ red), so the panel says so instead of queueing a refused job.
 *
 * Where the expectations come from: the recorded config is the Dataset 000 shape typed out
 * below; the sentence is the runner's (tit/blender/montage_publication.py), read here through
 * the panel's real `readExportMontage`. The panel is rendered for real with its API mocked.
 *
 * Reproduce: cd desktop && npx vitest run tests/unit/visual-exporter-gates.test.ts
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

const SIM_ROOT = "/project/derivatives/SimNIBS/sub-101/Simulations";
/** documentation/config.json of each simulation, as the simulator records it. */
const RECORDS: Record<string, unknown> = {
  "20260919_131736_879_1": {
    simulation_mode: "TI",
    montage_mode: "flex_free",
    eeg_net: null,
    electrode_pairs: [
      [
        [72.1, 10.5, -19.1],
        [75.6, 0.9, -24.3],
      ],
      [
        [-80.0, 19.2, -78.6],
        [-77.3, 30.0, -73.3],
      ],
    ],
    is_xyz_montage: true,
  },
  L_Insula: {
    simulation_mode: "TI",
    montage_mode: "net",
    eeg_net: "GSN-HydroCel-185.csv",
    electrode_pairs: [
      ["E010", "E011"],
      ["E012", "E013"],
    ],
  },
};

vi.mock("../../src/renderer/api/client", () => ({ getSubjects: vi.fn(async () => [{ id: "101" }]) }));
vi.mock("../../src/renderer/pages/panels/visual-exporter/api", () => ({
  getSimulationsFor: vi.fn(async () => Object.keys(RECORDS).map((name) => ({ name, path: `${SIM_ROOT}/${name}` }))),
  getAtlasRegions: vi.fn(async () => []),
  getNiftiLabels: vi.fn(async () => []),
  validateBlender: vi.fn(async () => ({ ok: true, errors: [] })),
  planBlender: vi.fn(async () => ({ jobs: [], lock_conflicts: [], cost: { cpus: 1, mem_gb: 1 }, warnings: [] })),
  createBlenderJob: vi.fn(async () => ({ id: "job" })),
}));
vi.mock("../../src/renderer/pages/results/api", () => ({
  getTextFile: vi.fn(async (path: string) => {
    const name = path.slice(SIM_ROOT.length + 1).split("/")[0] ?? "";
    return JSON.stringify(RECORDS[name]);
  }),
}));
vi.mock("../../src/renderer/pages/panels/ExtensionRunPanel", () => ({
  ExtensionRunPanel: () => null,
  useExtensionJobs: () => ({ startedJobIds: [], pinnedJobId: null, setPinnedJobId: () => {}, trackJob: () => {} }),
}));
vi.mock("../../src/renderer/pages/panels/visual-exporter/ExportPreview", () => ({ ExportPreview: () => null }));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

import { clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";
import * as blenderApi from "../../src/renderer/pages/panels/visual-exporter/api";
import * as resultsApi from "../../src/renderer/pages/results/api";
import blenderPage from "../../src/renderer/pages/panels/visual-exporter/index";

const NO_NET = "This simulation has no recorded EEG net.";

async function render(session: Record<string, unknown>) {
  clearPageSession();
  for (const [key, value] of Object.entries(session)) writeSession(sessionSlot("", key), value);
  vi.useFakeTimers();
  vi.mocked(blenderApi.createBlenderJob).mockClear();
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = (blenderPage as unknown as { Component: () => React.ReactElement }).Component;
  act(() => root.render(React.createElement(QueryClientProvider, { client }, React.createElement(Panel))));
  // Subjects, then simulations, then the simulation's record resolve one after another; each
  // step's render schedules the next, so the clock is advanced in turns (the panel's own
  // validate/plan debounce is 350 ms).
  for (let turn = 0; turn < 5; turn += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
  }
  const button = container.querySelector<HTMLButtonElement>('[data-testid="run-button"]');
  expect(button, "the panel renders its Run button").not.toBeNull();
  await act(async () => {
    button!.click();
    await vi.advanceTimersByTimeAsync(100);
  });
  const submitted = vi.mocked(blenderApi.createBlenderJob).mock.calls.map((call) => call[0]);
  const title = button!.getAttribute("title");
  act(() => root.unmount());
  client.clear();
  container.remove();
  return { title, submitted };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("visual exporter montage gate", () => {
  it("refuses a montage of a simulation placed by coordinates, with the runner's sentence", async () => {
    const { title, submitted } = await render({ mode: "montage", subjectId: "101", simulationName: "20260919_131736_879_1" });
    expect(vi.mocked(resultsApi.getTextFile)).toHaveBeenCalledWith(`${SIM_ROOT}/20260919_131736_879_1/documentation/config.json`);
    expect(title).toBe(NO_NET);
    expect(submitted).toEqual([]);
  });

  it("still exports that simulation's regions and vectors, which read no net", async () => {
    for (const mode of ["regions", "vectors"]) {
      const { title, submitted } = await render({ mode, subjectId: "101", simulationName: "20260919_131736_879_1" });
      expect(title, mode).toBeNull();
      expect(submitted.length, mode).toBe(mode === "regions" ? 2 : 1);
      expect(submitted.every((c) => (c as { simulation_name: string }).simulation_name === "20260919_131736_879_1")).toBe(true);
    }
  });

  it("refuses a magnitude-scale ramp whose percentiles do not rise, as VectorConfig does", async () => {
    const base = { mode: "vectors", subjectId: "101", simulationName: "L_Insula", color: "magscale" };
    const refused = await render({ ...base, bluePct: 90, greenPct: 50, redPct: 95 });
    expect(refused.title).toBe("Magnitude-scale percentiles must rise: blue ≤ green ≤ red.");
    expect(refused.submitted).toEqual([]);
    // Equal neighbours are a step, not a fall; RGB colouring reads no percentile.
    const step = await render({ ...base, bluePct: 50, greenPct: 50, redPct: 95 });
    expect(step.title).toBeNull();
    expect(step.submitted).toEqual([expect.objectContaining({ blue_percentile: 50, green_percentile: 50, red_percentile: 95 })]);
    const rgb = await render({ ...base, color: "rgb", bluePct: 90, greenPct: 50, redPct: 95 });
    expect(rgb.title).toBeNull();
    expect(rgb.submitted).toHaveLength(1);
  });

  it("runs a montage of a simulation that recorded its net", async () => {
    const { title, submitted } = await render({ mode: "montage", subjectId: "101", simulationName: "L_Insula" });
    expect(title).toBeNull();
    expect(submitted).toHaveLength(1);
    expect(submitted[0]).toMatchObject({ _type: "MontageConfig", subject_id: "101", simulation_name: "L_Insula" });
  });
});

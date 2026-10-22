// @vitest-environment jsdom
/**
 * What a run page says it will run equals what it validates and submits (p19, 2026-10-22; the
 * rule `planModel.ts::jobCountLabel` states: the digest never claims a different count than Run
 * submits).
 *
 * Pins:
 *  - the Analyzer's Jobs summary counts JOBS (one per sphere; one per region when uncombined —
 *    `rowTargets`, from `AnalyzerConfig.center` being one point) — it read "1 analysis job" over a
 *    row Run queues as 2;
 *  - the Optimizer validates EVERY config before queueing (it validated one per kind and read a
 *    failed validate request as "valid");
 *  - the Analyzer's batch plan merges like every other page (`mergePlanResults`: CPUs and memory
 *    are one job's, the ETA is the batch's) — it summed CPUs and memory and dropped the ETA;
 *  - the Simulator draws no plan grid, and its digest counts nothing, until every row's plan has
 *    answered — a grid of the rows that happened to answer first said "1 job" over two rows.
 *
 * Expected counts are hand-counted from each fixture's targets; costs are hand-computed (max,
 * max, sum). Reproduce: `cd desktop && npx vitest run tests/unit/run-counts.test.ts`.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { analyzerJobsSummary, emptyAnalyzerRow, type AnalyzerRow } from "../../src/renderer/pages/analyzer/JobRows";
import { planAnalyzerBatch } from "../../src/renderer/pages/analyzer/api";
import { validateJobs } from "../../src/renderer/pages/optimizer/plan";
import { jobCountLabel } from "../../src/renderer/pages/_shared/run/planModel";
import type { RoiValue } from "../../src/renderer/pages/_shared/roi";

const sim = vi.hoisted(() => ({ planSim: vi.fn() }));
vi.mock("../../src/renderer/pages/simulator/api", async (original) => ({ ...(await original<object>()), planSim: sim.planSim }));
vi.mock("../../src/renderer/pages/simulator/buildConfig", async (original) => ({
  ...(await original<object>()),
  buildMontageSources: () => undefined,
  buildSimulationConfig: (row: { subjectId: string; name: string }) => ({ subject_id: row.subjectId, name: row.name }),
}));
const { useSimPlan } = await import("../../src/renderer/pages/simulator/RunControls");

const sphere = (x: number) => ({ x, y: -18, z: 9, radius: 5 });
const row = (subjectId: string, roi: RoiValue, combine = true): AnalyzerRow =>
  emptyAnalyzerRow({ subjectId, simulation: "Thalamus", roi, combine });

describe("Analyzer Jobs summary counts the jobs Run queues", () => {
  it("one row with two spheres is two analysis jobs", () => {
    const roi: RoiValue = { mode: "spherical", space: "mni", volumetric: false, tissues: "GM", spheres: [sphere(-10), sphere(10)] };
    expect(analyzerJobsSummary([row("ernie", roi)], false)).toBe("2 analysis jobs · 1 subject");
  });

  it("two uncombined regions are two jobs, combined they are one", () => {
    const roi: RoiValue = {
      mode: "cortical",
      space: "subject",
      atlas: "DK40",
      regions: [
        { id: 1, name: "bankssts", hemi: "lh" },
        { id: 2, name: "insula", hemi: "lh" },
      ],
    };
    expect(analyzerJobsSummary([row("ernie", roi, false)], false)).toBe("2 analysis jobs · 1 subject");
    expect(analyzerJobsSummary([row("ernie", roi, true)], false)).toBe("1 analysis job · 1 subject");
    // Rows add up: 2 + 1 jobs over two subjects.
    expect(analyzerJobsSummary([row("ernie", roi, false), row("101", roi, true)], false)).toBe("3 analysis jobs · 2 subjects");
  });

  it("a cohort run is the lead row's targets, each over the whole cohort", () => {
    const two: RoiValue = { mode: "spherical", space: "mni", volumetric: false, tissues: "GM", spheres: [sphere(-10), sphere(10)] };
    expect(analyzerJobsSummary([row("ernie", two), row("101", two)], true)).toBe("2 group analyses over 2 subjects");
    const one: RoiValue = { ...two, spheres: [sphere(-10)] };
    expect(analyzerJobsSummary([row("ernie", one), row("101", one)], true)).toBe("one group analysis over 2 subjects");
  });
});

describe("Optimizer validates every job before queueing any", () => {
  const job = (label: string, radius: number) => ({ kind: "ex", label, config: { roi_radius: radius } });

  it("validates all three jobs and names the invalid second one", async () => {
    const validate = vi.fn(async (_kind: string, config: unknown) =>
      (config as { roi_radius: number }).roi_radius > 0
        ? { ok: true, errors: [] }
        : { ok: false, errors: [{ path: "roi_radius", message: "must be > 0" }] },
    );
    const problems = await validateJobs([job("Job 1", 3), job("Job 2", 0), job("Job 3", 3)], validate as never);
    expect(validate).toHaveBeenCalledTimes(3);
    expect(validate.mock.calls.map((c) => (c[1] as { roi_radius: number }).roi_radius)).toEqual([3, 0, 3]);
    expect(problems).toEqual(["Job 2 · ex: roi_radius: must be > 0"]);
  });

  it("blocks when the validate request itself fails, instead of reading it as valid", async () => {
    const validate = vi.fn(async (_kind: string, config: unknown) => {
      if ((config as { roi_radius: number }).roi_radius === 4) throw new TypeError("Failed to fetch");
      return { ok: true, errors: [] };
    });
    const problems = await validateJobs([job("Job 1", 3), job("Job 2", 4)], validate as never);
    expect(problems).toEqual(["Job 2 · ex: could not be validated (Failed to fetch)"]);
  });

  it("returns nothing when every job is valid", async () => {
    expect(await validateJobs([job("Job 1", 3)], async () => ({ ok: true, errors: [] }) as never)).toEqual([]);
  });
});

describe("Analyzer batch plan merges like every other page", () => {
  it("takes one job's CPUs and memory (max) and the whole batch's ETA (sum)", async () => {
    const costs = [
      { cpus: 2, mem_gb: 6, eta_minutes: 3 },
      { cpus: 4, mem_gb: 2, eta_minutes: 5 },
    ];
    let i = 0;
    const client = {
      POST: async () => ({
        data: { jobs: [], lock_conflicts: [], cost: { ...costs[i++]!, system: null }, warnings: [], resolved: null },
        response: new Response(null, { status: 200 }),
      }),
    };
    const spec = { config: {} as never, subjectIds: ["ernie"] };
    const merged = await planAnalyzerBatch([spec, spec], false, client as never);
    expect(merged.cost.cpus).toBe(4);
    expect(merged.cost.mem_gb).toBe(6);
    expect(merged.cost.eta_minutes).toBe(8);
  });
});

describe("Simulator digest counts every row or nothing", () => {
  let container: HTMLDivElement;
  let root: Root;
  let client: QueryClient;
  let captured: ReturnType<typeof useSimPlan> | null;

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    sim.planSim.mockReset();
    captured = null;
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

  function Harness({ rows }: { rows: { id: string; subjectId: string; name: string; source: "montage" }[] }) {
    captured = useSimPlan(rows as never, {} as never, ["ernie"]);
    return null;
  }

  const answer = (name: string) => ({
    jobs: [{ kind: "sim", subject: "ernie", output_dir: `/p/sub-ernie/Simulations/${name}`, exists: false, will_overwrite: false }],
    lock_conflicts: [],
    cost: { cpus: 1, mem_gb: 1, eta_minutes: 1, system: null },
    warnings: [],
    resolved: null,
  });

  async function render(rows: { id: string; subjectId: string; name: string; source: "montage" }[]) {
    act(() => root.render(createElement(QueryClientProvider, { client }, createElement(Harness, { rows }))));
    for (let k = 0; k < 4; k += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
    }
  }

  const rows = [
    { id: "a", subjectId: "ernie", name: "M1", source: "montage" as const },
    { id: "b", subjectId: "ernie", name: "M2", source: "montage" as const },
  ];

  it("shows no plan while one of two rows has not answered", async () => {
    sim.planSim.mockImplementation((config: { name: string }) => (config.name === "M2" ? new Promise(() => {}) : Promise.resolve(answer(config.name))));
    await render(rows);
    expect(sim.planSim).toHaveBeenCalledTimes(2);
    expect(captured?.model).toBeNull();
    expect(captured?.blockedReason).toBeNull();
  });

  it("counts both rows once both have answered", async () => {
    sim.planSim.mockImplementation((config: { name: string }) => Promise.resolve(answer(config.name)));
    await render(rows);
    expect(jobCountLabel(captured?.model ?? null)).toBe("2 jobs");
  });
});

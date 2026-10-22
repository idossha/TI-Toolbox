// @vitest-environment jsdom
/**
 * A flex job mapped onto a net that moved an electrode more than 20 mm says so, under the job.
 *
 * Why (package p24, audit_flex.md "mapping snap is unbounded and invisible", 2026-10-22): mapping
 * a flex result onto a net snaps each optimised electrode to the nearest free site. On Dataset 000
 * that moved electrodes up to 52 mm (BioSemi-128, sub-101) and 63.6 mm (BioSemi-64, CHN) with
 * nothing on screen, so the simulated montage was not the optimised one. The catalog now carries
 * each mapping's `max_snap_mm` (`tit.catalog.read_flex_mapping`); the Simulator warns above
 * `SNAP_WARN_MM` = 20 mm, the threshold the task set (about one inter-electrode spacing of a dense
 * net). Expected numbers are hand values around that threshold, not read from the code.
 *
 * The table is rendered for real; only the HTTP layer and Radix's portal Select are replaced, as in
 * montage-validity.test.tsx.
 */
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const NET = "BioSemi-128-A1.csv";
const api = vi.hoisted(() => ({
  getMontages: vi.fn(async () => ({ nets: {} })),
  getEegNets: vi.fn(async () => [{ name: "BioSemi-128-A1.csv", electrodes: ["A1", "A2", "B1", "B2", "C1"], n: 5 }]),
  getFlexRuns: vi.fn(async (): Promise<unknown[]> => []),
  getFreehand: vi.fn(async () => []),
  getFlexMapping: vi.fn(async (): Promise<unknown> => ({ pairs: [] })),
  getCandidateMapping: vi.fn(async () => ({ pairs: [] })),
  putMontage: vi.fn(async () => []),
  deleteMontage: vi.fn(async () => undefined),
  deleteFreehand: vi.fn(async () => undefined),
  putFreehand: vi.fn(async () => undefined),
}));
vi.mock("../../src/renderer/pages/simulator/api", () => api);
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), blocked: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock("../../src/renderer/ui/Toast", () => ({ notify: toast, notifySubmitError: vi.fn() }));
vi.mock("../../src/renderer/ui/Select", () => ({
  Select: ({ value, onValueChange, options, "aria-label": label, disabled }: { value?: string; onValueChange: (v: string) => void; options: { value: string; label: string }[]; "aria-label"?: string; disabled?: boolean }) => (
    <select aria-label={label} value={value ?? ""} disabled={disabled} onChange={(e) => onValueChange(e.target.value)}>
      <option value="" />
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { PageIdContext, clearPageSession } from "../../src/renderer/app/pageSession";
import { JobsTable } from "../../src/renderer/pages/simulator/MontageManager";
import { FreehandDraftProvider } from "../../src/renderer/pages/simulator/freehandDraft";
import { FlexSnapWarning, OPTIMIZED, SNAP_WARN_MM, placementsFor, snapWarning, type FlexPlacement } from "../../src/renderer/pages/simulator/FlexTab";
import { candidateRow, snapCandidateRow } from "../../src/renderer/pages/simulator/candidateHandoff";
import type { FlexRun } from "../../src/renderer/pages/simulator/api";
import type { SelectedRow } from "../../src/renderer/pages/simulator/types";

type Xyz = [number, number, number];
const OPTIMISED_XYZ: [Xyz, Xyz][] = [
  [[60, 10, 40], [-60, 10, 40]],
  [[0, 70, 30], [0, -70, 30]],
];
const PAIRS: [string, string][] = [["A1", "B1"], ["A2", "B2"]];

function flexRun(mappings: unknown[]): FlexRun {
  return { name: "flexrun", path: "/p", goal: "mean", roi: {}, created: "", manifest: { current_mA: 1 }, mappings, optimized: OPTIMISED_XYZ, artifacts: [] } as unknown as FlexRun;
}

const mapped = (maxSnapMm?: number): FlexPlacement => ({ value: NET, label: "BioSemi-128-A1", pairs: PAIRS, ...(maxSnapMm === undefined ? {} : { maxSnapMm }) });

describe("snap distance on a mapped placement", () => {
  it("the threshold is the 20 mm the task set", () => {
    expect(SNAP_WARN_MM).toBe(20);
  });

  it("placementsFor carries the catalog's max_snap_mm, and leaves an unknown one out", () => {
    const run = flexRun([
      { eeg_net: NET, pairs: PAIRS, max_snap_mm: 52.04 },
      { eeg_net: "GSN-HydroCel-185.csv", pairs: PAIRS },
      { eeg_net: "EEG10-10_UI_Jurak_2007.csv", pairs: PAIRS, max_snap_mm: null },
      { eeg_net: "EEG10-20_Okamoto_2004.csv", pairs: PAIRS, max_snap_mm: Number.NaN },
    ]);
    const options = placementsFor(run);
    expect(options.map((o) => [o.value, o.maxSnapMm])).toEqual([
      [NET, 52.04],
      ["GSN-HydroCel-185.csv", undefined],
      ["EEG10-10_UI_Jurak_2007.csv", undefined],
      ["EEG10-20_Okamoto_2004.csv", undefined],
      [OPTIMIZED, undefined],
    ]);
  });

  it("warns only above 20 mm at the 0.1 mm it prints, naming the net and the distance", () => {
    expect(snapWarning(mapped(20))).toBeNull();
    expect(snapWarning(mapped(19.99))).toBeNull();
    // 20.04 mm prints as 20.0 mm, which is not more than 20 mm: no self-contradicting sentence.
    expect(snapWarning(mapped(20.04))).toBeNull();
    expect(snapWarning(mapped(undefined))).toBeNull();
    expect(snapWarning(undefined)).toBeNull();
    expect(snapWarning(mapped(20.06))).toMatch(/ moves an electrode 20\.1 mm .*\(more than 20 mm\)/);
    expect(snapWarning(mapped(20.4))).toBe(
      "Mapping onto BioSemi-128-A1 moves an electrode 20.4 mm from where the optimiser put it (more than 20 mm), so this is not the optimised montage. Simulate the optimised positions, or map onto a denser net.",
    );
    expect(snapWarning(mapped(63.6))).toMatch(/^Mapping onto BioSemi-128-A1 moves an electrode 63\.6 mm /);
    expect(snapWarning(mapped(52.04))).toMatch(/^Mapping onto BioSemi-128-A1 moves an electrode 52\.0 mm /);
    // The optimised placement moves nothing.
    expect(snapWarning({ value: OPTIMIZED, label: "Optimised positions (XYZ)", xyzPairs: OPTIMISED_XYZ, maxSnapMm: 99 })).toBeNull();
  });
});

describe("the Simulator's flex job shows the warning", () => {
  let container: HTMLDivElement;
  let root: Root;
  let queryClient: QueryClient;

  beforeEach(() => {
    clearPageSession();
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    queryClient.clear();
    container.remove();
  });

  async function flush() {
    for (let i = 0; i < 8; i += 1) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  }

  function renderTable(rows: SelectedRow[], onRowsChange: (next: SelectedRow[]) => void = () => {}) {
    act(() =>
      root.render(
        <QueryClientProvider client={queryClient}>
          <PageIdContext.Provider value="simulator">
            <FreehandDraftProvider>
              <JobsTable subjects={[{ id: "ernie" }]} subjectNets={{ ernie: [NET] }} rows={rows} onRowsChange={onRowsChange} draft={null} onDraftChange={() => {}} />
            </FreehandDraftProvider>
          </PageIdContext.Provider>
        </QueryClientProvider>,
      ),
    );
  }
  const warning = () => container.querySelector("[data-testid='flex-snap-warning']");
  const flexRow = (seed: Partial<SelectedRow>): SelectedRow => ({ id: "r1", subjectId: "ernie", source: "flex", name: "flexrun", currents: "1,1", ...seed });

  it("a job mapped with a 52 mm snap shows it; 12 mm and the optimised placement do not", async () => {
    api.getFlexRuns.mockResolvedValue([flexRun([{ eeg_net: NET, pairs: PAIRS, max_snap_mm: 52.0 }])]);
    renderTable([flexRow({ eegNet: NET, pairs: PAIRS })]);
    await flush();
    expect(warning()?.textContent).toMatch(/^Mapping onto BioSemi-128-A1 moves an electrode 52\.0 mm /);

    renderTable([flexRow({ eegNet: undefined, xyzPairs: OPTIMISED_XYZ })]);
    await flush();
    expect(warning()).toBeNull();

    queryClient.clear();
    api.getFlexRuns.mockResolvedValue([flexRun([{ eeg_net: NET, pairs: PAIRS, max_snap_mm: 12.0 }])]);
    renderTable([flexRow({ eegNet: NET, pairs: PAIRS })]);
    await flush();
    expect(api.getFlexRuns).toHaveBeenCalled();
    expect(warning()).toBeNull();
  });

  it("the warning finds the run's mapping whether the net is named with .csv or without, and no other net's", async () => {
    const run = flexRun([{ eeg_net: NET, pairs: PAIRS, max_snap_mm: 52.0 }]);
    const shown = (r: FlexRun, net: string) => {
      act(() => root.render(<FlexSnapWarning run={r} net={net} />));
      return warning()?.textContent ?? null;
    };
    expect(shown(run, "BioSemi-128-A1")).toMatch(/^Mapping onto BioSemi-128-A1 moves an electrode 52\.0 mm /);
    expect(shown(run, NET)).toMatch(/^Mapping onto BioSemi-128-A1 moves an electrode 52\.0 mm /);
    // A run whose mapping file named the net by its stem, a job naming the cap file.
    const stemRun = flexRun([{ eeg_net: "BioSemi-128-A1", pairs: PAIRS, max_snap_mm: 52.0 }]);
    expect(shown(stemRun, NET)).toMatch(/^Mapping onto BioSemi-128-A1 moves an electrode 52\.0 mm /);
    // Another net of the same run: its own mapping (12 mm), not the 52 mm one.
    const two = flexRun([
      { eeg_net: NET, pairs: PAIRS, max_snap_mm: 52.0 },
      { eeg_net: "GSN-HydroCel-185.csv", pairs: PAIRS, max_snap_mm: 12.0 },
    ]);
    expect(shown(two, "GSN-HydroCel-185.csv")).toBeNull();
    expect(shown(run, "BioSemi-64.csv")).toBeNull();
  });

  it("a snapped optimiser candidate gets no warning from its run's winner mapping", async () => {
    // "Use in Simulator" on a flex candidate: a flex row carrying `candidate`, snapped to NET. Its
    // montage is named after the run, so the job finds the run, whose NET mapping (the winner's,
    // not this candidate's) moved an electrode 52 mm. That number says nothing about the candidate.
    api.getFlexRuns.mockResolvedValue([flexRun([{ eeg_net: NET, pairs: PAIRS, max_snap_mm: 52.0 }])]);
    const handoff = {
      id: "3",
      subject: "ernie",
      run: "derivatives/SimNIBS/sub-ernie/flex-search/flexrun",
      config: { subject_id: "ernie", montages: [{ name: "flexrun", electrode_pairs: OPTIMISED_XYZ }], intensities: [1, -1] },
    };
    const row = snapCandidateRow(candidateRow(handoff), NET, PAIRS);
    expect([row.source, row.name, row.eegNet, row.pairs, !!row.candidate]).toEqual(["flex", "flexrun", NET, PAIRS, true]);
    renderTable([row]);
    await flush();
    expect(api.getFlexRuns).toHaveBeenCalled();
    expect(container.querySelector("[data-job-detail]")?.textContent).toContain("A1");
    expect(warning()).toBeNull();
  });

  it("mapping a run onto a new net shows the snap once the run's mappings come back", async () => {
    // Before: the run was never mapped. After the server maps it, the flex-runs list it refetches
    // carries the new mapping and its snap.
    api.getFlexRuns.mockResolvedValueOnce([flexRun([])]);
    api.getFlexRuns.mockResolvedValue([flexRun([{ eeg_net: NET, pairs: PAIRS, max_snap_mm: 63.6 }])]);
    api.getFlexMapping.mockResolvedValue({ eeg_net: NET, pairs: PAIRS });
    let latest: SelectedRow[] = [flexRow({ eegNet: undefined, xyzPairs: OPTIMISED_XYZ })];
    const onRowsChange = (next: SelectedRow[]) => {
      latest = next;
      renderTable(next, onRowsChange);
    };
    renderTable(latest, onRowsChange);
    await flush();
    expect(warning()).toBeNull();

    await act(async () => {
      const select = container.querySelector<HTMLSelectElement>("select[aria-label='Placement']")!;
      select.value = NET;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();
    expect(api.getFlexMapping).toHaveBeenCalledWith("ernie", "flexrun", NET);
    expect(latest[0]!.pairs).toEqual(PAIRS);
    expect(warning()?.textContent).toMatch(/^Mapping onto BioSemi-128-A1 moves an electrode 63\.6 mm .*more than 20 mm/);
  });
});

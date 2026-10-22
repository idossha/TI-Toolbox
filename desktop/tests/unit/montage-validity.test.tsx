// @vitest-environment jsdom
/**
 * No montage with a repeated, unplaced or coincident electrode — or a name the server refuses —
 * can be saved or run from the Simulator.
 *
 * Expected behaviour is physical and the server's: an electrode cannot be its own return
 * (`["E1","E1"]`), two channels on one electrode short each other (`E1–E2 · E1–E3`), a free-hand
 * row never placed sits at the origin (inside the head), and `tit.catalog.put_montage` /
 * `put_freehand_config` hold a new name to `is_safe_name` (`tests/fixtures/entity_names.json`).
 * The editors are rendered for real; only the HTTP layer and Radix's portal Select are replaced.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const NET = "GSN-HydroCel-185.csv";
const api = vi.hoisted(() => ({
  getMontages: vi.fn(async () => ({ nets: { "GSN-HydroCel-185.csv": { uni_polar: {}, multi_polar: {} } } })),
  getEegNets: vi.fn(async () => [{ name: "GSN-HydroCel-185.csv", electrodes: ["E1", "E2", "E3", "E4", "E5"], n: 5 }]),
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
// Radix's Select renders its options in a portal jsdom cannot open; a native <select> with the
// same props is the same control for a test that only needs to pick an option.
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
import { JobsTable, montageDraftProblem, type MontageDraft } from "../../src/renderer/pages/simulator/MontageManager";
import { FreehandEditor, freehandPlacementProblem } from "../../src/renderer/pages/simulator/FreehandEditor";
import { FreehandDraftProvider } from "../../src/renderer/pages/simulator/freehandDraft";
import { coincidentElectrodes, isRunnableRow, repeatedElectrodes, rowProblem, type SelectedRow } from "../../src/renderer/pages/simulator/types";

type Xyz = [number, number, number];
const row = (seed: Partial<SelectedRow>): SelectedRow => ({ id: "r1", subjectId: "ernie", source: "montage", kind: "uni_polar", eegNet: NET, name: "M", currents: "", ...seed });

describe("repeated and coincident electrodes", () => {
  it("finds a label used twice, within a pair or across two channels", () => {
    expect(repeatedElectrodes([["E1", "E1"], ["E2", "E3"]])).toEqual(["E1"]);
    expect(repeatedElectrodes([["E1", "E2"], ["E1", "E3"]])).toEqual(["E1"]);
    expect(repeatedElectrodes([["E3", "E2"], ["E1", "E3"], ["E2", "E4"], ["E5", "E6"]])).toEqual(["E2", "E3"]);
    expect(repeatedElectrodes([["E1", "E2"], ["E3", "E4"]])).toEqual([]);
    // An unpicked slot is not an electrode.
    expect(repeatedElectrodes([["", ""], ["E1", ""]])).toEqual([]);
  });

  it("finds XYZ electrodes less than 1 mm apart, numbered in pair order", () => {
    const a: Xyz = [60, 10, 40];
    expect(coincidentElectrodes([[a, [60, 10, 40.5]], [[-60, 0, 0], [0, 70, 30]]])).toEqual([[1, 2]]);
    expect(coincidentElectrodes([[a, [0, 70, 30]], [[-60, 0, 0], [60.6, 10.6, 40]]])).toEqual([[1, 4]]);
    // 1 mm exactly is two places; just under it is one.
    expect(coincidentElectrodes([[a, [60, 10, 41]], [[-60, 0, 0], [0, 70, 30]]])).toEqual([]);
    expect(coincidentElectrodes([[a, [60, 10, 40.99]], [[-60, 0, 0], [0, 70, 30]]])).toEqual([[1, 2]]);
  });

  it("a montage row that repeats an electrode is not runnable, and the row says which", () => {
    for (const pairs of [[["E1", "E1"], ["E2", "E3"]], [["E1", "E2"], ["E1", "E3"]]] as [string, string][][]) {
      expect(isRunnableRow(row({ pairs })), JSON.stringify(pairs)).toBe(false);
      expect(rowProblem(row({ pairs }))).toBe("E1 is used more than once: an electrode cannot be its own return, and two channels cannot share one.");
    }
    expect(isRunnableRow(row({ pairs: [["E1", "E2"], ["E3", "E4"]] }))).toBe(true);
    // A flex run mapped onto a cap is judged by its labels too.
    expect(isRunnableRow(row({ source: "flex", kind: undefined, pairs: [["E7", "E9"], ["E9", "E8"]] }))).toBe(false);
  });

  it("a free-hand or flex XYZ row with two electrodes on one spot, or a NaN coordinate, is not runnable", () => {
    const pairs: [Xyz, Xyz][] = [[[60, 10, 40], [-60, 10, 40]], [[0, 70, 30], [60.2, 10.1, 40.3]]];
    for (const source of ["freehand", "flex"] as const) {
      const r = row({ source, kind: undefined, eegNet: undefined, pairs: undefined, xyzPairs: pairs });
      expect(isRunnableRow(r), source).toBe(false);
      expect(rowProblem(r)).toBe("Electrodes 1 and 4 are less than 1 mm apart: each electrode needs its own place on the scalp.");
    }
    const nan = row({ source: "freehand", kind: undefined, eegNet: undefined, xyzPairs: [[[60, 10, 40], [-60, 10, 40]], [[0, 70, Number.NaN], [0, -70, 30]]] });
    expect(rowProblem(nan)).toBe("Electrode 3 has a coordinate that is not a number.");
    expect(isRunnableRow({ ...nan, xyzPairs: [[[60, 10, 40], [-60, 10, 40]], [[0, 70, 30], [0, -70, 30]]] })).toBe(true);
  });
});

describe("the montage editor refuses what the server or physics refuses", () => {
  it("names the first reason a draft cannot be saved", () => {
    const ok: MontageDraft = { name: "F3_F4", pairs: [["E1", "E2"], ["E3", "E4"]] };
    expect(montageDraftProblem(ok)).toBeNull();
    expect(montageDraftProblem({ ...ok, pairs: [["E1", "E1"], ["E2", "E3"]] })).toMatch(/^E1 is used more than once/);
    expect(montageDraftProblem({ ...ok, pairs: [["E1", "E2"], ["E1", "E3"]] })).toMatch(/^E1 is used more than once/);
    expect(montageDraftProblem({ ...ok, name: "Thalamus (L)" })).toBe("A montage name may use letters, digits, '_' and '-' only, at most 64 characters.");
    // NAME_RE allows a space or a dot in a path component, but a saved montage is held to is_safe_name.
    expect(montageDraftProblem({ ...ok, name: "run 2" })).toMatch(/^A montage name may use/);
    expect(montageDraftProblem({ ...ok, name: "L.Insula" })).toMatch(/^A montage name may use/);
    expect(montageDraftProblem({ ...ok, name: "  " })).toBe("Name the montage.");
    expect(montageDraftProblem({ ...ok, pairs: [["E1", "E2"], ["E3", ""]] })).toBe("Pick both electrodes of every pair.");
    expect(montageDraftProblem({ ...ok, pairs: [["E1", "E2"], ["E3", "E4"], ["E5", "E6"]] })).toMatch(/^Use exactly 2 pairs/);
  });
});

describe("rendered editors", () => {
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
    for (let i = 0; i < 6; i += 1) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  }

  function renderTable(rows: SelectedRow[], draft: MontageDraft | null, onRowsChange: (next: SelectedRow[]) => void = () => {}) {
    act(() =>
      root.render(
        <QueryClientProvider client={queryClient}>
          <PageIdContext.Provider value="simulator">
            <FreehandDraftProvider>
              <JobsTable subjects={[{ id: "ernie" }]} subjectNets={{ ernie: [NET] }} rows={rows} onRowsChange={onRowsChange} draft={draft} onDraftChange={() => {}} />
            </FreehandDraftProvider>
          </PageIdContext.Provider>
        </QueryClientProvider>,
      ),
    );
  }
  const button = (text: string) => [...container.querySelectorAll("button")].find((b) => b.textContent === text) as HTMLButtonElement;

  it("Save montage is refused for a repeated electrode, with the reason shown, and saves a distinct one", async () => {
    renderTable([], { name: "M1", pairs: [["E1", "E1"], ["E2", "E3"]] });
    await flush();
    expect(button("Save montage").disabled).toBe(true);
    expect(button("Save montage").title).toMatch(/^E1 is used more than once/);
    expect(container.querySelector("[data-testid='montage-repeated-electrodes']")?.textContent).toMatch(/^E1 is used more than once/);

    renderTable([], { name: "M1", pairs: [["E1", "E2"], ["E1", "E3"]] });
    await flush();
    expect(button("Save montage").disabled).toBe(true);

    renderTable([], { name: "M1", pairs: [["E1", "E2"], ["E3", "E4"]] });
    await flush();
    expect(container.querySelector("[data-testid='montage-repeated-electrodes']")).toBeNull();
    expect(button("Save montage").disabled).toBe(false);
    await act(async () => button("Save montage").click());
    expect(api.putMontage).toHaveBeenCalledWith(NET, "uni_polar", "M1", [["E1", "E2"], ["E3", "E4"]]);
  });

  it("Save montage is refused for a name the catalog would refuse, with the rule shown", async () => {
    renderTable([], { name: "Thalamus (L)", pairs: [["E1", "E2"], ["E3", "E4"]] });
    await flush();
    expect(button("Save montage").disabled).toBe(true);
    expect(container.querySelector("[data-testid='montage-name-error']")?.textContent).toBe("A montage name may use letters, digits, '_' and '-' only, at most 64 characters.");
    await act(async () => button("Save montage").click());
    expect(api.putMontage).not.toHaveBeenCalled();
  });

  it("a hand-written 3-pair montage row is shown as not runnable, with the reason on its line", async () => {
    renderTable([row({ kind: "multi_polar", pairs: [["E1", "E2"], ["E3", "E4"], ["E5", "E6"]], currents: "1,1,1" })], null);
    await flush();
    expect(container.querySelector("[data-job-row='r1']")?.getAttribute("data-runnable")).toBe("false");
    expect(container.querySelector("[data-testid='job-row-problem']")?.textContent).toBe("3 electrode pairs: a montage needs 2 pairs (TI) or an even number from 4 (mTI).");
  });

  it("the channel inputs show the currents the job sends: blank is 1.0 mA, one input per channel", async () => {
    renderTable([row({ kind: "multi_polar", pairs: [["E1", "E2"], ["E3", "E4"], ["E5", "E6"], ["E7", "E8"]], currents: "2.5," })], null);
    await flush();
    const inputs = [...container.querySelectorAll<HTMLInputElement>("[data-job-detail='r1'] input")];
    expect(inputs.map((i) => Number(i.value))).toEqual([2.5, 1, 1, 1]);
    expect(container.querySelector("[data-testid='job-row-problem']")).toBeNull();
  });

  it("a flex mapping that puts two electrodes on one label is refused with a notice, leaving the row unrunnable", async () => {
    const optimized = [[[60, 10, 40], [-60, 10, 40]], [[0, 70, 30], [0, -70, 30]]];
    api.getFlexRuns.mockResolvedValue([{ name: "flexrun", path: "/p", goal: "mean", roi: {}, created: "", manifest: { current_mA: 1 }, mappings: [], optimized, artifacts: [] }]);
    api.getFlexMapping.mockResolvedValue({ pairs: [["E1", "E2"], ["E1", "E3"]] });
    const flexRow = row({ source: "flex", kind: undefined, eegNet: undefined, name: "flexrun", xyzPairs: optimized as SelectedRow["xyzPairs"], currents: "1,1" });
    let latest: SelectedRow[] = [flexRow];
    const onRowsChange = (next: SelectedRow[]) => {
      latest = next;
      renderTable(next, null, onRowsChange);
    };
    renderTable(latest, null, onRowsChange);
    await flush();
    const placement = container.querySelector<HTMLSelectElement>("select[aria-label='Placement']")!;
    await act(async () => {
      placement.value = NET;
      placement.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();
    expect(api.getFlexMapping).toHaveBeenCalledWith("ernie", "flexrun", NET);
    expect(toast.error).toHaveBeenCalledWith(`Could not map flexrun onto ${NET}.`, "E1 is used more than once: an electrode cannot be its own return, and two channels cannot share one.");
    expect(latest[0]!.eegNet).toBe(NET);
    expect(latest[0]!.pairs).toBeUndefined();
    expect(isRunnableRow(latest[0]!)).toBe(false);

    // A mapping onto distinct labels lands on the row, which then runs.
    api.getFlexMapping.mockResolvedValue({ pairs: [["E1", "E2"], ["E3", "E4"]] });
    queryClient.removeQueries({ queryKey: ["flex-mapping"] });
    latest = [flexRow];
    renderTable(latest, null, onRowsChange);
    await flush();
    await act(async () => {
      const select = container.querySelector<HTMLSelectElement>("select[aria-label='Placement']")!;
      select.value = NET;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();
    expect(latest[0]!.pairs).toEqual([["E1", "E2"], ["E3", "E4"]]);
    expect(isRunnableRow(latest[0]!)).toBe(true);
  });

  function renderFreehand() {
    act(() =>
      root.render(
        <QueryClientProvider client={queryClient}>
          <PageIdContext.Provider value="simulator">
            <FreehandDraftProvider>
              <FreehandEditor subjects={["ernie"]} onClose={() => {}} />
            </FreehandDraftProvider>
          </PageIdContext.Provider>
        </QueryClientProvider>,
      ),
    );
  }
  function fill(selector: string, value: string) {
    const target = container.querySelector<HTMLInputElement>(selector)!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(target, value);
      target.dispatchEvent(new Event("input", { bubbles: true }));
      target.dispatchEvent(new Event("change", { bubbles: true }));
      target.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
  }
  function place(i: number, [x, y, z]: Xyz) {
    fill(`[aria-label="Position ${i} X"]`, String(x));
    fill(`[aria-label="Position ${i} Y"]`, String(y));
    fill(`[aria-label="Position ${i} Z"]`, String(z));
  }

  it("free-hand Save stays disabled until every electrode is placed, then saves four distinct points", async () => {
    renderFreehand();
    fill("#sim-freehand-name", "custom_4");
    const save = () => button("Save placement");
    expect(save().disabled).toBe(true);
    expect(save().title).toBe("Place every electrode on the scalp: E1+, E1-, E2+, E2- are not placed yet.");
    place(1, [61.2, 10.4, 40.1]);
    place(2, [-60.5, 12.0, 38.7]);
    place(3, [5.3, 72.8, 31.9]);
    expect(save().disabled).toBe(true);
    expect(container.querySelector("[data-testid='freehand-placement-problem']")?.textContent).toBe("Place every electrode on the scalp: E2- is not placed yet.");
    // The fourth on top of the first is two pads on one spot.
    place(4, [61.2, 10.4, 40.6]);
    expect(save().disabled).toBe(true);
    expect(save().title).toBe("E1+ and E2- are less than 1 mm apart: each electrode needs its own place on the scalp.");
    place(4, [3.1, -74.6, 33.0]);
    expect(save().disabled).toBe(false);
    await act(async () => save().click());
    expect(api.putFreehand).toHaveBeenCalledTimes(1);
    const [subject, name, body] = api.putFreehand.mock.calls[0] as unknown as [string, string, { electrode_positions: { x: number; y: number; z: number }[] }];
    expect([subject, name]).toEqual(["ernie", "custom_4"]);
    expect(body.electrode_positions.map((p) => [p.x, p.y, p.z])).toEqual([[61.2, 10.4, 40.1], [-60.5, 12.0, 38.7], [5.3, 72.8, 31.9], [3.1, -74.6, 33.0]]);
  });

  it("free-hand Save refuses a name the catalog would refuse, with the rule shown", () => {
    renderFreehand();
    place(1, [61.2, 10.4, 40.1]);
    place(2, [-60.5, 12.0, 38.7]);
    place(3, [5.3, 72.8, 31.9]);
    place(4, [3.1, -74.6, 33.0]);
    fill("#sim-freehand-name", "my placement");
    expect(button("Save placement").disabled).toBe(true);
    expect(container.querySelector("[data-testid='freehand-name-error']")?.textContent).toBe("A placement name may use letters, digits, '_' and '-' only, at most 64 characters.");
    fill("#sim-freehand-name", "my_placement");
    expect(container.querySelector("[data-testid='freehand-name-error']")).toBeNull();
    expect(button("Save placement").disabled).toBe(false);
  });

  it("freehandPlacementProblem accepts only placed, finite, separate positions", () => {
    const p = (x: number, y: number, z: number, label = "") => ({ label, x, y, z });
    expect(freehandPlacementProblem([p(60, 10, 40), p(-60, 10, 40), p(0, 70, 30), p(0, -70, 30)])).toBeNull();
    // A label the user typed does not place a row left at the origin.
    expect(freehandPlacementProblem([p(60, 10, 40), p(-60, 10, 40), p(0, 0, 0, "Fz"), p(0, -70, 30)])).toBe("Place every electrode on the scalp: Fz is not placed yet.");
    expect(freehandPlacementProblem([p(60, 10, 40), p(-60, 10, 40), p(0, 70, Number.POSITIVE_INFINITY, "Fz"), p(0, -70, 30)])).toBe("Fz has a coordinate that is not a number.");
  });
});

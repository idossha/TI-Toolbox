// @vitest-environment jsdom
/** 2026-09-13: authored candidate IDs/coordinates pin linked table, plot and draft navigation.
 * 2026-11-01: an ex run's table is its final_output.csv. FINAL_OUTPUT below has the header of a real
 * ex-search CSV (the user's run; tit.opt.ex.results.build_csv_rows writes it) and authored rows; the
 * test splits it itself, so the expected header and cells are the file's text, not the component's.
 * Tick labels are hand-derived (span / 5 rounded to a 1-2-5 step). Server-side passthrough and
 * sorting are pinned by tests/test_candidate_catalog.py.
 * ScenePane is an external rendering boundary here; hidden GPU/E2E coverage belongs to the lead.
 * Run npx vitest run tests/unit/candidate-browser.test.tsx.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CandidateBrowser } from "../../src/renderer/pages/results/candidates/CandidateBrowser";
import { getCandidate, getCandidateHistory, getCandidates } from "../../src/renderer/pages/results/candidates/api";
import { useSceneManifest } from "../../src/renderer/pages/_shared/scene";
import type { Candidate } from "../../src/renderer/pages/results/candidates/model";

const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("../../src/renderer/pages/results/candidates/api", () => ({ getCandidate: vi.fn(), getCandidateHistory: vi.fn(), getCandidates: vi.fn() }));
vi.mock("../../src/renderer/pages/_shared/scene", () => ({ useSceneManifest: vi.fn(() => ({ data: { building: false } })), ScenePane: (props: { subject: string; placedMarkers?: { id: string }[] }) => <div data-testid="subject-preview" data-subject={props.subject}>{props.placedMarkers?.map((marker) => marker.id).join(",")}</div> }));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
// Radix's select reads pointer capture, which jsdom lacks (same shim as assistant-page.test.tsx).
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};
Element.prototype.scrollIntoView ??= () => {};
const a: Candidate = { id: "a", objective: -2, objective_label: "Mean", objective_direction: "minimize", metrics: { roi_mean: 2, background_p95: 1, contrast: 2 }, metric_labels: {}, comparison_key: "subject-a", positions: [[1, 2, 3]], currents_mA: [0.7, 1.3] };
const b: Candidate = { ...a, id: "b", metrics: { roi_mean: 3, background_p95: 2, contrast: 1.5 }, positions: [[4, 5, 6]] };
const FINAL_OUTPUT = `Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index,HFpeak_Focality,TI_Selectivity
AF3_F7 <> F1_FC1_I1-1.0mA_I2-1.0mA,1.0,1.0,0.0921,0.0448,0.0300,1.4933,0.0669,1.2100,1.2342
AF3_F7 <> F1_FC3_I1-1.5mA_I2-0.5mA,1.5,0.5,0.1310,0.0952,0.0465,2.0480,0.1950,1.0000,2.0480
AF4_F8 <> F2_FC2_I1-0.5mA_I2-1.5mA,0.5,1.5,0.0705,0.0600,0.0621,0.9664,0.0580,,`;
const [csvHeader, ...csvRows] = FINAL_OUTPUT.split("\n").map((line) => line.split(","));
const exRows: Candidate[] = csvRows.map((cells, index) => ({ id: `ex-${index}`, objective: Number(cells[7]), objective_label: "Composite index", objective_direction: "maximize", metrics: {}, metric_labels: {}, comparison_key: "ex-run", pairs: [["AF3", "F7"], ["F1", "FC1"]], eeg_net: "EEG10-10", currents_mA: [1, 1], csv: Object.fromEntries(csvHeader!.map((column, i) => [column, cells[i]!])) }));
const exSource = { subject: "ernie", kind: "ex", run: "run-1" };
let root: Root, container: HTMLDivElement, client: QueryClient;
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useSceneManifest).mockReturnValue({ data: { building: false } } as ReturnType<typeof useSceneManifest>);
  container = document.createElement("div"); document.body.append(container); root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  vi.mocked(getCandidates).mockResolvedValue({ candidates: [a, b], total: 2, legacy: false });
  vi.mocked(getCandidateHistory).mockResolvedValue({ candidates: [a, b], total: 2, legacy: false });
  vi.mocked(getCandidate).mockResolvedValue({ candidate: b, simulation_config: { subject_id: "ernie", montages: [{ name: "exact" }] } });
});
afterEach(async () => { await act(async () => root.unmount()); client.clear(); container.remove(); });
async function render(run = "run-1", kind: "flex" | "ex" = "flex") {
  await act(async () => { root.render(<QueryClientProvider client={client}><CandidateBrowser subject="ernie" kind={kind} run={run} /></QueryClientProvider>); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 15)); });
}
async function click(element: Element | null) { expect(element).not.toBeNull(); await act(async () => element!.dispatchEvent(new MouseEvent("click", { bubbles: true }))); }

it("table and plot selection share the same subject montage and exact candidate detail request", async () => {
  await render();
  expect(container.querySelector('[data-testid="subject-preview"]')?.textContent).toBe("a-0");
  await click(container.querySelector('circle[aria-label="Select candidate b"]'));
  expect(container.querySelector('[data-testid="subject-preview"]')?.textContent).toBe("b-0");
  expect(container.querySelector('button[aria-pressed="true"]')?.textContent).toBe("b");
  await click([...container.querySelectorAll("button")].find((button) => button.textContent === "Use in Simulator") ?? null);
  expect(getCandidate).toHaveBeenCalledWith({ subject: "ernie", kind: "flex", run: "run-1" }, "b");
  expect(navigate).toHaveBeenCalledWith("/simulator", { state: { optimizationCandidate: { subject: "ernie", kind: "flex", run: "run-1", id: "b", requestId: expect.any(String), config: { subject_id: "ernie", montages: [{ name: "exact" }] } } } });
  await click([...container.querySelectorAll("button")].find((button) => button.textContent === "a") ?? null);
  expect(container.querySelector('circle[data-selected="true"]')?.getAttribute("aria-label")).toBe("Select candidate a");
});

it("labels legacy winner history and handles empty/error libraries without a fake preview", async () => {
  vi.mocked(getCandidates).mockResolvedValue({ candidates: [a], total: 1, legacy: true });
  await render();
  expect(container.textContent).toContain("only the saved winner");
  vi.mocked(getCandidates).mockResolvedValue({ candidates: [], total: 0, legacy: false });
  await act(async () => { await client.invalidateQueries(); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 15)); });
  expect(container.textContent).toContain("No valid evaluated candidates");
  expect(container.querySelector('[data-testid="subject-preview"]')).toBeNull();
  vi.mocked(getCandidates).mockRejectedValue(new Error("unavailable"));
  await act(async () => { await client.invalidateQueries(); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 15)); });
  expect(container.textContent).toContain("Could not load candidates");
});

it("paginates server-side and refuses to navigate when exact replay is unavailable", async () => {
  vi.mocked(getCandidates).mockResolvedValue({ candidates: [a, b], total: 120, legacy: false });
  vi.mocked(getCandidate).mockRejectedValue(new Error("Recorded geometry is unsupported."));
  await render();
  await click([...container.querySelectorAll("button")].find((button) => button.textContent === "Next") ?? null);
  expect(getCandidates).toHaveBeenLastCalledWith({ subject: "ernie", kind: "flex", run: "run-1" }, 50, "roi_mean", true);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 15)); });
  await click([...container.querySelectorAll("button")].find((button) => button.textContent === "Use in Simulator") ?? null);
  expect(container.textContent).toContain("Recorded geometry is unsupported.");
  expect(navigate).not.toHaveBeenCalled();
});


it("resets pagination and selection when the source run changes", async () => {
  vi.mocked(getCandidates).mockResolvedValue({ candidates: [a, b], total: 120, legacy: false });
  await render();
  await click([...container.querySelectorAll("button")].find((button) => button.textContent === "Next") ?? null);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 15)); });
  await click([...container.querySelectorAll("button")].find((button) => button.textContent === "b") ?? null);
  await render("other-run");
  expect(getCandidates).toHaveBeenLastCalledWith({ subject: "ernie", kind: "flex", run: "other-run" }, 0, "roi_mean", true);
  expect(container.querySelector('button[aria-pressed="true"]')?.textContent).toBe("a");
});

it("does not transfer an earlier selection after its detail request finishes", async () => {
  let finish!: (value: Awaited<ReturnType<typeof getCandidate>>) => void;
  vi.mocked(getCandidate).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  await render();
  await click([...container.querySelectorAll("button")].find((button) => button.textContent === "Use in Simulator") ?? null);
  await click([...container.querySelectorAll("button")].find((button) => button.textContent === "b") ?? null);
  await act(async () => finish({ candidate: a, simulation_config: {} }));
  expect(navigate).not.toHaveBeenCalled();
});

it("explains an empty historical winner without claiming a trial history", async () => {
  vi.mocked(getCandidates).mockResolvedValue({ candidates: [], total: 0, legacy: true });
  await render();
  expect(container.textContent).toContain("no replayable saved winner");
  expect(container.textContent).toContain("No valid evaluated candidates");
});


it("renders named Ex geometry when explicit XYZ positions are absent", async () => {
  vi.mocked(getCandidates).mockResolvedValue({ candidates: [{ ...a, positions: undefined, pairs: [["F3", "P3"], ["F4", "P4"]], eeg_net: "EEG10-10" }], total: 1, legacy: false });
  await render();
  expect(container.querySelector('[data-testid="subject-preview"]')?.getAttribute("data-subject")).toBe("ernie");
  expect(container.textContent).toContain("Use in Simulator");
});

it("selecting a plotted evaluation on a later table page reveals its row and montage", async () => {
  const all = Array.from({ length: 60 }, (_, index) => ({ ...a, id: `trial-${index}`, positions: [[index, 2, 3]] as [number, number, number][] }));
  vi.mocked(getCandidateHistory).mockResolvedValue({ candidates: all, total: 60, legacy: false });
  vi.mocked(getCandidates).mockImplementation(async (_run, offset) => ({ candidates: all.slice(offset, offset + 50), total: 60, legacy: false }));
  await render();
  expect(container.querySelectorAll("circle")).toHaveLength(60);
  await click(container.querySelector('circle[aria-label="Select candidate trial-55"]'));
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 15)); });
  expect(container.textContent).toContain("51–60 of 60");
  expect(container.querySelector('button[aria-pressed="true"]')?.textContent).toBe("trial-55");
  expect(container.querySelector('[data-testid="subject-preview"]')?.textContent).toBe("trial-55-0");
  expect(container.querySelector('circle[data-selected="true"]')?.getAttribute("aria-label")).toBe("Select candidate trial-55");
});

it("does not invent focality for intensity-only recordings", async () => {
  const unobserved = { ...a, metrics: { roi_mean: 2 } };
  vi.mocked(getCandidateHistory).mockResolvedValue({ candidates: [unobserved], total: 1, legacy: false });
  vi.mocked(getCandidates).mockResolvedValue({ candidates: [unobserved], total: 1, legacy: false });
  await render();
  expect(container.querySelectorAll("circle")).toHaveLength(0);
  expect(container.textContent).toContain("No values are inferred");
  expect(container.querySelector('[data-testid="subject-preview"]')).not.toBeNull();
});

it("never draws subject coordinates on a fallback guide while subject anatomy is unavailable", async () => {
  vi.mocked(useSceneManifest).mockReturnValue({ data: undefined } as ReturnType<typeof useSceneManifest>);
  await render();
  expect(container.querySelector('[data-testid="subject-preview"]')).toBeNull();
  expect(container.textContent).toContain("Subject montage preview unavailable");
  expect(container.textContent).toContain("Electrode coordinates");
});

it("uses small intensity-coloured points and a labelled legend with keyboard-linked selection", async () => {
  await render();
  const low = container.querySelector('circle[aria-label="Select candidate a"]')!;
  const high = container.querySelector('circle[aria-label="Select candidate b"]')!;
  expect(low.getAttribute("fill")).not.toBe(high.getAttribute("fill"));
  expect(Number(high.getAttribute("r"))).toBeLessThan(3);
  expect(Number(low.getAttribute("r"))).toBeGreaterThan(Number(high.getAttribute("r")));
  expect(container.querySelector('[aria-label="Point colour: ROI mean (V/m)"]')?.textContent)
    .toContain("Low 2.000High 3.000");
  expect(container.querySelector('[aria-label="Trade-off non-ROI metric"]')).not.toBeNull();
  expect(container.textContent).not.toMatch(/background/i);
  await act(async () => high.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  expect(high.getAttribute("aria-pressed")).toBe("true");
  expect(container.querySelector('svg.candidate-plot circle:last-child')).toBe(high);
  expect(container.querySelector('button[aria-pressed="true"]')?.textContent).toBe("b");
  expect(container.querySelector('[data-testid="subject-preview"]')?.textContent).toBe("b-0");
});

it("keeps historical whole-GM measurements distinct from non-ROI", async () => {
  const historical = { ...a, metric_labels: { background_mean: "Volume-weighted whole-GM mean, includes ROI", contrast: "ROI / whole-GM mean" } };
  vi.mocked(getCandidateHistory).mockResolvedValue({ candidates: [historical], total: 1, legacy: false });
  vi.mocked(getCandidates).mockResolvedValue({ candidates: [historical], total: 1, legacy: false });
  await render();
  expect(container.textContent).toContain("Whole-GM mean (includes ROI; V/m)");
  expect(container.textContent).toContain("ROI / whole-GM mean");
});

async function renderEx(rows = exRows, total = rows.length) {
  vi.mocked(getCandidates).mockResolvedValue({ candidates: rows, total, legacy: false });
  vi.mocked(getCandidateHistory).mockResolvedValue({ candidates: rows, total, legacy: false });
  await render("run-1", "ex");
}
const headerCell = (name: string) => [...container.querySelectorAll("thead th")].find((th) => th.textContent === name)!;

it("an ex table is its final_output.csv: the CSV's columns in order and every cell as written", async () => {
  await renderEx();
  const table = container.querySelector(".candidate-table table")!;
  expect([...table.querySelectorAll("thead th")].map((th) => th.textContent)).toEqual(csvHeader);
  expect([...table.querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")].map((td) => td.textContent))).toEqual(csvRows);
  expect(container.textContent).not.toContain("Unavailable");
  // Ranked by the run's own objective; the montage names the row, no separate id column.
  expect(getCandidates).toHaveBeenLastCalledWith(exSource, 0, "Composite_Index", true);
  expect(headerCell("Composite_Index").getAttribute("aria-sort")).toBe("descending");
  expect(container.textContent).toContain(`Selected: ${csvRows[0]![0]}`);
  expect(container.querySelector('button[aria-pressed="true"]')?.textContent).toBe(csvRows[0]![0]);
});

it("an ex header click sorts every row on the server, a second click flips it, and the sorted column shows its arrow", async () => {
  await renderEx(exRows, 120);
  expect(container.querySelector('[aria-label="Sort candidates"]')).toBeNull();
  expect([...container.querySelectorAll("button")].some((button) => /^(Descending|Ascending)$/.test(button.textContent ?? ""))).toBe(false);
  await click([...container.querySelectorAll("button")].find((button) => button.textContent === "Next") ?? null);
  expect(getCandidates).toHaveBeenLastCalledWith(exSource, 50, "Composite_Index", true);
  await click(headerCell("TImax_ROI").querySelector("button"));
  // Back to the first page of the whole run's order, not a re-sort of the page on screen.
  expect(getCandidates).toHaveBeenLastCalledWith(exSource, 0, "TImax_ROI", true);
  expect(getCandidateHistory).toHaveBeenLastCalledWith(exSource, "TImax_ROI", true, expect.anything());
  expect(headerCell("TImax_ROI").getAttribute("aria-sort")).toBe("descending");
  expect(headerCell("TImax_ROI").querySelector(".lucide-arrow-down")).not.toBeNull();
  expect(headerCell("Composite_Index").getAttribute("aria-sort")).toBeNull();
  await click(headerCell("TImax_ROI").querySelector("button"));
  expect(getCandidates).toHaveBeenLastCalledWith(exSource, 0, "TImax_ROI", false);
  expect(headerCell("TImax_ROI").querySelector(".lucide-arrow-up")).not.toBeNull();
  await click(headerCell("TImax_ROI").querySelector("button"));
  expect(getCandidates).toHaveBeenLastCalledWith(exSource, 0, "TImax_ROI", true);
  await click(headerCell("Montage").querySelector("button"));
  expect(getCandidates).toHaveBeenLastCalledWith(exSource, 0, "Montage", false);
});

it("the ex vertical axis offers only the CSV metric columns the run has, and both axes carry column names and round ticks", async () => {
  // A CSV written before the carrier metrics: their cells are empty in every row, so they are not offered.
  await renderEx(exRows.map((row) => ({ ...row, csv: { ...row.csv, HFpeak_Focality: "", TI_Selectivity: "" } })));
  const trigger = container.querySelector<HTMLButtonElement>('button[aria-label="Vertical axis"]')!;
  expect(trigger.textContent).toBe("Focality");
  await act(async () => { trigger.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerType: "mouse" })); });
  expect([...document.querySelectorAll("[role=option]")].map((option) => option.textContent)).toEqual(["TImax_ROI", "TImean_GM", "Focality", "Composite_Index"]);
  await act(async () => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  const texts = [...container.querySelectorAll("svg.candidate-plot > text")].map((text) => text.textContent);
  expect(texts).toEqual(["Focality ↑", "TImean_ROI →"]);
  // x: TImean_ROI spans 0.0448-0.0952; y: Focality spans 0.9664-2.048.
  expect([...container.querySelectorAll(".candidate-ticks text")].map((text) => text.textContent))
    .toEqual(["0.05", "0.06", "0.07", "0.08", "0.09", "1.0", "1.2", "1.4", "1.6", "1.8", "2.0"]);
  expect(container.querySelectorAll("circle")).toHaveLength(3);
  expect(container.querySelector('circle[data-selected="true"]')?.getAttribute("aria-label")).toBe(`Select candidate ${csvRows[0]![0]}`);
});

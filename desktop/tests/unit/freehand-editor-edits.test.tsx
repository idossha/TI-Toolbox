// @vitest-environment jsdom
/**
 * The free-hand placement editor saves what the user typed, for the subject it was placed on, and
 * the job rows that use a placement run what its file now holds. Three audited defects (2026-11-17):
 *
 *  - typing `-60` into a coordinate saved +60: a number input reports a lone `-` as "", which the
 *    editor stored as 0, React wrote "0" back, and the next digits made "060";
 *  - switching the editor's Subject after placing saved subject A's head millimetres under B;
 *  - saving over an existing name left job rows on the old coordinates they had snapshotted.
 *
 * Expected values are the user's own keystrokes and clicks; nothing is derived from the code under
 * test. Only the HTTP layer, the toasts and Radix's portal Select are replaced.
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

const api = vi.hoisted(() => ({
  getMontages: vi.fn(async () => ({ nets: {} })),
  getEegNets: vi.fn(async () => []),
  getFlexRuns: vi.fn(async (): Promise<unknown[]> => []),
  getFreehand: vi.fn(async (): Promise<unknown[]> => []),
  getFlexMapping: vi.fn(async (): Promise<unknown> => ({ pairs: [] })),
  getCandidateMapping: vi.fn(async () => ({ pairs: [] })),
  putMontage: vi.fn(async () => []),
  deleteMontage: vi.fn(async () => undefined),
  deleteFreehand: vi.fn(async () => undefined),
  putFreehand: vi.fn(async () => undefined),
}));
vi.mock("../../src/renderer/pages/simulator/api", () => api);
vi.mock("../../src/renderer/ui/Toast", () => ({
  notify: { error: vi.fn(), success: vi.fn(), blocked: vi.fn(), info: vi.fn(), warning: vi.fn() },
  notifySubmitError: vi.fn(),
}));
vi.mock("../../src/renderer/ui/Select", () => ({
  Select: ({ id, value, onValueChange, options, disabled }: { id?: string; value?: string; onValueChange: (v: string) => void; options: { value: string; label: string }[]; disabled?: boolean }) => (
    <select id={id} value={value ?? ""} disabled={disabled} onChange={(e) => onValueChange(e.target.value)}>
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
import { FreehandEditor } from "../../src/renderer/pages/simulator/FreehandEditor";
import { FreehandDraftProvider } from "../../src/renderer/pages/simulator/freehandDraft";

type Xyz = [number, number, number];
const PLACED: Xyz[] = [[61.2, 10.4, 40.1], [-60.5, 12.0, 38.7], [5.3, 72.8, 31.9], [3.1, -74.6, 33.0]];

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
const input = (selector: string) => container.querySelector<HTMLInputElement>(selector)!;
const cell = (row: number, axis: "X" | "Y" | "Z") => input(`[aria-label="Position ${row} ${axis}"]`);
const button = (text: string) => [...container.querySelectorAll("button")].find((b) => b.textContent === text) as HTMLButtonElement;
const setValue = (el: HTMLInputElement | HTMLSelectElement, value: string) =>
  Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value")!.set!.call(el, value);

function fill(el: HTMLInputElement, value: string) {
  act(() => {
    setValue(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

/**
 * Types `text` one key at a time over a selected field, the way a browser does: it keeps its own
 * text and appends each key to it — unless the page wrote the field in between, after which it
 * appends to what the page wrote. jsdom, like a browser, reports an unfinished number such as "-"
 * as "".
 */
function typeKeys(el: HTMLInputElement, text: string) {
  let typed = "";
  for (const key of text) {
    typed += key;
    setValue(el, typed);
    const reported = el.value;
    act(() => {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
    if (el.value !== reported) typed = el.value;
  }
}

function placeAll(points: Xyz[] = PLACED) {
  points.forEach(([x, y, z], i) => {
    fill(cell(i + 1, "X"), String(x));
    fill(cell(i + 1, "Y"), String(y));
    fill(cell(i + 1, "Z"), String(z));
  });
}

function renderEditor(subjects = ["ernie"]) {
  act(() =>
    root.render(
      <QueryClientProvider client={queryClient}>
        <PageIdContext.Provider value="simulator">
          <FreehandDraftProvider>
            <FreehandEditor subjects={subjects} onClose={() => {}} />
          </FreehandDraftProvider>
        </PageIdContext.Provider>
      </QueryClientProvider>,
    ),
  );
}

describe("free-hand coordinates", () => {
  it("typing -60 key by key into X saves -60, not +60", async () => {
    renderEditor();
    placeAll();
    fill(input("#sim-freehand-name"), "left");
    typeKeys(cell(2, "X"), "-60");
    expect(cell(2, "X").value).toBe("-60");
    expect(button("Save placement").disabled).toBe(false);
    await act(async () => button("Save placement").click());
    expect(api.putFreehand).toHaveBeenCalledTimes(1);
    const [, , config] = api.putFreehand.mock.calls[0] as unknown as [string, string, { electrode_positions: { x: number }[] }];
    expect(config.electrode_positions[1]!.x).toBe(-60);
  });

  it("a cleared coordinate stays empty and blocks Save until it holds a number", () => {
    renderEditor();
    placeAll();
    fill(input("#sim-freehand-name"), "cleared");
    expect(button("Save placement").disabled).toBe(false);
    fill(cell(3, "Y"), "");
    expect(cell(3, "Y").value).toBe("");
    expect(button("Save placement").disabled).toBe(true);
    fill(cell(3, "Y"), "72.8");
    expect(button("Save placement").disabled).toBe(false);
  });
});

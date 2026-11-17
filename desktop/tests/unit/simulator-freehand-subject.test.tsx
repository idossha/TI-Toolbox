// @vitest-environment jsdom
/**
 * A free-hand placement stays with the subject it was placed on when a job row is duplicated and
 * the copy is pointed at another subject (2026-11-17, the owner's rule: "no free-hand should be
 * automatically available to another model"). The copy keeps the same subject until the user
 * changes it; then it is back to "pick a placement", never the first subject's coordinates.
 *
 * Expected values are the authored rows and the user's clicks; nothing is derived from the code
 * under test. Only the HTTP layer, the toasts, Radix's portal Select and the subject picker's
 * popover are replaced. Reproduce: cd desktop && npx vitest run tests/unit/simulator-freehand-subject.test.tsx
 * Deliberately elsewhere: the plan step (plan-step-form.test.ts) and the server's refusal
 * (tests/test_freehand_one_subject.py).
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

vi.mock("../../src/renderer/pages/simulator/api", () => ({
  getMontages: vi.fn(async () => ({ nets: {} })),
  getEegNets: vi.fn(async () => []),
  getFlexRuns: vi.fn(async () => []),
  getFreehand: vi.fn(async () => []),
  getFlexMapping: vi.fn(async () => ({ pairs: [] })),
  getCandidateMapping: vi.fn(async () => ({ pairs: [] })),
  putMontage: vi.fn(async () => []),
  deleteMontage: vi.fn(async () => undefined),
  deleteFreehand: vi.fn(async () => undefined),
  putFreehand: vi.fn(async () => undefined),
}));
vi.mock("../../src/renderer/ui/Toast", () => ({
  notify: { error: vi.fn(), success: vi.fn(), blocked: vi.fn(), info: vi.fn(), warning: vi.fn() },
  notifySubmitError: vi.fn(),
}));
vi.mock("../../src/renderer/ui/Select", () => ({
  Select: ({ id, value, onValueChange, options }: { id?: string; value?: string; onValueChange: (v: string) => void; options: { value: string; label: string }[] }) => (
    <select id={id} value={value ?? ""} onChange={(e) => onValueChange(e.target.value)}>
      <option value="" />
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}));
vi.mock("../../src/renderer/ui/SelectionList", () => ({
  SelectionPicker: ({ triggerTestId, value, onChange, items }: { triggerTestId?: string; value: string[]; onChange: (v: string[]) => void; items: { id: string }[] }) => (
    <select data-testid={triggerTestId} value={value[0] ?? ""} onChange={(e) => onChange([e.target.value])}>
      {items.map((i) => <option key={i.id} value={i.id}>{i.id}</option>)}
    </select>
  ),
}));

import { PageIdContext, clearPageSession } from "../../src/renderer/app/pageSession";
import { FreehandDraftProvider } from "../../src/renderer/pages/simulator/freehandDraft";
import { JobsTable } from "../../src/renderer/pages/simulator/MontageManager";
import type { SelectedRow } from "../../src/renderer/pages/simulator/types";

const NET = "GSN-HydroCel-185.csv";
let container: HTMLDivElement;
let root: Root;
let queryClient: QueryClient;

beforeEach(() => {
  clearPageSession();
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

function renderTable(rows: SelectedRow[], onRowsChange: (rows: SelectedRow[]) => void) {
  act(() =>
    root.render(
      <QueryClientProvider client={queryClient}>
        <PageIdContext.Provider value="simulator">
          <FreehandDraftProvider>
            <JobsTable subjects={[{ id: "ernie" }, { id: "101" }]} subjectNets={{ ernie: [NET], "101": [NET] }} rows={rows} onRowsChange={onRowsChange} draft={null} onDraftChange={() => {}} />
          </FreehandDraftProvider>
        </PageIdContext.Provider>
      </QueryClientProvider>,
    ),
  );
}

async function flush() {
  for (let i = 0; i < 6; i += 1) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

it("a duplicated free-hand row moved to another subject drops the first subject's points", async () => {
  const pairs: SelectedRow["xyzPairs"] = [[[-60, 10, 40], [60, 10, 40]], [[-60, -40, 40], [60, -40, 40]]];
  const original: SelectedRow = { id: "a", subjectId: "ernie", source: "freehand", name: "hand", xyzPairs: pairs, currents: "1,1" };
  const onRowsChange = vi.fn();
  renderTable([original], onRowsChange);
  await flush();
  act(() => container.querySelector<HTMLButtonElement>('[aria-label="Duplicate job 1"]')!.click());
  const duplicated = onRowsChange.mock.calls.at(-1)![0] as SelectedRow[];
  expect(duplicated.map((r) => [r.subjectId, r.name, r.xyzPairs])).toEqual([["ernie", "hand", pairs], ["ernie", "hand", pairs]]);

  renderTable(duplicated, onRowsChange);
  await flush();
  const copy = duplicated[1]!;
  const picker = container.querySelector<HTMLSelectElement>(`[data-testid="job-subject-${copy.id}"]`)!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(picker, "101");
    picker.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const moved = (onRowsChange.mock.calls.at(-1)![0] as SelectedRow[]).find((r) => r.id === copy.id)!;
  expect([moved.subjectId, moved.source, moved.name, moved.xyzPairs]).toEqual(["101", "freehand", "", undefined]);
});

/**
 * Autosave/flush ordering in `pages/notebooks/session.ts` (audit UI-01).
 *
 * The failure this pins: a slow PUT is in flight, the author types again, the
 * autosave that follows JOINS the in-flight promise instead of queueing a new
 * write — so when the OLD request resolves it clears `dirty`, `flush()` sees a
 * clean notebook and returns true, and the later edit is never sent at all.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const saveNotebook = vi.fn<(name: string, content: unknown) => Promise<unknown>>();

vi.mock("../../src/renderer/pages/notebooks/api", () => ({
  saveNotebook: (name: string, content: unknown) => saveNotebook(name, content),
  readNotebook: vi.fn(),
  createNotebook: vi.fn(),
  startKernel: vi.fn(),
  stopKernel: vi.fn(),
  restartKernel: vi.fn(),
  interruptKernel: vi.fn(),
}));

const { Session, useNotebookMetaStoreForTests } = await import("../../src/renderer/pages/notebooks/session");
import type { Notebook } from "../../src/renderer/pages/notebooks/notebook";

function notebook(source: string): Notebook {
  return {
    cells: [{ cell_type: "code", source, outputs: [], execution_count: null, metadata: {} }],
    metadata: {},
    nbformat: 4,
    nbformat_minor: 5,
  } as unknown as Notebook;
}

/** Source of the first cell of the document handed to the Nth saveNotebook call. */
function sentSource(call: number): string {
  const content = saveNotebook.mock.calls[call]?.[1] as Notebook;
  const cell = content.cells[0] as { source: string };
  return cell.source;
}

describe("Session.save — an edit made mid-flight is not lost (UI-01)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    saveNotebook.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("flush() sends the later edit rather than joining the stale in-flight save", async () => {
    let resolveFirst!: () => void;
    saveNotebook
      .mockImplementationOnce(() => new Promise<void>((resolve) => (resolveFirst = () => resolve())))
      .mockImplementation(() => Promise.resolve());

    const session = new Session("nb.ipynb");
    session.nb = notebook("v1");
    const cell = session.nb.cells[0] as unknown as { source: string };

    // First save is in flight with "v1".
    const first = session.save();
    expect(saveNotebook).toHaveBeenCalledTimes(1);
    expect(sentSource(0)).toBe("v1");

    // The author types again while it is still in flight, and the autosave fires.
    session.setCellSource(cell as never, "v2");
    vi.advanceTimersByTime(2000);
    await Promise.resolve();

    // The old request finally lands.
    resolveFirst();
    await first;
    await vi.runAllTimersAsync();

    expect(await session.flush()).toBe(true);
    await vi.runAllTimersAsync();

    const sent = saveNotebook.mock.calls.map((_, i) => sentSource(i));
    expect(sent[sent.length - 1]).toBe("v2");
    expect(useNotebookMetaStoreForTests.getState().byName["nb.ipynb"]?.dirty).toBe(false);
  });

  it("keeps the notebook dirty while a newer edit than the resolved save exists", async () => {
    let resolveFirst!: () => void;
    saveNotebook
      .mockImplementationOnce(() => new Promise<void>((resolve) => (resolveFirst = () => resolve())))
      .mockImplementation(() => Promise.resolve());

    const session = new Session("nb2.ipynb");
    session.nb = notebook("v1");
    const cell = session.nb.cells[0] as unknown as { source: string };
    const first = session.save();
    session.setCellSource(cell as never, "v2");
    resolveFirst();
    await first;
    // The resolved PUT carried "v1"; "v2" is still unsaved, so dirty must stand.
    expect(useNotebookMetaStoreForTests.getState().byName["nb2.ipynb"]?.dirty).toBe(true);
    await vi.runAllTimersAsync();
    expect(sentSource(1)).toBe("v2");
  });
});

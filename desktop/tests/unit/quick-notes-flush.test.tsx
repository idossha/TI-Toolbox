// @vitest-environment jsdom
/**
 * Quick notes never loses text typed just before the drawer closes, and its status says "Saved"
 * only once the text on screen is the text the server acknowledged.
 *
 * The failures it pins:
 * - `QuickNotesHost` unmounts the drawer when it closes, and the drawer's unmount cleanup cleared
 *   the 800 ms autosave timer without sending it: text typed less than 800 ms before Esc was never
 *   PUT, and reopening showed the pre-edit cache.
 * - Every PUT's success cleared "Unsaved changes" and wrote its value into the `["notes"]` cache,
 *   so an older PUT finishing after newer typing read as "Saved", and one finishing after a newer
 *   PUT put the older text back into the cache a reopen reads.
 *
 * - The window-close/reload flush started an ordinary PUT, which Chromium cancels with the
 *   document; only a `keepalive` request is delivered after the page is gone. The Fetch standard
 *   refuses a keepalive body over 64 KiB (65,536 bytes, UTF-8), so a larger notepad goes plain.
 * - "Only the newest text may read as saved" was per drawer, so a closed drawer's late answer
 *   could put its older text back into the cache after a reopened drawer had saved newer text.
 *
 * Expected values are the strings this test types and the 64 KiB limit from the Fetch standard;
 * `putNotes` and the client's `api.PUT` (the unload path) are the only stubs (their promises are
 * resolved by hand so the order is the test's). Timers are faked so "100 ms after typing" is
 * exact. 2026-10-22.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

interface Notes {
  text: string;
  updated_at: string | null;
}

const server = vi.hoisted(() => {
  const state = {
    stored: { text: "", updated_at: null } as { text: string; updated_at: string | null },
    /** Each PUT the drawer sent, in order: its text, its `keepalive` flag (`null`: sent through
     * `putNotes`, which has none), and the hand to resolve it. */
    puts: [] as { text: string; keepalive: boolean | null; resolve: () => void }[],
    put(text: string, keepalive: boolean | null) {
      return new Promise<{ text: string; updated_at: string | null }>((resolve) => {
        state.puts.push({
          text,
          keepalive,
          resolve: () => {
            state.stored = { text, updated_at: "2026-10-22T09:00:00Z" };
            resolve({ ...state.stored });
          },
        });
      });
    },
  };
  return state;
});

vi.mock("../../src/renderer/pages/panel-quick-notes/api", () => ({
  getNotes: vi.fn(async (): Promise<Notes> => ({ ...server.stored })),
  putNotes: vi.fn((text: string) => server.put(text, null)),
}));

// The unload flush calls the typed client itself, to set `keepalive`; everything else stays real.
vi.mock("../../src/renderer/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../src/renderer/api/client")>()),
  api: {
    PUT: vi.fn(async (path: string, init: { body: { text: string }; keepalive?: boolean }) => {
      if (path !== "/api/catalog/notes") throw new Error(`unexpected PUT ${path}`);
      const data = await server.put(init.body.text, init.keepalive ?? false);
      return { data, response: new Response(JSON.stringify(data), { status: 200 }) };
    }),
  },
}));

const { QuickNotesHost } = await import("../../src/renderer/app/QuickNotesHost");
// Loaded once up front so the host's lazy import resolves from the module cache under fake timers.
await import("../../src/renderer/pages/panel-quick-notes/QuickNotesDrawer");

let root: Root;
let container: HTMLDivElement;
let queryClient: QueryClient;

function render(open: boolean): void {
  act(() =>
    root.render(
      <QueryClientProvider client={queryClient}>
        <QuickNotesHost open={open} onOpenChange={() => {}} />
      </QueryClientProvider>,
    ),
  );
}

/** Let the lazy drawer module and the notes GET settle (real promises; fake timers advanced too). */
async function settle(): Promise<void> {
  for (let i = 0; i < 10; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
  }
}

function textarea(): HTMLTextAreaElement {
  const el = document.querySelector<HTMLTextAreaElement>('[data-testid="quick-notes-textarea"]');
  if (!el) throw new Error("the quick notes textarea is not on screen");
  return el;
}

function status(): string {
  return document.querySelector('[data-testid="quick-notes-status"]')?.textContent ?? "";
}

/** Type *value* into the controlled textarea the way a keystroke does (React listens for `input`). */
function type(value: string): void {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => {
    setter.call(textarea(), value);
    textarea().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

/** Run pending promise callbacks only: zero fake-clock time passes, so no debounce can fire. */
async function microtasks(): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

async function resolvePut(index: number): Promise<void> {
  await act(async () => {
    server.puts[index]!.resolve();
    await vi.advanceTimersByTimeAsync(0);
  });
}

describe("Quick notes autosave", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    server.stored = { text: "", updated_at: null };
    server.puts = [];
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    queryClient.clear();
    document.body.innerHTML = "";
    vi.useRealTimers();
  });

  it("sends text typed 100 ms before the drawer closes, once, and a reopen shows it", async () => {
    render(true);
    await settle();
    type("abc");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(server.puts).toHaveLength(0); // still inside the 800 ms debounce
    render(false); // Esc: the host unmounts the drawer
    await microtasks(); // the mutation calls putNotes a few microtasks later; no timer runs here
    expect(server.puts.map((p) => p.text)).toEqual(["abc"]);
    // The debounce it replaced never fires a second PUT.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(server.puts.map((p) => p.text)).toEqual(["abc"]);

    await resolvePut(0);
    render(true);
    await settle();
    expect(textarea().value).toBe("abc");
  });

  it("sends the pending text as a keepalive request when the window is about to unload", async () => {
    render(true);
    await settle();
    type("before unload");
    act(() => {
      window.dispatchEvent(new Event("beforeunload"));
    });
    await microtasks();
    // keepalive: Chromium still delivers it after the document is gone; a plain fetch is cancelled.
    expect(server.puts.map((p) => [p.text, p.keepalive])).toEqual([["before unload", true]]);
    // Closing afterwards has nothing left to send.
    render(false);
    await microtasks();
    expect(server.puts).toHaveLength(1);
    // The window stayed (another page's beforeunload can keep it): the answer still lands.
    await resolvePut(0);
    expect(queryClient.getQueryData<Notes>(["notes"])?.text).toBe("before unload");
  });

  it("sends a notepad over the 64 KiB keepalive budget as a plain request instead", async () => {
    // The JSON body is {"text":"…"}: 11 bytes around the text, measured in UTF-8 bytes.
    const cases: [string, boolean][] = [
      ["x".repeat(65_536 - 11), true], // exactly 64 KiB
      ["x".repeat(65_536 - 11 + 1), false], // one byte over
      ["é".repeat(32_763), false], // 65,526 bytes of text (2 each), 32,763 characters
    ];
    render(true);
    await settle();
    for (const [index, [text]] of cases.entries()) {
      type(text);
      act(() => {
        window.dispatchEvent(new Event("beforeunload"));
      });
      await microtasks();
      expect(server.puts).toHaveLength(index + 1);
    }
    expect(server.puts.map((p) => [p.text.length, p.keepalive])).toEqual(cases.map(([text, keepalive]) => [text.length, keepalive]));
  });

  it("closing with nothing typed sends nothing", async () => {
    render(true);
    await settle();
    render(false);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(server.puts).toHaveLength(0);
  });

  it("does not read Saved while newer text is still unsaved", async () => {
    render(true);
    await settle();
    type("a");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    expect(server.puts.map((p) => p.text)).toEqual(["a"]);
    type("ab"); // typed while "a" is in flight
    await resolvePut(0); // the older PUT answers
    expect(status()).toBe("Unsaved changes");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    expect(server.puts.map((p) => p.text)).toEqual(["a", "ab"]);
    await resolvePut(1);
    expect(status()).toMatch(/^Saved /);
  });

  it("an older PUT answering last neither reads as the save nor rewrites the cache", async () => {
    render(true);
    await settle();
    type("one");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    type("one two");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    expect(server.puts.map((p) => p.text)).toEqual(["one", "one two"]);
    await resolvePut(1); // the newest answers first
    expect(status()).toMatch(/^Saved /);
    await resolvePut(0); // then the older one
    expect(queryClient.getQueryData<Notes>(["notes"])?.text).toBe("one two");
    // Reopening reads the cache: the newest text, not the older PUT's.
    render(false);
    render(true);
    await settle();
    expect(textarea().value).toBe("one two");
  });

  it("a closed drawer's late answer does not undo newer text saved after reopening", async () => {
    render(true);
    await settle();
    type("first");
    render(false); // Esc: "first" goes out, and its answer is slow
    await microtasks();
    render(true); // reopened before that answer
    await settle();
    type("second");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    expect(server.puts.map((p) => p.text)).toEqual(["first", "second"]);
    await resolvePut(1);
    expect(status()).toMatch(/^Saved /);
    await resolvePut(0); // the first drawer's PUT answers last
    expect(queryClient.getQueryData<Notes>(["notes"])?.text).toBe("second");
    render(false);
    render(true);
    await settle();
    expect(textarea().value).toBe("second");
  });
});

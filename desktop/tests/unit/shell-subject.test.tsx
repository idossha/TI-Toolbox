// @vitest-environment jsdom
/**
 * The subject spine (plan §1): one store scopes every subject page, the URL carries it so a deep
 * link scopes the app, and localStorage remembers it per project. The three rules that are easy to
 * get wrong and expensive to get wrong are asserted here — a link beats a memory, switching the
 * primary subject never leaves it in the batch, and re-scoping replaces the history entry instead
 * of stacking one per subject.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// This jsdom's `localStorage` is a partial shim (no `clear`), so the spine gets a real in-memory
// one — the store's own try/catch means a broken localStorage would otherwise hide a failure here.
const store = new Map<string, string>();
Object.defineProperty(window, "localStorage", {
  writable: true,
  value: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: (i: number) => [...store.keys()][i] ?? null,
    get length() {
      return store.size;
    },
  },
});

vi.mock("../../src/renderer/api/client", () => ({
  getProject: vi.fn(async () => ({ name: "example", container_path: "/mnt/example", host_path: null })),
  getSubjects: vi.fn(async () => [{ id: "ernie", has_raw: true, has_freesurfer: true, has_m2m: true }]),
  api: { GET: vi.fn() },
  unwrap: vi.fn((r: unknown) => r),
}));

const { useSubjectContext, clearSubjectPages, presenceChips, readStoredSubject } = await import("../../src/renderer/app/subjectContext");
const { useSubjectSpine } = await import("../../src/renderer/app/subjectSpine");

async function settle(times = 12): Promise<void> {
  for (let i = 0; i < times; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });
  }
}

describe("the subject store", () => {
  beforeEach(() => {
    act(() => clearSubjectPages());
  });

  it("keeps the primary subject out of the batch, whichever side changes", () => {
    act(() => useSubjectContext.getState().setBatch(["bert", "ernie"]));
    expect(useSubjectContext.getState().batch).toEqual(["bert", "ernie"]);

    act(() => useSubjectContext.getState().setSubject("ernie"));
    // "ernie + 2 more" must never mean "ernie + ernie + one other".
    expect(useSubjectContext.getState().batch).toEqual(["bert"]);

    act(() => useSubjectContext.getState().setBatch(["ernie", "carl"]));
    expect(useSubjectContext.getState().batch).toEqual(["carl"]);
  });

  it("clearing the subject leaves the batch alone", () => {
    act(() => {
      useSubjectContext.getState().setSubject("ernie");
      useSubjectContext.getState().setBatch(["bert"]);
      useSubjectContext.getState().setSubject(null);
    });
    expect(useSubjectContext.getState().batch).toEqual(["bert"]);
  });

  it("presence chips use one vocabulary, and gain dwi/ct only once the detail is loaded", () => {
    expect(
      presenceChips({ id: "e", has_raw: true, has_fastsurfer: false, has_freesurfer: false, has_m2m: true, n_simulations: 0 }).map((c) => c.label),
    ).toEqual(["raw", "fastsurfer", "freesurfer", "m2m"]);
    const detail = {
      id: "e",
      has_raw: true,
      has_fastsurfer: true,
      has_freesurfer: true,
      has_m2m: true,
      n_simulations: 2,
      has_dwi: false,
      has_ct: true,
      has_leadfields: [],
    };
    expect(presenceChips(detail).map((c) => c.label)).toEqual(["raw", "fastsurfer", "freesurfer", "m2m", "dwi", "ct"]);
    expect(presenceChips(undefined)).toEqual([]);
  });
});

describe("useSubjectSpine — URL and localStorage", () => {
  let container: HTMLDivElement;
  let root: Root;
  let location: { pathname: string; search: string } = { pathname: "", search: "" };
  let historyLength = 0;
  let hash = "";

  function Probe() {
    useSubjectSpine();
    const l = useLocation();
    location = { pathname: l.pathname, search: l.search };
    hash = l.hash;
    historyLength += 1;
    return null;
  }

  async function mount(entry: string) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[entry]}>
            <Probe />
          </MemoryRouter>
        </QueryClientProvider>,
      );
    });
    await settle();
  }

  beforeEach(() => {
    window.localStorage.clear();
    act(() => clearSubjectPages());
    historyLength = 0;
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    window.history.replaceState({}, "", "/");
  });

  it("adopts ?subject= from the route — a deep link scopes the app", async () => {
    await mount("/simulator?subject=ernie");
    expect(useSubjectContext.getState().subjectId).toBe("ernie");
  });

  it("uses a browser entry's subject once when the memory route has none", async () => {
    window.history.replaceState({}, "", "?subject=ernie");
    await mount("/simulator");
    expect(useSubjectContext.getState().subjectId).toBe("ernie");
    act(() => useSubjectContext.getState().setSubject("bert"));
    await settle();
    expect(useSubjectContext.getState().subjectId).toBe("bert");
    expect(location.search).toBe("?subject=bert");
  });

  it("publishes the subject back onto the current route and remembers it per project", async () => {
    await mount("/simulator");
    act(() => useSubjectContext.getState().setSubject("bert"));
    await settle();
    expect(location).toEqual({ pathname: "/simulator", search: "?subject=bert" });
    expect(readStoredSubject("example")).toBe("bert");
    expect(readStoredSubject("other-project")).toBeNull();
  });

  it("preserves the requested Settings tab when publishing the remembered subject", async () => {
    window.localStorage.setItem("tit-subject:example", "bert");
    await mount("/settings#preprocessing");
    expect(location.search).toBe("?subject=bert");
    expect(hash).toBe("#preprocessing");
  });

  it("keeps any other search parameter the page put there", async () => {
    await mount("/results?kind=flex");
    act(() => useSubjectContext.getState().setSubject("ernie"));
    await settle();
    expect(location.search).toContain("kind=flex");
    expect(location.search).toContain("subject=ernie");
  });

  it("a user selection updates a URL that already names the previous subject", async () => {
    await mount("/simulator?subject=ernie");
    act(() => useSubjectContext.getState().setSubject("bert"));
    await settle();
    expect(location.search).toBe("?subject=bert");
    expect(useSubjectContext.getState().subjectId).toBe("bert");
    const renders = historyLength;
    await settle();
    expect(historyLength).toBe(renders);
  });

  it("a link beats a memory: ?subject= wins over the stored subject", async () => {
    window.localStorage.setItem("tit-subject:example", "bert");
    await mount("/simulator?subject=ernie");
    expect(useSubjectContext.getState().subjectId).toBe("ernie");
  });

  it("resumes the project's last subject when the route names none", async () => {
    window.localStorage.setItem("tit-subject:example", "bert");
    await mount("/simulator");
    expect(useSubjectContext.getState().subjectId).toBe("bert");
    expect(location.search).toBe("?subject=bert");
  });

  it("does not loop: re-scoping settles instead of re-navigating forever", async () => {
    await mount("/simulator");
    act(() => useSubjectContext.getState().setSubject("ernie"));
    await settle();
    const renders = historyLength;
    await settle();
    expect(historyLength).toBe(renders);
  });
});

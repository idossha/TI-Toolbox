// @vitest-environment jsdom
/**
 * Per-page session state (lane N2): the model, at the two seams a page cannot reach itself.
 *
 * The defect: a run page unmounts on every navigation (`app/App.tsx` renders one route element),
 * so everything it kept in `useState` — the sections the user opened, the tab they picked, where
 * they scrolled — died with it, and `RunWork`'s fill controller then re-derived a different layout
 * on the way back. `tests/e2e/page-memory.spec.ts` is the end-to-end gate (4 failed before, 4
 * passed after); this file pins the three rules the gate depends on:
 *
 *   1. the bag is per page and outlives the component that wrote it;
 *   2. a section the user toggled outranks the density pin and the fill controller, ACROSS mounts;
 *   3. a restored scroll offset survives a page that mounts short, and yields to a real user
 *      scroll rather than fighting it.
 */
import React, { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  PageIdContext,
  clearPageSession,
  readSession,
  sessionSlot,
  usePageSession,
} from "../../src/renderer/app/pageSession";
import { FormSection } from "../../src/renderer/ui/Layout";
import { RunWork } from "../../src/renderer/pages/_shared/run/RunWork";
import { attachScrollMemory } from "../../src/renderer/pages/_shared/run/scrollMemory";

describe("usePageSession", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    clearPageSession();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function Counter({ label }: { label: string }) {
    const [n, setN] = usePageSession("count", 0);
    return (
      <button type="button" onClick={() => setN((v) => v + 1)}>
        {label}:{n}
      </button>
    );
  }

  function mount(pageId: string, label = "a") {
    act(() =>
      root.render(
        <PageIdContext.Provider value={pageId}>
          <Counter label={label} />
        </PageIdContext.Provider>,
      ),
    );
  }

  it("a value written on a page is the value the next mount of that page starts from", () => {
    mount("simulator");
    const button = () => container.querySelector("button") as HTMLButtonElement;
    act(() => button().click());
    act(() => button().click());
    expect(button().textContent).toBe("a:2");

    // What navigating away and back does: the component is destroyed and rebuilt.
    act(() => root.render(<div />));
    mount("simulator");
    expect(button().textContent).toBe("a:2");
    expect(readSession<number>(sessionSlot("simulator", "count"))).toBe(2);
  });

  it("two pages keep separate bags — Simulator's sections are not the Analyzer's", () => {
    mount("simulator");
    act(() => (container.querySelector("button") as HTMLButtonElement).click());
    act(() => root.render(<div />));
    mount("analyzer", "b");
    expect((container.querySelector("button") as HTMLButtonElement).textContent).toBe("b:0");
    expect(readSession<number>(sessionSlot("simulator", "count"))).toBe(1);
    expect(readSession<number>(sessionSlot("analyzer", "count"))).toBe(0);
  });
});

describe("a user-touched section outranks the density rule and the fill controller", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    clearPageSession();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  /** The Simulator's shape: a section with a non-default value, which the density rule pins open. */
  function Page() {
    return (
      <PageIdContext.Provider value="simulator">
        <div data-testid="page-work">
          <div data-page-work-scroll>
            <RunWork>
              <FormSection title="Electrodes" collapsible changed summary="ellipse · 8×8 mm">
                <span>body</span>
              </FormSection>
            </RunWork>
          </div>
        </div>
      </PageIdContext.Provider>
    );
  }

  const trigger = () => container.querySelector("button.form-section-header-trigger") as HTMLButtonElement;

  it("closing a pinned-open section survives the unmount that navigation causes", () => {
    act(() => root.render(<Page />));
    // The density rule opened it: it holds a non-default value.
    expect(trigger().getAttribute("aria-expanded")).toBe("true");

    act(() => trigger().click());
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
    expect(readSession<Record<string, boolean>>(sessionSlot("simulator", "sections.user"))).toEqual({
      Electrodes: false,
    });

    // Navigate away and back.
    act(() => root.render(<div />));
    act(() => root.render(<Page />));
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
  });

  it("an untouched section is still the controller's to decide (nothing is recorded for it)", () => {
    act(() => root.render(<Page />));
    expect(readSession<Record<string, boolean>>(sessionSlot("simulator", "sections.user"))).toEqual({});
    // ...and the DOM says so, which is what a spec reads to tell "open" from "will stay open".
    expect(container.querySelector("[data-fill-section]")?.getAttribute("data-fill-user")).toBeNull();
  });

  it("data-fill-user names whose decision the state is", () => {
    act(() => root.render(<Page />));
    const section = () => container.querySelector("[data-fill-section]") as HTMLElement;
    act(() => trigger().click());
    expect(section().getAttribute("data-fill-user")).toBe("closed");
    act(() => trigger().click());
    expect(section().getAttribute("data-fill-user")).toBe("open");
    // Across the unmount navigation causes, too — the attribute is read off the session bag.
    act(() => root.render(<div />));
    act(() => root.render(<Page />));
    expect(section().getAttribute("data-fill-user")).toBe("open");
  });
});

describe("attachScrollMemory", () => {
  /**
   * A div whose `scrollTop` clamps to `max`, which is what the browser does and jsdom does not:
   * the page mounts short, so the first assignment cannot land and the offset has to be re-applied
   * as the content grows. Without the clamp this test would pass on code that only ever assigns
   * once — the exact bug it exists to catch.
   */
  function clampingScroller(max: number) {
    const el = document.createElement("div");
    let value = 0;
    let limit = max;
    Object.defineProperty(el, "scrollTop", {
      get: () => value,
      set: (v: number) => {
        value = Math.max(0, Math.min(v, limit));
      },
    });
    return { el, grow: (to: number) => (limit = to) };
  }

  it("re-applies the saved offset until the content is tall enough to hold it", () => {
    const { el, grow } = clampingScroller(0);
    let stored: number | undefined = 220;
    const memory = attachScrollMemory(el, () => stored, (v) => (stored = v));

    // Mounted short: nothing to scroll yet, so the browser clamped the restore to 0.
    expect(el.scrollTop).toBe(0);
    grow(120);
    memory.retry();
    expect(el.scrollTop).toBe(120); // still clamped — the sections have not all opened
    grow(400);
    memory.retry();
    expect(el.scrollTop).toBe(220); // landed
    memory.dispose();
  });

  it("stops restoring the moment the user scrolls, and records where they went", () => {
    const { el, grow } = clampingScroller(60);
    let stored: number | undefined = 220;
    const memory = attachScrollMemory(el, () => stored, (v) => (stored = v));
    expect(el.scrollTop).toBe(60); // clamped: the restore has not landed yet

    el.dispatchEvent(new Event("wheel"));
    el.scrollTop = 40;
    el.dispatchEvent(new Event("scroll"));
    expect(stored).toBe(40);

    // A later content resize must not drag them back to the stored offset.
    grow(400);
    memory.retry();
    expect(el.scrollTop).toBe(40);
    memory.dispose();
  });

  it("gives up at the deadline rather than yanking the view down for ever", () => {
    const { el, grow } = clampingScroller(0);
    let clock = 0;
    const memory = attachScrollMemory(el, () => 220, () => undefined, () => clock);

    clock = 5_000;
    grow(400);
    memory.retry();
    expect(el.scrollTop).toBe(0);
    memory.dispose();
  });

  it("does not record the browser's clamped values while a restore is in flight", () => {
    const { el, grow } = clampingScroller(0);
    const writes: number[] = [];
    const memory = attachScrollMemory(el, () => 220, (v) => writes.push(v));

    // The scroll events a growing page emits on its own, before the offset can land.
    grow(120);
    memory.retry();
    el.dispatchEvent(new Event("scroll"));
    expect(writes).toEqual([]);

    grow(400);
    memory.retry();
    el.dispatchEvent(new Event("scroll"));
    expect(writes).toEqual([220]);
    memory.dispose();
  });
});

describe("state that is not the user's is still local", () => {
  it("usePageSession is a drop-in for useState, so a transient can stay useState", () => {
    // A compile-time statement as much as a runtime one: the two signatures must match, which is
    // what makes "session-scope the user's decisions, leave the transients alone" a one-line
    // change per field rather than a rewrite.
    const a: typeof useState<number> = useState;
    const b = usePageSession<number>;
    expect(typeof a).toBe("function");
    expect(typeof b).toBe("function");
  });
});

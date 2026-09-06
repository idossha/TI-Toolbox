// @vitest-environment jsdom
/**
 * The run pane's controller: the render loop lane SCC measured, asserted at its two causes, and
 * the wrapper that worked around it kept deleted.
 *
 * SCC measured **720 renders in 2 s** on the Optimizer against 5 with the controller removed
 * (`scc-notes.md` §4.2). It was not a visible freeze — what it broke was the page's 400 ms plan
 * debounce, so `POST /api/plan/flex` was never sent and the digest stayed on "Resolving the
 * plan…" for ever. That is exactly why it needs a number: nothing about it is visible on screen.
 *
 * Two causes, both fixed in `ui/Layout.tsx` by lane LAY, both asserted here:
 *
 *   1. the pane's `ResizeObserver` reported the CONTENT box while `attach` seeded `measured` from
 *      the BORDER box. `.page-layout-run .page-layout-panel` has `padding-left: var(--space-3)`,
 *      so on a run page the two disagreed by 12 px and every disagreement re-rendered the page;
 *   2. `PageLayout` attached the controller from an INLINE ref callback, so React called
 *      `attach(null)` then `attach(el)` on every commit, rebuilding the observer each time — the
 *      loop's other half.
 *
 * `pages/_shared/run/useRunPaneController.ts` existed only to paper over (2) from the page side.
 * Three lanes (LAY, FIX-C, FIX-D) asked for its deletion once the cause was fixed; the last test
 * here is what keeps it deleted, because dead code that still compiles comes back.
 */
import React, { act, useState } from "react";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { PageLayout, usePaneController } from "../../src/renderer/ui/Layout";

const SRC = resolve(__dirname, "../../src/renderer");

/** The run shape's numbers: the pane is 400 px wide and 12 px of that is its own left padding. */
const BORDER_BOX = 400;
const PADDING_LEFT = 12;

interface FakeEntry {
  target: Element;
  contentRect: { width: number };
  borderBoxSize?: { inlineSize: number }[];
}

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  static observeCalls = 0;
  /** Emulate an engine without `borderBoxSize` (jsdom's own case) to exercise the fallback. */
  static withBorderBoxSize = false;
  /**
   * Observers with a delivery owed. A real `ResizeObserver` calls back once with the element's
   * current size as soon as `observe()` is called — which is what made the defect a *loop*:
   * re-attaching on every commit bought another delivery, which changed state, which committed.
   */
  static pending = new Set<FakeResizeObserver>();
  /** How many callbacks `drain()` has delivered — the loop's own counter. */
  static deliveries = 0;
  targets: Element[] = [];
  disconnected = false;
  constructor(private readonly callback: (entries: FakeEntry[]) => void) {
    FakeResizeObserver.instances.push(this);
  }
  observe(el: Element): void {
    this.targets.push(el);
    FakeResizeObserver.observeCalls++;
    FakeResizeObserver.pending.add(this);
  }
  disconnect(): void {
    this.disconnected = true;
    FakeResizeObserver.pending.delete(this);
  }
  /** What a real observer delivers: the CONTENT box, 12 px narrower than the element. */
  deliver(): void {
    if (this.disconnected) return;
    FakeResizeObserver.deliveries++;
    this.callback(
      this.targets.map((target) => ({
        target,
        contentRect: { width: BORDER_BOX - PADDING_LEFT },
        ...(FakeResizeObserver.withBorderBoxSize ? { borderBoxSize: [{ inlineSize: BORDER_BOX }] } : {}),
      })),
    );
  }
  /**
   * Run the callbacks the page is owed, and the callbacks those cause, until nothing is owed —
   * or until `cap` deliveries, which is the failure this whole file is about. A settled pane owes
   * one delivery per `observe()`; a looping one owes another on every commit, for ever.
   */
  static drain(cap = 200): void {
    while (FakeResizeObserver.pending.size > 0 && FakeResizeObserver.deliveries < cap) {
      const owed = [...FakeResizeObserver.pending];
      FakeResizeObserver.pending.clear();
      for (const observer of owed) observer.deliver();
    }
  }
}

let container: HTMLDivElement;
let root: Root;
let renders = 0;
let pageSeq = 0;
let pageId = "run-pane-0";

function Harness({ onBump }: { onBump: (bump: () => void) => void }) {
  renders++;
  const controller = usePaneController({ pageId, name: "run" });
  const [, setTick] = useState(0);
  onBump(() => setTick((t) => t + 1));
  return (
    <PageLayout paneController={controller} rightPane={<span>plan</span>}>
      work
    </PageLayout>
  );
}

/** The pane as the run shape lays it out: 400 px wide, 12 px of left padding. */
function sizePane(): void {
  const pane = container.querySelector<HTMLElement>('[data-testid="page-right-pane"]')!;
  pane.style.paddingLeft = `${PADDING_LEFT}px`;
  pane.getBoundingClientRect = () => ({ width: BORDER_BOX, height: 700, x: 0, y: 0, top: 0, left: 0, right: BORDER_BOX, bottom: 700, toJSON: () => ({}) }) as DOMRect;
}

beforeEach(() => {
  FakeResizeObserver.instances = [];
  FakeResizeObserver.observeCalls = 0;
  FakeResizeObserver.withBorderBoxSize = false;
  FakeResizeObserver.pending.clear();
  FakeResizeObserver.deliveries = 0;
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = FakeResizeObserver;
  // A fresh page id per test instead of clearing storage: jsdom's `localStorage` here has no
  // `clear()`, and a stored width would seed `measured` from the store rather than the element.
  pageId = `run-pane-${++pageSeq}`;
  renders = 0;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("usePaneController on a run pane — the 720-render loop, at both causes", () => {
  it("measures the border box the observer reports, not the content box inside its padding", () => {
    for (const supported of [false, true]) {
      FakeResizeObserver.withBorderBoxSize = supported;
      const widths: number[] = [];
      function Probe() {
        const controller = usePaneController({ pageId: `${pageId}-probe-${supported}`, name: "run" });
        widths.push(controller.measured);
        return (
          <PageLayout paneController={controller} rightPane={<span>plan</span>}>
            work
          </PageLayout>
        );
      }
      act(() => root.render(<Probe />));
      sizePane();
      act(() => FakeResizeObserver.drain());
      // 388 is the content box — the number the two sides disagreed by 12px over, and the loop
      // was made of. Both engine paths (`borderBoxSize`, and the `contentRect` + padding
      // fallback jsdom takes) must land on the element's own 400px.
      expect(widths.at(-1)).toBe(BORDER_BOX);
      // …and never passes through it on the way: an oscillation between the two boxes is the
      // loop itself, and a test that only reads the final value can watch it happen and pass.
      expect(widths).not.toContain(BORDER_BOX - PADDING_LEFT);
    }
  });

  it("attaches the pane once per element, however many times the page re-renders", () => {
    let bump = () => {};
    act(() => root.render(<Harness onBump={(b) => (bump = b)} />));
    sizePane();
    expect(FakeResizeObserver.observeCalls).toBe(1);

    // 20 commits of the page. An inline ref callback would re-attach on every one of them —
    // `attach(null)` then `attach(el)` — rebuilding the observer and buying another delivery.
    for (let i = 0; i < 20; i++) act(() => bump());
    expect(FakeResizeObserver.observeCalls).toBe(1);
    expect(FakeResizeObserver.instances).toHaveLength(1);
  });

  it("settles: the measurement arrives once and stops asking to be re-delivered", () => {
    act(() => root.render(<Harness onBump={() => {}} />));
    sizePane();
    // `drain` keeps calling back for as long as the page keeps re-observing. A settled pane owes
    // exactly one delivery; the defect owed one per commit, for ever — SCC's 720 renders in 2s.
    act(() => FakeResizeObserver.drain());
    expect(FakeResizeObserver.deliveries).toBe(1);

    const settled = renders;
    for (let i = 0; i < 10; i++) act(() => FakeResizeObserver.instances.forEach((o) => o.deliver()));
    // Ten more deliveries of the SAME size. React may re-render once before bailing out of a
    // no-op state write, so the bound is linear in events — never a cascade.
    expect(renders - settled).toBeLessThanOrEqual(10);
    expect(FakeResizeObserver.observeCalls).toBe(1);
  });

  it("stays bounded when commits and observer ticks interleave", () => {
    let bump = () => {};
    act(() => root.render(<Harness onBump={(b) => (bump = b)} />));
    sizePane();
    act(() => FakeResizeObserver.drain());
    const settled = renders;
    for (let i = 0; i < 25; i++) {
      act(() => bump());
      act(() => FakeResizeObserver.drain());
    }
    // 25 commits asked for, plus at most one bail-out render per delivery: linear in what the
    // test did, not in what the page did to itself.
    expect(renders - settled).toBeLessThanOrEqual(50);
    expect(FakeResizeObserver.deliveries).toBe(1);
  });
});

describe("the wrapper that worked around it stays deleted", () => {
  function sources(dir: string): string[] {
    const out: string[] = [];
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) out.push(...sources(path));
      else if (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx")) out.push(path);
    }
    return out;
  }

  it("no file names `useRunPaneController` — the run pages call `usePaneController` directly", () => {
    const hits: string[] = [];
    for (const path of sources(SRC)) {
      const text = readFileSync(path, "utf8");
      if (text.includes("useRunPaneController")) hits.push(relative(SRC, path));
    }
    expect(hits).toEqual([]);
  });

  it("all three run pages ask for the same pane: `{ pageId, name: \"run\" }`", () => {
    for (const [file, pageId] of [
      ["pages/optimizer/index.tsx", "optimizer"],
      ["pages/simulator/index.tsx", "simulator"],
      ["pages/analyzer/AnalyzerPage.tsx", "analyzer"],
    ] as const) {
      const text = readFileSync(join(SRC, file), "utf8");
      expect(text).toContain(`usePaneController({ pageId: "${pageId}", name: "run" })`);
    }
  });
});

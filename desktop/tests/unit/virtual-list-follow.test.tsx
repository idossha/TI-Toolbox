// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VirtualList } from "../../src/renderer/ui/VirtualList";

let container: HTMLDivElement;
let root: Root;
let viewportHeight: number;
const observers = new Set<ResizeObserverStub>();
class ResizeObserverStub {
  constructor(readonly callback: ResizeObserverCallback) { observers.add(this); }
  observe(): void {}
  unobserve(): void {}
  disconnect(): void { observers.delete(this); }
}
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  viewportHeight = 90;
  // jsdom has no layout: use the fixed-height spacer committed by the real virtualizer.
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(function (this: HTMLElement) {
    return parseFloat((this.firstElementChild as HTMLElement | null)?.style.height ?? "0") || 0;
  });
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(() => viewportHeight);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  observers.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
async function render(items: number[], followTail = true): Promise<HTMLDivElement> {
  await act(async () => root.render(
    <VirtualList items={items} rowHeight={18} followTail={followTail} renderRow={(item) => <span>{item}</span>} />,
  ));
  return container.querySelector<HTMLDivElement>(".virtual-list")!;
}
async function scroll(viewport: HTMLDivElement, top: number): Promise<void> {
  await act(async () => {
    viewport.scrollTop = top;
    viewport.dispatchEvent(new Event("scroll"));
  });
}
const lines = Array.from({ length: 20 }, (_, index) => index);
describe("VirtualList Follow tail", () => {
  it("follows appended output in the actual viewport while preserving horizontal position", async () => {
    const viewport = await render(lines);
    expect(viewport.scrollTop).toBe(270);
    await scroll(viewport, 36);
    viewport.scrollLeft = 120;
    await render([...lines, 20]);
    expect(viewport.scrollTop).toBe(288);
    expect(viewport.scrollLeft).toBe(120);
  });
  it("preserves reading position when off and follows immediately when enabled", async () => {
    const viewport = await render(lines, false);
    await scroll(viewport, 36);
    const updated = [...lines, 20];
    await render(updated, false);
    expect(viewport.scrollTop).toBe(36);
    await render(updated, true);
    expect(viewport.scrollTop).toBe(288);
  });
  it("follows a saturated buffer and filtered transcript changes", async () => {
    const viewport = await render(lines);
    await scroll(viewport, 18);
    await render([...lines.slice(1), 20]);
    expect(viewport.scrollTop).toBe(270);
    await render(lines.slice(0, 10));
    expect(viewport.scrollTop).toBe(90);
    await render(lines.slice(0, 2));
    expect(viewport.scrollTop).toBe(0);
    await render(lines);
    expect(viewport.scrollTop).toBe(270);
  });
  it("follows viewport resizing only while enabled", async () => {
    const viewport = await render(lines);
    viewportHeight = 180;
    const notifyResize = (): void => {
      for (const observer of observers) observer.callback([], observer as unknown as ResizeObserver);
    };
    await act(async () => notifyResize());
    expect(viewport.scrollTop).toBe(180);
    await render(lines, false);
    await scroll(viewport, 36);
    viewportHeight = 90;
    await act(async () => notifyResize());
    expect(viewport.scrollTop).toBe(36);
  });
});

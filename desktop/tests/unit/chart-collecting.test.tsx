// @vitest-environment jsdom
/**
 * `LineChart` shows a "Collecting…" skeleton until it has enough samples to draw a line, instead
 * of mounting uPlot with axes and nothing on them (ra_12 #29). uPlot itself is mocked — it needs a
 * real canvas 2D context, which jsdom doesn't provide — so this only exercises `Chart.tsx`'s own
 * branch: below `CHART_MIN_SAMPLES` render the skeleton and never construct the chart; at or above
 * it, construct exactly once and hide the skeleton.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const constructed: unknown[][] = [];
class FakeUPlot {
  static instances: FakeUPlot[] = [];
  constructor(...args: unknown[]) {
    constructed.push(args);
    FakeUPlot.instances.push(this);
  }
  setSize() {}
  setData() {}
  destroy() {}
}

vi.mock("uplot", () => ({ default: FakeUPlot }));
vi.mock("uplot/dist/uPlot.min.css", () => ({}));

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

describe("LineChart — collecting-samples skeleton", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    constructed.length = 0;
    FakeUPlot.instances = [];
    (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = FakeResizeObserver;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function renderChart(timestamps: number[], values: number[]) {
    const { LineChart } = await import("../../src/renderer/ui/Chart");
    act(() => {
      root.render(<LineChart timestamps={timestamps} values={values} label="CPU" />);
    });
  }

  it("shows the skeleton and never constructs uPlot with zero samples", async () => {
    await renderChart([], []);
    expect(container.querySelector(".chart-collecting")).not.toBeNull();
    expect(container.textContent).toContain("Collecting cpu…");
    expect(constructed).toHaveLength(0);
  });

  it("still shows the skeleton with exactly one sample — a single point has no line to draw", async () => {
    await renderChart([1000], [42]);
    expect(container.querySelector(".chart-collecting")).not.toBeNull();
    expect(constructed).toHaveLength(0);
  });

  it("constructs the chart and hides the skeleton once there are two samples", async () => {
    await renderChart([1000, 1001], [42, 43]);
    expect(constructed).toHaveLength(1);
    expect(container.querySelector(".chart-collecting")).toBeNull();
  });

  it("does not reconstruct the chart on further updates, only setData", async () => {
    const { LineChart } = await import("../../src/renderer/ui/Chart");
    act(() => {
      root.render(<LineChart timestamps={[1000, 1001]} values={[42, 43]} label="CPU" />);
    });
    expect(constructed).toHaveLength(1);
    act(() => {
      root.render(<LineChart timestamps={[1000, 1001, 1002]} values={[42, 43, 44]} label="CPU" />);
    });
    expect(constructed).toHaveLength(1); // same instance, updated in place
  });
});

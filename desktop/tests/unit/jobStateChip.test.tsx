// @vitest-environment jsdom
/** JobStateChip renders exactly one dot even for a running job with a known liveness — it used to
 * render its own leading `.chip-dot` plus a second, separate `StatusDot` (ra_12 #17). */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { JobStateChip } from "../../src/renderer/ui/Status";

function countDots(el: Element): number {
  return el.querySelectorAll(".chip-dot, .status-dot").length;
}

describe("JobStateChip", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("running + active (pulse=true): exactly one dot, and it pulses", () => {
    act(() => root.render(<JobStateChip state="running" pulse={true} />));
    const chip = container.querySelector(".chip")!;
    expect(countDots(chip)).toBe(1);
    expect(chip.querySelector(".chip-dot")!.className).toContain("chip-dot-pulse");
    expect(chip.getAttribute("title")).toBe("active");
  });

  it("running + stalled (pulse=false): exactly one dot, and it does not pulse", () => {
    act(() => root.render(<JobStateChip state="running" pulse={false} />));
    const chip = container.querySelector(".chip")!;
    expect(countDots(chip)).toBe(1);
    expect(chip.querySelector(".chip-dot")!.className).not.toContain("chip-dot-pulse");
    expect(chip.getAttribute("title")).toBe("stalled");
  });

  it("running with liveness unknown (pulse undefined): one dot, no title, no pulse", () => {
    act(() => root.render(<JobStateChip state="running" />));
    const chip = container.querySelector(".chip")!;
    expect(countDots(chip)).toBe(1);
    expect(chip.hasAttribute("title")).toBe(false);
  });

  it("a terminal state (succeeded) still shows exactly one, non-pulsing dot", () => {
    act(() => root.render(<JobStateChip state="succeeded" />));
    const chip = container.querySelector(".chip")!;
    expect(countDots(chip)).toBe(1);
    expect(chip.querySelector(".chip-dot")!.className).not.toContain("chip-dot-pulse");
  });
});

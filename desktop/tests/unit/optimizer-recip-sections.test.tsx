// @vitest-environment jsdom
/**
 * The reciprocity Search section, rendered offscreen (jsdom: no window, no focus, no screen — the
 * hidden-by-default rule in `docs/dev/TESTING.md`).
 *
 * What it pins is the one conditional the brief spells out — the weight is shown **only** for the
 * focality objective — plus the direction vector's own conditional and the fact that the cost line
 * the user reads is the same `recipCost()` the digest reads.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { RecipSearchSection } from "../../src/renderer/pages/optimizer/RecipSections";
import { defaultRecipFormState, type RecipFormState } from "../../src/renderer/pages/optimizer/recipConfig";

let container: HTMLDivElement;
let root: Root;
let form: RecipFormState;

/** Radix's slider measures its thumb; jsdom has no `ResizeObserver`, and no layout to report. */
class NoopResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= NoopResizeObserver as unknown as typeof ResizeObserver;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  form = defaultRecipFormState();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

/** Renders the section against the current `form`, patching it the way the row editor does. */
function render(): void {
  act(() =>
    root.render(
      <RecipSearchSection
        form={form}
        onChange={(patch) => {
          form = { ...form, ...patch };
          render();
        }}
      />,
    ),
  );
}

function segment(label: string): HTMLElement {
  const match = [...container.querySelectorAll<HTMLElement>("button")].find((b) => b.textContent?.trim() === label);
  if (!match) throw new Error(`No control labelled "${label}" — have: ${[...container.querySelectorAll("button")].map((b) => b.textContent).join(" | ")}`);
  return match;
}

const weight = () => container.querySelector('[data-testid="recip-focality-weight"]');
const cost = () => container.querySelector('[data-testid="optimizer-cost-recip"]')?.textContent;

describe("the reciprocity Search section", () => {
  it("shows the weight only while the objective is focality", () => {
    render();
    expect(weight()).toBeNull();
    act(() => segment("Focality").click());
    expect(form.objective).toBe("focality");
    expect(weight()).not.toBeNull();
    act(() => segment("Intensity").click());
    expect(form.objective).toBe("intensity");
    expect(weight()).toBeNull();
  });

  it("asks for a vector only when the direction is not 'any'", () => {
    render();
    expect(container.querySelector('input[aria-label="X coordinate"]')).toBeNull();
    act(() => segment("Along a vector").click());
    expect(form.directionMode).toBe("vector");
    expect(container.querySelector('input[aria-label="X coordinate"]')).not.toBeNull();
  });

  it("states the candidate ceiling, and restates it when the channel count changes", () => {
    render();
    expect(cost()).toBe("top 40 pairs · 2 channels · at most 780 candidates");
    act(() => segment("4 (mTI)").click());
    expect(form.nChannels).toBe(4);
    // C(20,4) is 4 845, over the runner's 1 000-candidate cap, so the line states the cap.
    expect(cost()).toBe("top 20 pairs · 4 channels · at most 1,000 candidates");
  });
});

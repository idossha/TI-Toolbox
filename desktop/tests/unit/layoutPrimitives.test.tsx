// @vitest-environment jsdom
/** Stack/Cluster/KeyValue (ra_12 #28) — replace the repeated inline flex/gap style objects with
 * fixed, token-backed classes; assert the class names a page actually gets, not just that it
 * renders. */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Cluster, KeyValue, Stack } from "../../src/renderer/ui/Layout";

describe("Stack / Cluster / KeyValue", () => {
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
  function render(el: React.ReactElement) {
    act(() => root.render(el));
  }

  it("Stack: defaults to gap-3, no inline style, adds an align class only when asked", () => {
    render(
      <Stack>
        <span>a</span>
      </Stack>,
    );
    const el = container.firstElementChild as HTMLElement;
    expect(el.className.split(" ")).toEqual(expect.arrayContaining(["stack", "gap-3"]));
    expect(el.getAttribute("style")).toBeNull();
    expect(el.className).not.toMatch(/items-/);
  });

  it("Stack: gap is one of the fixed --space-N steps, reflected as a gap-N class", () => {
    render(
      <Stack gap={6} align="center">
        <span>a</span>
      </Stack>,
    );
    const el = container.firstElementChild as HTMLElement;
    expect(el.className).toContain("gap-6");
    expect(el.className).toContain("items-center");
  });

  it("Cluster: wraps by default, no justify class unless given", () => {
    render(
      <Cluster>
        <span>a</span>
      </Cluster>,
    );
    const el = container.firstElementChild as HTMLElement;
    expect(el.className).toContain("cluster");
    expect(el.className).toContain("gap-2"); // default
    expect(el.className).toContain("items-center"); // default align
    expect(el.className).not.toContain("cluster-nowrap");
  });

  it("Cluster: wrap=false adds cluster-nowrap; justify maps to a single class", () => {
    render(
      <Cluster wrap={false} justify="between">
        <span>a</span>
      </Cluster>,
    );
    const el = container.firstElementChild as HTMLElement;
    expect(el.className).toContain("cluster-nowrap");
    expect(el.className).toContain("justify-between");
  });

  it("KeyValue: renders the label and value with the caption/value classes", () => {
    render(<KeyValue label="CPUs" value={8} />);
    const label = container.querySelector(".kv-item-label")!;
    const value = container.querySelector(".kv-item-value")!;
    expect(label.textContent).toBe("CPUs");
    expect(value.textContent).toBe("8");
  });
});

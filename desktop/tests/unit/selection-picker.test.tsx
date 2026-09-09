// @vitest-environment jsdom
import React, { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { SelectionPicker, type SelectionMode } from "../../src/renderer/ui/SelectionList";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const items = [
  { id: "a", label: "Alpha" },
  { id: "b", label: "Beta" },
  { id: "c", label: "Gamma" },
  { id: "x", label: "Unavailable", disabled: true },
];
function Picker({ mode = "multi" }: { mode?: SelectionMode }) {
  const [value, onChange] = useState<string[]>([]);
  return <SelectionPicker items={items} value={value} onChange={onChange} mode={mode} label="Electrodes" />;
}

describe("multi-selection picker rows", () => {
  let root: Root;
  let container: HTMLDivElement;
  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });
  function click(element: Element, options: MouseEventInit = {}) {
    act(() => element.dispatchEvent(new MouseEvent("click", { bubbles: true, ...options })));
  }
  function row(id: string) {
    return document.querySelector(`[data-testid="selection-row-${id}"]`)!;
  }
  function selected() {
    return [...document.querySelectorAll('[role="option"][aria-selected="true"]')]
      .map((element) => element.getAttribute("data-option-value"));
  }
  function open(mode: SelectionMode = "multi") {
    act(() => root.render(<Picker mode={mode} />));
    click(container.querySelector('[role="combobox"]')!);
  }
  it("adds and removes by clicking label or row space, and checkbox toggles exactly once", () => {
    open();
    click(row("a").querySelector(".selection-label")!);
    click(row("b"));
    expect(selected()).toEqual(["a", "b"]);
    click(row("a"));
    expect(selected()).toEqual(["b"]);
    click(row("c").querySelector('[role="checkbox"]')!);
    expect(selected()).toEqual(["b", "c"]);
    click(row("c").querySelector('[role="checkbox"]')!);
    expect(selected()).toEqual(["b"]);
    click(row("x"));
    expect(selected()).toEqual(["b"]);
  });
  it("preserves Shift ranges and listbox keyboard toggles", () => {
    open();
    click(row("a"));
    click(row("c"), { shiftKey: true });
    expect(selected()).toEqual(["a", "b", "c"]);
    const list = document.querySelector('[role="listbox"]')!;
    act(() => list.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true })));
    expect(selected()).toEqual(["a", "b"]);
    act(() => list.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    expect(selected()).toEqual(["a", "b", "c"]);
  });
  it("keeps single-select pickers limited to one value", () => {
    open("single");
    click(row("a"));
    click(row("b"));
    expect(selected()).toEqual(["b"]);
  });
});

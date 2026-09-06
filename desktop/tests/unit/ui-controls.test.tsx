// @vitest-environment jsdom
import React, { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PageActivityContext } from "../../src/renderer/app/pageActivity";
import { clearPageSession } from "../../src/renderer/app/pageSession";
import { SubjectsField } from "../../src/renderer/pages/_shared/subjects/SubjectsField";
import { Combobox, MultiSelect } from "../../src/renderer/ui/Combobox";
import { Dialog, Popover } from "../../src/renderer/ui/Overlay";
import { Checkbox, Slider } from "../../src/renderer/ui/Toggle";

let container: HTMLDivElement;
let root: Root;
const scrollIntoViewDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  // jsdom has no layout; this suite exercises keyboard and value behavior, not dimensions.
  vi.stubGlobal("ResizeObserver", class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: () => undefined });
  clearPageSession();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  if (scrollIntoViewDescriptor) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", scrollIntoViewDescriptor);
  else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  vi.unstubAllGlobals();
});

async function render(element: React.ReactElement) {
  await act(async () => root.render(element));
}

async function click(element: Element) {
  await act(async () => (element as HTMLElement).click());
}

describe("shared control accessibility", () => {
  it("names the subject checkbox and sends its new selection once", async () => {
    const change = vi.fn();
    await render(<Checkbox checked={false} onCheckedChange={change} aria-label="ernie" aria-describedby="reason" />);
    const checkbox = container.querySelector('[role="checkbox"]')!;
    expect(checkbox.getAttribute("aria-label")).toBe("ernie");
    expect(checkbox.getAttribute("aria-describedby")).toBe("reason");
    await click(checkbox);
    expect(change).toHaveBeenCalledExactlyOnceWith(true);
  });

  it("names the adjustable slider and its numeric value separately, and both change the same value", async () => {
    function Harness() {
      const [opacity, setOpacity] = useState(35);
      return <Slider value={opacity} onValueChange={setOpacity} aria-label="Skin opacity" unit="%" data-testid="skin" />;
    }
    await render(<Harness />);
    const slider = container.querySelector('[role="slider"]') as HTMLElement;
    expect(slider.getAttribute("aria-label")).toBe("Skin opacity");
    expect(slider.getAttribute("aria-valuetext")).toBe("35 %");
    await act(async () => {
      slider.focus();
      slider.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    });
    const input = container.querySelector('input[aria-label="Skin opacity value"]') as HTMLInputElement;
    expect(input.value).toBe("36");
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "150");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(slider.getAttribute("aria-valuenow")).toBe("100");
    expect(input.value).toBe("100");
  });

  it("a disabled multi-select cannot open or remove its existing selection", async () => {
    const change = vi.fn();
    await render(
      <MultiSelect disabled values={["F3"]} onValuesChange={change} options={[{ value: "F3", label: "F3" }]} aria-label="Electrodes" />,
    );
    const trigger = container.querySelector('[role="combobox"]') as HTMLElement;
    expect(trigger.getAttribute("aria-disabled")).toBe("true");
    await click(trigger);
    await act(async () => {
      trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    await click(container.querySelector('button[aria-label="Remove F3"]')!);
    expect(document.querySelector(".combobox-popover")).toBeNull();
    expect(change).not.toHaveBeenCalled();
    expect(trigger.textContent).toContain("F3");
  });

  it("a selected ineligible subject can still be cleared when no eligible subject exists", async () => {
    function Harness() {
      const [value, setValue] = useState(["101"]);
      return (
        <SubjectsField
          subjects={[{ id: "101" }]}
          value={value}
          onChange={setValue}
          eligibility={() => ({ ok: false, reason: "no head model" })}
          defaultOpen
        />
      );
    }
    await render(<Harness />);
    const disclosure = container.querySelector('[data-testid="subjects-change"]')!;
    expect(disclosure.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById(disclosure.getAttribute("aria-controls")!)).not.toBeNull();
    await click(container.querySelector('[data-testid="subject-row-101"] .checkbox-root')!);
    expect(container.querySelector('[data-testid="subjects-summary"]')!.textContent).toBe("No subjects selected");
    await click(disclosure);
    expect(disclosure.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("retained page portals", () => {
  it.each(["single", "multiple"] as const)("retains a %s picker filter across tab activity but clears it on deliberate close", async (kind) => {
    const options = [
      { value: "frontal-left", label: "Frontal left" },
      { value: "frontal-right", label: "Frontal right" },
      { value: "temporal-left", label: "Temporal left" },
    ];
    const change = vi.fn();
    const element = (active: boolean) => (
      <PageActivityContext.Provider value={active}>
        {kind === "single"
          ? <Combobox value={undefined} onValueChange={change} options={options} aria-label="Regions" />
          : <MultiSelect values={[]} onValuesChange={change} options={options} aria-label="Regions" />}
      </PageActivityContext.Provider>
    );
    const searchInput = () => document.querySelector<HTMLInputElement>(".combobox-search")!;
    const visibleOptions = () => Array.from(document.querySelectorAll('[role="option"]'), (option) => option.getAttribute("aria-label"));

    await render(element(true));
    const trigger = container.querySelector('[aria-label="Regions"]')!;
    await click(trigger);
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(searchInput(), "Frontal");
      searchInput().dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(searchInput().value).toBe("Frontal");
    expect(visibleOptions()).toEqual(["Frontal left", "Frontal right"]);

    await render(element(false));
    expect(document.querySelector(".combobox-popover")).toBeNull();
    await render(element(true));
    expect(searchInput().value).toBe("Frontal");
    expect(visibleOptions()).toEqual(["Frontal left", "Frontal right"]);

    await act(async () => searchInput().dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(document.querySelector(".combobox-popover")).toBeNull();
    await click(trigger);
    expect(searchInput().value).toBe("");
    expect(visibleOptions()).toEqual(options.map((option) => option.label));
    expect(change).not.toHaveBeenCalled();
  });

  it("hides a controlled dialog while its page is inactive without changing the page-owned open state", async () => {
    const onOpenChange = vi.fn();
    const element = (active: boolean) => (
      <PageActivityContext.Provider value={active}>
        <Dialog open onOpenChange={onOpenChange} title="Montage" description="Edit the current montage.">
          <input aria-label="Run name" value="kept draft" readOnly />
        </Dialog>
      </PageActivityContext.Provider>
    );
    await render(element(true));
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    await render(element(false));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(onOpenChange).not.toHaveBeenCalled();
    await render(element(true));
    expect((document.querySelector('input[aria-label="Run name"]') as HTMLInputElement).value).toBe("kept draft");
  });

  it("retains an uncontrolled popover's choice without showing it over another page", async () => {
    const element = (active: boolean) => (
      <PageActivityContext.Provider value={active}>
        <Popover trigger={<button type="button">Field help</button>}>Units are millimetres.</Popover>
      </PageActivityContext.Provider>
    );
    await render(element(true));
    await click(container.querySelector("button")!);
    expect(document.querySelector(".popover-content")?.textContent).toContain("Units are millimetres.");
    await render(element(false));
    expect(document.querySelector(".popover-content")).toBeNull();
    await render(element(true));
    expect(document.querySelector(".popover-content")?.textContent).toContain("Units are millimetres.");
  });
});

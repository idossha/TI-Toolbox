// @vitest-environment jsdom
/**
 * The help affordance is a **click** popover, not a hover tooltip.
 *
 * The maintainer's complaint was that the (i) looks clickable and was not, so these tests assert
 * the two halves of that: hovering opens nothing, and clicking opens a real `role="dialog"` with
 * `aria-expanded` on the trigger, dismissible by Esc, by an outside click and by a second click.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { HelpBody, HelpIcon, parseHelp, parseInline } from "../../src/renderer/ui/HelpPopover";

// Radix measures its content; jsdom has no layout engine and no ResizeObserver.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= RO;
(globalThis as unknown as { DOMRect: unknown }).DOMRect ??= class {};
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}

describe("mini-markdown", () => {
  it("splits bold and code out of a line, leaving the rest literal", () => {
    expect(parseInline("a **b** and `c` end")).toEqual([
      { kind: "text", value: "a " },
      { kind: "bold", value: "b" },
      { kind: "text", value: " and " },
      { kind: "code", value: "c" },
      { kind: "text", value: " end" },
    ]);
  });

  it("a line with no markers is one plain run", () => {
    expect(parseInline("plain")).toEqual([{ kind: "text", value: "plain" }]);
  });

  it("blank lines split paragraphs and a run of '- ' lines becomes one list", () => {
    expect(parseHelp("one\n\ntwo\n- a\n- b")).toEqual([
      { kind: "p", lines: ["one"] },
      { kind: "p", lines: ["two"] },
      { kind: "ul", items: ["a", "b"] },
    ]);
  });
});

describe("HelpIcon", () => {
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
  const render = (el: React.ReactElement) => act(() => root.render(el));
  const trigger = () => document.querySelector("[data-help-icon]") as HTMLElement;
  const popover = () => document.querySelector(".help-popover");

  const click = (el: HTMLElement) =>
    act(() => {
      el.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
      el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      el.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
      el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
      el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

  it("renders a focusable button with an accessible name and aria-expanded=false", () => {
    render(<HelpIcon title="Goal" text="What it maximises." />);
    const btn = trigger();
    expect(btn.tagName).toBe("BUTTON");
    expect(btn.getAttribute("aria-label")).toBe("Help");
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(btn.hasAttribute("disabled")).toBe(false);
  });

  it("hovering opens nothing — no popover, and no [role=tooltip] anywhere", () => {
    render(<HelpIcon title="Goal" text="What it maximises." />);
    const btn = trigger();
    act(() => {
      btn.dispatchEvent(new MouseEvent("pointerenter", { bubbles: true }));
      btn.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
      btn.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      btn.dispatchEvent(new FocusEvent("focus", { bubbles: true }));
    });
    expect(popover()).toBeNull();
    expect(document.querySelector("[role=tooltip]")).toBeNull();
  });

  it("clicking opens a dialog carrying the title and the help text", () => {
    render(<HelpIcon title="Goal" text="What it **maximises** inside the ROI." />);
    click(trigger());
    expect(popover()).not.toBeNull();
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    const content = document.querySelector("[data-radix-popper-content-wrapper] [role=dialog]") ?? popover()!.closest("[role=dialog]");
    expect(content).not.toBeNull();
    expect(popover()!.textContent).toContain("Goal");
    expect(popover()!.textContent).toContain("maximises");
    expect(popover()!.querySelector("strong")?.textContent).toBe("maximises");
  });

  it("Escape closes it", () => {
    render(<HelpIcon title="Goal" text="Body." />);
    click(trigger());
    expect(popover()).not.toBeNull();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(popover()).toBeNull();
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
  });

  it("a click outside closes it", async () => {
    render(<HelpIcon title="Goal" text="Body." />);
    click(trigger());
    expect(popover()).not.toBeNull();
    // Radix registers its outside-pointerdown listener on a `setTimeout(0)`, so the layer has to
    // be given a turn of the event loop before the click can dismiss it.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    await act(async () => {
      document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
      document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
    });
    expect(popover()).toBeNull();
  });

  it("a second click on the trigger closes it (it is a toggle)", () => {
    render(<HelpIcon title="Goal" text="Body." />);
    click(trigger());
    expect(popover()).not.toBeNull();
    click(trigger());
    expect(popover()).toBeNull();
  });

  it("controlled open renders the content without any interaction", () => {
    render(<HelpIcon title="Goal" text="Body." open onOpenChange={() => {}} />);
    expect(popover()!.textContent).toContain("Body.");
  });

  it("HelpBody renders lists and inline code as real elements", () => {
    render(<HelpBody text={"lead\n\n- `a` first\n- second"} />);
    expect(container.querySelectorAll(".help-list li")).toHaveLength(2);
    expect(container.querySelector("code.help-code")?.textContent).toBe("a");
    expect(container.querySelector("p")?.textContent).toBe("lead");
  });
});

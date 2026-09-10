// @vitest-environment jsdom
/**
 * "Unmodified keys belong to whatever has focus" (plan §3, DESIGN.md §6.5). The rule exists for
 * the Tetravox canvas, whose own keys are bare letters and arrows, so the canvas case is the one
 * that must not regress: a page may also claim its unmodified keys with `data-keyboard-owner`.
 */
import { describe, expect, it } from "vitest";

// jsdom ships no `matchMedia`; `keyboard.ts` reaches the registry, which imports every page and
// so reaches uPlot, which calls it at module scope.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

const { isTypingTarget } = await import("../../src/renderer/app/keyboard");

function el(html: string): HTMLElement {
  const host = document.createElement("div");
  host.innerHTML = html;
  return host.firstElementChild as HTMLElement;
}

describe("isTypingTarget", () => {
  it("is true for the form controls that always owned their keys", () => {
    expect(isTypingTarget(el("<input>"))).toBe(true);
    expect(isTypingTarget(el("<textarea></textarea>"))).toBe(true);
    expect(isTypingTarget(el("<select></select>"))).toBe(true);
    // jsdom does not implement contenteditable, so `isContentEditable` is stamped on directly —
    // the branch under test is ours, not the DOM's.
    const editable = el("<div></div>");
    Object.defineProperty(editable, "isContentEditable", { value: true });
    expect(isTypingTarget(editable)).toBe(true);
  });

  it("is true for a canvas — a canvas is only ever focusable because something wants its keys", () => {
    expect(isTypingTarget(el('<canvas tabindex="0"></canvas>'))).toBe(true);
  });

  it("is true inside anything that claims its keys with data-keyboard-owner", () => {
    const owner = el('<div data-keyboard-owner><button>x</button></div>');
    expect(isTypingTarget(owner)).toBe(true);
    expect(isTypingTarget(owner.querySelector("button"))).toBe(true);
  });

  it("is false for ordinary chrome, so ? still opens the keyboard sheet from a nav row", () => {
    expect(isTypingTarget(el("<button>Run</button>"))).toBe(false);
    expect(isTypingTarget(el("<div></div>"))).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
    expect(isTypingTarget(window)).toBe(false);
  });
});

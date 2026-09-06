// @vitest-environment jsdom
/**
 * The icon rail (below 1440px, DESIGN.md §9) shows a 20px monogram mark instead of the full
 * "TI-Toolbox" wordmark, which used to wrap onto a second line at 56px wide (ra_12 #6).
 * `aria-label` on the wrapping `.nav-brand` div keeps the name available to assistive tech
 * regardless of which is visually shown — CSS decides that from the `.nav-rail-icons` class, so
 * this only asserts both spans exist with the right content/markup and the accessible name never
 * disappears.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../src/renderer/app/registry", () => ({
  useNavSections: () => [
    {
      id: "workflow",
      pinned: false,
      pages: [{ id: "subjects", title: "Subjects", icon: () => null, shortcut: "1" }],
    },
  ],
  // v3: the rail asks the registry whether the page on screen forces the icon rail
  // (`PageDef.railMode`), on top of the >=1440px label breakpoint.
  pageById: () => undefined,
}));

// jsdom has no `matchMedia`; the rail asks it whether it is the icon rail.
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

describe("NavRail brand", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("has both the collapsed mark and the full wordmark, with one accessible name on the wrapper", async () => {
    const { NavRail } = await import("../../src/renderer/app/NavRail");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <MemoryRouter>
          <NavRail />
        </MemoryRouter>,
      );
    });

    const brand = container.querySelector(".nav-brand")!;
    expect(brand.getAttribute("aria-label")).toBe("TI-Toolbox");

    const mark = brand.querySelector(".nav-brand-mark")!;
    const text = brand.querySelector(".nav-brand-text")!;
    expect(mark).not.toBeNull();
    expect(text).not.toBeNull();
    expect(text.textContent).toBe("TI-Toolbox");
    // The mark is a short glyph, not the full name — it must not itself carry a second,
    // conflicting accessible name that could ever be read alongside the wrapper's.
    expect(mark.getAttribute("aria-hidden")).toBe("true");
  });
});

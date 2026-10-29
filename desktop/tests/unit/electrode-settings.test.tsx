// @vitest-environment jsdom
/**
 * The shared ELECTRODES section's "?" and the leadfield's electrode label (2026-10-28).
 *
 * Pins: the "?" opens on click a popover with the diagram, the four terms, and both references —
 * the SimNIBS ELECTRODE page and Saturnino, Antunes & Thielscher 2015 (NeuroImage 120:25-35,
 * doi:10.1016/j.neuroimage.2015.06.067, title and authors read from Crossref) — opening in the
 * system browser (`window.tit.openExternal` in the app, a `target="_blank"` link in a browser,
 * which Electron's window-open handler also sends out). The URLs are typed here from the two pages
 * themselves, not read from the component. A leadfield with no sidecar is "electrode not recorded",
 * never today's defaults.
 * Reproduce: cd desktop && npx vitest run tests/unit/electrode-settings.test.tsx
 */
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { leadfieldElectrodeLabel } from "../../src/renderer/pages/optimizer/nets";

class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= RO;
(globalThis as unknown as { DOMRect: unknown }).DOMRect ??= class {};
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SIMNIBS = "https://simnibs.github.io/simnibs/build/html/documentation/sim_struct/electrode.html";
const PAPER = "https://www.sciencedirect.com/science/article/pii/S1053811915005728";

const click = (el: Element) =>
  act(() => {
    for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) el.dispatchEvent(new MouseEvent(type, { bubbles: true }));
  });

/** A fresh module graph, so `isElectron` (read once at import) sees this test's `window.tit`. */
async function renderHelp() {
  vi.resetModules();
  const React = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { ElectrodeHelp } = await import("../../src/renderer/pages/_shared/electrodes/ElectrodeSettings");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(ElectrodeHelp)));
  return () => {
    act(() => root.unmount());
    container.remove();
  };
}

describe("ElectrodeHelp", () => {
  let cleanup: (() => void) | undefined;
  afterEach(() => {
    cleanup?.();
    delete (window as unknown as { tit?: unknown }).tit;
  });

  it("opens on click with the diagram, the terms and both references as external links", async () => {
    cleanup = await renderHelp();
    expect(document.querySelector('[data-testid="electrode-help-content"]')).toBeNull();
    click(document.querySelector('[data-testid="electrode-help"]')!);
    const content = document.querySelector('[data-testid="electrode-help-content"]')!;
    expect(content).not.toBeNull();
    expect(content.querySelector("svg.electrode-diagram")).not.toBeNull();
    for (const term of ["Shape", "Dimensions", "Gel thickness", "Rubber"]) expect(content.textContent).toContain(term);
    const links = [...content.querySelectorAll("a")];
    expect(links.map((a) => a.getAttribute("href"))).toEqual([SIMNIBS, PAPER]);
    for (const a of links) {
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toBe("noreferrer");
    }
    expect(links[1]!.textContent).toContain("Saturnino, Antunes & Thielscher 2015");
  });

  it("in the app, each reference opens in the system browser", async () => {
    const openExternal = vi.fn();
    (window as unknown as { tit: unknown }).tit = { openExternal };
    cleanup = await renderHelp();
    click(document.querySelector('[data-testid="electrode-help"]')!);
    const buttons = [...document.querySelectorAll('[data-testid="electrode-help-content"] button.electrode-help-link')];
    expect(buttons).toHaveLength(2);
    for (const b of buttons) click(b);
    expect(openExternal.mock.calls).toEqual([[SIMNIBS], [PAPER]]);
  });
});

describe("leadfieldElectrodeLabel", () => {
  it("names the recorded electrode, and says when there is none", () => {
    const recorded = { electrode_shape: "rect" as const, electrode_dimensions: [12, 6], gel_thickness: 2.5, rubber_thickness: 2 };
    expect(leadfieldElectrodeLabel({ electrode: recorded })).toBe("rect 12×6 mm, gel 2.5 mm");
    expect(leadfieldElectrodeLabel({ electrode: null })).toBe("electrode not recorded");
    expect(leadfieldElectrodeLabel({})).toBe("electrode not recorded");
  });
});

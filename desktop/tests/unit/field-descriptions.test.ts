// @vitest-environment jsdom
/**
 * 2026-11-02: the Output fields link to the wiki instead of repeating it in tooltips (maintainer:
 * "instead of this dense tooltip we should just give the link to the place in the docs that
 * explains it").
 *
 * Pins, on the one form Job settings and Settings ▸ Simulator both render (`SimulationSettings`):
 * "Field definitions" beside the Output fields heading opens the wiki's field section, the
 * carrier-only control's "Read more" opens its section on the Simulator page, no output-field
 * checkbox carries a `title` tooltip, and the desktop registry copies no field description. What
 * the form still shows makes no compliance or exposure-limit claim (docs/dev/DECISIONS.md "Field
 * metrics are described, never ranked for compliance"); the Python registry's descriptions are held
 * to that rule by tests/test_field_registry.py::TestOutputFieldDefinitions.
 *
 * Where the values come from: the URLs are the wiki headings that define the fields,
 * docs/wiki/analyzer.md "Field quantities {#quantities-of-interest}" and docs/wiki/simulator.md
 * "Carrier-only control (ΔF = 0) {#carrier-only-control}", typed here (groundTruth: authored);
 * tests/test_docs_deeplinks.py checks that both anchors exist. The forbidden words are the
 * maintainer's request, not derived from the code.
 *
 * Run: cd desktop && npx vitest run tests/unit/field-descriptions.test.ts
 * Deliberately elsewhere: that the link opens the system browser in the app
 * (tests/e2e/simulator.spec.ts).
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { FIELD_REGISTRY } from "../../src/renderer/pages/analyzer/fields";
import { SimulationSettings } from "../../src/renderer/pages/simulator/SimulationSettings";
import { defaultJobSettings, OUTPUT_FIELDS, WRITE_NIFTIS_HELP } from "../../src/renderer/pages/simulator/types";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SITE = "https://idossha.github.io/TI-Toolbox/";
const FORBIDDEN = ["complian", "exposure", "icnirp", "limit"];

let root: Root | undefined;
function render(): HTMLElement {
  const host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(createElement(SimulationSettings, { value: defaultJobSettings(), onChange: () => {} })));
  return host;
}
afterEach(() => {
  if (root) act(() => root!.unmount());
  root = undefined;
  document.body.innerHTML = "";
});

const link = (host: HTMLElement, text: string) => [...host.querySelectorAll("a")].find((a) => a.textContent?.trim() === text);

describe("Output fields", () => {
  it("link the field definitions and the carrier-only control to the wiki", () => {
    const host = render();
    const fields = link(host, "Field definitions");
    expect(fields?.getAttribute("href")).toBe(`${SITE}wiki/analyzer/#quantities-of-interest`);
    expect(fields?.closest("h4")?.textContent).toContain("Output fields");
    const carrier = link(host, "Read more");
    expect(carrier?.getAttribute("href")).toBe(`${SITE}wiki/simulator/#carrier-only-control`);
    expect(carrier?.parentElement?.textContent).toContain("Carrier-only control");
    for (const a of [fields!, carrier!]) {
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toBe("noreferrer");
    }
  });

  it("show no description tooltip on any output field", () => {
    const host = render();
    expect(OUTPUT_FIELDS.length, "has output fields to check").toBeGreaterThanOrEqual(5);
    for (const f of OUTPUT_FIELDS) {
      const box = host.querySelector(`[aria-label="${f.name}"]`);
      expect(box, f.name).not.toBeNull();
      expect(box!.closest("label")!.hasAttribute("title"), f.name).toBe(false);
    }
    expect(FIELD_REGISTRY.filter((f) => "description" in f)).toEqual([]);
  });

  it("make no compliance or exposure-limit claim", () => {
    const host = render();
    const titles = [...host.querySelectorAll("[title]")].map((el) => el.getAttribute("title") ?? "");
    for (const text of [host.textContent ?? "", ...titles, WRITE_NIFTIS_HELP]) {
      expect(text.length).toBeGreaterThan(0);
      for (const word of FORBIDDEN) expect(text.toLowerCase()).not.toContain(word);
    }
  });
});

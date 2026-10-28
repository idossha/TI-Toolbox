// @vitest-environment jsdom
/**
 * The Ex/mEx current inputs take their range from the same bounds table the row gate reads
 * (package p05, 2026-10-22). `optimizer-ex-counts.test.ts` drives the gate (`rowFormReason`);
 * this file renders `ExCurrentSection` and `MExCarrierSection` and checks that each input's
 * `min`/`max` attributes are the table's and that an out-of-range value marks the input invalid
 * (`control-error`), so the input, its error mark and the gate cannot drift apart.
 *
 * Expected values: `EX_BOUNDS`/`MEX_BOUNDS` for the attributes (the point is that the inputs
 * read the table); 11 mA and -1 mA are outside every current bound by the table's own maxima
 * and by physics (a current is > 0). Reproduce: `npx vitest run tests/unit/optimizer-ex-bounds.test.tsx`.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { EX_BOUNDS, MEX_BOUNDS, type Bound } from "../../src/renderer/pages/optimizer/cost";
import { ExCurrentSection, MExCarrierSection } from "../../src/renderer/pages/optimizer/ExSections";
import { defaultExFormState, defaultMExFormState, type ExFormState, type MExFormState } from "../../src/renderer/pages/optimizer/exConfig";

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

/** The number input inside the `.field` whose label is *label*. */
function inputFor(label: string): HTMLInputElement {
  const field = [...container.querySelectorAll<HTMLElement>(".field")].find((f) => f.querySelector("label")?.textContent?.trim() === label);
  const input = field?.querySelector<HTMLInputElement>('input[type="number"]');
  if (!input) throw new Error(`no number input labelled ${label}`);
  return input;
}

function expectRange(input: HTMLInputElement, bound: Bound) {
  expect(input.getAttribute("min")).toBe(String(bound.min));
  expect(input.getAttribute("max")).toBe(String(bound.max));
}

function renderEx(patch: Partial<ExFormState>) {
  render(<ExCurrentSection form={{ ...defaultExFormState(), ...patch }} onChange={() => {}} />);
}

function renderMex(patch: Partial<MExFormState>) {
  render(<MExCarrierSection form={{ ...defaultMExFormState(), ...patch }} onChange={() => {}} />);
}

const EX_FIELDS = [
  ["totalCurrent", EX_BOUNDS.totalCurrent],
  ["currentStep", EX_BOUNDS.currentStep],
  ["channelLimit", EX_BOUNDS.channelLimit],
] as const;

describe("ExCurrentSection inputs read EX_BOUNDS", () => {
  it("gives Total current, Step and Channel limit the table's min and max", () => {
    renderEx({ totalCurrent: 2, currentStep: 0.2, channelLimit: 1.6 });
    for (const [, bound] of EX_FIELDS) expectRange(inputFor(bound.label), bound);
  });

  it("marks none of them invalid at in-range values or with the channel limit cleared", () => {
    renderEx({ totalCurrent: 2, currentStep: 0.2, channelLimit: null });
    for (const [, bound] of EX_FIELDS) expect(inputFor(bound.label).classList.contains("control-error"), bound.label).toBe(false);
  });

  it.each(EX_FIELDS.flatMap(([key, bound]) => [[key, bound.label, 11], [key, bound.label, -1]] as const))(
    "marks %s invalid at %s = %s mA, and only that input",
    (key, label, value) => {
      renderEx({ totalCurrent: 2, currentStep: 0.2, channelLimit: 1.6, [key]: value });
      for (const [, bound] of EX_FIELDS) {
        expect(inputFor(bound.label).classList.contains("control-error"), bound.label).toBe(bound.label === label);
      }
    },
  );
});

describe("MExCarrierSection's channel current reads MEX_BOUNDS", () => {
  it("gives Channel current the table's min and max", () => {
    renderMex({ currentMa: 2 });
    expectRange(inputFor(MEX_BOUNDS.currentMa.label), MEX_BOUNDS.currentMa);
  });

  it.each([
    [2, false],
    [11, true],
    [-1, true],
  ] as const)("pair current %s mA -> invalid %s", (currentMa, invalid) => {
    renderMex({ currentMa });
    expect(inputFor(MEX_BOUNDS.currentMa.label).classList.contains("control-error")).toBe(invalid);
  });
});

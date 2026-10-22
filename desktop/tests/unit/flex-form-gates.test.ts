// @vitest-environment jsdom
/**
 * The Optimizer's flex form refuses, with a sentence naming the field, every value FlexConfig
 * refuses — so a flex row the page lets run is one the server accepts (package p08, 2026-10-22).
 *
 * What it pins: `FLEX_BOUNDS` and `flexFormReason` (the row gate `rowFormReason` reads), the
 * thresholds rule for a fixed-threshold focality run, and the rendered inputs: each bounded input
 * carries the table's `min`/`max`, an out-of-range value marks it invalid with the reason under it,
 * and an ellipse electrode is one diameter (SimNIBS's flex electrode is a disc).
 *
 * Where the expected values come from (not from the code under test):
 *   - physics: a current, a size, a gel thickness and a distance are > 0 (0 is not a value);
 *   - FlexConfig (tit/opt/config.py): intensity weight in [0, 1], at least one restart, ratio
 *     levels >= 2, adaptive shares in (0, 100) with non-ROI < ROI, a min distance > 0;
 *   - SimNIBS `measures.ROC` (read from the v3.1.1 image) and the field's own help text: one
 *     threshold (non-ROI max = ROI min) or two (non-ROI max, ROI min), the first not above the
 *     second; a single focality run has no default threshold;
 *   - the input bounds the page already declared (51 ratio levels, 20 runs).
 * The Python half of the same table is tests/test_flexconfig_validation_edges.py.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/flex-form-gates.test.ts`.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defaultFlexFormState, flexFormReason, thresholdsReason, FLEX_BOUNDS, type FlexFormState } from "../../src/renderer/pages/optimizer/flexConfig";
import { rowFormReason } from "../../src/renderer/pages/optimizer/plan";
import { emptyOptimizerRow } from "../../src/renderer/pages/optimizer/rows";
import { ElectrodesSection, ObjectiveSection, SolverSection } from "../../src/renderer/pages/optimizer/FlexSections";
import { emptyRoi } from "../../src/renderer/pages/_shared/roi";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const form = (patch: Partial<FlexFormState>): FlexFormState => ({ ...defaultFlexFormState(), goal: "mean", ...patch });

describe("flexFormReason: the bounds table", () => {
  // [field, value that must be refused, a value just inside, the label the sentence must name]
  const CASES: [keyof FlexFormState, number, number, string, Partial<FlexFormState>?][] = [
    ["currentMA", 0, 0.1, "Current"],
    ["currentMA", -1, 2, "Current"],
    ["dimensionWidth", 0, 8, "Electrode width", { electrodeShape: "rect" }],
    ["dimensionHeight", 0, 6, "Electrode height", { electrodeShape: "rect" }],
    ["gelThickness", 0, 4, "Gel thickness"],
    ["minElectrodeDistance", 0, 0.5, "Min distance"],
    ["minElectrodeDistance", -3, 5, "Min distance"],
    ["intensityWeight", 1.5, 1, "Intensity preference", { goal: "focality_tf" }],
    ["intensityWeight", -0.1, 0, "Intensity preference", { goal: "focality_tf" }],
    ["nMultistart", 0, 1, "Optimization runs"],
    ["nMultistart", 1.5, 2, "Optimization runs"],
    ["nMultistart", 21, 20, "Optimization runs"],
    ["ratioLevels", 1, 2, "Ratio levels", { optimizeCurrentRatio: true }],
    ["ratioLevels", 52, 51, "Ratio levels", { optimizeCurrentRatio: true }],
    ["ratioTotalMA", 0, 0.5, "Ratio total current", { optimizeCurrentRatio: true }],
    ["adaptiveNonRoiPct", 0, 1, "Non-ROI share", { goal: "focality", focalityMode: "adaptive" }],
    ["adaptiveRoiPct", 100, 99, "ROI share", { goal: "focality", focalityMode: "adaptive" }],
  ];

  it.each(CASES)("%s = %s is refused naming the field; %s inside is accepted", (key, bad, good, label, extra) => {
    const refused = flexFormReason(form({ ...extra, [key]: bad }));
    expect(refused).not.toBeNull();
    expect(refused!.startsWith(label)).toBe(true);
    expect(flexFormReason(form({ ...extra, [key]: good }))).toBeNull();
  });

  it("names the unit and the side of the bound", () => {
    expect(flexFormReason(form({ currentMA: 0 }))).toBe("Current must be greater than 0 mA.");
    expect(flexFormReason(form({ goal: "focality_tf", intensityWeight: 1.5 }))).toBe("Intensity preference must be at most 1.");
    expect(flexFormReason(form({ goal: "focality", focalityMode: "adaptive", adaptiveRoiPct: 100 }))).toBe("ROI share must be less than 100%.");
  });

  it("does not let a field the form does not send block it", () => {
    // The weight is sent only for threshold-free focality; the ratio settings only with the box ticked.
    expect(flexFormReason(form({ goal: "mean", intensityWeight: 1.5 }))).toBeNull();
    expect(flexFormReason(form({ optimizeCurrentRatio: false, ratioLevels: 1, ratioTotalMA: 0 }))).toBeNull();
    expect(flexFormReason(form({ goal: "focality", focalityMode: "pareto", adaptiveRoiPct: 100 }))).toBeNull();
  });

  it("refuses an adaptive non-ROI share at or above the ROI share", () => {
    expect(flexFormReason(form({ goal: "focality", focalityMode: "adaptive", adaptiveNonRoiPct: 80, adaptiveRoiPct: 80 }))).toBe("The non-ROI share must be below the ROI share.");
  });

  it("refuses an unequal ellipse but not an unequal rectangle", () => {
    expect(flexFormReason(form({ electrodeShape: "ellipse", dimensionWidth: 8, dimensionHeight: 10 }))).toMatch(/^Unequal ellipse/);
    expect(flexFormReason(form({ electrodeShape: "rect", dimensionWidth: 10, dimensionHeight: 6 }))).toBeNull();
  });

  it("refuses a multi-threshold list FlexConfig.ParetoSweepConfig refuses, and never drops a token", () => {
    const pareto = (roi: string, non: string) => flexFormReason(form({ goal: "focality", focalityMode: "pareto", paretoRoiPcts: roi, paretoNonRoiPcts: non }));
    expect(pareto("80", "20,30,40")).toBeNull();
    expect(pareto("", "20")).toBe("ROI thresholds: enter at least one percentage.");
    expect(pareto("80,abc", "20")).toBe("ROI thresholds: 'abc' is not a percentage between 0 and 100.");
    expect(pareto("80", "20,100")).toBe("Non-ROI thresholds: '100' is not a percentage between 0 and 100.");
    expect(pareto("70,80", "20,70")).toBe("Every non-ROI threshold must be below every ROI threshold.");
  });

  it("is the flex branch of the row gate", () => {
    const row = emptyOptimizerRow({ subjectId: "001", method: "flex", flex: form({ minElectrodeDistance: 0 }) });
    expect(rowFormReason(row)).toBe("Min distance must be greater than 0 mm.");
    expect(rowFormReason({ ...row, flex: form({}) })).toBeNull();
  });
});

describe("thresholdsReason: a fixed-threshold focality run", () => {
  it.each(["", "   ", "dynamic", "AUTO"])("refuses the unset spelling %j: a single run has no default", (text) => {
    expect(thresholdsReason(text)).toBe("Enter the E-field thresholds: one value (non-ROI max = ROI min) or two (non-ROI max, ROI min) in V/m.");
  });

  it.each([
    ["0.1,", "Each threshold must be a number greater than 0 V/m."],
    ["nan", "Each threshold must be a number greater than 0 V/m."],
    ["Infinity", "Each threshold must be a number greater than 0 V/m."],
    ["-0.1", "Each threshold must be a number greater than 0 V/m."],
    ["0", "Each threshold must be a number greater than 0 V/m."],
    ["0.1,0.2,0.3", "Give one or two thresholds, not 3."],
    ["0.5,0.1", "The non-ROI maximum (first value) may not exceed the ROI minimum (second value)."],
  ])("refuses %j", (text, reason) => {
    expect(thresholdsReason(text)).toBe(reason);
  });

  it.each(["0.2", "0.1,0.3", "0.2,0.2", " 0.1 , 0.3 "])("accepts %j", (text) => {
    expect(thresholdsReason(text)).toBeNull();
  });

  it("gates the row only in fixed-threshold mode", () => {
    expect(flexFormReason(form({ goal: "focality", focalityMode: "manual", manualThresholds: "" }))).toMatch(/^Enter the E-field thresholds/);
    expect(flexFormReason(form({ goal: "focality", focalityMode: "adaptive", manualThresholds: "" }))).toBeNull();
    expect(flexFormReason(form({ goal: "focality_tf", manualThresholds: "" }))).toBeNull();
  });
});

// ---------------------------------------------------------------------------------------------
// Rendered inputs
// ---------------------------------------------------------------------------------------------
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

function fieldFor(label: string): HTMLElement {
  const field = [...container.querySelectorAll<HTMLElement>(".field")].find((f) => f.querySelector(".field-label-text")?.textContent?.trim() === label);
  if (!field) throw new Error(`no field labelled ${label}`);
  return field;
}

function numberIn(label: string): HTMLInputElement {
  const input = fieldFor(label).querySelector<HTMLInputElement>('input[type="number"]');
  if (!input) throw new Error(`no number input in ${label}`);
  return input;
}

function errorIn(label: string): string | null {
  return fieldFor(label).querySelector('[role="alert"]')?.textContent ?? null;
}

describe("ElectrodesSection", () => {
  it("gives each bounded input the table's min, and marks 0 mm min distance invalid with the reason", () => {
    render(React.createElement(ElectrodesSection, { form: form({ minElectrodeDistance: 0 }), onChange: () => {} }));
    expect(numberIn("Current").getAttribute("min")).toBe(String(FLEX_BOUNDS.currentMA.min));
    expect(numberIn("Min distance").getAttribute("min")).toBe(String(FLEX_BOUNDS.minElectrodeDistance.min));
    expect(numberIn("Min distance").getAttribute("aria-invalid")).toBe("true");
    expect(errorIn("Min distance")).toBe("Min distance must be greater than 0 mm.");
    expect(numberIn("Current").getAttribute("aria-invalid")).toBeNull();
    expect(errorIn("Current")).toBeNull();
  });

  it("shows an ellipse as one diameter that sets both dimensions", () => {
    const onChange = vi.fn();
    render(React.createElement(ElectrodesSection, { form: form({ electrodeShape: "ellipse", dimensionWidth: 8, dimensionHeight: 8 }), onChange }));
    expect(() => fieldFor("Dimensions (x, y)")).toThrow();
    const diameter = numberIn("Diameter");
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(diameter, "12");
      diameter.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(onChange).toHaveBeenLastCalledWith({ dimensionWidth: 12, dimensionHeight: 12 });
  });

  it("keeps width and height apart for a rectangle", () => {
    render(React.createElement(ElectrodesSection, { form: form({ electrodeShape: "rect", dimensionWidth: 10, dimensionHeight: 6 }), onChange: () => {} }));
    expect(fieldFor("Dimensions (x, y)").querySelectorAll('input[type="number"]')).toHaveLength(2);
    expect(() => fieldFor("Diameter")).toThrow();
  });

  it("switching a 10 x 6 rectangle to an ellipse keeps one diameter, the width", () => {
    const onChange = vi.fn();
    render(React.createElement(ElectrodesSection, { form: form({ electrodeShape: "rect", dimensionWidth: 10, dimensionHeight: 6 }), onChange }));
    const ellipse = [...container.querySelectorAll<HTMLElement>('[role="radio"], button')].find((b) => b.textContent?.trim() === "Ellipse");
    if (!ellipse) throw new Error("no Ellipse option");
    act(() => ellipse.click());
    expect(onChange).toHaveBeenLastCalledWith({ electrodeShape: "ellipse", dimensionHeight: 10 });
  });
});

describe("ObjectiveSection and SolverSection", () => {
  it("shows the blank fixed-threshold box's reason under it", () => {
    render(
      React.createElement(ObjectiveSection, {
        form: form({ goal: "focality", focalityMode: "manual", manualThresholds: "" }),
        onChange: () => {},
        nonRoi: emptyRoi("spherical"),
        onNonRoiChange: () => {},
        subject: "001",
      }),
    );
    expect(errorIn("E-field thresholds")).toBe("Enter the E-field thresholds: one value (non-ROI max = ROI min) or two (non-ROI max, ROI min) in V/m.");
  });

  it("marks 0 optimization runs invalid", () => {
    render(React.createElement(SolverSection, { form: form({ nMultistart: 0 }), onChange: () => {}, eegNets: [] }));
    expect(numberIn("Optimization runs").getAttribute("aria-invalid")).toBe("true");
    expect(errorIn("Optimization runs")).toBe("Optimization runs must be at least 1.");
  });
});

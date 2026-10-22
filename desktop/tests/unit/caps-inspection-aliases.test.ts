/**
 * The caps panel does not call a correct SPM12 cap collapsed (package p07, 2026-10-22).
 *
 * SimNIBS's EEG10-20_extended_SPM12 cap lists the four 10-20 sites that carry two names (T3/T7,
 * T4/T8, T5/P7, T6/P8; Oostenveld & Praamstra 2001, Table 1) at one point each, by design. A
 * server before this change reported those four pairs in `collapsed`, and the Inspect card told
 * the user to "re-apply or fix the cap". `inspectionWarnings` and the red markers now drop the
 * alias pairs whichever server answers; a real collapse (two different sites on one point, even
 * when each label is half of some alias pair) still warns. Fixtures are hand-written.
 */
import { describe, expect, it } from "vitest";
import { inspectionMarkers, inspectionWarnings, isAliasPair } from "../../src/renderer/pages/panels/caps/model";
import type { CapInspection } from "../../src/renderer/pages/panels/caps/api";
import { SCENE_CATEGORICAL } from "../../src/renderer/scene/palette";

const at = (name: string, world: [number, number, number]) => ({ name, world, nn_mm: 0, nn_name: name, scalp_mm: 0 });

const spm12 = (collapsed: CapInspection["collapsed"]): CapInspection => ({
  subject: "ernie",
  net: "EEG10-20_extended_SPM12.csv",
  collapse_mm: 2,
  electrodes: [at("T7", [-80, 0, 10]), at("T3", [-80, 0, 10]), at("P8", [70, -40, 10]), at("T6", [70, -40, 10]), at("Fz", [0, 60, 60])],
  collapsed,
  duplicate_names: [],
  summary: { count: 5, nn_min_mm: 0, nn_median_mm: 0, nn_max_mm: 60, scalp_median_mm: 0, scalp_max_mm: 0 },
  compare: null,
});

describe("caps inspection and the 10-20 alias pairs", () => {
  it("knows exactly the four synonym pairs, in either order", () => {
    const pairs: [string, string][] = [["T3", "T7"], ["T4", "T8"], ["T5", "P7"], ["T6", "P8"]];
    for (const [a, b] of pairs) {
      expect(isAliasPair(a, b)).toBe(true);
      expect(isAliasPair(b, a)).toBe(true);
    }
    expect(isAliasPair("T3", "T8")).toBe(false);
    expect(isAliasPair("T7", "P7")).toBe(false);
    expect(isAliasPair("T3", "T3")).toBe(false);
    expect(isAliasPair("Fz", "Cz")).toBe(false);
  });

  it("does not warn about a cap whose only coincident pairs are aliases", () => {
    const inspection = spm12([
      { a: "T7", b: "T3", distance_mm: 0 },
      { a: "P8", b: "T6", distance_mm: 0 },
    ]);
    expect(inspectionWarnings(inspection)).toEqual([]);
    expect(inspectionMarkers(inspection).map((m) => m.color)).toEqual(Array(5).fill(SCENE_CATEGORICAL[0]));
  });

  it("still warns about a real collapse beside the aliases, and counts only it", () => {
    const inspection = spm12([
      { a: "T7", b: "T3", distance_mm: 0 },
      { a: "T3", b: "T8", distance_mm: 0.4 },
    ]);
    expect(inspectionWarnings(inspection)).toEqual(["1 electrode pair closer than 2 mm: T3–T8 0.4 mm"]);
    const red = inspectionMarkers(inspection)
      .filter((m) => m.color === SCENE_CATEGORICAL[7])
      .map((m) => m.label);
    expect(red).toEqual(["T3"]);
  });
});

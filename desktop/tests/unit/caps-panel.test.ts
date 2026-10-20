/**
 * The EEG caps panel's pure core (`pages/panels/caps/model.ts`): which status a cap row shows,
 * which caps Apply would overwrite (the question the existing-outputs dialog asks), and how an
 * inspection becomes scene markers — collapsed electrodes in red, the compare net after the net so
 * marker index i is table row i. Expected values are hand-written fixtures, 2026-10-16.
 */
import { describe, expect, it } from "vitest";
import { appliedDate, capLabel, capStatus, existingAmong, inspectionMarkers, inspectionWarnings, reapplicable } from "../../src/renderer/pages/panels/caps/model";
import type { CapInspection, CapStatus } from "../../src/renderer/pages/panels/caps/api";
import { SCENE_CATEGORICAL } from "../../src/renderer/scene/palette";

const cap = (over: Partial<CapStatus>): CapStatus => ({
  name: "A.csv",
  source: "simnibs",
  on_subject: false,
  subject_mtime: null,
  ...over,
});

const inspection = (over: Partial<CapInspection> = {}): CapInspection => ({
  subject: "ernie",
  net: "A.csv",
  collapse_mm: 2,
  electrodes: [
    { name: "Fz", world: [0, 0, 1], nn_mm: 0.5, nn_name: "Cz", scalp_mm: 0 },
    { name: "Cz", world: [0.5, 0, 1], nn_mm: 0.5, nn_name: "Fz", scalp_mm: 0 },
    { name: "Pz", world: [0, -50, 1], nn_mm: 50, nn_name: "Fz", scalp_mm: 0 },
  ],
  collapsed: [{ a: "Fz", b: "Cz", distance_mm: 0.5 }],
  duplicate_names: [],
  summary: { count: 3, nn_min_mm: 0.5, nn_median_mm: 0.5, nn_max_mm: 50, scalp_median_mm: 0, scalp_max_mm: 0 },
  compare: null,
  ...over,
});

describe("caps panel model", () => {
  it("names each status", () => {
    expect(capStatus(cap({})).label).toBe("not on subject");
    expect(capStatus(cap({ on_subject: true })).label).toBe("on subject");
    // A source newer than the subject's copy is not a status: after an image update every cap is.
    expect(capStatus(cap({ on_subject: true, subject_mtime: 1 }))).toMatchObject({ label: "on subject", kind: "success" });
    expect(capStatus(cap({ on_subject: true, source: null })).title).toMatch(/cannot be re-applied/);
  });

  it("names a cap as the rest of the app names a net, and dates only what is on the subject", () => {
    expect(capLabel("GSN-HydroCel-185.csv")).toBe("GSN-HydroCel-185");
    expect(capLabel("GSN-HydroCel-185")).toBe("GSN-HydroCel-185");
    expect(appliedDate(cap({}))).toBe("—");
    expect(appliedDate(cap({ on_subject: true, subject_mtime: 1_760_000_000 }))).toBe(new Date(1_760_000_000_000).toLocaleDateString());
  });

  it("asks before overwriting only the caps already on the subject", () => {
    const caps = [cap({ name: "A.csv", on_subject: true }), cap({ name: "B.csv" }), cap({ name: "Old.csv", on_subject: true, source: null })];
    expect(existingAmong(caps, ["A.csv", "B.csv"])).toEqual(["A.csv"]);
    expect(reapplicable(caps)).toEqual(["A.csv"]);
  });

  it("turns collapsed pairs and duplicate labels into sentences", () => {
    expect(inspectionWarnings(inspection())).toEqual(["1 electrode pair closer than 2 mm: Fz–Cz 0.5 mm"]);
    expect(inspectionWarnings(inspection({ collapsed: [], duplicate_names: ["E1"] }))).toEqual(["Duplicate labels: E1"]);
    expect(inspectionWarnings(inspection({ collapsed: [] }))).toEqual([]);
  });

  it("colours collapsed electrodes red and appends the compare net", () => {
    const markers = inspectionMarkers(
      inspection({ compare: { net: "B.csv", electrodes: [{ name: "X", world: [1, 2, 3] }], median_mm: 1, max_mm: 1 } }),
    );
    expect(markers.map((m) => m.label)).toEqual(["Fz", "Cz", "Pz", "X (B)"]);
    expect(markers.map((m) => m.color)).toEqual([SCENE_CATEGORICAL[7], SCENE_CATEGORICAL[7], SCENE_CATEGORICAL[0], SCENE_CATEGORICAL[1]]);
  });
});

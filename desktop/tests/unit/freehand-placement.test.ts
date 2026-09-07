import { describe, expect, it } from "vitest";
import {
  autoLabel,
  isBlankPosition,
  placeAt,
  placementMarkers,
  removeAt,
  renumber,
  roundMm,
} from "../../src/renderer/pages/simulator/freehandPlacement";
import type { ElectrodePosition } from "../../src/renderer/pages/simulator/api";

/**
 * The click-to-place model, checked against v2.5.0's own behaviour
 * (`tit/gui/extensions/electrode_placement.py::onMarkerPlaced` and `deleteChecked`) rather than
 * against what looked reasonable while writing it.
 */
const blank = (): ElectrodePosition[] => [
  { label: "", x: 0, y: 0, z: 0 },
  { label: "", x: 0, y: 0, z: 0 },
  { label: "", x: 0, y: 0, z: 0 },
  { label: "", x: 0, y: 0, z: 0 },
];

describe("autoLabel", () => {
  it("names rows E1+ E1- E2+ E2- … , the pairs the simulation runs", () => {
    expect([0, 1, 2, 3, 4, 5].map(autoLabel)).toEqual(["E1+", "E1-", "E2+", "E2-", "E3+", "E3-"]);
  });

  it("uses an ASCII hyphen, because the label becomes a JSON key SimNIBS reads back", () => {
    expect(autoLabel(1)).toBe("E1-");
    expect(autoLabel(1).charCodeAt(2)).toBe(45);
  });
});

describe("placeAt", () => {
  it("fills the first blank row rather than appending below four empty ones", () => {
    const { positions, index } = placeAt(blank(), [-68.14, -12.32, 22.51]);
    expect(index).toBe(0);
    expect(positions).toHaveLength(4);
    expect(positions[0]).toEqual({ label: "E1+", x: -68.1, y: -12.3, z: 22.5 });
    // Blank rows below are named but still blank-valued, so the table reads as a plan.
    expect(positions[1]?.x).toBe(0);
  });

  it("advances through the rows, one click each", () => {
    let rows = blank();
    for (const w of [
      [1, 1, 1],
      [2, 2, 2],
      [3, 3, 3],
    ] as [number, number, number][]) {
      rows = placeAt(rows, w).positions;
    }
    expect(rows.map((p) => [p.label, p.x])).toEqual([
      ["E1+", 1],
      ["E1-", 2],
      ["E2+", 3],
      ["E2-", 0],
    ]);
  });

  it("appends once every row is used, so placement never silently stops", () => {
    let rows = blank();
    for (let i = 0; i < 5; i += 1) rows = placeAt(rows, [i + 1, 0, 0]).positions;
    expect(rows).toHaveLength(5);
    expect(rows[4]).toMatchObject({ label: "E3+", x: 5 });
  });

  it("rounds to the 0.1 mm step the editor's number inputs use", () => {
    const { positions } = placeAt(blank(), [12.34567, -0.04, 99.95]);
    expect(positions[0]).toMatchObject({ x: 12.3, y: -0, z: 100 });
    expect(roundMm(-0.06)).toBe(-0.1);
  });
});

describe("removeAt / renumber", () => {
  it("renumbers what is left — Qt's deleteChecked, not a hole in the sequence", () => {
    let rows = blank();
    for (let i = 0; i < 4; i += 1) rows = placeAt(rows, [i + 1, 0, 0]).positions;
    const after = removeAt(rows, 1);
    expect(after.map((p) => [p.label, p.x])).toEqual([
      ["E1+", 1],
      ["E1-", 3],
      ["E2+", 4],
    ]);
  });

  it("leaves a name the user typed alone", () => {
    const rows: ElectrodePosition[] = [
      { label: "left-temporal", x: 1, y: 0, z: 0 },
      { label: "E9-", x: 2, y: 0, z: 0 },
    ];
    expect(renumber(rows).map((p) => p.label)).toEqual(["left-temporal", "E1-"]);
  });
});

describe("placementMarkers", () => {
  it("draws one dot per placed row, coloured by its pair", () => {
    let rows = blank();
    for (let i = 0; i < 3; i += 1) rows = placeAt(rows, [i + 1, 0, 0]).positions;
    const markers = placementMarkers(rows);
    expect(markers.map((m) => [m.id, m.channel])).toEqual([
      ["E1+", 0],
      ["E1-", 0],
      ["E2+", 1],
    ]);
    expect(markers[0]?.world).toEqual([1, 0, 0]);
  });

  it("draws nothing for a blank row — a dot at the origin is a dot inside the head", () => {
    expect(placementMarkers(blank())).toEqual([]);
    expect(isBlankPosition({ label: "", x: 0, y: 0, z: 0 })).toBe(true);
    expect(isBlankPosition({ label: "", x: 0, y: 0, z: 0.1 })).toBe(false);
  });
});

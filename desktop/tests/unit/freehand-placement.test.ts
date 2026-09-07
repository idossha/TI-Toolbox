import { describe, expect, it } from "vitest";
import {
  autoLabel,
  isBlankPosition,
  markerIndexOfRow,
  placeAt,
  placementMarkers,
  positionColor,
  positionSwatch,
  removeAt,
  renumber,
  roundMm,
  rowOfMarkerIndex,
} from "../../src/renderer/pages/simulator/freehandPlacement";
import { SCENE_CATEGORICAL } from "../../src/renderer/scene";
import type { ElectrodePosition } from "../../src/renderer/pages/simulator/api";

/**
 * The click-to-place state machine, checked against v2.5.0's own behaviour
 * (`tit/gui/extensions/electrode_placement.py::onMarkerPlaced` and `deleteChecked`) and against the
 * maintainer's 2026-09-06 requirement that it must never be ambiguous which electrode is being
 * manipulated.
 */
const blank = (n = 4): ElectrodePosition[] =>
  renumber(Array.from({ length: n }, () => ({ label: "", x: 0, y: 0, z: 0 })));

/**
 * Select a row, click, select the next, click — which is the whole flow, and deliberately not a
 * loop that places four points from four clicks: selection comes first every time
 * (maintainer, 2026-09-06).
 */
function clicks(rows: ElectrodePosition[], worlds: [number, number, number][]): ElectrodePosition[] {
  worlds.forEach((world, i) => {
    rows = placeAt(rows, world, i).positions;
  });
  return rows;
}

describe("autoLabel / renumber", () => {
  it("names rows E1+ E1- E2+ E2- … , the pairs the simulation runs", () => {
    expect([0, 1, 2, 3, 4, 5].map(autoLabel)).toEqual(["E1+", "E1-", "E2+", "E2-", "E3+", "E3-"]);
  });

  it("uses an ASCII hyphen, because the label becomes a JSON key SimNIBS reads back", () => {
    expect(autoLabel(1).charCodeAt(2)).toBe(45);
  });

  it("names the empty table too, so it reads as the plan before anything is clicked", () => {
    expect(blank().map((p) => p.label)).toEqual(["E1+", "E1-", "E2+", "E2-"]);
    // ...and an auto-named row with no coordinates is still blank, or the first click would find
    // no free row and the table would grow behind the user's back.
    expect(blank().every(isBlankPosition)).toBe(true);
  });

  it("leaves a name the user typed alone", () => {
    const rows: ElectrodePosition[] = [
      { label: "left-temporal", x: 1, y: 0, z: 0 },
      { label: "E9-", x: 2, y: 0, z: 0 },
    ];
    expect(renumber(rows).map((p) => p.label)).toEqual(["left-temporal", "E1-"]);
  });
});

describe("placeAt", () => {
  it("does nothing at all when no row is selected", () => {
    const rows = blank();
    const result = placeAt(rows, [1, 2, 3], null);
    // The failure this prevents: a click that always does *something*, leaving the user to read the
    // table afterwards to find out which electrode moved.
    expect(result.index).toBe(-1);
    expect(result.positions).toBe(rows);
  });

  it("writes the SELECTED row, however many blank rows sit above it", () => {
    const { positions, index } = placeAt(blank(), [-68.14, -12.32, 22.51], 2);
    expect(index).toBe(2);
    expect(positions[2]).toEqual({ label: "E2+", x: -68.1, y: -12.3, z: 22.5 });
    expect(positions[0]?.x).toBe(0);
  });

  it("MOVES the selected electrode when it is already placed", () => {
    // The selection does not advance, so a second click on the scalp adjusts the same electrode
    // instead of needing it deleted and everything after it re-placed.
    let rows = placeAt(blank(), [1, 0, 0], 1).positions;
    rows = placeAt(rows, [9, 9, 9], 1).positions;
    expect(rows).toHaveLength(4);
    expect(rows[1]).toMatchObject({ label: "E1-", x: 9, y: 9, z: 9 });
  });

  it("never grows the table — rows come from Add electrode pair", () => {
    const rows = clicks(blank(), [
      [1, 0, 0],
      [2, 0, 0],
      [3, 0, 0],
      [4, 0, 0],
    ]);
    expect(rows).toHaveLength(4);
    expect(placeAt(rows, [5, 0, 0], 9).positions).toHaveLength(4);
    expect(placeAt(rows, [5, 0, 0], 9).index).toBe(-1);
  });

  it("keeps a label the user typed when it moves that row's coordinates", () => {
    const rows: ElectrodePosition[] = [{ label: "left-temporal", x: 0, y: 0, z: 0 }, { label: "E1-", x: 0, y: 0, z: 0 }];
    expect(placeAt(rows, [1, 2, 3], 0).positions[0]).toMatchObject({ label: "left-temporal", x: 1 });
  });

  it("rounds to the 0.1 mm step the editor's number inputs use", () => {
    expect(placeAt(blank(), [12.34567, -0.04, 99.95], 0).positions[0]).toMatchObject({ x: 12.3, y: -0, z: 100 });
    expect(roundMm(-0.06)).toBe(-0.1);
  });
});

describe("removeAt", () => {
  it("renumbers what is left — Qt's deleteChecked, not a hole in the sequence", () => {
    const rows = clicks(blank(), [
      [1, 0, 0],
      [2, 0, 0],
      [3, 0, 0],
      [4, 0, 0],
    ]);
    expect(removeAt(rows, 1).map((p) => [p.label, p.x])).toEqual([
      ["E1+", 1],
      ["E1-", 3],
      ["E2+", 4],
    ]);
  });
});

describe("colours", () => {
  it("gives every row of a configuration its own colour", () => {
    const eight = Array.from({ length: 8 }, (_, i) => positionSwatch(i));
    expect(new Set(eight).size).toBe(8);
  });

  it("is stable per index — a renamed electrode keeps its colour", () => {
    expect(positionColor(3)).toEqual(SCENE_CATEGORICAL[3]);
    expect(positionSwatch(0)).toBe("#0072b2");
  });

  it("wraps only past the ramp, and is never the invisible black Okabe-Ito ends on", () => {
    expect(positionSwatch(SCENE_CATEGORICAL.length)).toBe(positionSwatch(0));
    expect(SCENE_CATEGORICAL.some((c) => c[0] === 0 && c[1] === 0 && c[2] === 0)).toBe(false);
  });
});

describe("placementMarkers", () => {
  it("draws one dot per placed row, each in that row's own colour", () => {
    const rows = clicks(blank(), [
      [1, 0, 0],
      [2, 0, 0],
      [3, 0, 0],
    ]);
    const markers = placementMarkers(rows);
    expect(markers.map((m) => m.id)).toEqual(["E1+", "E1-", "E2+"]);
    expect(markers.map((m) => m.color)).toEqual([positionColor(0), positionColor(1), positionColor(2)]);
    expect(markers[0]?.world).toEqual([1, 0, 0]);
  });

  it("draws nothing for a blank row — a dot at the origin is a dot inside the head", () => {
    expect(placementMarkers(blank())).toEqual([]);
    expect(isBlankPosition({ label: "", x: 0, y: 0, z: 0.1 })).toBe(false);
  });
});

describe("row ↔ dot", () => {
  it("maps both ways across blank rows, which draw no dot", () => {
    // Rows 0 and 2 placed, rows 1 and 3 blank: row 2 is dot 1, not dot 2. A component that assumed
    // the indices matched would highlight the wrong electrode exactly while the table is half full.
    const rows: ElectrodePosition[] = [
      { label: "E1+", x: 1, y: 0, z: 0 },
      { label: "E1-", x: 0, y: 0, z: 0 },
      { label: "E2+", x: 3, y: 0, z: 0 },
      { label: "E2-", x: 0, y: 0, z: 0 },
    ];
    expect(markerIndexOfRow(rows, 0)).toBe(0);
    expect(markerIndexOfRow(rows, 2)).toBe(1);
    expect(markerIndexOfRow(rows, 1)).toBe(-1);
    expect(rowOfMarkerIndex(rows, 1)).toBe(2);
    expect(rowOfMarkerIndex(rows, 5)).toBe(-1);
  });
});

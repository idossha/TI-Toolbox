/**
 * The Simulator's scene is a pure function of one focus (ARCHITECTURE §7.2, 2026-10-28): the row
 * or the open form the user last touched. Each case below is a sentence of that rule, written from
 * the rule rather than read off the code:
 *  - a row draws its own net (none if it has none, never one from elsewhere) and its channels; a
 *    row's saved coordinates and a snapped row's optimised origins are drawn on its subject;
 *  - the montage form draws its own net (none until chosen) and its draft, and takes the picks;
 *  - the placement form draws the placement subject's head and takes the clicks;
 *  - a closed form, or a removed row, falls back to a row that exists.
 * Net names are the mock's (`EGI_template`, `GSN-HydroCel-185`) and a warped cap the packaged guide
 * lacks (`BioSemi-64-10-10.csv`, as on the maintainer's sub-101). The end-to-end walk of the same
 * paths is `desktop/tests/e2e/simulator-scene-focus.spec.ts`.
 */
import { describe, expect, it } from "vitest";
import { resolveFocus, sceneFor, type SceneData, type SceneFocus } from "../../src/renderer/pages/simulator/sceneFocus";
import type { SelectedRow } from "../../src/renderer/pages/simulator/types";

const GUIDE = ["EGI_template.csv", "GSN-HydroCel-185.csv"];
const row = (id: string, extra: Partial<SelectedRow> = {}): SelectedRow => ({ id, subjectId: "ernie", source: "montage", name: "", currents: "1.0,1.0", ...extra });
const F3F4: [string, string][] = [["E36", "E24"], ["E45", "E58"]];
const XYZ: [[number, number, number], [number, number, number]][] = [[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [10, 11, 12]]];

const noNet = row("blank");
const big = row("big", { eegNet: "EGI_template", name: "F3_F4", kind: "uni_polar", pairs: F3F4 });
const small = row("small", { eegNet: "GSN-HydroCel-185" });
const warped = row("warped", { subjectId: "101", eegNet: "BioSemi-64-10-10.csv" });
const placed = row("placed", { source: "freehand", name: "my_set", xyzPairs: XYZ });
const snapped = row("snapped", {
  source: "flex",
  name: "candidate_x",
  eegNet: "GSN-HydroCel-185",
  pairs: [["E1", "E2"], ["E3", "E4"]],
  candidate: { id: "trial-2", run: "flex_run", config: { montages: [{ electrode_pairs: XYZ }] }, originalCurrents: "1,1", originalSettings: {} as never },
});

const data = (extra: Partial<SceneData> = {}): SceneData => ({
  rows: [noNet, big, small, warped, placed, snapped],
  draft: null,
  placementSubject: "ernie",
  flexRuns: {},
  guideNets: GUIDE,
  subjectNets: { ernie: ["EGI_template", "GSN-HydroCel-185"], "101": ["BioSemi-64-10-10.csv"] },
  subjects: ["ernie", "101"],
  ...extra,
});
const onRow = (rowId: string): SceneFocus => ({ on: "row", rowId });

describe("sceneFor", () => {
  it("a row with no net draws no electrodes and says why", () => {
    expect(sceneFor(onRow("blank"), data())).toEqual({
      rowId: "blank", edits: null, subject: null, net: null, showing: null, note: "Choose an EEG net to see its electrodes.",
    });
  });

  it("a row draws its own net and montage on the guide, read-only", () => {
    const view = sceneFor(onRow("big"), data());
    expect(view).toMatchObject({ net: "EGI_template", pairs: F3F4, subject: null, edits: null, showing: { montage: "F3_F4", net: "EGI_template" } });
    expect(sceneFor(onRow("small"), data())).toMatchObject({ net: "GSN-HydroCel-185", pairs: undefined, showing: null });
  });

  it("a row on a net the guide lacks is drawn on its subject's head", () => {
    expect(sceneFor(onRow("warped"), data())).toMatchObject({ net: "BioSemi-64-10-10.csv", subject: "101" });
  });

  it("a row's saved coordinates are drawn on its subject, without a net", () => {
    const view = sceneFor(onRow("placed"), data());
    expect(view).toMatchObject({ subject: "ernie", net: null, showing: { montage: "my_set", net: "4 placed positions" } });
    expect(view.positions).toEqual([{ x: 1, y: 2, z: 3 }, { x: 4, y: 5, z: 6 }, { x: 7, y: 8, z: 9 }, { x: 10, y: 11, z: 12 }]);
  });

  it("a snapped candidate keeps its subject's head and its optimised origins", () => {
    const view = sceneFor(onRow("snapped"), data());
    expect(view).toMatchObject({ subject: "ernie", net: "GSN-HydroCel-185", pairs: [["E1", "E2"], ["E3", "E4"]] });
    expect(view.originalPositions).toHaveLength(4);
  });

  it("the montage form draws its own net and draft, and takes the picks", () => {
    const draft = { name: "", pairs: [["E1", ""], ["", ""]] as [string, string][], net: "GSN-HydroCel-185" };
    expect(sceneFor({ on: "montage-form", rowId: "big" }, data({ draft }))).toMatchObject({
      net: "GSN-HydroCel-185", pairs: draft.pairs, edits: "montage", showing: null, subject: null, note: undefined,
    });
  });

  it("the montage form with no net yet draws none, whatever row it came from", () => {
    const draft = { name: "", pairs: [["", ""], ["", ""]] as [string, string][] };
    expect(sceneFor({ on: "montage-form", rowId: "big" }, data({ draft }))).toMatchObject({ net: null, edits: "montage", note: "Choose an EEG net to see its electrodes." });
  });

  it("the montage form on a net the guide lacks draws it on a subject that has it", () => {
    const draft = { name: "", pairs: [["", ""], ["", ""]] as [string, string][], net: "BioSemi-64-10-10.csv" };
    expect(sceneFor({ on: "montage-form", rowId: null }, data({ draft })).subject).toBe("101");
  });

  it("the placement form draws the placement subject's head and takes the clicks", () => {
    expect(sceneFor({ on: "placement-form", rowId: "big" }, data({ placementSubject: "101" }))).toEqual({ subject: "101", net: null, showing: null, edits: "placement" });
  });

  it("no rows draw nothing", () => {
    expect(sceneFor({ on: "row", rowId: null }, data({ rows: [] }))).toEqual({ subject: null, net: null, showing: null, edits: null });
  });
});

describe("resolveFocus", () => {
  const rows = [noNet, big];
  it("starts on the first row", () => {
    expect(resolveFocus({ rowId: null, form: false }, rows, false, false)).toEqual({ on: "row", rowId: "blank" });
  });
  it("is the touched form while it is open, remembering the row to return to", () => {
    expect(resolveFocus({ rowId: "big", form: true }, rows, true, false)).toEqual({ on: "montage-form", rowId: "big" });
    expect(resolveFocus({ rowId: "big", form: true }, rows, false, true)).toEqual({ on: "placement-form", rowId: "big" });
  });
  it("returns to that row once the form is closed", () => {
    expect(resolveFocus({ rowId: "big", form: true }, rows, false, false)).toEqual({ on: "row", rowId: "big" });
  });
  it("an open form the user has since left stays open but is not drawn", () => {
    expect(resolveFocus({ rowId: "big", form: false }, rows, true, false)).toEqual({ on: "row", rowId: "big" });
  });
  it("a removed row gives way to the first row, and no rows to none", () => {
    expect(resolveFocus({ rowId: "gone", form: false }, rows, false, false)).toEqual({ on: "row", rowId: "blank" });
    expect(resolveFocus({ rowId: "gone", form: false }, [], false, false)).toEqual({ on: "row", rowId: null });
  });
});

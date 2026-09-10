/**
 * `scene/selection.ts` — what a pick means, per mode (plan §2.4, decisions S5/S6).
 *
 * These cases are the pane's whole behavioural contract, and they run without a canvas because the
 * form drives the same reducer: if the reducer is right, the pane and the form cannot disagree
 * about what "toggle" means, which is the only way S6's two-way sync is more than a hope.
 */
import { describe, expect, it } from "vitest";
import {
  EMPTY_SELECTION,
  MODE_RULES,
  isPickable,
  isSelected,
  selectionReducer,
  type SceneSelection,
} from "../../src/renderer/scene/selection";

const montage = MODE_RULES.montage;
const target = MODE_RULES.target;
const inspect = MODE_RULES.inspect;

const pickMarker = (index: number) => ({ type: "pick", target: { kind: "marker" as const, index } }) as const;
const pickRegion = (index: number) => ({ type: "pick", target: { kind: "region" as const, index } }) as const;

describe("montage mode (Simulator)", () => {
  it("adds electrodes in pick order", () => {
    const one = selectionReducer(EMPTY_SELECTION, pickMarker(4), montage);
    const two = selectionReducer(one, pickMarker(9), montage);
    expect(two.markers).toEqual([4, 9]);
  });

  it("toggles an already-selected electrode off", () => {
    const two: SceneSelection = { markers: [4, 9], regions: [] };
    expect(selectionReducer(two, pickMarker(4), montage).markers).toEqual([9]);
  });

  it("evicts the oldest when the pair is full rather than ignoring the click", () => {
    // Two electrodes make a pair. A user who has picked two and clicks a third means "replace the
    // one I picked first"; a silently ignored click is the failure this rule exists to prevent.
    const full: SceneSelection = { markers: [4, 9], regions: [] };
    expect(selectionReducer(full, pickMarker(11), montage).markers).toEqual([9, 11]);
  });

  it("does not select regions at all", () => {
    const next = selectionReducer(EMPTY_SELECTION, pickRegion(1005), montage);
    expect(next.regions).toEqual([]);
    // Nothing changed, so the same object comes back and a React consumer does not re-render.
    expect(next).toBe(EMPTY_SELECTION);
  });
});

describe("target mode (Optimizer)", () => {
  it("accumulates regions without a cap", () => {
    let state: SceneSelection = EMPTY_SELECTION;
    for (const id of [1001, 1002, 1003, 1004, 1005, 1006]) {
      state = selectionReducer(state, pickRegion(id), target);
    }
    expect(state.regions).toEqual([1001, 1002, 1003, 1004, 1005, 1006]);
  });

  it("removes a region on a second pick", () => {
    const state: SceneSelection = { markers: [], regions: [1001, 1002] };
    expect(selectionReducer(state, pickRegion(1001), target).regions).toEqual([1002]);
  });

  it("does not select markers", () => {
    expect(selectionReducer(EMPTY_SELECTION, pickMarker(2), target).markers).toEqual([]);
  });
});

describe("inspect mode (Analyzer)", () => {
  it("keeps at most one marker — the sphere centre", () => {
    const one = selectionReducer(EMPTY_SELECTION, pickMarker(3), inspect);
    expect(one.markers).toEqual([3]);
    expect(selectionReducer(one, pickMarker(8), inspect).markers).toEqual([8]);
  });

  it("has no pickable regions", () => {
    expect(isPickable(inspect, "region")).toBe(false);
    expect(isPickable(inspect, "marker")).toBe(true);
    expect(isPickable(target, "region")).toBe(true);
    expect(isPickable(montage, "region")).toBe(false);
  });
});

describe("clearing", () => {
  const state: SceneSelection = { markers: [1, 2], regions: [1001] };

  it("a pick on empty space clears everything", () => {
    expect(selectionReducer(state, { type: "pick", target: null }, montage)).toEqual({ markers: [], regions: [] });
  });

  it("clearing an already-empty selection returns the same object", () => {
    expect(selectionReducer(EMPTY_SELECTION, { type: "clear" }, montage)).toBe(EMPTY_SELECTION);
    expect(selectionReducer(EMPTY_SELECTION, { type: "pick", target: null }, montage)).toBe(EMPTY_SELECTION);
  });

  it("clears one kind at a time", () => {
    expect(selectionReducer(state, { type: "clear", kind: "marker" }, montage)).toEqual({
      markers: [],
      regions: [1001],
    });
    expect(selectionReducer(state, { type: "clear", kind: "region" }, target)).toEqual({
      markers: [1, 2],
      regions: [],
    });
  });
});

describe("set (the form pushing its state into the pane)", () => {
  it("replaces a list, de-duplicates it and applies the mode's cap", () => {
    const next = selectionReducer(EMPTY_SELECTION, { type: "set", kind: "marker", ids: [7, 7, 8, 9] }, montage);
    expect(next.markers).toEqual([8, 9]); // de-duplicated to [7,8,9], capped to the last two
  });

  it("returns the same object when the list is unchanged, so a sync loop terminates", () => {
    // The form pushes on every render; without this, pane -> form -> pane would re-render forever.
    const state: SceneSelection = { markers: [], regions: [1001, 1002] };
    expect(selectionReducer(state, { type: "set", kind: "region", ids: [1001, 1002] }, target)).toBe(state);
  });

  it("drops everything for a kind the mode does not select", () => {
    expect(selectionReducer(EMPTY_SELECTION, { type: "set", kind: "region", ids: [1, 2] }, montage).regions).toEqual([]);
  });
});

describe("isSelected", () => {
  it("answers for either kind, and for nothing", () => {
    const state: SceneSelection = { markers: [3], regions: [1001] };
    expect(isSelected(state, { kind: "marker", index: 3 })).toBe(true);
    expect(isSelected(state, { kind: "marker", index: 4 })).toBe(false);
    expect(isSelected(state, { kind: "region", index: 1001 })).toBe(true);
    expect(isSelected(state, null)).toBe(false);
  });
});

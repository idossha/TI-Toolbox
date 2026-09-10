/**
 * The selection reducer — what a pick *means*, per mode (plan §2.4, decision S5).
 *
 * It is a pure function of (state, action, rules) because decision S6 says the pane is never the
 * only way to make a selection: the same reducer runs whether the user clicked the canvas or typed
 * into the form, so the two can never disagree about what "toggle" means. Keeping it out of the
 * component is also what lets the three modes be tested without a GPU or a DOM.
 */

import { samePickTarget, type PickKind, type PickTarget } from "./pickId";

export type SceneMode = "montage" | "target" | "inspect";

export interface SceneSelection {
  /** Indices into the markers array, in the order they were picked. */
  markers: number[];
  /** Atlas label ids, in the order they were picked. */
  regions: number[];
}

export const EMPTY_SELECTION: SceneSelection = { markers: [], regions: [] };

export type SelectMode = "none" | "single" | "multi";

export interface SelectionRules {
  markers: SelectMode;
  regions: SelectMode;
  /**
   * Cap on the marker list. When it is full a new pick evicts the OLDEST entry rather than being
   * ignored — the Simulator's pair slots are two electrodes, and a user who has picked two and
   * clicks a third means "replace the one I picked first", not "nothing happens". A silently
   * ignored click is the failure this exists to prevent.
   */
  maxMarkers?: number;
  maxRegions?: number;
}

/** The rules each mode runs under (plan §2.4). `inspect` is read-only except for the sphere centre,
 *  which the Analyzer form drives as a single marker. */
export const MODE_RULES: Record<SceneMode, SelectionRules> = {
  montage: { markers: "multi", regions: "none", maxMarkers: 2 },
  target: { markers: "none", regions: "multi" },
  inspect: { markers: "single", regions: "none" },
};

export type SelectionAction =
  /** The canvas (or the form) picked something; `null` means empty space was clicked. */
  | { type: "pick"; target: PickTarget | null }
  /** Replace one kind's list wholesale — how the form pushes its state into the pane. */
  | { type: "set"; kind: PickKind; ids: number[] }
  /** Clear one kind, or everything when `kind` is omitted (Escape). */
  | { type: "clear"; kind?: PickKind };

function toggle(list: number[], id: number, mode: SelectMode, max: number | undefined): number[] {
  if (mode === "none") return list;
  if (list.includes(id)) return list.filter((v) => v !== id);
  if (mode === "single") return [id];
  const next = [...list, id];
  if (max !== undefined && next.length > max) return next.slice(next.length - max);
  return next;
}

function capped(ids: number[], mode: SelectMode, max: number | undefined): number[] {
  if (mode === "none") return [];
  const unique = [...new Set(ids)];
  if (mode === "single") return unique.slice(0, 1);
  if (max !== undefined && unique.length > max) return unique.slice(unique.length - max);
  return unique;
}

/**
 * Applies one action. Always returns a new object when something changed and the SAME object when
 * nothing did, so a React consumer's identity check is a correct "did the selection change?" test:
 * a reducer that always allocates makes every no-op pick re-render the pane and re-upload buffers.
 */
export function selectionReducer(
  state: SceneSelection,
  action: SelectionAction,
  rules: SelectionRules,
): SceneSelection {
  switch (action.type) {
    case "pick": {
      if (action.target === null) {
        // A click on empty space clears — the standard "deselect" gesture. Nothing to do when it is
        // already empty.
        return state.markers.length === 0 && state.regions.length === 0 ? state : { markers: [], regions: [] };
      }
      if (action.target.kind === "marker") {
        const markers = toggle(state.markers, action.target.index, rules.markers, rules.maxMarkers);
        return markers === state.markers ? state : { ...state, markers };
      }
      const regions = toggle(state.regions, action.target.index, rules.regions, rules.maxRegions);
      return regions === state.regions ? state : { ...state, regions };
    }
    case "set": {
      if (action.kind === "marker") {
        const markers = capped(action.ids, rules.markers, rules.maxMarkers);
        return sameList(markers, state.markers) ? state : { ...state, markers };
      }
      const regions = capped(action.ids, rules.regions, rules.maxRegions);
      return sameList(regions, state.regions) ? state : { ...state, regions };
    }
    case "clear": {
      if (action.kind === "marker") return state.markers.length === 0 ? state : { ...state, markers: [] };
      if (action.kind === "region") return state.regions.length === 0 ? state : { ...state, regions: [] };
      return state.markers.length === 0 && state.regions.length === 0 ? state : { markers: [], regions: [] };
    }
    default:
      return state;
  }
}

function sameList(a: number[], b: number[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

/** True when `target` is currently selected — the shading and the legend both ask this. */
export function isSelected(state: SceneSelection, target: PickTarget | null): boolean {
  if (!target) return false;
  const list = target.kind === "marker" ? state.markers : state.regions;
  return list.includes(target.index);
}

/** Whether a mode lets a kind be picked at all. The GL pick pass skips a kind that is not
 *  pickable, so a read-only `inspect` pane cannot even report a region under the cursor. */
export function isPickable(rules: SelectionRules, kind: PickKind): boolean {
  return (kind === "marker" ? rules.markers : rules.regions) !== "none";
}

export { samePickTarget };
export type { PickTarget, PickKind };

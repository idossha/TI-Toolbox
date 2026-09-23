/**
 * The right pane's state machine (program U13) — pure, so the clamping and the mode transitions
 * the maintainer asked for ("allow user to stretch/collapse/expand the right hand side") are read
 * off `tests/unit/pane-state.test.ts` rather than off a screenshot.
 *
 * No React and no DOM: `ui/Layout.tsx` drives this from `usePaneController`, Jobs and Results both
 * drive that one controller, and the persistence below is the *only* place a pane width is written
 * to storage. DESIGN.md §2.1 already said the width is "persisted per machine per page kind"; this
 * module is that sentence made executable, one key per page id.
 */

/**
 * `normal` — work pane + right pane side by side.
 * `collapsed` — the pane is not rendered at all (U1: never an empty pane), the work pane takes the
 * width, and a 16 px rail on the divider brings it back.
 * `expanded` — the pane takes the whole content box and the work pane is not rendered, for reading
 * a long report or a wide results table. Transient: Esc and the header's restore button leave it.
 */
export type PaneMode = "normal" | "collapsed" | "expanded";

export interface PaneLimits {
  min: number;
  max: number;
}

/**
 * The preview and detail panes' drag range (Results' preview, Jobs' detail column): a 320 px floor
 * and a ceiling at 70 % of the WINDOW. Fractions because the ask was stated as a share of the
 * screen, and a flat px ceiling once sat below the pane's own default on a 2000 px screen.
 */
export const PREVIEW_PANE_MIN = 320;
export const PREVIEW_PANE_MAX_VW = 0.7;

/** The preview/detail drag limits for a window `viewportWidth` px wide (1280 when unknown). */
export function previewPaneLimits(viewportWidth: number): PaneLimits {
  const w = Number.isFinite(viewportWidth) && viewportWidth > 0 ? viewportWidth : 1280;
  return { min: PREVIEW_PANE_MIN, max: Math.round(w * PREVIEW_PANE_MAX_VW) };
}

/**
 * The run shape's split, in pixels of the split's own box (`.page-layout-body`), not of the window
 * (ARCHITECTURE §11 "Layout and navigation"; DECISIONS 2026-09-23). Window fractions let a 70 vw
 * pane squeeze the Jobs table to 162 px at 1440 and a 36 vw floor stretch it to 959 px at 1920.
 *
 * `RUN_WORK_MIN` is measured, not chosen: an offscreen probe shrank the work pane in 4 px steps
 * until something in a Jobs table truncated — Simulator's SUBJECT header at 628, the Optimizer's
 * goal select at 556, the Analyzer's "Choose a simulation" at 632 (2026-09-23, mock fixture) — so
 * 640 is the widest of the three rounded up. `RUN_WORK_MAX` stops the table stretching into empty
 * ground; `RUN_PANE_MIN` is the old fixed run column, enough for the Terminal/Scene tab row.
 * Below `RUN_STACK_BODY` the two do not fit side by side and the page stacks instead (the
 * `max-width: 1139px` media query, which `pane-state.test.ts` ties to these numbers).
 */
export const RUN_WORK_MIN = 640;
export const RUN_WORK_MAX = 800;
export const RUN_PANE_MIN = 400;
/** The undragged pane, clamped by the limits like any other width. */
export const RUN_PANE_DEFAULT_VW = 45;
/** The grab strip between the panes (`.page-layout-inspector-handle`'s width). */
export const PANE_HANDLE = 6;
export const RUN_STACK_BODY = RUN_WORK_MIN + PANE_HANDLE + RUN_PANE_MIN;

/** The run pane's drag range for a split box `bodyWidth` px wide: the work pane stays inside
 * [RUN_WORK_MIN, RUN_WORK_MAX] and the pane never drops under RUN_PANE_MIN. A box too narrow for
 * both (the layout stacks there) pins the pane at its floor rather than returning an empty range. */
export function runPaneLimits(bodyWidth: number): PaneLimits {
  const room = Number.isFinite(bodyWidth) && bodyWidth > 0 ? bodyWidth - PANE_HANDLE : RUN_STACK_BODY - PANE_HANDLE;
  return {
    min: Math.round(Math.max(RUN_PANE_MIN, room - RUN_WORK_MAX)),
    max: Math.round(Math.max(RUN_PANE_MIN, room - RUN_WORK_MIN)),
  };
}

/** Which rule a pane's drag obeys: the run split, or the preview/detail window fraction. */
export type PaneKind = "run" | "preview";

/** The one limits function both dividers (`PaneSeparator` via `usePaneController`, and the
 * controller-less `InspectorHandle`) clamp against. */
export function paneLimits(kind: PaneKind, bodyWidth: number, viewportWidth: number): PaneLimits {
  return kind === "run" ? runPaneLimits(bodyWidth) : previewPaneLimits(viewportWidth);
}

/**
 * The same numbers as CSS custom properties, set once on every run-shape `.page-layout` by
 * `PageLayout`, so `ui/components.css` clamps the pane with these values instead of repeating them.
 */
export const RUN_SPLIT_CSS_VARS: Readonly<Record<string, string>> = {
  "--run-work-min": `${RUN_WORK_MIN}px`,
  "--run-work-max": `${RUN_WORK_MAX}px`,
  "--run-pane-min": `${RUN_PANE_MIN}px`,
  "--run-pane-default": `${RUN_PANE_DEFAULT_VW}vw`,
  "--pane-handle": `${PANE_HANDLE}px`,
};

export interface PaneState {
  /**
   * `null` = the user has never sized this pane, so the design's own CSS width still applies (the
   * run pane's clamped 45 vw, `clamp(380px, 40%, 560px)` for a preview). Storing a
   * number the moment a page mounts would freeze the responsive default into local storage, and the
   * pane would stop answering the 1440 px step for good.
   */
  width: number | null;
  mode: PaneMode;
}

export type PaneAction =
  /** Absolute width in px, from a pointer drag or an arrow key on the separator. */
  | { type: "resize"; width: number }
  | { type: "collapse" }
  | { type: "expand" }
  | { type: "restore" }
  | { type: "toggleCollapse" }
  | { type: "toggleExpand" };

const MODES: readonly PaneMode[] = ["normal", "collapsed", "expanded"];

/** Rounded and inside `[min, max]`. `NaN` falls back to the minimum rather than poisoning the
 * stored state, which would render a pane of width `NaNpx` — i.e. none, which looks exactly like
 * the pane failing to open. An infinity is just a very large drag and clamps to a limit. */
export function clampPaneWidth(width: number, limits: PaneLimits): number {
  const min = Math.min(limits.min, limits.max);
  const max = Math.max(limits.min, limits.max);
  if (Number.isNaN(width)) return min;
  return Math.round(Math.min(max, Math.max(min, width)));
}

/**
 * Every transition of the pane. Resizing always lands in `normal`: a drag or an arrow key is a
 * statement about how wide the pane should be *beside the work pane*, so it is also the gesture
 * that leaves a collapsed or expanded state rather than silently storing a width nobody can see.
 */
export function paneReducer(state: PaneState, action: PaneAction, limits: PaneLimits): PaneState {
  switch (action.type) {
    case "resize":
      return { width: clampPaneWidth(action.width, limits), mode: "normal" };
    case "collapse":
      return { ...state, mode: "collapsed" };
    case "expand":
      return { ...state, mode: "expanded" };
    case "restore":
      return { ...state, mode: "normal" };
    case "toggleCollapse":
      return { ...state, mode: state.mode === "collapsed" ? "normal" : "collapsed" };
    case "toggleExpand":
      return { ...state, mode: state.mode === "expanded" ? "normal" : "expanded" };
    default:
      return state;
  }
}

/**
 * One key per page id — Jobs' 360 px column and Results' 490 px preview are different decisions.
 *
 * The version segment is a one-time reset, not decoration: the run pane's default grew from a
 * fixed 360/400 px column to 36 vw (`v2`) and then to 45 vw (`v3`, DESIGN.md §2.1), and every
 * machine that had ever touched the old divider held a stored width sized against the old default.
 * Reading those back would pin exactly the users who use the pane most to the narrow pane the
 * maintainer asked us to widen. A new key means the new default applies once; the very next drag
 * persists as before.
 */
export function paneStorageKey(pageId: string): string {
  return `tit-pane-v3-${pageId}`;
}

/** The subset of `Storage` this module needs, so a unit test passes a `Map` instead of a jsdom. */
export interface PaneStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

const DEFAULT_STATE: PaneState = { width: null, mode: "normal" };

/**
 * The stored state for `pageId`, or the CSS default when nothing is stored, the entry is corrupt,
 * or storage itself throws (Electron with site data blocked, a private window). Never throws: a
 * pane that cannot read its width still renders at the design's default.
 */
export function readPaneState(pageId: string, limits: PaneLimits, storage: PaneStorage | undefined): PaneState {
  if (!storage) return DEFAULT_STATE;
  let raw: string | null;
  try {
    raw = storage.getItem(paneStorageKey(pageId));
  } catch {
    return DEFAULT_STATE;
  }
  if (!raw) return DEFAULT_STATE;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return DEFAULT_STATE;
    const record = parsed as { width?: unknown; mode?: unknown };
    const width = typeof record.width === "number" ? clampPaneWidth(record.width, limits) : null;
    // `expanded` is deliberately not restorable: it is a reading posture, not a layout preference,
    // and coming back to a page whose work pane is missing reads as a broken page.
    const mode: PaneMode =
      typeof record.mode === "string" && MODES.includes(record.mode as PaneMode) && record.mode !== "expanded"
        ? (record.mode as PaneMode)
        : "normal";
    return { width, mode };
  } catch {
    return DEFAULT_STATE;
  }
}

/** Persist `state` for `pageId`. Silently does nothing when storage is unavailable or full. */
export function writePaneState(pageId: string, state: PaneState, storage: PaneStorage | undefined): void {
  if (!storage) return;
  try {
    storage.setItem(
      paneStorageKey(pageId),
      JSON.stringify({ width: state.width, mode: state.mode === "expanded" ? "normal" : state.mode }),
    );
  } catch {
    /* storage disabled or full — the pane still works, it just forgets. */
  }
}

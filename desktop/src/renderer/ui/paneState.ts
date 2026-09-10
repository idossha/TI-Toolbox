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
 * The run pane's drag range as fractions of the WINDOW (DESIGN.md §2.1).
 *
 * The maintainer's numbers, measured on a 2000 px screen: the pane opens at 45 % and may be
 * stretched to 70 % or pulled back to 36 % — the width that used to be the *default* is now the
 * floor. Fractions rather than px because the ask was always stated as a share of the screen, and
 * a flat px ceiling is what produced the defect this replaces (see `PANE_MIN_VW` users).
 */
export const PANE_MIN_VW = 0.36;
export const PANE_DEFAULT_VW = 0.45;
export const PANE_MAX_VW = 0.7;

/**
 * The drag limits for a window `viewportWidth` px wide.
 *
 * `minOverride` is how Jobs' 360 px detail column and the Results preview keep the narrower floor
 * DESIGN.md §2.1 pins for them while still gaining the wide ceiling.
 */
export function paneLimitsForViewport(viewportWidth: number, minOverride?: number): PaneLimits {
  const w = Number.isFinite(viewportWidth) && viewportWidth > 0 ? viewportWidth : 1280;
  return {
    min: minOverride ?? Math.round(w * PANE_MIN_VW),
    max: Math.round(w * PANE_MAX_VW),
  };
}

export interface PaneState {
  /**
   * `null` = the user has never sized this pane, so the design's own CSS width still applies (the
   * 360/400 px breakpoint for a fixed column, `clamp(380px, 40%, 560px)` for a preview). Storing a
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

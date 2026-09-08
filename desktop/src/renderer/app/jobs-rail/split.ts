/**
 * The jobs master–detail split: where the divider sits, and what may move it there.
 *
 * Pure and separate from the component so the geometry is testable without a DOM, and so the
 * 260 px panel and the full `jobs` page cannot end up with two different ideas of the default.
 *
 * **Why a fraction and not a pixel width.** The panel used `ResizablePanels` with
 * `defaultLeftWidth={560}`, a fixed number: at 1280 that is a sensible 44 % list, and at 1920 the
 * same 560 px is a 29 % list next to a detail pane holding a definition list in its left third —
 * which is exactly the waste the maintainer's screenshot marked. A fraction keeps the *shape* of
 * the split across widths, and the pixel minimum below keeps it usable at the narrow end.
 */

/** The list gets the larger share: it is the thing being scanned; the detail is read after. */
export const DEFAULT_LIST_FRACTION = 0.62;

/** Below this the detail pane's key/value grid drops to one column and its buttons wrap. */
export const MIN_DETAIL_PX = 420;

/** Below this the table's fixed columns (`jobs-rail.css`) leave no room for STAGE at all. */
export const MIN_LIST_PX = 360;

/** The grab strip between the two panes. */
export const HANDLE_PX = 6;

/** One arrow-key press; Shift multiplies it. */
export const STEP_PX = 16;
export const STEP_COARSE_PX = 64;

export const SPLIT_KEY = "tit.jobs.split";

/**
 * The fraction of *content* width (the box minus the handle) the list may occupy at this width.
 *
 * Both minimums are honoured wherever the box is wide enough for both. Where it is not — a
 * window narrower than ~786 px, which the shell does not offer but a test or a very small screen
 * can — neither minimum can be met, so the split falls back to the default proportion rather than
 * to whichever minimum happened to be applied last. Returning a clamp that cannot hold is worse
 * than returning a proportion that at least keeps both panes on screen.
 */
export function clampListFraction(fraction: number, boxWidth: number): number {
  const content = boxWidth - HANDLE_PX;
  if (!Number.isFinite(fraction) || !Number.isFinite(content) || content <= 0) {
    return DEFAULT_LIST_FRACTION;
  }
  if (content < MIN_LIST_PX + MIN_DETAIL_PX) return DEFAULT_LIST_FRACTION;
  const min = MIN_LIST_PX / content;
  const max = (content - MIN_DETAIL_PX) / content;
  return Math.min(max, Math.max(min, fraction));
}

/** The list's width in px for a given box — what the component writes into the grid. */
export function listWidth(fraction: number, boxWidth: number): number {
  return Math.round(clampListFraction(fraction, boxWidth) * (boxWidth - HANDLE_PX));
}

/**
 * The remembered fraction, or the default.
 *
 * A per-viewer convenience, so `localStorage` is the right home and every failure mode — a
 * private window, cleared site data, a browser that blocks storage, a value someone else wrote —
 * collapses to "start at the default", which is a perfectly good place to start.
 */
export function readSplit(storage: Pick<Storage, "getItem"> | undefined = safeStorage()): number {
  try {
    const raw = storage?.getItem(SPLIT_KEY);
    if (raw === null || raw === undefined) return DEFAULT_LIST_FRACTION;
    const value = Number.parseFloat(raw);
    // A stored value is still bounded here: only `clampListFraction` knows the current width, and
    // 0 or 1.4 must never reach it as a starting point.
    if (!Number.isFinite(value) || value <= 0 || value >= 1) return DEFAULT_LIST_FRACTION;
    return value;
  } catch {
    return DEFAULT_LIST_FRACTION;
  }
}

export function writeSplit(fraction: number, storage: Pick<Storage, "setItem"> | undefined = safeStorage()): void {
  try {
    storage?.setItem(SPLIT_KEY, fraction.toFixed(4));
  } catch {
    /* storage unavailable — the split still drags, it just forgets */
  }
}

function safeStorage(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

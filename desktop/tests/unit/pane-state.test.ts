/**
 * `ui/paneState.ts` — the right pane's clamping and its three modes (program U13).
 *
 * The e2e specs assert what the pane *measures* on screen (`paneWidths().right` grows by 200 ± 4
 * after a drag, reads 0 when collapsed, and the work pane reads 0 when expanded). This file asserts
 * the arithmetic behind those numbers, where a bad clamp is one assertion rather than one browser.
 */
import { describe, expect, it } from "vitest";
import {
  clampPaneWidth,
  paneReducer,
  paneStorageKey,
  readPaneState,
  writePaneState,
  type PaneLimits,
  type PaneState,
  type PaneStorage,
} from "../../src/renderer/ui/paneState";

const LIMITS: PaneLimits = { min: 320, max: 880 };
const NORMAL: PaneState = { width: null, mode: "normal" };

/** A `Map` is enough of a `Storage` for this module, which is the point of the narrow interface. */
function memoryStorage(seed: Record<string, string> = {}): PaneStorage & { data: Map<string, string> } {
  const data = new Map(Object.entries(seed));
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
  };
}

describe("clampPaneWidth", () => {
  it("keeps a width inside the limits and rounds it", () => {
    expect(clampPaneWidth(490.4, LIMITS)).toBe(490);
    expect(clampPaneWidth(319.9, LIMITS)).toBe(320);
    expect(clampPaneWidth(2000, LIMITS)).toBe(880);
  });

  it("falls back to the minimum rather than storing NaN", () => {
    // A pointer event with no clientX, or a corrupt stored value, must not produce `width: NaNpx`
    // — which renders as no width at all and looks exactly like the pane failing to open.
    expect(clampPaneWidth(Number.NaN, LIMITS)).toBe(320);
    expect(clampPaneWidth(Number.POSITIVE_INFINITY, LIMITS)).toBe(880);
  });

  it("survives limits given the wrong way round", () => {
    expect(clampPaneWidth(500, { min: 880, max: 320 })).toBe(500);
    expect(clampPaneWidth(100, { min: 880, max: 320 })).toBe(320);
  });
});

describe("paneReducer", () => {
  it("a drag of +200 from 490 lands on 690, which is what the e2e drag asserts", () => {
    const next = paneReducer({ width: 490, mode: "normal" }, { type: "resize", width: 690 }, LIMITS);
    expect(next).toEqual({ width: 690, mode: "normal" });
  });

  it("clamps a drag past either limit instead of refusing it", () => {
    expect(paneReducer(NORMAL, { type: "resize", width: 1400 }, LIMITS).width).toBe(880);
    expect(paneReducer(NORMAL, { type: "resize", width: 40 }, LIMITS).width).toBe(320);
  });

  it("resizing leaves a collapsed or expanded pane, because a width is a statement about the split", () => {
    expect(paneReducer({ width: 400, mode: "collapsed" }, { type: "resize", width: 500 }, LIMITS).mode).toBe("normal");
    expect(paneReducer({ width: 400, mode: "expanded" }, { type: "resize", width: 500 }, LIMITS).mode).toBe("normal");
  });

  it("toggles collapse and expand, and keeps the width across both", () => {
    let s: PaneState = { width: 520, mode: "normal" };
    s = paneReducer(s, { type: "toggleCollapse" }, LIMITS);
    expect(s).toEqual({ width: 520, mode: "collapsed" });
    s = paneReducer(s, { type: "toggleCollapse" }, LIMITS);
    expect(s.mode).toBe("normal");
    s = paneReducer(s, { type: "toggleExpand" }, LIMITS);
    expect(s).toEqual({ width: 520, mode: "expanded" });
    // Esc / the restore button.
    expect(paneReducer(s, { type: "restore" }, LIMITS)).toEqual({ width: 520, mode: "normal" });
  });

  it("collapse and expand are one mode, not two flags — the pane cannot be both", () => {
    const collapsed = paneReducer(NORMAL, { type: "collapse" }, LIMITS);
    expect(paneReducer(collapsed, { type: "expand" }, LIMITS).mode).toBe("expanded");
  });
});

describe("persistence", () => {
  it("keys one entry per page id", () => {
    expect(paneStorageKey("jobs")).toBe("tit-pane-jobs");
    expect(paneStorageKey("results")).toBe("tit-pane-results");
  });

  it("round-trips a dragged width — what the e2e reload assertion depends on", () => {
    const storage = memoryStorage();
    writePaneState("results", { width: 690, mode: "normal" }, storage);
    expect(readPaneState("results", LIMITS, storage)).toEqual({ width: 690, mode: "normal" });
  });

  it("never restores the expanded mode: a page whose work pane is missing on arrival reads as broken", () => {
    const storage = memoryStorage();
    writePaneState("jobs", { width: 400, mode: "expanded" }, storage);
    expect(JSON.parse(storage.data.get("tit-pane-jobs")!)).toEqual({ width: 400, mode: "normal" });
    expect(readPaneState("jobs", LIMITS, storage).mode).toBe("normal");
  });

  it("restores a collapsed pane, which is a layout preference", () => {
    const storage = memoryStorage();
    writePaneState("jobs", { width: null, mode: "collapsed" }, storage);
    expect(readPaneState("jobs", LIMITS, storage)).toEqual({ width: null, mode: "collapsed" });
  });

  it("re-clamps a stored width against the current limits", () => {
    const storage = memoryStorage({ "tit-pane-results": JSON.stringify({ width: 2000, mode: "normal" }) });
    expect(readPaneState("results", LIMITS, storage).width).toBe(880);
  });

  it("falls back to the CSS default for a missing, corrupt or hostile entry", () => {
    expect(readPaneState("results", LIMITS, undefined)).toEqual(NORMAL);
    expect(readPaneState("results", LIMITS, memoryStorage())).toEqual(NORMAL);
    expect(readPaneState("results", LIMITS, memoryStorage({ "tit-pane-results": "{oops" }))).toEqual(NORMAL);
    expect(readPaneState("results", LIMITS, memoryStorage({ "tit-pane-results": "42" }))).toEqual(NORMAL);
    expect(
      readPaneState("results", LIMITS, memoryStorage({ "tit-pane-results": JSON.stringify({ width: "wide", mode: "huge" }) })),
    ).toEqual(NORMAL);
  });

  it("does not throw when storage itself throws (site data blocked)", () => {
    const hostile: PaneStorage = {
      getItem() {
        throw new DOMException("denied");
      },
      setItem() {
        throw new DOMException("quota");
      },
    };
    expect(readPaneState("jobs", LIMITS, hostile)).toEqual(NORMAL);
    expect(() => writePaneState("jobs", { width: 500, mode: "normal" }, hostile)).not.toThrow();
  });
});

/**
 * `ui/paneState.ts` — the right pane's clamping and its three modes (program U13).
 *
 * The e2e specs assert what the pane *measures* on screen (`paneWidths().right` grows by 200 ± 4
 * after a drag, reads 0 when collapsed, and the work pane reads 0 when expanded). This file asserts
 * the arithmetic behind those numbers, where a bad clamp is one assertion rather than one browser.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  PANE_HANDLE,
  PREVIEW_PANE_MIN,
  RUN_PANE_MIN,
  RUN_STACK_BODY,
  RUN_WORK_MAX,
  RUN_WORK_MIN,
  runPaneLimits,
  RUN_SPLIT_CSS_VARS,
  paneLimits,
  previewPaneLimits,
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

describe("previewPaneLimits", () => {
  // Results' preview and Jobs' detail column: a 320 px floor, a ceiling at 70 % of the window.
  it("is 320 px to 70 % of the window", () => {
    expect(previewPaneLimits(1280)).toEqual({ min: 320, max: 896 });
    expect(previewPaneLimits(2000)).toEqual({ min: 320, max: 1400 });
    expect(PREVIEW_PANE_MIN).toBe(320);
  });

  it("falls back to 1280 rather than producing a zero-width range", () => {
    expect(previewPaneLimits(0)).toEqual(previewPaneLimits(1280));
    expect(previewPaneLimits(Number.NaN)).toEqual(previewPaneLimits(1280));
  });

  it("is what paneLimits answers for a preview, whatever the split box measures", () => {
    expect(paneLimits("preview", 1656, 2000)).toEqual(previewPaneLimits(2000));
    expect(paneLimits("run", 1656, 2000)).toEqual(runPaneLimits(1656));
  });
});

/**
 * The run split (2026-09-23): the user dragged the Terminal/Scene pane to 70 vw and got a 162 px
 * Jobs table at 1440, or left it at 36 vw and got a 959 px one at 1920 (offscreen probe, mock
 * fixture). The rule is now in pixels of the split box: work 640–800, pane ≥ 400, 6 px handle.
 * Expected values below are that sentence's arithmetic done by hand, not read off the function.
 */
describe("runPaneLimits", () => {
  it("gives the pane what the work pane's 640–800 px band leaves (hand-computed)", () => {
    // 1280 window: body 1280 - 56 rail - 2x16 pad = 1192; room 1186 → pane 386..546, floored at 400.
    expect(runPaneLimits(1192)).toEqual({ min: 400, max: 546 });
    // 1920 window: body 1920 - 216 - 2x24 = 1656; room 1650 → pane 850..1010.
    expect(runPaneLimits(1656)).toEqual({ min: 850, max: 1010 });
  });

  it("keeps the work pane in [640, 800] and the pane at or over 400 wherever the two fit", () => {
    for (let body = RUN_STACK_BODY; body <= 4000; body += 7) {
      const { min, max } = runPaneLimits(body);
      for (const pane of [min, max]) {
        const work = body - PANE_HANDLE - pane;
        expect(pane, `pane at body ${body}`).toBeGreaterThanOrEqual(RUN_PANE_MIN);
        expect(work, `work at body ${body}`).toBeGreaterThanOrEqual(RUN_WORK_MIN);
        expect(work, `work at body ${body}`).toBeLessThanOrEqual(RUN_WORK_MAX);
      }
    }
  });

  it("pins the pane at its floor in a box too narrow for both, instead of an empty range", () => {
    expect(runPaneLimits(900)).toEqual({ min: 400, max: 400 });
    expect(runPaneLimits(Number.NaN)).toEqual({ min: 400, max: 400 });
  });
});

/**
 * The CSS half of the same rule, read off disk: the stacked breakpoint and the pane's min/max are
 * literals in stylesheets (a media query cannot read a custom property), so this is what keeps them
 * equal to the constants above.
 */
describe("run split CSS agrees with paneState", () => {
  const SRC = resolve(__dirname, "../../src/renderer");
  const STACKED = ["ui/components.css", "ui/pane.css", "pages/_shared/run/run.css", "pages/_shared/scene/scene-pane.css", "pages/panels/panels.css"];

  it("stacks below the first window width where both panes fit beside the icon rail", () => {
    // Below 1440 the shell spends a 56 px icon rail and 2 x 16 px padding around the split box.
    const firstSideBySide = 1139 + 1;
    expect(firstSideBySide - 56 - 32).toBeGreaterThanOrEqual(RUN_STACK_BODY);
    // At 1440 the labelled rail (216) and 24 px padding still leave room for both.
    expect(1440 - 216 - 48).toBeGreaterThanOrEqual(RUN_STACK_BODY);
    for (const file of STACKED) {
      const css = readFileSync(resolve(SRC, file), "utf8");
      expect(css, file).toContain("@media (max-width: 1139px)");
      expect(css, file).not.toContain("max-width: 1099px");
    }
  });

  it("clamps the run pane with paneState's numbers, not a copy of them", () => {
    const css = readFileSync(resolve(SRC, "ui/components.css"), "utf8");
    expect(css).toContain("min-width: max(var(--run-pane-min), calc(100% - var(--run-work-max) - var(--pane-handle)))");
    expect(css).toContain("max-width: max(var(--run-pane-min), calc(100% - var(--run-work-min) - var(--pane-handle)))");
    expect(RUN_SPLIT_CSS_VARS).toMatchObject({
      "--run-work-min": `${RUN_WORK_MIN}px`,
      "--run-work-max": `${RUN_WORK_MAX}px`,
      "--run-pane-min": `${RUN_PANE_MIN}px`,
      "--pane-handle": `${PANE_HANDLE}px`,
    });
    // The grab strip is shared with pages outside `.page-layout` (Jobs), so its width stays a
    // literal; this is what keeps it equal to the handle the arithmetic subtracts.
    expect(css).toMatch(new RegExp(String.raw`\.page-layout-inspector-handle \{\s*width: ${PANE_HANDLE}px;`));
  });
});

describe("persistence", () => {
  it("keys one entry per page id", () => {
    expect(paneStorageKey("jobs")).toBe("tit-pane-v3-jobs");
    expect(paneStorageKey("results")).toBe("tit-pane-v3-results");
  });

  it("ignores a width stored under an older key, so the new wider default applies once", () => {
    // The run pane's default grew twice — fixed 360/400 px, then 36 vw, now 45 vw (DESIGN.md
    // §2.1). A machine holding the old width must NOT be pinned to it.
    const storage = memoryStorage({ "tit-pane-v2-simulator": JSON.stringify({ width: 461, mode: "normal" }) });
    expect(readPaneState("simulator", LIMITS, storage)).toEqual(NORMAL);
    // …and the user's next drag persists as before, under the new key.
    writePaneState("simulator", { width: 700, mode: "normal" }, storage);
    expect(readPaneState("simulator", LIMITS, storage).width).toBe(700);
  });

  it("round-trips a dragged width — what the e2e reload assertion depends on", () => {
    const storage = memoryStorage();
    writePaneState("results", { width: 690, mode: "normal" }, storage);
    expect(readPaneState("results", LIMITS, storage)).toEqual({ width: 690, mode: "normal" });
  });

  it("never restores the expanded mode: a page whose work pane is missing on arrival reads as broken", () => {
    const storage = memoryStorage();
    writePaneState("jobs", { width: 400, mode: "expanded" }, storage);
    expect(JSON.parse(storage.data.get("tit-pane-v3-jobs")!)).toEqual({ width: 400, mode: "normal" });
    expect(readPaneState("jobs", LIMITS, storage).mode).toBe("normal");
  });

  it("restores a collapsed pane, which is a layout preference", () => {
    const storage = memoryStorage();
    writePaneState("jobs", { width: null, mode: "collapsed" }, storage);
    expect(readPaneState("jobs", LIMITS, storage)).toEqual({ width: null, mode: "collapsed" });
  });

  it("re-clamps a stored width against the current limits", () => {
    const storage = memoryStorage({ "tit-pane-v3-results": JSON.stringify({ width: 2000, mode: "normal" }) });
    expect(readPaneState("results", LIMITS, storage).width).toBe(880);
  });

  it("falls back to the CSS default for a missing, corrupt or hostile entry", () => {
    expect(readPaneState("results", LIMITS, undefined)).toEqual(NORMAL);
    expect(readPaneState("results", LIMITS, memoryStorage())).toEqual(NORMAL);
    expect(readPaneState("results", LIMITS, memoryStorage({ "tit-pane-v3-results": "{oops" }))).toEqual(NORMAL);
    expect(readPaneState("results", LIMITS, memoryStorage({ "tit-pane-v3-results": "42" }))).toEqual(NORMAL);
    expect(
      readPaneState("results", LIMITS, memoryStorage({ "tit-pane-v3-results": JSON.stringify({ width: "wide", mode: "huge" }) })),
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

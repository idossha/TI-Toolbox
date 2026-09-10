/**
 * The jobs master–detail split: the table on the left, the selected job's detail on the right,
 * with a divider you can drag, double-click to reset, and move with the arrow keys.
 *
 * It replaces the panel's `ResizablePanels` (a fixed 560 px left pane, forgotten on every
 * collapse) for the reason in `split.ts`: the maintainer's screenshot showed a ~55/45 split whose
 * detail pane used only its left third, and a pixel default cannot keep a *shape* across 1280,
 * 1440 and 1920. Here the divider's position is a fraction of the box, clamped by real pixel
 * minimums, and remembered.
 *
 * Not a general `ui/` primitive on purpose: `ResizablePanels` and `PaneSeparator` already live in
 * `ui/Layout.tsx` — another lane's file — and a third variant there would be a third thing to keep
 * in sync for one surface's geometry.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import {
  clampListFraction,
  DEFAULT_LIST_FRACTION,
  listWidth,
  readSplit,
  STEP_COARSE_PX,
  STEP_PX,
  writeSplit,
} from "./split";

export function JobsSplit({ list, detail }: { list: ReactNode; detail: ReactNode }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [fraction, setFraction] = useState(readSplit);
  const [box, setBox] = useState(0);

  useLayoutEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const read = () => setBox(el.clientWidth);
    read();
    // Absent in jsdom: the split then renders at the default proportion, which is the same thing
    // it renders at before the first observation anywhere.
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(read);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Persist on change rather than on drag end: a keyboard nudge and a drag are the same edit, and
  // the write is one short string.
  useEffect(() => {
    writeSplit(fraction);
  }, [fraction]);

  const applyPx = useCallback(
    (px: number) => {
      const width = boxRef.current?.clientWidth ?? box;
      if (width <= 0) return;
      setFraction(clampListFraction(px / width, width));
    },
    [box],
  );

  const width = box > 0 ? listWidth(fraction, box) : undefined;

  return (
    <div className="jobs-split" ref={boxRef} data-testid="jobs-split">
      <div className="jobs-split-list" style={width === undefined ? { flex: DEFAULT_LIST_FRACTION } : { width }}>
        {list}
      </div>
      <button
        type="button"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the jobs list"
        aria-valuenow={Math.round(clampListFraction(fraction, box) * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        title="Drag to resize · double-click to reset"
        className="jobs-split-handle"
        data-testid="jobs-split-handle"
        onPointerDown={(e) => {
          const startX = e.clientX;
          const startWidth = width ?? 0;
          (e.target as HTMLElement).setPointerCapture(e.pointerId);
          const onMove = (ev: PointerEvent) => applyPx(startWidth + (ev.clientX - startX));
          const onUp = () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
          };
          window.addEventListener("pointermove", onMove);
          window.addEventListener("pointerup", onUp);
        }}
        onDoubleClick={() => setFraction(DEFAULT_LIST_FRACTION)}
        onKeyDown={(e) => {
          const step = e.shiftKey ? STEP_COARSE_PX : STEP_PX;
          if (e.key === "ArrowLeft") applyPx((width ?? 0) - step);
          else if (e.key === "ArrowRight") applyPx((width ?? 0) + step);
          else if (e.key === "Home") applyPx(0);
          else if (e.key === "End") applyPx(box);
          else if (e.key === "Enter" || e.key === " ") setFraction(DEFAULT_LIST_FRACTION);
          else return;
          e.preventDefault();
        }}
      />
      <div className="jobs-split-detail">{detail}</div>
    </div>
  );
}

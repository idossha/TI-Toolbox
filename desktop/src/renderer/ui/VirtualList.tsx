import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef, type CSSProperties, type ReactNode } from "react";
import { cn } from "./utils";

/**
 * Fixed-row-height virtualised list — used for the job console and long log/event streams.
 *
 * "Fixed" is load-bearing: every row is positioned absolutely at `index * rowHeight`, so a row
 * whose content is TALLER than `rowHeight` paints over its neighbours (the overlapping log lines
 * the maintainer screenshotted, caused by log "lines" that held embedded newlines). Callers must
 * therefore give each item exactly one visual line's worth of content — for the console that is
 * `jobEventsToLogLines`/`splitLogText`, which turn one server event into one item per VISUAL line.
 * Clipping the row box was tried and rejected: `overflow: hidden` makes the row its own scroll
 * container, so a long path stops contributing to the list's `scrollWidth` and can no longer be
 * scrolled to — trading one obstruction for another. The split is the fix; `tests/e2e/terminal.spec.ts`
 * measures both invariants (no two rows overlap, and the long line still scrolls sideways).
 */
export function VirtualList<T>({
  items,
  rowHeight,
  renderRow,
  getRowKey,
  className,
  style,
  followTail = false,
}: {
  items: T[];
  rowHeight: number;
  renderRow: (item: T, index: number) => ReactNode;
  /** Stable identity per item; defaults to the row index. */
  getRowKey?: (item: T, index: number) => string;
  className?: string;
  style?: CSSProperties;
  /** When true, stays scrolled to the bottom as items are appended. */
  followTail?: boolean;
}) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 12,
  });

  const atBottomRef = useRef(true);
  if (followTail && atBottomRef.current) {
    // Scroll after the DOM commits; rAF avoids fighting the virtualizer's own measurement pass.
    // `scrollToIndex` parks the box horizontally as well as vertically, which would snap a reader
    // back to column 0 of a long log line on every appended row. Follow tail is about the bottom,
    // not about the left edge, so the horizontal offset is restored.
    requestAnimationFrame(() => {
      const left = parentRef.current?.scrollLeft ?? 0;
      virtualizer.scrollToIndex(items.length - 1, { align: "end" });
      if (parentRef.current && left > 0) parentRef.current.scrollLeft = left;
    });
  }

  return (
    <div
      ref={parentRef}
      className={cn("virtual-list", className)}
      style={style}
      onScroll={(e) => {
        const el = e.currentTarget;
        atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < rowHeight;
      }}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
        {virtualizer.getVirtualItems().map((row) => (
          <div
            key={getRowKey ? getRowKey(items[row.index] as T, row.index) : row.key}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              height: row.size,
              transform: `translateY(${row.start}px)`,
            }}
          >
            {renderRow(items[row.index] as T, row.index)}
          </div>
        ))}
      </div>
    </div>
  );
}

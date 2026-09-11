import { useVirtualizer } from "@tanstack/react-virtual";
import { useLayoutEffect, useRef, type CSSProperties, type ReactNode } from "react";
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

  useLayoutEffect(() => {
    if (followTail && parentRef.current) scrollToBottom(parentRef.current);
  }, [followTail, items, rowHeight]);

  useLayoutEffect(() => {
    const viewport = parentRef.current;
    if (!followTail || !viewport) return;
    // A resized pane can move the tail out of view without changing the transcript.
    const observer = new ResizeObserver(() => scrollToBottom(viewport));
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [followTail]);

  return (
    <div
      ref={parentRef}
      className={cn("virtual-list", className)}
      style={style}
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

/** Follow is explicit: new output follows even if a prior scroll moved away from the tail. */
function scrollToBottom(viewport: HTMLDivElement): void {
  // Assign only the vertical offset; long log lines must keep their horizontal position.
  viewport.scrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
}

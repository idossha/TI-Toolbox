import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef, type CSSProperties, type ReactNode } from "react";
import { cn } from "./utils";

/** Fixed-row-height virtualised list — used for the job console and long log/event streams. */
export function VirtualList<T>({
  items,
  rowHeight,
  renderRow,
  className,
  style,
  followTail = false,
}: {
  items: T[];
  rowHeight: number;
  renderRow: (item: T, index: number) => ReactNode;
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
            key={row.key}
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

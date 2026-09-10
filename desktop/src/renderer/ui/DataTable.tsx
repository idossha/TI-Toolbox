import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";

/**
 * A type alias, not an `interface extends` — `ColumnDef` is a union (accessor/display/group
 * column defs), and an interface cannot extend a union type.
 */
export type DataTableColumn<T> = ColumnDef<T, unknown> & {
  /** Right-aligns the header and cells and renders values as tabular mono numbers. */
  numeric?: boolean;
};

/** Sticky header, sortable columns, optional row selection, right-aligned numeric columns. */
export function DataTable<T>({
  data,
  columns,
  getRowId,
  selectable = false,
  selected,
  onSelectedChange,
  emptyMessage = "No rows.",
  onRowClick,
  minRows = 0,
  fill = false,
}: {
  data: T[];
  columns: DataTableColumn<T>[];
  getRowId?: (row: T) => string;
  selectable?: boolean;
  selected?: RowSelectionState;
  onSelectedChange?: (selected: RowSelectionState) => void;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  /** Keep the table at least this many rows tall, drawing the surplus as ground rows. */
  minRows?: number;
  /**
   * Draw ground rows to the bottom of the box the table is in — the shape of the list that will
   * appear, instead of a table that stops a quarter of the way down the page.
   *
   * It lives here because the rows are this component's: two pages (`pages/jobs/jobs-page.css`'s
   * `.jobs-page-filler` and `pages/panels/panels.css`'s `.panel-table-filler`) each painted the
   * same repeating gradient BEHIND the table to fake them, which is one rule written twice, in two
   * files that do not know about each other, and neither could align with a row the table
   * actually draws.
   *
   * The box is height-constrained by the page (a flex column), so adding rows changes the table's
   * scroll height and never the box's client height: one observation, one answer, no oscillation.
   */
  fill?: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const [fitRows, setFitRows] = useState(0);
  const measure = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const head = el.querySelector("thead");
    const headH = head ? head.getBoundingClientRect().height : 0;
    const row = el.querySelector("tbody tr:not(.data-table-filler)");
    const cssRowH = parseFloat(getComputedStyle(el).getPropertyValue("--row-h"));
    // The empty state has one row and it is a message, not a row of the list: fall back to the
    // token every row is laid out on, so the ground rows keep the list's own pitch.
    const rowH = row && row.clientHeight > 0 ? row.getBoundingClientRect().height : Number.isFinite(cssRowH) ? cssRowH : 28;
    if (rowH < 1) return;
    const fits = Math.max(0, Math.floor((el.clientHeight - headH) / rowH));
    setFitRows((prev) => (prev === fits ? prev : fits));
  }, []);
  useLayoutEffect(() => {
    // `ResizeObserver` is absent in jsdom and in older engines; the table then renders exactly
    // the rows it has, which is the pre-`fill` behaviour and never a crash.
    if (!fill || !box || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure(box));
    observer.observe(box);
    return () => observer.disconnect();
  }, [fill, box, measure]);
  // A row arriving does not resize the box (its height comes from the page), so the observer never
  // fires for it — re-measure on the next frame, after that row has laid out.
  useEffect(() => {
    if (!fill || !box) return;
    const frame = requestAnimationFrame(() => measure(box));
    return () => cancelAnimationFrame(frame);
  }, [fill, box, measure, data.length]);
  const table = useReactTable({
    data,
    columns: columns as ColumnDef<T, unknown>[],
    state: { sorting, rowSelection: selected ?? {} },
    onSortingChange: setSorting,
    onRowSelectionChange: (updater) => {
      if (!onSelectedChange) return;
      const next = typeof updater === "function" ? updater(selected ?? {}) : updater;
      onSelectedChange(next);
    },
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    enableRowSelection: selectable,
  });

  const targetRows = Math.max(minRows, fill ? fitRows : 0);
  // `Math.max(1, …)`: an empty table still shows one row — its message — and the ground rows go
  // below it, so the message sits where the first row of the list will be.
  const groundRows = Math.max(0, targetRows - Math.max(1, data.length));

  return (
    <div className="data-table-container scroll-x" data-fill={fill ? "true" : undefined} ref={setBox}>
      <table className="data-table">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => {
                const numeric = (header.column.columnDef as DataTableColumn<T>).numeric;
                const sortable = header.column.getCanSort();
                const sortState = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    data-sortable={sortable || undefined}
                    data-align={numeric ? "right" : undefined}
                    onClick={sortable ? header.column.getToggleSortingHandler() : undefined}
                  >
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                    {sortable && (
                      <span className="data-table-sort-icon">
                        {sortState === "asc" ? <ArrowUp size={12} /> : sortState === "desc" ? <ArrowDown size={12} /> : <ArrowUpDown size={12} />}
                      </span>
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} data-selected={row.getIsSelected() || undefined} onClick={() => onRowClick?.(row.original)}>
              {row.getVisibleCells().map((cell) => {
                const numeric = (cell.column.columnDef as DataTableColumn<T>).numeric;
                return (
                  <td key={cell.id} data-align={numeric ? "right" : undefined} className={numeric ? "data-table-numeric" : undefined}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                );
              })}
            </tr>
          ))}
          {data.length === 0 && (
            <tr>
              <td colSpan={columns.length} style={{ textAlign: "center", color: "var(--ink-2)" }}>
                {emptyMessage}
              </td>
            </tr>
          )}
          {Array.from({ length: groundRows }, (_, i) => (
            <tr key={`ground-${i}`} className="data-table-filler" aria-hidden>
              <td colSpan={columns.length} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

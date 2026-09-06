/**
 * The status bar's cell registry (DESIGN.md §11, program U8).
 *
 * The v2 bar printed `RAS — Space — Renderer —` on Jobs, Subjects, Results and Pre-processing:
 * three cells about a canvas that was not mounted, each filled with a dash because the shell knew
 * the cells but not whether they meant anything. v3 inverts it — **the page registers what it can
 * actually fill, and a cell with no value is not rendered at all.** `AppStatusBar` gains no page
 * knowledge and keeps only the right cluster (connection, versions), which are the two facts that
 * are true regardless of which page is on.
 *
 * Registration is per active component, so leaving a page removes its cells: a stale cell from a
 * page you left is not a bug you can write.
 */
import { useEffect, useId, useMemo } from "react";
import type { ReactNode } from "react";
import { create } from "zustand";
import { usePageActive } from "./pageActivity";

export interface StatusCellSpec {
  /** Unique within the page. Also the `data-status-cell` attribute the metrics instrument reads. */
  id: string;
  /** Omitted for self-describing values ("subject"); required for ones that need a unit ("RAS"). */
  label?: string;
  /** `null` / `undefined` / `""` → the cell is NOT rendered. There is no "—" in the status bar. */
  value: ReactNode | null | undefined;
  /** Ascending, left to right; 10 / 20 / 30 by convention. */
  priority: number;
  title?: string;
  tone?: "default" | "warning" | "danger";
  /** Tabular mono, e.g. an RAS read-out. */
  mono?: boolean;
}

interface StatusCellState {
  /** Keyed by the registering component instance, so two pages can never clobber each other. */
  byOwner: Record<string, StatusCellSpec[]>;
  register: (owner: string, cells: StatusCellSpec[]) => void;
  unregister: (owner: string) => void;
}

export const useStatusCellStore = create<StatusCellState>((set) => ({
  byOwner: {},
  register: (owner, cells) => set((s) => ({ byOwner: { ...s.byOwner, [owner]: cells } })),
  unregister: (owner) =>
    set((s) => {
      if (!(owner in s.byOwner)) return s;
      const next = { ...s.byOwner };
      delete next[owner];
      return { byOwner: next };
    }),
}));

/**
 * A cell's identity for change detection: everything the bar renders except the node itself, plus
 * the value's string form. This is what makes an inline array literal safe — a page may write
 * `useStatusCells([{ id: "ras", value: ras, priority: 10 }])` in its render body without pushing a
 * store write on every keystroke elsewhere on the page.
 *
 * A `ReactNode` that is not a primitive stringifies to a constant, so a page passing a *node* whose
 * content changes must give the cell a changing `title` or `id` — or, better, pass a string, which
 * §11.3 asks for anyway ("a value is a string or a node the page has already formatted").
 */
function cellKey(cells: StatusCellSpec[]): string {
  return cells
    .map((c) => {
      const v = c.value;
      const text = v === null || v === undefined ? "" : typeof v === "object" ? "<node>" : String(v);
      return [c.id, c.label ?? "", c.priority, c.tone ?? "", c.mono ? "1" : "", c.title ?? "", text].join("");
    })
    .join("");
}

/**
 * Registers `cells` while the calling page is active; hiding or unmounting it removes its cells.
 *
 * Empty-valued cells are dropped here rather than at render time, so `useRegisteredStatusCells()`
 * and the `data-status-cell` attributes the metrics read agree with what is on screen.
 */
export function useStatusCells(cells: StatusCellSpec[]): void {
  const active = usePageActive();
  const owner = useId();
  const register = useStatusCellStore((s) => s.register);
  const unregister = useStatusCellStore((s) => s.unregister);
  const key = cellKey(cells);
  // The key, not the array, is the dependency: the array is a fresh literal on every render.
  const stable = useMemo(() => cells.filter(hasValue), [key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!active) return;
    register(owner, stable);
    return () => unregister(owner);
  }, [active, owner, stable, register, unregister]);
}

/** `null`, `undefined` and `""` are "nothing to say", and §11 renders nothing for them. */
export function hasValue(cell: StatusCellSpec): boolean {
  return cell.value !== null && cell.value !== undefined && cell.value !== "";
}

/** Every registered cell, ascending `priority`, ties broken by registration order. */
export function sortStatusCells(byOwner: Record<string, StatusCellSpec[]>): StatusCellSpec[] {
  return Object.values(byOwner)
    .flat()
    .filter(hasValue)
    .map((cell, i) => ({ cell, i }))
    .sort((a, b) => a.cell.priority - b.cell.priority || a.i - b.i)
    .map((x) => x.cell);
}

/** What `AppStatusBar` renders on the left. Nothing else may write the bar. */
export function useRegisteredStatusCells(): StatusCellSpec[] {
  const byOwner = useStatusCellStore((s) => s.byOwner);
  return useMemo(() => sortStatusCells(byOwner), [byOwner]);
}

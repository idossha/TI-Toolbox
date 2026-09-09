/**
 * `SelectionList` — **the** way anything is picked out of a list in v3 (plan of record
 * `docs/dev/HISTORY.md § 2026-09-05/06 (Tetravox auto-update, selection, pipeline canvas)` §1-C, C1/C2).
 *
 * The defect it closes, in the maintainer's words: *"in the TI toolbox 2.5.0 we had a great logic
 * for selecting multiple jobs … right now it's too convoluted for the users to choose and to
 * understand the jobs that they're selecting."* v3 had grown **five** selection idioms —
 * a row-click-*and*-checkbox table (`SubjectsField`), the same table deliberately without a filter
 * (`ParticipantsField`), two `Select` combos per electrode pair, `MultiSelect` chips per ex bucket,
 * and a 3-D click-toggle — so a user learned "choose several things" five times and none of them
 * agreed on what a click did.
 *
 * 2.5.0's rule, restated and implemented here once:
 *
 *   - **click** selects exactly one row (and parks the range anchor there),
 *   - **⇧-click** selects the range from the anchor to the row, inclusive,
 *   - **⌘/Ctrl-click** toggles one row, leaving the rest alone,
 *   - **the checkbox column** is the same toggle, made visible: a mouse-only or touch user never
 *     has to know a modifier exists, and a keyboard user never has to guess whether the row is
 *     selected — which is the ambiguity `SubjectsField` shipped (whole-row click *and* a checkbox,
 *     with no way to tell which one you were about to hit),
 *   - **⌘A** selects everything the filter is currently showing, **Esc** clears the selection,
 *   - **`All · None`** are the only bulk buttons — the one pair 2.5.0 had, not a menu,
 *   - an **always-on filter box**, and an `N of M selected` badge that is the whole status line.
 *
 * Multi-select picker dialogs make every row click a toggle; Shift still extends a range.
 *
 * Two shapes, one model:
 *   - `SelectionList` — the list itself, for a page that has room for it (subjects, participants,
 *     jobs, saved ROIs);
 *   - `SelectionPicker` — the same list inside a dialog behind a summary button, for a page that
 *     does not (an ex bucket, an electrode-pair slot, an atlas's 150 regions). Its `mode="single"`
 *     form is what replaces the two `Select` combos of a pair.
 *
 * Everything below the `Model` heading is pure and unit-tested in
 * `tests/unit/selection-model.test.ts`; the component is a rendering of it.
 *
 * **Filter interplay**, the rule every bulk operation obeys: a row the filter is hiding keeps the
 * state it has. `All` selects the *visible* rows in addition to what is already chosen, `None`
 * deselects the *visible* rows only, and ⌘A is exactly `All`. Anything else silently edits rows the
 * user cannot see, which is how a filtered "select all" quietly queues forty jobs.
 *
 * **Order is meaning**: the value array keeps the order rows were chosen in, because that is the
 * order jobs are submitted in (`optimizer`'s `flexSubmissions`, `simulator`'s rows).
 *
 * **Shape**: a `<table>` with real column headers, wrapped in a `role="listbox"`
 * `aria-multiselectable` box whose rows are `role="option"`. The table is what the run pages'
 * measured ground-row machinery reads (`tests/e2e/table-room.spec.ts` counts `tbody tr`), and the
 * explicit roles are what a screen reader reads; `role="presentation"` on the table keeps the two
 * from contradicting each other.
 */
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { Button } from "./Button";
import { TextInput } from "./Field";
import { Skeleton } from "./Feedback";
import { Dialog } from "./Overlay";
import { Checkbox } from "./Toggle";
import { cn } from "./utils";
import "./selection.css";

/* ------------------------------------------------------------------ Model */

export type SelectionMode = "multi" | "single";

/** One extra column, for a list whose rows are richer than label + detail (the Jobs page). */
export interface SelectionColumn {
  id: string;
  header: string;
  cell: (item: SelectionItem) => ReactNode;
  numeric?: boolean;
}

/** One catalog item: a subject, a montage, a region, an electrode, a job, a participant row. */
export interface SelectionItem {
  id: string;
  /** The primary cell. A string is rendered monospaced; a node is rendered as given. */
  label: ReactNode;
  /** What the filter box matches on. Defaults to `id` plus a string `label`. */
  search?: string;
  /** Middle column — presence chips, coordinates, a job's state. */
  detail?: ReactNode;
  /**
   * A `"#rrggbb"` colour dot before the label — the atlas colour an ROI row is painted in, so the
   * picker and the 3D pane name the same region with the same colour. Omitted for every list that
   * has no colour of its own, which is all of them but the region lists.
   */
  swatch?: string;
  /** The row's own object, for `columns[].cell` to read. */
  value?: unknown;
  /** "Why not" text. The row stays selectable (its reason is what Run then prints). */
  reason?: string;
  /** Hard-excluded: never selectable by any path, and skipped by `All`. */
  disabled?: boolean;
  /** Extra `data-*` written onto the row, so a spec can assert page-specific state. */
  data?: Record<string, string | undefined>;
}

/** Case-insensitive substring match over `search` (or the id + a string label). One box, no syntax. */
export function itemText(item: SelectionItem): string {
  if (item.search !== undefined) return item.search;
  return typeof item.label === "string" ? `${item.id} ${item.label}` : item.id;
}

export function filterItems(items: SelectionItem[], query: string): SelectionItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter((i) => itemText(i).toLowerCase().includes(q));
}

/** Selectable = not hard-disabled. An ineligible-but-explained row is still selectable (J3). */
function selectable(item: SelectionItem): boolean {
  return item.disabled !== true;
}

/**
 * `All`: add every visible, selectable row to the selection, in list order, keeping what was
 * already chosen (including rows the filter is hiding).
 */
export function selectAllVisible(value: string[], visible: SelectionItem[], exclude?: ReadonlySet<string>): string[] {
  const out = [...value];
  for (const item of visible) {
    if (selectable(item) && !exclude?.has(item.id) && !out.includes(item.id)) out.push(item.id);
  }
  return out;
}

/** `None` / Esc: drop the visible rows only — a hidden row keeps its state. */
export function selectNoneVisible(value: string[], visible: SelectionItem[]): string[] {
  const ids = new Set(visible.map((i) => i.id));
  return value.filter((id) => !ids.has(id));
}

export interface SelectionIntent {
  /** ⌘/Ctrl held: toggle this row only. */
  toggle?: boolean;
  /** ⇧ held: select the range from the anchor to this row. */
  range?: boolean;
}

export interface SelectionState {
  value: string[];
  /** The row a range extends from. `null` before the first click. */
  anchor: string | null;
}

/**
 * The one click rule (C1). `visible` is the filtered list, so a ⇧-range is a range *of what you can
 * see* — never a sweep through rows the filter is hiding.
 *
 * `single` mode ignores the modifiers: one row, always, because a control that can express two
 * selections for a form field that takes one is a control that lies.
 */
export function applyClick(
  state: SelectionState,
  visible: SelectionItem[],
  id: string,
  intent: SelectionIntent = {},
  mode: SelectionMode = "multi",
): SelectionState {
  const item = visible.find((i) => i.id === id);
  if (item && !selectable(item)) return state;
  if (mode === "single") {
    return { value: state.value.includes(id) && !intent.range ? [] : [id], anchor: id };
  }
  if (intent.range && state.anchor !== null) {
    const from = visible.findIndex((i) => i.id === state.anchor);
    const to = visible.findIndex((i) => i.id === id);
    if (from >= 0 && to >= 0) {
      const [lo, hi] = from <= to ? [from, to] : [to, from];
      const span = visible.slice(lo, hi + 1).filter(selectable);
      // A range ADDS; it does not replace. Two ⇧-ranges in a 200-row list is a real way to build a
      // selection, and a replacing range makes the second one silently discard the first.
      return { value: selectAllVisible(state.value, span), anchor: state.anchor };
    }
  }
  if (intent.toggle) {
    const next = state.value.includes(id) ? state.value.filter((x) => x !== id) : [...state.value, id];
    return { value: next, anchor: id };
  }
  // A plain click on the only selected row clears it — otherwise a single-row list would have no
  // way back to "nothing chosen" without the None button.
  const only = state.value.length === 1 && state.value[0] === id;
  return { value: only ? [] : [id], anchor: id };
}

/** The badge, and the `SelectionPicker` trigger's line: `3 of 12 selected`, `None of 12`. */
export function selectionBadge(selectedCount: number, total: number): string {
  if (selectedCount === 0) return `None of ${total} selected`;
  return `${selectedCount} of ${total} selected`;
}

/**
 * The picker trigger's summary: `3 regions · F7, P7…` / `F7` / `Choose…`. Names, never ids — the
 * trigger is what a person reads when the list is closed, and `lh:1` is not an answer.
 *
 * **The count comes first** (maintainer, 2026-09-06, on the Analyzer's region picker, applied
 * site-wide because it is better everywhere): with more than one thing chosen, "how many" is the
 * question a closed control is actually asked, and the old `a, b, c, +2 more` answered it last and
 * only by arithmetic — and, in a narrow cell, often not at all, because the trailing `+2 more` is
 * exactly the part that gets ellipsised away. One selection still reads as its own name: `2
 * subjects · ernie, 101` is right, `1 subjects · ernie` never is.
 */
export function selectionSummary(value: string[], placeholder = "Choose…", cap = 2, noun?: string): string {
  if (value.length === 0) return placeholder;
  if (value.length === 1) return value[0] as string;
  const names = value.slice(0, cap).join(", ");
  const shown = value.length > cap ? `${names}…` : names;
  return noun ? `${value.length} ${noun} · ${shown}` : shown;
}

/** `Regions` -> `regions`, `Subject` -> `subjects`: the noun the count is counting. */
export function selectionNoun(label: string, count: number): string {
  const word = label.trim().toLowerCase().replace(/\(s\)$/, "").replace(/s$/, "");
  return count === 1 ? word : `${word}s`;
}

/* -------------------------------------------------------------- Component */

export interface SelectionListProps {
  items: SelectionItem[];
  /** Chosen ids, in the order they were chosen. */
  value: string[];
  onChange: (value: string[]) => void;
  mode?: SelectionMode;
  /** Picker rows toggle independently; page lists retain single-click replacement. */
  toggleOnRowClick?: boolean;
  /** Names the listbox for assistive tech ("Subjects", "E1+ electrodes"). */
  label: string;
  /** Column headings. Omitted columns are still rendered — headerless. */
  headers?: { label?: string; detail?: string; reason?: string };
  /** Extra columns after the label. Given, they replace the single `detail` column. */
  columns?: SelectionColumn[];
  /**
   * `listbox` (the default) is right for a list of things: rows are `option`s and a screen reader
   * reads one name per row. `grid` is right for a multi-column TABLE of things — the Jobs page,
   * whose row is state + kind + subjects + stage + elapsed — where "row" and "cell" are what a
   * screen reader has to be able to navigate. Both are multi-selectable and both are driven by the
   * exact same model; only the roles differ.
   */
  aria?: "listbox" | "grid";
  /** Controlled filter text. Omit for the list's own state. */
  query?: string;
  onQueryChange?: (query: string) => void;
  filterPlaceholder?: string;
  /** `subject` ⇒ rows are `subject-row-<id>`, the filter is `subject-filter`. */
  idPrefix?: string;
  /** Container testid. Defaults to `${idPrefix}-selection`. */
  testId?: string;
  /** Filter box testid. Defaults to `${idPrefix}-filter`. */
  filterTestId?: string;
  /** Class added to every row — pages keep their existing row vocabulary (`.subject-picker-row`). */
  rowClassName?: string;
  /**
   * Rows `All` (and the header checkbox, and ⌘A) skip while leaving them individually selectable.
   * The subject grammar's J3 rule: a subject that cannot run here keeps its checkbox — its reason
   * is what the Run button then prints — but a bulk convenience must never create a blocked run.
   */
  bulkExclude?: string[];
  /** Drawn to the right of `All · None`. */
  toolbar?: ReactNode;
  /** Hide the toolbar row entirely (a `single`-mode picker has nothing to select all of). */
  hideBulk?: boolean;
  /**
   * Hide the `N of M selected` badge. For a control that already states its selection somewhere the
   * user is looking — `SubjectsField`'s summary line names the chosen subjects in the header band —
   * a second count in the toolbar is the same fact printed twice.
   */
  hideBadge?: boolean;
  hideFilter?: boolean;
  loading?: boolean;
  emptyMessage?: string;
  /** Ground rows to this many, the way the run pages' tables already do. */
  minRows?: number;
  /** `max-height` of the scroll box, in px. */
  maxHeight?: number;
  /** Ref to the scroll box, for a page that measures its own room (`SubjectsField`'s `fill`). */
  scrollRef?: (el: HTMLDivElement | null) => void;
  scrollTestId?: string;
  /**
   * Lifts the 176px cap and lets the box take the room its layout gives it — and draws ground rows
   * to the bottom of that room, which is what makes a short list on the Jobs page show the SHAPE of
   * the list rather than ending in a hard edge halfway up the pane (DESIGN.md §4.4).
   */
  scrollFill?: boolean;
  /**
   * Never pad the list: no `minRows` floor and no measured ground rows, whatever `scrollFill` says.
   * The subject list asks for this — the maintainer's "just a simple list of subjects": with the
   * ground rows in it, a 3-subject project read as a table of empty lines rather than a short list.
   */
  hideGround?: boolean;
  /**
   * Esc clears the visible selection. Off inside a dialog (`SelectionPicker`), where Esc means
   * "close this" — a key that both closes the dialog and throws away what was chosen in it is a
   * key nobody can press safely.
   */
  escClears?: boolean;
  /** Above this many visible rows the list windows its DOM (see `WINDOW_FROM`). */
  windowFrom?: number;
  className?: string;
}

/**
 * Past this many visible rows only the rows near the viewport are in the DOM, with a spacer row
 * above and below. Below it the whole list is rendered, which is what keeps the run pages' measured
 * ground rows (`minRows`, `tests/e2e/table-room.spec.ts`) honest — a table with filler rows is by
 * definition shorter than its box, so it can never be the long case.
 */
const WINDOW_FROM = 150;
const ROW_H = 26;
const OVERSCAN = 10;

export function SelectionList({
  items,
  value,
  onChange,
  mode = "multi",
  toggleOnRowClick = false,
  label,
  headers,
  columns,
  aria = "listbox",
  query: queryProp,
  onQueryChange,
  filterPlaceholder = "Filter…",
  idPrefix = "selection",
  testId,
  filterTestId,
  rowClassName,
  bulkExclude,
  toolbar,
  hideBulk = false,
  hideBadge = false,
  hideFilter = false,
  loading = false,
  emptyMessage = "Nothing to choose from.",
  minRows = 0,
  maxHeight,
  scrollRef,
  scrollTestId,
  scrollFill,
  hideGround = false,
  escClears = true,
  windowFrom = WINDOW_FROM,
  className,
}: SelectionListProps) {
  const listId = useId();
  const [ownQuery, setOwnQuery] = useState("");
  const query = queryProp ?? ownQuery;
  const setQuery = onQueryChange ?? setOwnQuery;
  const [anchor, setAnchor] = useState<string | null>(null);
  const [focusIndex, setFocusIndex] = useState(0);
  const boxRef = useRef<HTMLDivElement | null>(null);

  const visible = useMemo(() => filterItems(items, query), [items, query]);
  const excluded = useMemo(() => new Set(bulkExclude ?? []), [bulkExclude]);
  const bulkTargets = useMemo(() => visible.filter((i) => !i.disabled && !excluded.has(i.id)), [visible, excluded]);
  const selectedVisible = useMemo(() => visible.filter((i) => value.includes(i.id)).length, [visible, value]);
  const allVisibleSelected = bulkTargets.length > 0 && bulkTargets.every((i) => value.includes(i.id));

  const commit = useCallback(
    (next: SelectionState) => {
      setAnchor(next.anchor);
      onChange(next.value);
    },
    [onChange],
  );

  const click = useCallback(
    (e: MouseEvent, id: string) => {
      commit(applyClick({ value, anchor }, visible, id, { toggle: toggleOnRowClick || e.metaKey || e.ctrlKey, range: e.shiftKey }, mode));
    },
    [anchor, commit, mode, toggleOnRowClick, value, visible],
  );

  const toggleOne = useCallback(
    (id: string) => {
      commit(applyClick({ value, anchor }, visible, id, { toggle: mode !== "single" }, mode));
    },
    [anchor, commit, mode, value, visible],
  );

  /* ---- windowing ---- */
  const windowed = visible.length > windowFrom;
  const [scrollTop, setScrollTop] = useState(0);
  const [boxH, setBoxH] = useState(maxHeight ?? 320);
  useEffect(() => {
    const el = boxRef.current;
    if (!el || !windowed) return;
    setBoxH(el.clientHeight || maxHeight || 320);
  }, [windowed, maxHeight, visible.length]);
  const start = windowed ? Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN) : 0;
  const end = windowed ? Math.min(visible.length, Math.ceil((scrollTop + boxH) / ROW_H) + OVERSCAN) : visible.length;
  const slice = windowed ? visible.slice(start, end) : visible;

  /* ---- keyboard ---- */
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>): void {
    // Native checkbox keyboard activation already owns its toggle.
    if ((e.target as HTMLElement).closest(".checkbox-root")) return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a") {
      e.preventDefault();
      if (mode !== "single") onChange(selectAllVisible(value, visible, excluded));
      return;
    }
    if (e.key === "Escape") {
      if (!escClears || selectedVisible === 0) return;
      e.preventDefault();
      e.stopPropagation();
      onChange(selectNoneVisible(value, visible));
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Home" || e.key === "End") {
      e.preventDefault();
      const last = visible.length - 1;
      const next =
        e.key === "Home" ? 0 : e.key === "End" ? last : Math.min(last, Math.max(0, focusIndex + (e.key === "ArrowDown" ? 1 : -1)));
      setFocusIndex(next);
      const item = visible[next];
      if (item && e.shiftKey && mode !== "single") {
        commit(applyClick({ value, anchor }, visible, item.id, { range: true }, mode));
      }
      if (windowed && boxRef.current) {
        const top = next * ROW_H;
        const el = boxRef.current;
        if (top < el.scrollTop) el.scrollTop = top;
        else if (top + ROW_H > el.scrollTop + el.clientHeight) el.scrollTop = top + ROW_H - el.clientHeight;
      } else {
        boxRef.current?.querySelector(`[data-row-index="${next}"]`)?.scrollIntoView({ block: "nearest" });
      }
      return;
    }
    if (e.key === " " || e.key === "Enter") {
      const item = visible[focusIndex];
      if (!item) return;
      e.preventDefault();
      toggleOne(item.id);
    }
  }

  /* Ground rows, measured: how many more rows would fit in the box as it currently is. The box's
     height comes from its layout and never from its content (`flex: 1` in a column), so adding
     filler rows cannot change the answer — one observation, one result, no oscillation. */
  const [fitRows, setFitRows] = useState(0);
  useEffect(() => {
    const el = boxRef.current;
    if (!scrollFill || hideGround || !el || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const head = el.querySelector("thead");
      const headH = head ? head.getBoundingClientRect().height : 0;
      const row = el.querySelector("tbody tr");
      const rowH = row ? row.getBoundingClientRect().height : 0;
      if (rowH < 1) return;
      const fits = Math.max(0, Math.floor((el.clientHeight - headH) / rowH));
      setFitRows((prev) => (prev === fits ? prev : fits));
    };
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [scrollFill, hideGround, visible.length]);

  const anyReason = visible.some((i) => i.reason);
  const extra = columns ?? [];
  const columnCount = 1 + (extra.length > 0 ? extra.length : headers?.detail !== undefined ? 1 : 0) + (anyReason ? 1 : 0);
  const groundRows = hideGround ? 0 : Math.max(0, Math.max(minRows, scrollFill ? fitRows : 0) - visible.length);

  return (
    <div
      className={cn("selection", className)}
      data-testid={testId ?? `${idPrefix}-selection`}
      data-mode={mode}
      data-selected={value.length}
      data-visible={visible.length}
    >
      {(!hideFilter || (!hideBulk && mode !== "single") || !hideBadge || toolbar) && (
        <div className="selection-tools">
          {!hideFilter && (
            <TextInput
              className="selection-filter"
              aria-label={`Filter ${label.toLowerCase()}`}
              placeholder={filterPlaceholder}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid={filterTestId ?? `${idPrefix}-filter`}
            />
          )}
          {!hideBulk && mode !== "single" && (
            <div className="selection-bulk" role="group" aria-label={`Select ${label.toLowerCase()}`}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onChange(selectAllVisible(value, visible, excluded))}
                disabled={bulkTargets.length === 0 || allVisibleSelected}
                data-testid={`${idPrefix}-select-all`}
              >
                All
              </Button>
              <span className="selection-bulk-sep" aria-hidden>
                ·
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onChange(selectNoneVisible(value, visible))}
                disabled={selectedVisible === 0}
                data-testid={`${idPrefix}-select-none`}
              >
                None
              </Button>
            </div>
          )}
          {!hideBadge && (
            <span className="selection-badge text-caption tabular-nums" data-testid={`${idPrefix}-count`}>
              {selectionBadge(value.length, items.length)}
            </span>
          )}
          {toolbar}
        </div>
      )}

      {loading && <Skeleton rows={3} />}
      {!loading && (
        <div
          className="selection-scroll run-subject-scroll"
          ref={(el) => {
            boxRef.current = el;
            scrollRef?.(el);
          }}
          data-fill={scrollFill ? "true" : undefined}
          style={maxHeight ? { maxHeight: `${Math.round(maxHeight)}px` } : undefined}
          data-testid={scrollTestId ?? `${idPrefix}-list`}
          onScroll={windowed ? (e) => setScrollTop(e.currentTarget.scrollTop) : undefined}
          onKeyDown={onKeyDown}
          tabIndex={0}
          role={aria}
          aria-label={label}
          aria-multiselectable={mode !== "single"}
          aria-activedescendant={visible[focusIndex] ? `${listId}-${visible[focusIndex].id}` : undefined}
        >
          <table className="run-subject-table selection-table" role="presentation">
            {headers && (
              <thead>
                <tr>
                  <th scope="col" className="selection-check">
                    {mode !== "single" && (
                      <Checkbox
                        checked={allVisibleSelected ? true : selectedVisible > 0 ? "indeterminate" : false}
                        onCheckedChange={(on) =>
                          onChange(on ? selectAllVisible(value, visible, excluded) : selectNoneVisible(value, visible))
                        }
                        disabled={bulkTargets.length === 0}
                        aria-label={`Select all ${label.toLowerCase()}`}
                      />
                    )}
                  </th>
                  <th scope="col">{headers.label ?? ""}</th>
                  {extra.length > 0
                    ? extra.map((c) => (
                        <th key={c.id} scope="col" className={c.numeric ? "numeric" : undefined}>
                          {c.header}
                        </th>
                      ))
                    : headers.detail !== undefined && <th scope="col">{headers.detail}</th>}
                  {anyReason && <th scope="col">{headers.reason ?? "Why not"}</th>}
                </tr>
              </thead>
            )}
            <tbody>
              {windowed && start > 0 && (
                <tr className="selection-spacer" aria-hidden style={{ height: start * ROW_H }}>
                  <td colSpan={columnCount + 1} />
                </tr>
              )}
              {slice.map((item, i) => {
                const index = start + i;
                const checked = value.includes(item.id);
                return (
                  <tr
                    key={item.id}
                    id={`${listId}-${item.id}`}
                    role={aria === "grid" ? "row" : "option"}
                    aria-selected={checked}
                    /* The option carries its own value and its own name, so a spec (or a scene
                       pane) that holds the server's data can address a row without also knowing
                       which separator the label happens to print — the finding `roi-idiom.spec.ts`
                       calls defect 2b. */
                    data-option-value={item.id}
                    aria-label={typeof item.label === "string" ? item.label : undefined}
                    aria-disabled={item.disabled || undefined}
                    className={cn("selection-row", rowClassName, item.disabled && "selection-row-disabled")}
                    data-testid={`${idPrefix}-row-${item.id}`}
                    data-row-index={index}
                    data-selected={checked ? "true" : "false"}
                    data-focused={index === focusIndex ? "true" : undefined}
                    {...Object.fromEntries(
                      Object.entries(item.data ?? {})
                        .filter(([, v]) => v !== undefined)
                        .map(([k, v]) => [`data-${k}`, v]),
                    )}
                    onClick={(e) => {
                      // The checkbox has already handled its own click; without this guard the two
                      // handlers cancel each other out and the box becomes unclickable.
                      if ((e.target as HTMLElement).closest(".checkbox-root")) return;
                      setFocusIndex(index);
                      click(e, item.id);
                    }}
                  >
                    <td className="selection-check">
                      <Checkbox
                        checked={checked}
                        onCheckedChange={() => {
                          setFocusIndex(index);
                          toggleOne(item.id);
                        }}
                        disabled={item.disabled}
                        aria-label={typeof item.label === "string" ? item.label : item.id}
                      />
                    </td>
                    <td className="selection-label">
                      {item.swatch ? (
                        <span
                          className="selection-swatch"
                          style={{ background: item.swatch }}
                          aria-hidden
                          data-testid="selection-swatch"
                        />
                      ) : null}
                      {typeof item.label === "string" ? <span className="mono">{item.label}</span> : item.label}
                    </td>
                    {extra.length > 0
                      ? extra.map((c) => (
                          <td key={c.id} className={c.numeric ? "selection-detail numeric" : "selection-detail"}>
                            {c.cell(item)}
                          </td>
                        ))
                      : headers?.detail !== undefined && <td className="selection-detail">{item.detail}</td>}
                    {anyReason && (
                      <td>
                        {item.reason && (
                          <span className="selection-reason" data-testid={`${idPrefix}-reason-${item.id}`}>
                            {item.reason}
                          </span>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
              {windowed && end < visible.length && (
                <tr className="selection-spacer" aria-hidden style={{ height: (visible.length - end) * ROW_H }}>
                  <td colSpan={columnCount + 1} />
                </tr>
              )}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={columnCount + 1} className="field-help">
                    {items.length === 0 ? emptyMessage : `Nothing matches “${query.trim()}”.`}
                  </td>
                </tr>
              )}
              {/* Ground rows are drawn on an EMPTY list too: the empty state's whole job is to show
                  the shape of the list that is coming (DESIGN.md §4.4). */}
              {Array.from({ length: groundRows }, (_, i) => (
                <tr key={`filler-${i}`} className="run-table-filler" aria-hidden>
                  <td colSpan={columnCount + 1} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------- SelectionPicker */

export interface SelectionPickerProps extends Omit<SelectionListProps, "minRows" | "scrollRef" | "scrollTestId" | "scrollFill"> {
  /** Shown on the trigger when nothing is chosen. */
  placeholder?: string;
  /** Dialog title. Defaults to the `label`. */
  title?: string;
  description?: string;
  disabled?: boolean;
  triggerTestId?: string;
  /** Fired when the trigger is pressed — the pair editor uses it to move the active-slot cursor. */
  onOpen?: () => void;
}

/**
 * The same list, behind a summary button, for a field that has no room for a list: an ex bucket,
 * one slot of an electrode pair (`mode="single"`), an atlas's 150 regions. The trigger states the
 * selection in words — `F7, P7, +3 more` — so the closed control still answers "what did I pick?",
 * which a `MultiSelect`'s truncated chip row did not.
 */
export function SelectionPicker({
  placeholder = "Choose…",
  title,
  description,
  disabled,
  triggerTestId,
  onOpen,
  idPrefix = "selection",
  ...list
}: SelectionPickerProps) {
  const [open, setOpen] = useState(false);
  const count = list.value.length;
  const names = list.value.map((id) => {
    const item = list.items.find((i) => i.id === id);
    return item && typeof item.label === "string" ? item.label : id;
  });
  return (
    <>
      {/* `combobox` is the honest role for a trigger that holds the chosen value(s) and opens a
          listbox to change them — single or multiple. It is also the role the controls this
          replaces had (`ui/Select`, `ui/Combobox`'s `MultiSelect`), so every spec and every screen
          reader that knew how to work an electrode slot or a region picker still does. */}
      <Button
        variant="secondary"
        size="sm"
        className="selection-trigger"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => {
          onOpen?.();
          setOpen(true);
        }}
        data-testid={triggerTestId ?? `${idPrefix}-open`}
        data-count={count}
        title={count > 0 ? names.join(", ") : undefined}
      >
        <span className={cn("selection-trigger-text", count === 0 && "selection-trigger-empty")}>
          {selectionSummary(names, placeholder, 2, typeof list.label === "string" ? selectionNoun(list.label, count) : undefined)}
        </span>
      </Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={title ?? list.label}
        description={description}
        footer={
          <Button variant="primary" onClick={() => setOpen(false)} data-testid={`${idPrefix}-done`}>
            Done
          </Button>
        }
      >
        <SelectionList {...list} toggleOnRowClick={list.mode !== "single"} idPrefix={idPrefix} escClears={false} maxHeight={list.maxHeight ?? 320} />
      </Dialog>
    </>
  );
}

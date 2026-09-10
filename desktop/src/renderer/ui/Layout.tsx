import * as TabsPrimitive from "@radix-ui/react-tabs";
import { ChevronDown, ChevronLeft, ChevronRight, Maximize2, Minimize2, MoreHorizontal, PanelRightClose } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import { Button, IconButton } from "./Button";
import { Popover } from "./Overlay";
import { PageActivityContext, usePageActive } from "../app/pageActivity";
import {
  clampPaneWidth,
  paneLimitsForViewport,
  paneReducer,
  readPaneState,
  writePaneState,
  type PaneAction,
  type PaneLimits,
  type PaneMode,
  type PaneState,
  type PaneStorage,
} from "./paneState";
import { cn } from "./utils";
import "./pane.css";

/** The 4px-grid space steps that have a `--space-N` token (tokens.css §3) — the only gaps
 * `Stack`/`Cluster` accept, so a page can never reintroduce an arbitrary one-off px value. */
export type Space = 1 | 2 | 3 | 4 | 6 | 8 | 12;
export type Align = "start" | "center" | "end" | "stretch" | "baseline";

const ALIGN_CLASS: Record<Align, string> = {
  start: "items-start",
  center: "items-center",
  end: "items-end",
  stretch: "items-stretch",
  baseline: "items-baseline",
};

/**
 * A vertical flex column with a token gap — the most repeated inline style in the codebase
 * (`style={{ display: "flex", flexDirection: "column", gap: "var(--space-N)" }}`, 50+ call sites)
 * before this existed (ra_12 #28). `<Stack gap={3}>{children}</Stack>` replaces it exactly, and
 * because `gap` is one of the fixed `Space` steps there is no way to smuggle an arbitrary px value
 * back in through this primitive.
 */
export function Stack({ gap = 3, align, className, children }: { gap?: Space; align?: Align; className?: string; children: ReactNode }) {
  return <div className={cn("stack", `gap-${gap}`, align && ALIGN_CLASS[align], className)}>{children}</div>;
}

/**
 * A horizontal flex row with a token gap, wrapping by default — the second-most repeated inline
 * style (`display: "flex", gap: "var(--space-N)"`, optionally `alignItems`/`flexWrap`) before this
 * existed (ra_12 #28). Toolbars, chip rows, and inline label+control groups all used this same
 * shape by hand.
 */
export function Cluster({
  gap = 2,
  align = "center",
  wrap = true,
  justify,
  className,
  children,
}: {
  gap?: Space;
  align?: Align;
  /** Default true: most call sites this replaces had `flexWrap: "wrap"`. */
  wrap?: boolean;
  justify?: "start" | "end" | "center" | "between";
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "cluster",
        `gap-${gap}`,
        ALIGN_CLASS[align],
        !wrap && "cluster-nowrap",
        justify === "between" && "justify-between",
        justify === "end" && "justify-end",
        justify === "center" && "justify-center",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * One compact "Label value" pair for ad-hoc inline stats (e.g. a card's "8 CPUs" fragment) — for a
 * *list* of pairs use `DefinitionList` (`Feedback.tsx`) instead, and for *editable* rows use
 * `KeyValueTable`. This is the third recurring shape ra_12 #28 named: a label in `--ink-2` next to
 * a value in `--ink`, laid out with `Cluster` under the hood so it never needs its own inline gap.
 */
export function KeyValue({ label, value, mono }: { label: ReactNode; value: ReactNode; mono?: boolean }) {
  return (
    <Cluster gap={1} wrap={false} className="kv-item">
      <span className="kv-item-label text-caption">{label}</span>
      <span className={cn("kv-item-value", mono && "mono")}>{value}</span>
    </Cluster>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("card", className)}>{children}</div>;
}

export function CardHeader({ title, actions }: { title: ReactNode; actions?: ReactNode }) {
  return (
    <div className="card-header">
      <span className="card-title">{title}</span>
      {actions}
    </div>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("card-body", className)}>{children}</div>;
}

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
}

export function Tabs({
  items,
  value,
  onValueChange,
  defaultValue,
}: {
  items: TabItem[];
  value?: string;
  onValueChange?: (id: string) => void;
  defaultValue?: string;
}) {
  return (
    <TabsPrimitive.Root value={value} onValueChange={onValueChange} defaultValue={defaultValue ?? items[0]?.id}>
      <TabsPrimitive.List className="tabs-list">
        {items.map((item) => (
          <TabsPrimitive.Trigger key={item.id} value={item.id} className="tabs-trigger">
            {item.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {items.map((item) => (
        <TabsPrimitive.Content key={item.id} value={item.id} className="tabs-content">
          {item.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}

/**
 * The run shape's fill rule (fix lane FXU1, program U1): a run page's collapsible sections
 * **auto-expand to fill the work pane** when their expanded heights fit, and only what would
 * overflow stays collapsed. The controller that measures lives in
 * `pages/_shared/run/RunWork.tsx`; this context is the seam it drives `FormSection` through, so
 * `FormSection` still owns its own open state and a page outside the run shape is untouched.
 *
 * Precedence inside a section, highest first: the user's own toggle → the density rule
 * (`changed`/`error` force the section open, so a non-default value is never out of sight) → the
 * controller's decision → `defaultOpen`.
 *
 * **The user's toggle outlives this component** (lane N2). A page unmounts on every navigation
 * (`app/App.tsx` renders one route element), so a decision kept only in this component's own state
 * was lost the moment the user visited another page and the controller re-derived a different
 * answer on the way back — the defect the maintainer reported as "jumping between tabs resets
 * them". `userOpenFor` is where the controller hands that decision back, so the top of the
 * precedence list above is the top of it across mounts too, not just within one.
 */
export interface FormSectionFill {
  /**
   * The user's own decision for this section, remembered for the session by the controller;
   * `undefined` = they have never touched it. Outranks the density pin and `openFor`.
   */
  userOpenFor(id: string): boolean | undefined;
  /** `undefined` = the controller has no opinion about this section yet. */
  openFor(id: string): boolean | undefined;
  /** A section reports its identity + whether the density rule pins it open. */
  register(id: string, pinned: boolean): void;
  /** The user toggled it by hand: the controller must stop deciding for this one, and remember it. */
  onUserToggle(id: string, open: boolean): void;
}
export const FormSectionFillContext = createContext<FormSectionFill | null>(null);

export interface FormSectionProps {
  title: string;
  helpSlot?: ReactNode;
  children: ReactNode;
  /** Rendered behind a nested "Advanced" disclosure inside this section. */
  advanced?: ReactNode;
  /**
   * The section's current values, right-aligned in the header: "ellipse · 8×8 mm · gel 4 mm".
   * This is what makes collapsing safe rather than lossy — a collapsed section still states what
   * it holds. Supply it whenever `collapsible` is set.
   */
  summary?: ReactNode;
  /** Any child differs from its default: the header takes an accent dot. */
  changed?: boolean;
  /** Any child has a validation error: the header takes a `--danger` dot, visible while collapsed. */
  error?: boolean;
  /** Adds a disclosure chevron to the header. */
  collapsible?: boolean;
  /** Only meaningful with `collapsible`. Defaults to open. */
  defaultOpen?: boolean;
  /**
   * How many fields inside `advanced` are non-default. Greater than zero force-opens the
   * disclosure and badges it "Advanced · N changed": a parameter can never sit out of sight doing
   * something to the science. The user may still collapse it by hand afterwards.
   */
  advancedChangedCount?: number;
  /** Wired to a "Reset section" item in the header's ⋯ menu. Omit and no menu is rendered. */
  onReset?: () => void;
  /** Extra items for the header's ⋯ menu (rendered under "Reset section"). */
  menu?: ReactNode;
  /** Stable id for the fill controller. Defaults to `title`, which is unique within a page. */
  fillId?: string;
  /** 1 = never collapsed by the fill controller; 2 = the deepest, collapsed first on overflow. */
  tier?: 1 | 2;
}

/**
 * `FormSection` v2 — a flush `<section>`, not a card (DESIGN.md §3): an 11px uppercase eyebrow, a
 * 1px rule, and the body flush to the pane edge. No border box, no shadow, no gap between
 * sections. Chrome per section: 41px, down from 94px.
 *
 * `Card` is still the right primitive for a Workbench card or a result summary — a genuinely
 * separate object on the page. It is the wrong one for a form group.
 */
export function FormSection({
  title,
  helpSlot,
  children,
  advanced,
  summary,
  changed,
  error,
  collapsible,
  defaultOpen = true,
  advancedChangedCount = 0,
  onReset,
  menu,
  fillId,
  tier = 2,
}: FormSectionProps) {
  const id = fillId ?? title;
  const fill = useContext(FormSectionFillContext);
  // The density rule: a section holding a non-default value or an error is never collapsed by the
  // fill controller, because a parameter must not sit out of sight doing something to the science.
  const pinnedOpen = !!changed || !!error;
  useEffect(() => {
    fill?.register(id, pinnedOpen);
  }, [fill, id, pinnedOpen]);
  // `null` = the user has not toggled this section *in this mount*; the controller's memory of an
  // earlier mount (N2) is consulted next, and only then the density rule and the controller.
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const decided = userOpen ?? fill?.userOpenFor(id) ?? null;
  const open = decided ?? (pinnedOpen ? true : (fill?.openFor(id) ?? defaultOpen));
  const setOpen = (next: boolean | ((prev: boolean) => boolean)) => {
    const value = typeof next === "function" ? next(open) : next;
    setUserOpen(value);
    fill?.onUserToggle(id, value);
  };
  // `null` = the user has not decided; the changed-count decides instead. Once they toggle it by
  // hand their choice wins, so force-open is a starting state, not a cage.
  const [advancedOverride, setAdvancedOverride] = useState<boolean | null>(null);
  const advancedForced = advancedChangedCount > 0;
  const advancedOpen = advancedOverride ?? advancedForced;
  const bodyShown = !collapsible || open;

  const header = (
    <>
      {collapsible && (
        <span className="form-section-chevron" aria-hidden>
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
      )}
      <span className="form-section-title text-eyebrow">{title}</span>
      {!bodyShown && summary !== undefined && <span className="form-section-summary">{summary}</span>}
      <span className="form-section-marks">
        {changed && <span className="form-section-mark-changed" title="Contains a non-default value" />}
        {error && <span className="form-section-mark-error" title="Contains an error" />}
      </span>
    </>
  );

  // `data-fill-user` states whose decision the current open/closed state is — "open"/"closed" when
  // the USER set it (this mount or an earlier one this session, N2), absent while it is still the
  // controller's or the default's. The same contract `RunPaneTabs` already publishes as
  // `data-chosen`, and the only way a spec (or a person debugging) can tell a section that happens
  // to be open from one that will *stay* open.
  return (
    <section
      className="form-section"
      data-fill-section={id}
      data-fill-tier={tier}
      data-fill-collapsible={collapsible ? "" : undefined}
      data-fill-user={decided === null ? undefined : decided ? "open" : "closed"}
    >
      <div className="form-section-header">
        {collapsible ? (
          <button type="button" className="form-section-header-trigger" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            {header}
          </button>
        ) : (
          <span className="form-section-header-trigger">{header}</span>
        )}
        {helpSlot}
        {(onReset || menu) && (
          <span className="form-section-menu">
            <Popover
              trigger={
                <IconButton aria-label={`${title} section menu`} size="sm" icon={<MoreHorizontal size={14} />} />
              }
            >
              <Stack gap={1}>
                {onReset && (
                  <Button variant="ghost" size="sm" onClick={onReset}>
                    Reset section
                  </Button>
                )}
                {menu}
              </Stack>
            </Popover>
          </span>
        )}
      </div>
      {bodyShown && (
        <div className="form-section-body">
          <div className="form-grid">{children}</div>
          {advanced && (
            <div className="form-section-advanced">
              <button
                type="button"
                className="form-section-advanced-toggle"
                onClick={() => setAdvancedOverride(!advancedOpen)}
                aria-expanded={advancedOpen}
              >
                {advancedOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                Advanced
                {advancedForced && <span className="form-section-advanced-badge">· {advancedChangedCount} changed</span>}
              </button>
              {advancedOpen && (
                <div className="form-grid" style={{ marginTop: "var(--space-2)" }}>
                  {advanced}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export function PageHeader({
  title,
  purpose,
  breadcrumb,
  actions,
}: {
  title: string;
  purpose?: string;
  breadcrumb?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        {breadcrumb && <div className="page-header-breadcrumb">{breadcrumb}</div>}
        <h1 className="text-page-title">{title}</h1>
        {purpose && <p className="page-header-purpose text-body">{purpose}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ the right-pane controller (U13)

/**
 * One right pane, three gestures — **stretch, collapse, expand** (program U13; the maintainer:
 * *"we must allow user to stretch/collapse/expand the right hand side"*, said about Jobs and about
 * Results). One controller drives all of them so the two pages cannot drift apart:
 *
 * - `PaneSeparator` is the divider: pointer drag, arrow keys, `role="separator"` with a live
 *   `aria-valuenow`, and — once collapsed — the 16 px rail that brings the pane back.
 * - `PaneHeaderControls` is the pair of buttons a page drops into its own pane header: collapse
 *   (chevron) and expand/restore.
 * - `⌘⇧I` collapses and restores; `Esc` leaves the expanded state.
 *
 * The width is persisted per page id (`ui/paneState.ts`), which is DESIGN.md §2.1's "persisted per
 * machine per page kind" made executable. `width` stays `null` until the user actually drags, so
 * the design's responsive default (360/400 px, or `clamp(380px, 40%, 560px)`) keeps applying to a
 * pane nobody has resized.
 */
export interface PaneController {
  pageId: string;
  /** The pane's noun, used in every accessible name: "Collapse the preview pane". */
  name: string;
  /** `null` = no explicit width; the stylesheet's own default applies. */
  width: number | null;
  /** The pane's measured width right now — what `aria-valuenow` reports and a drag starts from. */
  measured: number;
  mode: PaneMode;
  collapsed: boolean;
  expanded: boolean;
  limits: PaneLimits;
  dispatch: (action: PaneAction) => void;
  toggleCollapse: () => void;
  toggleExpand: () => void;
  restore: () => void;
  /** Ref callback for the pane element, so the controller can measure what CSS actually produced. */
  attach: (el: HTMLElement | null) => void;
}

/** `undefined` until probed; `null` once probed and found unusable. Module-level rather than a ref
 * so nothing reads a ref during render (the React Compiler's rule, and the reason it is a rule:
 * a value read during render must be one React can re-render on). */
let probedStorage: PaneStorage | null | undefined;
function browserStorage(): PaneStorage | undefined {
  if (probedStorage === undefined) {
    try {
      probedStorage = typeof window === "undefined" ? null : window.localStorage;
    } catch {
      probedStorage = null;
    }
  }
  return probedStorage ?? undefined;
}

export interface PaneControllerOptions {
  /** Storage key scope. Use the page's registry id (`"jobs"`, `"results"`). */
  pageId: string;
  name: string;
  /** Floor. Defaults to 36 vw; Jobs and Results pass 320 to keep the narrower columns §2.1 pins. */
  minWidth?: number;
  /** Stretch ceiling. Defaults to 70 vw. */
  maxWidth?: number;
  /**
   * `false` while the page has nothing to put in the pane. The keyboard chords go quiet (a page
   * with no pane must not swallow `⌘⇧I`) and the mode reads `normal`, so U1's "a pane with nothing
   * selected is not rendered" is never confused with "the user collapsed it".
   */
  enabled?: boolean;
}

/**
 * The window's width, tracked. The pane's limits are fractions of the window (DESIGN.md §2.1), so
 * they have to answer a resize — a ceiling computed once at mount is a ceiling the user's next
 * window resize invalidates.
 */
function useViewportWidth(): number {
  const [width, setWidth] = useState<number>(() => (typeof window === "undefined" ? 1280 : window.innerWidth));
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onResize = () => setWidth(window.innerWidth);
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return width;
}

export function usePaneController({
  pageId,
  name,
  minWidth,
  maxWidth,
  enabled = true,
}: PaneControllerOptions): PaneController {
  const active = usePageActive();
  const viewport = useViewportWidth();
  const limits = useMemo<PaneLimits>(() => {
    const vw = paneLimitsForViewport(viewport, minWidth);
    return { min: vw.min, max: maxWidth ?? vw.max };
  }, [viewport, minWidth, maxWidth]);
  const [state, dispatch] = useReducer(
    (current: PaneState, action: PaneAction) => paneReducer(current, action, limits),
    undefined,
    () => readPaneState(pageId, limits, browserStorage()),
  );
  // Persisting in an effect rather than inside the dispatcher keeps the reducer pure and keeps this
  // hook free of a "current state" ref: the write follows the state React actually committed.
  useEffect(() => {
    writePaneState(pageId, state, browserStorage());
  }, [pageId, state]);

  // What CSS actually produced. A pane sized by the stylesheet (360/400, or the preview's 40%) has
  // no number of its own until the user drags, so the drag and `aria-valuenow` measure the element
  // instead of guessing — the same reason the v2 `InspectorHandle` took a `currentWidth()` thunk.
  const [measured, setMeasured] = useState<number>(() => clampPaneWidth(state.width ?? limits.min, limits));
  // A ref, written only from the ref callback and the unmount effect — never read during render,
  // which is the rule the React Compiler enforces and the reason the state above is not one.
  const observerRef = useRef<ResizeObserver | null>(null);
  const attach = useCallback((el: HTMLElement | null) => {
    observerRef.current?.disconnect();
    observerRef.current = null;
    // React 18 has no ref-callback cleanup, so the disconnect happens on the NEXT attach (React
    // calls the callback with `null` when the pane unmounts) and on unmount, below.
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      // BORDER box, not `contentRect` — the same box `getBoundingClientRect()` below reports, and
      // the same box `width: var(--right-pane-w)` sets under the app's global
      // `box-sizing: border-box`. Mixing the two was a real render loop, not a rounding nit: lane
      // SCC measured 720 renders in 2s on the Optimizer, because `.page-layout-run
      // .page-layout-panel` has `padding-left: var(--space-3)` so the two writes disagreed by
      // 12px and each one re-rendered, re-attached and re-measured. What it actually broke was the
      // page's 400ms plan debounce — `POST /api/plan/flex` was never sent and the digest stayed on
      // "Resolving the plan…" for ever. `borderBoxSize` is unsupported in some older engines and
      // in jsdom, hence the `contentRect` + padding fallback.
      let w = entry?.borderBoxSize?.[0]?.inlineSize;
      if (w === undefined && entry) {
        const cs = typeof getComputedStyle === "function" ? getComputedStyle(entry.target as Element) : null;
        // `parseFloat`, not `parseFloat` alone: a computed border-width can come back as the
        // KEYWORD `medium` (jsdom returns it for an element with no border), and one NaN makes the
        // whole sum NaN, which the `rounded > 0` guard below then drops — the fallback silently
        // measuring nothing in the one environment it exists for. Measured: `borderLeftWidth` =
        // "medium" on `.page-layout-panel` in jsdom, so `measured` stayed at the 320px minimum
        // instead of the pane's 400px.
        const px = (value: string | undefined): number => {
          const n = parseFloat(value ?? "");
          return Number.isFinite(n) ? n : 0;
        };
        const pad = cs ? px(cs.paddingLeft) + px(cs.paddingRight) : 0;
        const border = cs ? px(cs.borderLeftWidth) + px(cs.borderRightWidth) : 0;
        w = entry.contentRect.width + pad + border;
      }
      const rounded = Math.round(w ?? 0);
      // Guarded so the observer cannot loop with its own state update during a drag.
      if (rounded > 0) setMeasured((prev) => (prev === rounded ? prev : rounded));
    });
    ro.observe(el);
    observerRef.current = ro;
    setMeasured((prev) => {
      const w = Math.round(el.getBoundingClientRect().width);
      return w > 0 && w !== prev ? w : prev;
    });
  }, []);
  useEffect(() => () => observerRef.current?.disconnect(), []);

  // `⌘⇧I` and `Esc` live with the pane they act on, not in `app/keyboard.ts` (DESIGN.md §6.5 — one
  // gesture, one meaning): a page whose pane is not on screen must not swallow either chord, and
  // Esc only fires while the pane is expanded so it never competes with a dialog's own Esc.
  const isExpanded = state.mode === "expanded";
  useEffect(() => {
    if (!enabled || !active) return;
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && !e.altKey && e.key.toLowerCase() === "i") {
        e.preventDefault();
        dispatch({ type: "toggleCollapse" });
      } else if (e.key === "Escape" && isExpanded) {
        e.preventDefault();
        dispatch({ type: "restore" });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active, enabled, isExpanded]);

  const mode: PaneMode = enabled ? state.mode : "normal";
  return {
    pageId,
    name,
    width: state.width,
    measured,
    mode,
    collapsed: mode === "collapsed",
    expanded: mode === "expanded",
    limits,
    dispatch,
    attach,
    toggleCollapse: useCallback(() => dispatch({ type: "toggleCollapse" }), [dispatch]),
    toggleExpand: useCallback(() => dispatch({ type: "toggleExpand" }), [dispatch]),
    restore: useCallback(() => dispatch({ type: "restore" }), [dispatch]),
  };
}

/** Arrow-key step, and the coarse step with Shift held. */
const PANE_STEP = 16;
const PANE_STEP_COARSE = 64;

/**
 * The divider between the work pane and the right pane, in whichever of its three states applies.
 *
 * Dragging LEFT widens the pane, so the pointer delta is subtracted (the same sign the v2
 * `InspectorHandle` used, and the opposite of {@link ResizablePanels}, whose handle sizes the pane
 * on its *left*). ArrowLeft widens, ArrowRight narrows, Home/End jump to the limits.
 */
export function PaneSeparator({ controller, className }: { controller: PaneController; className?: string }) {
  const { mode, measured, limits, name, dispatch, restore } = controller;
  if (mode === "expanded") return null;
  if (mode === "collapsed") {
    return (
      <button
        type="button"
        className={cn("page-layout-inspector-handle", "pane-separator", className)}
        data-pane-mode="collapsed"
        data-testid="pane-collapsed-rail"
        aria-label={`Show the ${name} pane`}
        title={`Show the ${name} pane (⌘⇧I)`}
        onClick={restore}
      >
        <ChevronLeft size={12} aria-hidden />
      </button>
    );
  }
  const resize = (width: number): void => dispatch({ type: "resize", width });
  return (
    <button
      type="button"
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize the ${name} pane`}
      aria-valuenow={measured}
      aria-valuemin={limits.min}
      aria-valuemax={limits.max}
      className={cn("page-layout-inspector-handle", "pane-separator", className)}
      data-pane-mode="normal"
      data-testid="inspector-handle"
      onPointerDown={(e) => {
        const startX = e.clientX;
        const startWidth = measured;
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        const onMove = (ev: PointerEvent): void => resize(startWidth - (ev.clientX - startX));
        const onUp = (): void => {
          window.removeEventListener("pointermove", onMove);
          window.removeEventListener("pointerup", onUp);
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
      }}
      onKeyDown={(e) => {
        const step = e.shiftKey ? PANE_STEP_COARSE : PANE_STEP;
        if (e.key === "ArrowLeft") resize(measured + step);
        else if (e.key === "ArrowRight") resize(measured - step);
        else if (e.key === "Home") resize(limits.max);
        else if (e.key === "End") resize(limits.min);
        else return;
        e.preventDefault();
      }}
    />
  );
}

/**
 * The two buttons a page puts at the right end of its own pane header: collapse, and
 * expand/restore. They live in the page's header rather than in a header this component renders,
 * because Results' preview header and Jobs' detail header are the pages' own 28 px rows.
 */
export function PaneHeaderControls({ controller }: { controller: PaneController }) {
  const { name, expanded, toggleCollapse, toggleExpand } = controller;
  return (
    <span className="pane-controls" data-testid="pane-controls">
      <IconButton
        size="sm"
        aria-label={expanded ? `Restore the ${name} pane` : `Expand the ${name} pane`}
        title={expanded ? `Restore the ${name} pane (Esc)` : `Expand the ${name} pane to the full width`}
        data-testid="pane-expand"
        icon={expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        onClick={toggleExpand}
      />
      <IconButton
        size="sm"
        aria-label={`Collapse the ${name} pane`}
        title={`Collapse the ${name} pane (⌘⇧I)`}
        data-testid="pane-collapse"
        icon={expanded ? <ChevronRight size={13} /> : <PanelRightClose size={13} />}
        onClick={toggleCollapse}
      />
    </span>
  );
}

/**
 * `PageLayout` v3 (DESIGN.md §2, §4.1; program U1).
 *
 * Three shapes and one right pane. The v2 names still resolve — `standard` → `run`, `full-bleed` →
 * `bleed`, `inspector`/`contextPanel` → `rightPane` — so no page needs an edit to keep working.
 * What is gone is the 880 px work-pane cap and the "Plan block, then page blocks" inspector: the
 * work pane takes every pixel the right pane does not, and the right pane holds exactly one thing.
 */
export type PageLayoutVariant = "run" | "browse" | "bleed" | "standard" | "full-bleed";
/** What the right pane is for. `none` is the assertion that a page has decided not to have one. */
export type RightPaneKind = "run" | "preview" | "none";

/** v2 spellings resolve to the three v3 shapes; nothing else is accepted. */
const VARIANT: Record<PageLayoutVariant, "run" | "browse" | "bleed"> = {
  run: "run",
  browse: "browse",
  bleed: "bleed",
  standard: "run",
  "full-bleed": "bleed",
};

export interface PageLayoutProps {
  children: ReactNode;
  /**
   * `run` — work pane + `RunPanel` right pane + sticky action bar (Pre-processing, Simulator,
   * Optimizer, Analyzer). `browse` — an internally split work pane with an optional preview pane,
   * panes flush against 1 px rules (Results, Subjects, Jobs). `bleed` — no padding, no max width;
   * the page fills the shell's content box (Viewer).
   */
  variant?: PageLayoutVariant;
  /**
   * The right-hand pane. **Not rendered when undefined or null** — U1 in its enforceable form: a
   * pane whose model is empty is not a pane, and the work pane takes its width. `paneWidths().right`
   * reading `0` is how a spec asserts that rather than describes it.
   */
  rightPane?: ReactNode;
  /** Defaults to `run` on the run shape and `preview` on the browse shape. */
  rightPaneKind?: RightPaneKind;
  /**
   * Width in px. Default 360 below 1440 and 400 at or above it (a CSS breakpoint, not a prop), and
   * `clamp(380px, 40%, 560px)` for a `preview` pane, whose content is a document rather than a
   * fixed column of controls.
   */
  rightPaneWidth?: number;
  /** Adds the drag handle and reports the new width; the page owns the number and persists it. */
  onRightPaneWidthChange?: (width: number) => void;
  rightPaneMinWidth?: number;
  rightPaneMaxWidth?: number;
  /** ⌘⇧I collapses and restores the pane. Defaults to true for a `run` pane. */
  rightPaneCollapsible?: boolean;
  rightPaneDefaultCollapsed?: boolean;
  /**
   * The U13 controller from {@link usePaneController}. When given it owns the pane's width and its
   * collapsed/expanded mode, this component's own `⌘⇧I`/`draggedWidth` state stands down, and the
   * divider becomes a {@link PaneSeparator} (drag + arrow keys + the collapsed rail). Pass it
   * together with a {@link PaneHeaderControls} inside the pane's own header.
   */
  paneController?: PaneController;
  /** Sticky 44px bar at the bottom of the work pane. Build it with `ActionBar`. */
  actionBar?: ReactNode;
  /**
   * A page header is off by default — the nav rail already says which page this is, and a title
   * plus a purpose sentence costs 86px of every screen. Settings and Help opt back in.
   */
  showHeader?: boolean;
  title?: string;
  purpose?: string;
  headerActions?: ReactNode;
  /**
   * v1 escape hatch: a fully-built header node. When given it always renders, `showHeader` or
   * not — an explicit node is an explicit decision, and every page written against v1 passes one.
   */
  header?: ReactNode;
  /** v2 name for `rightPane`. */
  inspector?: ReactNode;
  /** v1 name for `rightPane`. */
  contextPanel?: ReactNode;
  /** Splits the work pane so the pane can resize (v2 spelling of `onRightPaneWidthChange`). */
  resizableInspector?: boolean;
  /** v2 name for `rightPaneWidth`. Defaults to 300 when it is the prop the page passes. */
  inspectorWidth?: number;
  /** v2 name for `onRightPaneWidthChange`. */
  onInspectorResize?: (width: number) => void;
  inspectorMinWidth?: number;
  inspectorMaxWidth?: number;
  className?: string;
}

/**
 * Work pane + optional right pane + optional sticky action bar.
 *
 * The DOM contract is `data-testid="page-work"` and `data-testid="page-right-pane"`, because that
 * is what `tests/e2e/_metrics.ts` measures (DESIGN.md §12.1). Classes are styling; the testids are
 * the layout's public statement of what it built, and the metric is only as honest as they are.
 */
export function PageLayout({
  children,
  variant = "run",
  rightPane,
  rightPaneKind,
  rightPaneWidth,
  onRightPaneWidthChange,
  rightPaneMinWidth,
  rightPaneMaxWidth,
  rightPaneCollapsible,
  rightPaneDefaultCollapsed = false,
  paneController,
  actionBar,
  showHeader,
  title,
  purpose,
  headerActions,
  header,
  inspector,
  contextPanel,
  resizableInspector,
  inspectorWidth,
  onInspectorResize,
  inspectorMinWidth,
  inspectorMaxWidth,
  className,
}: PageLayoutProps) {
  const active = usePageActive();
  const shape = VARIANT[variant];
  const panel = rightPane ?? inspector ?? contextPanel;
  const kind: RightPaneKind = rightPaneKind ?? (shape === "browse" ? "preview" : "run");
  const collapsible = rightPaneCollapsible ?? kind === "run";
  const [collapsed, setCollapsed] = useState(rightPaneDefaultCollapsed);

  // ⌘⇧I lives here, not in `app/keyboard.ts`: the pane it toggles is this component's state, and a
  // page with no right pane must not swallow the chord (DESIGN.md §6.5 — one gesture, one meaning).
  // A `paneController` owns the chord instead — two listeners would toggle each other's state.
  useEffect(() => {
    if (!active || !panel || !collapsible || paneController) return;
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && !e.altKey && e.key.toLowerCase() === "i") {
        e.preventDefault();
        setCollapsed((c) => !c);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active, panel, collapsible, paneController]);

  const controlledCollapse = paneController ? paneController.collapsed : collapsible && collapsed;
  const expanded = !!paneController?.expanded && !!panel;
  const paneVisible = !!panel && !controlledCollapse;
  const paneRef = useRef<HTMLElement | null>(null);
  // A STABLE ref callback. React 18 calls an inline ref callback with `null` and then with the
  // element on every single render, so an inline one here made `attach` disconnect and rebuild the
  // pane's ResizeObserver on every commit — half of lane SCC's render loop (the other half is the
  // box mismatch fixed in `usePaneController`). `paneController.attach` is itself `useCallback([])`,
  // so this identity changes only when the page swaps controllers.
  const controllerAttach = paneController?.attach;
  const attachPane = useCallback(
    (el: HTMLElement | null) => {
      paneRef.current = el;
      controllerAttach?.(el);
    },
    [controllerAttach],
  );
  // The drag is the shell's; the *persistence* is the page's (§2.1 — "persisted per machine per
  // page kind"), which is why a page that wants to remember the width passes the callback and a
  // page that does not still gets a resizable pane.
  const [draggedWidth, setDraggedWidth] = useState<number | null>(null);
  const headerNode = header ?? (showHeader && title ? <PageHeader title={title} purpose={purpose} actions={headerActions} /> : null);
  const onResize = onRightPaneWidthChange ?? onInspectorResize;
  // `inspectorWidth` keeps its own 300px default: a v2 page that passes it asked for that panel.
  // A controller's `null` width means "nobody has dragged this pane yet", so the stylesheet's own
  // responsive default still applies — the controller does not freeze 490 px into local storage
  // just because a page mounted at 1280.
  const width = paneController ? (paneController.width ?? undefined) : (rightPaneWidth ?? inspectorWidth ?? draggedWidth ?? undefined);
  // THE defect the maintainer hit: Pre-processing and Source pass no `paneController`, so their
  // divider is the legacy `InspectorHandle` below — and its ceiling was a flat 560 px, *narrower*
  // than the run pane's own 36 vw default on a 2000 px screen. Dragging the pane wider therefore
  // snapped it NARROWER and looked like "the pane cannot go past its default". Both paths now read
  // the same window-relative limits (DESIGN.md §2.1).
  const viewport = useViewportWidth();
  const viewportLimits = paneLimitsForViewport(viewport, kind === "preview" ? 320 : undefined);
  const minWidth = rightPaneMinWidth ?? inspectorMinWidth ?? viewportLimits.min;
  const maxWidth = rightPaneMaxWidth ?? inspectorMaxWidth ?? viewportLimits.max;

  const main = (
    <div
      className="page-layout-main"
      data-testid="page-work"
      hidden={expanded}
      aria-hidden={expanded ? true : undefined}
      {...(expanded ? { inert: "" } : {})}
    >
      <PageActivityContext.Provider value={active && !expanded}>
        <div className="page-layout-main-scroll" data-page-work-scroll>
          {children}
        </div>
        {actionBar}
      </PageActivityContext.Provider>
    </div>
  );

  // CSS variables rather than a `style.width` on the pane: the <1099px stacking rule and the
  // 1440px step both override `width` on `.page-layout-panel` without having to know a page
  // passed a number, and `--inspector-w` stays defined for the v2 page CSS that reads it.
  const vars =
    width === undefined
      ? undefined
      : ({ "--right-pane-w": `${Math.round(width)}px`, "--inspector-w": `${Math.round(width)}px` } as CSSProperties);

  const pane = panel && (
    <aside
      ref={attachPane}
      className="page-layout-panel"
      data-testid="page-right-pane"
      data-pane-kind={kind}
      data-pane-mode={paneController?.mode}
      data-pane-width={expanded ? "expanded" : width === undefined ? undefined : "fixed"}
      hidden={controlledCollapse}
      aria-hidden={controlledCollapse ? true : undefined}
      {...(controlledCollapse ? { inert: "" } : {})}
    >
      <PageActivityContext.Provider value={active && paneVisible}>{panel}</PageActivityContext.Provider>
    </aside>
  );

  // The 6px handle is part of §2.1's arithmetic at 1280 (666 work + 6 handle + 360 panel = the
  // 1032px the content box leaves), so a run pane always has one — a page does not have to pass a
  // callback to make its pane resizable, it passes one to make the width *stick*. A preview pane
  // is a percentage of the window and only gets a handle if its page asked for one.
  // With a controller the divider is the U13 `PaneSeparator`, which also renders the 16px rail
  // that brings a collapsed pane back — so it is rendered whenever the page *has* a pane model,
  // not only when the pane itself is on screen.
  const handle = paneController ? (
    panel && !expanded && <PaneSeparator controller={paneController} />
  ) : (
    paneVisible && (kind === "run" || onResize) && !resizableInspector && (
    <InspectorHandle
      currentWidth={() => paneRef.current?.getBoundingClientRect().width ?? width ?? 360}
      min={minWidth}
      max={maxWidth}
      onResize={(w) => {
        setDraggedWidth(w);
        onResize?.(w);
      }}
    />
    )
  );

  return (
    <div
      className={cn(
        "page-layout",
        `page-layout-${shape}`,
        // The v2 class name survives so `ui/components.css` and `viewer-page.css` keep matching.
        shape === "bleed" && "page-layout-full-bleed",
        className,
      )}
      data-variant={shape}
      style={vars}
    >
      {headerNode}
      <div className="page-layout-body" data-pane-mode={paneController?.mode}>
        {resizableInspector ? (
          <ResizablePanels
            left={main}
            right={pane}
            leftHidden={expanded}
            rightHidden={!paneVisible}
            defaultLeftWidth={880}
            minLeftWidth={480}
            maxLeftWidth={1400}
          />
        ) : (
          <>
            {/* Hiding removes geometry and focus without destroying drafts, scroll or the scene's
                browsing context. Inactive child effects pause; the page controller still restores. */}
            {main}
            {handle}
            {pane}
          </>
        )}
      </div>
    </div>
  );
}

/**
 * The 6px grab strip between the work pane and the inspector.
 *
 * Dragging LEFT widens the inspector, so the delta is subtracted — the opposite sign to
 * {@link ResizablePanels}, whose handle sizes the pane on its left. Keyboard mirrors the pointer:
 * ArrowLeft widens, ArrowRight narrows, 16px a step.
 */
function InspectorHandle({
  currentWidth,
  min,
  max,
  onResize,
}: {
  /** Read at the start of a gesture, so a pane sized by CSS (the 360/400 default, or the preview
   *  percentage) drags from where it actually is rather than from a guessed number. */
  currentWidth: () => number;
  min: number;
  max: number;
  onResize: (width: number) => void;
}) {
  const clamp = (w: number): number => Math.min(max, Math.max(min, w));
  return (
    <button
      type="button"
      className="page-layout-inspector-handle"
      data-testid="inspector-handle"
      aria-label="Resize inspector"
      aria-orientation="vertical"
      role="separator"
      onPointerDown={(e) => {
        const startX = e.clientX;
        const startWidth = currentWidth();
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        const onMove = (ev: PointerEvent): void => onResize(clamp(startWidth - (ev.clientX - startX)));
        const onUp = (): void => {
          window.removeEventListener("pointermove", onMove);
          window.removeEventListener("pointerup", onUp);
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") onResize(clamp(currentWidth() + 16));
        if (e.key === "ArrowRight") onResize(clamp(currentWidth() - 16));
      }}
    />
  );
}

/** Two panes with a draggable divider. Basic keyboard support via arrow keys on the handle. */
export function ResizablePanels({
  left,
  right,
  leftHidden = false,
  rightHidden = false,
  defaultLeftWidth = 320,
  minLeftWidth = 200,
  maxLeftWidth = 560,
}: {
  left: ReactNode;
  right: ReactNode;
  leftHidden?: boolean;
  rightHidden?: boolean;
  defaultLeftWidth?: number;
  minLeftWidth?: number;
  maxLeftWidth?: number;
}) {
  const [width, setWidth] = useState(defaultLeftWidth);
  const dragging = useRef(false);

  function clamp(w: number) {
    return Math.min(maxLeftWidth, Math.max(minLeftWidth, w));
  }

  function onPointerDown(e: ReactPointerEvent) {
    dragging.current = true;
    const startX = e.clientX;
    const startWidth = width;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    function onMove(ev: PointerEvent) {
      if (!dragging.current) return;
      setWidth(clamp(startWidth + (ev.clientX - startX)));
    }
    function onUp() {
      dragging.current = false;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  return (
    <div className="resizable-panels">
      <div
        className="resizable-panel"
        hidden={leftHidden}
        aria-hidden={leftHidden ? true : undefined}
        {...(leftHidden ? { inert: "" } : {})}
        style={rightHidden ? { flex: 1 } : { width }}
      >
        {left}
      </div>
      <button
        type="button"
        className="resizable-handle"
        hidden={leftHidden || rightHidden}
        aria-label="Resize panel"
        aria-orientation="vertical"
        role="separator"
        tabIndex={0}
        onPointerDown={onPointerDown}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setWidth((w) => clamp(w - 16));
          if (e.key === "ArrowRight") setWidth((w) => clamp(w + 16));
        }}
      />
      <div
        className="resizable-panel"
        hidden={rightHidden}
        aria-hidden={rightHidden ? true : undefined}
        {...(rightHidden ? { inert: "" } : {})}
        style={{ flex: 1 }}
      >
        {right}
      </div>
    </div>
  );
}

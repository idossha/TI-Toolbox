import { useCallback, useEffect, useState, type ReactElement } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { ChevronDown, ChevronRight, Puzzle } from "lucide-react";
import { pageById, pagePath, useNavSections, type ResolvedPage } from "./registry";
import { isMac } from "./keyboard";
import { isProjectHome } from "../env";
import { Tooltip } from "../ui/Overlay";
import { PendingProposalsBadge } from "./proposals/PendingProposalsBadge";
import { AppVersionLabel } from "./appUpdate";

/**
 * The width at which the rail carries labels — the same literal as `shell.css`.
 *
 * The program's Q1: U7 wanted labels at ≥ 1280, but a 216px rail at 1280 leaves a 1064px content
 * box. Rather than one page forcing the icon rail and every other page paying 160px for a label it
 * did not need, the rail is **icons below 1440 and labelled at or above it**, so no page needs a
 * special case. (The figure was set for the retired in-app viewer embed, which needed a ≥ 1200px
 * content box.)
 */
export const LABEL_RAIL_QUERY = "(min-width: 1440px)";

/**
 * True while the rail is the icon rail. Tooltips exist for that state only — a tooltip repeating
 * a label that is already on screen is noise on every hover of every row.
 *
 * Two independent listeners, not one (found while wiring the since-retired Viewer embed, DESIGN.md
 * §9 Q1): a resize during a busy `window.addEventListener("message", …)` stream could leave
 * `matchMedia`'s own `"change"` event un-fired — or fired but not landing as a state update — often
 * enough to matter, a scheduling interaction between Electron's window resize and the stream rather
 * than anything wrong with the query itself.
 * `window`'s own `"resize"` event is dispatched through a different Chromium code path than a media
 * query's `"change"`, so the same race dropping one is very unlikely to drop both; both handlers
 * just re-read `mql.matches` fresh, so there is one source of truth and no risk of the two
 * disagreeing with each other.
 */
function useLabelledRail(): boolean {
  const [labelled, setLabelled] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.(LABEL_RAIL_QUERY).matches === true,
  );
  useEffect(() => {
    const mql = window.matchMedia?.(LABEL_RAIL_QUERY);
    if (!mql) return;
    const read = () => setLabelled(mql.matches);
    read();
    mql.addEventListener("change", read);
    window.addEventListener("resize", read);
    return () => {
      mql.removeEventListener("change", read);
      window.removeEventListener("resize", read);
    };
  }, []);
  return labelled;
}

/**
 * Which groups the user has collapsed, remembered per browser.
 *
 * A navigation convenience, so `localStorage` is the right home and a throw is not worth a state:
 * a private window, cleared site data or a browser that blocks storage just means every group
 * starts expanded, which is the default anyway.
 */
const COLLAPSED_KEY = "tit.nav.collapsed";

function readCollapsed(): string[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(COLLAPSED_KEY) ?? "[]") as unknown;
    return Array.isArray(raw) ? raw.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function writeCollapsed(ids: string[]): void {
  try {
    window.localStorage.setItem(COLLAPSED_KEY, JSON.stringify(ids));
  } catch {
    /* storage unavailable — the rail still works, it just forgets */
  }
}

/** `aria-keyshortcuts` wants key names, not glyphs. */
function ariaShortcut(shortcut: string | undefined): string | undefined {
  if (!shortcut) return undefined;
  return `${isMac ? "Meta" : "Control"}+${shortcut}`;
}

/** Presentation-only grouping: extension routes and retained page ownership stay unchanged. */
function ExtensionsNav({
  pages,
  icons,
  collapsed,
  onToggle,
  activePageId,
}: {
  pages: ResolvedPage[];
  icons: boolean;
  collapsed: boolean;
  onToggle: () => void;
  activePageId: string;
}) {
  if (pages.length === 0) return null;
  const containsActive = pages.some((page) => page.id === activePageId);
  const heading = (
    <button
      type="button"
      className="nav-item"
      aria-label="Extensions"
      aria-expanded={!collapsed}
      aria-controls="nav-subitems-extensions"
      data-testid="nav-item-extensions"
      data-contains-active={containsActive ? "true" : undefined}
      onClick={onToggle}
    >
      <Puzzle size={16} aria-hidden />
      <span className="nav-label">Extensions</span>
      {!icons &&
        (collapsed ? (
          <ChevronRight size={14} aria-hidden />
        ) : (
          <ChevronDown size={14} aria-hidden />
        ))}
    </button>
  );
  return (
    <div className="nav-row">
      {icons ? <Tooltip label="Extensions">{heading}</Tooltip> : heading}
      <div
        className="nav-subitems"
        id="nav-subitems-extensions"
        hidden={collapsed}
      >
        {pages.map((page) => {
          const Icon = page.icon;
          const row = isProjectHome ? (
            <span role="link" aria-disabled="true" title="Open a project to use this tool"
              className={icons ? "nav-item nav-extension-icon" : "nav-subitem"} data-testid={`nav-item-${page.id}`}>
              {icons && <Icon size={16} aria-hidden />}
              <span className="nav-label">{page.title}</span>
            </span>
          ) : (
            <NavLink
              to={pagePath(page)}
              className={icons ? "nav-item nav-extension-icon" : "nav-subitem"}
              aria-label={page.title}
              data-testid={`nav-item-${page.id}`}
            >
              {icons && <Icon size={16} aria-hidden />}
              <span className="nav-label">{page.title}</span>
            </NavLink>
          );
          return icons ? (
            <Tooltip key={page.id} label={page.title}>
              {row}
            </Tooltip>
          ) : (
            <div key={page.id}>{row}</div>
          );
        })}
      </div>
    </div>
  );
}

export function NavRail() {
  // Live, not the static `navSections()`: a "panels" page's presence here follows `settings.panels`
  // through the shared React Query cache, so toggling a panel in Settings updates the nav the
  // moment the save succeeds — no reload (see `registry.ts`'s `useEnabledPages` doc comment).
  const sections = useNavSections();
  const location = useLocation();
  const labelled = useLabelledRail();
  // A page may still force the icon rail where labels would fit (`PageDef.railMode`); nothing does
  // today, and the width rule above is why.
  const forced = pageById(location.pathname.replace(/^\//, "").split("/")[0] ?? "")?.railMode === "icons";
  const icons = !isProjectHome && (forced || !labelled);
  const activePageId = location.pathname.replace(/^\//, "").split("/")[0] ?? "";

  const [collapsed, setCollapsed] = useState<string[]>(readCollapsed);
  const toggleCollapsed = useCallback((id: string) => {
    setCollapsed((current) => {
      const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
      writeCollapsed(next);
      return next;
    });
  }, []);

  return (
    <nav
      className={icons ? "nav-rail nav-rail-icons" : "nav-rail"}
      aria-label="Main"
      data-testid="nav-rail"
      data-rail-mode={icons ? "icons" : "labels"}
    >
      {/* The icon rail shows a 20px monogram instead of the wordmark: at 56px "TI-Toolbox" wraps
          onto a second line (ra_12 #6). `aria-label` on the wrapper keeps the name available to
          assistive tech in both states. */}
      <div className="nav-brand" aria-label="TI-Toolbox">
        <span className="nav-brand-mark" aria-hidden>
          TI
        </span>
        <span className="nav-brand-text">TI-Toolbox</span>
      </div>
      {sections.map((section) => (
        <div key={section.id} className={section.pinned ? "nav-section-pinned" : undefined}>
          {section.pinned && <div className="nav-divider" role="separator" />}
          <div className="nav-section">
            {section.pages.filter((page) => page.navGroup !== "panels").map((page) => {
              const Icon = page.icon;
              const row: ReactElement = isProjectHome && page.id !== "overview" ? (
                <span role="link" aria-disabled="true" title="Open a project to use this tool"
                  className="nav-item" aria-label={page.title} data-testid={`nav-item-${page.id}`}>
                  <Icon size={16} aria-hidden />
                  <span className="nav-label">{page.title}</span>
                </span>
              ) : (
                <NavLink
                  to={pagePath(page)}
                  className="nav-item"
                  aria-label={page.title}
                  aria-keyshortcuts={ariaShortcut(page.shortcut)}
                  data-testid={`nav-item-${page.id}`}
                >
                  <Icon size={16} aria-hidden />
                  <span className="nav-label">{page.title}</span>
                  {page.id === "jobs" && <PendingProposalsBadge />}
                </NavLink>
              );
              return icons ? (
                <Tooltip key={page.id} label={page.title}>
                  {row}
                </Tooltip>
              ) : (
                <div key={page.id} className="nav-row">
                  {row}
                </div>
              );
            })}
            <ExtensionsNav
              pages={section.pages.filter((page) => page.navGroup === "panels")}
              icons={icons}
              collapsed={collapsed.includes("extensions")}
              onToggle={() => toggleCollapsed("extensions")}
              activePageId={activePageId}
            />
          </div>
        </div>
      ))}
      <AppVersionLabel />
    </nav>
  );
}

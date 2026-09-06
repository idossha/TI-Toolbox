import { useEffect, useState, type ReactElement } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { pageById, useNavSections } from "./registry";
import { isMac } from "./keyboard";
import { Tooltip } from "../ui/Overlay";

/**
 * The width at which the rail carries labels — the same literal as `shell.css`.
 *
 * The program's Q1: U7 wanted labels at ≥ 1280, but a 216px rail at 1280 leaves a 1064px content
 * box, and the Viewer's embed needs ≥ 1200px there. Rather than one page forcing the icon rail and
 * every other page paying 160px for a label it did not need, the rail is **icons below 1440 and
 * labelled at or above it**: every page gains the width, and the Viewer needs no special case.
 */
export const LABEL_RAIL_QUERY = "(min-width: 1440px)";

/**
 * True while the rail is the icon rail. Tooltips exist for that state only — a tooltip repeating
 * a label that is already on screen is noise on every hover of every row.
 *
 * Two independent listeners, not one (found by B5 while wiring the Viewer, DESIGN.md §9 Q1): a
 * resize under load (the flake was first seen while the Viewer streamed a scene) can leave `matchMedia`'s own
 * `"change"` event un-fired — or fired but not landing as a state update — often enough to matter,
 * apparently a scheduling interaction between Electron's window resize and a busy
 * `window.addEventListener("message", …)` stream rather than anything wrong with the query itself.
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
 * The v3 rail (DESIGN.md §9, program U7): **flat and workflow-ordered** — Subjects ·
 * Pre-processing · Simulator · Optimizer · Analyzer · Results · Viewer · Jobs, then a spacer, then
 * Settings and Help. No group headers, no subject-id label, no subject scoping.
 *
 * Three things v2 had that are gone: the `Kbd` badge on every row (19 pieces of chrome for
 * something needed twice — shortcuts live in ⌘K and the `?` sheet), the group labels, and the
 * "Subject" heading that printed a subject id above pages the subject did not own.
 */

/** `aria-keyshortcuts` wants key names, not glyphs. */
function ariaShortcut(shortcut: string | undefined): string | undefined {
  if (!shortcut) return undefined;
  return `${isMac ? "Meta" : "Control"}+${shortcut}`;
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
  const icons = forced || !labelled;

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
            {section.pages.map((page) => {
              const Icon = page.icon;
              const row: ReactElement = (
                <NavLink
                  to={`/${page.id}`}
                  className="nav-item"
                  aria-label={page.title}
                  aria-keyshortcuts={ariaShortcut(page.shortcut)}
                  data-testid={`nav-item-${page.id}`}
                >
                  <Icon size={16} aria-hidden />
                  <span className="nav-label">{page.title}</span>
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
          </div>
        </div>
      ))}
    </nav>
  );
}

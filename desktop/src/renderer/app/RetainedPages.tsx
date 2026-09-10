import { useState } from "react";
import { Route, Routes, useLocation, type Location } from "react-router-dom";
import { PageActivityContext } from "./pageActivity";
import { PageErrorBoundary } from "./PageErrorBoundary";
import { PageIdContext } from "./pageSession";
import type { PageDef } from "./registry";

/**
 * Qt's tab lifecycle: visit once, then hide/show the same component and iframe instances.
 * Each page also keeps its last route context, so a hidden Viewer cannot consume another
 * page's search parameters. A project change replaces this entire host from Shell.
 */
export function RetainedPages({ pages }: { pages: readonly PageDef[] }) {
  const location = useLocation();
  const activeId = location.pathname.split("/")[1] ?? "";
  const [visits, setVisits] = useState<Record<string, Location>>({});
  const activePage = pages.find((page) => page.id === activeId);
  if (activePage && visits[activeId] !== location) {
    setVisits((previous) => ({ ...previous, [activeId]: location }));
  }

  return pages.map((page) => {
    const route = page.id === activeId ? location : visits[page.id];
    if (!route) return null;
    const active = page.id === activeId;
    return (
      <div
        key={page.id}
        className="retained-page"
        data-page-panel={page.id}
        data-page-active={active ? "true" : "false"}
        hidden={!active}
        aria-hidden={active ? undefined : true}
        {...(!active ? { inert: "" } : {})}
      >
        <PageIdContext.Provider value={page.id}>
          <PageActivityContext.Provider value={active}>
            <Routes location={route}>
              <Route
                // `/*`: sub-item routes (`/viewer/menu`, `/viewer/tetravox`) belong to this one
                // page and must not fall through to the catch-all.
                path={`/${page.id}/*`}
                element={<PageErrorBoundary pageId={page.id}><page.Component /></PageErrorBoundary>}
              />
            </Routes>
          </PageActivityContext.Provider>
        </PageIdContext.Provider>
      </div>
    );
  });
}

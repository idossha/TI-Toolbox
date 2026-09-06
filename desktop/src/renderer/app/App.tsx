import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./Shell";
import { ToastHost } from "../ui/Toast";
import { landingPage, useEnabledPages } from "./registry";

// Only the very first paint's initial route: MemoryRouter's `initialEntries` is read once, at
// construction, so it must be a plain value computed before the QueryClient has any data — the
// static default (matching each panel's own localStorage-mirrored `PageDef.enabled`) is exactly
// as good a guess here as `useEnabledPages()` would be, since neither can know the server's
// answer before the first render anyway.
//
// The landing page is the first page of the Project group (plan §1) — not simply the lowest
// `order`, so a Stage-2 page that sorts ahead of Project inside another group cannot silently
// become the app's front door.
const firstPage = landingPage();

export function App() {
  // Live, not the static `enabledPages`: a route must exist for a panel the moment NavRail shows
  // it (see `registry.ts`'s `useEnabledPages` doc comment) — otherwise a freshly toggled-on
  // panel would appear in the nav but 404 into the catch-all redirect when clicked.
  const pages = useEnabledPages();
  // One toast when the server installs a newer Tetravox embed under us (A3).
  return (
    <MemoryRouter initialEntries={firstPage ? [`/${firstPage.id}`] : ["/"]}>
      <ToastHost />
      <Routes>
        <Route element={<Shell pages={pages} />}>
          {pages.map((page) => (
            <Route
              key={page.id}
              path={`/${page.id}`}
              element={null}
            />
          ))}
          {firstPage && <Route path="*" element={<Navigate to={`/${firstPage.id}`} replace />} />}
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

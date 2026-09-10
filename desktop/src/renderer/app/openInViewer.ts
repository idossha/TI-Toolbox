/**
 * "Open in viewer" — the ONE way anywhere in the app asks the Viewer to show something.
 *
 * A deep link to the Viewer page, not a launch: D3 removed X11 from the runtime, so there is no
 * Freeview and no Gmsh to hand a file to. The query goes on the ROUTER's URL — the app is a
 * `MemoryRouter`, so that is the only query the Viewer page can read from a navigation — and the
 * subject also rides in the router state so the shell's subject switcher re-scopes with it.
 *
 * It lives in `app/` rather than in `pages/results/` because the jobs rail uses it too, and a
 * shell component importing a page module would pull that whole page into the shell's chunk.
 * `pages/results/index.tsx` re-exports it, so its existing importers are unchanged.
 *
 * **`open`** is the part that makes the link mean what it says. Without it the Viewer only
 * pre-filled its Menu and left an Open button to press — the maintainer's report, *"Open in viewer
 * sends me to the Menu but doesn't actually select the correct items"*. With `open: true` the
 * Viewer runs the same `open()` its own button runs (`POST /api/view/open`, `build_view`'s rules
 * per kind) and lands on the Tetravox sub-page with the Menu pre-filled behind it. It is opt-in:
 * Optimizer's and Analyzer's "go to the viewer for this subject" gestures are navigation, not a
 * request to render something, and they say so by leaving it unset.
 */
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

export interface ViewerLink {
  subject: string;
  simulation?: string;
  field?: string;
  kind?: "subject" | "simulation" | "analysis" | "group" | "custom";
  /** One file, when the caller is opening a specific artifact rather than a whole result. */
  path?: string;
  /** Build and show the scene on arrival, rather than only pre-filling the Menu. */
  open?: boolean;
}

export function viewerSearch(link: ViewerLink): string {
  const params = new URLSearchParams();
  params.set("kind", link.kind ?? (link.path ? "custom" : link.simulation ? "simulation" : "subject"));
  params.set("subject", link.subject);
  if (link.simulation) params.set("simulation", link.simulation);
  if (link.field) params.set("field", link.field);
  if (link.path) params.set("path", link.path);
  if (link.open) params.set("open", "1");
  return `?${params.toString()}`;
}

export function useOpenInViewer(): (link: ViewerLink) => void {
  const navigate = useNavigate();
  return useCallback(
    (link: ViewerLink) =>
      navigate({ pathname: "/viewer", search: viewerSearch(link) }, { state: { subject: link.subject } }),
    [navigate],
  );
}

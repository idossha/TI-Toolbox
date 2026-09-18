/** Shared native viewer action; URL helpers remain available for saved deep links. */
import { useCallback, useRef } from "react";
import { openView } from "../pages/viewer/api";
import { openNativeScene } from "../viewer/native";
import { notify } from "../ui/Toast";

export interface ViewerLink {
  subject: string;
  simulation?: string;
  field?: string;
  kind?: "subject" | "simulation" | "analysis" | "group" | "custom";
  /** One file, when the caller is opening a specific artifact rather than a whole result. */
  path?: string;
  /** For saved deep links: build the scene on arrival. Direct native actions always open. */
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

/** Open the requested scene without changing the current page or subject selection. */
export function useOpenInViewer(): (link: ViewerLink) => void {
  const pending = useRef(new Set<string>());
  return useCallback((link: ViewerLink) => {
    const { subject, simulation, field, path } = link;
    const kind = link.kind ?? (path ? "custom" : simulation ? "simulation" : "subject");
    const key = JSON.stringify([kind, subject, simulation, field, path]);
    if (pending.current.has(key)) return;
    const requests = pending.current;
    requests.add(key);
    void (async () => {
      try {
        // A `*.tetravox.json` artifact is already a scene: opening it means opening it, not asking
        // the server to compose a second one around it.
        if (path?.toLowerCase().endsWith(".tetravox.json")) {
          await openNativeScene(path);
          return;
        }
        const written = await openView(kind, { subject, simulation, field, path }, path ? { files: [path] } : {});
        await openNativeScene(written.path);
      } catch (error) {
        notify.error(`Could not open TetraVox: ${error instanceof Error ? error.message : String(error)}`);
      } finally {
        requests.delete(key);
      }
    })();
  }, []);
}

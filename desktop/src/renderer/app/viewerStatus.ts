/**
 * The status bar's window onto the viewer, without dragging `viewer/store.ts` into the entry chunk.
 *
 * `viewer/store.ts` is a few KB of postMessage plumbing over the Tetravox Embed's iframe (the
 * embed itself ships inside the container image, not this bundle — D1/D3,
 * `dev/notes/v3-docker-streamline-plan.md`), so importing it here is cheap either way. The lazy
 * fetch is kept anyway for the chunking property it still gives: through `import.meta.glob`,
 * whose loader Vite turns into the same dynamic chunk the Viewer page itself uses, the module
 * loads only while a page that declares `PageDef.viewer` is mounted. Off that page the bar reads
 * "—" and no chunk is fetched.
 */
import { useEffect, useState } from "react";
import type { ViewerStatus } from "../viewer/store";

export interface ViewerReadout {
  status: ViewerStatus;
  renderer: string | null;
  cursor: [number, number, number] | null;
  space: "subject" | "mni";
}

interface ViewerStoreModule {
  useViewerStore: {
    getState: () => ViewerReadout;
    subscribe: (listener: () => void) => () => void;
  };
}

// A glob rather than a bare `import()` so the path is resolved at build time and the module is
// never in the entry graph. One key, one loader.
const loaders = import.meta.glob("../viewer/store.ts") as Record<string, () => Promise<unknown>>;

const IDLE: ViewerReadout = { status: "idle", renderer: null, cursor: null, space: "subject" };

/**
 * `active` is "a viewer page is on screen". When it goes false the readout resets to idle: the
 * cursor of a canvas that is no longer mounted is not a fact about anything.
 */
export function useViewerReadout(active: boolean): ViewerReadout | null {
  const [readout, setReadout] = useState<ViewerReadout | null>(null);
  const [wasActive, setWasActive] = useState(active);

  // Adjusting state during render (React's documented "a prop changed" pattern) rather than in an
  // effect: leaving a viewer page must drop the readout in the same commit that unmounts the
  // canvas, not one render later, and an effect that calls setState synchronously is a cascading
  // render by definition.
  if (wasActive !== active) {
    setWasActive(active);
    setReadout(null);
  }

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;
    const load = Object.values(loaders)[0];
    if (!load) return;
    void load().then((mod) => {
      if (cancelled) return;
      const store = (mod as ViewerStoreModule).useViewerStore;
      const read = () => {
        const s = store.getState();
        setReadout({ status: s.status, renderer: s.renderer, cursor: s.cursor, space: s.space });
      };
      read();
      unsubscribe = store.subscribe(read);
    });
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, [active]);

  return active ? (readout ?? IDLE) : null;
}

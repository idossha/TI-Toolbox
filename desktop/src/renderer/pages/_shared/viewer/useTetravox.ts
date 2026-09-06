/**
 * The renderer's view of the external Tetravox app (V1/V3,
 * `dev/notes/v3-native-panes-external-viewer-plan.md`).
 *
 * One hook, used by the Viewer page and by Settings, so both answer the same question the same
 * way. It is thin on purpose: everything it knows comes from `window.tit.viewer`, which is the
 * only thing that can look at the host's filesystem or start a program on it.
 *
 * `mode` is the fact that shapes every caller. In Electron the app can be launched; in a browser
 * there is no main process at all, so the scene file is downloaded instead and the person opens it
 * themselves. Neither is an error state and neither should be reported as one.
 */
import { useCallback, useEffect, useState } from "react";
import type { TitViewerInfo, TitViewerOpenResult } from "../../../../shared/tit-bridge";

export interface TetravoxHandle {
  mode: "electron" | "browser";
  /** `null` until the first probe answers (Electron only); always `null` in browser mode. */
  info: TitViewerInfo | null;
  /** Re-probe the host — call it after the user changes the path override or installs the app. */
  refresh: () => void;
  open: (containerScenePath: string) => Promise<TitViewerOpenResult>;
  setPath: (path: string) => Promise<void>;
}

export function useTetravox(): TetravoxHandle {
  const bridge = typeof window !== "undefined" ? window.tit?.viewer : undefined;
  const [info, setInfo] = useState<TitViewerInfo | null>(null);
  const [epoch, setEpoch] = useState(0);

  useEffect(() => {
    if (!bridge) return;
    let cancelled = false;
    void bridge.probe().then((next) => {
      if (!cancelled) setInfo(next);
    });
    return () => {
      cancelled = true;
    };
  }, [bridge, epoch]);

  const refresh = useCallback(() => setEpoch((e) => e + 1), []);

  const open = useCallback(
    async (containerScenePath: string): Promise<TitViewerOpenResult> => {
      if (!bridge) return { ok: false, reason: "no desktop shell" };
      return bridge.open(containerScenePath);
    },
    [bridge],
  );

  const setPath = useCallback(
    async (path: string): Promise<void> => {
      if (!bridge) return;
      setInfo(await bridge.setPath(path));
    },
    [bridge],
  );

  return { mode: bridge ? "electron" : "browser", info, refresh, open, setPath };
}

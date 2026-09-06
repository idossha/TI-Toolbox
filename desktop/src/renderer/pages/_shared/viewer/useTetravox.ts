/**
 * The renderer's view of the external Tetravox app (V1/V3,
 * `dev/notes/v3-native-panes-external-viewer-plan.md`).
 *
 * One hook, used by the Viewer page and by Settings, so both answer the same question the same
 * way. It is thin on purpose: everything it knows comes from `window.tit.viewer`, which is the
 * only thing that can look at the host's filesystem or start a program on it.
 *
 * V6 added the **managed install**: TI-Toolbox downloads and maintains Tetravox itself, so this
 * hook also carries the live progress of an install (`progress`) and the three actions Settings
 * needs — `install`, `checkUpdates`, `remove`. Progress is a push from main rather than a poll:
 * a 130 MB download reports itself, and nothing here has to ask.
 *
 * `mode` is the fact that shapes every caller. In Electron the app can be launched; in a browser
 * there is no main process at all, so the scene file is downloaded instead and the person opens it
 * themselves. Neither is an error state and neither should be reported as one.
 */
import { useCallback, useEffect, useState } from "react";
import type { TitViewerEvent, TitViewerInfo, TitViewerInstallResult, TitViewerOpenResult } from "../../../../shared/tit-bridge";

export interface TetravoxHandle {
  mode: "electron" | "browser";
  /** `null` until the first probe answers (Electron only); always `null` in browser mode. */
  info: TitViewerInfo | null;
  /** Re-probe the host — call it after the user changes the path override or installs the app. */
  refresh: () => void;
  open: (containerScenePath: string) => Promise<TitViewerOpenResult>;
  setPath: (path: string) => Promise<void>;
  /** The last install event, or null when none is in flight. Cleared once `done` is re-probed. */
  progress: TitViewerEvent | null;
  install: () => Promise<TitViewerInstallResult>;
  checkUpdates: () => Promise<void>;
  remove: () => Promise<void>;
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

  const [progress, setProgress] = useState<TitViewerEvent | null>(null);
  useEffect(() => {
    if (!bridge) return;
    return bridge.onEvent((event) => {
      setProgress(event.phase === "done" ? null : event);
      // A finished install changes what `probe` answers, so re-ask rather than patch the state
      // here: main is the only thing that knows which copy discovery now prefers.
      if (event.phase === "done") refresh();
    });
  }, [bridge, refresh]);

  const install = useCallback(async (): Promise<TitViewerInstallResult> => {
    if (!bridge) return { ok: false, reason: "no desktop shell" };
    const result = await bridge.install();
    refresh();
    return result;
  }, [bridge, refresh]);

  const checkUpdates = useCallback(async (): Promise<void> => {
    if (!bridge) return;
    setInfo(await bridge.checkUpdates());
  }, [bridge]);

  const remove = useCallback(async (): Promise<void> => {
    if (!bridge) return;
    setInfo(await bridge.remove());
  }, [bridge]);

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

  return { mode: bridge ? "electron" : "browser", info, refresh, open, setPath, progress, install, checkUpdates, remove };
}

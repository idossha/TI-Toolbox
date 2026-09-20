/** A launch receipt is not proof that the viewer loaded a scene or acquired OS focus. */
export type ViewerHandoffResult =
  | { ok: true; status: "launch-requested" }
  | { ok: false; cancelled: true };

/** Serialize native handoffs so two requests cannot bypass the running-window confirmation. */
export function createViewerHandoff() {
  let tail: Promise<unknown> = Promise.resolve();
  return (request: {
    hasScene: boolean;
    running: () => Promise<boolean>;
    confirm: () => Promise<boolean>;
    launch: () => Promise<void>;
  }): Promise<ViewerHandoffResult> => {
    const next = tail.then(async (): Promise<ViewerHandoffResult> => {
      // A failed process probe cannot establish that replacing a scene is safe.
      const mayBeRunning = request.hasScene && await request.running().catch(() => true);
      if (mayBeRunning && !await request.confirm()) {
        return { ok: false, cancelled: true };
      }
      await request.launch();
      return { ok: true, status: "launch-requested" };
    });
    tail = next.catch(() => undefined);
    return next;
  };
}

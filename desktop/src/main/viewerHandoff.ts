/** Serialize native handoffs so two requests cannot bypass the running-window confirmation. */
export function createViewerHandoff() {
  let tail: Promise<unknown> = Promise.resolve();
  return (request: {
    hasScene: boolean;
    running: () => Promise<boolean>;
    confirm: () => Promise<boolean>;
    launch: () => Promise<void>;
  }): Promise<{ ok: boolean; cancelled?: boolean }> => {
    const next = tail.then(async () => {
      if (request.hasScene && await request.running() && !await request.confirm()) {
        return { ok: false, cancelled: true };
      }
      await request.launch();
      return { ok: true };
    });
    tail = next.catch(() => undefined);
    return next;
  };
}

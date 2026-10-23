/**
 * "Reveal in file manager" for an artifact path, via the `TitBridge` method the main process
 * resolves through host<->container path mapping (`stack.getCurrent()`'s mount, or
 * `GET /api/project`'s `host_path` when this app did not itself start the stack). Falls back to a
 * notice outside Electron (browser mode has no OS shell to hand a path to).
 */
import { isElectron } from "../../env";
import { notify } from "../../ui/Toast";

/** "Reveal in file manager" — mirrors the identical helper in `pages/results/index.tsx`. */
export function reveal(path: string): void {
  const fn = isElectron ? window.tit?.showItemInFolder : undefined;
  if (fn) void fn(path);
  else notify.info("Reveal in file manager isn't available outside the Electron app.");
}

/**
 * Open a folder in the file manager — the folder itself, not its parent with it selected (what
 * `reveal` does, which is right for a file and wrong for a button that says "Open … folder").
 * The main process refuses a path outside the project mount or with a `.`/`..` segment, and the OS
 * refuses one that does not exist; both come back as `{ ok: false, reason }`, which is said rather
 * than swallowed.
 */
export function openFolder(path: string): void {
  const open = isElectron ? window.tit?.openPath : undefined;
  if (!open) {
    notify.info("Opening a folder isn't available outside the Electron app.");
    return;
  }
  void open(path).then((result) => {
    if (!result.ok) notify.error("Could not open the folder.", result.reason);
  });
}

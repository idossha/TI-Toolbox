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

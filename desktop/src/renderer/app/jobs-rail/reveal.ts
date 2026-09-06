/**
 * OS-integration helpers for artifact paths, via the `TitBridge` methods P9's main process
 * resolves through host<->container path mapping (`stack.getCurrent()`'s mount, or
 * `GET /api/project`'s `host_path` when this app did not itself start the stack). Both fall back
 * gracefully outside Electron (browser mode has no OS shell to hand a path to).
 */
import { isElectron } from "../../env";
import { notify } from "../../ui/Toast";
import { artifactUrl } from "./api";

/** "Reveal in file manager" — mirrors the identical helper in `pages/results/index.tsx`. */
export function reveal(path: string): void {
  const fn = isElectron ? window.tit?.showItemInFolder : undefined;
  if (fn) void fn(path);
  else notify.info("Reveal in file manager isn't available outside the Electron app.");
}

/**
 * "Open" with the OS default application (`ArtifactList`'s Open action, distinct from its View
 * action — DESIGN.md §5's "Open / View / Reveal" triad). Falls back to the same in-browser tab
 * `onView` uses when there is no native shell to hand the path to (browser mode).
 */
export function openNative(path: string): void {
  const fn = isElectron ? window.tit?.openPath : undefined;
  if (fn) void fn(path);
  else window.open(artifactUrl(path), "_blank", "noopener");
}

/**
 * One `<iframe>` onto a Tetravox embed, and its lifecycle — **the only one in the app**.
 *
 * Two things host an embed now: the Viewer page (`TetravoxFrame`) and the run pages' scene panes
 * (`pages/_shared/scene/ScenePane`), and up to four are alive at once. They share this element,
 * `channel.ts`'s message layer, and this teardown, because the parts that are easy to get subtly
 * wrong are the same in both: which sandbox flags, when the channel is created against *which* DOM
 * node, and that the workers are freed on unmount.
 *
 * ## Why `sandbox="allow-scripts allow-same-origin"`
 *
 * `allow-scripts` is obvious — a WebGL2/WASM renderer with no scripts is a blank box.
 *
 * `allow-same-origin` is the one that deserves a sentence, because the pair together is usually a
 * smell ("a sandbox that isn't"). Here the embed is served **from this app's own origin**, by the
 * same `tit.server` that served this page, and it needs to be:
 *
 *  - its dataset workers `fetch('/api/files/raw/…')` and `fetch('/api/scene/surface?…')`, and both
 *    routes are authenticated by the session cookie. A sandboxed frame WITHOUT `allow-same-origin`
 *    is an opaque origin: no cookie is sent, every fetch is cross-origin, and every file 401s.
 *  - the protocol's whole trust model is `event.origin === hostOrigin`. An opaque origin posts
 *    `"null"`, which no host can distinguish from any other sandboxed frame on the page — the
 *    origin check would have to be dropped exactly where it matters most.
 *  - `worker-src 'self' blob:` and `'wasm-unsafe-eval'` are granted to `/tetravox/` responses by
 *    the server; an opaque origin cannot use a `'self'` source at all.
 *
 * So the pair grants the embed nothing it would not already have as a plain same-origin iframe,
 * and the flags that are ABSENT are the ones doing work: no `allow-popups`, no `allow-modals`, no
 * `allow-top-navigation` (a bug in the viewer cannot navigate the app away), no `allow-downloads`,
 * no `allow-forms`. The real confinement is the server-side CSP on `/tetravox/`, plus the fact
 * that a crashed or leaking viewer dies with its frame.
 *
 * ## Session lifetime and teardown
 *
 * Each embed instance carries its own wasm heap and its own dataset workers. The **only** way a
 * dataset's heap comes back is `worker.terminate()`, and unmounting the iframe does that for every
 * worker at once. Visited tabs retain their frame for the project session so navigation preserves
 * camera, layers and loaded geometry (DESIGN.md §13). Project close/switch and explicit reload
 * unmount the frame and release those workers. `disconnect`
 * posts `reset` first, for the case where the frame survives the unmount (React strict mode's
 * double invoke, a remount into the same DOM node).
 */
import { useEffect, useRef } from "react";
import { embedUrl } from "./protocol";
import { HANDSHAKE_TIMEOUT_MS } from "./channel";

export interface EmbedFrameProps {
  /**
   * The origin the embed is served from — this app's own. Defaults to `window.location.origin`;
   * passed explicitly only by tests.
   */
  origin?: string;
  /**
   * Open a channel against this iframe. The signature is the Viewer store's `connect` verbatim, so
   * a host may pass its store action or an instance-local one from `useEmbedHost`.
   */
  connect: (frame: HTMLIFrameElement, embedOrigin: string, timeoutMs: number) => void;
  /** Close it. Called on unmount and whenever `reloadToken` changes. */
  disconnect: () => void;
  /** Overrides the handshake timeout. Tests use a short one; nothing else should set it. */
  handshakeTimeoutMs?: number;
  /**
   * Bumped by the host to force a full remount of the iframe — the only way to recover from a
   * frame that mounted and never answered.
   */
  reloadToken?: number;
  title: string;
  className?: string;
  /** `data-testid` on the iframe itself. */
  testId?: string;
  /** Run-page previews use only the viewport; the dedicated Viewer keeps its full controls. */
  presentation?: "full" | "viewport";
}

/**
 * The origin to serve the embed from, or `""` when there is none.
 *
 * `window.location.origin` is the string `"null"` for an opaque document (file://, a data: URL).
 * There is no embed to reach in that case, and building a URL from it would produce
 * `"nullundefined/tetravox/…"`.
 */
export function embedOriginFor(explicit: string | undefined): string {
  if (explicit !== undefined) return explicit;
  if (typeof window === "undefined") return "";
  const origin = window.location.origin;
  return origin === "null" ? "" : origin;
}

export function EmbedFrame({
  origin,
  connect,
  disconnect,
  handshakeTimeoutMs = HANDSHAKE_TIMEOUT_MS,
  reloadToken = 0,
  title,
  className,
  testId,
  presentation = "full",
}: EmbedFrameProps) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const resolvedOrigin = embedOriginFor(origin);

  useEffect(() => {
    const frame = frameRef.current;
    if (frame === null || resolvedOrigin === "") return;
    connect(frame, resolvedOrigin, handshakeTimeoutMs);
    // `reloadToken` is a dependency for exactly one reason: the `key` below remounts the
    // `<iframe>` DOM node when it changes, and this effect has to run again against the NEW node
    // rather than the stale ref value.
    return () => disconnect();
  }, [connect, disconnect, resolvedOrigin, handshakeTimeoutMs, reloadToken]);

  if (resolvedOrigin === "") return null;

  return (
    <iframe
      key={reloadToken}
      ref={frameRef}
      className={className}
      data-testid={testId}
      title={title}
      src={embedUrl(resolvedOrigin, undefined, presentation)}
      // See this module's header for why these two, and only these two.
      sandbox="allow-scripts allow-same-origin"
      allow="fullscreen"
    />
  );
}

/**
 * The postMessage channel to one Tetravox embed — **one message layer for every host in the app**.
 *
 * There are up to four embeds alive at once now: the Viewer page's, and the run pages' three scene
 * panes (plan of record `docs/dev/HISTORY.md § 2026-09-04 (embed convergence)`, decision E6). They share this
 * file and `EmbedFrame.tsx`, deliberately: a second copy of the handshake, the id correlation and
 * the teardown is a second place for "the frame reloaded and nobody re-sent the scene" to be wrong,
 * and the two would drift the first time one of them was fixed.
 *
 * What is here is exactly what has no opinion about *what* is being shown: the origin/source check,
 * the `h<n>` correlation ids, the handshake timer, and a `dispose` that rejects every promise it
 * still owes. What each host does with the messages — the Viewer's layer list and progress rows,
 * a pane's electrodes and regions — stays with that host.
 *
 * Two rules, each with the failure it prevents:
 *
 *  - **A reply is matched by its `id` alone, never by its type.** Two screenshots in flight would
 *    otherwise resolve in whatever order the embed answered them.
 *  - **`dispose` rejects every pending request.** A promise that outlived the frame would resolve
 *    against a channel whose iframe is gone, and its `.then` would run against an unmounted host.
 *
 * This file was `store.ts`'s private half until lane M; it moved rather than being copied, and the
 * Viewer store imports it back.
 */
import { PROTOCOL_VERSION, acceptEmbedMessage, type EmbedMessage, type HostPayload, type HostRequest } from "./protocol";

/** How long a mounted iframe has to say `ready` before a host calls it a missing embed. */
export const HANDSHAKE_TIMEOUT_MS = 8000;

/**
 * How long a request (`screenshot`, `serialize`, `probe`, `getCamera`) waits for its reply.
 *
 * A reply that never comes is the normal case for a message an embed build does not implement —
 * the protocol says "ignore a type you do not know", so silence is CORRECT behaviour on the far
 * side and a host that waited forever would leave a control spinning until the page was closed.
 * Every caller of `request` has a fallback for the rejection.
 */
export const REQUEST_TIMEOUT_MS = 6000;

export interface EmbedChannel {
  frame: HTMLIFrameElement;
  origin: string;
  post: (message: HostPayload) => void;
  request: <T extends EmbedMessage>(message: HostRequest, wanted: T["type"]) => Promise<T>;
  dispose: () => void;
}

/**
 * The whole postMessage plumbing, in one place and with no React in it.
 *
 * Ids are `h0`, `h1`, … A request whose reply is an `error` rejects with that message; a request
 * that is never answered rejects when the channel is disposed, so no promise outlives the frame.
 */
export function createChannel(
  frame: HTMLIFrameElement,
  origin: string,
  onMessage: (message: EmbedMessage) => void,
  timeoutMs: number,
  onHandshakeTimeout: () => void,
): EmbedChannel {
  let counter = 0;
  const pending = new Map<
    string,
    { resolve: (m: EmbedMessage) => void; reject: (e: Error) => void; wanted: string; timer: ReturnType<typeof setTimeout> }
  >();
  let handshake: ReturnType<typeof setTimeout> | null = setTimeout(onHandshakeTimeout, timeoutMs);

  const clearHandshake = (): void => {
    if (handshake !== null) {
      clearTimeout(handshake);
      handshake = null;
    }
  };

  const listener = (event: MessageEvent): void => {
    const message = acceptEmbedMessage(
      { source: event.source, origin: event.origin, data: event.data },
      { expectedSource: frame.contentWindow, embedOrigin: origin },
    );
    if (message === null) return;
    if (message.type === "ready") clearHandshake();

    const id = message.id;
    if (id !== undefined) {
      const waiter = pending.get(id);
      if (waiter !== undefined) {
        pending.delete(id);
        clearTimeout(waiter.timer);
        if (message.type === "error") waiter.reject(new Error(message.message));
        else if (message.type === waiter.wanted) waiter.resolve(message);
        else waiter.reject(new Error(`expected ${waiter.wanted}, got ${message.type}`));
      }
    }
    onMessage(message);
  };
  window.addEventListener("message", listener);

  const post = (message: HostPayload): void => {
    // `contentWindow` is null between an `src` change and the new document's first tick; a message
    // posted then is simply lost, and the caller will re-send after `ready`.
    frame.contentWindow?.postMessage({ ...message, tvx: PROTOCOL_VERSION }, origin);
  };

  return {
    frame,
    origin,
    post,
    request: <T extends EmbedMessage>(message: HostRequest, wanted: T["type"]): Promise<T> => {
      const id = `h${counter++}`;
      return new Promise<T>((resolve, reject) => {
        const timer = setTimeout(() => {
          pending.delete(id);
          reject(new Error(`the viewer did not answer "${message.type}" within ${REQUEST_TIMEOUT_MS} ms`));
        }, REQUEST_TIMEOUT_MS);
        pending.set(id, { resolve: resolve as (m: EmbedMessage) => void, reject, wanted, timer });
        post({ ...message, id } as HostPayload);
      });
    },
    dispose: () => {
      clearHandshake();
      window.removeEventListener("message", listener);
      for (const waiter of pending.values()) {
        clearTimeout(waiter.timer);
        waiter.reject(new Error("viewer disconnected"));
      }
      pending.clear();
    },
  };
}

/**
 * `/ws/tetravox` — one toast when the server replaces the viewer bundle under the app (A3,
 * `dev/notes/v3-tetravox-selection-pipeline-plan.md`).
 *
 * Why a hook and not a stream class: this socket carries one message type, has no state to
 * accumulate, no backfill and nothing to subscribe to. `jobsStream.ts`'s machinery (a store, a
 * seed from REST, per-job event rings) would all be dead weight. What it does borrow is the
 * reconnect shape — a viewer update arriving during a dropped connection is simply missed, which
 * is safe, because `GET /api/tetravox` is always the truth and Settings shows it.
 *
 * The toast is deliberately *not* a reload: panes already mounted keep the iframe they have (the
 * old bundle is still on disk and still being served to them); a new pane gets the new one. Being
 * told is what lets a user decide when to reload; doing it for them would drop whatever they were
 * looking at.
 */
import { useEffect } from "react";
import { wsUrl } from "../api/client";
import { notify } from "../ui/Toast";

export interface TetravoxUpdatedEvent {
  type: "tetravox.updated";
  version: string;
  protocol: number | null;
  message: string;
}

const RECONNECT_MS = 5000;

/** Narrow an arbitrary parsed message; anything else is ignored rather than shown. */
export function asTetravoxUpdated(value: unknown): TetravoxUpdatedEvent | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (v.type !== "tetravox.updated" || typeof v.version !== "string") return null;
  return {
    type: "tetravox.updated",
    version: v.version,
    protocol: typeof v.protocol === "number" ? v.protocol : null,
    message: typeof v.message === "string" ? v.message : `Tetravox ${v.version} installed`,
  };
}

export function useTetravoxUpdated(): void {
  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const open = () => {
      if (stopped) return;
      try {
        socket = new WebSocket(wsUrl("/ws/tetravox"));
      } catch {
        timer = setTimeout(open, RECONNECT_MS);
        return;
      }
      socket.onmessage = (ev) => {
        if (typeof ev.data !== "string") return;
        let parsed: unknown;
        try {
          parsed = JSON.parse(ev.data);
        } catch {
          return;
        }
        const event = asTetravoxUpdated(parsed);
        if (event) notify.success(event.message);
      };
      socket.onclose = () => {
        socket = null;
        if (!stopped) timer = setTimeout(open, RECONNECT_MS);
      };
    };
    open();

    return () => {
      stopped = true;
      if (timer !== null) clearTimeout(timer);
      if (socket) {
        socket.onclose = null;
        socket.onmessage = null;
        socket.close();
      }
    };
  }, []);
}

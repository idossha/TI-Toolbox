import { useEffect, useSyncExternalStore } from "react";
import { wsUrl } from "../api/client";
import { SystemStream, type SystemStreamState } from "./systemStream";

/**
 * One shared stream for the whole app: started by the first mounted consumer, stopped when the
 * last one unmounts. Acquire/release live in an effect (not in render), so StrictMode's
 * mount → unmount → mount rehearsal simply stops and restarts the stream without leaking sockets.
 */
const IDLE: SystemStreamState = { status: "idle", samples: [], attempt: 0 };
const listeners = new Set<() => void>();
let shared: SystemStream | null = null;
let users = 0;

function notify(): void {
  for (const l of listeners) l();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Current state of the shared stream, or a stable idle state when nobody holds it. */
export function getState(): SystemStreamState {
  return shared ? shared.getState() : IDLE;
}

export function acquire(): void {
  users += 1;
  if (!shared) {
    shared = new SystemStream({ url: wsUrl("/ws/system") });
    shared.subscribe(notify);
    shared.start();
    notify();
  }
}

export function release(): void {
  users = Math.max(0, users - 1);
  if (users === 0 && shared) {
    shared.stop();
    shared = null;
    notify();
  }
}

export function useSystemStream(): SystemStreamState {
  useEffect(() => {
    acquire();
    return release;
  }, []);
  return useSyncExternalStore(subscribe, getState);
}

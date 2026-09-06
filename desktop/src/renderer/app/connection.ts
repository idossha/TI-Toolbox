/**
 * One reading of "is the app talking to its server", for the context bar's dot, the disconnected
 * warning strip and any page that needs to disable a commit with a reason (DESIGN.md §4.4).
 *
 * The signal is the shared `/ws/system` socket: it is the only always-on connection, so its state
 * is the app's state. A 401 is reported separately by `api/client`'s `onUnauthorized` and the
 * shell passes it in, because "the server forgot you" is a different problem from "the socket
 * dropped" and the two want different copy.
 */
import { useSystemStream } from "../ws/useSystemStream";

export type ConnectionStatus = "connected" | "connecting" | "reconnecting" | "disconnected" | "unauthenticated";

export interface Connection {
  status: ConnectionStatus;
  /**
   * True only for a real problem (reconnecting / closed / 401) — never for the first connection
   * attempt, which would put a warning strip on every launch and in every screenshot.
   */
  degraded: boolean;
  /** Sentence-case, plain: shown in the context bar and as a disabled primary's tooltip. */
  label: string;
  reason: string | null;
}

const LABEL: Record<ConnectionStatus, string> = {
  connected: "connected",
  connecting: "connecting",
  reconnecting: "reconnecting",
  disconnected: "disconnected",
  unauthenticated: "not authenticated",
};

const REASON: Record<ConnectionStatus, string | null> = {
  connected: null,
  connecting: null,
  reconnecting: "Reconnecting to the server. Nothing can be queued until it answers.",
  disconnected: "No connection to the server. Nothing can be queued until it answers.",
  unauthenticated: "The server rejected the session. Sign in again to queue work.",
};

export function connectionStatus(streamStatus: string, unauthenticated: boolean): ConnectionStatus {
  if (unauthenticated) return "unauthenticated";
  if (streamStatus === "open") return "connected";
  if (streamStatus === "reconnecting") return "reconnecting";
  // "idle" is the state before the first consumer mounts and "connecting" is the first attempt:
  // neither is a problem, and neither may raise a warning strip on every launch.
  if (streamStatus === "idle" || streamStatus === "connecting") return "connecting";
  return "disconnected";
}

export function useConnection(unauthenticated = false): Connection {
  const stream = useSystemStream();
  const status = connectionStatus(stream.status, unauthenticated);
  return {
    status,
    degraded: status !== "connected" && status !== "connecting",
    label: LABEL[status],
    reason: REASON[status],
  };
}

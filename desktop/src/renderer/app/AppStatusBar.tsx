import { useQuery } from "@tanstack/react-query";
import { getVersion } from "../api/client";
import { StatusBar, StatusCell } from "../ui/Chrome";
import { StatusDot } from "../ui/Status";
import type { Connection } from "./connection";
import { useRegisteredStatusCells } from "./statusCells";

/**
 * The 24 px strip along the bottom (DESIGN.md §11, program U8).
 *
 * It has **no page knowledge**. The left cluster is whatever the page on screen registered through
 * `useStatusCells`, sorted by priority; a cell with no value never reaches here (`statusCells.ts`
 * drops it), so there is no "—" in the bar. The right cluster is the shell's own and is always
 * present in this order: connection, then `tit x.y · api vN` — the two facts that stay true
 * whichever page is on.
 *
 * What v2 had here and v3 does not: the RAS / Space / Renderer cells and the `viewerStatus` import
 * behind them. The Viewer page registers those three itself and takes them with it when you leave.
 */
export function AppStatusBar({ connection, unauthenticated }: { connection: Connection; unauthenticated: boolean }) {
  const version = useQuery({ queryKey: ["version"], queryFn: () => getVersion(), enabled: !unauthenticated });
  const cells = useRegisteredStatusCells();

  const dotKind =
    connection.status === "unauthenticated"
      ? "danger"
      : connection.status === "connected"
        ? "success"
        : connection.status === "reconnecting"
          ? "warning"
          : "neutral";

  return (
    <StatusBar>
      {cells.map((cell) => (
        <StatusCell key={cell.id} id={cell.id} label={cell.label} title={cell.title}>
          <span
            className={[
              cell.mono ? "mono tabular-nums" : undefined,
              cell.tone === "warning" ? "status-bar-warning" : undefined,
              cell.tone === "danger" ? "status-bar-danger" : undefined,
            ]
              .filter(Boolean)
              .join(" ")}
            data-testid={`status-${cell.id}`}
          >
            {cell.value}
          </span>
        </StatusCell>
      ))}
      <StatusCell id="connection" end title={connection.reason ?? undefined}>
        <span className="status-bar-connection" data-testid="status-connection">
          <StatusDot kind={dotKind} pulse={dotKind === "warning"} />
          {connection.label}
        </span>
      </StatusCell>
      <StatusCell id="version">
        <span className="tabular-nums" data-testid="server-version">
          {version.data ? `tit ${version.data.tit_version} · api ${version.data.server_api}` : ""}
        </span>
      </StatusCell>
    </StatusBar>
  );
}

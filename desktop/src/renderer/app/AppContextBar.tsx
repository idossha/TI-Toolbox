import { useState } from "react";
import { Search } from "lucide-react";
import { logout } from "../api/client";
import { isElectron } from "../env";
import { ContextBar } from "../ui/Chrome";
import { StatusDot } from "../ui/Status";
import { Kbd } from "../ui/Feedback";
import { Button } from "../ui/Button";
import type { Connection } from "./connection";
import { modKey } from "./keyboard";

/**
 * The 40 px strip (plan §1, program U11). Left: the palette trigger, now a wide search field —
 * this is the only thing the bar owns on that side. Right: the connection dot and the running-job
 * count.
 *
 * What used to live here and does not any more: the project crumb and the subject switcher
 * (program U11 — a second place to pick a subject that no page needed; the project is inspected at
 * Settings ▸ Project, reachable from the rail and the palette's "Open settings", and every subject
 * switch already goes through this same palette's Subjects section). What was already deliberately
 * NOT here stays out: the theme control (a palette action) and the version string (a status-bar
 * cell).
 */
/** POST /auth/logout, then leave the page: launcher in Electron, a fresh (401) load in browser mode. */
async function signOut(): Promise<void> {
  try {
    await logout();
  } finally {
    if (isElectron) await window.tit!.connect();
    else window.location.reload();
  }
}

export function AppContextBar({
  connection,
  runningJobs,
  onToggleJobsRail,
  onOpenPalette,
}: {
  connection: Connection;
  runningJobs: number;
  onToggleJobsRail: () => void;
  onOpenPalette: () => void;
}) {
  const [signingOut, setSigningOut] = useState(false);

  const dotKind =
    connection.status === "unauthenticated"
      ? "danger"
      : connection.status === "connected"
        ? "success"
        : connection.status === "reconnecting"
          ? "warning"
          : "neutral";

  return (
    <ContextBar
      end={
        <>
          <span className="context-bar-connection" data-testid="connection-state" title={connection.reason ?? undefined}>
            <StatusDot kind={dotKind} pulse={dotKind === "warning"} />
            {connection.label}
          </span>
          <button
            type="button"
            className="jobs-indicator"
            onClick={onToggleJobsRail}
            aria-label={`${runningJobs} running — toggle the jobs panel`}
            data-testid="jobs-count"
          >
            {runningJobs} running
          </button>
          {/* Only when the session is gone — the same rule the v1 top bar had. A healthy session
              signs out from the command palette, which is where preferences and account actions
              live now; a rejected one needs the way out to be on screen, because the palette is
              not the first thing someone reaches for when the app says it cannot talk to the
              server. */}
          {connection.status === "unauthenticated" && (
            <Button
              variant="secondary"
              size="sm"
              loading={signingOut}
              onClick={() => {
                setSigningOut(true);
                void signOut().finally(() => setSigningOut(false));
              }}
            >
              Sign out
            </Button>
          )}
        </>
      }
    >
      {/* Where the crumb used to sit: a wide search field, not a small trigger button, so the
          space it freed up reads as "the search lives here" rather than as slack. */}
      <button
        type="button"
        className="palette-trigger palette-trigger-wide"
        onClick={onOpenPalette}
        aria-label="Search or run a command"
        data-testid="palette-trigger"
      >
        <Search size={13} aria-hidden />
        <span className="palette-trigger-label">Search or run a command…</span>
        <Kbd>{modKey("K")}</Kbd>
      </button>
    </ContextBar>
  );
}

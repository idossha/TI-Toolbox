import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Outlet, useLocation } from "react-router-dom";
import { getProject, onUnauthorized } from "../api/client";
import { isElectron } from "../env";
import { NavRail } from "./NavRail";
import { AppContextBar } from "./AppContextBar";
import { CommandPalette } from "./CommandPalette";
import { KeyboardSheet } from "./KeyboardSheet";
import { QuickNotesHost } from "./QuickNotesHost";
import { JobsRail, RUNNING_STATES } from "./jobs-rail/JobsRail";
import { useJobsStream } from "./jobs/useJobsStream";
import { useGlobalShortcuts } from "./keyboard";
import { useConnection } from "./connection";
import { clearPageSession } from "./pageSession";
import { RetainedPages } from "./RetainedPages";
import type { ResolvedPage } from "./registry";
import { useSubjectSpine } from "./subjectSpine";
import { useSubjectContext } from "./subjectContext";
import { Button } from "../ui/Button";
import type { JobState } from "../ui/Status";
import { resetJobsUi } from "./jobs-rail/store";

function Unauthenticated() {
  return (
    <div className="unauthenticated">
      <h2 className="text-section">Not authenticated</h2>
      <p className="text-body" style={{ color: "var(--ink-2)" }}>
        The server rejected the session.{" "}
        {isElectron ? "Return to the launcher and connect again with a valid token." : "Open the tokenized URL printed by the server."}
      </p>
      {isElectron && (
        <Button variant="primary" onClick={() => void window.tit!.connect()}>
          Back to launcher
        </Button>
      )}
    </div>
  );
}


export function Shell({ pages }: { pages: readonly ResolvedPage[] }) {
  const [jobsRailExpanded, setJobsRailExpanded] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [keyboardSheetOpen, setKeyboardSheetOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [unauthenticated, setUnauthenticated] = useState(false);
  const [sessionEpoch, setSessionEpoch] = useState(0);
  const queryClient = useQueryClient();
  const projectQuery = useQuery({ queryKey: ["project"], queryFn: () => getProject() });
  const location = useLocation();
  /** `/results` -> `results`; the catch-all redirect means this is always a real page id. */
  const activePageId = location.pathname.replace(/^\//, "").split("/")[0] ?? "";
  const { jobs } = useJobsStream();
  const connection = useConnection(unauthenticated);
  const projectKey = projectQuery.data
    ? [projectQuery.data.name, projectQuery.data.host_path ?? "", projectQuery.data.container_path].join("\u0000")
    : null;
  const lastProjectKey = useRef<string | null>(null);

  useSubjectSpine();
  const activeSubjectId = useSubjectContext((st) => st.subjectId);

  useEffect(
    () =>
      onUnauthorized(() => {
        setUnauthenticated(true);
        void queryClient.cancelQueries();
      }),
    [queryClient],
  );

  // Page-session state is a draft of this project, not a global preference. If Electron reconnects
  // the renderer to a different project without restarting it, discard form/page memory and remount
  // the page subtree so local `usePageSession` mirrors cannot write the previous project's draft
  // back into the now-empty bag. Jobs filters/selection live in their own app store, so reset them
  // at the same boundary. First hydration is not a switch.
  useEffect(() => {
    if (!projectKey) return;
    if (lastProjectKey.current === null) {
      lastProjectKey.current = projectKey;
      return;
    }
    if (lastProjectKey.current === projectKey) return;
    lastProjectKey.current = projectKey;
    clearPageSession();
    resetJobsUi();
    setSessionEpoch((epoch) => epoch + 1);
  }, [projectKey]);

  const toggleJobs = useCallback(() => setJobsRailExpanded((e) => !e), []);
  useGlobalShortcuts({
    toggleJobs,
    openPalette: () => setPaletteOpen(true),
    // U11 removed the context bar's subject switcher; the palette's own Subjects section is now
    // the one place ⌘P and ⌘K both land, so the two shortcuts share a handler rather than one of
    // them opening a control that no longer exists.
    openSubjectSwitcher: () => setPaletteOpen(true),
    toggleQuickNotes: () => setNotesOpen((o) => !o),
    openKeyboardSheet: () => setKeyboardSheetOpen(true),
  });

  const runningCount = useMemo(
    () => Object.values(jobs).filter((j) => RUNNING_STATES.includes(j.state as JobState)).length,
    [jobs],
  );

  const paletteActions = useMemo(
    () => ({
      openJobs: () => setJobsRailExpanded(true),
      openKeyboardSheet: () => setKeyboardSheetOpen(true),
      openQuickNotes: () => setNotesOpen(true),
    }),
    [],
  );

  return (
    <div className="shell">
      <NavRail />
      <div className="shell-main">
        <AppContextBar
          connection={connection}
          runningJobs={runningCount}
          onToggleJobsRail={toggleJobs}
          onOpenPalette={() => setPaletteOpen(true)}
        />
        {/* DESIGN.md §4.4, "disconnected": a strip under the context bar, forms stay editable, and
            the reason is the text — not a toast that takes the explanation with it. */}
        {connection.degraded && connection.reason && (
          <div className="connection-strip" role="status" data-testid="connection-strip">
            {connection.reason}
          </div>
        )}
        {/* `data-page` is the app's assertable statement of "which screen is on". The router is a
            MemoryRouter (`App.tsx`), so the document URL never moves and a test cannot read the
            route from it; and DESIGN.md v2 removed the page headings a test used to key on. One
            attribute, set where the page is actually mounted, is what both the E2E suite and an
            agent reviewing a screen read instead — a number/DOM fact, not a picture.
            `data-subject` does the same for the subject spine, which is likewise URL-synced into
            a URL nothing outside the renderer can see. */}
        <div
          className="shell-content"
          data-testid="shell-content"
          data-page={activePageId ?? ""}
          data-subject={activeSubjectId ?? ""}
        >
          {unauthenticated ? <Unauthenticated /> : <RetainedPages key={sessionEpoch} pages={pages} />}
          {/* Child routes validate navigation and own the catch-all redirect; pages live above. */}
          <Outlet />
        </div>
        <JobsRail expanded={jobsRailExpanded} onExpandedChange={setJobsRailExpanded} />
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} actions={paletteActions} />
      <KeyboardSheet open={keyboardSheetOpen} onOpenChange={setKeyboardSheetOpen} />
      <QuickNotesHost open={notesOpen} onOpenChange={setNotesOpen} />
    </div>
  );
}

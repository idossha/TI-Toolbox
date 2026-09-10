import { useMemo } from "react";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";
import { useEnabledPages } from "./registry";
import { buildCommands, groupCommands, usePageCommandList } from "./commands";
import { useSubject } from "./subjectContext";
import { useJobsStream } from "./jobs/useJobsStream";
import { RUNNING_STATES } from "./jobs-rail/JobsRail";
import { useThemeStore } from "./theme/store";
import { modKey, modShiftKey } from "./keyboard";
import type { JobState } from "../ui/Status";

/**
 * ⌘K (plan §1). Five sections: what the page on screen can do, where to go, who to look at, what
 * is running, and the app's own verbs. The theme control lives here rather than in the context
 * bar — a preference set twice a year does not deserve permanent chrome.
 */
export interface PaletteActions {
  openJobs: () => void;
  openKeyboardSheet: () => void;
  openQuickNotes: () => void;
}

export function CommandPalette({
  open,
  onOpenChange,
  actions,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actions: PaletteActions;
}) {
  const navigate = useNavigate();
  const pages = useEnabledPages();
  const pageCommands = usePageCommandList();
  const { subjects, setId } = useSubject();
  const { jobs } = useJobsStream();
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  const running = useMemo(
    () => Object.values(jobs).filter((j) => RUNNING_STATES.includes(j.state as JobState)),
    [jobs],
  );

  const sections = useMemo(
    () =>
      groupCommands(
        buildCommands({
          pageCommands,
          pages,
          subjects,
          runningJobs: running,
          theme,
          modKey,
          modShiftKey,
          navigate: (path) => navigate(path),
          setSubject: setId,
          setTheme,
          openJobs: actions.openJobs,
          openKeyboardSheet: actions.openKeyboardSheet,
          openQuickNotes: actions.openQuickNotes,
        }),
      ),
    [pageCommands, pages, subjects, running, theme, navigate, setId, setTheme, actions],
  );

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      className="palette palette-dialog"
      overlayClassName="overlay"
      contentClassName="palette-dialog-content"
    >
      <Command.Input className="palette-input" placeholder="Search or run a command…" data-testid="palette-input" />
      <Command.List className="palette-list">
        <Command.Empty className="palette-empty">Nothing matches.</Command.Empty>
        {sections.map((group) => (
          <Command.Group key={group.section} heading={group.section} className="palette-group">
            {group.items.map((c) => (
              <Command.Item
                key={c.id}
                value={`${c.label} ${c.keywords ?? ""}`}
                className="palette-item"
                onSelect={() => {
                  onOpenChange(false);
                  c.run();
                }}
              >
                <span className="palette-item-label">{c.label}</span>
                {c.hint && <span className="palette-item-hint">{c.hint}</span>}
              </Command.Item>
            ))}
          </Command.Group>
        ))}
      </Command.List>
    </Command.Dialog>
  );
}

/**
 * The command palette's model (plan §1, DESIGN.md §2). Nav rows carry no shortcut badges any
 * more; ⌘K is where a verb is found and where a shortcut is learned.
 *
 * Two kinds of entry meet here:
 *   - what the shell always knows (pages, subjects, running jobs, app-level actions), assembled in
 *     `CommandPalette.tsx`;
 *   - what only the page on screen knows ("Run simulation", "Open in viewer"), registered through
 *     `usePageCommands` while that page is active.
 */
import { useEffect, useId } from "react";
import { create } from "zustand";
import type { ThemeSetting } from "./theme/store";
import { usePageActive } from "./pageActivity";
import { pagePath } from "./registry";

export type CommandSection = "Page" | "Pages" | "Subjects" | "Jobs" | "Actions";

export interface Command {
  /** Stable within its section; used as the React key and the cmdk value. */
  id: string;
  label: string;
  section: CommandSection;
  /** Right-aligned: a shortcut, a state ("running"), a path — never a second sentence. */
  hint?: string;
  /** Extra words the fuzzy match should see but the row should not show. */
  keywords?: string;
  run: () => void;
}

interface PageCommandState {
  /** Keyed by the registering component instance, so two pages can never clobber each other. */
  byOwner: Record<string, Command[]>;
  register: (owner: string, commands: Command[]) => void;
  unregister: (owner: string) => void;
}

export const usePageCommandStore = create<PageCommandState>((set) => ({
  byOwner: {},
  register: (owner, commands) => set((s) => ({ byOwner: { ...s.byOwner, [owner]: commands } })),
  unregister: (owner) =>
    set((s) => {
      if (!(owner in s.byOwner)) return s;
      const next = { ...s.byOwner };
      delete next[owner];
      return { byOwner: next };
    }),
}));

/**
 * Registers page-level commands while the calling page is active.
 *
 * Pass a stable array (a `useMemo` over the things the commands close over). The commands are
 * replaced wholesale on every change, so a stale closure is impossible; an unstable array just
 * means a needless store write per render.
 */
export function usePageCommands(commands: Command[]): void {
  const active = usePageActive();
  const owner = useId();
  const register = usePageCommandStore((s) => s.register);
  const unregister = usePageCommandStore((s) => s.unregister);
  useEffect(() => {
    if (!active) return;
    register(owner, commands);
    return () => unregister(owner);
  }, [active, owner, commands, register, unregister]);
}

/** Everything currently registered by the page on screen, in registration order. */
export function usePageCommandList(): Command[] {
  const byOwner = usePageCommandStore((s) => s.byOwner);
  return Object.values(byOwner).flat();
}

// ---------------------------------------------------------------------------
// The shell's own entries
// ---------------------------------------------------------------------------

/** The three theme settings, in the order the palette lists them. */
export const THEME_ORDER: ThemeSetting[] = ["system", "light", "dark"];

/** The order sections appear in. "Page" first: what you can do here beats where you can go. */
export const SECTION_ORDER: CommandSection[] = ["Page", "Pages", "Subjects", "Jobs", "Actions"];

/** Just enough of a `ResolvedPage` to build a row — every enabled page, hidden ones included. */
export interface CommandPage {
  id: string;
  title: string;
  purpose: string;
  shortcut?: string;
  /** Rail sub-items (`PageDef.subNav`); each becomes its own row. */
  subNav?: readonly { id: string; title: string }[];
}

/** Just enough of a job. */
export interface CommandJob {
  id: string;
  kind: string;
  subject_ids: string[];
  state: string;
}

export interface CommandContext {
  /** Registered by the page on screen through `usePageCommands`. */
  pageCommands: Command[];
  pages: CommandPage[];
  subjects: { id: string }[];
  runningJobs: CommandJob[];
  theme: ThemeSetting;
  /** How a shortcut is spelled on this platform ("⌘K" / "Ctrl+K"). */
  modKey: (key: string) => string;
  modShiftKey: (key: string) => string;
  navigate: (path: string) => void;
  setSubject: (id: string) => void;
  setTheme: (theme: ThemeSetting) => void;
  openJobs: () => void;
  openKeyboardSheet: () => void;
  openQuickNotes: () => void;
}

/**
 * Everything ⌘K can reach, in one pure function so the list is testable without a DOM: page
 * commands first, then every enabled page (hidden and dev pages included — palette-reachable is
 * exactly what "hidden" means), the project's subjects, what is running, and the app's own verbs.
 */
export function buildCommands(ctx: CommandContext): Command[] {
  const list: Command[] = [...ctx.pageCommands];

  for (const page of ctx.pages) {
    list.push({
      id: `page:${page.id}`,
      label: page.title,
      section: "Pages",
      hint: page.shortcut ? ctx.modKey(page.shortcut) : undefined,
      keywords: page.purpose,
      run: () => ctx.navigate(pagePath(page)),
    });
    // A page's rail sub-items are rows here too. Below 1440 the rail draws no sub-items at all
    // (there is no room to indent one), so the palette is the only place some people can reach
    // the Viewer's Tetravox sub-page by name -- it is not a convenience row.
    for (const sub of page.subNav ?? []) {
      list.push({
        id: `page:${page.id}:${sub.id}`,
        label: `${page.title} · ${sub.title}`,
        section: "Pages",
        keywords: page.purpose,
        run: () => ctx.navigate(`/${page.id}/${sub.id}`),
      });
    }
  }

  for (const s of ctx.subjects) {
    list.push({
      id: `subject:${s.id}`,
      label: s.id,
      section: "Subjects",
      hint: "switch subject",
      run: () => ctx.setSubject(s.id),
    });
  }

  for (const job of ctx.runningJobs) {
    list.push({
      id: `job:${job.id}`,
      label: `${job.kind} · ${job.subject_ids.join(", ") || "—"}`,
      section: "Jobs",
      hint: job.state,
      keywords: job.id,
      run: ctx.openJobs,
    });
  }

  for (const t of THEME_ORDER) {
    list.push({
      id: `theme:${t}`,
      label: `Theme: ${t}`,
      section: "Actions",
      hint: t === ctx.theme ? "current" : undefined,
      keywords: "appearance dark light colour color",
      run: () => ctx.setTheme(t),
    });
  }

  list.push(
    { id: "action:settings", label: "Open settings", section: "Actions", hint: ctx.modKey(","), run: () => ctx.navigate("/settings") },
    { id: "action:help", label: "Open help", section: "Actions", run: () => ctx.navigate("/help") },
    { id: "action:keys", label: "Show keyboard shortcuts", section: "Actions", hint: "?", run: ctx.openKeyboardSheet },
    { id: "action:notes", label: "Open quick notes", section: "Actions", hint: ctx.modShiftKey("N"), run: ctx.openQuickNotes },
    { id: "action:jobs", label: "Toggle the jobs panel", section: "Actions", hint: ctx.modKey("J"), run: ctx.openJobs },
  );

  return list;
}

/** The same list, grouped for rendering; empty sections are dropped. */
export function groupCommands(commands: Command[]): { section: CommandSection; items: Command[] }[] {
  return SECTION_ORDER.map((section) => ({ section, items: commands.filter((c) => c.section === section) })).filter(
    (g) => g.items.length > 0,
  );
}

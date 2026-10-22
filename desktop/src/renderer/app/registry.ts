import { isProjectHome } from "../env";
/**
 * Pages are discovered, never listed by hand: every `pages/<name>/index.tsx` default-exports a
 * `PageDef`, and `import.meta.glob` finds them at build time. Adding a screen means adding a
 * directory under `pages/` — nothing here changes.
 *
 * v3 (program U7, DESIGN.md §9) replaces the v2 grouping with **one flat, workflow-ordered rail**:
 * `NAV_ORDER` is the rail and the ⌘-numbers, `PINNED_ORDER` is the pair at the bottom, and a page
 * in neither is palette-only. A `PageDef`'s own `navGroup` and `shortcut` no longer decide where it
 * lands or which key reaches it. The rail defines the workflow order here.
 */
import type { LucideIcon } from "lucide-react";
import type { ComponentType } from "react";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSettings } from "../pages/settings/api";

/** The two sections the v3 rail draws: the workflow rows, and the pinned pair below the spacer. */
export type NavSectionId = "workflow" | "pinned";

export interface PageDef {
  /** Route id, also the nav rail's stable key. Convention: the pages/<id> directory name. */
  id: string;
  title: string;
  /** One sentence. v2 hides page headers, so this is palette/tooltip copy, not a printed line. */
  purpose: string;
  /**
   * Legacy field. v3 derives the rail from `NAV_ORDER`, not from this — it survives because
   * `settings.panels` still keys panel pages off `navGroup === "panels"`.
   */
  navGroup: string;
  /** Legacy field; the rail's order is `NAV_ORDER`. Kept so no page directory needs an edit. */
  order: number;
  icon: LucideIcon;
  /**
   * Ignored on a `PageDef`: the ⌘-number is the page's index in `NAV_ORDER` (§9), and `resolvePage`
   * overwrites this with it. A page that still sets one must agree with that map
   * (`tests/unit/page-shortcut-agreement.test.ts`).
   */
  shortcut?: string;
  Component: ComponentType;
  /** false hides the page from the nav and its route (e.g. an in-progress screen). */
  enabled: boolean;

  // ---- optional, all with defaults so no page directory needs an edit ----
  /** Reachable from the command palette and by route, but not shown in the rail. */
  hidden?: boolean;
  /**
   * Forces the 56px icon rail at every width. Below 1440 every page gets it anyway (§9); this is
   * for a page whose content needs the 160px even where labels would otherwise fit.
   */
  railMode?: "icons";
}

/** A page with every v3 default resolved. What the shell, the palette and the tests read. */
export interface ResolvedPage extends PageDef {
  section: NavSectionId;
  /** The rail slot this page occupies, or `null` for palette-only. */
  slot: string | null;
  hidden: boolean;
}

/**
 * **The rail, in order** (DESIGN.md §9, program U7). Flat, workflow-ordered, no group headers and
 * no subject-id label: a subject is chosen in the context bar, and printing "101" as a group
 * heading told the user a page belonged to a subject when it did not.
 *
 * The index in this array *is* the ⌘-number, so the nav, the palette and the `?` sheet cannot
 * disagree about which key jumps where — a `PageDef.shortcut` is ignored for a page in the rail.
 */
export const NAV_ORDER = [
  "overview",
  "preprocess",
  "optimizer",
  "simulator",
  "analyzer",
  "viewer",
  "results",
  "notebooks",
  "jobs",
] as const;

/**
 * Pinned to the bottom below a spacer, in this order: **Assistant · System · Settings · Help**
 * (Assistant added 2026-10-07: the user's own agent, ARCHITECTURE §6).
 *
 * None of the three takes a rail digit — the workflow digits belong to the workflow rows (see
 * `shortcutForSlot`). Settings keeps ⌘, and Help the `?` sheet; System has no chord at all, which
 * is right for a screen you open when something looks wrong rather than one you jump to mid-task.
 *
 * System sits *above* Settings on the maintainer's instruction (2026-09-07: *"place it above the
 * Settings over there in the bottom left corner of the UI"*), and the order reads correctly for
 * what these are: the machine, then this install's preferences, then the manual.
 */
export const PINNED_ORDER = ["assistant", "system", "settings", "help"] as const;

/** ⌘, opens Settings. The rail's digits are ⌘0–⌘9 and the workflow digits belong to workflow rows, so this
 *  alias is now Settings' only chord, and the `?` sheet spells it. */
export const SHORTCUT_ALIASES: Record<string, string> = { ",": "settings" };

const modules = import.meta.glob("../pages/*/index.tsx", { eager: true }) as Record<string, { default: PageDef }>;

/**
 * Which rail slot a page occupies, or `null` for "palette-only".
 *
 * `null` is the mechanism §9's "there is no Panels group and no Tools group" is implemented with
 * for `dev`: still routable and still in ⌘K, but never a row in the rail, in any state. (`system`
 * was palette-only until 2026-09-07, when the full-height system monitor came back as a pinned row
 * above Settings; the jobs panel's Host tab stays as the glance you take without leaving the page
 * you are on.) A `navGroup: "panels"` page is different — §9 calls it "a *mode* inside a page,
 * toggled by Settings ▸ Optional tools", which needs a rail row *while the user has it turned on*:
 * it gets the `panel-<id>` slot below, so whether it shows follows `PageDef.enabled` (§ live gating
 * below) rather than being permanently excluded like a palette-only page.
 */
export function navSlotOf(id: string): string | null {
  if ((NAV_ORDER as readonly string[]).includes(id)) return id;
  if ((PINNED_ORDER as readonly string[]).includes(id)) return id;
  // DESIGN.md §9 / program U7: an optional panel is a mode toggled in Settings, but it still needs
  // *somewhere* in the rail when the user has turned it on. `panel-<id>` (the convention every
  // `pages/panels/*` module follows) gets its own slot, appended after the nine workflow rows, so
  // it is gated by `PageDef.enabled` like any other page instead of being permanently hidden.
  if (id.startsWith("panel-")) return id;
  return null;
}

/**
 * The ⌘-number for a slot: the rail counts **from ⌘0**, so the nine workflow rows are ⌘0 Overview
 * through ⌘7 Notebooks and ⌘8 Jobs, and nothing else has a number (⌘9 is free).
 *
 * A keyboard has ten digits, so every row has one — but only because the count starts at zero
 * (maintainer, 2026-09-06: *"start from 0 the rail digit and finish at 9"*, when the rail had ten
 * rows). Counting from 1 spends ⌘0 on Settings, which is not a rail row at all, and then leaves a
 * tenth row with no key: earlier revisions printed "⌘10", a chord no keyboard can send, and then
 * dropped it, which cost Jobs its shortcut. Settings keeps ⌘, (`SHORTCUT_ALIASES`) and Help the `?`
 * sheet; neither is in `NAV_ORDER`, so neither takes a digit from a workflow row.
 *
 * An eleventh row would again have no number. That is a real limit of ten digits, not of this
 * function, and it is `NAV_ORDER`'s job to stay within it.
 */
export function shortcutForSlot(slot: string | null): string | undefined {
  if (slot === null) return undefined;
  const i = (NAV_ORDER as readonly string[]).indexOf(slot);
  if (i >= 0) return i < 10 ? String(i) : undefined;
  return undefined;
}

export function resolvePage(page: PageDef): ResolvedPage {
  const slot = navSlotOf(page.id);
  const section: NavSectionId = slot !== null && (PINNED_ORDER as readonly string[]).includes(slot) ? "pinned" : "workflow";
  const coreIndex = slot === null ? -1 : (NAV_ORDER as readonly string[]).indexOf(slot);
  const railIndex =
    slot === null
      ? Number.MAX_SAFE_INTEGER
      : section === "pinned"
        ? (PINNED_ORDER as readonly string[]).indexOf(slot)
        : coreIndex >= 0
          ? coreIndex
          : // A panel slot (its own id, e.g. "panel-source") isn't one of the nine workflow rows —
            // it belongs at the end of the workflow section (U7's "only when enabled"), ordered
            // among other panels by the page's own `order` field rather than a second list to keep
            // in sync with `pages/panels/*`.
            NAV_ORDER.length + (page.order ?? 0);
  return {
    ...page,
    slot,
    shortcut: shortcutForSlot(slot),
    order: railIndex,
    section,
    // A page with no slot is palette-only. `hidden: false` on such a page cannot put it back in
    // the rail: the rail's contents are NAV_ORDER, not a vote.
    hidden: slot === null ? true : (page.hidden ?? false),
    railMode: page.railMode,
  };
}

/** The route a page's rail row, its ⌘-number and its palette entry all go to. */
export function pagePath(page: Pick<PageDef, "id">): string {
  return `/${page.id}`;
}

/** Every discovered page, enabled or not, v3 defaults resolved, sorted into rail order. */
export const pages: ResolvedPage[] = Object.values(modules)
  .map((m) => resolvePage(m.default))
  .sort((a, b) => a.order - b.order);

export const enabledPages: ResolvedPage[] = pages.filter((p) => p.enabled);

export function pageById(id: string): ResolvedPage | undefined {
  return pages.find((p) => p.id === id);
}

/** The page the app lands on: the first row of the rail (R1 — Overview). */
export function landingPage(list: ResolvedPage[] = enabledPages): ResolvedPage | undefined {
  return list.find((p) => p.section === "workflow" && !p.hidden) ?? list[0];
}

/**
 * A panel `PageDef.id` is always `panel-<id>` (`pages/panels/_shared.ts`'s `PanelId`); `settings.
 * panels` (the server field, plan §3) holds the bare `<id>`.
 */
function isPanelPageEnabled(page: PageDef, enabledPanelIds: string[]): boolean {
  return page.navGroup !== "panels" || enabledPanelIds.includes(page.id.replace(/^panel-/, ""));
}

/**
 * Live view of `enabledPages`: every page keeps its static `PageDef.enabled` default, except a
 * "panels" page, whose enabled state is read from `settings.panels` instead — through the exact
 * same React Query cache entry (`queryKey: ["settings"]`, `pages/settings/api.ts`'s `getSettings`)
 * that `pages/settings` itself reads and writes. That's what makes this "live" with no code in
 * `pages/settings` to change: when Settings saves, it calls `queryClient.setQueryData(["settings"],
 * saved)`, and every other `useQuery(["settings"])` observer — this hook included — re-renders
 * with the new value immediately, no reload. Falls back to `enabledPages` (each panel's own static
 * default, itself seeded from a `localStorage` mirror) until the first `/api/settings` response.
 */
export function useEnabledPages(): ResolvedPage[] {
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: getSettings, enabled: !isProjectHome });
  const panelIds = settingsQuery.data?.panels;
  return useMemo(() => {
    if (isProjectHome) return enabledPages;
    if (!panelIds) return enabledPages;
    return pages.filter((p) => isPanelPageEnabled(p, panelIds));
  }, [panelIds]);
}

export interface NavSection {
  id: NavSectionId;
  /** Pinned sections sit at the bottom of the rail, below a spacer. */
  pinned: boolean;
  pages: ResolvedPage[];
}

/**
 * The rail's two sections — the workflow rows and the pinned pair — with palette-only pages
 * removed. **Neither carries a label**: U7 deletes the group headers, and the one that printed a
 * subject id with them.
 */
export function navSections(list: ResolvedPage[] = enabledPages): NavSection[] {
  return (["workflow", "pinned"] as NavSectionId[])
    .map((id) => ({
      id,
      pinned: id === "pinned",
      pages: list.filter((p) => p.section === id && !p.hidden).sort((a, b) => a.order - b.order),
    }))
    .filter((s) => s.pages.length > 0);
}

/** `navSections()` over the live `useEnabledPages()` list — see its doc comment. */
export function useNavSections(): NavSection[] {
  const list = useEnabledPages();
  return useMemo(() => navSections(list), [list]);
}

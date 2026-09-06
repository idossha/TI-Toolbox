/**
 * Pages are discovered, never listed by hand: every `pages/<name>/index.tsx` default-exports a
 * `PageDef`, and `import.meta.glob` finds them at build time. Adding a screen means adding a
 * directory under `pages/` — nothing here changes.
 *
 * v3 (program U7, DESIGN.md §9) replaces the v2 grouping with **one flat, workflow-ordered rail**:
 * `NAV_ORDER` is the rail and the ⌘-numbers, `PINNED_ORDER` is the pair at the bottom, and a page
 * in neither is palette-only. A `PageDef`'s own `navGroup` and `shortcut` no longer decide where it
 * lands or which key reaches it — a page directory said "pipeline" and got two nav entries copied
 * from the PyQt tab strip; the rail says what the workflow is, once, here.
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
  /** Legacy field; the ⌘-number is the page's index in `NAV_ORDER` (§9). */
  shortcut?: string;
  Component: ComponentType;
  /** false hides the page from the nav and its route (e.g. an in-progress screen). */
  enabled: boolean;

  // ---- optional, all with defaults so no page directory needs an edit ----
  /** `full-bleed` pages own every pixel of the shell's content box (the Viewer). */
  layout?: "standard" | "full-bleed";
  /** Does the context bar's subject switcher scope this page? */
  subjectScoped?: boolean;
  /** Reachable from the command palette and by route, but not shown in the rail. */
  hidden?: boolean;
  /** This page mounts the Tetravox canvas. */
  viewer?: boolean;
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
  subjectScoped: boolean;
  viewer: boolean;
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
  "simulator",
  "optimizer",
  "analyzer",
  "pipeline",
  "results",
  "viewer",
  "jobs",
] as const;

/** Pinned to the bottom below a spacer. Settings takes ⌘0 (⌘, alias); Help is the `?` sheet only. */
export const PINNED_ORDER = ["settings", "help"] as const;

/** ⌘, still opens Settings — one preference, two ways in, both spelled in the `?` sheet. */
export const SHORTCUT_ALIASES: Record<string, string> = { ",": "settings" };

/**
 * A legacy page id that stands in for a v3 slot **until the page that owns the slot exists**.
 *
 * `pages/optimizer` is lane B3's to create (one page, Method ⟨Flex │ Ex │ mEx⟩). Until it lands,
 * `optimizer-flex` occupies the Optimizer slot so the rail is already the v3 rail — eight rows,
 * ⌘4 bound — and `optimizer-ex`, which has no slot at all, drops out of the rail into the palette.
 * The day `pages/optimizer/index.tsx` appears this table stops applying by itself: the stand-in
 * only wins while the real id is undiscovered.
 */
const LEGACY_SLOT: Record<string, string> = { "optimizer-flex": "optimizer" };

const modules = import.meta.glob("../pages/*/index.tsx", { eager: true }) as Record<string, { default: PageDef }>;

/** Every page id `import.meta.glob` actually found — what makes `LEGACY_SLOT` self-retiring. */
const DISCOVERED: ReadonlySet<string> = new Set(Object.values(modules).map((m) => m.default.id));

/** These pages are read as "…for the current subject"; nothing in the rail says so any more. */
const SUBJECT_SCOPED = new Set<string>(["preprocess", "simulator", "optimizer", "analyzer", "results", "viewer"]);

/**
 * Which rail slot a page occupies, or `null` for "palette-only".
 *
 * `null` is the mechanism §9's "there is no Panels group and no Tools group" is implemented with
 * for `system`, `optimizer-ex` and `dev`: all still routable and all still in ⌘K, but never a row
 * in the rail, in any state. A `navGroup: "panels"` page is different — §9 calls it "a *mode*
 * inside a page, toggled by Settings ▸ Optional tools", which needs a rail row *while the user has
 * it turned on*: it gets the `panel-<id>` slot below, so whether it shows follows `PageDef.enabled`
 * (§ live gating below) rather than being permanently excluded like the three palette-only ids.
 */
export function navSlotOf(id: string, known: ReadonlySet<string> = DISCOVERED): string | null {
  if ((NAV_ORDER as readonly string[]).includes(id)) return id;
  if ((PINNED_ORDER as readonly string[]).includes(id)) return id;
  const slot = LEGACY_SLOT[id];
  if (slot !== undefined && !known.has(slot)) return slot;
  // DESIGN.md §9 / program U7: an optional panel is a mode toggled in Settings, not a page copied
  // from the PyQt tab strip — but it still needs *somewhere* in the rail when the user has turned
  // it on. `panel-<id>` (the convention every `pages/panels/*` module follows, enforced by
  // `resolvePage`'s doc comment) gets its own slot, appended after the eight workflow rows, so it
  // is gated by `PageDef.enabled` like any other page instead of being permanently hidden.
  if (id.startsWith("panel-")) return id;
  return null;
}

/**
 * The ⌘-number for a slot: 1..N across the rail, then the next free digit for Settings, none for
 * Help.
 *
 * Settings used to be hard-coded to ⌘9 because the rail was exactly eight rows. Adding the ninth
 * (Pipeline, ⌘6) would have put two pages on ⌘9 — a shortcut that opens whichever page the lookup
 * happened to find first. Deriving it from `NAV_ORDER.length` instead means the rail can grow
 * without ever silently colliding, and Settings keeps its ⌘, alias either way.
 */
export function shortcutForSlot(slot: string | null): string | undefined {
  if (slot === null) return undefined;
  const i = (NAV_ORDER as readonly string[]).indexOf(slot);
  if (i >= 0) return String(i + 1);
  if (slot === "settings") return NAV_ORDER.length < 9 ? "9" : "0";
  return undefined;
}

export function resolvePage(page: PageDef, known: ReadonlySet<string> = DISCOVERED): ResolvedPage {
  const slot = navSlotOf(page.id, known);
  const section: NavSectionId = slot !== null && (PINNED_ORDER as readonly string[]).includes(slot) ? "pinned" : "workflow";
  const coreIndex = slot === null ? -1 : (NAV_ORDER as readonly string[]).indexOf(slot);
  const railIndex =
    slot === null
      ? Number.MAX_SAFE_INTEGER
      : section === "pinned"
        ? (PINNED_ORDER as readonly string[]).indexOf(slot)
        : coreIndex >= 0
          ? coreIndex
          : // A panel slot (its own id, e.g. "panel-source") isn't one of the eight workflow rows —
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
    subjectScoped: page.subjectScoped ?? (slot !== null && SUBJECT_SCOPED.has(slot)),
    viewer: page.viewer ?? (page.id === "viewer" || page.id === "viewer-dev"),
    railMode: page.railMode,
  };
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
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const panelIds = settingsQuery.data?.panels;
  return useMemo(() => {
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

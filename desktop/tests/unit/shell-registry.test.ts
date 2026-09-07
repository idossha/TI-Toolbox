// @vitest-environment jsdom
/**
 * `app/registry.ts` is the whole information architecture: which rail slot a page occupies, which
 * number jumps to it, and whether it appears in the rail at all. v3 (program U7, DESIGN.md §9)
 * makes `NAV_ORDER` the single source of all three, so it is asserted twice over — once as a pure
 * function on synthetic `PageDef`s, and once against the real discovered pages.
 */
import { describe, expect, it } from "vitest";
import type { LucideIcon } from "lucide-react";

// jsdom ships no `matchMedia`; importing the registry pulls in every page module, one of which
// reaches uPlot through the `ui` barrel and calls it at module scope.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

const { resolvePage, navSections, landingPage, navSlotOf, shortcutForSlot, pagePath, NAV_ORDER, PINNED_ORDER, pages, enabledPages, pageById } =
  await import("../../src/renderer/app/registry");
type Registry = typeof import("../../src/renderer/app/registry");
type PageDef = Parameters<Registry["resolvePage"]>[0];

const icon = (() => null) as unknown as LucideIcon;

function def(over: Partial<PageDef> & Pick<PageDef, "id" | "navGroup">): PageDef {
  return {
    title: over.id,
    purpose: "",
    order: 10,
    icon,
    Component: () => null,
    enabled: true,
    ...over,
  } as PageDef;
}

describe("the rail is NAV_ORDER, not a page's own navGroup (U7)", () => {
  it("a page in NAV_ORDER takes that slot; one in neither list is palette-only", () => {
    expect(navSlotOf("simulator")).toBe("simulator");
    expect(navSlotOf("settings")).toBe("settings");
    expect(navSlotOf("system")).toBeNull();
    expect(navSlotOf("dev")).toBeNull();
  });

  it("a panel id (panel-<id>) gets its own slot, so it is gated by `enabled` and not palette-only", () => {
    // §9: an optional panel is a *mode*, toggled by Settings, not a page copied from the PyQt tab
    // strip — it still needs a rail row while the user has it turned on.
    expect(navSlotOf("panel-source")).toBe("panel-source");
    expect(navSlotOf("panel-subject-info")).toBe("panel-subject-info");
  });

  it("optimizer-flex stands in for the Optimizer slot ONLY until pages/optimizer exists", () => {
    // Lane B3 creates `pages/optimizer`. The stand-in retires itself the day it lands: the second
    // argument is the set of discovered ids, and the real page wins as soon as it is in there.
    expect(navSlotOf("optimizer-flex", new Set(["optimizer-flex"]))).toBe("optimizer");
    expect(navSlotOf("optimizer-flex", new Set(["optimizer-flex", "optimizer"]))).toBeNull();
    // optimizer-ex has no slot at all — two nav entries were a copy of the PyQt tab strip.
    expect(navSlotOf("optimizer-ex")).toBeNull();
  });

  it("a page with no slot is hidden from the rail whatever its PageDef says", () => {
    expect(resolvePage(def({ id: "system", navGroup: "system" })).hidden).toBe(true);
    expect(resolvePage(def({ id: "jobs", navGroup: "system" })).hidden).toBe(false);
  });

  it("a panel page is NOT force-hidden: it gets a real slot, gated by `enabled` like any other page", () => {
    // This is the fix for the cross-lane regression B6 found: `settings.panels` said "source" was
    // on, but the rail never showed it because every panel was force-`hidden` regardless. A panel
    // page's visibility is now `enabled` alone — exactly like every other page in the rail.
    const resolved = resolvePage(def({ id: "panel-x", navGroup: "panels", hidden: false, order: 100 }));
    expect(resolved.hidden).toBe(false);
    expect(resolved.slot).toBe("panel-x");
    expect(resolved.section).toBe("workflow");
    // Sorts after the eight workflow rows, however the panel's own `order` compares to theirs.
    expect(resolved.order).toBe(NAV_ORDER.length + 100);
  });

  it("subjectScoped follows the slot, not the group, and stays overridable", () => {
    expect(resolvePage(def({ id: "simulator", navGroup: "pipeline" })).subjectScoped).toBe(true);
    expect(resolvePage(def({ id: "overview", navGroup: "workspace" })).subjectScoped).toBe(false);
    expect(resolvePage(def({ id: "overview", navGroup: "workspace", subjectScoped: true })).subjectScoped).toBe(true);
  });
});

describe("the shortcut map (DESIGN.md §9: ⌘1 Overview … ⌘9 Jobs, ⌘0 Settings)", () => {
  const shortcutOf = (id: string) => pageById(id)?.shortcut;

  it("the ⌘-number IS the index in NAV_ORDER, so nav/palette/sheet cannot disagree", () => {
    // Only the first nine: there are nine digits, and ⌘0 is Settings.
    NAV_ORDER.forEach((slot, i) =>
      expect(shortcutForSlot(slot)).toBe(i < 9 ? String(i + 1) : undefined),
    );
    // Settings takes the first digit the rail does not: ⌘9 while the rail was eight rows, ⌘0 now
    // that Pipeline made it nine. Two pages on one number would be a shortcut that opens
    // whichever the lookup found first.
    expect(shortcutForSlot("settings")).toBe(NAV_ORDER.length < 9 ? "9" : "0");
    expect(shortcutForSlot("help")).toBeUndefined();
    expect(shortcutForSlot(null)).toBeUndefined();
  });

  it("assigns them to today's page ids, with optimizer-flex holding ⌘4", () => {
    expect(shortcutOf("overview")).toBe("1");
    expect(shortcutOf("preprocess")).toBe("2");
    expect(shortcutOf("simulator")).toBe("3");
    expect(shortcutOf("optimizer") ?? shortcutOf("optimizer-flex")).toBe("4");
    expect(shortcutOf("analyzer")).toBe("5");
    expect(shortcutOf("pipeline")).toBe("6");
    expect(shortcutOf("notebooks")).toBe("7");
    expect(shortcutOf("results")).toBe("8");
    expect(shortcutOf("viewer")).toBe("9");
    // The tenth workflow row. Nine digits, and ⌘0 is Settings — so Jobs is
    // reached by ⌘K and by its route, and the rail says no number rather than
    // printing one that cannot be typed.
    expect(shortcutOf("jobs")).toBeUndefined();
    expect(shortcutOf("settings")).toBe("0");
  });

  it("gives no number to a page the rail does not carry, whatever its PageDef declared", () => {
    // Every one of these declares a `shortcut` in its own directory; the rail is the authority.
    expect(shortcutOf("optimizer-ex")).toBeUndefined();
    expect(shortcutOf("system")).toBeUndefined();
    expect(shortcutOf("help")).toBeUndefined();
  });

  it("never binds one number to two pages", () => {
    const taken = enabledPages.filter((p) => p.shortcut).map((p) => p.shortcut);
    expect(new Set(taken).size).toBe(taken.length);
  });
});

describe("the rail's two sections, over the real discovered pages", () => {
  const sections = navSections();
  const ids = (id: string) => sections.find((s) => s.id === id)?.pages.map((p) => p.id) ?? [];

  it("is flat: one workflow section and one pinned pair, and nothing else", () => {
    expect(sections.map((s) => s.id)).toEqual(["workflow", "pinned"]);
    expect(sections.find((s) => s.id === "pinned")?.pinned).toBe(true);
    expect(sections.filter((s) => s.pinned).length).toBe(1);
  });

  it("carries every workflow page in NAV_ORDER", () => {
    // `optimizer-flex` is standing in for `optimizer` until lane B3's page lands; the *slots* are
    // NAV_ORDER either way, which is the invariant worth asserting.
    expect(sections.find((s) => s.id === "workflow")!.pages.map((p) => p.slot)).toEqual([...NAV_ORDER]);
    expect(ids("pinned")).toEqual([...PINNED_ORDER]);
  });

  it("carries no group label at all — U7 deletes the headers and the subject id with them", () => {
    for (const section of sections) expect("label" in section).toBe(false);
  });

  it("keeps system and dev out of the rail but addressable for the palette", () => {
    const railIds = sections.flatMap((s) => s.pages.map((p) => p.id));
    for (const id of ["system", "dev", "optimizer-ex"]) expect(railIds).not.toContain(id);
  });

  it("panel pages are structurally rail-eligible (not `hidden`) — only `enabled` keeps a disabled one out", () => {
    // `navSections()` here reads the default `enabledPages`, i.e. each real panel module's static
    // `PageDef.enabled` (`isPanelEnabled`, a localStorage mirror empty in this test environment) —
    // so none show up in `railIds` today, but that must be because they are disabled, never because
    // they are architecturally excluded the way `system`/`dev`/`optimizer-ex` are.
    expect(pages.some((p) => p.navGroup === "panels")).toBe(true);
    expect(pages.filter((p) => p.navGroup === "panels").every((p) => !p.hidden)).toBe(true);
    expect(pages.filter((p) => p.navGroup === "panels").every((p) => p.slot?.startsWith("panel-"))).toBe(true);
  });

  it("an enabled panel lands at the end of the workflow section", () => {
    const list = [
      ...NAV_ORDER.map((id) => resolvePage(def({ id, navGroup: "pipeline" }))),
      resolvePage(def({ id: "panel-x", navGroup: "panels", order: 100 })),
    ];
    const workflowIds = navSections(list).find((s) => s.id === "workflow")!.pages.map((p) => p.id);
    expect(workflowIds).toEqual([...NAV_ORDER, "panel-x"]);
  });

  it("lands on the first row of the rail", () => {
    expect(landingPage()?.id).toBe("overview");
    expect(landingPage()?.section).toBe("workflow");
  });

  it("falls back to the first enabled page when no workflow page exists", () => {
    const only = [resolvePage(def({ id: "settings", navGroup: "system" }))];
    expect(landingPage(only)?.id).toBe("settings");
  });

  it("drops a section that has no visible page", () => {
    const list = [resolvePage(def({ id: "overview", navGroup: "project" }))];
    expect(navSections(list).map((s) => s.id)).toEqual(["workflow"]);
  });
});

describe("the viewer flag", () => {
  it("marks the pages that mount the canvas", () => {
    expect(pageById("viewer")?.viewer).toBe(true);
    expect(pageById("overview")?.viewer).toBe(false);
  });
});

/**
 * `PageDef.subNav` — the one exception to the flat rail (VE, 2026-09-06). The maintainer: *"In the
 * Viewer, the left menu has two subsections: the Menu, and below it the actual Viewer."*
 *
 * These assert the two properties the design rests on: a sub-item is **not** a page (it takes no
 * rail slot and no ⌘-number of its own), and a page that has sub-items has no route of its own —
 * its row, its number and its palette entry all land on the first one.
 */
describe("rail sub-items (PageDef.subNav)", () => {
  it("a sub-item takes no rail slot and no ⌘-number — it is a route inside one page", () => {
    // The rail is still exactly NAV_ORDER. A sub-item that had a slot would also have a number,
    // and ⌘9 would have moved off Jobs the day the Viewer grew a second row.
    expect(navSlotOf("menu")).toBeNull();
    expect(navSlotOf("tetravox")).toBeNull();
    expect(shortcutForSlot(navSlotOf("tetravox"))).toBeUndefined();
    // Relational, not a hard-coded digit. The rail grows -- the Notebooks row arrived while this
    // lane was open and moved every number after Pipeline, and this assertion was edited twice in
    // one evening to chase it. What must stay true is that the Viewer's number is its own
    // NAV_ORDER position, and that its two sub-items consumed none: a sub-item with a slot would
    // have pushed everything after the Viewer along by two.
    const order = NAV_ORDER as readonly string[];
    const viewerIndex = order.indexOf("viewer");
    expect(viewerIndex).toBeGreaterThanOrEqual(0);
    expect(pageById("viewer")?.shortcut).toBe(shortcutForSlot("viewer"));
    expect(pageById("viewer")?.shortcut).toBe(String(viewerIndex + 1));
    // The row after the Viewer is one slot after it, not three.
    expect(order.indexOf("jobs")).toBe(viewerIndex + 1);
  });

  it("the real Viewer page declares Menu then Tetravox, in that order", () => {
    // Order is load-bearing: the first is where the page's row, ⌘8 and a bare /viewer all land.
    expect(pageById("viewer")?.subNav?.map((s) => s.id)).toEqual(["menu", "tetravox"]);
    expect(pageById("viewer")?.subNav?.map((s) => s.title)).toEqual(["Menu", "Tetravox"]);
  });

  it("pagePath sends a page with sub-items to its first one, and any other page to itself", () => {
    expect(pagePath({ id: "viewer", subNav: [{ id: "menu", title: "Menu" }] })).toBe("/viewer/menu");
    expect(pagePath({ id: "viewer", subNav: [] })).toBe("/viewer");
    expect(pagePath({ id: "jobs" })).toBe("/jobs");
    // The real page, so the rail, ⌘8 and the palette cannot disagree with this test either.
    expect(pagePath(pageById("viewer")!)).toBe("/viewer/menu");
  });

  it("no page but the Viewer has sub-items — the rail is otherwise flat", () => {
    const withSubs = pages.filter((p) => (p.subNav?.length ?? 0) > 0).map((p) => p.id);
    expect(withSubs).toEqual(["viewer"]);
  });
});

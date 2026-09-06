/**
 * The one selection grammar's pure core (plan `v3-tetravox-selection-pipeline-plan.md` §1-C, C1).
 *
 * These are the rules a user learns once and then relies on everywhere — subjects, ex buckets, ROI
 * regions, montages, pair slots, jobs — so they are asserted here, without a DOM, rather than
 * re-observed through five component tests that could each drift.
 *
 * The rule with teeth is the **filter interplay**: a bulk button acts on what is visible and never
 * on what the filter is hiding. A "select all" that silently ticks forty rows the user cannot see
 * is how a batch of jobs gets queued by accident, and it is exactly what a naive implementation
 * does.
 */
import { describe, expect, it } from "vitest";
import {
  applyClick,
  filterItems,
  selectAllVisible,
  selectNoneVisible,
  selectionBadge,
  selectionNoun,
  selectionSummary,
  type SelectionItem,
} from "../../src/renderer/ui/SelectionList";

const ITEMS: SelectionItem[] = [
  { id: "a", label: "alpha" },
  { id: "b", label: "beta" },
  { id: "x", label: "excluded", disabled: true },
  { id: "c", label: "gamma" },
  { id: "d", label: "delta" },
];

describe("filtering", () => {
  it("is a case-insensitive substring of the id and the label, with no syntax", () => {
    expect(filterItems(ITEMS, "AL").map((i) => i.id)).toEqual(["a"]);
    expect(filterItems(ITEMS, "t").map((i) => i.id)).toEqual(["b", "d"]);
    expect(filterItems(ITEMS, "  ").map((i) => i.id)).toEqual(["a", "b", "x", "c", "d"]);
    expect(filterItems(ITEMS, "zzz")).toEqual([]);
  });

  it("matches an explicit `search` string when the label is a node", () => {
    const rows: SelectionItem[] = [{ id: "12", label: null, search: "L · bankssts" }];
    expect(filterItems(rows, "banks")).toHaveLength(1);
    expect(filterItems(rows, "12")).toHaveLength(0);
  });
});

describe("clicks", () => {
  it("a plain click selects exactly one row and parks the anchor there", () => {
    expect(applyClick({ value: ["a", "b"], anchor: "a" }, ITEMS, "c")).toEqual({ value: ["c"], anchor: "c" });
  });

  it("a plain click on the only selected row clears it", () => {
    expect(applyClick({ value: ["c"], anchor: "c" }, ITEMS, "c")).toEqual({ value: [], anchor: "c" });
  });

  it("⌘/Ctrl-click toggles one row and leaves the rest alone", () => {
    expect(applyClick({ value: ["a"], anchor: "a" }, ITEMS, "c", { toggle: true }).value).toEqual(["a", "c"]);
    expect(applyClick({ value: ["a", "c"], anchor: "a" }, ITEMS, "a", { toggle: true }).value).toEqual(["c"]);
  });

  it("⇧-click takes the inclusive range from the anchor, in either direction, and ADDS it", () => {
    const down = applyClick({ value: ["a"], anchor: "a" }, ITEMS, "c", { range: true });
    expect(down.value).toEqual(["a", "b", "c"]);
    // The anchor does not move, so a second ⇧-click re-ranges from the same place.
    expect(down.anchor).toBe("a");
    const up = applyClick({ value: ["d"], anchor: "d" }, ITEMS, "b", { range: true });
    expect(up.value).toEqual(["d", "b", "c"]);
  });

  it("a ⇧-click with no anchor yet behaves as a plain click", () => {
    expect(applyClick({ value: [], anchor: null }, ITEMS, "c", { range: true }).value).toEqual(["c"]);
  });

  it("a range steps OVER a hard-disabled row rather than selecting something that cannot run", () => {
    expect(applyClick({ value: [], anchor: "a" }, ITEMS, "d", { range: true }).value).toEqual(["a", "b", "c", "d"]);
  });

  it("a click on a hard-disabled row changes nothing at all", () => {
    const before = { value: ["a"], anchor: "a" };
    expect(applyClick(before, ITEMS, "x")).toBe(before);
  });

  it("selection order is the order rows were chosen — it is the order jobs are submitted in", () => {
    let s = applyClick({ value: [], anchor: null }, ITEMS, "d");
    s = applyClick(s, ITEMS, "a", { toggle: true });
    s = applyClick(s, ITEMS, "b", { toggle: true });
    expect(s.value).toEqual(["d", "a", "b"]);
  });

  it("single mode ignores the modifiers: one row, always", () => {
    expect(applyClick({ value: ["a"], anchor: "a" }, ITEMS, "c", { toggle: true }, "single").value).toEqual(["c"]);
    expect(applyClick({ value: ["a"], anchor: "a" }, ITEMS, "c", { range: true }, "single").value).toEqual(["c"]);
    expect(applyClick({ value: ["c"], anchor: "c" }, ITEMS, "c", {}, "single").value).toEqual([]);
  });
});

describe("All · None · ⌘A, and what the filter hides", () => {
  const visible = filterItems(ITEMS, "t"); // beta, delta — alpha, gamma and the disabled row are out

  it("All takes every visible selectable row, keeping what was already chosen", () => {
    expect(selectAllVisible(["c"], visible)).toEqual(["c", "b", "d"]);
  });

  it("All never takes a hard-disabled row", () => {
    expect(selectAllVisible([], ITEMS)).toEqual(["a", "b", "c", "d"]);
  });

  it("All skips a bulk-excluded row while it stays individually selectable", () => {
    // The subject grammar's J3 rule: an ineligible subject keeps its checkbox, but a bulk
    // convenience must not create a blocked run.
    expect(selectAllVisible([], ITEMS, new Set(["c"]))).toEqual(["a", "b", "d"]);
    expect(applyClick({ value: [], anchor: null }, ITEMS, "c").value).toEqual(["c"]);
  });

  it("None deselects the visible rows ONLY — a filtered-out row keeps its state", () => {
    expect(selectNoneVisible(["a", "b", "d"], visible)).toEqual(["a"]);
  });

  it("a row hidden by the filter survives an All, and is still there when the filter clears", () => {
    const afterAll = selectAllVisible(["a"], visible);
    expect(afterAll).toContain("a");
    expect(selectNoneVisible(afterAll, visible)).toEqual(["a"]);
  });

  it("All is idempotent", () => {
    const once = selectAllVisible([], visible);
    expect(selectAllVisible(once, visible)).toEqual(once);
  });
});

describe("the words the control says", () => {
  it("the badge is the whole status line", () => {
    expect(selectionBadge(0, 12)).toBe("None of 12 selected");
    expect(selectionBadge(3, 12)).toBe("3 of 12 selected");
  });

  it("a closed picker still answers “what did I pick?”", () => {
    expect(selectionSummary([], "Add electrode…")).toBe("Add electrode…");
    // One thing chosen reads as its own name — "1 regions · insula" is never right.
    expect(selectionSummary(["F7"])).toBe("F7");
    expect(selectionSummary(["F7", "P7"])).toBe("F7, P7");
    expect(selectionSummary(["F7", "P7", "F3", "P3", "Cz"])).toBe("F7, P7…");
    /*
     * Count first (maintainer, 2026-09-06): with more than one chosen, "how many" is what a closed
     * control is asked, and the old trailing `+2 more` answered it last — and was the first thing
     * an ellipsis ate in a narrow cell.
     */
    expect(selectionSummary(["F7", "P7", "F3", "P3", "Cz"], "Choose…", 2, "regions")).toBe(
      "5 regions · F7, P7…",
    );
    expect(selectionSummary(["F7", "P7"], "Choose…", 2, "regions")).toBe("2 regions · F7, P7");
    expect(selectionSummary(["F7"], "Choose…", 2, "regions")).toBe("F7");
  });

  it("the noun the count counts is the list's own label, singular or plural", () => {
    expect(selectionNoun("Regions", 3)).toBe("regions");
    expect(selectionNoun("Region(s)", 3)).toBe("regions");
    expect(selectionNoun("Subject", 2)).toBe("subjects");
    expect(selectionNoun("Subject", 1)).toBe("subject");
  });
});

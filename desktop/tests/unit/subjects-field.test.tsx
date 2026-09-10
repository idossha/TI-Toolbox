// @vitest-environment jsdom
/**
 * The one subject grammar (plan §3, J1-J4): its pure core, and the DOM contract every page's
 * spec — mock and real — locates a subject by.
 *
 * The pure half is where the *words* are decided (the summary line, the blocked sentence), so a
 * page can never invent its own vocabulary. The rendered half pins the shape: one `subjects-field`
 * with a summary, a disclosure, and — once open — a filter, a select-all and one
 * `subject-row-<id>` per subject with its reason. Both halves are what `tests/e2e/_subjects.ts`
 * then drives identically on all four run pages.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { SubjectsField } from "../../src/renderer/pages/_shared/subjects/SubjectsField";
import {
  blockedSubjects,
  filterSubjects,
  selectAll,
  subjectsBlockedReason,
  subjectsSummary,
  toggleSelection,
} from "../../src/renderer/pages/_shared/subjects/model";
import { notConvertedColumn, presenceColumns } from "../../src/renderer/pages/_shared/subjects/columns";
import { clearPageSession } from "../../src/renderer/app/pageSession";

describe("subjectsSummary — one line, and the semantics stated once (J1/J4)", () => {
  it("names a single subject and what running it means", () => {
    expect(subjectsSummary(["ernie"], "per-subject").text).toBe("ernie · one job per subject");
    expect(subjectsSummary(["ernie"], "grouped").text).toBe("ernie · one job over all subjects");
    expect(subjectsSummary(["ernie"], "single").text).toBe("ernie · one job");
  });

  it("counts and then names several", () => {
    expect(subjectsSummary(["101", "ernie", "MNI152"], "per-subject").text).toBe(
      "3 subjects · 101, ernie, MNI152 · one job per subject",
    );
    expect(subjectsSummary(["101", "ernie", "MNI152"], "grouped").text).toBe(
      "3 subjects · 101, ernie, MNI152 · one job over all subjects",
    );
  });

  it("caps the name list rather than growing the line without bound", () => {
    const many = ["a", "b", "c", "d", "e", "f", "g", "h"];
    expect(subjectsSummary(many, "per-subject").names).toBe("a, b, c, d, e, +3 more");
  });

  it("says only that nothing is selected — a semantics phrase would promise a run that cannot happen", () => {
    expect(subjectsSummary([], "per-subject").text).toBe("No subjects selected");
    expect(subjectsSummary([], "grouped").text).toBe("No subjects selected");
  });
});

describe("filterSubjects", () => {
  const subjects = [{ id: "ernie" }, { id: "101" }, { id: "MNI152" }];
  it("is a case-insensitive substring match on the id, and an empty box filters nothing", () => {
    expect(filterSubjects(subjects, "").map((s) => s.id)).toEqual(["ernie", "101", "MNI152"]);
    expect(filterSubjects(subjects, "  ").map((s) => s.id)).toEqual(["ernie", "101", "MNI152"]);
    expect(filterSubjects(subjects, "mni").map((s) => s.id)).toEqual(["MNI152"]);
    expect(filterSubjects(subjects, "1").map((s) => s.id)).toEqual(["101", "MNI152"]);
    expect(filterSubjects(subjects, "zz")).toEqual([]);
  });
});

describe("toggleSelection — the order ids are chosen in is the order jobs are submitted in", () => {
  it("appends, and never duplicates", () => {
    expect(toggleSelection(["ernie"], "101", true, "per-subject")).toEqual(["ernie", "101"]);
    expect(toggleSelection(["ernie", "101"], "ernie", true, "per-subject")).toEqual(["ernie", "101"]);
  });
  it("removes without disturbing the rest", () => {
    expect(toggleSelection(["ernie", "101", "MNI152"], "101", false, "per-subject")).toEqual(["ernie", "MNI152"]);
  });
  it("replaces in single mode — the control cannot express a set the page would silently narrow", () => {
    expect(toggleSelection(["ernie"], "101", true, "single")).toEqual(["101"]);
    expect(toggleSelection(["ernie"], "ernie", false, "single")).toEqual([]);
  });
});

describe("selectAll / blockedSubjects / subjectsBlockedReason (J3)", () => {
  const subjects = [
    { id: "ernie", m2m: true },
    { id: "101", m2m: false },
    { id: "MNI152", m2m: false },
  ];
  const eligibility = (s: { m2m: boolean }) => (s.m2m ? { ok: true } : { ok: false, reason: "no head model (m2m)" });

  it("select-all takes only what can actually run", () => {
    expect(selectAll(subjects, (s) => eligibility(s).ok)).toEqual(["ernie"]);
  });

  it("reports only the SELECTED subjects that cannot run", () => {
    expect(blockedSubjects(subjects, ["ernie"], eligibility)).toEqual([]);
    expect(blockedSubjects(subjects, ["ernie", "101"], eligibility)).toEqual([{ id: "101", reason: "no head model (m2m)" }]);
  });

  it("an empty selection is the same sentence on every page", () => {
    expect(subjectsBlockedReason([], [])).toBe("Select at least one subject.");
  });

  it("names the subject that cannot run and its reason — never a page-wide sentence", () => {
    expect(subjectsBlockedReason(["ernie", "101"], blockedSubjects(subjects, ["ernie", "101"], eligibility))).toBe(
      "101 cannot run — no head model (m2m). Deselect it, or fix it first.",
    );
  });

  it("merges one shared reason, and itemises different ones", () => {
    expect(subjectsBlockedReason(["101", "MNI152"], blockedSubjects(subjects, ["101", "MNI152"], eligibility))).toBe(
      "101, MNI152 cannot run — no head model (m2m). Deselect them, or fix them first.",
    );
    expect(
      subjectsBlockedReason(["101", "MNI152"], [
        { id: "101", reason: "no leadfield" },
        { id: "MNI152", reason: "no head model (m2m)" },
      ]),
    ).toBe("101, MNI152 cannot run — 101: no leadfield · MNI152: no head model (m2m). Deselect them, or fix them first.");
  });

  it("is null when everything selected can run", () => {
    expect(subjectsBlockedReason(["ernie"], [])).toBeNull();
  });
});

describe("presence columns — the shared readiness vocabulary, not new dots", () => {
  const row = {
    id: "ernie",
    has_raw: true,
    has_fastsurfer: true,
    has_freesurfer: false,
    has_m2m: true,
    has_dwi: false,
    has_ct: undefined,
    has_sourcedata: false,
  };
  it("is RAW / FS / FSR / M2M, with DWI and CT only where the page has that detail", () => {
    expect(presenceColumns<typeof row>().map((c) => c.label)).toEqual(["raw", "fastsurfer", "freesurfer", "m2m"]);
    expect(presenceColumns<typeof row>({ dwi: true, ct: true }).map((c) => c.label)).toEqual([
      "raw",
      "fastsurfer",
      "freesurfer",
      "m2m",
      "dwi",
      "ct",
    ]);
    expect(presenceColumns<typeof row>({ dwi: true }).map((c) => c.present(row))).toEqual([true, true, false, true, false]);
  });

  it("'not converted' is a flag, true only for a sourcedata-only subject", () => {
    const col = notConvertedColumn<typeof row>();
    expect(col.kind).toBe("flag");
    expect(col.present(row)).toBe(false);
    expect(col.present({ ...row, has_raw: false, has_sourcedata: true })).toBe(true);
    expect(col.present({ ...row, has_raw: true, has_sourcedata: true })).toBe(false);
  });
});

// ---------------------------------------------------------------------------------------------
// The rendered contract — the same DOM every page's spec drives.
// ---------------------------------------------------------------------------------------------

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  clearPageSession();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
function render(el: React.ReactElement) {
  act(() => root.render(el));
}
function click(el: Element | null) {
  act(() => (el as HTMLElement).click());
}
/** A modified click, as `ui/SelectionList` reads it: ⌘ toggles one row, ⇧ extends a range. */
function clickWith(el: Element | null, init: MouseEventInit) {
  act(() => {
    (el as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true, ...init }));
  });
}

interface Row {
  id: string;
  m2m: boolean;
}
const ROWS: Row[] = [
  { id: "ernie", m2m: true },
  { id: "101", m2m: true },
  { id: "MNI152", m2m: false },
];
const COLUMNS = [{ id: "m2m", label: "m2m", present: (s: Row) => s.m2m }];
const ELIGIBILITY = (s: Row) => (s.m2m ? { ok: true } : { ok: false, reason: "no head model (m2m)" });

function Harness({
  mode = "per-subject",
  initial = ["ernie"],
  defaultOpen = false,
}: {
  mode?: "per-subject" | "grouped" | "single";
  initial?: string[];
  defaultOpen?: boolean;
}) {
  const [value, setValue] = React.useState<string[]>(initial);
  return (
    <SubjectsField
      subjects={ROWS}
      value={value}
      onChange={setValue}
      columns={COLUMNS}
      eligibility={ELIGIBILITY}
      mode={mode}
      defaultOpen={defaultOpen}
    />
  );
}

describe("SubjectsField — the rendered grammar", () => {
  it("collapsed: a summary line and a disclosure, and no table at all", () => {
    render(<Harness />);
    const field = container.querySelector('[data-testid="subjects-field"]')!;
    expect(field.getAttribute("data-mode")).toBe("per-subject");
    expect(field.getAttribute("data-open")).toBe("false");
    expect(container.querySelector('[data-testid="subjects-summary"]')!.textContent).toBe("ernie · one job per subject");
    expect(container.querySelector(".subjects-field-disclosure")!.textContent).toBe("Change subjects…");
    expect(container.querySelectorAll(".subject-picker-row")).toHaveLength(0);
  });

  it("open: a filter, one row per subject, and the reason on the row that cannot run", () => {
    render(<Harness defaultOpen />);
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-open")).toBe("true");
    expect(container.querySelector('[data-testid="subjects-filter"]')).not.toBeNull();
    // No `All · None` pair and no count badge: the header checkbox is the bulk act and the summary
    // line above states the selection, so neither was a second way to learn anything.
    expect(container.querySelector('[data-testid="subject-select-all"]')).toBeNull();
    expect(container.querySelector('[data-testid="subject-select-none"]')).toBeNull();
    expect(container.querySelector('[data-testid="subject-count"]')).toBeNull();
    expect(container.querySelector('[data-testid="subjects-field-table"]')).not.toBeNull();
    expect(container.querySelectorAll("tbody .subject-picker-row")).toHaveLength(3);
    for (const id of ["ernie", "101", "MNI152"]) {
      expect(container.querySelector(`[data-testid="subject-row-${id}"]`)).not.toBeNull();
    }
    const blocked = container.querySelector('[data-testid="subject-row-MNI152"]')!;
    expect(blocked.getAttribute("data-eligible")).toBe("false");
    expect(container.querySelector('[data-testid="subject-reason-MNI152"]')!.textContent).toBe("no head model (m2m)");
    expect(container.querySelector('[data-testid="subject-reason-ernie"]')).toBeNull();
    // The header band itself closes it again — there is no separate Done button.
    expect(container.querySelector(".subjects-field-disclosure")!.textContent).toBe("Hide");
    click(container.querySelector('[data-testid="subjects-change"]'));
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-open")).toBe("false");
  });

  /* The 2.5.0 grammar, restored (plan C1): a PLAIN click selects exactly one row — that is what
     made "choose these three, not those" legible — and ⌘/Ctrl-click is how a second row is added.
     Before this the row-click ADDED and the checkbox in the same row also toggled, so two gestures
     one pixel apart did different things and neither said which. */
  it("a plain click selects exactly that row; ⌘-click adds a second", () => {
    render(<Harness defaultOpen />);
    click(container.querySelector('[data-testid="subject-row-101"] td:nth-child(3)'));
    expect(container.querySelector('[data-testid="subjects-summary"]')!.textContent).toBe("101 · one job per subject");
    clickWith(container.querySelector('[data-testid="subject-row-ernie"] td:nth-child(3)'), { metaKey: true });
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-selected")).toBe("2");
  });

  it("⇧-click selects the range from the last clicked row", () => {
    render(<Harness defaultOpen initial={[]} />);
    click(container.querySelector('[data-testid="subject-row-ernie"] td:nth-child(3)'));
    clickWith(container.querySelector('[data-testid="subject-row-MNI152"] td:nth-child(3)'), { shiftKey: true });
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-selected")).toBe("3");
  });

  it("the checkbox column is the same toggle, made visible", () => {
    render(<Harness defaultOpen />);
    click(container.querySelector('[data-testid="subject-row-101"] .checkbox-root'));
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-selected")).toBe("2");
  });

  it("an ineligible row is still tickable — its reason is what the page's Run button then prints", () => {
    render(<Harness defaultOpen />);
    click(container.querySelector('[data-testid="subject-row-MNI152"] .checkbox-root'));
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-selected")).toBe("2");
    expect(subjectsBlockedReason(["ernie", "MNI152"], blockedSubjects(ROWS, ["ernie", "MNI152"], ELIGIBILITY))).toBe(
      "MNI152 cannot run — no head model (m2m). Deselect it, or fix it first.",
    );
  });

  it("the header checkbox still takes only the eligible ones — a bulk convenience must not create a blocked run", () => {
    render(<Harness defaultOpen />);
    // Partly selected, so the header box first fills in the rest — the ineligible one excepted.
    const headerBox = () => container.querySelector("thead .checkbox-root")!;
    click(headerBox());
    expect(container.querySelector('[data-testid="subjects-summary"]')!.textContent).toBe(
      "2 subjects · ernie, 101 · one job per subject",
    );
    // Now everything selectable is ticked, so the same box clears it.
    click(headerBox());
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-selected")).toBe("0");
  });

  it("the filter narrows the rows without touching the selection", () => {
    render(<Harness defaultOpen />);
    const input = container.querySelector('[data-testid="subjects-filter"]') as HTMLInputElement;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "mni");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.querySelectorAll("tbody .subject-picker-row")).toHaveLength(1);
    expect(container.querySelector('[data-testid="subject-row-MNI152"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-selected")).toBe("1");
  });

  it("the disclosure and filter are page-session state, not remount-local state", () => {
    render(<Harness />);
    click(container.querySelector('[data-testid="subjects-change"]'));
    const input = container.querySelector('[data-testid="subjects-filter"]') as HTMLInputElement;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "101");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.querySelectorAll("tbody .subject-picker-row")).toHaveLength(1);

    act(() => root.render(<div />));
    render(<Harness />);
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-open")).toBe("true");
    expect((container.querySelector('[data-testid="subjects-filter"]') as HTMLInputElement).value).toBe("101");
    expect(container.querySelectorAll("tbody .subject-picker-row")).toHaveLength(1);
  });

  it("single mode: no header select-all, and ticking a second subject replaces the first", () => {
    render(<Harness mode="single" defaultOpen />);
    expect(container.querySelector("thead .checkbox-root")).toBeNull();
    click(container.querySelector('[data-testid="subject-row-101"] td:nth-child(3)'));
    expect(container.querySelector('[data-testid="subjects-summary"]')!.textContent).toBe("101 · one job");
    expect(container.querySelector('[data-testid="subjects-field"]')!.getAttribute("data-selected")).toBe("1");
  });

  it("an empty project says so inside the table rather than rendering an empty box", () => {
    render(
      <SubjectsField subjects={[]} value={[]} onChange={() => undefined} defaultOpen emptyMessage="No subjects in this project yet." />,
    );
    expect(container.querySelector('[data-testid="subjects-field-table"]')!.textContent).toContain(
      "No subjects in this project yet.",
    );
  });
});

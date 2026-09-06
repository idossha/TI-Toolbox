// @vitest-environment jsdom
/**
 * The participants grammar (fix round, lane FIX-D, defect 3): its pure core, its DOM contract, and
 * the guard that stops it drifting away from `SubjectsField`'s.
 *
 * Three panels cannot use `SubjectsField` — their model is a list of `(subject, simulation, role)`
 * rows in which one subject may legitimately repeat, which a set control cannot express (lane
 * SUB's §4, measured, not preferred). The risk that creates is a *fourth idiom*, so the tests
 * below assert the words (`participantsSummary`, `participantsBlockedReason`), the shape (a table
 * with real headers, a "Why not" cell that appears with the first reason), and — the drift guard —
 * that `participants.css` and `subjects.css` still declare the same grammar.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ParticipantsField } from "../../src/renderer/pages/panels/_participants/ParticipantsField";
import {
  blockedParticipants,
  participantsBlockedReason,
  participantsSummary,
} from "../../src/renderer/pages/panels/_participants/model";

const GROUPED = "one job over all subjects";

describe("participantsSummary — SubjectsField's line, over rows", () => {
  it("names a single subject and what running it means", () => {
    expect(participantsSummary(["ernie"], 1, GROUPED).text).toBe(`ernie · ${GROUPED}`);
  });

  it("counts and then names several", () => {
    expect(participantsSummary(["101", "ernie", "MNI152"], 3, GROUPED).text).toBe(
      `3 subjects · 101, ernie, MNI152 · ${GROUPED}`,
    );
  });

  it("states rows AND subjects when one subject takes part twice — the case a set cannot express", () => {
    // `cluster-permutation`'s paired test and `nifti-group-average`'s diff pairs are exactly this.
    const s = participantsSummary(["ernie", "ernie", "101"], 3, GROUPED);
    expect(s.lead).toBe("3 rows · 2 subjects");
    expect(s.text).toBe(`3 rows · 2 subjects · ernie, 101 · ${GROUPED}`);
    expect(s.subjects).toBe(2);
  });

  it("ignores a row whose subject has not been chosen — the line must agree with what would run", () => {
    expect(participantsSummary(["ernie", ""], 2, GROUPED).text).toBe(`ernie · ${GROUPED}`);
  });

  it("says only that nothing is chosen — a semantics phrase would promise a run that cannot happen", () => {
    expect(participantsSummary(["", ""], 2, GROUPED).text).toBe("No subjects chosen yet");
  });

  it("caps the name list rather than growing the line without bound", () => {
    expect(participantsSummary(["a", "b", "c", "d", "e", "f", "g", "h"], 8, GROUPED).names).toBe("a, b, c, d, e, +3 more");
  });
});

describe("participantsBlockedReason — one sentence, and it names the row", () => {
  const eligibility = (r: { subject: string; sim: string }) =>
    !r.subject ? { ok: false, reason: "no subject chosen" } : !r.sim ? { ok: false, reason: "no simulation chosen" } : { ok: true };

  it("states the requirement, not the symptom, while the table is short", () => {
    expect(participantsBlockedReason(0, [], 2)).toBe("Add at least 2 subjects with a simulation.");
    expect(participantsBlockedReason(0, [], 1)).toBe("Add at least one subject with a simulation.");
  });

  it("names the row and the reason once the count is met", () => {
    const rows = [
      { subject: "ernie", sim: "Thalamus" },
      { subject: "101", sim: "Thalamus" },
      { subject: "MNI152", sim: "" },
    ];
    const blocked = blockedParticipants(rows, eligibility);
    expect(blocked).toEqual([{ index: 3, reason: "no simulation chosen" }]);
    expect(participantsBlockedReason(2, blocked, 2)).toBe(
      "row 3 cannot run — no simulation chosen. Remove it, or fix it first.",
    );
  });

  it("lists every blocked row when they differ", () => {
    const rows = [
      { subject: "", sim: "" },
      { subject: "ernie", sim: "" },
      { subject: "101", sim: "Thalamus" },
      { subject: "MNI152", sim: "Thalamus" },
    ];
    const blocked = blockedParticipants(rows, eligibility);
    expect(participantsBlockedReason(2, blocked, 2)).toBe(
      "row 1, row 2 cannot run — row 1: no subject chosen · row 2: no simulation chosen. Remove them, or fix them first.",
    );
  });

  it("is null when nothing is wrong", () => {
    expect(participantsBlockedReason(2, [], 2)).toBeNull();
  });
});

interface Row {
  id: string;
  subject: string;
  sim: string;
}

const ROWS: Row[] = [
  { id: "r1", subject: "ernie", sim: "Thalamus" },
  { id: "r2", subject: "101", sim: "" },
];

function renderField(container: HTMLElement, root: Root, rows: Row[] = ROWS): void {
  act(() => {
    root.render(
      <ParticipantsField
        rows={rows}
        rowId={(r) => r.id}
        subjectOf={(r) => r.subject}
        note={GROUPED}
        eligibility={(r) => (!r.subject ? { ok: false, reason: "no subject chosen" } : !r.sim ? { ok: false, reason: "no simulation chosen" } : { ok: true })}
        subjectCell={(r) => <span data-testid={`subject-${r.id}`}>{r.subject || "—"}</span>}
        simulationCell={(r) => <span>{r.sim || "—"}</span>}
        columns={[{ id: "group", header: "Group", cell: () => <span>Group1</span> }]}
        onAdd={() => undefined}
        onRemove={() => undefined}
      />,
    );
  });
  void container;
}

describe("ParticipantsField — the rendered contract every panel spec drives", () => {
  let container: HTMLElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("renders one control, its summary, and one row per participant", () => {
    renderField(container, root);
    const field = container.querySelector('[data-testid="participants-field"]');
    expect(field).not.toBeNull();
    expect(field?.getAttribute("data-rows")).toBe("2");
    expect(field?.getAttribute("data-subjects")).toBe("2");
    expect(container.querySelector('[data-testid="participants-summary"]')?.textContent).toBe(
      `2 subjects · ernie, 101 · ${GROUPED}`,
    );
    expect(container.querySelectorAll("tbody .participant-row")).toHaveLength(2);
  });

  it("is a real table: a selection column, then # / Subject / Simulation, then the page's own columns", () => {
    renderField(container, root);
    const headers = Array.from(container.querySelectorAll("thead th")).map((th) => th.textContent);
    // The leading empty heading is the selection checkbox column (plan C1) — the same 24px column
    // every other list in the app draws, here as the ONLY selection gesture because the row's own
    // cells are live controls.
    expect(headers.slice(0, 5)).toEqual(["", "#", "Subject", "Simulation", "Group"]);
  });

  it("draws the Why-not column only while some row has a why-not, and marks the row", () => {
    renderField(container, root);
    expect(Array.from(container.querySelectorAll("thead th")).map((th) => th.textContent)).toContain("Why not");
    expect(container.querySelector('[data-testid="participant-reason-r2"]')?.textContent).toBe("no simulation chosen");
    expect(container.querySelector('[data-testid="participant-row-r1"]')?.getAttribute("data-eligible")).toBe("true");
    expect(container.querySelector('[data-testid="participant-row-r2"]')?.getAttribute("data-eligible")).toBe("false");

    renderField(container, root, [{ id: "r1", subject: "ernie", sim: "Thalamus" }]);
    expect(Array.from(container.querySelectorAll("thead th")).map((th) => th.textContent)).not.toContain("Why not");
  });

  it("keeps the title word every other page uses", () => {
    renderField(container, root);
    expect(container.querySelector(".participants-field-title")?.textContent).toBe("Subjects");
  });
});

/**
 * The drift guard. `participants.css` writes its own class names — a class must name what it
 * styles (defect 2's rule) — so nothing but a test stops the two stylesheets diverging into two
 * grammars, which is exactly the failure defect 3 exists to prevent.
 */
describe("participants.css declares the same grammar as subjects.css", () => {
  const read = (p: string) => readFileSync(resolve(__dirname, "..", "..", p), "utf8");
  const participants = read("src/renderer/pages/panels/_participants/participants.css");
  const subjects = read("src/renderer/pages/_shared/subjects/subjects.css");

  function block(css: string, selector: string): string {
    const start = css.indexOf(`${selector} {`);
    expect(start, `${selector} missing`).toBeGreaterThan(-1);
    return css.slice(start + selector.length + 2, css.indexOf("}", start));
  }
  const decls = (css: string, selector: string) =>
    block(css, selector)
      .split(";")
      .map((d) => d.trim())
      .filter(Boolean)
      .sort();

  it("the header band is the same 28px --surface-2 strip", () => {
    // The band's own geometry, not every declaration in the block: `SubjectsField`'s header is a
    // <button> (the band IS its disclosure — there is no Done button any more), so it also carries
    // the button reset. Everything that makes it a BAND must still match.
    const BAND = ["display", "align-items", "gap", "padding", "min-height", "background", "min-width"];
    const band = (css: string, selector: string) =>
      decls(css, selector).filter((d) => BAND.includes(d.split(":")[0]!.trim()));
    expect(band(participants, ".participants-field-head")).toEqual(band(subjects, ".subjects-field-head"));
  });

  it("the summary line is the same 12px ellipsised --ink-2 line", () => {
    expect(decls(participants, ".participants-field-summary")).toEqual(decls(subjects, ".subjects-field-summary"));
  });

  it("the reason is the same 12px warning text", () => {
    expect(decls(participants, ".participants-reason")).toEqual(decls(subjects, ".subjects-field-reason"));
  });

  it("the control itself is the same column", () => {
    expect(decls(participants, ".participants-field")).toEqual(decls(subjects, ".subjects-field"));
  });
});

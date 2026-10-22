/**
 * The subject grammar's pure core: the summary line and the blocked sentence. No React, no DOM —
 * every rule below is unit-tested in `tests/unit/subjects-field.test.tsx`, and every page gets the
 * same words from the same function. Row selection itself is `ui/SelectionList`'s.
 */
import type { SubjectsMode } from "./types";

/** J4's semantics, one phrase per mode, stated in every page's summary line. */
export const MODE_NOTE: Record<SubjectsMode, string> = {
  "per-subject": "one job per subject",
  grouped: "one job over all subjects",
  single: "one job",
};

/** Past this many ids the summary names the first few and counts the rest. */
const NAME_CAP = 6;

export interface SubjectsSummary {
  count: number;
  /** `3 subjects`, or null for 0 and 1 (the id itself is the whole label). */
  lead: string | null;
  /** `ernie` / `101, ernie, MNI152` / `101, ernie, … +3 more`. Empty when nothing is selected. */
  names: string;
  note: string;
  /** The whole line, exactly as the collapsed control prints it. */
  text: string;
}

/**
 * The one-line summary (J1) plus the selection semantics (J4):
 * `ernie · one job per subject`, `3 subjects · 101, ernie, MNI152 · one job per subject`.
 *
 * With nothing selected it says so and nothing else — a semantics phrase attached to an empty
 * selection reads as a promise about a run that cannot happen.
 */
export function subjectsSummary(value: string[], mode: SubjectsMode): SubjectsSummary {
  const note = MODE_NOTE[mode];
  if (value.length === 0) {
    return { count: 0, lead: null, names: "", note, text: "No subjects selected" };
  }
  const shown = value.length > NAME_CAP ? value.slice(0, NAME_CAP - 1) : value;
  const names = value.length > NAME_CAP ? `${shown.join(", ")}, +${value.length - shown.length} more` : shown.join(", ");
  const lead = value.length > 1 ? `${value.length} subjects` : null;
  return {
    count: value.length,
    lead,
    names,
    note,
    text: [lead, names, note].filter((p): p is string => !!p).join(" · "),
  };
}

export interface BlockedSubject {
  id: string;
  reason: string;
}

/**
 * Why the run is blocked *by the subject set*, in the page's action bar and on its Run button
 * (J3: "the reason text is what the Run button shows when it is disabled"). One wording for every
 * page, and it always names the subject — a batch blocked by a page-wide sentence never says
 * which of the three ticked subjects is the problem.
 */
export function subjectsBlockedReason(value: string[], blocked: BlockedSubject[]): string | null {
  if (value.length === 0) return "Select at least one subject.";
  if (blocked.length === 0) return null;
  const names = blocked.map((b) => b.id).join(", ");
  const reasons = [...new Set(blocked.map((b) => b.reason))];
  const detail = reasons.length === 1 ? reasons[0] : blocked.map((b) => `${b.id}: ${b.reason}`).join(" · ");
  const it = blocked.length === 1 ? "it" : "them";
  return `${names} cannot run — ${detail}. Deselect ${it}, or fix ${it} first.`;
}

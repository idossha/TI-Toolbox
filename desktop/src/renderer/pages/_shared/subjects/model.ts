/**
 * The subject grammar's pure core: the summary line, the filter, the selection algebra and the
 * blocked sentence. No React, no DOM — every rule below is unit-tested in
 * `tests/unit/subjects-field.test.ts`, and every page gets the same words from the same function.
 */
import type { SubjectEligibility, SubjectLike, SubjectsMode } from "./types";

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

/** Case-insensitive substring filter on the id. One box, no syntax — the table is small. */
export function filterSubjects<T extends SubjectLike>(subjects: T[], query: string): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return subjects;
  return subjects.filter((s) => s.id.toLowerCase().includes(q));
}

/**
 * Tick / untick, preserving the order ids were chosen in — that order is the order jobs are
 * submitted in (`optimizer`'s `flexSubmissions`, `simulator`'s rows), so it is not cosmetic.
 * In `single` mode a tick REPLACES the selection: the control cannot express a state the page
 * would then silently narrow behind the user's back.
 */
export function toggleSelection(value: string[], id: string, on: boolean, mode: SubjectsMode): string[] {
  if (mode === "single") return on ? [id] : value.filter((x) => x !== id);
  if (on) return value.includes(id) ? value : [...value, id];
  return value.filter((x) => x !== id);
}

/** Select-all takes every *eligible* subject; an ineligible one can never be ticked by any path. */
export function selectAll<T extends SubjectLike>(subjects: T[], eligible: (s: T) => boolean): string[] {
  return subjects.filter(eligible).map((s) => s.id);
}

export interface BlockedSubject {
  id: string;
  reason: string;
}

/** The selected subjects that cannot run, with the page's own reason for each. */
export function blockedSubjects<T extends SubjectLike>(
  subjects: T[],
  value: string[],
  eligibility?: (s: T) => SubjectEligibility,
): BlockedSubject[] {
  if (!eligibility) return [];
  const out: BlockedSubject[] = [];
  for (const id of value) {
    const subject = subjects.find((s) => s.id === id);
    if (!subject) continue;
    const verdict = eligibility(subject);
    if (!verdict.ok) out.push({ id, reason: verdict.reason ?? "cannot be used here" });
  }
  return out;
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

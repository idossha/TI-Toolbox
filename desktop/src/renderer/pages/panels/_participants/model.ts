/**
 * The participants grammar's pure core — the summary line and the blocked sentence, in
 * `pages/_shared/subjects/model.ts`'s words, over a row list rather than a set.
 *
 * No React, no DOM: every rule here is unit-tested in `tests/unit/participants-field.test.tsx`.
 */
import type { ParticipantEligibility } from "./types";

/** Past this many ids the summary names the first few and counts the rest (SubjectsField's rule). */
const NAME_CAP = 6;

export interface ParticipantsSummary {
  /** Rows, which is not the same as subjects — that difference is the whole reason for this file. */
  rows: number;
  subjects: number;
  /** `3 rows · 2 subjects`, or null when one row is one subject and there is only one of them. */
  lead: string | null;
  names: string;
  note: string;
  /** The whole line, exactly as the header prints it. */
  text: string;
}

/**
 * `ernie · one job over all subjects`, `3 subjects · 101, ernie, MNI152 · one job over all
 * subjects`, and — the case a set control cannot state at all — `4 rows · 3 subjects · 101,
 * ernie, MNI152 · one job over all subjects` when a subject takes part twice.
 *
 * A row with no subject yet contributes nothing to the names: it is a row the user has not
 * answered, and counting it would make the line disagree with what would run.
 */
export function participantsSummary(subjectIds: string[], rowCount: number, note: string): ParticipantsSummary {
  const named = subjectIds.filter((id) => id !== "");
  const distinct = [...new Set(named)];
  if (distinct.length === 0) {
    return { rows: rowCount, subjects: 0, lead: null, names: "", note, text: "No subjects chosen yet" };
  }
  const shown = distinct.length > NAME_CAP ? distinct.slice(0, NAME_CAP - 1) : distinct;
  const names =
    distinct.length > NAME_CAP ? `${shown.join(", ")}, +${distinct.length - shown.length} more` : shown.join(", ");
  const repeats = named.length !== distinct.length;
  const lead = repeats
    ? `${named.length} rows · ${distinct.length} subjects`
    : distinct.length > 1
      ? `${distinct.length} subjects`
      : null;
  return {
    rows: rowCount,
    subjects: distinct.length,
    lead,
    names,
    note,
    text: [lead, names, note].filter((p): p is string => !!p).join(" · "),
  };
}

export interface BlockedParticipant {
  /** 1-based, because that is the number the row prints in its own `#` column. */
  index: number;
  reason: string;
}

/** The rows that cannot take part, with the page's own reason for each. */
export function blockedParticipants<R>(
  rows: R[],
  eligibility?: (row: R) => ParticipantEligibility,
): BlockedParticipant[] {
  if (!eligibility) return [];
  const out: BlockedParticipant[] = [];
  rows.forEach((row, i) => {
    const verdict = eligibility(row);
    if (!verdict.ok) out.push({ index: i + 1, reason: verdict.reason ?? "cannot be used here" });
  });
  return out;
}

/**
 * Why the run is blocked *by the participants table* — the same sentence shape
 * `subjectsBlockedReason` gives every run page, and for the same reason: a page-wide "complete the
 * configuration" never says which of four rows is the problem.
 *
 * `minRows` is the analysis's own floor (2 for a group average or a permutation test, 1 for a
 * visualisation), so the first clause states the requirement rather than the symptom.
 */
export function participantsBlockedReason(
  complete: number,
  blocked: BlockedParticipant[],
  minRows: number,
): string | null {
  if (complete < minRows) {
    return minRows === 1
      ? "Add at least one subject with a simulation."
      : `Add at least ${minRows} subjects with a simulation.`;
  }
  if (blocked.length === 0) return null;
  const names = blocked.map((b) => `row ${b.index}`).join(", ");
  const reasons = [...new Set(blocked.map((b) => b.reason))];
  const detail = reasons.length === 1 ? reasons[0] : blocked.map((b) => `row ${b.index}: ${b.reason}`).join(" · ");
  const it = blocked.length === 1 ? "it" : "them";
  return `${names} cannot run — ${detail}. Remove ${it}, or fix ${it} first.`;
}

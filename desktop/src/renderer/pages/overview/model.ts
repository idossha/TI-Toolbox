/**
 * What the Overview page renders, as pure functions over the one `/api/catalog/overview` response.
 *
 * The arithmetic that used to live here (coverage tiles, readiness, per-stage output totals over a
 * per-subject fan-out) is now the server's: `tit/server/routes/overview.py` owns coverage, counts
 * and readiness, so a row and a stage card cannot disagree and a project of any size gets the same
 * answer. What is left here is presentation — how a `PresenceState` reads, which column order the
 * matrix uses, and the page's status-bar cell.
 */
import type { Overview, OverviewSubject, PresenceState } from "./api";
import type { SemanticKind } from "../../ui/Status";

/** The presence vocabulary, in the order the matrix draws it. */
export const PRESENCE_COLUMNS = [
  "raw",
  "fastsurfer",
  "freesurfer",
  "m2m",
  "dwi",
  "ct",
  "leadfield",
  "eeg_net",
] as const;

export type PresenceColumn = (typeof PRESENCE_COLUMNS)[number];

/** Short column heads for the matrix — the row is a table cell, not prose. */
export const COLUMN_LABEL: Record<PresenceColumn, string> = {
  raw: "raw",
  fastsurfer: "fs",
  freesurfer: "fsr",
  m2m: "m2m",
  dwi: "dwi",
  ct: "ct",
  leadfield: "lf",
  eeg_net: "net",
};

export interface PresenceCell {
  key: PresenceColumn;
  label: string;
  state: PresenceState;
  kind: SemanticKind;
  /** A running job is the one thing on this page that is still changing. */
  pulse: boolean;
  title: string;
}

/**
 * Five states, five readings. `absent` is the only one that means "nothing to say": `partial`,
 * `pending` and `failed` each answer a different question the old two-state boolean could not
 * (staged but not converted · a job is running now · the last attempt failed).
 */
const STATE_KIND: Record<PresenceState, SemanticKind> = {
  present: "success",
  partial: "warning",
  pending: "accent",
  failed: "danger",
  absent: "neutral",
};

const STATE_WORD: Record<PresenceState, string> = {
  present: "present",
  partial: "partial",
  pending: "running now",
  failed: "last run failed",
  absent: "missing",
};

export function presenceCells(row: OverviewSubject): PresenceCell[] {
  return PRESENCE_COLUMNS.map((key) => {
    const state = row[key];
    return {
      key,
      label: COLUMN_LABEL[key],
      state,
      kind: STATE_KIND[state],
      pulse: state === "pending",
      title: `${key} ${STATE_WORD[state]}`,
    };
  });
}

/** Is a subject ready for a stage? Server-computed; this is the lookup, not the rule. */
export function readyFor(row: OverviewSubject, stage: string): boolean {
  return row.readiness.some((r) => r.stage === stage && r.ready);
}

/** The requirement that failed, or undefined when the subject is ready. */
export function blockedReason(row: OverviewSubject, stage: string): string | undefined {
  return row.readiness.find((r) => r.stage === stage && !r.ready)?.reason ?? undefined;
}

export type StageId = "preprocess" | "simulator" | "optimizer" | "analyzer";

export interface Stage {
  id: StageId;
  label: string;
  /** The button's verb, sentence case. */
  verb: string;
  route: string;
  ready: string[];
  blocked: { subject: string; reason: string }[];
  /** The stage's project-wide output line, from the server's own totals. */
  summary: string;
}

const STAGES: { id: StageId; label: string; verb: string; route: string }[] = [
  { id: "preprocess", label: "Pre-processing", verb: "Pre-process", route: "/preprocess" },
  { id: "simulator", label: "Simulator", verb: "Simulate", route: "/simulator" },
  { id: "optimizer", label: "Optimizer", verb: "Optimize", route: "/optimizer" },
  { id: "analyzer", label: "Analyzer", verb: "Analyze", route: "/analyzer" },
];

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** The readiness board: who can run what next, and what each stage has produced so far. */
export function stages(data: Overview): Stage[] {
  const m2m = data.totals.coverage.find((c) => c.id === "m2m")?.have ?? 0;
  const summaries: Record<StageId, string> = {
    preprocess: `${plural(m2m, "head model")} built`,
    simulator: `${plural(data.totals.simulations, "simulation")} so far`,
    optimizer: `${plural(data.totals.optimizations, "search run")} so far`,
    analyzer: `${plural(data.totals.analyses, "analysis", "analyses")} so far`,
  };
  return STAGES.map((s) => ({
    ...s,
    summary: summaries[s.id],
    ready: data.subjects.filter((r) => readyFor(r, s.id)).map((r) => r.id),
    blocked: data.subjects
      .filter((r) => !readyFor(r, s.id))
      .map((r) => ({ subject: r.id, reason: blockedReason(r, s.id) ?? "not ready" })),
  }));
}

/** Has this subject everything a simulation needs? Drives the Ready/Incomplete filter. */
export function isReady(row: OverviewSubject): boolean {
  return readyFor(row, "simulator") && row.raw === "present";
}

/** `sourcedata/` has raw data staged but no BIDS directory yet — the DICOM onboarding case. */
export function notConverted(row: OverviewSubject): boolean {
  return row.raw === "partial";
}

/**
 * The `counts` status cell (§11.1): `3 subjects · 3 m2m · 1 leadfield`. Zero counts are dropped
 * rather than printed — the bar has no placeholders (U8).
 */
export function overviewStatusValue(data: Overview | undefined): string | undefined {
  if (!data || data.totals.subjects === 0) return undefined;
  const have = (id: string): number => data.totals.coverage.find((c) => c.id === id)?.have ?? 0;
  const n = data.totals.subjects;
  const parts = [`${n} subject${n === 1 ? "" : "s"}`];
  const m2m = have("m2m");
  const leadfields = have("leadfield");
  if (m2m) parts.push(`${m2m} m2m`);
  if (leadfields) parts.push(`${leadfields} leadfield${leadfields === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

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

/**
 * Short column heads for the matrix — the row is a table cell, not prose.
 *
 * One word per column, and no word that has to wrap: the previous heads put `fs`/`fsr` next to
 * each other (two different surface reconstructions, told apart by one letter) and let the `lf`
 * head sit under the neighbouring "Leadfield" column, which read as one clipped two-line label.
 * `fast`/`free` name the two reconstructions the way their tools are named, and `COLUMN_TITLE`
 * carries the long form as the header's tooltip.
 */
export const COLUMN_LABEL: Record<PresenceColumn, string> = {
  raw: "raw",
  fastsurfer: "fast",
  freesurfer: "free",
  m2m: "m2m",
  dwi: "dwi",
  ct: "ct",
  leadfield: "lf",
  eeg_net: "net",
};

/** The long form of each head, as its `title` — a four-letter column still has to be answerable. */
export const COLUMN_TITLE: Record<PresenceColumn, string> = {
  raw: "Raw MRI, converted into the BIDS tree",
  fastsurfer: "FastSurfer surface reconstruction",
  freesurfer: "FreeSurfer surface reconstruction",
  m2m: "SimNIBS head model (m2m directory)",
  dwi: "Diffusion-weighted images",
  ct: "CT volume",
  leadfield: "Leadfield matrix, per EEG net",
  eeg_net: "EEG net definition",
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

/** The dot vocabulary, spelled out once under the matrix rather than learned by hovering. */
export const PRESENCE_LEGEND: { state: PresenceState; kind: SemanticKind; word: string }[] = (
  ["present", "partial", "pending", "failed", "absent"] as const
).map((state) => ({ state, kind: STATE_KIND[state], word: STATE_WORD[state] }));

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
}

/**
 * The four workflows a selected subject can be sent into, from the detail pane's verb row.
 *
 * This used to also drive a readiness board of four cards on the page itself — per-stage ready
 * counts, output totals and a chip per subject. That board is gone: it restated what the matrix
 * already shows, one chip at a time, and the empty chip wells owned most of the page. The rail
 * reaches every workflow; the verbs here reach one scoped to the selected subject.
 */
export const STAGES: Stage[] = [
  { id: "preprocess", label: "Pre-processing", verb: "Pre-process", route: "/preprocess" },
  { id: "simulator", label: "Simulator", verb: "Simulate", route: "/simulator" },
  { id: "optimizer", label: "Optimizer", verb: "Optimize", route: "/optimizer" },
  { id: "analyzer", label: "Analyzer", verb: "Analyze", route: "/analyzer" },
];

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

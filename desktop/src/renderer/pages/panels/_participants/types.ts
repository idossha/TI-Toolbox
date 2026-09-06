/**
 * The participants grammar — its types (fix round, lane FIX-D, defect 3).
 *
 * `pages/_shared/subjects/SubjectsField` is the one control for a *set* of subjects. Three panels
 * cannot use it, for a reason lane SUB measured rather than assumed (its §4): their model is a
 * list of `(subject, simulation, role)` **rows**, and the same subject may legitimately appear
 * twice — `cluster-permutation`'s `testType: "paired"` and `nifti-group-average`'s diff pairs are
 * exactly that design. A set control cannot express it.
 *
 * So the model differs and the grammar does not. This control is `SubjectsField`'s header band,
 * summary line, table, "Why not" column and reason wording over a row list. The failure it
 * prevents: a fourth vocabulary for choosing who takes part — the three panels each drew their own
 * `<div style="display:grid">` of bare selects, with no header row, no summary of what would run,
 * and every problem reported as one page-level sentence that never said which row it meant.
 */
import type { ReactNode } from "react";

/** Can this row take part, and if not, why not — a noun phrase, not a sentence (J3's wording). */
export interface ParticipantEligibility {
  ok: boolean;
  /** "no subject chosen", "no simulation chosen", "no group name". Lower case. */
  reason?: string;
}

/** One column of the participants table, after the fixed `#` / Subject / Simulation ones. */
export interface ParticipantColumn<R> {
  id: string;
  header: string;
  cell: (row: R, index: number) => ReactNode;
  /** Column width, e.g. "120px" or "1fr"-ish `%`. Omitted lets the table share the space evenly. */
  width?: string;
}

export interface ParticipantsFieldProps<R> {
  rows: R[];
  rowId: (row: R) => string;
  /** The subject this row is about — "" while the row is still empty. */
  subjectOf: (row: R) => string;
  /** Subject + Simulation are always the first two columns; these follow. */
  columns: ParticipantColumn<R>[];
  /** Renders the Subject cell — a `Select` the page owns, because only the page knows its options. */
  subjectCell: (row: R, index: number) => ReactNode;
  /** Renders the Simulation cell, for the same reason. */
  simulationCell: (row: R, index: number) => ReactNode;
  eligibility?: (row: R) => ParticipantEligibility;
  /** J4, stated once in the summary line: what running these rows actually does. */
  note: string;
  onAdd?: () => void;
  /** "Add subject" / "Add pair" — the page's own word for one row. */
  addLabel?: string;
  onRemove?: (id: string) => void;
  /**
   * Keep the table at least this many rows tall, drawing the surplus as ground rows (the
   * `.run-table-filler` device `SubjectsField` and `MontageManager` both use). A three-row table
   * at the top of a 704 px pane is why these pages measured 65-74 % empty.
   */
  minRows?: number;
  /**
   * Draw ground rows all the way to the bottom of the box the table is in, whatever that is —
   * `minRows` measured rather than guessed.
   *
   * The loop is provably convergent, which is the thing to check here (lane UC's fill controller
   * oscillated because its input moved when it acted): the scroll box is `flex: 1` inside a grid
   * cell whose height comes from the OTHER column, so adding rows changes the table's scroll
   * height and never its client height. One observation, one answer.
   */
  fill?: boolean;
  /** The (i) affordance the page supplies, next to the title — never inside the table. */
  help?: ReactNode;
  loading?: boolean;
  emptyMessage?: string;
}

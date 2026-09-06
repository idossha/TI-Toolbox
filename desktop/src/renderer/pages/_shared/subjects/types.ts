/**
 * The one subject grammar (plan §3, J1-J4) — its types.
 *
 * Every page that picks subjects renders `SubjectsField` with these props and nothing else: the
 * page supplies *what a subject has* (`columns`) and *whether it can be used here*
 * (`eligibility`); the control owns the summary line, the disclosure, the filter, select-all, the
 * rows and the per-row reason. A page never re-implements any of that.
 */
import type { ReactNode } from "react";

/** The least a row needs. Pages pass their own richer objects (`Subject`, `SubjectDetail`, …). */
export interface SubjectLike {
  id: string;
}

/**
 * What running with N subjects means, stated in the summary line (J4). A user must never have to
 * guess whether three subjects is three runs or one.
 *
 * `single` is the third value the plan's two do not cover: the Analyzer's Subject scope submits
 * ONE job for ONE subject (`AnalyzerConfig.subject_id`), so neither "one job per subject" nor
 * "one job over all subjects" is true there. Stating it as a mode — and letting the control
 * enforce it — is what stops the page from silently analysing only the first of three ticked
 * subjects, which is what it did before (see `AnalyzerPage.effectiveSubjectIdsFor`).
 */
export type SubjectsMode = "per-subject" | "grouped" | "single";

/** Can this subject be used on this page, and if not, why not — a noun phrase, not a sentence. */
export interface SubjectEligibility {
  ok: boolean;
  /** "no head model", "no GSN-HydroCel-185 leadfield", "has not run Thalamus". Lower case. */
  reason?: string;
}

/**
 * One readiness column. `presence` renders Pre-processing's own chip (success when on, muted
 * "missing" when off) — the general case, reused rather than reinvented. `flag` renders a warning
 * chip only when true, for a state that is not a presence at all (Pre-processing's "not
 * converted": DICOMs staged under `sourcedata/`, no BIDS directory yet).
 */
export interface SubjectColumn<T extends SubjectLike> {
  id: string;
  label: string;
  present: (subject: T) => boolean;
  kind?: "presence" | "flag";
  title?: string;
}

export interface SubjectsFieldProps<T extends SubjectLike> {
  /** Every subject in the project, in the order the catalog returned them. */
  subjects: T[];
  /** The chosen ids, in the order they were chosen (the order jobs are submitted in). */
  value: string[];
  onChange: (ids: string[]) => void;
  /** Readiness columns, left to right. Empty renders no presence cell at all. */
  columns?: SubjectColumn<T>[];
  /** Page-specific gate. Omitted = every subject is usable. */
  eligibility?: (subject: T) => SubjectEligibility;
  mode?: SubjectsMode;
  /** Open on mount — true where batch selection *is* the page's job (Pre-processing, Source). */
  defaultOpen?: boolean;
  /**
   * Keep the table at least this many rows tall, drawing the surplus as ground rows — the same
   * device `MontageManager` uses (`.run-table-filler`, `pages/_shared/run/run.css`).
   * Pre-processing opts in because it opens the table by default and batch selection is what the
   * page is for: with three subjects the table otherwise ends in a hard edge halfway up a 900px
   * pane (measured: the last band of the work pane was 100 % empty at 1440x900). 0 — the default,
   * and what every other page uses — renders exactly the rows there are.
   */
  minRows?: number;
  /**
   * Draw ground rows to the bottom of the room the page actually has — `minRows` measured rather
   * than chosen by hand — and lift `.run-subject-scroll`'s 176 px cap, which is a sensible
   * default and was never meant to be a ceiling.
   *
   * The room is measured in the two shapes a subject table lives in, and both are convergent,
   * which is the thing to check after lane UC's oscillating fill controller:
   *
   *   - a **height-constrained box** (the Source panel: `flex: 1` in a column whose height comes
   *     from the pane) — its own `clientHeight` is the answer, and adding rows cannot change it;
   *   - a **scrolling column** (a run page: the box is as tall as its content) — the room is what
   *     the work pane's scrollport has left over, so growing by exactly that slack makes the next
   *     measurement report zero slack. A fixed point, reached in one step, and it can only shrink
   *     when the pane does.
   *
   * Pre-processing is why this exists: with `minRows={5}` its table stopped at 169 px in a 900 px
   * window whose page had ~90 px going spare, and the Source panel needed the cap lifted from
   * `pages/panels/panels.css` — one control's geometry decided in another page's stylesheet.
   */
  fill?: boolean;
  /** The (i) affordance the page supplies; rendered next to the title, never inside the table. */
  help?: ReactNode;
  /** Shown in place of the table when the project has no subjects. */
  emptyMessage?: string;
  /** The subject list is still loading. */
  loading?: boolean;
}

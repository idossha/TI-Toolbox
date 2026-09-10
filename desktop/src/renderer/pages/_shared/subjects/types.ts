/**
 * The one subject grammar (plan §3, J1-J4) — its types.
 *
 * Every page that picks subjects renders `SubjectsField` with these props and nothing else: the
 * page supplies *what a subject has* (`columns`) and *whether it can be used here*
 * (`eligibility`); the control owns the summary line, the disclosure, the filter, select-all, the
 * rows and the per-row reason. A page never re-implements any of that.
 */
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
   * Let the table take the room the page actually has, lifting `.run-subject-scroll`'s 176 px cap
   * — a sensible default that was never meant to be a ceiling.
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
   * The list itself still ends after the last subject: a taller box is room the rows may use, not
   * a shape to pad out with empty lines.
   */
  fill?: boolean;
  /** Shown in place of the table when the project has no subjects. */
  emptyMessage?: string;
  /** The subject list is still loading. */
  loading?: boolean;
}

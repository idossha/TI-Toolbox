/**
 * The **receipt** — "this will run N jobs, and here they are" — directly above Run on every run
 * page (plan `v3-tetravox-selection-pipeline-plan.md` §1-C, C3).
 *
 * 2.5.0 confirmed a batch by printing it: a plain list of the jobs about to be submitted, then the
 * button. v3 replaced that with a subject × stage matrix in the *other* pane, which is a fine
 * detail view and a poor confirmation — it states coverage, not a count, and it is nowhere near the
 * button you are about to press. The digest in the action bar says "6 jobs" but never which six.
 *
 * So the receipt goes back, derived from the same `planModelFrom` rows the grid draws, which is the
 * property that matters: **the grid, the digest and the receipt cannot disagree**, because all
 * three are renderings of one `PlanModel`. First 15 rows, then "… and K more" — exactly 2.5.0's
 * cut-off, and enough that a 3-subject × 2-montage batch is listed in full.
 *
 * The existing-outputs line is the second half of the same sentence: how many of those jobs already
 * have output, and therefore what the Skip / Replace / Cancel dialog (`ExistingOutputsDialog`) will
 * be asking about when Run is pressed.
 *
 * **Sticky, and collapsed by default.** "Directly above Run" has to be true on a page that
 * overflows its pane, which every run page does at 1280x800 — measured on the Simulator, where a
 * receipt written as the last child of the work column sat two screens below the button it is
 * about. So it is `position: sticky; bottom: 0` inside the work scroller: always the last thing
 * before the action bar, whatever the scroll offset. It costs one 24px line for that, because the
 * *count* is what confirms a batch and the *list* is what checks it — the list opens on demand and
 * the page remembers that choice (`app/pageSession`), like every other disclosure here.
 */
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { usePageSession } from "../../../app/pageSession";
import { Button } from "../../../ui/Button";
import type { PlanChip, PlanModel } from "./planModel";
import { stageLabelOf } from "./planModel";
import "./run.css";

export interface ReceiptRow {
  subject: string;
  stage: string;
  chip: PlanChip;
  outputDir: string;
}

export interface Receipt {
  rows: ReceiptRow[];
  /** `rows.length` — the number the button and the digest also print. */
  jobs: number;
  /** Jobs whose output directory already exists (`skip` + `overwrite`). */
  existing: number;
  /** Of those, the ones that would be replaced rather than skipped. */
  overwrites: number;
  blocked: number;
  waits: number;
}

/**
 * One row per planned job, in the page's own display order (subjects as selected, stages in run
 * order). A `null` chip means "this stage is not part of this subject's run" — the grid draws a `·`
 * for it and the receipt simply has no row, because a job that will not run is not a job.
 */
export function receiptFrom(plan: PlanModel | null): Receipt {
  const rows: ReceiptRow[] = [];
  let existing = 0;
  let overwrites = 0;
  let blocked = 0;
  for (const subject of plan?.subjects ?? []) {
    for (const cell of subject.cells) {
      if (cell.chip === null) continue;
      rows.push({
        subject: subject.subject,
        stage: stageLabelOf(plan!.kind, cell.stageId),
        chip: cell.chip,
        outputDir: cell.outputDir,
      });
      if (cell.chip === "skip") existing += 1;
      if (cell.chip === "overwrite") {
        existing += 1;
        overwrites += 1;
      }
      if (cell.chip === "blocked") blocked += 1;
    }
  }
  return { rows, jobs: rows.length, existing, overwrites, blocked, waits: plan?.stats.waits ?? 0 };
}

/**
 * The first line: `This will run 6 jobs`, or the page's own blocked sentence.
 *
 * `blocked` is passed separately because most pages build **no** `PlanModel` at all while the
 * configuration is incomplete (`plan === null`), and a receipt that then says "nothing to run yet"
 * where the action bar says "Select at least one subject." is two answers to one question.
 */
export function receiptHeadline(plan: PlanModel | null, receipt: Receipt, blocked?: string | null): string {
  if (plan?.blockedReason) return plan.blockedReason;
  if (blocked) return blocked;
  if (!plan) return "Nothing to run yet.";
  if (receipt.jobs === 0) return "This will run no jobs.";
  return `This will run ${receipt.jobs} job${receipt.jobs === 1 ? "" : "s"}:`;
}

/** The existing-outputs line, or `null` when nothing already exists. */
export function receiptExistingLine(receipt: Receipt, policy: "skip" | "replace"): string | null {
  if (receipt.existing === 0) return null;
  const n = receipt.existing;
  const noun = `${n} ${n === 1 ? "job" : "jobs"}`;
  return policy === "replace"
    ? `${noun} already have output and will be replaced.`
    : `${noun} already have output. You will be asked to skip or replace them.`;
}

const SHOWN = 15;

const CHIP_WORD: Record<PlanChip, string> = {
  new: "new",
  skip: "exists",
  overwrite: "replace",
  blocked: "blocked",
  wait: "waits",
};

export function Receipt({
  plan,
  policy = "skip",
  blockedReason,
  className,
  defaultOpen = true,
}: {
  plan: PlanModel | null;
  /** What the page's own overwrite control currently says, so the line matches the dialog. */
  policy?: "skip" | "replace";
  /** The page's own blocked sentence — the same one the action bar's digest prints. */
  blockedReason?: string | null;
  className?: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = usePageSession("receipt.open", defaultOpen);
  const receipt = receiptFrom(plan);
  const shown = receipt.rows.slice(0, SHOWN);
  const more = receipt.rows.length - shown.length;
  const existingLine = receiptExistingLine(receipt, policy);

  return (
    <section
      className={className ? `run-receipt ${className}` : "run-receipt"}
      data-testid="run-receipt"
      data-jobs={receipt.jobs}
      data-existing={receipt.existing}
      aria-label="What will run"
    >
      <div className="run-receipt-head">
        {/* One line: the count, then what already exists, then the disclosure. Two stacked lines
            cost the subject table a row of the room it measured, for the same words. */}
        <p className="run-receipt-headline" data-testid="run-receipt-headline">
          {receiptHeadline(plan, receipt, blockedReason)}
        </p>
        {existingLine && (
          <span className="run-receipt-existing" data-testid="run-receipt-existing">
            <AlertTriangle size={12} aria-hidden />
            {existingLine}
          </span>
        )}
        {receipt.jobs > 0 && (
          <Button
            variant="ghost"
            size="sm"
            icon={open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            data-testid="run-receipt-toggle"
          >
            {open ? "Hide" : `Show ${receipt.jobs === 1 ? "it" : "them"}`}
          </Button>
        )}
      </div>
      {open && shown.length > 0 && (
        <ul className="run-receipt-rows" data-testid="run-receipt-rows">
          {shown.map((row, i) => (
            <li key={`${row.subject}-${row.stage}-${i}`} className="run-receipt-row" data-chip={row.chip}>
              <span className="mono run-receipt-subject">{row.subject}</span>
              <span className="run-receipt-sep" aria-hidden>
                ·
              </span>
              <span className="mono run-receipt-stage">{row.stage}</span>
              <span className="run-receipt-chip">{CHIP_WORD[row.chip]}</span>
            </li>
          ))}
          {more > 0 && (
            <li className="run-receipt-row run-receipt-more" data-testid="run-receipt-more">
              … and {more} more
            </li>
          )}
        </ul>
      )}
    </section>
  );
}

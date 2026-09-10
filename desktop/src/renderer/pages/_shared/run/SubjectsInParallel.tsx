/**
 * `Subjects in parallel` — the one execution-policy control (IMPLEMENTATION_PLAN.md R3).
 *
 * Every workflow that runs one independent job per selected subject shows exactly this control,
 * with exactly this meaning:
 *
 *   1 = sequential, N = up to N of the group's jobs may run at once.
 *
 * It is a *server* cap, not a client behaviour: the number goes onto the one
 * `POST /api/jobs/groups` request as `parallel_subjects`, the whole group is created queued in
 * that single request, and `tit.jobs.scheduler.evaluate` releases the members N-at-a-time as
 * earlier ones finish (subject to the same lock and budget checks every job gets). Nothing in the
 * renderer spaces out or withholds requests — a `Promise.all` or a sequential POST loop would
 * only *look* like a policy while the scheduler ran whatever it liked.
 *
 * Pages that submit one job over the whole cohort (a grouped Analyzer run, statistics) do not
 * show it: there is one job, so there is nothing to run in parallel.
 */
import { Field } from "../../../ui/Field";
import { NumberInput } from "../../../ui/NumberInput";

export interface SubjectsInParallelProps {
  value: number;
  onChange: (value: number) => void;
  /** How many subjects are selected — the cap can never usefully exceed this. */
  subjectCount: number;
  /** Overrides the default help line for a page whose unit of work is not "one subject". */
  help?: string;
  disabled?: boolean;
}

/** The line the collapsed section summary and the control's own help both read. */
export function parallelSummary(value: number): string {
  return value <= 1 ? "sequential" : `${value} in parallel`;
}

export function SubjectsInParallel({
  value,
  onChange,
  subjectCount,
  help = "How many subjects run at once; 1 runs them one after another. The server's scheduler enforces this, not the app.",
  disabled = false,
}: SubjectsInParallelProps) {
  const max = Math.max(1, subjectCount);
  return (
    <Field label="Subjects in parallel" help={help}>
      <NumberInput
        value={value}
        onValueChange={(v) => onChange(Math.min(max, Math.max(1, v ?? 1)))}
        min={1}
        max={max}
        disabled={disabled}
        data-testid="subjects-in-parallel"
      />
    </Field>
  );
}

/**
 * The ONE definition of what a job row says — shared by the 260px rail (`JobsTable`), the Jobs
 * page's selection list (`pages/jobs/JobsSelectionTable`) and the Summary tab
 * (`JobDetailPane`). Each surface maps `JOB_COLUMNS` into its own table component's column type;
 * none of them chooses fields or formats a value on its own, so the three cannot disagree
 * (`tests/unit/jobs-row-model.test.tsx` renders one job through all of them and compares).
 *
 * Columns, in the order the brief fixes them: state · kind · subjects · elapsed · CPU · RSS. The
 * STAGE column that used to sit before ELAPSED is gone (DECISIONS 2026-09-19): the run pages'
 * terminals and the Summary own progress. CPU and RSS are the run's peak with the average beside
 * it (`cpuLabel` / `rssLabel` in `format.ts`).
 */
import type { ReactNode } from "react";
import { JobStateChip } from "../../ui/Status";
import type { JobStatus } from "./api";
import { cpuLabel, elapsedLabel, resourceText, rssLabel, type ResourceLabel } from "./format";

export const RESOURCE_HINT = "Peak · average over the run, summed over the job's process tree";

/** `peak · avg x` as one tabular cell, the average the quieter half; "—" only when never sampled.
 *  Its text is exactly `resourceText(label)`, which is what the Summary prints. */
export function ResourceCell({ label }: { label: ResourceLabel | null }) {
  if (!label) return <span className="jobs-cell-none">—</span>;
  return (
    <span className="jobs-cell-resource tabular-nums" title={RESOURCE_HINT}>
      {label.peak}
      {label.avg && <span className="jobs-cell-resource-avg"> · avg {label.avg}</span>}
    </span>
  );
}

export interface JobColumn {
  id: "state" | "kind" | "subjects" | "elapsed" | "cpu" | "rss";
  header: string;
  numeric?: boolean;
  cell: (job: JobStatus, now: number) => ReactNode;
}

/** The state chip: the first column, and the selection list's row label. */
export function stateCell(job: JobStatus): ReactNode {
  return <JobStateChip state={job.state} pulse={job.liveness === "active"} />;
}

export const JOB_COLUMNS: readonly JobColumn[] = [
  { id: "state", header: "State", cell: stateCell },
  { id: "kind", header: "Kind", cell: (j) => j.kind },
  {
    id: "subjects",
    header: "Subjects",
    // A batch of eight subjects has to give way somewhere: the cell ellipsizes and keeps the whole
    // list on hover rather than pushing CPU/RSS out of the box.
    cell: (j) => {
      const label = j.subject_ids.join(", ") || "—";
      return (
        <span className="jobs-cell-subjects" title={label}>
          {label}
        </span>
      );
    },
  },
  { id: "elapsed", header: "Elapsed", numeric: true, cell: (j, now) => elapsedLabel(j, now) },
  { id: "cpu", header: "CPU", numeric: true, cell: (j) => <ResourceCell label={cpuLabel(j)} /> },
  { id: "rss", header: "RSS", numeric: true, cell: (j) => <ResourceCell label={rssLabel(j)} /> },
];

/** The Summary tab's rows for the same fields, as plain strings — same formatters, same order. */
export function jobSummaryRows(job: JobStatus, now: number): [string, string][] {
  return [
    ["Kind", job.kind],
    ["Subjects", job.subject_ids.join(", ") || "—"],
    ["Elapsed", elapsedLabel(job, now)],
    ["CPU (peak · avg)", resourceText(cpuLabel(job))],
    ["RSS (peak · avg)", resourceText(rssLabel(job))],
  ];
}

/**
 * The bottom strip: what the machine is actually *working on*.
 *
 * It is on this page rather than left to the jobs rail because every number above it is a
 * consequence of these rows — a monitor that shows 100 % CPU and does not say which job is
 * responsible has made the reader open a second surface to finish the sentence.
 *
 * When nothing is running it shows the **last five finished** instead of an empty box: "nothing
 * is running" is worth one line, not a panel, and what a person wants next in that moment is what
 * just happened.
 */
import { useMemo } from "react";
import type { JobStatus } from "../../app/jobs-rail/api";
import { elapsedLabel } from "../../app/jobs-rail/format";
import type { JobsModel } from "../../app/jobs-rail/model";
import { JobStateChip } from "../../ui/Status";
import { bytes, pct } from "../../ui/utils";
import { Panel } from "./parts";

/**
 * A linear extrapolation of what is left, from the runner's own progress percentage.
 *
 * Deliberately *labelled* as an extrapolation ("at this rate") rather than presented as an ETA:
 * the server has no per-job time model, and a stage-weighted run — charm is not linear — would
 * make a confident-looking "4 min remaining" a lie. Below 5 % it says nothing at all, because the
 * extrapolation from two seconds of a two-hour job is meaningless.
 */
export function remainingLabel(job: JobStatus, now: number): string {
  const p = job.progress?.pct;
  if (p === undefined || p < 5 || p >= 100) return "";
  const started = job.started_at ? Date.parse(job.started_at) : Number.NaN;
  if (!Number.isFinite(started)) return "";
  const elapsedMs = now - started;
  if (elapsedMs <= 0) return "";
  const remainingMs = elapsedMs * ((100 - p) / p);
  const minutes = Math.round(remainingMs / 60_000);
  if (minutes < 1) return "< 1 min left, at this rate";
  if (minutes < 90) return `~${minutes} min left, at this rate`;
  return `~${(minutes / 60).toFixed(1)} h left, at this rate`;
}

export function JobsStrip({ model }: { model: JobsModel }) {
  const active = model.active;
  const recent = useMemo(
    () => model.all.filter((j) => !active.some((a) => a.id === j.id)).slice(0, 5),
    [model.all, active],
  );
  const showing = active.length > 0 ? active : recent;
  const idle = active.length === 0;

  return (
    <Panel
      title={idle ? "Recently finished" : `Running · ${model.runningCount}`}
      aside={idle ? "nothing running or queued" : `${model.all.length} jobs total`}
      className="system-panel-jobs"
      testId="system-jobs"
    >
      {showing.length === 0 ? (
        <p className="system-note text-caption">No jobs yet. Anything you run appears here while it runs.</p>
      ) : (
        <table className="system-mini system-jobs-table">
          <tbody>
            {showing.map((job) => (
              <tr key={job.id}>
                <td>
                  <JobStateChip state={job.state} pulse={job.liveness === "active"} />
                </td>
                <td className="system-mini-strong">{job.kind}</td>
                <td className="system-mini-dim system-mini-ellipsis">{job.subject_ids.join(", ") || "project"}</td>
                <td className="system-mini-dim">
                  {job.progress ? `${job.progress.stage} · ${Math.round(job.progress.pct)} %` : "—"}
                </td>
                <td className="system-mini-num tabular-nums">{elapsedLabel(job, model.now)}</td>
                <td className="system-mini-num tabular-nums">{pct(job.cpu_percent)}</td>
                <td className="system-mini-num tabular-nums">{job.rss ? bytes(job.rss) : "—"}</td>
                <td className="system-mini-dim system-jobs-eta">{idle ? "" : remainingLabel(job, model.now)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

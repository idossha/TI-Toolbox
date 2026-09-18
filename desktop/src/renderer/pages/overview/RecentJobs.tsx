/**
 * "Recent jobs" — the Overview's answer to "what have I run, and where is it?".
 *
 * Every row is a link: a finished job whose kind Results browses opens Results on that job's
 * subject; anything else opens the Jobs page with that job selected, on its log. The mapping is
 * `recentModel.ts::destinationFor`, tested without a DOM.
 *
 * It reads `useJobsModel()` — the one `/ws/jobs` store the rail, the panel and the Jobs page share
 * — so the section costs no request of its own and cannot disagree with the rail about a state.
 */
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../ui/Button";
import { EmptyState } from "../../ui/Feedback";
import { JobStateChip } from "../../ui/Status";
import { useJobsModel } from "../../app/jobs-rail/model";
import { useJobsUi } from "../../app/jobs-rail/store";
import { recentJobRows, type RecentJobDestination } from "./recentModel";

export function RecentJobs() {
  const navigate = useNavigate();
  const model = useJobsModel();
  const select = useJobsUi((s) => s.select);
  const rows = recentJobRows(model.all, model.now);

  const open = useCallback(
    (destination: RecentJobDestination) => {
      if (destination.page === "results") {
        // The subject rides on the navigation itself, never set first: `app/subjectSpine.ts`
        // republishes the CURRENT route when the shell's subject changes, and a subject set one
        // tick before a push is replaced straight back onto Overview.
        navigate("/results", { state: { subject: destination.subject ?? undefined } });
        return;
      }
      select(destination.jobId);
      navigate("/jobs", { state: { openJobId: destination.jobId } });
    },
    [navigate, select],
  );

  return (
    <section className="overview-recent" aria-label="Recent jobs" data-testid="overview-recent">
      <div className="overview-recent-head">
        <p className="overview-eyebrow">Recent jobs</p>
        <Button variant="ghost" size="sm" data-testid="overview-recent-see-all" onClick={() => navigate("/jobs")}>
          See all
        </Button>
      </div>
      {rows.length === 0 ? (
        <EmptyState variant="inline" message="Nothing has run in this project yet." />
      ) : (
        <div className="overview-recent-list">
          {rows.map((row) => (
            <button
              key={row.id}
              type="button"
              className="overview-recent-row"
              data-testid={`overview-recent-${row.id}`}
              data-destination={row.destination.page}
              title={`${row.kind} · ${row.subjects}${row.runName ? ` · ${row.runName}` : ""}`}
              onClick={() => open(row.destination)}
            >
              <span className="overview-recent-kind">{row.kind}</span>
              <span className="overview-recent-subjects">{row.subjects}</span>
              <span className="overview-recent-run">{row.runName ?? "—"}</span>
              <JobStateChip state={row.state} pulse={row.pulse} />
              <span className="overview-recent-time">{row.started}</span>
              <span className="overview-recent-time tabular-nums">{row.duration}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

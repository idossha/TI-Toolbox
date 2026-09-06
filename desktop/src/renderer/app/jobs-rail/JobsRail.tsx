/**
 * The signature element (DESIGN.md §0): running work is always in view, on every screen. One
 * component at three heights (plan §1) — this file is heights 1 and 2:
 *
 *   32px  collapsed: per-job traces, exactly as before (kind, subject, elapsed, animated bar),
 *         with everything past `RAIL_MAX_TRACES` collapsed into one "+N queued" chip instead of
 *         eight chips clipped mid-word by a horizontal scroll.
 *   260px expanded (⌘J): `JobsPanel`, tabs [Jobs][Console][Host][Report].
 *
 * Height 3 is `pages/jobs`, which renders the same `JobsTable` + `JobDetailPane` at full height
 * from the same `useJobsModel()`.
 *
 * The prop contract (`expanded` / `onExpandedChange`) is unchanged, so `app/Shell.tsx` and
 * `app/keyboard.ts` — another lane's files — need no edit.
 */
import { useEffect, useRef, useState } from "react";
import { ChevronUp } from "lucide-react";
import { IconButton } from "../../ui/Button";
import { JobTrace, type JobSummary } from "../../ui/Jobs";
import { Tooltip } from "../../ui/Overlay";
import type { JobState } from "../../ui/Status";
import "./jobs-rail.css";
import type { JobStatus } from "./api";
import { elapsedLabel } from "./format";
import { JobsPanel } from "./JobsPanel";
import { fitTraces, isRunning, overflowTooltip, RAIL_MAX_TRACES, splitRailJobs, useJobsModel } from "./model";
import { useJobsUi } from "./store";

export { RUNNING_STATES } from "./model";

function toSummary(job: JobStatus, now: number): JobSummary {
  return {
    id: job.id,
    kind: job.kind,
    subject: job.subject_ids.join(", ") || "—",
    state: job.state as JobState,
    progressPct: job.progress?.pct,
    // `JobStatus.liveness` is `"active" | "stalled" | null | undefined`; `JobSummary.liveness`
    // has no `null` — narrow here rather than widen `ui/Jobs.tsx` for one field.
    liveness: job.liveness ?? undefined,
    elapsed: elapsedLabel(job, now),
  };
}

export function JobsRail({ expanded, onExpandedChange }: { expanded: boolean; onExpandedChange: (expanded: boolean) => void }) {
  const model = useJobsModel();
  const select = useJobsUi((s) => s.select);
  const tracesRef = useRef<HTMLDivElement>(null);
  const [maxTraces, setMaxTraces] = useState(RAIL_MAX_TRACES);

  // How many traces fit is a function of the window, so it is measured rather than assumed: a
  // 1024px window (the minimum) has room for fewer than a 1600px one, and either way the rest
  // becomes the "+N queued" chip instead of scrolling out of sight.
  useEffect(() => {
    const el = tracesRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      setMaxTraces(fitTraces(width));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [expanded]);

  const { traces, overflow, overflowLabel } = splitRailJobs(model.active, maxTraces);

  if (expanded) {
    return (
      <div className="jobs-rail jobs-dock jobs-rail-expanded">
        <JobsPanel model={model} onCollapse={() => onExpandedChange(false)} />
      </div>
    );
  }

  return (
    <div className="jobs-rail jobs-dock jobs-rail-collapsed">
      <div className="jobs-rail-traces" ref={tracesRef}>
        {traces.length === 0 ? (
          <span className="jobs-rail-empty">No jobs running</span>
        ) : (
          traces.map((job) => (
            <JobTrace
              key={job.id}
              job={toSummary(job, model.now)}
              finishing={!isRunning(job)}
              onClick={() => {
                select(job.id);
                onExpandedChange(true);
              }}
            />
          ))
        )}
        {overflowLabel && (
          <Tooltip label={overflowTooltip(overflow)}>
            <button
              type="button"
              className="jobs-rail-overflow"
              data-testid="jobs-rail-overflow"
              onClick={() => onExpandedChange(true)}
            >
              {overflowLabel}
            </button>
          </Tooltip>
        )}
      </div>
      <IconButton aria-label="Expand jobs rail" icon={<ChevronUp size={16} />} onClick={() => onExpandedChange(true)} />
    </div>
  );
}

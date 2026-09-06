/**
 * Group jobs rendered as subject → stage trees (TODO.md §2.3: `POST /api/jobs/groups` creates one
 * job per subject, chained by `after` for the DAG's stage order — a subject can therefore have
 * several `JobStatus` rows sharing one `group_id`). The mock's `/api/jobs/groups` currently
 * creates exactly one "pre" job per subject rather than a full per-stage DAG (see PARITY.md), so
 * against it every subject renders one stage node; this view supports any number.
 */
import { ChevronRight, ChevronDown } from "lucide-react";
import { useState } from "react";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Chip, JobStateChip, LivenessBadge } from "../../ui/Status";
import { EmptyState } from "../../ui/Feedback";
import { elapsedLabel } from "./format";
import type { JobStatus } from "./api";

function groupJobs(jobs: JobStatus[]): Map<string, Map<string, JobStatus[]>> {
  const groups = new Map<string, Map<string, JobStatus[]>>();
  for (const job of jobs) {
    if (!job.group_id) continue;
    if (!groups.has(job.group_id)) groups.set(job.group_id, new Map());
    const bySubject = groups.get(job.group_id)!;
    const key = job.subject_ids.join(", ") || "(no subject)";
    if (!bySubject.has(key)) bySubject.set(key, []);
    bySubject.get(key)!.push(job);
  }
  for (const bySubject of groups.values()) {
    for (const stages of bySubject.values()) stages.sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
  }
  return groups;
}

/**
 * The group's representative kind, for the card header ("pre · 2 subjects"). Not simply
 * `all[0]?.kind`: a preprocessing group's stage job and its own trailing "report" job
 * (`tit.jobs.plans.plan_preprocessing`'s final step, every subject gets exactly one) can share the
 * same millisecond `created_at` with no secondary tiebreaker, and `Array.prototype.sort`'s
 * stability only helps when the input order is itself deterministic — observed in practice
 * flipping which one sorts first once enough other jobs exist in the list for a comparator with a
 * `-1`-on-ties bug (`GET /api/jobs`'s mock implementation) to reorder. Counting occurrences and
 * preferring the non-"report" kind sidesteps the ordering question entirely: "report" is always
 * the trailing, incidental stage, never the group's actual work.
 */
function groupSummary(bySubject: Map<string, JobStatus[]>): { kind: string; total: number; running: number; failed: number } {
  const all = [...bySubject.values()].flat();
  const counts = new Map<string, number>();
  for (const j of all) counts.set(j.kind, (counts.get(j.kind) ?? 0) + 1);
  const candidates = [...counts.entries()].filter(([kind]) => kind !== "report");
  const [kind] = (candidates.length > 0 ? candidates : [...counts.entries()]).sort((a, b) => b[1] - a[1])[0] ?? ["—"];
  return {
    kind,
    total: all.length,
    running: all.filter((j) => j.state === "queued" || j.state === "running").length,
    failed: all.filter((j) => j.state === "failed" || j.state === "lost").length,
  };
}

function StageNode({ job, onOpen }: { job: JobStatus; onOpen: (jobId: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(job.id)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 8px",
        borderRadius: "var(--radius-controls)",
        border: "1px solid var(--line)",
        background: "var(--surface)",
        cursor: "pointer",
      }}
    >
      <JobStateChip state={job.state} pulse={job.liveness === "active"} />
      {job.progress && (
        <span className="text-caption tabular-nums" style={{ color: "var(--ink-2)" }}>
          {job.progress.stage}
        </span>
      )}
      {job.liveness === "stalled" && <LivenessBadge state="stalled" />}
    </button>
  );
}

export function GroupsView({ jobs, now, onOpenJob }: { jobs: JobStatus[]; now: number; onOpenJob: (jobId: string) => void }) {
  const groups = groupJobs(jobs);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  if (groups.size === 0) {
    return <EmptyState icon={<ChevronRight size={20} />} message="No grouped jobs yet — batch preprocessing submissions from the Preprocess page appear here as subject → stage trees." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      {[...groups.entries()].map(([groupId, bySubject]) => {
        const summary = groupSummary(bySubject);
        const isOpen = !collapsed.has(groupId);
        return (
          <Card key={groupId}>
            <CardHeader
              title={
                <button
                  type="button"
                  onClick={() =>
                    setCollapsed((prev) => {
                      const next = new Set(prev);
                      if (next.has(groupId)) next.delete(groupId);
                      else next.add(groupId);
                      return next;
                    })
                  }
                  style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", color: "inherit", font: "inherit", padding: 0 }}
                >
                  {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  {summary.kind} · {bySubject.size} subject{bySubject.size === 1 ? "" : "s"}
                </button>
              }
              actions={
                <span style={{ display: "flex", gap: "var(--space-2)" }}>
                  {summary.running > 0 && <Chip kind="accent">{summary.running} running</Chip>}
                  {summary.failed > 0 && <Chip kind="danger">{summary.failed} failed</Chip>}
                  <span className="text-caption" style={{ color: "var(--ink-2)" }}>
                    {groupId}
                  </span>
                </span>
              }
            />
            {isOpen && (
              <CardBody>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                  {[...bySubject.entries()].map(([subject, stages]) => (
                    <div key={subject} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap" }}>
                      <span className="text-body" style={{ minWidth: 96, fontWeight: 500 }}>
                        {subject}
                      </span>
                      {stages.map((stage, i) => (
                        <span key={stage.id} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                          {i > 0 && <span style={{ color: "var(--ink-3)" }}>→</span>}
                          <StageNode job={stage} onOpen={onOpenJob} />
                        </span>
                      ))}
                      <span className="text-caption tabular-nums" style={{ color: "var(--ink-2)", marginLeft: "auto" }}>
                        {elapsedLabel(stages[stages.length - 1]!, now)}
                      </span>
                    </div>
                  ))}
                </div>
              </CardBody>
            )}
          </Card>
        );
      })}
    </div>
  );
}

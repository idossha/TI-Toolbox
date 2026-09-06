/**
 * The right pane's top half: a compact receipt of what Run will submit.
 *
 * This is the one page where the maintainer wants a run summary, and it has one job — say what
 * will happen, and if it cannot happen, say which step to go and fix. What it must **not** be is
 * what it was: a flat list of every issue the server returned, in which
 *
 *   "sim (sim1) is not connected to anything; it will run on its own"
 *
 * — a legitimate graph, and one this page has no opinion about — reads exactly like a blocker, and
 * three unwired nodes fill the pane with warnings before the user has done anything wrong.
 *
 * So: issues are grouped by the node they are about, only `level: "error"` is shown as a problem,
 * each group carries a **Fix** button that selects and centres that node, and the two findings
 * that are not faults at all — `unconnected` and `unconfigured` — are collapsed into one sentence
 * at the bottom. Keying on `PipelineIssue.code` rather than on the message text is what makes that
 * split possible; the code was added to the contract for this.
 */
import { AlertCircle } from "lucide-react";
import { displayName, nodeById, type PipelineDoc } from "./graph";
import type { PipelineIssue, PipelineJobPreview } from "./api";

/** §4.8's "first 15 + … and K more" rule. */
const SHOWN = 15;

export interface ReceiptProps {
  doc: PipelineDoc;
  issues: PipelineIssue[];
  jobs: PipelineJobPreview[];
  loading: boolean;
  onFocusNode: (nodeId: string) => void;
}

export function Receipt({ doc, issues, jobs, loading, onFocusNode }: ReceiptProps) {
  const errors = issues.filter((i) => i.level === "error");
  const independent = issues.filter((i) => i.code === "unconnected").length;
  const unconfigured = issues.filter((i) => i.code === "unconfigured").length;

  // Errors, grouped by node, in the document's own node order so the list matches the canvas.
  // A graph-level error (a cycle, an edge to a node that is gone) has no node and leads.
  const byNode = new Map<string, PipelineIssue[]>();
  const graphLevel: PipelineIssue[] = [];
  for (const issue of errors) {
    if (!issue.node_id) {
      graphLevel.push(issue);
      continue;
    }
    const list = byNode.get(issue.node_id) ?? [];
    list.push(issue);
    byNode.set(issue.node_id, list);
  }
  const order = doc.nodes.map((n) => n.id).filter((id) => byNode.has(id));

  if (doc.nodes.length === 0) {
    return (
      <div data-testid="pipeline-receipt">
        <p className="pipeline-muted">Nothing on the canvas yet.</p>
      </div>
    );
  }

  return (
    <div data-testid="pipeline-receipt">
      {errors.length > 0 ? (
        <>
          <p className="pipeline-receipt-headline">
            <strong>
              {errors.length} {errors.length === 1 ? "problem" : "problems"}
            </strong>{" "}
            to fix before this can run.
          </p>
          {graphLevel.length > 0 && (
            <div className="pipeline-problem">
              <div className="pipeline-problem-head">
                <span className="pipeline-problem-node">
                  <AlertCircle size={12} aria-hidden /> The graph
                </span>
              </div>
              <ul>
                {graphLevel.map((issue, i) => (
                  <li key={i} className="is-error">
                    {issue.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {order.map((nodeId) => {
            const node = nodeById(doc, nodeId);
            return (
              <div className="pipeline-problem" key={nodeId} data-testid={`pipeline-problem-${nodeId}`}>
                <div className="pipeline-problem-head">
                  <span className="pipeline-problem-node">{node ? displayName(node) : nodeId}</span>
                  <button
                    type="button"
                    className="pipeline-fix"
                    data-testid={`pipeline-fix-${nodeId}`}
                    onClick={() => onFocusNode(nodeId)}
                  >
                    Fix
                  </button>
                </div>
                <ul>
                  {byNode.get(nodeId)!.map((issue, i) => (
                    <li key={i} className="is-error">
                      {/* The port is the actionable half; the server's sentence spells out both
                          ways to satisfy it, and repeating the node's name here would be noise. */}
                      {issue.code === "missing_input" && issue.port
                        ? `needs ${issue.port} — wire it, or set it in this step's form`
                        : issue.message}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </>
      ) : loading ? (
        <p className="pipeline-muted">Checking…</p>
      ) : (
        <>
          <p className="pipeline-receipt-headline">
            <strong>{jobs.length}</strong> {jobs.length === 1 ? "job" : "jobs"} in <strong>one</strong> group —{" "}
            {doc.nodes.length} {doc.nodes.length === 1 ? "step" : "steps"}.
          </p>
          <ol className="pipeline-receipt-rows">
            {jobs.slice(0, SHOWN).map((job) => (
              <li key={job.label}>
                <code>{job.label}</code>
                <span className="pipeline-muted">
                  {job.kind}
                  {job.subject_ids.length ? ` · ${job.subject_ids.join(", ")}` : ""}
                  {job.after.length ? ` · after ${job.after.join(", ")}` : ""}
                </span>
              </li>
            ))}
          </ol>
          {jobs.length > SHOWN && <p className="pipeline-muted">… and {jobs.length - SHOWN} more</p>}
        </>
      )}

      {/* Stated once, at the bottom, in the past tense of a fact rather than the tone of a
          warning — because neither of these stops anything from running. */}
      {(independent > 0 || unconfigured > 0) && (
        <p className="pipeline-note" data-testid="pipeline-notes">
          {independent > 0 &&
            `${independent} ${independent === 1 ? "step runs" : "steps run"} independently (nothing is wired to ${independent === 1 ? "it" : "them"}).`}
          {independent > 0 && unconfigured > 0 && " "}
          {unconfigured > 0 &&
            `${unconfigured} ${unconfigured === 1 ? "step is" : "steps are"} still at ${unconfigured === 1 ? "its" : "their"} defaults.`}
        </p>
      )}
    </div>
  );
}

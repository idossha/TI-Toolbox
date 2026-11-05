/**
 * The Networks tab's explicit assess, for what no render starts by itself: `all.trx` for the
 * thalamocortical sequence, and the edge table a top-N list reads. A `tract` job's assess stage on
 * this simulation. Its one input the app cannot offer here, the subject's tractogram and network, is
 * checked before the button is offered, and the job's finish refreshes the tab (`app/jobs/invalidation.ts`).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Waypoints } from "lucide-react";
import { missingInputLines } from "../../../api/client";
import { usePageSession } from "../../../app/pageSession";
import { RUNNING_STATES, useJobsModel } from "../../../app/jobs-rail/model";
import { Button } from "../../../ui/Button";
import { Callout } from "../../../ui/Feedback";
import type { JobState } from "../../../ui/Status";
import { notifySubmitError } from "../../../ui/Toast";
import { ExistingOutputsDialog, isExistingOutputsConflict } from "../../_shared/run/ExistingOutputsDialog";
import { createTractJob, planTract, preflightTract, type JobStatus } from "./api";
import { buildAssessConfig, buildConnectionsAssessConfig } from "./config";

export function AssessNetworks({ subjectId, simulationName, onQueued, connectionsOnly = false }: {
  subjectId: string;
  simulationName: string;
  onQueued: (job: JobStatus) => void;
  /** Only the edge table: no `.trx`, so next to no disk. */
  connectionsOnly?: boolean;
}) {
  const config = connectionsOnly ? buildConnectionsAssessConfig(subjectId, simulationName) : buildAssessConfig(subjectId, simulationName);
  const preflight = useQuery({
    queryKey: ["tract-preflight", subjectId, simulationName],
    queryFn: () => preflightTract(config, subjectId),
  });
  const [assessJobs, setAssessJobs] = usePageSession<Record<string, string>>("assessJobs", {});
  const key = `${subjectId}/${simulationName}/${connectionsOnly ? "edges" : "all"}`;
  const { all } = useJobsModel();
  const running = all.some((job) => job.id === assessJobs[key] && RUNNING_STATES.includes(job.state as JobState));
  const [submitting, setSubmitting] = useState(false);
  const [askReplace, setAskReplace] = useState(false);

  async function submit(overwrite: boolean) {
    setSubmitting(true);
    try {
      // The plan answers first, so the question comes before anything is queued.
      if (!overwrite && (await planTract(config, subjectId)).jobs.some((job) => job.will_overwrite)) {
        setAskReplace(true);
        return;
      }
      const job = await createTractJob(config, subjectId, overwrite);
      setAssessJobs((previous) => ({ ...previous, [key]: job.id }));
      onQueued(job);
    } catch (error) {
      // A plan can lag the disk: the server's own refusal asks the same question.
      if (!overwrite && isExistingOutputsConflict(error)) setAskReplace(true);
      else notifySubmitError("Could not queue the network assessment.", error);
    } finally {
      setSubmitting(false);
    }
  }

  if (preflight.error) return <Callout kind="danger">{preflight.error.message}</Callout>;
  const missing = preflight.data ?? [];
  if (missing.length > 0) {
    return (
      <div data-testid="ve-assess-missing">
        <Callout kind="info">
          {missingInputLines(missing).map((line) => <p key={line}>{line}</p>)}
        </Callout>
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "var(--space-2)" }}>
      <Button
        variant="secondary"
        icon={<Waypoints size={14} />}
        loading={submitting || running || preflight.isPending}
        onClick={() => void submit(false)}
        data-testid="ve-assess-networks"
      >
        {running ? "Assessing…" : connectionsOnly ? "Assess connections" : "Assess networks"}
      </Button>
      <p className="field-help">
        Samples this simulation&rsquo;s fields along every streamline of sub-{subjectId}&rsquo;s tractogram and writes <code>Simulations/{simulationName}/tract/</code>
        {connectionsOnly ? ", with no streamline file." : <>, including <code>all.trx</code> (about 0.4 GB at 200,000 seeds).</>}
      </p>
      <ExistingOutputsDialog
        open={askReplace}
        onOpenChange={setAskReplace}
        existing={1}
        total={1}
        noun="network output"
        busy={submitting}
        onDecide={(decision) => {
          setAskReplace(false);
          if (decision === "replace") void submit(true);
        }}
      />
    </div>
  );
}

/**
 * One agent proposal as a plan card (ARCHITECTURE §6): who proposed what and why, each step in
 * the user's terms with its outputs, ETA and dependencies, anything it would replace (loud), and
 * Approve / Reject / Edit. After approval the same card follows each step's live state and links
 * its jobs. The server decides everything; this file only shows and asks.
 */
import { useId, useState } from "react";
import { type QueryClient, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bot, ChevronRight, X } from "lucide-react";
import { ApiError } from "../../api/client";
import { Button, IconButton } from "../../ui/Button";
import { Callout } from "../../ui/Feedback";
import { Field, TextInput, Textarea } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Chip } from "../../ui/Status";
import { Checkbox } from "../../ui/Toggle";
import { notify } from "../../ui/Toast";
import type { JobStatus } from "../jobs/types";
import { approveProposal, dismissProposal, editStep, PROPOSALS_KEY, rejectProposal, runStep, type StepEdit } from "./api";
import {
  blockers,
  isFinished,
  kindLabel,
  liveStepState,
  overwrites,
  proposer,
  STEP_STATE_KIND,
  stepFacts,
  totalEta,
  type Proposal,
  type ProposalStep,
} from "./model";
import { planStepTarget, stepRoute } from "./stepForm";
import "./proposals.css";

const STATUS_KIND = { draft: "neutral", pending: "warning", rejected: "neutral", running: "accent", succeeded: "success", failed: "danger" } as const;
const STATUS_LABEL = { draft: "draft", pending: "waiting for you", rejected: "rejected", running: "running", succeeded: "done", failed: "failed" } as const;

function minutes(m: number | null | undefined): string | null {
  if (m === null || m === undefined) return null;
  return m < 90 ? `~${Math.max(1, Math.round(m))} min` : `~${(m / 60).toFixed(1)} h`;
}

function errorText(e: unknown): string {
  return e instanceof ApiError || e instanceof Error ? e.message : String(e);
}

/**
 * Show a route's reply at once, then re-read the list. The reply is the plan as the server saw it
 * when it answered; /ws/jobs can have delivered (and the list refetched) a newer one before the
 * reply is handled, and written last it would freeze the card there — say "running" over a plan
 * that is already done — until the next proposal message, which may never come.
 */
function showReply(queryClient: QueryClient, p: Proposal): void {
  queryClient.setQueryData<Proposal[]>(PROPOSALS_KEY, (all) => all?.map((x) => (x.id === p.id ? p : x)));
  void queryClient.invalidateQueries({ queryKey: PROPOSALS_KEY });
}

/**
 * Inline editor for one pending step: the fields people change most, the config itself (folded),
 * and the way to the full run-page form ("Open in form", `stepForm.tsx`), which carries what is
 * typed here. The run pages' own Field / input / checkbox / button components.
 */
function StepEditor({
  proposal,
  step,
  onSave,
  onCancel,
  saving,
}: {
  proposal: Proposal;
  step: ProposalStep;
  onSave: (edit: StepEdit) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const navigate = useNavigate();
  const id = useId();
  const [text, setText] = useState(() => JSON.stringify(step.config, null, 2));
  const [subjects, setSubjects] = useState(step.subject_ids.join(", "));
  const [overwrite, setOverwrite] = useState(step.overwrite);
  let parsed: Record<string, unknown> | null = null;
  try {
    const value = JSON.parse(text) as unknown;
    if (value && typeof value === "object" && !Array.isArray(value)) parsed = value as Record<string, unknown>;
  } catch {
    parsed = null;
  }
  const setField = (key: string, value: unknown) => parsed && setText(JSON.stringify({ ...parsed, [key]: value }, null, 2)); // undefined drops the key
  const subjectIds = subjects.split(",").map((s) => s.trim()).filter(Boolean);
  const flex = step.kind.startsWith("flex");
  const sim = step.kind === "sim" || step.kind === "sim_from_flex";
  const route = stepRoute(step.kind);
  return (
    <div className="proposal-editor" data-testid={`proposal-editor-${step.id}`}>
      <div className="proposal-editor-fields">
        <Field label="Subjects" htmlFor={`${id}-subjects`}>
          <TextInput id={`${id}-subjects`} value={subjects} onChange={(e) => setSubjects(e.target.value)} aria-label="Subjects" />
        </Field>
        {flex && parsed && (
          <>
            <Field label="Run name" htmlFor={`${id}-run`}>
              <TextInput id={`${id}-run`} value={String(parsed.output_folder ?? "")} onChange={(e) => setField("output_folder", e.target.value)} aria-label="Run name" />
            </Field>
            <Field label="Current" htmlFor={`${id}-current`} help="Per channel.">
              <NumberInput
                id={`${id}-current`}
                unit="mA"
                step={0.1}
                min={0}
                value={typeof parsed.current_mA === "number" ? parsed.current_mA : undefined}
                onValueChange={(v) => setField("current_mA", v)}
                aria-label="Current per channel"
              />
            </Field>
          </>
        )}
        {sim && parsed && (
          <Field label="Currents" htmlFor={`${id}-currents`} help="mA per channel, comma-separated. Empty: the flex run's own.">
            <TextInput
              id={`${id}-currents`}
              placeholder={step.kind === "sim_from_flex" ? "the run's own" : "e.g. 1, 1"}
              value={Array.isArray(parsed.intensities) ? parsed.intensities.join(", ") : ""}
              onChange={(e) => {
                const values = e.target.value.split(",").map((v) => v.trim()).filter(Boolean).map(Number);
                setField("intensities", values.length ? values : undefined);
              }}
              aria-label="Currents"
            />
          </Field>
        )}
      </div>
      <Checkbox checked={overwrite} onCheckedChange={setOverwrite} label="Replace existing output" />
      <details className="proposal-editor-json">
        <summary>
          <ChevronRight size={12} aria-hidden className="proposal-editor-json-chevron" />
          Config (JSON)
        </summary>
        <Textarea
          className="control-mono"
          rows={12}
          value={text}
          invalid={parsed === null}
          onChange={(e) => setText(e.target.value)}
          aria-label="Step config JSON"
          spellCheck={false}
        />
      </details>
      <footer className="proposal-editor-actions">
        {route && (
          <Button
            size="sm"
            variant="ghost"
            disabled={parsed === null}
            title="Edit this step on its run page, with the full form"
            onClick={() => {
              if (!parsed) return;
              onCancel(); // the form takes over; the card is closed when the user comes back
              navigate(route, { state: { planStep: planStepTarget(proposal, { ...step, config: parsed, subject_ids: subjectIds, overwrite }) } });
            }}
          >
            Open in form
          </Button>
        )}
        <Button size="sm" variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button
          size="sm"
          variant="primary"
          loading={saving}
          disabled={parsed === null}
          onClick={() => parsed && onSave({ config: parsed, subject_ids: subjectIds, overwrite })}
        >
          Save step
        </Button>
      </footer>
    </div>
  );
}

function StepRow({
  proposal,
  step,
  index,
  jobs,
  onOpenJob,
}: {
  proposal: Proposal;
  step: ProposalStep;
  index: number;
  jobs: Record<string, JobStatus>;
  onOpenJob?: (jobId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const pending = proposal.status === "pending";
  const state = liveStepState(step, jobs);
  const replace = (p: Proposal) => showReply(queryClient, p);
  const save = useMutation({
    mutationFn: (edit: StepEdit) => editStep(proposal.id, step.id, edit),
    onSuccess: (p) => {
      replace(p);
      setEditing(false);
    },
    onError: (e) => notify.error(`Could not save step ${step.id}.`, errorText(e)),
  });
  const retry = useMutation({
    mutationFn: () => runStep(proposal.id, step.id),
    onSuccess: replace,
    onError: (e) => notify.error(`Could not run step ${step.id}.`, errorText(e)),
  });
  const plan = step.plan;
  const eta = minutes(plan?.eta_minutes);
  return (
    <li className="proposal-step" data-testid={`proposal-step-${step.id}`} data-state={state}>
      <div className="proposal-step-head">
        <span className="proposal-step-index tabular-nums">{index + 1}</span>
        <span className="proposal-step-kind">{kindLabel(step.kind)}</span>
        <span className="proposal-step-subjects mono">{step.subject_ids.map((s) => `sub-${s}`).join(", ")}</span>
        {step.after.length > 0 && <span className="proposal-step-after text-caption">after step {step.after.join(", ")}</span>}
        {eta && <span className="proposal-step-eta text-caption tabular-nums">{eta}</span>}
        <span className="proposal-step-end">
          {proposal.status !== "pending" && proposal.status !== "rejected" && (
            <Chip kind={STEP_STATE_KIND[state]} dot pulse={state === "running"}>
              {state}
            </Chip>
          )}
          {pending && !editing && (
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)} aria-expanded={false}>
              Edit
            </Button>
          )}
          {(state === "failed" || state === "error" || state === "skipped") && proposal.decision.state === "approved" && (
            <Button size="sm" variant="secondary" loading={retry.isPending} onClick={() => retry.mutate()}>
              Retry step
            </Button>
          )}
        </span>
      </div>
      {step.note && <p className="proposal-step-note">{step.note}</p>}
      <dl className="proposal-facts">
        {stepFacts(step, proposal.steps).map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
        {step.overwrite && (
          <div>
            <dt>Existing output</dt>
            <dd className="proposal-danger-text">replaced</dd>
          </div>
        )}
      </dl>
      {plan?.deferred && <p className="proposal-step-deferred text-caption">{plan.deferred}</p>}
      {(plan?.outputs ?? []).map((o) => (
        <div key={o.output_dir} className={o.exists ? "proposal-output proposal-output-exists" : "proposal-output"} title={o.output_dir}>
          <ChevronRight size={12} aria-hidden />
          <span className="mono">{o.output_dir}</span>
          {o.exists && <span className="proposal-danger-text"> · exists</span>}
        </div>
      ))}
      {step.error && <p className="proposal-danger-text">{step.error}</p>}
      {step.skipped && <p className="text-caption">Skipped: {step.skipped}</p>}
      {step.job_ids.length > 0 && onOpenJob && (
        <div className="proposal-step-jobs">
          {step.job_ids.map((id) => (
            <button key={id} type="button" className="proposal-job-link mono" onClick={() => onOpenJob(id)}>
              {id.slice(0, 8)}
            </button>
          ))}
        </div>
      )}
      {editing && (
        <StepEditor proposal={proposal} step={step} saving={save.isPending} onSave={(edit) => save.mutate(edit)} onCancel={() => setEditing(false)} />
      )}
    </li>
  );
}

export function ProposalCard({
  proposal,
  jobs,
  onOpenJob,
}: {
  proposal: Proposal;
  jobs: Record<string, JobStatus>;
  onOpenJob?: (jobId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const replace = (p: Proposal) => showReply(queryClient, p);
  const approve = useMutation({
    mutationFn: () => approveProposal(proposal.id),
    onSuccess: (p) => {
      replace(p);
      notify.success(`Approved “${p.title}”. Its jobs are queued.`);
    },
    onError: (e) => notify.error("The plan cannot run as it stands.", errorText(e)),
  });
  const reject = useMutation({
    mutationFn: () => rejectProposal(proposal.id, note.trim() || undefined),
    onSuccess: (p) => {
      replace(p);
      setRejecting(false);
    },
    onError: (e) => notify.error("Could not reject the plan.", errorText(e)),
  });
  const dismiss = useMutation({
    mutationFn: () => dismissProposal(proposal.id),
    onSuccess: () => queryClient.setQueryData<Proposal[]>(PROPOSALS_KEY, (all) => all?.filter((x) => x.id !== proposal.id)),
    onError: (e) => notify.error("Could not dismiss the plan.", errorText(e)),
  });
  const pending = proposal.status === "pending";
  const replaced = overwrites(proposal);
  const problems = blockers(proposal);
  const eta = minutes(totalEta(proposal));
  return (
    <section id={`proposal-${proposal.id}`} className="proposal-card" data-testid="proposal-card" data-status={proposal.status} aria-label={`Plan: ${proposal.title}`}>
      <header className="proposal-head">
        <Bot size={16} aria-hidden />
        <h3 className="proposal-title">{proposal.title}</h3>
        <span className="text-caption">from {proposer(proposal)}</span>
        {proposal.edited && <Chip kind="neutral">edited by you</Chip>}
        <span className="proposal-head-end">
          <Chip kind={STATUS_KIND[proposal.status]} dot={proposal.status === "running"} pulse={proposal.status === "running"}>
            {STATUS_LABEL[proposal.status]}
          </Chip>
          {proposal.status === "failed" && (
            <IconButton
              aria-label={`Dismiss “${proposal.title}”`}
              title="Dismiss"
              size="sm"
              icon={<X size={14} aria-hidden />}
              disabled={dismiss.isPending}
              onClick={() => dismiss.mutate()}
            />
          )}
        </span>
      </header>
      {proposal.rationale && <p className="proposal-rationale">{proposal.rationale}</p>}
      {pending && replaced.length > 0 && (
        <Callout kind="danger" title="This plan replaces existing results">
          <ul className="proposal-list">
            {replaced.map((r) => (
              <li key={r.path}>
                <span className="mono">{r.path}</span> (step {r.step}){r.allowed ? "" : " — not allowed yet: Edit the step and tick “Replace existing output”, or rename the run"}
              </li>
            ))}
          </ul>
        </Callout>
      )}
      {pending && problems.length > 0 && (
        <Callout kind="warning" title="Cannot run as proposed">
          <ul className="proposal-list">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Callout>
      )}
      <ol className="proposal-steps">
        {proposal.steps.map((step, i) => (
          <StepRow key={step.id} proposal={proposal} step={step} index={i} jobs={jobs} onOpenJob={onOpenJob} />
        ))}
      </ol>
      {proposal.decision.note && (
        <p className="proposal-decision-note text-caption">
          Your note: <q>{proposal.decision.note}</q>
        </p>
      )}
      {pending && (
        <footer className="proposal-actions">
          {eta && <span className="text-caption tabular-nums">Estimated {eta} in total</span>}
          {rejecting ? (
            <>
              <TextInput
                className="proposal-note"
                placeholder="Tell the agent what to change (optional)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                aria-label="Rejection note"
                autoFocus
              />
              <Button size="sm" variant="ghost" onClick={() => setRejecting(false)}>
                Cancel
              </Button>
              <Button size="sm" variant="destructive" loading={reject.isPending} onClick={() => reject.mutate()}>
                Reject plan
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="secondary" onClick={() => setRejecting(true)}>
                Reject…
              </Button>
              <Button
                size="sm"
                variant="primary"
                loading={approve.isPending}
                // The server refuses the same two cases (tit.server.proposals._blockers).
                disabled={problems.length > 0 || replaced.some((r) => !r.allowed)}
                onClick={() => approve.mutate()}
              >
                Approve and run
              </Button>
            </>
          )}
        </footer>
      )}
    </section>
  );
}

const FINISHED_OPEN_KEY = "tit-finished-plans-open";

function readOpen(): boolean {
  try {
    return window.localStorage.getItem(FINISHED_OPEN_KEY) === "1";
  } catch {
    return false; // localStorage unavailable: collapsed
  }
}

function FinishedRow({ proposal, onOpenJob }: { proposal: Proposal; onOpenJob?: (jobId: string) => void }) {
  const queryClient = useQueryClient();
  const dismiss = useMutation({
    mutationFn: () => dismissProposal(proposal.id),
    onSuccess: () => queryClient.setQueryData<Proposal[]>(PROPOSALS_KEY, (all) => all?.filter((x) => x.id !== proposal.id)),
    onError: (e) => notify.error("Could not dismiss the plan.", errorText(e)),
  });
  const at = proposal.updated_at ?? proposal.created_at;
  return (
    <li className="finished-plan" data-testid="finished-plan" data-status={proposal.status}>
      <span className="proposal-title">{proposal.title}</span>
      <Chip kind={STATUS_KIND[proposal.status]}>{STATUS_LABEL[proposal.status]}</Chip>
      <span className="text-caption">from {proposer(proposal)}</span>
      <time className="text-caption tabular-nums" dateTime={at}>
        {new Date(at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
      </time>
      {onOpenJob &&
        proposal.steps
          .flatMap((s) => s.job_ids)
          .map((id) => (
            <button key={id} type="button" className="proposal-job-link mono" onClick={() => onOpenJob(id)}>
              {id.slice(0, 8)}
            </button>
          ))}
      <IconButton
        className="finished-plan-dismiss"
        aria-label={`Dismiss “${proposal.title}”`}
        title="Dismiss"
        size="sm"
        icon={<X size={14} aria-hidden />}
        disabled={dismiss.isPending}
        onClick={() => dismiss.mutate()}
      />
    </li>
  );
}

/** "Finished plans (N)": one line collapsed; expanded, a compact row per plan with Dismiss. */
function FinishedPlans({ proposals, onOpenJob }: { proposals: readonly Proposal[]; onOpenJob?: (jobId: string) => void }) {
  const [open, setOpen] = useState(readOpen);
  const toggle = () => {
    try {
      window.localStorage.setItem(FINISHED_OPEN_KEY, open ? "0" : "1");
    } catch {
      // best-effort persistence only
    }
    setOpen(!open);
  };
  return (
    <div className="finished-plans" data-testid="finished-plans">
      <button type="button" className="finished-plans-toggle text-caption" aria-expanded={open} onClick={toggle}>
        <ChevronRight size={12} aria-hidden className={open ? "finished-plans-chevron open" : "finished-plans-chevron"} />
        Finished plans ({proposals.length})
      </button>
      {open && (
        <ul className="finished-plans-list">
          {proposals.map((p) => (
            <FinishedRow key={p.id} proposal={p} onOpenJob={onOpenJob} />
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The Jobs page's strip of plans: a card for each one that needs the user, is in flight or failed
 * (pending, then running, then failed), and the done/rejected ones folded into a "Finished plans
 * (N)" disclosure. A failed card keeps its per-step Retry until the user dismisses it.
 */
export function ProposalsStrip({
  proposals,
  jobs,
  onOpenJob,
}: {
  proposals: readonly Proposal[];
  jobs: Record<string, JobStatus>;
  onOpenJob?: (jobId: string) => void;
}) {
  if (proposals.length === 0) return null;
  const finished = proposals.filter(isFinished);
  const rank = (p: Proposal) => (p.status === "pending" ? 0 : p.status === "failed" ? 2 : 1); // pending, running, failed
  const active = proposals.filter((p) => !isFinished(p)).sort((a, b) => rank(a) - rank(b));
  return (
    <div className="proposals-strip" data-testid="proposals-strip">
      {active.map((p) => (
        <ProposalCard key={p.id} proposal={p} jobs={jobs} onOpenJob={onOpenJob} />
      ))}
      {finished.length > 0 && <FinishedPlans proposals={finished} onOpenJob={onOpenJob} />}
    </div>
  );
}

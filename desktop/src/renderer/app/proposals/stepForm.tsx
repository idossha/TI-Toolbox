/**
 * "Open in form" (ARCHITECTURE §6): a pending plan step edited on its own run page. The card
 * navigates with the step in the router state; the page puts its own draft aside, loads the
 * step's config into its usual form through its own config→form mapping, and swaps Run for
 * "Save to plan", which PATCHes the step (`editStep`) and returns to Jobs. Cancel restores the
 * draft without saving. Nothing here runs anything; the server re-plans the edited step.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { usePageSession } from "../pageSession";
import { Button } from "../../ui/Button";
import { Callout } from "../../ui/Feedback";
import { notify } from "../../ui/Toast";
import { useRunShortcut } from "../../pages/_shared/run/useRunShortcut";
import { editStep, PROPOSALS_KEY, type StepEdit } from "./api";
import { kindLabel, type Proposal, type ProposalStep } from "./model";

/** The step as its run page receives it. `flexRun` is a sim_from_flex step's source run name. */
export interface PlanStepTarget {
  proposalId: string;
  stepId: string;
  number: number;
  title: string;
  kind: string;
  config: Record<string, unknown>;
  subjectIds: string[];
  overwrite: boolean;
  flexRun?: string;
}

/** The run page that edits each step kind; `null` for a kind no page builds (leadfield, analyzer). */
export function stepRoute(kind: string): string | null {
  if (kind === "pre") return "/preprocess";
  if (kind === "sim" || kind === "sim_from_flex") return "/simulator";
  if (["flex", "flex_adaptive", "flex_pareto", "ex", "mex"].includes(kind)) return "/optimizer";
  return null;
}

export function planStepTarget(proposal: Proposal, step: ProposalStep): PlanStepTarget {
  const config = step.config as Record<string, unknown>;
  const parent = proposal.steps.find((s) => s.id === config.flex_step);
  const parentFolder = parent ? String((parent.config as Record<string, unknown>).output_folder ?? "") : "";
  return {
    proposalId: proposal.id,
    stepId: step.id,
    number: proposal.steps.findIndex((s) => s.id === step.id) + 1,
    title: proposal.title,
    kind: step.kind,
    config: structuredClone(config),
    subjectIds: [...step.subject_ids],
    overwrite: step.overwrite,
    flexRun: step.kind === "sim_from_flex" ? (parentFolder.split("/").pop() || (config.flex_run as string | undefined)) : undefined,
  };
}

interface Session<S> {
  step: PlanStepTarget;
  stash: S;
}

/**
 * The page side. *snapshot* reads the page's own draft, *load* replaces it with the step,
 * *restore* puts the draft back. Returns the step being edited (or `null`), `save` and `cancel`.
 */
export function usePlanStepEdit<S>({
  snapshot,
  load,
  restore,
}: {
  snapshot: () => S;
  load: (step: PlanStepTarget) => void | Promise<void>;
  restore: (stash: S) => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [session, setSession] = usePageSession<Session<S> | null>("planStep", null);
  const [handled, setHandled] = useState<string | null>(null);
  const incoming = (location.state as { planStep?: PlanStepTarget } | null)?.planStep;

  // The handoff becomes page state once, during render (the candidate handoff's pattern); the
  // draft is read before the step replaces it. A second "Open in form" keeps the first draft.
  if (incoming && handled !== location.key) {
    setHandled(location.key);
    setSession({ step: incoming, stash: session ? session.stash : snapshot() });
  }
  const loaded = useRef<string | null>(null);
  useEffect(() => {
    if (!incoming || loaded.current === location.key) return;
    loaded.current = location.key;
    void Promise.resolve(load(incoming)).catch((e: unknown) => notify.error("Could not open the step in the form.", e instanceof Error ? e.message : String(e)));
    navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per router handoff
  }, [incoming, location.key]);

  const leave = useCallback(() => {
    if (session) restore(session.stash);
    setSession(null);
    navigate("/jobs", { state: session ? { proposalId: session.step.proposalId } : undefined });
  }, [session, restore, setSession, navigate]);

  const mutation = useMutation({
    mutationFn: (edit: StepEdit) => editStep(session!.step.proposalId, session!.step.stepId, edit),
    onSuccess: (p) => {
      queryClient.setQueryData<Proposal[]>(PROPOSALS_KEY, (all) => all?.map((x) => (x.id === p.id ? p : x)));
      notify.success(`Saved step ${session!.step.number} of “${p.title}”. Nothing runs until you approve the plan.`);
      leave();
    },
    onError: (e) => notify.error(`Could not save step ${session?.step.number}.`, e instanceof ApiError || e instanceof Error ? e.message : String(e)),
  });

  return { step: session?.step ?? null, save: mutation.mutate, saving: mutation.isPending, cancel: leave };
}

/** Above the page's form while a step is open in it. */
export function PlanStepBanner({ step }: { step: PlanStepTarget }) {
  return (
    <div data-testid="plan-step-banner">
      <Callout kind="info" title={`Editing plan step: ${step.title} · step ${step.number}`}>
        {kindLabel(step.kind)} for {step.subjectIds.map((s) => `sub-${s}`).join(", ")}. Save to plan updates the step; nothing runs until you
        approve the plan on the Jobs page.
      </Callout>
    </div>
  );
}

/**
 * The action bar's primary and secondary in place of Run (and ⌘⏎ while a step is open). *build*
 * turns the page's form into the step edit, or throws an Error whose message says why it cannot
 * (shown; nothing is sent).
 */
export function usePlanStepActions(edit: ReturnType<typeof usePlanStepEdit>, build: () => StepEdit) {
  const save = () => {
    try {
      edit.save(build());
    } catch (e) {
      notify.error("This step cannot be saved as it stands.", e instanceof Error ? e.message : String(e));
    }
  };
  useRunShortcut(save, edit.step !== null);
  return {
    secondary: (
      <Button variant="secondary" onClick={edit.cancel} disabled={edit.saving}>
        Cancel
      </Button>
    ),
    primary: (
      <Button variant="primary" loading={edit.saving} onClick={save} data-testid="plan-step-save">
        Save to plan
      </Button>
    ),
  };
}

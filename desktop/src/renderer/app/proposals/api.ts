/**
 * `/api/proposals` calls and the one shared query of them. Live: the `/ws/jobs` store bumps
 * `proposalRev` on every `{type: "proposal"}` message and `useProposals` refetches; a new
 * pending proposal raises a toast once (the nav's Jobs badge counts them).
 */
import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { isProjectHome } from "../../env";
import { notify } from "../../ui/Toast";
import { useJobsStream } from "../jobs/useJobsStream";
import { proposer, type Proposal } from "./model";

export interface StepEdit {
  config?: Record<string, unknown>;
  subject_ids?: string[];
  overwrite?: boolean;
}

export async function listProposals(): Promise<Proposal[]> {
  return unwrap(await api.GET("/api/proposals", { params: { query: {} } }), "/api/proposals");
}

export async function approveProposal(id: string, note?: string): Promise<Proposal> {
  return unwrap(await api.POST("/api/proposals/{id}/approve", { params: { path: { id } }, body: { note } }), "/api/proposals/approve");
}

export async function rejectProposal(id: string, note?: string): Promise<Proposal> {
  return unwrap(await api.POST("/api/proposals/{id}/reject", { params: { path: { id } }, body: { note } }), "/api/proposals/reject");
}

export async function editStep(id: string, stepId: string, edit: StepEdit): Promise<Proposal> {
  return unwrap(
    await api.PATCH("/api/proposals/{id}/steps/{step_id}", { params: { path: { id, step_id: stepId } }, body: edit }),
    "/api/proposals/steps",
  );
}

export async function runStep(id: string, stepId: string): Promise<Proposal> {
  return unwrap(await api.POST("/api/proposals/{id}/steps/{step_id}/run", { params: { path: { id, step_id: stepId } } }), "/api/proposals/run");
}

export const PROPOSALS_KEY = ["proposals"] as const;

/** Every proposal, kept current by `/ws/jobs`; toasts once per proposal that arrives pending. */
export function useProposals(): Proposal[] | undefined {
  const queryClient = useQueryClient();
  const { proposalRev } = useJobsStream();
  const query = useQuery({ queryKey: PROPOSALS_KEY, queryFn: listProposals, enabled: !isProjectHome });
  useEffect(() => {
    if (proposalRev) void queryClient.invalidateQueries({ queryKey: PROPOSALS_KEY });
  }, [proposalRev, queryClient]);
  return query.data;
}

/** Mounted once (the nav rail): a toast for each proposal that arrives while the app is open. */
export function useProposalToasts(proposals: Proposal[] | undefined): void {
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!proposals) return;
    const pending = proposals.filter((p) => p.status === "pending");
    if (seen.current === null) {
      seen.current = new Set(pending.map((p) => p.id)); // already waiting when the app opened
      return;
    }
    for (const p of pending) {
      if (seen.current.has(p.id)) continue;
      seen.current.add(p.id);
      notify.info(`${proposer(p)} proposes “${p.title}” — review it on the Jobs page.`);
    }
  }, [proposals]);
}

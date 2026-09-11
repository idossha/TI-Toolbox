import { useEffect, useSyncExternalStore } from "react";
import { api, unwrap, wsUrl } from "../../api/client";
import { JobsStream, type JobsStreamState } from "./jobsStream";
import type { JobStatus } from "./types";

/** `GET /api/jobs` — seeds the shared store on every connect (see `jobsStream.ts`'s `seed`
 * option) so the rail and the Jobs table read the exact same merged data (ra_12 #4). */
async function seedJobs(): Promise<JobStatus[]> {
  return unwrap(await api.GET("/api/jobs", { params: { query: {} } }), "/api/jobs");
}

/**
 * One shared `/ws/jobs` connection for the whole app (the rail and, later, the full Jobs page
 * both read it) — started by the first mounted consumer, stopped when the last one unmounts.
 * Acquire/release live in an effect, matching `ws/useSystemStream.ts`, so StrictMode's mount →
 * unmount → mount rehearsal doesn't leak a socket.
 */
const IDLE: JobsStreamState = { status: "idle", jobs: {}, eventsByJob: {}, attempt: 0 };
const listeners = new Set<() => void>();
let shared: JobsStream | null = null;
let users = 0;

function notify(): void {
  for (const l of listeners) l();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getJobsState(): JobsStreamState {
  return shared ? shared.getState() : IDLE;
}

export function acquireJobsStream(): void {
  users += 1;
  if (!shared) {
    shared = new JobsStream({ url: wsUrl("/ws/jobs"), seed: seedJobs });
    shared.subscribe(notify);
    shared.start();
    notify();
  }
}

export function releaseJobsStream(): void {
  users = Math.max(0, users - 1);
  if (users === 0 && shared) {
    shared.stop();
    shared = null;
    notify();
  }
}

/** Subscribe (or resume from `sinceSeq`) to one job's events on the shared connection. */
export function subscribeJob(jobId: string, sinceSeq = 0): void {
  shared?.subscribeJob(jobId, sinceSeq);
}

/** Stop receiving one job's events and drop its buffered event ring. */
export function unsubscribeJob(jobId: string): void {
  shared?.unsubscribeJob(jobId);
}

export function useJobsStream(): JobsStreamState {
  useEffect(() => {
    acquireJobsStream();
    return releaseJobsStream;
  }, []);
  return useSyncExternalStore(subscribe, getJobsState);
}

/** Forget a job only after the server confirms deletion. */
export function forgetJob(jobId: string): void {
  shared?.forgetJob(jobId);
}

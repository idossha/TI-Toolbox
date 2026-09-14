import type { CandidateDetail, CandidatePage, CandidateRun } from "./model";
const ROOT = "/api/catalog/optimization-candidates";
async function read<T>(path: string, query: URLSearchParams, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${path}?${query}`, { signal, credentials: "same-origin", headers: { accept: "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === "string" ? body.detail : `Candidate request failed (HTTP ${response.status}).`);
  }
  return response.json() as Promise<T>;
}
export function getCandidates(run: CandidateRun, offset: number, sort: string, descending: boolean, limit = 50, signal?: AbortSignal): Promise<CandidatePage> {
  return read(ROOT, new URLSearchParams({ ...run, offset: String(offset), limit: String(limit), sort, descending: String(descending) }), signal);
}
export function getCandidate(run: CandidateRun, id: string): Promise<CandidateDetail> {
  return read(`${ROOT}/${encodeURIComponent(id)}`, new URLSearchParams({ ...run }));
}

/** Bound SVG/geometry memory; the UI explicitly reports any incomplete history. */
export const HISTORY_LIMIT = 10_000;
export async function getCandidateHistory(run: CandidateRun, sort: string, descending: boolean, signal?: AbortSignal): Promise<CandidatePage> {
  const candidates: CandidatePage["candidates"] = [];
  let total: number, legacy: boolean;
  do {
    const page = await getCandidates(run, candidates.length, sort, descending, 500, signal);
    total = page.total; legacy = page.legacy;
    if (!page.candidates.length) break;
    candidates.push(...page.candidates);
  } while (candidates.length < total && candidates.length < HISTORY_LIMIT);
  return { candidates: candidates.slice(0, HISTORY_LIMIT), total, legacy };
}

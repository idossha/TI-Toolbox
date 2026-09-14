import { afterEach, expect, it, vi } from "vitest";
import { getCandidateHistory } from "../../src/renderer/pages/results/candidates/api";
const run = { subject: "ernie", kind: "flex" as const, run: "recorded" };
afterEach(() => vi.unstubAllGlobals());
it("loads sorted pages beyond the table page and forwards cancellation", async () => {
  const signal = new AbortController().signal;
  const offsets: number[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, options: RequestInit) => {
    expect(options.signal).toBe(signal);
    const query = new URL(url, "http://localhost").searchParams;
    expect(query.get("limit")).toBe("500");
    expect(query.get("sort")).toBe("roi_mean");
    const offset = Number(query.get("offset")); offsets.push(offset);
    return { ok: true, json: async () => ({ candidates: Array.from({ length: offset === 0 ? 500 : 17 }, (_, i) => ({ id: String(offset + i) })), total: 517, legacy: false }) };
  }));
  const result = await getCandidateHistory(run, "roi_mean", true, signal);
  expect(offsets).toEqual([0, 500]);
  expect(result.candidates).toHaveLength(517);
  expect(result.candidates.at(-1)?.id).toBe("516");
});
it("bounds the history and retains the total so incomplete plots are disclosed", async () => {
  let requests = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    requests++;
    return { ok: true, json: async () => ({ candidates: Array.from({ length: 500 }, (_, i) => ({ id: `${requests}-${i}` })), total: 20_000, legacy: false }) };
  }));
  const result = await getCandidateHistory(run, "roi_mean", true);
  expect(requests).toBe(20);
  expect(result.candidates).toHaveLength(10_000);
  expect(result.total).toBe(20_000);
});
it("propagates an aborted request without starting another page", async () => {
  const fetcher = vi.fn().mockRejectedValue(new DOMException("Stopped", "AbortError"));
  vi.stubGlobal("fetch", fetcher);
  await expect(getCandidateHistory(run, "roi_mean", true)).rejects.toMatchObject({ name: "AbortError" });
  expect(fetcher).toHaveBeenCalledTimes(1);
});

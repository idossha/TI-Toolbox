/**
 * `GET /api/jobs/{id}/events?since=` is the console's whole backlog, and its `since` is INCLUSIVE
 * with a contract minimum of 0 (`contracts/openapi.yaml`; `tit/jobs/tailer.py::read_events` keeps
 * every event with `seq >= since`).
 *
 * The renderer used to default to `since=-1`. The mock server accepted it (it filtered `seq > since`),
 * so the whole e2e suite was green — but a real `tit.server` answers 422:
 *
 *   $ curl -s -o /dev/null -w '%{http_code}' \
 *       'http://127.0.0.1:8765/api/jobs/9f8c260536f44a8d/events?since=-1'   # 422
 *   $ curl -s -o /dev/null -w '%{http_code}' \
 *       'http://127.0.0.1:8765/api/jobs/9f8c260536f44a8d/events?since=0'    # 200
 *
 * so every console that read a real job got no backlog at all, and a job that had already finished
 * (nothing is streamed over `/ws/jobs` for a terminal job) showed an empty terminal.
 */
import { describe, expect, it, vi } from "vitest";

const calls: { path: string; init: unknown }[] = [];
vi.mock("../../src/renderer/api/client", () => ({
  api: {
    GET: (path: string, init: unknown) => {
      calls.push({ path, init });
      return Promise.resolve({ data: [], response: new Response("[]", { status: 200 }) });
    },
  },
  unwrap: <T,>(result: { data?: T }) => result.data,
}));

import { getJobEvents } from "../../src/renderer/app/jobs-rail/api";

function lastCall(): { path: string; init: unknown } {
  const call = calls[calls.length - 1];
  if (!call) throw new Error("no request was made");
  return call;
}

function lastQuery(): Record<string, unknown> {
  return (lastCall().init as { params: { query: Record<string, unknown> } }).params.query;
}

describe("getJobEvents since", () => {
  it("asks for the whole history with the smallest value the contract allows", async () => {
    await getJobEvents("j1");
    expect(lastCall().path).toBe("/api/jobs/{id}/events");
    expect(lastQuery().since).toBe(0);
  });

  it("never sends a negative sequence number, which a real server rejects with 422", async () => {
    await getJobEvents("j1");
    await getJobEvents("j1", 12);
    for (const call of calls) {
      const since = (call.init as { params: { query: { since: number } } }).params.query.since;
      expect(Number.isInteger(since)).toBe(true);
      expect(since).toBeGreaterThanOrEqual(0);
    }
  });
});

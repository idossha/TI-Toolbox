// @vitest-environment jsdom
/** Authored final transcript must replace delayed socket replay and retain its final line. */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { useJobLogEvents } from "../../src/renderer/app/jobs/useJobLogEvents";
import type { JobEvent, JobState } from "../../src/renderer/app/jobs/types";
const mocks = vi.hoisted(() => ({ getJobEvents: vi.fn(), subscribeJob: vi.fn(), unsubscribeJob: vi.fn(), eventsByJob: {} as Record<string, JobEvent[]> }));
vi.mock("../../src/renderer/app/jobs-rail/api", () => ({ getJobEvents: mocks.getJobEvents, TERMINAL_STATES: ["succeeded", "failed", "cancelled", "lost", "skipped"] }));
vi.mock("../../src/renderer/app/jobs/useJobsStream", () => ({ subscribeJob: mocks.subscribeJob, unsubscribeJob: mocks.unsubscribeJob, useJobsStream: () => ({ eventsByJob: mocks.eventsByJob }) }));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); mocks.eventsByJob = {}; });
it.each<JobState>(["succeeded", "failed", "cancelled"])("settles on the complete final transcript after %s", async (state) => {
  vi.useFakeTimers();
  const event = (seq: number, msg: string): JobEvent => ({ seq, msg, ts: seq, type: "log" });
  mocks.getJobEvents.mockResolvedValueOnce([event(0, "start")]).mockResolvedValueOnce([event(0, "start"), event(1, "last evaluation"), event(2, "final report")]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const container = document.createElement("div"); const root = createRoot(container);
  function Probe({ state }: { state: JobState }) { const { lines } = useJobLogEvents("j1", state); return <pre>{lines.map((line) => line.text).join("\n")}</pre>; }
  async function render(state: JobState) {
    await act(async () => { root.render(<QueryClientProvider client={client}><Probe state={state} /></QueryClientProvider>); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
  }
  try {
    await render("running"); expect(container.textContent).toBe("start");
    mocks.eventsByJob = { j1: [event(1, "last evaluation")] }; await render("running"); expect(container.textContent).toContain("last evaluation");
    await render(state); expect(mocks.unsubscribeJob).toHaveBeenCalledWith("j1"); expect(container.textContent).toBe("start\nlast evaluation\nfinal report");
    mocks.eventsByJob = { j1: [event(1, "stale replay")] }; await render(state);
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(container.textContent).toBe("start\nlast evaluation\nfinal report"); expect(mocks.getJobEvents).toHaveBeenCalledTimes(2);
  } finally { act(() => root.unmount()); client.clear(); }
});

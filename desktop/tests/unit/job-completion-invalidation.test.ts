import { describe, expect, it, vi } from "vitest";
import type { QueryClient } from "@tanstack/react-query";
import { completedBetween, invalidateForJobs, queriesAffectedBy } from "../../src/renderer/app/jobs/invalidation";
import type { JobStatus } from "../../src/renderer/app/jobs/types";

function job(id: string, kind: string, state: JobStatus["state"]): JobStatus {
  return { id, kind, state } as unknown as JobStatus;
}

function keysOf(kind: string): string[] {
  return queriesAffectedBy(kind).map((k) => JSON.stringify(k));
}

describe("queriesAffectedBy", () => {
  it("a finished simulation reaches the Analyzer's simulation picker and the Viewer/Results lists", () => {
    const keys = keysOf("sim");
    for (const k of [["simulations"], ["results-simulations"], ["viewer-tree"], ["viewer-candidates"], ["subject-detail"], ["overview"]]) {
      expect(keys).toContain(JSON.stringify(k));
    }
  });

  it("a finished flex search reaches the Simulator's montage sources and the search results", () => {
    for (const kind of ["flex", "flex_adaptive", "flex_pareto"]) {
      const keys = keysOf(kind);
      expect(keys).toContain(JSON.stringify(["flex-runs"]));
      expect(keys).toContain(JSON.stringify(["flex-mapping"]));
      expect(keys).toContain(JSON.stringify(["results-flex-runs"]));
    }
    for (const kind of ["ex", "mex", "recip"]) {
      expect(keysOf(kind)).toContain(JSON.stringify(["results-ex-runs"]));
      expect(keysOf(kind)).toContain(JSON.stringify(["optimization-candidates"]));
    }
  });

  it("finished preprocessing reaches every subject list and the head-model-derived pickers", () => {
    const keys = keysOf("pre");
    for (const k of [["subjects"], ["subject-detail"], ["jobs-subjects"], ["eeg-nets"], ["atlases"], ["scene"]]) {
      expect(keys).toContain(JSON.stringify(k));
    }
  });

  it("a finished analysis reaches the Results analyses list and the Overview", () => {
    const keys = keysOf("analyzer");
    expect(keys).toContain(JSON.stringify(["results-analyses"]));
    expect(keys).toContain(JSON.stringify(["overview"]));
  });

  it("leadfields keep the invalidation the Optimizer used to do on its own", () => {
    expect(keysOf("leadfield")).toContain(JSON.stringify(["leadfields"]));
  });

  it("an unknown kind still refreshes the common rollups, with no duplicate keys", () => {
    const keys = keysOf("something_new");
    expect(keys).toContain(JSON.stringify(["overview"]));
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe("completedBetween", () => {
  it("reports only jobs that moved from a live state into a terminal one", () => {
    const previous = { a: job("a", "sim", "running"), b: job("b", "sim", "queued"), c: job("c", "pre", "succeeded") };
    const next = { a: job("a", "sim", "succeeded"), b: job("b", "sim", "queued"), c: job("c", "pre", "succeeded"), d: job("d", "flex", "failed") };
    expect(completedBetween(previous, next).map((j) => j.id)).toEqual(["a"]);
  });

  it("treats failed and cancelled transitions as completions too", () => {
    const previous = { a: job("a", "pre", "running"), b: job("b", "sim", "running") };
    const next = { a: job("a", "pre", "failed"), b: job("b", "sim", "cancelled") };
    expect(completedBetween(previous, next).map((j) => j.id)).toEqual(["a", "b"]);
  });

  it("ignores history replayed by the connect-time seed", () => {
    expect(completedBetween({}, { a: job("a", "sim", "succeeded") })).toEqual([]);
  });
});

describe("invalidateForJobs", () => {
  it("invalidates each affected key once across several finished jobs", () => {
    const invalidateQueries = vi.fn();
    const client = { invalidateQueries } as unknown as QueryClient;
    invalidateForJobs(client, [job("a", "sim", "succeeded"), job("b", "sim", "succeeded"), job("c", "flex", "succeeded")]);
    const called = invalidateQueries.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(new Set(called).size).toBe(called.length);
    expect(called).toContain(JSON.stringify(["simulations"]));
    expect(called).toContain(JSON.stringify(["flex-runs"]));
  });
});

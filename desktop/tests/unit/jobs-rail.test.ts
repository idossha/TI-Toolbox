/**
 * The pure parts of the jobs component family: rail overflow, the density contract shared by the
 * three heights, and the UI store the three heights read.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { densitySpec, overflowTooltip, RAIL_MAX_TRACES, splitRailJobs } from "../../src/renderer/app/jobs-rail/model";
import { activeFilterCount, ALL, applyJobsFilters, NO_FILTERS, useJobsUi } from "../../src/renderer/app/jobs-rail/store";
import type { JobStatus } from "../../src/renderer/app/jobs-rail/api";

function job(id: string, state: string, kind = "sim", subjects = ["ernie"]): JobStatus {
  return {
    id,
    kind,
    state,
    subject_ids: subjects,
    created_at: "2026-09-02T12:00:00Z",
    artifacts: [],
  } as unknown as JobStatus;
}

describe("splitRailJobs", () => {
  it("draws every job when they fit", () => {
    const jobs = [job("a", "running"), job("b", "running")];
    const split = splitRailJobs(jobs, 6);
    expect(split.traces).toHaveLength(2);
    expect(split.overflow).toHaveLength(0);
    expect(split.overflowLabel).toBeNull();
  });

  it("collapses the tail into one '+N queued' chip instead of clipping chips mid-word", () => {
    // The reported bug: eight queued jobs rendered eight traces in a scroller, so the last ones
    // were cut through the middle of their subject id.
    const jobs = [job("r", "running"), ...Array.from({ length: 8 }, (_, i) => job(`q${i}`, "queued"))];
    const split = splitRailJobs(jobs, 6);
    expect(split.traces).toHaveLength(6);
    expect(split.overflow).toHaveLength(3);
    expect(split.overflowLabel).toBe("+3 queued");
  });

  it("says '+N more' when the overflow is not all queued", () => {
    const jobs = Array.from({ length: 8 }, (_, i) => job(`r${i}`, "running"));
    expect(splitRailJobs(jobs, 6).overflowLabel).toBe("+2 more");
  });

  it("never overflows at exactly the cap", () => {
    const jobs = Array.from({ length: RAIL_MAX_TRACES }, (_, i) => job(`q${i}`, "queued"));
    expect(splitRailJobs(jobs).overflowLabel).toBeNull();
  });

  it("lists the hidden jobs in the chip's tooltip", () => {
    const hidden = [job("q1", "queued", "sim", ["ernie"]), job("q2", "queued", "flex", ["101"]), job("q3", "queued", "pre", [])];
    expect(overflowTooltip(hidden)).toBe("sim · ernie, flex · 101, pre · project");
  });
});

describe("table density", () => {
  it("is ONE density: the panel and the page use the same 28px row (DESIGN.md §3.3)", () => {
    expect(densitySpec("panel").rowH).toBe(28);
    expect(densitySpec("page").rowH).toBe(28);
  });

  it("gives the filters/grouping toolbar to the full page only", () => {
    expect(densitySpec("page").toolbar).toBe(true);
    expect(densitySpec("panel").toolbar).toBe(false);
  });
});

describe("jobs UI store", () => {
  beforeEach(() => {
    useJobsUi.setState({ selectedId: null, tab: "jobs", filters: NO_FILTERS, grouped: false });
  });

  it("shares the selection across the three heights", () => {
    useJobsUi.getState().select("job-7");
    expect(useJobsUi.getState().selectedId).toBe("job-7");
  });

  it("moves off the Host tab when a job is selected — Host shows no job", () => {
    useJobsUi.getState().setTab("host");
    useJobsUi.getState().select("job-7");
    expect(useJobsUi.getState().tab).toBe("jobs");
  });

  it("keeps a job-shaped tab when a job is selected", () => {
    useJobsUi.getState().setTab("console");
    useJobsUi.getState().select("job-8");
    expect(useJobsUi.getState().tab).toBe("console");
  });

  it("filters by state, kind and subject together", () => {
    const jobs = [
      job("a", "running", "sim", ["ernie"]),
      job("b", "queued", "analyzer", ["ernie"]),
      job("c", "running", "sim", ["101"]),
    ];
    expect(applyJobsFilters(jobs, { state: ALL, kind: "sim", subject: ALL }).map((j) => j.id)).toEqual(["a", "c"]);
    expect(applyJobsFilters(jobs, { state: "running", kind: "sim", subject: "101" }).map((j) => j.id)).toEqual(["c"]);
    expect(applyJobsFilters(jobs, NO_FILTERS)).toHaveLength(3);
  });

  it("counts the narrowing filters", () => {
    expect(activeFilterCount(NO_FILTERS)).toBe(0);
    expect(activeFilterCount({ state: "running", kind: ALL, subject: "ernie" })).toBe(2);
  });
});

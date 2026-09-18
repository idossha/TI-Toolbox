/**
 * `pages/overview/recentModel.ts` — the Overview's "Recent jobs" row model.
 *
 * The destination mapping is the part worth pinning: a row that leads somewhere with nothing in it
 * is worse than no row, so "which jobs go to Results" is asserted kind by kind rather than
 * described in a comment.
 */
import { describe, expect, it } from "vitest";
import type { JobStatus } from "../../src/renderer/app/jobs-rail/api";
import {
  RECENT_JOBS_LIMIT,
  destinationFor,
  durationLabel,
  recentJobRows,
  relativeTime,
  runNameOf,
} from "../../src/renderer/pages/overview/recentModel";

const NOW = Date.parse("2026-09-17T12:00:00Z");

function job(patch: Partial<JobStatus> = {}): JobStatus {
  return {
    id: "j1",
    kind: "sim",
    state: "succeeded",
    subject_ids: ["ernie"],
    created_at: "2026-09-17T11:00:00Z",
    started_at: "2026-09-17T11:00:05Z",
    finished_at: "2026-09-17T11:03:17Z",
    artifacts: [{ path: "/p/derivatives/SimNIBS/sub-ernie/Simulations/run_a/TI/mesh/x.msh", kind: "mesh" }],
    ...patch,
  } as JobStatus;
}

describe("destinationFor", () => {
  it("sends a finished job of a browsable kind to Results, scoped to its subject", () => {
    for (const kind of ["sim", "flex", "flex_adaptive", "flex_pareto", "ex", "mex", "analyzer", "stats", "report"] as JobStatus["kind"][]) {
      expect(destinationFor(job({ kind })), kind).toEqual({ page: "results", subject: "ernie" });
    }
  });

  it("sends a kind Results does not browse to the Jobs page instead", () => {
    for (const kind of ["leadfield", "project_init", "pre", "tools", "source", "blender"] as JobStatus["kind"][]) {
      expect(destinationFor(job({ kind })), kind).toEqual({ page: "jobs", jobId: "j1" });
    }
  });

  it("sends a running, queued or failed job to the Jobs page, on its log", () => {
    for (const state of ["queued", "running", "failed", "cancelled", "lost", "skipped"] as const) {
      expect(destinationFor(job({ state })), state).toEqual({ page: "jobs", jobId: "j1" });
    }
  });

  it("sends a job that wrote nothing to the Jobs page, not to an empty Results", () => {
    expect(destinationFor(job({ artifacts: [] }))).toEqual({ page: "jobs", jobId: "j1" });
  });

  it("carries a null subject for a project-level job", () => {
    expect(destinationFor(job({ kind: "stats", subject_ids: [] }))).toEqual({ page: "results", subject: null });
  });
});

describe("runNameOf", () => {
  it("names the directory a job's outputs share", () => {
    expect(
      runNameOf(
        job({
          artifacts: [
            { path: "/p/sub-ernie/Simulations/mock_7/report/report.html", kind: "report" },
            { path: "/p/sub-ernie/Simulations/mock_7/TI/mesh/ernie_TI.msh", kind: "mesh" },
          ],
        } as Partial<JobStatus>),
      ),
    ).toBe("mock_7");
  });

  it("uses the one artifact's own directory when there is only one", () => {
    expect(runNameOf(job({ artifacts: [{ path: "/p/flex-search/run_b/manifest.json", kind: "manifest" }] } as Partial<JobStatus>))).toBe(
      "run_b",
    );
  });

  it("is null when the job wrote nothing", () => {
    expect(runNameOf(job({ artifacts: [] }))).toBeNull();
  });
});

describe("relativeTime", () => {
  it("reads in the grain a list of eight rows wants", () => {
    expect(relativeTime("2026-09-17T11:59:40Z", NOW)).toBe("just now");
    expect(relativeTime("2026-09-17T11:48:00Z", NOW)).toBe("12m ago");
    expect(relativeTime("2026-09-17T09:00:00Z", NOW)).toBe("3h ago");
    expect(relativeTime("2026-09-15T12:00:00Z", NOW)).toBe("2d ago");
    expect(relativeTime(null, NOW)).toBe("—");
    expect(relativeTime("not a date", NOW)).toBe("—");
  });
});

describe("durationLabel", () => {
  it("measures start to finish, and start to now while it runs", () => {
    expect(durationLabel(job(), NOW)).toBe("3m 12s");
    expect(durationLabel(job({ started_at: "2026-09-17T11:59:15Z", finished_at: null, state: "running" }), NOW)).toBe("45s");
    expect(durationLabel(job({ started_at: null, finished_at: null, state: "queued" }), NOW)).toBe("—");
  });
});

describe("recentJobRows", () => {
  it("is newest first and eight rows by default", () => {
    const jobs = Array.from({ length: 12 }, (_, i) =>
      job({ id: `j${i}`, created_at: new Date(NOW - i * 60_000).toISOString() }),
    );
    const rows = recentJobRows(jobs.slice().reverse(), NOW);
    expect(rows).toHaveLength(RECENT_JOBS_LIMIT);
    expect(rows.map((r) => r.id)).toEqual(["j0", "j1", "j2", "j3", "j4", "j5", "j6", "j7"]);
  });

  it("labels a job with no subject as project work", () => {
    expect(recentJobRows([job({ subject_ids: [] })], NOW)[0]!.subjects).toBe("project");
  });
});

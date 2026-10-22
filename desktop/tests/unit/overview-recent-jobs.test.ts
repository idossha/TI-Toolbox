// @vitest-environment jsdom
/**
 * `pages/overview/recentModel.ts` — the Overview's "Recent jobs" row model.
 *
 * The destination mapping is the part worth pinning: a row that leads somewhere with nothing in it
 * is worse than no row, so "which jobs go to Results" is asserted kind by kind rather than
 * described in a comment.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JobStatus } from "../../src/renderer/app/jobs-rail/api";
import {
  RECENT_JOBS_LIMIT,
  destinationFor,
  durationLabel,
  recentJobRows,
  relativeTime,
  runNameOf,
} from "../../src/renderer/pages/overview/recentModel";
import { RecentJobs } from "../../src/renderer/pages/overview/RecentJobs";
import { useSubjectSpine } from "../../src/renderer/app/subjectSpine";
import { clearSubjectPages, readStoredSubject, useSubjectContext } from "../../src/renderer/app/subjectContext";
import { RESULTS_ROW_STATE } from "../../src/renderer/pages/results/useOutputs";
import { GROUP_SUBJECT } from "../../src/renderer/pages/results/outputsTree";

const NOW = Date.parse("2026-09-17T12:00:00Z");

/** The jobs the mocked `/ws/jobs` store holds for the rendered section below. */
const jobsStore = vi.hoisted(() => ({ all: [] as unknown[] }));
vi.mock("../../src/renderer/app/jobs-rail/model", async (original) => ({
  ...(await original<object>()),
  useJobsModel: () => ({
    all: jobsStore.all,
    active: [],
    runningCount: 0,
    now: Date.parse("2026-09-17T12:00:00Z"),
    isLoading: false,
    isRefetching: false,
    error: null,
    refetch: () => {},
  }),
}));
vi.mock("../../src/renderer/api/client", async (original) => ({
  ...(await original<object>()),
  getProject: vi.fn(async () => ({ name: "example", container_path: "/mnt/example", host_path: null })),
}));

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
  it("sends a finished job of a per-subject kind to Results, scoped to its subject", () => {
    for (const kind of ["sim", "flex", "flex_adaptive", "flex_pareto", "ex", "mex", "analyzer"] as JobStatus["kind"][]) {
      expect(destinationFor(job({ kind })), kind).toEqual({ page: "results", subject: "ernie" });
    }
  });

  // Results lists group statistics, nilearn visuals and NIfTI averages only under its `Group`
  // pseudo-subject (`outputsTree.ts::groupOutputsFor`), never in a subject's tree.
  it("sends a finished group-level job to Results' Group row, whatever subjects it covered", () => {
    for (const kind of ["stats", "nilearn", "nifti_average"] as JobStatus["kind"][]) {
      expect(destinationFor(job({ kind, subject_ids: ["101", "LA", "ernie"] })), kind).toEqual({ page: "results", subject: "Group" });
      expect(destinationFor(job({ kind, subject_ids: [] })), `${kind} with no subjects`).toEqual({ page: "results", subject: "Group" });
    }
  });

  it("sends a kind Results does not browse to the Jobs page instead", () => {
    for (const kind of ["leadfield", "project_init", "pre", "tools", "source", "blender"] as JobStatus["kind"][]) {
      expect(destinationFor(job({ kind })), kind).toEqual({ page: "jobs", jobId: "j1" });
    }
  });

  it("sends an unfinished or empty group-level job to the Jobs page, on its log", () => {
    expect(destinationFor(job({ kind: "stats", state: "failed" }))).toEqual({ page: "jobs", jobId: "j1" });
    expect(destinationFor(job({ kind: "nilearn", state: "running" }))).toEqual({ page: "jobs", jobId: "j1" });
    expect(destinationFor(job({ kind: "nifti_average", artifacts: [] }))).toEqual({ page: "jobs", jobId: "j1" });
  });

  it("sends a running, queued or failed job to the Jobs page, on its log", () => {
    for (const state of ["queued", "running", "failed", "cancelled", "lost", "skipped"] as const) {
      expect(destinationFor(job({ state })), state).toEqual({ page: "jobs", jobId: "j1" });
    }
  });

  it("sends a job that wrote nothing to the Jobs page, not to an empty Results", () => {
    expect(destinationFor(job({ artifacts: [] }))).toEqual({ page: "jobs", jobId: "j1" });
  });

  it("carries a null subject for a per-subject kind recorded without one", () => {
    expect(destinationFor(job({ kind: "sim", subject_ids: [] }))).toEqual({ page: "results", subject: null });
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

  it("takes a `dir` artifact as the run folder itself, not its parent", () => {
    // A simulation registers its montage directory and then its mesh three levels down; the run
    // is the montage, not "Simulations".
    expect(
      runNameOf(
        job({
          artifacts: [
            { path: "/p/Simulations/L_Insula", kind: "dir" },
            { path: "/p/Simulations/L_Insula/TI/mesh/L_Insula_TI.msh", kind: "mesh" },
          ],
        } as Partial<JobStatus>),
      ),
    ).toBe("L_Insula");
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

// The section's click, followed through the real subject spine (`app/subjectSpine.ts`): the spine
// adopts a link's `state.subject` as the shell's subject and the project's remembered one. `Group`
// is a Results row, not a subject, so following a group job must leave both on the subject that
// was open, while a per-subject job still re-scopes them to its subject.
describe("RecentJobs, followed through the subject spine", () => {
  // This jsdom's localStorage is a partial shim; the spine's store swallows its errors, so a real
  // in-memory one keeps a broken write from passing as "nothing remembered".
  const stored = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => stored.get(k) ?? null,
      setItem: (k: string, v: string) => void stored.set(k, String(v)),
      removeItem: (k: string) => void stored.delete(k),
      clear: () => stored.clear(),
      key: (i: number) => [...stored.keys()][i] ?? null,
      get length() {
        return stored.size;
      },
    },
  });
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  let container: HTMLDivElement;
  let root: Root;
  let at: { pathname: string; search: string; state: Record<string, unknown> | null };

  function Probe() {
    useSubjectSpine();
    const l = useLocation();
    at = { pathname: l.pathname, search: l.search, state: l.state as Record<string, unknown> | null };
    return null;
  }

  async function settle(): Promise<void> {
    for (let i = 0; i < 10; i++) await act(async () => await new Promise((r) => setTimeout(r, 5)));
  }

  /** Overview with `subject` open, then a click on `row`'s Recent jobs entry. */
  async function follow(row: JobStatus, subject: string): Promise<void> {
    jobsStore.all = [row];
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    act(() =>
      root.render(
        createElement(
          QueryClientProvider,
          { client },
          createElement(MemoryRouter, { initialEntries: ["/overview"] }, createElement(Probe), createElement(RecentJobs)),
        ),
      ),
    );
    await settle();
    act(() => useSubjectContext.getState().setSubject(subject));
    await settle();
    // The spine has published the open subject before the click: the starting point is real.
    expect(at.search).toBe(`?subject=${subject}`);
    expect(readStoredSubject("example")).toBe(subject);
    await act(async () => container.querySelector<HTMLButtonElement>(`[data-testid="overview-recent-${row.id}"]`)!.click());
    await settle();
    expect(at.pathname).toBe("/results");
  }

  beforeEach(() => {
    stored.clear();
    act(() => clearSubjectPages());
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("opens a group job on Results' Group row and leaves the open subject, and the remembered one, alone", async () => {
    await follow(job({ id: "g1", kind: "stats", subject_ids: ["101", "LA", "ernie"] }), "ernie");
    expect(at.state?.[RESULTS_ROW_STATE]).toBe(GROUP_SUBJECT);
    expect(useSubjectContext.getState().subjectId).toBe("ernie");
    expect(at.search).toBe("?subject=ernie");
    expect(readStoredSubject("example")).toBe("ernie");
  });

  it("re-scopes the shell to a per-subject job's subject", async () => {
    await follow(job({ id: "s1", kind: "sim", subject_ids: ["101"] }), "ernie");
    expect(useSubjectContext.getState().subjectId).toBe("101");
    expect(at.search).toBe("?subject=101");
    expect(readStoredSubject("example")).toBe("101");
  });
});

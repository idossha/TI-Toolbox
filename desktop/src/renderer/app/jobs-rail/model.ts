/**
 * The ONE data source behind all three heights of the jobs component (plan §1, "Jobs is one
 * component at three heights"): the 32px rail, the 260px panel (⌘J) and the full `jobs` page all
 * call `useJobsModel()` and therefore cannot disagree about what is running.
 *
 * It is the `/ws/jobs` store (`app/jobs/useJobsStream`, shared socket) merged with one
 * `GET /api/jobs` seed, exactly as the rail and the Jobs page each used to do separately.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useJobsStream } from "../jobs/useJobsStream";
import type { JobState } from "../../ui/Status";
import { listJobs, type JobStatus } from "./api";
import { mergeJobs } from "./format";

export const RUNNING_STATES: JobState[] = ["queued", "running"];

/** DESIGN.md quality floor ("never just vanishes"): a job that leaves a running state keeps its
 * trace in the collapsed rail, showing its final `JobStateChip`, for this long before it's dropped. */
export const FINISHED_LINGER_MS = 4000;

/**
 * How many traces the 32px rail draws before the rest become one "+N queued" chip. Six is the cap
 * at any width; `fitTraces` lowers it to whatever actually fits, so a trace is never squeezed or
 * clipped by the rail's right edge the way the old horizontal scroller clipped the seventh chip
 * mid-word.
 */
export const RAIL_MAX_TRACES = 6;

/** One rail trace is a fixed-width slot (`jobs-rail.css`), plus the 8px flex gap after it. */
export const RAIL_TRACE_W = 172;
/** Room kept for the "+N queued" chip, so the chip itself never causes the overflow it reports. */
export const RAIL_OVERFLOW_RESERVE = 96;

/**
 * How many traces fit in `width` px of rail. At least one — a rail that shows nothing but a chip
 * has stopped being the signature element — and never more than the cap.
 */
export function fitTraces(width: number): number {
  const usable = width - RAIL_OVERFLOW_RESERVE;
  return Math.max(1, Math.min(RAIL_MAX_TRACES, Math.floor(usable / RAIL_TRACE_W)));
}

export function isRunning(job: { state: string }): boolean {
  return RUNNING_STATES.includes(job.state as JobState);
}

/** "3m 12s" for a rail trace; the table uses the same helper from `./format`. */
export interface RailSplit<T> {
  /** Jobs that get their own `JobTrace`. */
  traces: T[];
  /** Everything that did not fit, collapsed behind one chip. */
  overflow: T[];
  /** The chip's label, or null when nothing overflowed. */
  overflowLabel: string | null;
}

/**
 * Rail overflow. The old rail rendered every active job into a horizontally scrolling strip, so
 * eight queued jobs produced eight chips clipped mid-word at the right edge. Running work always
 * keeps its trace — that is the signature — and the remainder collapses into one chip whose label
 * names what it is hiding ("+5 queued"), with the full list in its tooltip.
 *
 * `jobs` must already be ordered the way the rail draws them (running first, then queued, newest
 * first within each) — `useJobsModel().active` is.
 */
export function splitRailJobs<T extends { state: string }>(jobs: T[], max = RAIL_MAX_TRACES): RailSplit<T> {
  if (jobs.length <= max) return { traces: jobs, overflow: [], overflowLabel: null };
  const traces = jobs.slice(0, max);
  const overflow = jobs.slice(max);
  const allQueued = overflow.every((j) => j.state === "queued");
  return { traces, overflow, overflowLabel: `+${overflow.length} ${allQueued ? "queued" : "more"}` };
}

/** "sim · ernie, flex · 101, …" — what the overflow chip's tooltip lists. */
export function overflowTooltip(jobs: { kind: string; subject_ids: string[] }[]): string {
  return jobs.map((j) => `${j.kind} · ${j.subject_ids.join(", ") || "project"}`).join(", ");
}

/**
 * Table density. There is ONE shipped density (DESIGN.md §3.3) — a compact/comfortable switch
 * means two sets of screenshots and two sets of bugs — so both call sites resolve to the same
 * 28px row. What differs is how much room the table has and therefore what chrome it carries:
 * the panel is 260px tall beside a detail pane and scrolls internally with no toolbar of its own;
 * the page fills the work area and owns the filter/grouping toolbar.
 */
export type JobsTableDensity = "panel" | "page";

export interface JobsDensitySpec {
  /** px. Equal for both by design — asserted by `tests/unit/jobs-table.test.tsx`. */
  rowH: number;
  /** Does this height draw the filters + grouping toolbar? */
  toolbar: boolean;
}

const DENSITY: Record<JobsTableDensity, JobsDensitySpec> = {
  panel: { rowH: 28, toolbar: false },
  page: { rowH: 28, toolbar: true },
};

export function densitySpec(density: JobsTableDensity): JobsDensitySpec {
  return DENSITY[density];
}

export interface JobsModel {
  /** Every job, newest first. */
  all: JobStatus[];
  /** Running or queued, plus anything that finished in the last `FINISHED_LINGER_MS`. */
  active: JobStatus[];
  /** Running or queued only — what the shell counts in the context bar. */
  runningCount: number;
  now: number;
  /** First load only. A refetch keeps the rows and shows a `RefetchBar`. */
  isLoading: boolean;
  isRefetching: boolean;
  error: unknown;
  refetch: () => void;
}

/**
 * A 1s wall-clock tick shared by every consumer, so elapsed times in the rail, the panel and the
 * page advance on the same frame instead of three independent intervals drifting apart.
 */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

export function useJobsModel(): JobsModel {
  const seed = useQuery({ queryKey: ["jobs"], queryFn: () => listJobs(), refetchOnWindowFocus: false });
  const { jobs: live } = useJobsStream();
  const now = useNow();

  const all = useMemo(
    () => mergeJobs(seed.data, live).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)),
    [seed.data, live],
  );

  // jobId -> the ms it stopped running; present only while it is still lingering in the rail.
  const [finishedAt, setFinishedAt] = useState<Map<string, number>>(new Map());
  const lastStates = useRef<Map<string, JobState>>(new Map());
  const allRef = useRef(all);
  useEffect(() => {
    allRef.current = all;
  });

  useEffect(() => {
    const t = setInterval(() => {
      const nowMs = Date.now();
      // Detect transitions out of a running state and start that job's linger window; a rerun
      // while lingering clears it; drop any window past FINISHED_LINGER_MS. All three read the
      // wall clock, so this can only live in an effect — React Compiler's purity rule forbids
      // calling `Date.now()` during render.
      const justFinished: string[] = [];
      const running = new Set<string>();
      for (const job of allRef.current) {
        const wasRunning = RUNNING_STATES.includes(lastStates.current.get(job.id) as JobState);
        if (wasRunning && !isRunning(job)) justFinished.push(job.id);
        if (isRunning(job)) running.add(job.id);
      }
      lastStates.current = new Map(allRef.current.map((j) => [j.id, j.state as JobState]));

      setFinishedAt((prev) => {
        let changed = false;
        const next = new Map(prev);
        for (const id of justFinished) {
          if (!next.has(id)) {
            next.set(id, nowMs);
            changed = true;
          }
        }
        for (const id of running) {
          if (next.delete(id)) changed = true;
        }
        for (const [id, ts] of next) {
          if (nowMs - ts > FINISHED_LINGER_MS) {
            next.delete(id);
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 1000);
    return () => clearInterval(t);
  }, []);

  // Running work first (that is what the rail is for), then queued, newest first within each.
  const active = useMemo(
    () =>
      all
        .filter((j) => isRunning(j) || finishedAt.has(j.id))
        .sort((a, b) => {
          const rank = (j: JobStatus) => (j.state === "running" ? 0 : j.state === "queued" ? 1 : 2);
          return rank(a) - rank(b) || Date.parse(b.created_at) - Date.parse(a.created_at);
        }),
    [all, finishedAt],
  );

  const runningCount = useMemo(() => all.filter(isRunning).length, [all]);

  return {
    all,
    active,
    runningCount,
    now,
    isLoading: seed.isLoading,
    isRefetching: seed.isRefetching,
    error: seed.error,
    refetch: () => void seed.refetch(),
  };
}

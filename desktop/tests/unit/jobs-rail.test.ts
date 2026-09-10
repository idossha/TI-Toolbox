/**
 * The pure parts of the jobs component family: rail overflow, the density contract shared by the
 * three heights, and the UI store the three heights read.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { densitySpec, overflowTooltip, RAIL_MAX_TRACES, splitRailJobs } from "../../src/renderer/app/jobs-rail/model";
import {
  activeFilterCount,
  ALL,
  applyJobsFilters,
  JOBS_PANEL_TABS,
  NO_FILTERS,
  useJobsUi,
} from "../../src/renderer/app/jobs-rail/store";
import {
  clampListFraction,
  DEFAULT_LIST_FRACTION,
  HANDLE_PX,
  listWidth,
  MIN_DETAIL_PX,
  MIN_LIST_PX,
  readSplit,
  SPLIT_KEY,
  writeSplit,
} from "../../src/renderer/app/jobs-rail/split";
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
    useJobsUi.getState().setTab("jobs");
    useJobsUi.getState().select("job-8");
    expect(useJobsUi.getState().tab).toBe("jobs");
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

describe("the panel's tabs", () => {
  it("is Jobs and Host — Console and Report are gone (maintainer, 2026-09-07)", () => {
    expect(JOBS_PANEL_TABS.map((t) => t.value)).toEqual(["jobs", "host"]);
    expect(JOBS_PANEL_TABS.map((t) => t.label)).toEqual(["Jobs", "Host"]);
  });

  it("keeps Jobs first, so the panel opens on the work rather than on the machine", () => {
    expect(JOBS_PANEL_TABS[0]!.value).toBe("jobs");
  });
});

describe("the master–detail split", () => {
  it("defaults to a list-heavy 62/38, not the old fixed 560px", () => {
    // At 1440 the fixed 560px default was a 39% list; at 1920 it was 29%. The fraction keeps the
    // shape the maintainer's screenshot asked for at every width.
    expect(DEFAULT_LIST_FRACTION).toBeCloseTo(0.62, 2);
    expect(clampListFraction(DEFAULT_LIST_FRACTION, 1440)).toBeCloseTo(0.62, 2);
    expect(clampListFraction(DEFAULT_LIST_FRACTION, 1920)).toBeCloseTo(0.62, 2);
  });

  it("never leaves the detail pane below its 420px minimum", () => {
    for (const box of [1280, 1440, 1920]) {
      const width = listWidth(0.95, box); // a drag all the way right
      expect(box - HANDLE_PX - width).toBeGreaterThanOrEqual(MIN_DETAIL_PX);
    }
  });

  it("never leaves the list below its own minimum", () => {
    for (const box of [1280, 1440, 1920]) {
      expect(listWidth(0.01, box)).toBeGreaterThanOrEqual(MIN_LIST_PX);
    }
  });

  it("falls back to the default proportion where neither minimum can hold", () => {
    // Narrower than 360 + 420 + handle: clamping to either minimum would push the other pane off
    // the box entirely, so the proportion wins.
    expect(clampListFraction(0.95, 600)).toBe(DEFAULT_LIST_FRACTION);
  });

  it("remembers the divider, and shrugs off anything it cannot use", () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    };
    writeSplit(0.45, storage);
    expect(store.get(SPLIT_KEY)).toBe("0.4500");
    expect(readSplit(storage)).toBeCloseTo(0.45, 4);

    for (const junk of ["", "nonsense", "0", "1", "-0.3", "1.4"]) {
      store.set(SPLIT_KEY, junk);
      expect(readSplit(storage)).toBe(DEFAULT_LIST_FRACTION);
    }
    store.clear();
    expect(readSplit(storage)).toBe(DEFAULT_LIST_FRACTION);
  });

  it("survives storage that throws (private window, blocked site data)", () => {
    const throwing = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    expect(readSplit(throwing)).toBe(DEFAULT_LIST_FRACTION);
    expect(() => writeSplit(0.5, throwing)).not.toThrow();
  });
});

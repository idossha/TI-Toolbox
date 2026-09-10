/**
 * The System page's payload → meters / series / rows model.
 *
 * Two things are being pinned. One is the arithmetic (uptime, rates, stacked-bar fractions, the
 * chart windows). The other, and the reason most of these tests exist, is **what a missing
 * optional field renders as**: every field the 2026-09-07 snapshot added is optional because a
 * host may not be able to answer it, and a monitor that answers a question it was not told the
 * answer to is worse than one that says "—".
 */
import { describe, expect, it } from "vitest";
import type { SystemSnapshot } from "../../src/renderer/api/client";
import {
  CORE_WINDOW_MS,
  coreRows,
  diskSegments,
  dockerSegments,
  dockerStatus,
  dockerTotal,
  formatRate,
  formatUptime,
  isStoppable,
  limitsLabel,
  loadLabel,
  loadTone,
  memorySegments,
  netRate,
  seriesOf,
  sortProcesses,
  swapSegments,
  toneFor,
  windowed,
  WINDOW_MS,
  PROJECT_BANDS,
  projectSegments,
  projectShareOfDisk,
  scanAgeLabel,
  type Process,
} from "../../src/renderer/pages/system/model";

const GB = 1024 ** 3;

function snap(over: Partial<SystemSnapshot> = {}): SystemSnapshot {
  return {
    ts: 1_760_000_000,
    cpu_percent: 42.5,
    cpu_count: 8,
    cpu_per_core: [10, 20, 30, 40, 50, 60, 70, 95],
    load_avg: [1.42, 1.1, 0.98],
    uptime_s: 3 * 86_400 + 4 * 3600 + 12 * 60,
    mem: { total: 32 * GB, available: 18 * GB, used: 10 * GB, percent: 43.8, free: 18 * GB, cached: 3 * GB, buffers: 1 * GB },
    swap: { total: 4 * GB, used: 0.5 * GB, free: 3.5 * GB, percent: 12 },
    disk: { total: 1000 * GB, free: 412 * GB, percent: 58.8, path: "/mnt/example" },
    processes: [],
    process_total: 0,
    ...over,
  } as SystemSnapshot;
}

function proc(over: Partial<Process> = {}): Process {
  return {
    pid: 100,
    name: "python3",
    cmdline: "python3 -c pass",
    cpu_percent: 1,
    rss: 1024,
    started: 0,
    relevant: false,
    owner_kind: null,
    owner_id: null,
    owner_label: "",
    ...over,
  } as Process;
}

// ------------------------------------------------------------------- tones

describe("tones", () => {
  it("is one scale, so two meters cannot disagree about 'hot'", () => {
    expect(toneFor(10)).toBe("accent");
    expect(toneFor(74.9)).toBe("accent");
    expect(toneFor(75)).toBe("warning");
    expect(toneFor(89.9)).toBe("warning");
    expect(toneFor(90)).toBe("danger");
    expect(toneFor(undefined)).toBe("neutral");
  });

  it("reads load against the core count, never as an absolute", () => {
    // 8.0 is saturation on eight cores and half-idle on sixteen.
    expect(loadTone([8, 0, 0], 8)).toBe("danger");
    expect(loadTone([8, 0, 0], 16)).toBe("accent"); // half the cores busy: normal
    expect(loadTone(undefined, 8)).toBe("neutral");
    expect(loadTone([1], undefined)).toBe("neutral");
  });

  it("has no load label to print when the platform has no load average", () => {
    expect(loadLabel(undefined)).toBe("—");
    expect(loadLabel([])).toBe("—");
    expect(loadLabel([1.42, 1.1, 0.98])).toBe("1.42 · 1.10 · 0.98");
  });
});

// ------------------------------------------------------------------ uptime

describe("uptime", () => {
  it("prints days, hours and minutes the way an uptime reads", () => {
    expect(formatUptime(3 * 86_400 + 4 * 3600 + 12 * 60)).toBe("3 d 04:12");
    expect(formatUptime(4 * 3600 + 7 * 60 + 33)).toBe("4:07:33");
    expect(formatUptime(12 * 60 + 5)).toBe("12:05");
  });

  it("says nothing rather than '0:00' when the host did not report it", () => {
    expect(formatUptime(undefined)).toBe("—");
    expect(formatUptime(0)).toBe("—");
    expect(formatUptime(Number.NaN)).toBe("—");
  });
});

// ------------------------------------------------------------ stacked bars

describe("the memory bar", () => {
  it("separates cache from used — the point of a bar over a percentage", () => {
    // A container at "92 % memory" where a third is page cache is not in trouble, and one
    // undifferentiated block cannot say so.
    const segs = memorySegments(snap().mem);
    expect(segs.map((s) => s.id)).toEqual(["used", "cached", "buffers", "free"]);
    const total = segs.reduce((n, s) => n + s.fraction, 0);
    expect(total).toBeCloseTo(1, 4);
    expect(segs.find((s) => s.id === "cached")!.bytes).toBe(3 * GB);
  });

  it("degrades to used/free where psutil reports no cache (macOS, Windows)", () => {
    const segs = memorySegments({ total: 8 * GB, available: 4 * GB, used: 4 * GB, percent: 50 });
    expect(segs.map((s) => s.id)).toEqual(["used", "free"]);
  });

  it("draws nothing at all with no memory reading, rather than an empty full bar", () => {
    expect(memorySegments(undefined)).toEqual([]);
  });
});

describe("swap and disk bars", () => {
  it("has no bar for a machine with no swap configured", () => {
    expect(swapSegments({ total: 0, used: 0, free: 0, percent: 0 })).toEqual([]);
    expect(swapSegments(undefined)).toEqual([]);
    expect(swapSegments({ total: 4 * GB, used: 1 * GB, free: 3 * GB, percent: 25 })).toHaveLength(2);
  });

  it("derives used from total - free, and tones it by the reported percent", () => {
    const segs = diskSegments({ total: 100, free: 5, percent: 95 });
    expect(segs.find((s) => s.id === "used")!.bytes).toBe(95);
    expect(segs.find((s) => s.id === "used")!.tone).toBe("danger");
    expect(diskSegments(null)).toEqual([]);
  });
});

describe("the docker system df bar", () => {
  const df = { images_size: 60 * GB, containers_size: 1 * GB, volumes_size: 9 * GB, build_cache_size: 3 * GB };

  it("is images · containers · volumes · build cache, summing to the whole", () => {
    const segs = dockerSegments(df);
    expect(segs.map((s) => s.id)).toEqual(["images", "containers", "volumes", "cache"]);
    expect(dockerTotal(df)).toBe(73 * GB);
    expect(segs.reduce((n, s) => n + s.fraction, 0)).toBeCloseTo(1, 4);
  });

  it("reads a total the daemon refused as 0 rather than blanking the bar", () => {
    // Every df field is optional in the contract: some daemons permission-gate /system/df.
    const partial = dockerSegments({ images_size: 10 });
    expect(partial.map((s) => s.id)).toEqual(["images"]);
    expect(dockerTotal({})).toBe(0);
    expect(dockerSegments(null)).toEqual([]);
  });
});

// -------------------------------------------------------------- docker status

describe("docker status", () => {
  it("makes 'unreachable' a first-class state with its own copy", () => {
    // Zeros would read as a healthy daemon holding nothing, which is the opposite of true.
    const down = dockerStatus({ reachable: false, error: "no Docker socket at /var/run/docker.sock" });
    expect(down.tone).toBe("danger");
    expect(down.label).toBe("Unreachable");
    expect(down.detail).toContain("/var/run/docker.sock");
  });

  it("falls back to its own words when the daemon failed without saying why", () => {
    expect(dockerStatus({ reachable: false }).detail).toBe("the daemon did not answer");
  });

  it("names the engine and its round-trip when it is up", () => {
    const up = dockerStatus({ reachable: true, version: "27.3.1", api_version: "1.47", latency_ms: 3.4 });
    expect(up.label).toBe("Engine 27.3.1");
    expect(up.detail).toBe("API 1.47 · 3.4 ms");
  });

  it("says 'unknown', not 'unreachable', when the snapshot carried no docker block at all", () => {
    // A payload from an older server is not evidence that Docker is down.
    expect(dockerStatus(undefined).label).toBe("Unknown");
  });
});

describe("container limits", () => {
  it("spells out both limits, and says plainly when there are none", () => {
    expect(limitsLabel({ cpu_limit: 8, mem_limit: 24 * GB })).toBe("8 cores · 24.0 GB");
    expect(limitsLabel({ cpu_limit: 1, mem_limit: null })).toBe("1 core");
    expect(limitsLabel({ cpu_limit: null, mem_limit: null })).toBe("no limit set");
    expect(limitsLabel(null)).toBe("—");
  });
});

// -------------------------------------------------------------------- series

describe("chart windows", () => {
  const now = 1_760_000_000_000;
  const at = (msAgo: number, over: Partial<SystemSnapshot> = {}) => snap({ ts: (now - msAgo) / 1000, ...over });

  it("keeps the last five minutes and drops what fell out of it", () => {
    const samples = [at(WINDOW_MS + 10_000), at(WINDOW_MS - 1_000), at(60_000), at(0)];
    expect(windowed(samples, now)).toHaveLength(3);
  });

  it("gives the per-core sparklines their own, shorter window", () => {
    const samples = [at(CORE_WINDOW_MS + 5_000), at(30_000), at(0)];
    expect(windowed(samples, now, CORE_WINDOW_MS)).toHaveLength(2);
  });

  it("turns a window into the two arrays uPlot wants, in order", () => {
    const samples = [snap({ ts: 100, cpu_percent: 10 }), snap({ ts: 102, cpu_percent: 20 })];
    expect(seriesOf(samples, (s) => s.cpu_percent)).toEqual({ timestamps: [100, 102], values: [10, 20] });
  });

  it("is empty, not undefined, before any sample arrives — the chart says 'collecting'", () => {
    expect(seriesOf([], (s) => s.cpu_percent)).toEqual({ timestamps: [], values: [] });
  });
});

describe("the per-core grid", () => {
  const now = 1_760_000_000_000;

  it("is one row per reported core, each with its own recent history", () => {
    const a = snap({ ts: (now - 20_000) / 1000, cpu_per_core: [5, 5, 5, 5, 5, 5, 5, 5] });
    const b = snap({ ts: now / 1000 });
    const rows = coreRows([a, b], now);
    expect(rows).toHaveLength(8);
    expect(rows[7]).toMatchObject({ index: 7, percent: 95, tone: "danger" });
    expect(rows[7]!.history).toEqual([5, 95]);
  });

  it("draws nothing rather than cpu_count bars all showing the average", () => {
    // Repeating one figure `cpu_count` times would look exactly like real per-core data.
    expect(coreRows([snap({ cpu_per_core: undefined })], now)).toEqual([]);
    expect(coreRows([], now)).toEqual([]);
  });
});

// --------------------------------------------------------------------- rates

describe("network rate", () => {
  it("is a delta over real elapsed time, from two cumulative counters", () => {
    const a = snap({ ts: 100, net: { bytes_sent: 1000, bytes_recv: 5000 } });
    const b = snap({ ts: 102, net: { bytes_sent: 3000, bytes_recv: 9000 } });
    expect(netRate([a, b])).toEqual({ sent: 1000, recv: 2000 });
  });

  it("needs two samples, and refuses a zero or negative interval", () => {
    const a = snap({ ts: 100, net: { bytes_sent: 0, bytes_recv: 0 } });
    expect(netRate([a])).toBeNull();
    expect(netRate([a, snap({ ts: 100, net: { bytes_sent: 1, bytes_recv: 1 } })])).toBeNull();
  });

  it("reports zero, not a vast negative spike, when a counter resets", () => {
    // A counter going down means the host rebooted or the interface was reset.
    const a = snap({ ts: 100, net: { bytes_sent: 9_000_000, bytes_recv: 9_000_000 } });
    const b = snap({ ts: 102, net: { bytes_sent: 10, bytes_recv: 10 } });
    expect(netRate([a, b])).toEqual({ sent: 0, recv: 0 });
  });

  it("says nothing where the host reported no counters", () => {
    expect(netRate([snap(), snap()])).toBeNull();
  });

  it("formats a rate per second, and a missing one as a dash", () => {
    expect(formatRate(1024 ** 2)).toBe("1 MB/s");
    expect(formatRate(null)).toBe("—");
    expect(formatRate(Number.NaN)).toBe("—");
  });
});

// ----------------------------------------------------------------- processes

describe("the process table", () => {
  it("defaults to CPU descending, and breaks ties by memory so rows do not reshuffle", () => {
    const rows = [proc({ pid: 1, cpu_percent: 0, rss: 10 }), proc({ pid: 2, cpu_percent: 0, rss: 99 }), proc({ pid: 3, cpu_percent: 5 })];
    expect(sortProcesses(rows, "cpu").map((p) => p.pid)).toEqual([3, 2, 1]);
  });

  it("sorts memory by RSS, not by the rounded percentage derived from it", () => {
    const rows = [proc({ pid: 1, rss: 10, mem_percent: 0.1 }), proc({ pid: 2, rss: 900, mem_percent: 0.1 })];
    expect(sortProcesses(rows, "mem").map((p) => p.pid)).toEqual([2, 1]);
  });

  it("sorts by pid and name too, without mutating the input", () => {
    const rows = [proc({ pid: 9, name: "zsh" }), proc({ pid: 2, name: "charm" })];
    expect(sortProcesses(rows, "pid").map((p) => p.pid)).toEqual([2, 9]);
    expect(sortProcesses(rows, "name").map((p) => p.name)).toEqual(["charm", "zsh"]);
    expect(rows.map((p) => p.pid)).toEqual([9, 2]);
  });

  it("offers to stop ONLY a process the server attributed to a job or a kernel", () => {
    // An unowned pid has no cancel path, and a monitoring page must not raw-kill one.
    expect(isStoppable(proc({ owner_kind: "job", owner_id: "j1" }))).toBe(true);
    expect(isStoppable(proc({ owner_kind: "kernel", owner_id: "k1" }))).toBe(true);
    expect(isStoppable(proc({ owner_kind: "server" }))).toBe(false);
    expect(isStoppable(proc({ owner_kind: null }))).toBe(false);
    // Being a *toolbox* process is not ownership: `charm` spawned outside a job is still unowned.
    expect(isStoppable(proc({ relevant: true, owner_kind: null }))).toBe(false);
  });
});


// ---------------------------------------------------------- project storage

describe("the project's storage breakdown", () => {
  const storage = {
    project_dir: "/mnt/000",
    total_bytes: 100,
    total_files: 10,
    scanned_at: 1_000,
    duration_s: 1,
    scanning: false,
    partial: false,
    kinds: [
      { kind: "a", label: "A", bytes: 50, files: 1 },
      { kind: "b", label: "B", bytes: 20, files: 1 },
      { kind: "c", label: "C", bytes: 10, files: 1 },
      { kind: "d", label: "D", bytes: 8, files: 1 },
      { kind: "e", label: "E", bytes: 6, files: 1 },
      { kind: "f", label: "F", bytes: 4, files: 1 },
      { kind: "g", label: "G", bytes: 1, files: 1 },
      { kind: "h", label: "H", bytes: 1, files: 1 },
    ],
    largest: [],
  };

  it("shows the biggest kinds and folds the tail, summing to the whole", () => {
    const segs = projectSegments(storage);
    // Six bands plus one "Other kinds": fifteen bands is a colour key, not a reading.
    expect(segs).toHaveLength(PROJECT_BANDS + 1);
    expect(segs[0]!.label).toBe("A");
    expect(segs[segs.length - 1]!.label).toBe("Other kinds");
    expect(segs[segs.length - 1]!.bytes).toBe(2);
    expect(segs.reduce((n, s) => n + s.bytes, 0)).toBe(storage.total_bytes);
    expect(segs.reduce((n, s) => n + s.fraction, 0)).toBeCloseTo(1, 6);
  });

  it("draws nothing before the first scan, rather than an empty full bar", () => {
    expect(projectSegments(undefined)).toEqual([]);
    expect(projectSegments({ ...storage, total_bytes: 0, kinds: [] })).toEqual([]);
  });

  it("states the project as a share of the disk it competes for", () => {
    // "246 GB" means nothing until you know the disk is 1 TB.
    expect(projectShareOfDisk(storage, { total: 400 })).toBeCloseTo(25, 5);
    expect(projectShareOfDisk(storage, null)).toBeNull();
    expect(projectShareOfDisk(undefined, { total: 400 })).toBeNull();
    expect(projectShareOfDisk(storage, { total: 0 })).toBeNull();
  });

  it("says how old its own numbers are — it is a scan, not a live sample", () => {
    const at = 1_700_000_000;
    const s = { ...storage, scanned_at: at };
    expect(scanAgeLabel(s, at * 1000 + 30_000)).toBe("scanned 30 s ago");
    expect(scanAgeLabel(s, at * 1000 + 3 * 60_000)).toBe("scanned 3 min ago");
    expect(scanAgeLabel(s, at * 1000 + 5 * 3600_000)).toBe("scanned 5 h ago");
    expect(scanAgeLabel({ ...s, scanning: true }, at * 1000)).toBe("scanning…");
    // Never scanned is its own answer: "0 bytes" would be a wrong number, not a missing one.
    expect(scanAgeLabel({ ...s, scanned_at: 0 }, at * 1000)).toBe("never scanned");
    expect(scanAgeLabel(undefined)).toBe("…");
  });
});

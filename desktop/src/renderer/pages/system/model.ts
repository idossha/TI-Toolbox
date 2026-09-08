/**
 * The System page's pure model: one `/ws/system` snapshot → the meters and rows a monitor draws,
 * and a window of snapshots → the chart series.
 *
 * Split out from the components because it is the part with rules in it — how a stacked bar is
 * segmented, what a rate is, when a number counts as pressure, and above all **what a missing
 * optional field renders as**. Every field the 2026-09-07 snapshot added is optional because a
 * host may not be able to answer it, and a monitor that answers a question it was not told the
 * answer to is worse than one that says "—".
 */
import type { SystemSnapshot } from "../../api/client";
import { bytes } from "../../ui/utils";

/** The history charts' window. The stream sends every 1–2 s, so this is 150–300 samples. */
export const WINDOW_MS = 5 * 60 * 1000;
/** The per-core sparklines' window — a core's *recent* behaviour, at a glance. */
export const CORE_WINDOW_MS = 60 * 1000;

export type Tone = "neutral" | "accent" | "warning" | "danger";

/** Utilisation → tone. One scale everywhere, so two meters cannot disagree about "hot". */
export function toneFor(percent: number | undefined | null): Tone {
  if (percent === undefined || percent === null) return "neutral";
  if (percent >= 90) return "danger";
  if (percent >= 75) return "warning";
  return "accent";
}

/** "3 d 04:12" / "4:07:33" / "12:05" — the shape an uptime reads, not a count of seconds. */
export function formatUptime(seconds: number | undefined): string {
  if (!seconds || seconds <= 0 || !Number.isFinite(seconds)) return "—";
  const total = Math.floor(seconds);
  const days = Math.floor(total / 86_400);
  const h = Math.floor((total % 86_400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (days > 0) return `${days} d ${pad(h)}:${pad(m)}`;
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/** "1.42 · 1.10 · 0.98", or "—" where the platform has no load average. */
export function loadLabel(load: number[] | undefined): string {
  if (!load || load.length === 0) return "—";
  return load.map((v) => v.toFixed(2)).join(" · ");
}

/**
 * A load average is only readable against the core count — 8.0 is saturation on eight cores and
 * half-idle on sixteen — so the tone is the *ratio*, never the absolute.
 */
export function loadTone(load: number[] | undefined, cpuCount: number | undefined): Tone {
  const one = load?.[0];
  if (one === undefined || !cpuCount) return "neutral";
  return toneFor((one / cpuCount) * 100);
}

// ---------------------------------------------------------------- stacked bars

export interface Segment {
  id: string;
  label: string;
  bytes: number;
  /** Share of the bar, 0–1. */
  fraction: number;
  tone: Tone | "muted" | "cache";
}

function segments(total: number, parts: Omit<Segment, "fraction">[]): Segment[] {
  if (total <= 0) return [];
  return parts
    .filter((p) => p.bytes > 0)
    .map((p) => ({ ...p, fraction: Math.max(0, Math.min(1, p.bytes / total)) }));
}

/**
 * The memory bar: **used · cache · buffers · free**.
 *
 * The cache band is the point of this over a single percentage. A container sitting at "92 %
 * memory" where 40 % of that is page cache is not in trouble, and a bar that draws one
 * undifferentiated block cannot say so. `cached`/`buffers` are Linux-only in psutil and arrive as
 * 0 elsewhere, where this degrades to used/free — honest, rather than a fabricated band.
 */
export function memorySegments(mem: SystemSnapshot["mem"] | undefined): Segment[] {
  if (!mem) return [];
  const cached = mem.cached ?? 0;
  const buffers = mem.buffers ?? 0;
  // `used` from psutil already excludes cache on Linux; where it does not (no cached reported),
  // this is just used + free and the subtraction is a no-op.
  const used = Math.max(0, mem.used - 0);
  const free = Math.max(0, mem.total - used - cached - buffers);
  return segments(mem.total, [
    { id: "used", label: "Used", bytes: used, tone: toneFor(mem.percent) },
    { id: "cached", label: "Cache", bytes: cached, tone: "cache" },
    { id: "buffers", label: "Buffers", bytes: buffers, tone: "cache" },
    { id: "free", label: "Free", bytes: free, tone: "muted" },
  ]);
}

export function swapSegments(swap: SystemSnapshot["swap"] | undefined): Segment[] {
  if (!swap || swap.total <= 0) return [];
  return segments(swap.total, [
    { id: "used", label: "Used", bytes: swap.used, tone: toneFor(swap.percent) },
    { id: "free", label: "Free", bytes: swap.free, tone: "muted" },
  ]);
}

export function diskSegments(disk: { total: number; free: number; percent: number } | undefined | null): Segment[] {
  if (!disk || disk.total <= 0) return [];
  const used = Math.max(0, disk.total - disk.free);
  return segments(disk.total, [
    { id: "used", label: "Used", bytes: used, tone: toneFor(disk.percent) },
    { id: "free", label: "Free", bytes: disk.free, tone: "muted" },
  ]);
}

/**
 * `docker system df` as one bar: images · containers · volumes · build cache.
 *
 * This is the high-level Docker-health answer from *inside* the container, where
 * `/var/lib/docker` is normally not visible at all — so when `disk_docker` is absent this is
 * still a real reading of what the daemon is holding, rather than a blank.
 */
/** Every field is optional in the contract (a daemon may refuse `/system/df`), so it is optional
 *  here too and reads as 0 — one missing total must not blank the whole bar. */
export interface DfTotals {
  images_size?: number;
  containers_size?: number;
  volumes_size?: number;
  build_cache_size?: number;
}

export function dockerSegments(df: DfTotals | null | undefined): Segment[] {
  if (!df) return [];
  return segments(dockerTotal(df), [
    { id: "images", label: "Images", bytes: df.images_size ?? 0, tone: "accent" },
    { id: "containers", label: "Containers", bytes: df.containers_size ?? 0, tone: "warning" },
    { id: "volumes", label: "Volumes", bytes: df.volumes_size ?? 0, tone: "cache" },
    { id: "cache", label: "Build cache", bytes: df.build_cache_size ?? 0, tone: "muted" },
  ]);
}

export function dockerTotal(df: DfTotals | null | undefined): number {
  if (!df) return 0;
  return (df.images_size ?? 0) + (df.containers_size ?? 0) + (df.volumes_size ?? 0) + (df.build_cache_size ?? 0);
}

// -------------------------------------------------------------------- series

export interface Series {
  /** uPlot's x: seconds since epoch. */
  timestamps: number[];
  values: number[];
}

/** Snapshots inside a window, oldest first. `now` is injected so this is testable. */
export function windowed(samples: SystemSnapshot[], now: number = Date.now(), ms: number = WINDOW_MS): SystemSnapshot[] {
  const floor = (now - ms) / 1000;
  return samples.filter((s) => s.ts >= floor);
}

export function seriesOf(samples: SystemSnapshot[], pick: (s: SystemSnapshot) => number): Series {
  return { timestamps: samples.map((s) => s.ts), values: samples.map(pick) };
}

export interface CoreRow {
  index: number;
  percent: number;
  tone: Tone;
  /** The last `CORE_WINDOW_MS` of this core, for its own sparkline. */
  history: number[];
}

/**
 * The per-core grid.
 *
 * Empty when the host did not report per-core figures — the grid then does not render at all
 * rather than drawing `cpu_count` bars all reading the same average, which would look exactly
 * like real per-core data and be a fabrication.
 */
export function coreRows(samples: SystemSnapshot[], now: number = Date.now()): CoreRow[] {
  const latest = samples[samples.length - 1];
  const per = latest?.cpu_per_core ?? [];
  if (per.length === 0) return [];
  const recent = windowed(samples, now, CORE_WINDOW_MS);
  return per.map((percent, index) => ({
    index,
    percent,
    tone: toneFor(percent),
    history: recent.map((s) => s.cpu_per_core?.[index] ?? 0),
  }));
}

// --------------------------------------------------------------------- rates

export interface Rate {
  sent: number;
  recv: number;
}

/**
 * Network throughput in bytes/second, from the two most recent snapshots.
 *
 * The payload carries cumulative counters (they only ever go up, and are meaningless as an
 * absolute), so a rate needs two samples and a real elapsed time — `WINDOW_MS / sample count`
 * would be wrong the moment the stream reconnects. A counter that went *down* means the host
 * rebooted or the interface was reset: report zero rather than a vast negative spike.
 */
export function netRate(samples: SystemSnapshot[]): Rate | null {
  const b = samples[samples.length - 1];
  const a = samples[samples.length - 2];
  if (!a?.net || !b?.net) return null;
  const dt = b.ts - a.ts;
  if (dt <= 0) return null;
  const sent = (b.net.bytes_sent - a.net.bytes_sent) / dt;
  const recv = (b.net.bytes_recv - a.net.bytes_recv) / dt;
  return { sent: Math.max(0, sent), recv: Math.max(0, recv) };
}

export function formatRate(bytesPerSecond: number | undefined | null): string {
  if (bytesPerSecond === undefined || bytesPerSecond === null || !Number.isFinite(bytesPerSecond)) return "—";
  return `${bytes(Math.round(bytesPerSecond))}/s`;
}

// ----------------------------------------------------------------- processes

export type ProcessSort = "cpu" | "mem" | "pid" | "name";

export type Process = SystemSnapshot["processes"][number];

/** Sorted process rows. Default CPU descending — the htop default, and the useful one. */
export function sortProcesses(rows: Process[], sort: ProcessSort): Process[] {
  const out = [...rows];
  switch (sort) {
    case "mem":
      // RSS, not `mem_percent`: the percentage is derived from it and rounds ties together.
      return out.sort((a, b) => b.rss - a.rss);
    case "pid":
      return out.sort((a, b) => a.pid - b.pid);
    case "name":
      return out.sort((a, b) => a.name.localeCompare(b.name));
    default:
      return out.sort((a, b) => b.cpu_percent - a.cpu_percent || b.rss - a.rss);
  }
}

/**
 * May the UI offer to stop this process?
 *
 * Only a process the server says belongs to a job or a kernel. That is the whole rule, and it is
 * here rather than in the component so it cannot be half-applied: stopping an owned process goes
 * through that job's own cancel (which cleans up its lock, its events and its sibling containers),
 * and an unowned pid has no such path — offering a button that would raw-kill an unknown process
 * inside the container is not something a monitoring page should do.
 */
export function isStoppable(p: Process): boolean {
  return p.owner_kind === "job" || p.owner_kind === "kernel";
}

/** "sim · ernie" / "kernel k-9f2c" / "" — never a fabricated owner. */
export function ownerLabel(p: Process): string {
  return p.owner_label ?? "";
}

// ------------------------------------------------------------ docker summary

export interface DockerStatus {
  tone: Tone | "muted";
  label: string;
  detail: string;
}

/**
 * The Docker panel's one-line verdict.
 *
 * "Unreachable" is a real, first-class state with its own copy — not zeros, which read as a
 * healthy daemon holding nothing.
 */
export function dockerStatus(docker: SystemSnapshot["docker"] | undefined): DockerStatus {
  if (!docker) return { tone: "muted", label: "Unknown", detail: "no Docker information in this snapshot" };
  if (!docker.reachable) {
    return { tone: "danger", label: "Unreachable", detail: docker.error || "the daemon did not answer" };
  }
  const latency = docker.latency_ms === undefined || docker.latency_ms === null ? "" : ` · ${docker.latency_ms.toFixed(1)} ms`;
  return {
    tone: "accent",
    label: `Engine ${docker.version || "?"}`,
    detail: `API ${docker.api_version || "?"}${latency}`,
  };
}

/** "8 cores · 24.0 GB" — the container's own limits, or "no limit set". */
export function limitsLabel(own: { cpu_limit?: number | null; mem_limit?: number | null } | null | undefined): string {
  if (!own) return "—";
  const parts: string[] = [];
  if (own.cpu_limit) parts.push(`${own.cpu_limit} core${own.cpu_limit === 1 ? "" : "s"}`);
  if (own.mem_limit) parts.push(bytes(own.mem_limit));
  return parts.length > 0 ? parts.join(" · ") : "no limit set";
}


// ------------------------------------------------------- the redundancy map

/**
 * Which card owns each metric — **one card each, and only one**.
 *
 * The page showed the same number in two places more than once while it was being built (a CPU
 * percentage in its own tile and again in the chart legend; disk free in a tile and in the meter
 * caption; the load average in two cards), and every instance of that was a place a reader had to
 * check whether the two agreed. This table is the rule, `tests/unit/system-redundancy.test.tsx`
 * enforces it against the rendered DOM, and each card carries its own list as `data-metrics` so
 * the rule and the markup cannot drift apart.
 *
 * Adding a metric means adding it here, once. If it genuinely belongs in two cards, that is a
 * layout problem to solve, not an entry to duplicate.
 */
export type CardId = "timeline" | "processes" | "memory" | "storage" | "docker" | "host";

export const METRIC_HOME = {
  // The timeline is the only place a CPU or memory *percentage* is printed.
  "cpu.percent": "timeline",
  "mem.percent": "timeline",
  "cpu.perCore": "timeline",
  // Memory: the composition, not the percentage.
  "mem.breakdown": "memory",
  "mem.swap": "memory",
  // Storage: both the filesystem and what Docker is holding — one question, one card.
  "disk.project": "storage",
  "disk.dockerRoot": "storage",
  "docker.df": "storage",
  // Docker: the daemon and this container.
  "docker.engine": "docker",
  "docker.own": "docker",
  "docker.mounts": "docker",
  "docker.siblings": "docker",
  "docker.images": "docker",
  // Host: the numbers that are neither a resource meter nor a Docker fact.
  "host.load": "host",
  "host.uptime": "host",
  "host.net": "host",
  "host.counts": "host",
  processes: "processes",
  // No `jobs` key. A jobs strip lived here briefly and was removed (maintainer, 2026-09-07): the
  // rail is on every screen and `pages/jobs` is the full list, so a third view of the same rows
  // was the page's own largest redundancy — and it was taking height from the process table,
  // which always has more to show.
} as const satisfies Record<string, CardId>;

export type MetricKey = keyof typeof METRIC_HOME;

/** The metrics a card owns — what it renders as `data-metrics`. */
export function metricsOf(card: CardId): MetricKey[] {
  return (Object.keys(METRIC_HOME) as MetricKey[]).filter((k) => METRIC_HOME[k] === card);
}

// ------------------------------------------------------------- the timeline

/** One series on the shared timeline. */
export interface TimelineSeries {
  id: string;
  label: string;
  values: number[];
  /** A CSS custom property name, resolved at draw time so the chart follows the theme toggle. */
  colorVar: string;
  /** Filled area under the line. Per-core lines are not filled — twelve fills is a smear. */
  fill: boolean;
}

export interface Timeline {
  timestamps: number[];
  series: TimelineSeries[];
}

/**
 * CPU and memory on **one** shared x-axis, plus per-core lines when they are turned on.
 *
 * One timeline rather than two stacked charts because the question people actually have is
 * whether the two moved *together* — memory climbing while CPU flatlines is a solve that started
 * swapping, and two charts with two independent time axes make that a thing you have to
 * reconstruct rather than see.
 */
export function timeline(samples: SystemSnapshot[], opts: { perCore?: boolean } = {}): Timeline {
  const timestamps = samples.map((s) => s.ts);
  const series: TimelineSeries[] = [
    { id: "cpu", label: "CPU", values: samples.map((s) => s.cpu_percent), colorVar: "--accent", fill: true },
    { id: "mem", label: "Memory", values: samples.map((s) => s.mem.percent), colorVar: "--success", fill: true },
  ];
  if (opts.perCore) {
    const count = samples[samples.length - 1]?.cpu_per_core?.length ?? 0;
    for (let i = 0; i < count; i += 1) {
      series.push({
        id: `core-${i}`,
        label: `Core ${i}`,
        values: samples.map((s) => s.cpu_per_core?.[i] ?? 0),
        colorVar: "--ink-3",
        fill: false,
      });
    }
  }
  return { timestamps, series };
}

/** "CPU 0.5 % · Memory 6.6 %" — the live read-out, which is the legend. */
export function timelineLegend(latest: SystemSnapshot | undefined): { id: string; label: string; value: string; colorVar: string }[] {
  return [
    { id: "cpu", label: "CPU", value: pctLabel(latest?.cpu_percent), colorVar: "--accent" },
    { id: "mem", label: "Memory", value: pctLabel(latest?.mem.percent), colorVar: "--success" },
  ];
}

function pctLabel(n: number | undefined): string {
  return n === undefined ? "—" : `${n.toFixed(1)} %`;
}

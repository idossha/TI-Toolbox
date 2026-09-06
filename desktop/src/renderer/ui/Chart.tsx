import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { useEffect, useRef } from "react";
import { Skeleton } from "./Feedback";

/** Below this many samples a line chart has nothing to draw — one point is a dot, not a trend —
 * yet the axes still rendered, which read as a broken/empty chart rather than "just started"
 * (ra_12 #29). Both `LineChart` and any page using it (e.g. System's CPU/memory history) show a
 * skeleton with this label until enough samples arrive. */
export const CHART_MIN_SAMPLES = 2;

function readVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/**
 * A single-series line chart (System's CPU/memory history). Re-themes on redraw so it tracks a
 * light/dark toggle without a remount; timestamps are seconds since epoch, values are the y-axis.
 */
export function LineChart({
  timestamps,
  values,
  label,
  unit = "%",
  height = 64,
  color,
}: {
  timestamps: number[];
  values: number[];
  label: string;
  unit?: string;
  height?: number;
  color?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);

  // Resize wiring only — independent of data, set up once per mount.
  useEffect(() => {
    if (!ref.current) return;
    const resize = () => plotRef.current?.setSize({ width: ref.current!.clientWidth || 240, height });
    const observer = new ResizeObserver(resize);
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      plotRef.current?.destroy();
      plotRef.current = null;
    };
  }, [height]);

  // Construct the plot lazily, once there are enough samples to draw a line, and update it after
  // that. uPlot's auto time-scale range degenerates (garbage multi-year tick spacing) when it is
  // *constructed* with an empty series — as it always would be here, since the live stream has no
  // sample yet at mount — so we wait for real data rather than seeding it with `[[], []]`. A
  // single sample is deliberately not "enough": one point has no line to draw, so constructing on
  // it just showed bare axes (ra_12 #29) — the skeleton below covers that gap instead.
  useEffect(() => {
    if (!ref.current || timestamps.length < CHART_MIN_SAMPLES) return;
    if (!plotRef.current) {
      const stroke = color ?? readVar("--accent", "#1F5BD7");
      const grid = readVar("--line", "#D8DEE6");
      const ink2 = readVar("--ink-2", "#4B5865");
      const opts: uPlot.Options = {
        width: ref.current.clientWidth || 240,
        height,
        class: "sparkline-wrap",
        legend: { show: false },
        cursor: { show: true },
        // uPlot's own default x-range for a near-single-point time series is *not* [min, max]
        // padded a little — its built-in degenerate-scale fallback sets `max = min + 1000 days`,
        // which is what the (initMin, initMax) arguments below actually carry in that case. So
        // this ignores those arguments and re-derives the window straight from the real series
        // data on every (re)range, which is the only way to get a sane time axis on the first
        // sample or two of a live chart.
        scales: {
          x: {
            time: true,
            range: (u) => {
              const xs = u.data[0] as number[] | undefined;
              if (!xs || xs.length === 0) return [0, 60];
              const first = xs[0]!;
              const last = xs[xs.length - 1]!;
              if (last - first < 60) {
                const mid = (first + last) / 2;
                return [mid - 30, mid + 30];
              }
              const pad = (last - first) * 0.02;
              return [first - pad, last + pad];
            },
          },
        },
        axes: [
          { stroke: ink2, grid: { stroke: grid, width: 1 }, ticks: { show: false } },
          { stroke: ink2, grid: { stroke: grid, width: 1 }, ticks: { show: false }, values: (_u, vals) => vals.map((v) => `${v}${unit}`) },
        ],
        series: [{}, { label, stroke, width: 1.5, points: { show: false } }],
      };
      plotRef.current = new uPlot(opts, [timestamps, values], ref.current);
    } else {
      plotRef.current.setData([timestamps, values]);
    }
  }, [timestamps, values, color, height, label, unit]);

  const collecting = timestamps.length < CHART_MIN_SAMPLES;
  return (
    <div className="chart-frame" style={{ height }}>
      <div ref={ref} role="img" aria-label={label} style={{ display: collecting ? "none" : "block" }} />
      {collecting && (
        <div className="chart-collecting" aria-live="polite">
          <Skeleton height={height} />
          <span className="chart-collecting-label text-caption">Collecting {label.toLowerCase()}…</span>
        </div>
      )}
    </div>
  );
}

/** Minimal axis-free trend line for dense contexts (job rows, table cells). */
export function Sparkline({ values, color, height = 20, width = 64 }: { values: number[]; color?: string; height?: number; width?: number }) {
  if (values.length === 0) return <svg width={width} height={height} aria-hidden />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const points = values.map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - min) / range) * height).toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} role="img" aria-label="trend">
      <polyline points={points} fill="none" stroke={color ?? "var(--accent)"} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

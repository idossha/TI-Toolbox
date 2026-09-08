/**
 * The System page's history chart: a filled area with a faint grid, real axis labels, and the
 * current value emphasised at the right edge.
 *
 * Local to this page rather than added to `ui/Chart.tsx` (another lane's file), and different
 * from that file's `LineChart` in the ways a monitor needs: a fill under the curve, a fixed 0–100
 * y-scale so a quiet minute is *drawn* as a quiet minute instead of being auto-ranged into a
 * dramatic mountain, and a right-anchored read-out so the number you want is where your eye
 * already is.
 *
 * uPlot rather than SVG because the page redraws every 1–2 s and eight of these on one screen is
 * exactly the case a canvas plotter exists for.
 */
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { useEffect, useRef } from "react";

/** The chart's narrowest x-window, in seconds. See the `range` comment below. */
const MIN_SPAN_S = 60;

function readVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** `#1F5BD7` → `rgba(31,91,215,α)`. Falls back to the colour itself where it is not hex. */
function withAlpha(color: string, alpha: number): string {
  const hex = color.trim();
  if (!/^#([0-9a-f]{6}|[0-9a-f]{3})$/i.test(hex)) return hex;
  const full = hex.length === 4 ? `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}` : hex;
  const r = parseInt(full.slice(1, 3), 16);
  const g = parseInt(full.slice(3, 5), 16);
  const b = parseInt(full.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

export function AreaChart({
  timestamps,
  values,
  label,
  height = 92,
  colorVar = "--accent",
  /** Fixed y-range. A percentage chart is always 0–100; a rate chart auto-ranges. */
  max = 100,
}: {
  timestamps: number[];
  values: number[];
  label: string;
  height?: number;
  colorVar?: string;
  max?: number | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);
  // Read in the draw effect, not in a dep array: re-creating the plot on every theme read would
  // throw away the series.
  const themeKey = typeof document === "undefined" ? "" : document.documentElement.dataset.theme ?? "";

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const resize = () => plotRef.current?.setSize({ width: el.clientWidth || 240, height });
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    return () => {
      observer.disconnect();
      plotRef.current?.destroy();
      plotRef.current = null;
    };
  }, [height]);

  // Rebuild on a theme change so the grid and stroke follow the toggle; otherwise update in place.
  useEffect(() => {
    plotRef.current?.destroy();
    plotRef.current = null;
  }, [themeKey, colorVar]);

  useEffect(() => {
    const el = ref.current;
    // One sample is a dot, not a trend: uPlot's time scale also degenerates when constructed with
    // an empty series (its fallback range is min + 1000 days), so the plot waits for two.
    if (!el || timestamps.length < 2) return;
    if (!plotRef.current) {
      const stroke = readVar(colorVar, "#1F5BD7");
      const grid = readVar("--line", "#D8DEE6");
      const ink2 = readVar("--ink-2", "#4B5865");
      const opts: uPlot.Options = {
        width: el.clientWidth || 240,
        height,
        legend: { show: false },
        cursor: { show: true, y: false },
        padding: [4, 2, 0, 0],
        scales: {
          x: {
            time: true,
            // A minimum 60 s window. uPlot ranges a two-sample series to the two seconds between
            // them, and then labels the axis in fractions of a second (":31.400") — which reads
            // as a broken chart rather than as "this only just started". Anchoring the right edge
            // at the newest sample and the left edge at least a minute back keeps the axis in
            // clock time from the very first frame, and the line simply starts part-way across.
            range: (u) => {
              const xs = u.data[0] as number[] | undefined;
              if (!xs || xs.length === 0) return [0, 60];
              const last = xs[xs.length - 1]!;
              const first = Math.min(xs[0]!, last - MIN_SPAN_S);
              return [first, last];
            },
          },
          // A monitor's y-axis must not move: auto-ranging turns a flat 3 % into a jagged wall,
          // and a reader cannot tell a busy machine from a quiet one at a glance.
          ...(max === null ? {} : { y: { range: [0, max] as [number, number] } }),
        },
        axes: [
          {
            stroke: ink2,
            grid: { stroke: grid, width: 1, dash: [2, 4] },
            ticks: { show: false },
            size: 22,
            space: 90,
          },
          {
            stroke: ink2,
            grid: { stroke: grid, width: 1, dash: [2, 4] },
            ticks: { show: false },
            size: 34,
            values: (_u, vals) => vals.map((v) => `${v}%`),
          },
        ],
        series: [
          {},
          {
            label,
            stroke,
            width: 1.5,
            fill: withAlpha(stroke, 0.18),
            points: { show: false },
          },
        ],
      };
      plotRef.current = new uPlot(opts, [timestamps, values], el);
    } else {
      plotRef.current.setData([timestamps, values]);
    }
  }, [timestamps, values, label, height, colorVar, max, themeKey]);

  const collecting = timestamps.length < 2;
  return (
    <div className="system-area" style={{ height }} data-collecting={collecting || undefined}>
      <div ref={ref} role="img" aria-label={label} />
      {collecting && <span className="system-area-collecting text-caption">Collecting {label.toLowerCase()}…</span>}
    </div>
  );
}

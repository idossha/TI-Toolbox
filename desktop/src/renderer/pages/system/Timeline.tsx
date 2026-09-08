/**
 * The page's headline: **CPU and memory on one rolling five-minute timeline**.
 *
 * One chart, not two stacked ones, because the question people have is whether the two moved
 * *together* — memory climbing while CPU flatlines is a solve that has started swapping, and two
 * charts on two independent time axes make that something you reconstruct rather than see.
 *
 * The legend is the live read-out ("CPU 0.5 % · Memory 6.6 %"), which is why neither percentage is
 * printed anywhere else on the page (`METRIC_HOME`): a number shown twice is a number a reader has
 * to check for agreement.
 *
 * Per-core is a **toggle, not an addition**: turning it on replaces the footer's twelve bars with
 * twelve lines on the same axis. The same metric, one place, whichever way you are reading it.
 */
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { useEffect, useMemo, useRef, useState } from "react";
import type { SystemSnapshot } from "../../api/client";
import { coreRows, metricsOf, timeline, timelineLegend, WINDOW_MS, type CoreRow } from "./model";

/** The narrowest x-window. Anchoring the right edge at the newest sample and the left edge at
 *  least a minute back keeps the axis in clock time from the very first frame; uPlot would
 *  otherwise label a two-sample series in fractions of a second (":31.400"). */
const MIN_SPAN_S = 60;

function readVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** `#1F5BD7` → `rgba(31,91,215,α)`. Returns the colour unchanged when it is not hex. */
function withAlpha(color: string, alpha: number): string {
  const hex = color.trim();
  if (!/^#([0-9a-f]{6}|[0-9a-f]{3})$/i.test(hex)) return hex;
  const full = hex.length === 4 ? `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}` : hex;
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(full.slice(i, i + 2), 16));
  return `rgba(${r},${g},${b},${alpha})`;
}

export function Timeline({ samples, latest }: { samples: SystemSnapshot[]; latest: SystemSnapshot | undefined }) {
  const [perCore, setPerCore] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);
  const [cursor, setCursor] = useState<{ cpu: string; mem: string; at: string } | null>(null);

  const data = useMemo(() => timeline(samples, { perCore }), [samples, perCore]);
  const legend = useMemo(() => timelineLegend(latest), [latest]);
  const cores = useMemo(() => coreRows(samples), [samples]);
  const themeKey = typeof document === "undefined" ? "" : (document.documentElement.dataset.theme ?? "");

  // The plot is rebuilt when the SHAPE changes (series added or removed by the per-core toggle, or
  // a theme swap that changes every stroke) and updated in place otherwise — `setData` cannot add
  // a series, and rebuilding on every 1 s frame would throw the cursor away as you hover.
  const shapeKey = `${themeKey}:${data.series.length}`;
  useEffect(() => {
    plotRef.current?.destroy();
    plotRef.current = null;
  }, [shapeKey]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const resize = () =>
      plotRef.current?.setSize({ width: el.clientWidth || 320, height: Math.max(120, el.clientHeight || 200) });
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    return () => {
      observer.disconnect();
      plotRef.current?.destroy();
      plotRef.current = null;
    };
  }, []);

  useEffect(() => {
    const el = ref.current;
    // One sample is a dot, not a trend, and uPlot's time scale degenerates when it is constructed
    // with an empty series (its fallback range is min + 1000 days).
    if (!el || data.timestamps.length < 2) return;
    const table: (number[] | null)[] = [data.timestamps, ...data.series.map((s) => s.values)];
    if (!plotRef.current) {
      const grid = readVar("--line", "#D8DEE6");
      const ink2 = readVar("--ink-2", "#4B5865");
      const opts: uPlot.Options = {
        width: el.clientWidth || 320,
        height: Math.max(120, el.clientHeight || 200),
        legend: { show: false },
        cursor: {
          show: true,
          // Both values at the hovered instant, in the header, rather than uPlot's own legend
          // table under the chart — the point of one shared axis is reading the two together.
          y: false,
        },
        padding: [6, 6, 0, 0],
        scales: {
          x: {
            time: true,
            range: (u) => {
              const xs = u.data[0] as number[] | undefined;
              if (!xs || xs.length === 0) return [0, MIN_SPAN_S];
              const last = xs[xs.length - 1]!;
              return [Math.min(xs[0]!, last - MIN_SPAN_S), last];
            },
          },
          // Fixed 0–100. Auto-ranging turns a flat 3 % into a jagged wall, and a reader cannot
          // tell a busy machine from a quiet one at a glance.
          y: { range: [0, 100] },
        },
        axes: [
          { stroke: ink2, grid: { stroke: grid, width: 1, dash: [2, 4] }, ticks: { show: false }, size: 24, space: 110 },
          {
            stroke: ink2,
            grid: { stroke: grid, width: 1, dash: [2, 4] },
            ticks: { show: false },
            size: 38,
            values: (_u, vals) => vals.map((v) => `${v}%`),
          },
        ],
        series: [
          {},
          ...data.series.map((s) => {
            const stroke = readVar(s.colorVar, s.id === "mem" ? "#1F8A50" : "#1F5BD7");
            return {
              label: s.label,
              stroke: s.fill ? stroke : withAlpha(stroke, 0.45),
              width: s.fill ? 1.75 : 0.75,
              fill: s.fill ? withAlpha(stroke, 0.16) : undefined,
              points: { show: false },
            } satisfies uPlot.Series;
          }),
        ],
        hooks: {
          setCursor: [
            (u) => {
              const i = u.cursor.idx;
              if (i === null || i === undefined) {
                setCursor(null);
                return;
              }
              const cpu = (u.data[1] as number[] | undefined)?.[i];
              const mem = (u.data[2] as number[] | undefined)?.[i];
              const ts = (u.data[0] as number[] | undefined)?.[i];
              setCursor({
                cpu: cpu === undefined ? "—" : `${cpu.toFixed(1)} %`,
                mem: mem === undefined ? "—" : `${mem.toFixed(1)} %`,
                at: ts === undefined ? "" : new Date(ts * 1000).toLocaleTimeString(),
              });
            },
          ],
        },
      };
      plotRef.current = new uPlot(opts, table as uPlot.AlignedData, el);
    } else {
      plotRef.current.setData(table as uPlot.AlignedData);
    }
  }, [data, shapeKey]);

  const collecting = data.timestamps.length < 2;

  return (
    <section className="system-panel system-timeline" data-testid="system-timeline" data-metrics={metricsOf("timeline").join(" ")}>
      <header className="system-panel-head">
        <span className="text-eyebrow">Last {Math.round(WINDOW_MS / 60000)} minutes</span>
        <span className="system-timeline-legend tabular-nums" data-testid="timeline-legend">
          {legend.map((l) => (
            <span key={l.id} className="system-timeline-key">
              <span className="system-timeline-swatch" style={{ background: `var(${l.colorVar})` }} aria-hidden />
              {l.label} <strong>{cursor ? (l.id === "cpu" ? cursor.cpu : cursor.mem) : l.value}</strong>
            </span>
          ))}
          {cursor && <span className="system-timeline-at text-caption">at {cursor.at}</span>}
        </span>
        <button
          type="button"
          className="system-chip"
          data-active={perCore || undefined}
          aria-pressed={perCore}
          onClick={() => setPerCore((v) => !v)}
        >
          Per-core
        </button>
      </header>

      <div className="system-timeline-plot">
        <div ref={ref} role="img" aria-label="CPU and memory over the last five minutes" />
        {collecting && (
          <span className="system-timeline-collecting text-caption" aria-live="polite">
            Collecting…
          </span>
        )}
      </div>

      {/* The per-core footer, and the other half of the toggle: with the lines on, twelve gauges
          repeating them would be the same metric twice. */}
      {!perCore && cores.length > 0 && (
        <div className="system-cores-block">
          <span className="text-eyebrow system-cores-label">Per core</span>
          <div
            className="system-cores"
            data-testid="system-cores"
            style={{ gridTemplateColumns: `repeat(${cores.length}, minmax(0, 1fr))` }}
          >
            {cores.map((core) => (
              <CoreGauge key={core.index} core={core} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * One core, as a vertical gauge that spans its share of the card's full width.
 *
 * It was a 6 px sliver with a 1 px fill, in the left third of a card that had the width to spare —
 * which made the one thing this row exists for, *seeing at a glance that one core is pinned while
 * eleven idle*, something you had to squint at. Now the row is `repeat(n, 1fr)` across the card
 * and each gauge is tall enough to read: the fill rises from the bottom, the live percentage sits
 * at the top of the track, and the core's own last-60 s history is drawn faintly behind it — that
 * series is already computed for `coreRows`, so the sparkline costs a `<polyline>` and nothing
 * else.
 */
function CoreGauge({ core }: { core: CoreRow }) {
  const level = Math.max(2, Math.min(100, core.percent));
  return (
    <div className="system-core" data-tone={core.tone} title={`Core ${core.index}: ${core.percent.toFixed(1)} %`}>
      <div className="system-core-track">
        <CoreSpark values={core.history} />
        <div className="system-core-fill" style={{ height: `${level}%` }} />
        <span className="system-core-pct tabular-nums">{Math.round(core.percent)}</span>
      </div>
      <span className="system-core-num text-caption tabular-nums">{core.index}</span>
    </div>
  );
}

/** The core's last 60 s, stretched to fill the gauge behind the level. Fewer than two samples
 *  draws nothing rather than a flat line along the floor, which would read as "0 % for a minute"
 *  when the truth is "we have only just started looking". */
function CoreSpark({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const step = 100 / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(2)},${(100 - Math.max(0, Math.min(100, v))).toFixed(2)}`)
    .join(" ");
  return (
    <svg className="system-core-spark" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
      <polyline points={points} fill="none" strokeWidth={1} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

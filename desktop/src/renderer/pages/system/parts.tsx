/**
 * The small, shared pieces the System page's panels are built from: a stacked meter, a legend, a
 * headline read-out and a per-core cell. They live together because they are one visual language
 * — every bar on the page has the same height, the same tone scale and the same legend shape —
 * and splitting them across the panels is how three bars end up looking like three bars from
 * three different applications.
 */
import type { ReactNode } from "react";
import { bytes } from "../../ui/utils";
import type { Segment } from "./model";

/** A card: an eyebrow title, an optional right-aligned aside, and a body. */
export function Panel({
  title,
  aside,
  children,
  className,
  testId,
  metrics,
}: {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
  /**
   * The metrics this card owns (`model.ts`'s `metricsOf`), published on the DOM so the redundancy
   * audit can check the rule against what is actually rendered rather than against a table that
   * says what ought to be rendered.
   */
  metrics?: readonly string[];
}) {
  return (
    <section
      className={className ? `system-panel ${className}` : "system-panel"}
      data-testid={testId}
      data-metrics={metrics ? metrics.join(" ") : undefined}
    >
      <header className="system-panel-head">
        <span className="text-eyebrow">{title}</span>
        {aside !== undefined && <span className="system-panel-aside text-caption tabular-nums">{aside}</span>}
      </header>
      {children}
    </section>
  );
}

/**
 * A stacked bar. Every meter on the page is one of these, so "used vs cache vs free" and "images
 * vs volumes vs build cache" are read the same way without the reader relearning anything.
 *
 * Segments below ~1 % still get a hairline rather than disappearing: a 200 MB build cache next to
 * 60 GB of images is genuinely tiny, and a bar that drops it silently is saying it is zero.
 */
export function Meter({ segments, testId }: { segments: Segment[]; testId?: string }) {
  if (segments.length === 0) {
    return <div className="system-meter system-meter-empty" data-testid={testId} aria-hidden />;
  }
  return (
    <div className="system-meter" data-testid={testId}>
      {segments.map((s) => (
        <div
          key={s.id}
          className="system-meter-seg"
          data-tone={s.tone}
          style={{ width: `${Math.max(0.6, s.fraction * 100)}%` }}
          title={`${s.label}: ${bytes(s.bytes)}`}
        />
      ))}
    </div>
  );
}

/** The bar's key, as swatch + label + size. Never a colour with no name beside it. */
export function MeterLegend({ segments }: { segments: Segment[] }) {
  if (segments.length === 0) return null;
  return (
    <ul className="system-legend text-caption">
      {segments.map((s) => (
        <li key={s.id}>
          <span className="system-legend-dot" data-tone={s.tone} aria-hidden />
          {s.label} <span className="system-legend-value tabular-nums">{bytes(s.bytes)}</span>
        </li>
      ))}
    </ul>
  );
}


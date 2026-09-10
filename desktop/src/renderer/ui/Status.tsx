import type { ReactNode } from "react";
import { cn } from "./utils";

export type SemanticKind = "neutral" | "accent" | "success" | "warning" | "danger" | "field" | "lost";

export function StatusDot({
  kind = "neutral",
  pulse = false,
  title,
}: {
  kind?: SemanticKind;
  pulse?: boolean;
  title?: string;
}) {
  return (
    <span
      className={cn("status-dot", `status-dot-${kind}`, pulse && "status-dot-pulse")}
      role={title ? "img" : undefined}
      aria-label={title}
      title={title}
    />
  );
}

export function Chip({
  kind = "neutral",
  dot = false,
  pulse = false,
  missing = false,
  title,
  children,
}: {
  kind?: SemanticKind;
  dot?: boolean;
  /** Animate the leading dot (e.g. a running job that is actively emitting). Only meaningful
   * with `dot`. There is always exactly one dot — never add a second, separate `StatusDot`
   * next to a `Chip` that already has one (DESIGN.md §5 chip spec; ra_12 #17). */
  pulse?: boolean;
  missing?: boolean;
  title?: string;
  children: ReactNode;
}) {
  return (
    <span className={cn("chip", `chip-${kind}`, missing && "chip-missing")} title={title}>
      {dot && <span className={cn("chip-dot", pulse && "chip-dot-pulse")} aria-hidden />}
      {children}
    </span>
  );
}

export function Badge({ count, neutral = false }: { count: number; neutral?: boolean }) {
  return <span className={cn("badge", neutral && "badge-neutral")}>{count}</span>;
}

export function Progress({
  value,
  label,
  indeterminate = false,
}: {
  /** 0-100, ignored when indeterminate. */
  value?: number;
  label?: string;
  indeterminate?: boolean;
}) {
  const clamped = value === undefined ? 0 : Math.min(100, Math.max(0, value));
  return (
    <div className="progress">
      {label && (
        <div className="progress-row">
          <span>{label}</span>
          {!indeterminate && <span className="tabular-nums">{Math.round(clamped)} %</span>}
        </div>
      )}
      <div
        className={cn("progress-track", indeterminate && "progress-indeterminate")}
        role="progressbar"
        aria-valuenow={indeterminate ? undefined : Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div className="progress-fill" style={indeterminate ? undefined : { width: `${clamped}%` }} />
      </div>
    </div>
  );
}

/** "active" pulses; "stalled" shows elapsed time as a warning. Never a fake percentage. */
export function LivenessBadge({ state, stalledFor }: { state: "active" | "stalled"; stalledFor?: string }) {
  return (
    <span className={cn("liveness", state === "active" ? "liveness-active" : "liveness-stalled")}>
      <StatusDot kind={state === "active" ? "success" : "warning"} pulse={state === "active"} />
      {state === "active" ? "active" : `stalled${stalledFor ? ` ${stalledFor}` : ""}`}
    </span>
  );
}

export type JobState = "queued" | "running" | "succeeded" | "failed" | "cancelled" | "skipped" | "lost";

const JOB_STATE_KIND: Record<JobState, SemanticKind> = {
  queued: "neutral",
  running: "accent",
  succeeded: "success",
  failed: "danger",
  cancelled: "warning",
  skipped: "neutral",
  lost: "lost",
};

export function JobStateChip({ state, pulse }: { state: JobState; pulse?: boolean }) {
  const isRunning = state === "running";
  const liveness = isRunning && pulse !== undefined ? (pulse ? "active" : "stalled") : undefined;
  return (
    <Chip kind={JOB_STATE_KIND[state]} dot pulse={isRunning && pulse === true} title={liveness}>
      {state}
    </Chip>
  );
}

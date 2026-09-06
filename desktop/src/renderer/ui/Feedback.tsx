import { AlertTriangle, Info, OctagonAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "./utils";
import { Button } from "./Button";

/**
 * `page` — the whole-page empty: centred, icon, one sentence, one action.
 * `inline` — the empty state of a surface inside a populated page (a panel, an inspector block, a
 * table body): left- and top-aligned, at most two lines, one action, no icon, no box. A centred
 * 180px block inside a 300px inspector is a hole, not a state.
 */
export type EmptyStateVariant = "page" | "inline";

export function EmptyState({
  icon,
  message,
  actionLabel,
  onAction,
  variant = "page",
  className,
}: {
  icon?: ReactNode;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  variant?: EmptyStateVariant;
  className?: string;
}) {
  const inline = variant === "inline";
  return (
    <div className={cn("empty-state", inline && "empty-state-inline", className)}>
      {icon && !inline && <div className="empty-state-icon">{icon}</div>}
      <p className="empty-state-message">{message}</p>
      {actionLabel && onAction && (
        <Button variant={inline ? "ghost" : "primary"} size="sm" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
}

/**
 * A skeleton is sized to the rows it replaces, never to a slab: `<Skeleton rows={3} />` is three
 * `--row-h` bars, which is exactly what a three-row table becomes. `height={240}` in front of
 * 84px of real content is a guaranteed layout jump on first paint.
 *
 * Skeletons are for FIRST load only. A refetch of a populated surface uses `RefetchBar`.
 */
export function Skeleton({
  width,
  height = 16,
  rows,
  className,
}: {
  width?: number | string;
  height?: number | string;
  /** Number of `--row-h` rows to stand in for. Overrides `height`. */
  rows?: number;
  className?: string;
}) {
  if (rows !== undefined) {
    return (
      <div className={cn("skeleton-rows", className)} aria-hidden>
        {Array.from({ length: Math.max(0, rows) }, (_, i) => (
          <div key={i} className="skeleton" style={{ width: width ?? "100%", height: "var(--row-h)" }} />
        ))}
      </div>
    );
  }
  return (
    <div
      className={cn("skeleton", className)}
      style={{ width: width ?? "100%", height }}
      aria-hidden
    />
  );
}

/**
 * A failed data load is never a toast — a toast disappears and takes the explanation with it. It
 * is an inline error in the surface that failed, next to the thing that is missing, carrying the
 * retry that fixes it.
 */
export function InlineError({
  message,
  detail,
  actionLabel = "Retry",
  onAction,
  className,
}: {
  message: string;
  /** The server's own message, verbatim. Shown small, under the sentence, never in place of it. */
  detail?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}) {
  return (
    <div className={cn("inline-error", className)} role="alert">
      <span className="inline-error-icon" aria-hidden>
        <OctagonAlert size={14} />
      </span>
      <div className="inline-error-body">
        <span>{message}</span>
        {detail && <span className="inline-error-detail mono">{detail}</span>}
      </div>
      {onAction && (
        <span className="inline-error-action">
          <Button variant="secondary" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        </span>
      )}
    </div>
  );
}

export type CalloutKind = "info" | "warning" | "danger";

const CALLOUT_ICON: Record<CalloutKind, ReactNode> = {
  info: <Info size={16} />,
  warning: <AlertTriangle size={16} />,
  danger: <OctagonAlert size={16} />,
};

export function Callout({ kind = "info", title, children }: { kind?: CalloutKind; title?: string; children: ReactNode }) {
  return (
    <div className={cn("callout", `callout-${kind}`)} role={kind === "danger" ? "alert" : undefined}>
      <span className="callout-icon">{CALLOUT_ICON[kind]}</span>
      <div>
        {title && <div className="callout-title">{title}</div>}
        <div>{children}</div>
      </div>
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

export function DefinitionList({ entries }: { entries: [string, ReactNode][] }) {
  return (
    <dl className="definition-list">
      {entries.map(([term, value], i) => (
        <div key={`${term}-${i}`} className="contents">
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

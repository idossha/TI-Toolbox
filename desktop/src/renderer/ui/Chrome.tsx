import { ChevronDown } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Badge } from "./Status";
import { Button } from "./Button";
import { Kbd } from "./Feedback";
import { cn } from "./utils";

/**
 * The shell's horizontal strips. The shell (S1) decides what goes in them; the design system owns
 * their geometry, so a page can reserve space for one — or measure the viewport left under the
 * chrome — without knowing how the shell is assembled.
 */

/** 40px bar under the top of the content column: scope on the left, global state on the right. */
export function ContextBar({ children, end, className }: { children: ReactNode; end?: ReactNode; className?: string }) {
  return (
    <div className={cn("context-bar", className)}>
      {children}
      {end && <div className="context-bar-end">{end}</div>}
    </div>
  );
}

export interface CrumbProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** The thing this crumb names: a project, a subject, a run. */
  label: ReactNode;
  /** Presence chips or counts rendered after the label, inside the trigger. */
  meta?: ReactNode;
  /** Shows the chevron. A crumb with no picker behind it is still a crumb, just not a switcher. */
  switcher?: boolean;
}

/**
 * A context-bar crumb, optionally a switcher trigger. This is the primitive the shell's subject
 * switcher is built from — the ONE subject picker in the app; pages never grow their own.
 */
export const Crumb = forwardRef<HTMLButtonElement, CrumbProps>(function Crumb(
  { label, meta, switcher, className, ...rest },
  ref,
) {
  return (
    <button ref={ref} type="button" className={cn("crumb", className)} {...rest}>
      <span className="crumb-label">{label}</span>
      {meta && <span className="crumb-meta">{meta}</span>}
      {switcher && <ChevronDown className="crumb-chevron" size={12} aria-hidden />}
    </button>
  );
});

/** The "›" between crumbs. Decorative — screen readers get the crumb labels, not the glyph. */
export function CrumbSeparator() {
  return (
    <span className="crumb-separator" aria-hidden>
      ›
    </span>
  );
}

export interface ActionBarProps {
  /**
   * The plan's one-line digest: "2 jobs · 8 CPU · 16 GB · 1 overwrite". Shown only while the run
   * is startable — when it is not, the digest is **not** rendered at all.
   */
  digest?: ReactNode;
  /**
   * The plan cannot be resolved. The bar then prints no digest: the single signal that a run
   * cannot start is the primary itself — disabled, in the disabled treatment, with the reason as
   * its `title` (maintainer call, 2026-09; supersedes the older "never a silent disabled button").
   */
  blocked?: boolean;
  /** Problem count, shown as a chip. Clicking it jumps to the first problem. */
  warningCount?: number;
  onWarningsClick?: () => void;
  /** One secondary action at most ("Save preset ▾"). */
  secondary?: ReactNode;
  /** The primary. Its label comes from the plan: "Run simulation", "Queue 3 jobs". */
  primary?: ReactNode;
  /** Shows the ⌘⏎ hint next to the primary. */
  shortcutHint?: boolean;
  className?: string;
}

/**
 * The sticky 44px bar at the bottom of a run screen's work pane. The Plan panel keeps the detail
 * (resolved outputs, overwrite markers, lock waits); the bar keeps the digest and the button, so
 * you commit from a control that is next to the field you last edited.
 */
export function ActionBar({
  digest,
  blocked,
  warningCount = 0,
  onWarningsClick,
  secondary,
  primary,
  shortcutHint = true,
  className,
}: ActionBarProps) {
  return (
    <div className={cn("action-bar", className)}>
      {digest !== undefined && !blocked && (
        <span className="action-bar-digest" title={typeof digest === "string" ? digest : undefined}>
          {digest}
        </span>
      )}
      {warningCount > 0 && (
        <span className="action-bar-warnings">
          <Button variant="ghost" size="sm" onClick={onWarningsClick}>
            {warningCount} {warningCount === 1 ? "problem" : "problems"}
          </Button>
        </span>
      )}
      <div className="action-bar-end">
        {secondary}
        {primary && <div className="action-bar-primary">{primary}</div>}
        {primary && shortcutHint && (
          <span className="action-bar-hint">
            <Kbd>⌘⏎</Kbd>
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * Refetch is a 2px indeterminate bar under the context bar — never a re-skeleton. A populated
 * surface that re-skeletons on refresh makes the page jump between two identical states.
 * Renders nothing (and reserves no space) when `active` is false.
 */
export function RefetchBar({ active, className }: { active: boolean; className?: string }) {
  if (!active) return null;
  return (
    <div className={cn("refetch-bar", className)} role="progressbar" aria-label="Refreshing" aria-busy>
      <div className="refetch-bar-fill" />
    </div>
  );
}

/** Count chip for a context bar or a section header ("3 running"). */
export function CountChip({ count, label }: { count: number; label: string }) {
  return (
    <span className="cluster gap-1 items-center">
      <Badge count={count} neutral />
      <span>{label}</span>
    </span>
  );
}

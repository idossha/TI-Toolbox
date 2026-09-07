import { type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes, useId } from "react";
import { HelpIcon } from "./HelpPopover";
import { cn } from "./utils";

/**
 * `layout` picks the row shape.
 *
 *  - `row` (default) — label left in a `var(--field-label-w)` gutter, control right, 28px tall.
 *    This is the density the whole app is tuned to: ten fields cost 280px, not 700px.
 *  - `stacked` — the v1 shape (label above control). The escape hatch for a row that needs the
 *    full column width but still wants a visible label.
 */
export type FieldLayout = "row" | "stacked";

export interface FieldProps {
  label: string;
  htmlFor?: string;
  required?: boolean;
  /**
   * One sentence of help. It is NOT a third line any more — it is an (i) trigger next to the
   * label that opens a Popover. Units belong inside the control as a suffix (`NumberInput`'s
   * `unit`), never here.
   */
  help?: string;
  error?: string;
  /**
   * A visible line under the control, for a constraint the form is currently applying — a
   * disabled option's reason, a value the current mode forces. Distinct from `help`, which is an
   * (i) popover a reader opens on purpose: a reason the control is not doing what someone just
   * asked for has to be readable without a click (DESIGN.md v2 §4.2), and distinct from `error`,
   * which says the input is wrong.
   */
  note?: string;
  children: ReactNode;
  /** Extra trigger rendered next to the label (a page's own Popover, a "learn more" link). */
  helpSlot?: ReactNode;
  layout?: FieldLayout;
  /**
   * Drop the label gutter and let the control span the row. The named exceptions from DESIGN.md
   * §3 — coordinate/sphere tables, `ElectrodePairsEditor`, `KeyValueTable`, `PathInput`, chip
   * `MultiSelect`, consoles, callouts — also request this structurally (a `:has()` rule in
   * components.css), so they behave correctly inside pages written before this prop existed.
   */
  fullBleed?: boolean;
  /**
   * Defaults are visible, changes are marked. `false` renders the value in `--ink-2`; `true`
   * renders it in `--ink` and puts a 2px accent tick in the label gutter. Leave it `undefined` to
   * opt the field out of the mechanism entirely (no tint, no tick).
   */
  changed?: boolean;
  className?: string;
}

/** Label, control and error — the wrapper every form input renders inside. */
export function Field({
  label,
  htmlFor,
  required,
  help,
  error,
  note,
  children,
  helpSlot,
  layout = "row",
  fullBleed,
  changed,
  className,
}: FieldProps) {
  const errorId = useId();
  return (
    <div
      className={cn(
        "field",
        layout === "stacked" && "field-stacked",
        fullBleed && "field-full-bleed",
        changed === true && "field-changed",
        changed === false && "field-default",
        className,
      )}
    >
      <div className="field-label-row">
        <label htmlFor={htmlFor} className="field-label">
          {/* Own element, not a bare text node — see the note in `Toggle.tsx`. Here it only bit on
              a `required` field, whose `*` span made the <label> a non-leaf and its text invisible
              to the dead-space probe: every required row on the Optimizer read as empty ground. */}
          <span className="field-label-text">{label}</span>
          {required && (
            <>
              {" "}
              <span className="field-required" aria-hidden>
                *
              </span>
            </>
          )}
        </label>
        {help && (
          // The accessible name is deliberately just "Help" and does NOT repeat the field label:
          // an accessible name containing the label would make `getByLabel("<label>")` — how every
          // form is driven, in tests and by assistive tech alike — resolve to two elements. The
          // field context is carried by the popover's own heading instead.
          <HelpIcon variant="plain" size={12} title={label} text={help} />
        )}
        {helpSlot}
      </div>
      <div className="field-control">{children}</div>
      {error && (
        <span id={errorId} role="alert" className="field-error">
          {error}
        </span>
      )}
      {!error && note && <span className="field-note">{note}</span>}
    </div>
  );
}

/**
 * Which fields differ from their defaults. Feed the result to `Field`'s `changed` prop so a form
 * marks its own changes without every call site hand-writing a comparison, and to `FormSection`'s
 * `changedCount` so a collapsed section can badge them.
 *
 * Not a hook (no state, no effects) — a pure comparison over two plain objects, so it is safe to
 * call anywhere, including inside a `map`. Values are compared with `JSON.stringify` so arrays and
 * small objects (an ROI, a coordinate) compare structurally; that is deliberate, and the reason
 * this is a helper rather than a `===` at each call site.
 */
export function changedFields<T extends object>(values: Partial<T>, defaults: Partial<T>): Set<keyof T> {
  const changed = new Set<keyof T>();
  for (const key of Object.keys(defaults) as (keyof T)[]) {
    if (!same(values[key], defaults[key])) changed.add(key);
  }
  for (const key of Object.keys(values) as (keyof T)[]) {
    if (!(key in defaults) && values[key] !== undefined) changed.add(key);
  }
  return changed;
}

function same(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === undefined || b === undefined || a === null || b === null) return false;
  if (typeof a !== "object" && typeof b !== "object") return false;
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * The form-facing wrapper: `const isChanged = useChangedFields(values, defaults)` then
 * `<Field changed={isChanged("goal")} …>`. Named as a hook because call sites read it as one and
 * because a future memoised version must stay a hook to be swappable.
 */
export function useChangedFields<T extends object>(
  values: Partial<T>,
  defaults: Partial<T>,
): ((key: keyof T) => boolean) & { count: number; keys: Set<keyof T> } {
  const keys = changedFields(values, defaults);
  const fn = (key: keyof T) => keys.has(key);
  return Object.assign(fn, { count: keys.size, keys });
}

export function describedBy(help?: string, error?: string, helpId?: string, errorId?: string): string | undefined {
  const ids = [error && errorId, !error && help && helpId].filter(Boolean) as string[];
  return ids.length ? ids.join(" ") : undefined;
}

export function TextInput({
  className,
  invalid,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return <input className={cn("control", invalid && "control-error", className)} {...rest} />;
}

export function Textarea({
  className,
  invalid,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  return <textarea className={cn("control", invalid && "control-error", className)} {...rest} />;
}

import { Fragment } from "react";

/** `X_{sub}` in display text: `TI_{max}`, `HF_{peak}` (tit.constants.FIELD_REGISTRY labels). */
const SUBSCRIPT = /_\{([^}]*)\}/g;

/**
 * *text* with every `X_{sub}` drawn as X with a `<sub>` — the one renderer of field display labels
 * (`fieldLabel`). Text without braces is returned as it is.
 */
export function Subscripted({ text }: { text: string }) {
  if (!text.includes("_{")) return <>{text}</>;
  const parts = text.split(SUBSCRIPT);
  // One span: inside a flex label (gap) a fragment's text and <sub> would be separate items.
  // split with one capture group alternates plain text and subscript text.
  return <span>{parts.map((part, i) => (i % 2 ? <sub key={i}>{part}</sub> : <Fragment key={i}>{part}</Fragment>))}</span>;
}

/** *text* for a place that holds no markup (a `title`, an `aria-label`): `TI_{max}` → `TI_max`. */
export function plainLabel(text: string): string {
  return text.replace(SUBSCRIPT, "_$1");
}

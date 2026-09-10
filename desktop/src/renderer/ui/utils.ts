import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge class names; safe to use with or without Tailwind utility classes. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Stable id generator for form/aria wiring in components that don't get an id prop. Not a hook
 * (no "use" prefix) so it is safe to call outside render rules — components still prefer React's
 * own `useId()` where SSR-safe ids matter; this is for one-off DOM ids in client-only components.
 */
let seq = 0;
export function nextId(prefix: string): string {
  seq += 1;
  return `${prefix}-${seq}`;
}

export function bytes(n: number): string {
  const gb = n / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = n / 1024 ** 2;
  return mb >= 1 ? `${mb.toFixed(0)} MB`.trim() : `${(n / 1024).toFixed(0)} KB`;
}

export function pct(n: number | undefined | null, digits = 1): string {
  return n === undefined || n === null ? "—" : `${n.toFixed(digits)} %`;
}

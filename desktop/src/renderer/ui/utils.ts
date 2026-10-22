import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge class names; safe to use with or without Tailwind utility classes. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
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

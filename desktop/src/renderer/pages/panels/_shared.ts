/**
 * Bridges `settings.panels` (server truth, fetched async by the Settings page) to each panel
 * page's static `PageDef.enabled` (read once, synchronously, when the page registry module
 * graph loads — see `app/registry.ts`'s `import.meta.glob(..., { eager: true })`).
 *
 * Same trick as `app/theme/store.ts`'s `initTheme()`: a localStorage mirror gives a synchronous
 * answer before the first network round trip, at the cost of being one save behind the server on
 * a machine that has never opened Settings. `pages/settings` calls `writeEnabledPanels` on every
 * successful load and save; each panel's `index.tsx` calls `isPanelEnabled(id)` once, at module
 * scope, to set its own `enabled`.
 *
 * Known gap (out of P8's ownership — reported in the final task report): `app/registry.ts` and
 * `app/NavRail.tsx` (F2-owned) read the static `enabled` field once and never re-render on
 * change, so a toggle only reaches the nav after `pages/settings` reloads the window. A live
 * settings store feeding `enabledPages`/`navGroups` would remove that reload.
 */
import type { components } from "../../api/schema";

export type PlanResult = components["schemas"]["PlanResult"];
export type ValidateResult = components["schemas"]["ValidateResult"];

const STORAGE_KEY = "tit-enabled-panels";

export type PanelId =
  | "source"
  | "cluster-permutation"
  | "nifti-group-average"
  | "nilearn-visuals"
  | "visual-exporter"
  | "quick-notes"
  | "subject-info";

export function readEnabledPanels(): string[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) return parsed.filter((p): p is string => typeof p === "string");
    }
  } catch {
    // localStorage unavailable (private mode, sandboxed webview) — no panels enabled by default.
  }
  return [];
}

export function writeEnabledPanels(panels: string[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(panels));
  } catch {
    // best-effort mirror only
  }
}

export function isPanelEnabled(id: PanelId): boolean {
  return readEnabledPanels().includes(id);
}

/**
 * The action bar's one-line digest, in the four run pages' own words: the first blocking reason
 * while the run cannot start, then `2 jobs · 8 CPU · 16 GB` once it can (DESIGN.md §4.7 L3 — the
 * action bar always shows the digest of what will run, or the reason it cannot).
 *
 * The failure it prevents: a panel that reported problems only as a list of sentences above a
 * Run button that stayed enabled, and said nothing at all about the cost of what it was about to
 * queue — four panels, four ways, none of them the one every run page uses.
 */
export function panelDigest(problems: string[], plan: PlanResult | null | undefined, loading: boolean): string {
  if (problems.length > 0) return problems[0] as string;
  if (loading || !plan) return "Resolving the plan…";
  const jobs = plan.jobs.length;
  return `${jobs} ${jobs === 1 ? "job" : "jobs"} · ${plan.cost.cpus} CPU · ${plan.cost.mem_gb} GB`;
}

/**
 * The jobs UI state the three heights share: which job is selected, which panel tab is showing,
 * and the page's filters. It is a store rather than component state because the rail, the panel
 * and the page are three views of one thing — clicking a trace in the 32px rail must select that
 * job in the 260px panel and in the full page, and going from one to the other must not lose the
 * selection.
 */
import { create } from "zustand";

export type JobsPanelTab = "jobs" | "console" | "host" | "report";

export const JOBS_PANEL_TABS: { value: JobsPanelTab; label: string }[] = [
  { value: "jobs", label: "Jobs" },
  { value: "console", label: "Console" },
  { value: "host", label: "Host" },
  { value: "report", label: "Report" },
];

/** The "all" sentinel for a filter that is not narrowing anything. */
export const ALL = "all";

export interface JobsFilters {
  state: string;
  kind: string;
  subject: string;
}

export const NO_FILTERS: JobsFilters = { state: ALL, kind: ALL, subject: ALL };

export interface JobsUiState {
  selectedId: string | null;
  tab: JobsPanelTab;
  filters: JobsFilters;
  /** The full page's "Groups" toggle: subject → stage trees instead of a flat table. */
  grouped: boolean;
  select: (id: string | null) => void;
  setTab: (tab: JobsPanelTab) => void;
  setFilter: (key: keyof JobsFilters, value: string) => void;
  clearFilters: () => void;
  setGrouped: (grouped: boolean) => void;
}

const DEFAULT_JOBS_UI = {
  selectedId: null,
  tab: "jobs" as JobsPanelTab,
  filters: NO_FILTERS,
  grouped: false,
};

export const useJobsUi = create<JobsUiState>((set) => ({
  ...DEFAULT_JOBS_UI,
  /** Selecting a job also puts the panel on a tab that shows it — never on Host. */
  select: (id) => set((s) => ({ selectedId: id, tab: s.tab === "host" ? "jobs" : s.tab })),
  setTab: (tab) => set({ tab }),
  setFilter: (key, value) => set((s) => ({ filters: { ...s.filters, [key]: value } })),
  clearFilters: () => set({ filters: NO_FILTERS }),
  setGrouped: (grouped) => set({ grouped }),
}));

/** Actual project switches discard session-only jobs page choices. */
export function resetJobsUi(): void {
  useJobsUi.setState(DEFAULT_JOBS_UI);
}

/** Pure, so the filter row and its "N of M" count cannot drift apart. */
export function applyJobsFilters<T extends { state: string; kind: string; subject_ids: string[] }>(
  jobs: T[],
  filters: JobsFilters,
): T[] {
  return jobs.filter(
    (j) =>
      (filters.state === ALL || j.state === filters.state) &&
      (filters.kind === ALL || j.kind === filters.kind) &&
      (filters.subject === ALL || j.subject_ids.includes(filters.subject)),
  );
}

export function activeFilterCount(filters: JobsFilters): number {
  return (Object.values(filters) as string[]).filter((v) => v !== ALL).length;
}

/**
 * Execution preferences — user-level, not per page (maintainer, 2026-09-06: "This should only be
 * present in the settings page and is a user level setting").
 *
 * `existingOutputs` is the default answer to the shared existing-outputs question (Skip / Replace).
 * It lives in Settings ▸ Execution and is persisted in localStorage the way the theme is
 * (`app/theme/store.ts`). The retired `parallelSubjects` key an older build stored there is ignored
 * and dropped on the next write: one job per product runs at a time (DECISIONS 2026-09-22).
 */
import { create } from "zustand";

export type ExistingOutputPolicy = "skip" | "replace";

const STORAGE_KEY = "tit-execution-prefs";

export interface ExecutionPrefs {
  existingOutputs: ExistingOutputPolicy;
}

export const DEFAULT_EXECUTION_PREFS: ExecutionPrefs = { existingOutputs: "skip" };

function readStored(): ExecutionPrefs {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const v = JSON.parse(raw) as Partial<ExecutionPrefs>;
      return {
        existingOutputs: v.existingOutputs === "replace" ? "replace" : "skip",
      };
    }
  } catch {
    // localStorage unavailable or corrupt — defaults.
  }
  return { ...DEFAULT_EXECUTION_PREFS };
}

interface ExecutionPrefsState extends ExecutionPrefs {
  setExecutionPrefs: (patch: Partial<ExecutionPrefs>) => void;
}

export const useExecutionPrefs = create<ExecutionPrefsState>((set, get) => ({
  ...readStored(),
  setExecutionPrefs: (patch) => {
    const next: ExecutionPrefs = {
      existingOutputs: patch.existingOutputs ?? get().existingOutputs,
    };
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // best-effort persistence only
    }
    set(next);
  },
}));

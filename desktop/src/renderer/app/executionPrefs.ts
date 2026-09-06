/**
 * Execution preferences — user-level, not per page (maintainer, 2026-09-06: "This should only be
 * present in the settings page and is a user level setting").
 *
 * `existingOutputs` is the default answer to the shared existing-outputs question (Skip / Replace)
 * and `parallelSubjects` is the `Subjects in parallel` cap that goes on every job-group request.
 * Both used to be a collapsed section on each run page; they now live in Settings ▸ Execution and
 * are persisted in localStorage the way the theme is (`app/theme/store.ts`).
 */
import { create } from "zustand";

export type ExistingOutputPolicy = "skip" | "replace";

const STORAGE_KEY = "tit-execution-prefs";

export interface ExecutionPrefs {
  existingOutputs: ExistingOutputPolicy;
  parallelSubjects: number;
}

export const DEFAULT_EXECUTION_PREFS: ExecutionPrefs = { existingOutputs: "skip", parallelSubjects: 1 };

function readStored(): ExecutionPrefs {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const v = JSON.parse(raw) as Partial<ExecutionPrefs>;
      return {
        existingOutputs: v.existingOutputs === "replace" ? "replace" : "skip",
        parallelSubjects: Number.isInteger(v.parallelSubjects) && (v.parallelSubjects as number) >= 1 ? (v.parallelSubjects as number) : 1,
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
      parallelSubjects: Math.max(1, Math.floor(patch.parallelSubjects ?? get().parallelSubjects)),
    };
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // best-effort persistence only
    }
    set(next);
  },
}));

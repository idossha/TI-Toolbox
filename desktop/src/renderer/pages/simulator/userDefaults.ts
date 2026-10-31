/**
 * The user's own defaults for new Simulator jobs, set in Settings ▸ Simulator.
 *
 * Persisted in localStorage the way the execution preferences are (`app/executionPrefs.ts`). Only
 * the settings that differ from the factory defaults (`defaultJobSettings()`, the one source of
 * those) are stored, so a factory default the user never changed keeps following the app. A job
 * row with no settings of its own runs with these, and its Job settings dialog resets to them.
 */
import { useMemo } from "react";
import { create } from "zustand";
import { defaultJobSettings, type JobSettings } from "./types";

const STORAGE_KEY = "tit-simulator-defaults";

/** What is stored: the user's changes from the factory defaults. */
export type SavedSimulatorDefaults = Partial<JobSettings>;

function readStored(): SavedSimulatorDefaults {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null");
    if (value && typeof value === "object" && !Array.isArray(value)) return value as SavedSimulatorDefaults;
  } catch {
    // localStorage unavailable or corrupt: the factory defaults.
  }
  return {};
}

const kind = (v: unknown) => (Array.isArray(v) ? "array" : v === null ? "null" : typeof v);

/** The saved changes over the factory defaults. A stored value the factory has no field for, or of
 *  another type (a corrupt or hand-edited store), is ignored. */
export function resolveSimulatorDefaults(saved: SavedSimulatorDefaults): JobSettings {
  const factory = defaultJobSettings();
  const kept = Object.entries(saved).filter(([key, value]) => key in factory && kind(value) === kind(factory[key as keyof JobSettings]));
  return { ...factory, ...Object.fromEntries(kept) };
}

interface SimulatorDefaultsState {
  saved: SavedSimulatorDefaults;
  /** Save *next* as the defaults for new jobs; `null` restores the factory defaults. */
  setSimulatorDefaults: (next: JobSettings | null) => void;
}

export const useSimulatorDefaults = create<SimulatorDefaultsState>((set) => ({
  saved: readStored(),
  setSimulatorDefaults: (next) => {
    const factory = defaultJobSettings();
    const saved: SavedSimulatorDefaults = next
      ? Object.fromEntries(Object.entries(next).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(factory[key as keyof JobSettings])))
      : {};
    try {
      if (Object.keys(saved).length) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // best-effort persistence only
    }
    set({ saved });
  },
}));

/** The defaults a new job starts from, live: they follow Settings ▸ Simulator. */
export function useSimulatorJobDefaults(): JobSettings {
  const saved = useSimulatorDefaults((s) => s.saved);
  return useMemo(() => resolveSimulatorDefaults(saved), [saved]);
}

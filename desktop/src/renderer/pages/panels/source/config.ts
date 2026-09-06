/**
 * Pure `SourceConfig` builders, split out of `index.tsx` so `tests/unit/source-defaults.test.ts`
 * can validate them against `contracts/schema.json` without rendering React — same split as
 * `pages/simulator/buildConfig.ts`. Typed against the real `SourceConfig` `$def` (ra_13 finding
 * #10) instead of `Record<string, unknown>`.
 */
import type { SourceConfig } from "./api";

export interface ForwardFormState {
  subjectIds: string[];
  eegNet: string;
  fsaverageSpacing: number;
  cpus: number;
  overwrite: boolean;
}

/**
 * `tit/source/config.py`'s `SourceConfig.eeg_net` docstring: "EEG cap name **without** the
 * `.csv` suffix" — the runner always appends it itself (`forward.py`: `f"{cfg.eeg_net}.csv"`).
 * `index.tsx`'s `net` state is one of `SubjectDetail.eeg_nets`, which (like every other page's
 * EEG-net catalog) carries the real filename *with* `.csv` — sent unstripped, the runner looks
 * for `<net>.csv.csv` and fails with "EEG net not found" on every real project (verified: a real
 * run against `sub-101`/`EEG10-10_UI_Jurak_2007.csv` failed on exactly that double suffix).
 */
function stripCsvSuffix(net: string): string {
  return net.replace(/\.csv$/i, "");
}

export function buildForwardConfig(state: ForwardFormState): SourceConfig {
  return {
    mode: "forward",
    subject_ids: state.subjectIds,
    forward: { eeg_net: stripCsvSuffix(state.eegNet), fsaverage_spacing: state.fsaverageSpacing, cpus: state.cpus, overwrite: state.overwrite },
  };
}

export interface FsavgPair {
  subject_id: string;
  simulation: string;
}

export interface FsavgFormState {
  pairs: FsavgPair[];
  fields: string[];
  fsaverageSpacing: number;
  workers: number;
  overwrite: boolean;
}

export function buildFsavgConfig(state: FsavgFormState): SourceConfig {
  return {
    mode: "fsavg_map",
    pairs: state.pairs,
    fsavg_map: { fields: state.fields, fsaverage_spacing: state.fsaverageSpacing, workers: state.workers, overwrite: state.overwrite },
  };
}

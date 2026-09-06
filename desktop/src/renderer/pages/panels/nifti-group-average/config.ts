/**
 * Pure `NiftiAverageConfig` builder, split out of `index.tsx` so a defaults test can validate it
 * against `contracts/schema.json` without rendering React — same split as
 * `pages/panels/cluster-permutation/config.ts`.
 */
import type { NiftiAverageConfig } from "./api";

export interface NiftiAverageRow {
  subjectId: string;
  simulationName: string;
  group: string;
}

export function buildNiftiAverageConfig(args: {
  outputName: string;
  rows: NiftiAverageRow[];
  space: "subject" | "mni";
  niftiFilePattern: string;
  diffPairs: string[];
}): NiftiAverageConfig {
  return {
    output_name: args.outputName,
    subjects: args.rows.map((r) => ({ subject_id: r.subjectId, simulation_name: r.simulationName, group: r.group })),
    space: args.space,
    nifti_file_pattern: args.niftiFilePattern.trim() || null,
    diff_pairs: args.diffPairs,
  };
}

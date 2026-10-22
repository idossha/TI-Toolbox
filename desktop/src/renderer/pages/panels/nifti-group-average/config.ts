/**
 * Pure `NiftiAverageConfig` builder, split out of `index.tsx` so a defaults test can validate it
 * against `contracts/generated/config.schema.json` without rendering React — same split as
 * `pages/panels/cluster-permutation/config.ts`.
 */
import type { NiftiAverageConfig } from "./api";

/** Each space's default file, mirrored from `tit/stats/nifti_average_config.py`'s
 *  `_DEFAULT_PATTERNS` (pinned by `nifti-group-average-defaults.test.ts`). Only the placeholder
 *  reads it: an empty pattern is sent as `null`, so the server picks the space's own file. */
export const DEFAULT_PATTERNS = {
  mni: "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
  subject: "grey_{simulation_name}_TI_subject_TI_max.nii.gz",
} as const;

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
    // Trimmed, as the panel's eligibility check reads it: "Group1 " and "Group1" are one group.
    subjects: args.rows.map((r) => ({ subject_id: r.subjectId, simulation_name: r.simulationName, group: r.group.trim() })),
    space: args.space,
    nifti_file_pattern: args.niftiFilePattern.trim() || null,
    diff_pairs: args.diffPairs,
  };
}

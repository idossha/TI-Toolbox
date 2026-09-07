/**
 * Pure `NilearnConfig` builder, split out of `index.tsx` so a defaults test can validate it
 * against `contracts/generated/config.schema.json` without rendering React — same split as
 * `pages/panels/cluster-permutation/config.ts`.
 */
import type { NilearnConfig } from "./api";

export interface NilearnPair {
  subjectId: string;
  simulationName: string;
}

export function buildNilearnConfig(args: {
  pairs: NilearnPair[];
  subdirName: string;
  usePercentiles: boolean;
  minCutoff: number;
  maxCutoff: number;
  atlasName: string;
  selectedRegion: string;
}): NilearnConfig {
  return {
    subject_simulation_pairs: args.pairs.map((p) => ({ subject_id: p.subjectId, simulation_name: p.simulationName })),
    subdir_name: args.subdirName,
    use_percentiles: args.usePercentiles,
    min_cutoff: args.minCutoff,
    max_cutoff: args.maxCutoff,
    atlas_name: args.atlasName,
    selected_regions: args.selectedRegion === "__all__" ? null : [Number(args.selectedRegion)],
    create_glass_brain: true,
    glass_brain_cmap: "hot",
  };
}

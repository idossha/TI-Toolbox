/**
 * Pure `GroupComparisonConfig`/`CorrelationConfig` builders, split out of `index.tsx` so
 * `tests/unit/cluster-permutation-defaults.test.ts` can validate them against
 * `contracts/schema.json` without rendering React — same split as
 * `pages/simulator/buildConfig.ts`.
 */
import type { CorrelationConfig, GroupComparisonConfig } from "./api";

export interface SharedStatsFields {
  analysisName: string;
  clusterThreshold: number;
  clusterStat: "mass" | "size";
  nPermutations: number;
  alpha: number;
  nJobs: number;
  tissueType: "grey" | "white" | "all";
  niftiPattern: string;
  space: "mni" | "fsaverage";
  fsaverageField: string;
  fsaverageSpacing: number;
  atlasFiles: string[];
}

function sharedConfig(shared: SharedStatsFields) {
  return {
    analysis_name: shared.analysisName,
    cluster_threshold: shared.clusterThreshold,
    cluster_stat: shared.clusterStat,
    n_permutations: shared.nPermutations,
    alpha: shared.alpha,
    n_jobs: shared.nJobs,
    tissue_type: shared.tissueType,
    nifti_file_pattern: shared.niftiPattern.trim() || null,
    space: shared.space,
    fsaverage_field: shared.fsaverageField,
    fsaverage_spacing: shared.fsaverageSpacing,
    atlas_files: shared.atlasFiles,
  };
}

export interface ClassificationRow {
  subjectId: string;
  simulationName: string;
  response: 0 | 1;
}

export function buildGroupComparisonConfig(
  shared: SharedStatsFields,
  rows: ClassificationRow[],
  extra: { testType: "unpaired" | "paired"; alternative: "two-sided" | "greater" | "less"; group1Name: string; group2Name: string; valueMetric: string },
): GroupComparisonConfig {
  return {
    ...sharedConfig(shared),
    subjects: rows.map((r) => ({ subject_id: r.subjectId, simulation_name: r.simulationName, response: r.response })),
    test_type: extra.testType,
    alternative: extra.alternative,
    group1_name: extra.group1Name,
    group2_name: extra.group2Name,
    value_metric: extra.valueMetric,
  };
}

export interface CorrelationRow {
  subjectId: string;
  simulationName: string;
  effectSize: number;
  weight: number;
}

export function buildCorrelationConfig(
  shared: SharedStatsFields,
  rows: CorrelationRow[],
  extra: { correlationType: "pearson" | "spearman"; useWeights: boolean; effectMetric: string; fieldMetric: string },
): CorrelationConfig {
  return {
    ...sharedConfig(shared),
    subjects: rows.map((r) => ({ subject_id: r.subjectId, simulation_name: r.simulationName, effect_size: r.effectSize, weight: r.weight })),
    correlation_type: extra.correlationType,
    use_weights: extra.useWeights,
    effect_metric: extra.effectMetric,
    field_metric: extra.fieldMetric,
  };
}

#!/usr/bin/env simnibs_python

import tit
tit.init()

from tit.stats import run_group_comparison, GroupComparisonConfig

PROJECT_DIR = "/mnt/000/"

subjects = GroupComparisonConfig.load_subjects("path/to/subjects.csv")

config = GroupComparisonConfig(
    project_dir=PROJECT_DIR,
    analysis_name="from_csv",
    subjects=subjects,
    test_type=GroupComparisonConfig.TestType.UNPAIRED,
    alternative=GroupComparisonConfig.Alternative.TWO_SIDED,
    cluster_stat=GroupComparisonConfig.ClusterStat.MASS,
    n_permutations=1000,
    tissue_type=GroupComparisonConfig.TissueType.GREY,
)
result = run_group_comparison(config)

print(f"Significant clusters: {result.n_significant_clusters}")
print(f"Significant voxels:   {result.n_significant_voxels}")
print(f"Output:               {result.output_dir}")


# ── Correlation analysis ─────────────────────────────────────────────────

# from tit.stats import run_correlation, CorrelationConfig
#
# config = CorrelationConfig(
#     project_dir=PROJECT_DIR,
#     analysis_name="efield_vs_improvement",
#     subjects=[
#         CorrelationConfig.Subject("070", "ICP_RHIPPO", effect_size=0.45, weight=25),
#         CorrelationConfig.Subject("071", "ICP_RHIPPO", effect_size=0.32, weight=30),
#         CorrelationConfig.Subject("072", "ICP_RHIPPO", effect_size=0.55, weight=28),
#         CorrelationConfig.Subject("073", "ICP_RHIPPO", effect_size=0.18, weight=22),
#         CorrelationConfig.Subject("074", "ICP_RHIPPO", effect_size=0.41, weight=35),
#     ],
#     correlation_type=CorrelationConfig.CorrelationType.PEARSON,
#     cluster_stat=CorrelationConfig.ClusterStat.MASS,
#     n_permutations=1000,
#     effect_metric="Behavioral Improvement",
# )
# result = run_correlation(config)

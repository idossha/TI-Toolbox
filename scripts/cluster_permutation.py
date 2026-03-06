#!/usr/bin/env simnibs_python

from tit.stats import (
    run_group_comparison,
    run_correlation,
    GroupComparisonConfig,
    CorrelationConfig,
    CorrelationSubject,
    GroupSubject,
    TestType,
    Alternative,
    ClusterStat,
    TissueType,
    CorrelationType,
    load_group_subjects,
)

PROJECT_DIR = "/mnt/000/"

# ── Group comparison ─────────────────────────────────────────────────────
# ── Load subjects from CSV instead ──────────────────────────────────────

subjects = load_group_subjects("path/to/subjects.csv")
config = GroupComparisonConfig(
    project_dir=PROJECT_DIR,
    analysis_name="from_csv",
    subjects=subjects,
    test_type=TestType.UNPAIRED,
    alternative=Alternative.TWO_SIDED,
    cluster_stat=ClusterStat.MASS,
    n_permutations=1000,
    tissue_type=TissueType.GREY,
)
result = run_group_comparison(config)

print(f"Significant clusters: {result.n_significant_clusters}")
print(f"Significant voxels:   {result.n_significant_voxels}")
print(f"Output:               {result.output_dir}")



# ── Correlation analysis ─────────────────────────────────────────────────

# corr_config = CorrelationConfig(
#     project_dir=PROJECT_DIR,
#     analysis_name="efield_vs_improvement",
#     subjects=[
#         CorrelationSubject("070", "ICP_RHIPPO", effect_size=0.45, weight=25),
#         CorrelationSubject("071", "ICP_RHIPPO", effect_size=0.32, weight=30),
#         CorrelationSubject("072", "ICP_RHIPPO", effect_size=0.55, weight=28),
#         CorrelationSubject("073", "ICP_RHIPPO", effect_size=0.18, weight=22),
#         CorrelationSubject("074", "ICP_RHIPPO", effect_size=0.41, weight=35),
#     ],
#     correlation_type=CorrelationType.PEARSON,
#     cluster_stat=ClusterStat.MASS,
#     n_permutations=1000,
#     effect_metric="Behavioral Improvement",
# )
# result = run_correlation(corr_config)

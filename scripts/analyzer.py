#!/usr/bin/env simnibs_python

from tit.analyzer import (
    Analyzer,
    AnalysisResult,
    run_group_analysis,
)

PROJECT_DIR = "/mnt/000/"
SUBJECT_ID = "101"

# -- Single-subject spherical analysis ----------------------------------------

analyzer = Analyzer(
    subject_id=SUBJECT_ID,
    simulation="L_Insula",
    space="voxel",
)

result = analyzer.analyze_sphere(
    center=(0.0, 0.0, 0.0),
    radius=10.0,
    coordinate_space="MNI",
    visualize=True,
)

# -- Single-subject cortical analysis -----------------------------------------

# result = analyzer.analyze_cortex(
#     atlas="DK40",
#     region="superiorfrontal",
#     visualize=True,
# )

# -- Group analysis ------------------------------------------------------------

# group_result = run_group_analysis(
#     subject_ids=["101", "102", "103"],
#     simulation="L_Insula",
#     space="mesh",
#     analysis_type="spherical",
#     center=(0.0, 0.0, 0.0),
#     radius=10.0,
#     coordinate_space="MNI",
#     visualize=True,
# )

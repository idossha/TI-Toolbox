"""Entry point: simnibs_python -m tit.stats config.json"""

import json
import sys

from tit.stats.config import (
    CorrelationConfig,
    GroupComparisonConfig,
)


def _build_group_subjects(raw: list[dict]) -> list[GroupComparisonConfig.Subject]:
    return [GroupComparisonConfig.Subject(**s) for s in raw]


def _build_correlation_subjects(raw: list[dict]) -> list[CorrelationConfig.Subject]:
    return [CorrelationConfig.Subject(**s) for s in raw]


def main() -> None:
    """Run statistical analysis from a JSON config passed as the first CLI argument."""
    from tit.logger import add_stream_handler, setup_logging

    setup_logging("INFO")
    add_stream_handler("tit.stats")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    mode = data.pop("mode", "group_comparison")

    if mode == "correlation":
        _run_correlation(data)
    else:
        _run_group_comparison(data)


def _run_group_comparison(data: dict) -> None:
    from tit.stats.permutation import run_group_comparison

    subjects = _build_group_subjects(data.pop("subjects"))
    config = GroupComparisonConfig(
        analysis_name=data["analysis_name"],
        subjects=subjects,
        test_type=GroupComparisonConfig.TestType(data.get("test_type", "unpaired")),
        alternative=GroupComparisonConfig.Alternative(
            data.get("alternative", "two-sided")
        ),
        cluster_stat=GroupComparisonConfig.ClusterStat(
            data.get("cluster_stat", "mass")
        ),
        n_permutations=data.get("n_permutations", 1000),
        tissue_type=GroupComparisonConfig.TissueType(data.get("tissue_type", "grey")),
    )
    result = run_group_comparison(config)
    sys.exit(0 if result.n_significant_clusters >= 0 else 1)


def _run_correlation(data: dict) -> None:
    from tit.stats.permutation import run_correlation

    subjects = _build_correlation_subjects(data.pop("subjects"))
    config = CorrelationConfig(
        analysis_name=data["analysis_name"],
        subjects=subjects,
        correlation_type=CorrelationConfig.CorrelationType(
            data.get("correlation_type", "pearson")
        ),
        cluster_stat=CorrelationConfig.ClusterStat(data.get("cluster_stat", "mass")),
        n_permutations=data.get("n_permutations", 1000),
        effect_metric=data.get("effect_metric", ""),
    )
    result = run_correlation(config)
    sys.exit(0 if result.n_significant_clusters >= 0 else 1)


if __name__ == "__main__":
    main()

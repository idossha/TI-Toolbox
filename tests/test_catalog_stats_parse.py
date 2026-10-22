"""The Results pane reads every stats run's key numbers: size-stat thresholds and surface runs.

What this pins (2026-10-22)
    ``catalog._parse_stats_log`` matched the threshold line with ``(\\w+) units``, which only
    the mass statistic logs (``... 812.40 mass units``); a size-statistic run logs
    ``... 12.00 voxels`` and lost its "Cluster threshold" tile. A surface (fsaverage) run logs
    none of the lines the parser reads, so its pane had no settings, no groups and no outcome;
    it does write a machine-readable sidecar (``surface_stats.json``, via
    ``tit.source.fsaverage.write_fsaverage_msh``) and ``significant_clusters.csv``, which the
    catalog now reads for such a run.

Where the expectations come from
    The writers, run for real on the host with real scipy (``real_scipy`` fixture): the volume
    engine (``PermutationEngine.correct_groups``) logging through the stats runner's own file
    logger (``tit.stats.permutation._setup_logger``, ``tit.logger.LOG_FORMAT``), and the
    surface runner ``run_surface_group_comparison`` / ``run_surface_correlation`` on a chain
    adjacency with its data loader stubbed. Expected values are what those calls *return*
    (the engine's threshold, formatted as the engine formats it, ``%.2f``; the runner's
    ``n_significant_clusters`` / ``n_significant_voxels``) and the config the test passed in --
    never the parser's own output.

Run: .venv/bin/python -m pytest tests/test_catalog_stats_parse.py -q -p no:cacheprovider
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pytest

from tit import catalog
from tit.paths import get_path_manager

pytestmark = pytest.mark.usefixtures("real_scipy")


def _volume_fixture(seed: int = 7):
    """6 responders vs 6 non-responders on a 6x6x6 grid, +1.0 in a 3x3x3 block."""
    rng = np.random.default_rng(seed)
    shape = (6, 6, 6)
    resp = 1.0 + 0.05 * rng.standard_normal((*shape, 6))
    non = 1.0 + 0.05 * rng.standard_normal((*shape, 6))
    resp[1:4, 1:4, 1:4, :] += 1.0
    return resp, non


def _detach(logger: logging.Logger, before: list) -> None:
    for handler in logger.handlers[:]:
        if handler not in before:
            handler.close()
            logger.removeHandler(handler)


def _volume_run(project: Path, name: str, cluster_stat: str):
    """One volume group comparison, logged exactly as a stats run logs it."""
    from tit.stats import engine, permutation

    get_path_manager(str(project))
    run_dir = permutation._resolve_output_dir("group_comparison", name)
    log = logging.getLogger("tit.stats.group_comparison")
    before = list(log.handlers)
    try:
        log, log_file = permutation._setup_logger(run_dir, "group_comparison")
        resp, non = _volume_fixture()
        p, t, valid = engine.ttest_voxelwise(resp, non, log=log)
        out = engine.PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=40,
            alpha=0.05,
            cluster_stat=cluster_stat,
            n_jobs=1,
            log=log,
        ).correct_groups(resp, non, p_values=p, t_statistics=t, valid_mask=valid)
    finally:
        _detach(log, before)
    return run_dir, Path(log_file).read_text(), out


def _results(parsed: dict) -> dict:
    return {r["label"]: r["value"] for r in parsed["results"]}


@pytest.mark.parametrize("cluster_stat", ["size", "mass"])
def test_the_cluster_threshold_is_read_for_both_statistics(
    tmp_path: Path, cluster_stat: str
) -> None:
    _run_dir, text, out = _volume_run(tmp_path, f"vol_{cluster_stat}", cluster_stat)
    sig_mask, threshold, sig_clusters = out[0], out[1], out[2]
    results = _results(catalog._parse_stats_log(text))
    assert results["Cluster threshold"] == f"{threshold:.2f}"
    # The same parse also reads the outcome the engine returned.
    assert results["Significant clusters"] == str(len(sig_clusters))
    assert results["Significant voxels"] == str(int(np.sum(sig_mask)))


def test_group_stats_detail_shows_the_size_threshold(tmp_path: Path) -> None:
    _run_dir, _text, out = _volume_run(tmp_path, "vol_size", "size")
    pm = get_path_manager(str(tmp_path))
    detail = catalog.group_stats_detail(pm, "group_comparison", "vol_size")
    assert _results(detail)["Cluster threshold"] == f"{out[1]:.2f}"


# -- surface ------------------------------------------------------------------------------------

N_NODES = 120
PLANTED = slice(40, 71)  # 31 neighbouring vertices on the chain


def _chain(n: int) -> np.ndarray:
    """Vertex i touches i-1 and i+1. Dense on purpose: ``connected_components`` accepts it, and
    a ``scipy.sparse`` matrix built here can fail its sparse-class check when another module
    imported scipy before the ``real_scipy`` fixture re-imported it (full-suite order).
    """
    return np.eye(n, k=1) + np.eye(n, k=-1)


@pytest.fixture()
def surface(monkeypatch):
    """``tit.stats.surface`` bound to the real-scipy engine kernels for this test only."""
    from tit.stats import engine, surface

    for name in (
        "correlation",
        "pval_from_histogram",
        "tail_from_alternative",
        "tail_statistic",
        "ttest_ind",
        "ttest_rel",
    ):
        monkeypatch.setattr(surface, name, getattr(engine, name))
    monkeypatch.setattr(
        surface, "build_fsaverage_adjacency", lambda _s: _chain(N_NODES)
    )
    return surface


def _surface_data(
    n_subjects: int, planted_cols: list[int], seed: int = 3
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    data = 1.0 + 0.05 * rng.standard_normal((N_NODES, n_subjects))
    for col in planted_cols:
        data[PLANTED, col] += 1.0
    return data


def _detail(project: Path, analysis_type: str, name: str) -> dict:
    return catalog.group_stats_detail(
        get_path_manager(str(project)), analysis_type, name
    )


def test_a_surface_group_comparison_shows_settings_groups_and_outcome(
    tmp_path: Path, surface, monkeypatch
) -> None:
    from tit.stats.config import GroupComparisonConfig

    get_path_manager(str(tmp_path))
    subjects = [GroupComparisonConfig.Subject(f"r{i}", "M1", 1) for i in range(6)] + [
        GroupComparisonConfig.Subject(f"n{i}", "M1", 0) for i in range(6)
    ]
    config = GroupComparisonConfig(
        analysis_name="surf_gc",
        subjects=subjects,
        space=GroupComparisonConfig.AnalysisSpace.FSAVERAGE,
        n_permutations=60,
        cluster_stat=GroupComparisonConfig.ClusterStat.MASS,
    )
    ids = [s.subject_id for s in subjects]
    monkeypatch.setattr(
        surface,
        "load_group_surface_data",
        lambda pairs, field, spacing: (_surface_data(12, list(range(6))), ids),
    )
    log = logging.getLogger("tit.stats.group_comparison")
    before = list(log.handlers)
    try:
        result = surface.run_surface_group_comparison(config)
    finally:
        _detach(log, before)

    detail = _detail(tmp_path, "group_comparison", "surf_gc")
    config_rows = {c["label"]: c["value"] for c in detail["config"]}
    assert config_rows["Test"] == config.test_type.value
    assert config_rows["Alternative"] == config.alternative.value
    assert config_rows["Cluster statistic"] == config.cluster_stat.value
    assert config_rows["Permutations"] == str(config.n_permutations)
    assert config_rows["Cluster-forming p"] == f"{config.cluster_threshold:.3f}"
    assert config_rows["Cluster alpha"] == f"{config.alpha:.3f}"
    assert detail["groups"] == [
        {"name": config.group1_name, "n": 6, "subjects": ids[:6]},
        {"name": config.group2_name, "n": 6, "subjects": ids[6:]},
    ]
    results = _results(detail)
    assert results["Significant clusters"] == str(result.n_significant_clusters)
    assert results["Significant vertices"] == str(result.n_significant_voxels)
    # The planted 31-vertex block is found: the numbers above are not vacuous zeros.
    assert result.n_significant_clusters >= 1
    assert detail["clusters"]["rows"], "significant_clusters.csv is the cluster table"


def test_a_surface_correlation_shows_settings_subjects_and_outcome(
    tmp_path: Path, surface, monkeypatch
) -> None:
    from tit.stats.config import CorrelationConfig

    get_path_manager(str(tmp_path))
    effects = [0.1, 0.4, 0.9, 1.6, 2.5, 3.6, 4.9, 6.4]
    subjects = [
        CorrelationConfig.Subject(f"s{i}", "M1", e) for i, e in enumerate(effects)
    ]
    config = CorrelationConfig(
        analysis_name="surf_corr",
        subjects=subjects,
        space=CorrelationConfig.AnalysisSpace.FSAVERAGE,
        n_permutations=60,
    )
    ids = [s.subject_id for s in subjects]
    data = _surface_data(len(effects), [])
    data[PLANTED, :] += np.asarray(effects)[None, :]  # field rises with the response
    monkeypatch.setattr(
        surface, "load_group_surface_data", lambda pairs, field, spacing: (data, ids)
    )
    log = logging.getLogger("tit.stats.correlation")
    before = list(log.handlers)
    try:
        result = surface.run_surface_correlation(config)
    finally:
        _detach(log, before)

    detail = _detail(tmp_path, "correlation", "surf_corr")
    config_rows = {c["label"]: c["value"] for c in detail["config"]}
    assert config_rows["Correlation"] == config.correlation_type.value
    assert config_rows["Permutations"] == str(config.n_permutations)
    assert config_rows["Cluster statistic"] == config.cluster_stat.value
    assert detail["groups"] == [{"name": "Subjects", "n": len(ids), "subjects": ids}]
    results = _results(detail)
    assert results["Significant clusters"] == str(result.n_significant_clusters)
    assert results["Significant vertices"] == str(result.n_significant_voxels)

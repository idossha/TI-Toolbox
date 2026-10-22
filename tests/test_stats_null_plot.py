"""The null-distribution figure draws the test that ran (p16, 2026-10-22).

Pins:

* observed clusters sit at their *oriented* statistic -- the scale the null is built on
  (``|mass|`` two-sided, ``-mass`` for ``"less"``, ``mass`` for ``"greater"``, size as is) -- so a
  significant negative cluster lands to the right of the null, not at ``x < 0``;
* a cluster is drawn significant when ``p < alpha`` for the configured alpha, and the legend
  says that alpha (v3.1.x hard-coded 0.05: alpha 0.01 with p 0.03 was drawn green);
* with no candidate cluster (empty null) no figure is written, and the summary says why.

Expected x positions are the hand-oriented masses of the fixtures below (the orientation rule
as stated in Maris & Oostenveld 2007 / MNE ``tail``), not values read from the code under test.

Run: ``.venv/bin/python -m pytest tests/test_stats_null_plot.py -q -p no:cacheprovider``.
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from tests.stats_real_scipy import real_scipy  # noqa: F401  (fixture)

# One negative and one positive cluster: (size, signed mass, p).
OBSERVED = [
    {"id": 1, "size": 50, "stat_value": -120.0, "p_value": 0.004},
    {"id": 2, "size": 30, "stat_value": 80.0, "p_value": 0.03},
]


def _series(**kw):
    from tit.plotting.stats import null_plot_series

    args = {"threshold": 100.0, "alpha": 0.05, "cluster_stat": "mass"}
    args.update(kw)
    return null_plot_series(np.array([5.0, 40.0, 100.0]), OBSERVED, **args)


@pytest.mark.parametrize(
    "alternative, expected_x",
    [
        ("two-sided", [120.0, 80.0]),  # |mass|
        ("less", [120.0, -80.0]),  # -mass
        ("greater", [-120.0, 80.0]),  # mass
    ],
)
def test_observed_mass_is_drawn_on_the_null_scale(alternative, expected_x):
    series = _series(alternative=alternative)
    np.testing.assert_array_equal(series["observed_x"], expected_x)


def test_negative_significant_cluster_sits_right_of_the_null():
    series = _series(alternative="two-sided")
    assert series["significant"][0]
    assert series["observed_x"][0] > series["null"].max()


def test_size_statistic_is_drawn_at_the_cluster_size():
    series = _series(cluster_stat="size")
    np.testing.assert_array_equal(series["observed_x"], [50.0, 30.0])
    assert series["x_label"] == "Maximum Cluster Size (voxels)"


@pytest.mark.parametrize(
    "alpha, expected",
    [(0.05, [True, True]), (0.01, [True, False]), (0.001, [False, False])],
)
def test_significance_uses_the_configured_alpha(alpha, expected):
    np.testing.assert_array_equal(_series(alpha=alpha)["significant"], expected)


def test_without_p_values_significance_is_oriented_stat_above_threshold():
    from tit.plotting.stats import null_plot_series

    observed = [{"stat_value": -150.0}, {"stat_value": 90.0}]
    series = null_plot_series(
        np.zeros(3), observed, threshold=100.0, alpha=0.05, cluster_stat="mass"
    )
    np.testing.assert_array_equal(series["significant"], [True, False])


def test_figure_lines_and_legend_follow_alpha(monkeypatch, tmp_path):
    """What ``plot_permutation_null_distribution`` hands to matplotlib."""
    import matplotlib.pyplot as plt

    from tit.plotting.stats import plot_permutation_null_distribution

    fig, ax = MagicMock(), MagicMock()
    monkeypatch.setattr(plt, "subplots", MagicMock(return_value=(fig, ax)))
    monkeypatch.setitem(sys.modules, "seaborn", MagicMock())

    plot_permutation_null_distribution(
        np.array([5.0, 40.0, 100.0]),
        100.0,
        OBSERVED,
        str(tmp_path / "null.pdf"),
        alpha=0.01,
        cluster_stat="mass",
        alternative="two-sided",
    )

    threshold_call, *cluster_calls = ax.axvline.call_args_list
    assert threshold_call.args[0] == 100.0
    assert "p<0.01" in threshold_call.kwargs["label"]
    drawn = [(c.args[0], c.kwargs["color"], c.kwargs["label"]) for c in cluster_calls]
    assert drawn == [
        (120.0, "green", "Significant Clusters (p<0.01)"),
        (80.0, "orange", "Non-significant Clusters (p≥0.01)"),
    ]


def _group_run(
    monkeypatch, groups, threshold, plots, alpha=0.05, alternative="two-sided"
):
    import tit.stats.permutation as perm
    from tit.stats.config import GroupComparisonConfig

    template = SimpleNamespace(affine=np.eye(4), header=None)
    resp, non = groups
    monkeypatch.setattr(
        perm,
        "load_group_data_ti_toolbox",
        lambda dicts, **_: (
            resp if dicts[0]["subject_id"].startswith("r") else non,
            template,
            [d["subject_id"] for d in dicts],
        ),
    )
    monkeypatch.setattr(perm, "_save_nifti", lambda *a, **k: None)
    monkeypatch.setattr(
        perm, "plot_permutation_null_distribution", lambda *a, **k: plots.append((a, k))
    )
    monkeypatch.setattr(
        perm, "plot_cluster_size_mass_correlation", lambda *a, **k: None
    )
    subjects = [GroupComparisonConfig.Subject(f"r{i}", "T", 1) for i in range(3)] + [
        GroupComparisonConfig.Subject(f"n{i}", "T", 0) for i in range(3)
    ]
    cfg = GroupComparisonConfig(
        analysis_name="nullplot",
        subjects=subjects,
        n_permutations=10,
        n_jobs=1,
        cluster_threshold=threshold,
        alpha=alpha,
        alternative=alternative,
    )
    return perm.run_group_comparison(cfg)


def _groups(effect):
    rng = np.random.default_rng(4)
    resp = (rng.random((6, 6, 6, 3)) + 1.0).astype(np.float32)
    non = (rng.random((6, 6, 6, 3)) + 1.0).astype(np.float32)
    if effect:
        non[1:4, 1:4, 1:4] += 5.0  # responders < non-responders: a negative cluster
    return resp, non


def test_empty_null_writes_no_figure_and_says_why(real_scipy, init_pm, monkeypatch):
    plots = []
    result = _group_run(monkeypatch, _groups(effect=False), 1e-12, plots)

    assert plots == []
    with open(f"{result.output_dir}/analysis_summary.txt") as fh:
        summary = fh.read()
    assert "no candidate clusters; threshold not computed" in summary
    assert "Null-distribution figure: not drawn" in summary
    with open(result.log_file) as fh:
        assert "No null-distribution figure: no candidate clusters" in fh.read()


def test_runner_passes_alpha_and_alternative_to_the_figure(
    real_scipy, init_pm, monkeypatch
):
    plots = []
    _group_run(
        monkeypatch, _groups(effect=True), 0.01, plots, alpha=0.01, alternative="less"
    )

    ((args, kwargs),) = plots
    null, _, observed, path = args
    assert len(null) == 10
    assert path.endswith("permutation_null_distribution.pdf")
    assert kwargs["alpha"] == 0.01
    assert kwargs["alternative"] == "less"
    # The planted cluster is negative; under "less" the figure orients it to a positive x.
    from tit.plotting.stats import null_plot_series

    negative = [o for o in observed if o["stat_value"] < 0]
    assert negative
    series = null_plot_series(
        null,
        negative,
        threshold=0.0,
        alpha=0.01,
        cluster_stat="mass",
        alternative="less",
    )
    np.testing.assert_array_equal(
        series["observed_x"], [-o["stat_value"] for o in negative]
    )

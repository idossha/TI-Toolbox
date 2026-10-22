"""The group summary lists the engine's significant clusters, with their mass and p (p16).

Pins (2026-10-22): ``run_group_comparison``'s ``result.clusters``, ``n_significant_clusters`` and
the "Number of Clusters" / "TOP 10 CLUSTERS" section of ``analysis_summary.txt`` all describe the
same sign-separated clusters the permutation engine tested. v3.1.x re-labelled the union of the
significant voxels without regard to sign, so two touching clusters of opposite sign became one
summary entry ("Number of Clusters: 1" beside ``n_significant_clusters == 2``), never printed
the mass or p-value, and sorted by size under a "by statistic" header. A run with no candidate
cluster printed "Cluster mass threshold: 0.00" as if a permutation null had been computed, and
its ``result.cluster_threshold`` was 0.0 -- the same number a computed null of zeros gives; it is
now NaN.

Fixture: 3 responders vs 3 non-responders, two touching 4x4x4 blocks (x 2..5 responders > non,
x 6..9 responders < non) on a background identical across all subjects (excluded as
degenerate, so it can never form a cluster). The permutation null is replaced by zeros, so
each cluster's p is exactly ``1 / (n_permutations + 1)`` (Phipson & Smyth). Expected masses are
per-voxel ``scipy.stats.ttest_ind`` t summed over each block; expected MNI centres are the
affine applied by hand to the block centroids.

Run: ``.venv/bin/python -m pytest tests/test_stats_cluster_bookkeeping.py -q -p no:cacheprovider``.
"""

import math
import re
from types import SimpleNamespace

import numpy as np
import pytest

from tests.stats_real_scipy import real_scipy  # noqa: F401  (fixture)

N_PERM = 24
POS = (slice(2, 6), slice(3, 7), slice(3, 7))  # responders > non-responders
NEG = (
    slice(6, 10),
    slice(3, 7),
    slice(3, 7),
)  # responders < non-responders, touches POS
# Oblique, translated affine: a transposed or translation-free centre would not match.
AFFINE = np.array(
    [
        [2.0, 0.25, 0.0, -90.0],
        [0.0, 2.0, 0.5, -126.0],
        [0.1, 0.0, 2.0, -72.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)


def _groups():
    rng = np.random.default_rng(5)
    resp = np.ones((12, 12, 12, 3), dtype=np.float32)
    non = np.ones((12, 12, 12, 3), dtype=np.float32)
    resp[POS] = 5.0 + rng.random((4, 4, 4, 3)) * 0.01
    non[POS] = 1.0 + rng.random((4, 4, 4, 3)) * 0.01
    resp[NEG] = 1.0 + rng.random((4, 4, 4, 3)) * 0.01
    non[NEG] = 6.0 + rng.random((4, 4, 4, 3)) * 0.01
    return resp, non


def _patch_runner(monkeypatch, groups, plots):
    import tit.stats.engine as engine
    import tit.stats.permutation as perm

    template = SimpleNamespace(affine=AFFINE, header=None)
    resp, non = groups

    def fake_load(dicts, **_):
        ids = [d["subject_id"] for d in dicts]
        return (resp if ids[0].startswith("r") else non), template, ids

    def zero_null(
        test_data, test_coords, n_resp, n_total, *a, return_indices=False, **k
    ):
        if return_indices:
            return 0.0, np.arange(n_total), 0, 0.0
        return 0.0, 0, 0.0

    monkeypatch.setattr(perm, "load_group_data_ti_toolbox", fake_load)
    monkeypatch.setattr(engine, "_run_single_permutation", zero_null)
    monkeypatch.setattr(perm, "_save_nifti", lambda *a, **k: None)
    monkeypatch.setattr(
        perm,
        "plot_permutation_null_distribution",
        lambda *a, **k: plots.append((a, k)),
    )
    monkeypatch.setattr(
        perm, "plot_cluster_size_mass_correlation", lambda *a, **k: None
    )
    return perm


def _config(**kw):
    from tit.stats.config import GroupComparisonConfig

    subjects = [GroupComparisonConfig.Subject(f"r{i}", "T", 1) for i in range(3)] + [
        GroupComparisonConfig.Subject(f"n{i}", "T", 0) for i in range(3)
    ]
    return GroupComparisonConfig(
        analysis_name=kw.pop("analysis_name", "touch"),
        subjects=subjects,
        n_permutations=N_PERM,
        n_jobs=1,
        **kw,
    )


@pytest.fixture
def touching_run(real_scipy, init_pm, monkeypatch):
    groups = _groups()
    perm = _patch_runner(monkeypatch, groups, [])
    result = perm.run_group_comparison(_config(cluster_threshold=0.01))
    with open(f"{result.output_dir}/analysis_summary.txt") as fh:
        summary = fh.read()

    resp, non = groups

    def block_mass(block):
        a, b = resp[block].astype(np.float64), non[block].astype(np.float64)
        return float(real_scipy.ttest_ind(a, b, axis=-1).statistic.sum())

    expected = {
        "pos": {"mass": block_mass(POS), "centroid": np.array([3.5, 4.5, 4.5])},
        "neg": {"mass": block_mass(NEG), "centroid": np.array([7.5, 4.5, 4.5])},
    }
    return result, summary, expected


def _cluster_lines(summary):
    lines = summary.splitlines()
    head = next(i for i, line in enumerate(lines) if line.startswith("TOP 10 CLUSTERS"))
    body = [line for line in lines[head + 2 :] if line[:1].isdigit()]
    return lines[head], body


def test_counts_agree_between_result_engine_and_summary(touching_run):
    result, summary, _ = touching_run

    assert result.n_significant_clusters == 2
    assert len(result.clusters) == 2
    assert "Number of Clusters: 2" in summary.splitlines()
    _, body = _cluster_lines(summary)
    assert len(body) == 2
    assert result.n_significant_voxels == 128
    # A permutation null of zeros puts every quantile of it at 0: a computed threshold of 0,
    # which the result must keep apart from "no permutation ran" (NaN, below).
    assert result.cluster_threshold == 0.0


def test_each_cluster_carries_its_signed_mass_and_p(touching_run):
    result, summary, expected = touching_run
    p = 1.0 / (N_PERM + 1)

    masses = sorted(c["stat_value"] for c in result.clusters)
    assert masses == pytest.approx(
        sorted([expected["pos"]["mass"], expected["neg"]["mass"]]), rel=1e-5
    )
    assert expected["neg"]["mass"] < 0 < expected["pos"]["mass"]
    assert [c["p_value"] for c in result.clusters] == pytest.approx([p, p])
    assert all(c["size"] == 64 for c in result.clusters)

    header, body = _cluster_lines(summary)
    assert header == "TOP 10 CLUSTERS (by |cluster mass|, largest first):"
    # Ordered by |mass|, largest first, exactly as the header says.
    # The engine tests float32 voxel data and the reference float64, and the line rounds to
    # 2 decimals: rel 1e-6 absorbs the first, abs 0.006 the second.
    order = sorted(expected.values(), key=lambda e: -abs(e["mass"]))
    for line, exp in zip(body, order):
        m = re.fullmatch(r"\d+\. Cluster \d+: 64 voxels, mass = (\S+), p = (\S+)", line)
        assert m, line
        assert float(m.group(1)) == pytest.approx(exp["mass"], rel=1e-6, abs=0.006)
        assert m.group(2) == f"{p:.4f}"


def test_result_clusters_are_ordered_most_extreme_first(touching_run):
    result, _, expected = touching_run

    # |mass| of the 1-vs-6 block exceeds that of the 5-vs-1 block, though the engine labels
    # the positive block first.
    assert abs(expected["neg"]["mass"]) > abs(expected["pos"]["mass"])
    assert [np.sign(c["stat_value"]) for c in result.clusters] == [-1.0, 1.0]


def test_summary_orders_clusters_it_is_given_by_magnitude(tmp_path):
    """``generate_summary`` keeps its header true whatever order the caller passes."""
    from tit.stats.reporting import generate_summary

    clusters = [
        {
            "cluster_id": 1,
            "size": 9,
            "stat_value": 12.0,
            "p_value": 0.04,
            "center_mni": [0, 0, 0],
        },
        {
            "cluster_id": 2,
            "size": 3,
            "stat_value": -30.0,
            "p_value": 0.01,
            "center_mni": [0, 0, 0],
        },
        {
            "cluster_id": 3,
            "size": 5,
            "stat_value": 20.0,
            "p_value": 0.02,
            "center_mni": [0, 0, 0],
        },
    ]
    group = np.ones((2, 2, 2, 2))
    out = tmp_path / "summary.txt"
    generate_summary(
        _config(), group, group, np.zeros((2, 2, 2)), 7.0, clusters, {}, out
    )

    _, body = _cluster_lines(out.read_text())
    assert [line.split(":")[0] for line in body] == [
        "1. Cluster 2",
        "2. Cluster 3",
        "3. Cluster 1",
    ]


def test_centres_are_the_affine_applied_to_each_block_centroid(touching_run):
    result, _, expected = touching_run

    got = sorted((tuple(np.round(c["center_mni"], 9)) for c in result.clusters))
    want = sorted(
        tuple(np.round(AFFINE @ np.append(e["centroid"], 1.0), 9)[:3])
        for e in expected.values()
    )
    assert got == want


def test_no_candidate_cluster_says_threshold_was_not_computed(
    real_scipy, init_pm, monkeypatch
):
    rng = np.random.default_rng(9)
    resp = (rng.random((6, 6, 6, 3)) + 1.0).astype(np.float32)
    non = (rng.random((6, 6, 6, 3)) + 1.0).astype(np.float32)
    plots = []
    perm = _patch_runner(monkeypatch, (resp, non), plots)

    result = perm.run_group_comparison(
        _config(analysis_name="none", cluster_threshold=1e-12)
    )
    with open(f"{result.output_dir}/analysis_summary.txt") as fh:
        lines = fh.read().splitlines()

    assert result.n_significant_clusters == 0
    # The result object says what the summary says: no threshold was computed.
    assert math.isnan(result.cluster_threshold)
    assert (
        "Cluster mass threshold: no candidate clusters; threshold not computed" in lines
    )
    assert not any(line.startswith("Cluster mass threshold: 0") for line in lines)
    assert "Number of Clusters: 0" in lines

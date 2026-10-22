"""A cluster's peak r is its most extreme signed r; the summary states the two-sided test (p16).

Pins (2026-10-22):

* ``peak_r`` of a significant cluster is the ``r`` of largest magnitude with its sign, in the
  volume engine and the fsaverage path. v3.1.x took ``max(r)``, which for a negative-correlation
  cluster is its value closest to zero (planted r ~ -1 block: mean -0.995, peak -0.813).
* ``analysis_summary.txt`` names the alternative the permutation engine ran with
  (``tit.stats.permutation`` passes ``"two-sided"``) and no longer says the analysis "tests
  positive correlations only"; its "Peak r" line follows the same largest-|r| rule.
* ``generate_correlation_summary`` called directly: its interpretation note matches the
  alternative it is given (two-sided, or one-sided "greater" -> positive, "less" -> negative);
  its cluster list is ordered by |mass| under the header that says so, each entry with its
  signed mass, p, Mean r and Peak r; its Min r / Max r cover the significant voxels only.

Expected r values come from ``np.corrcoef`` per voxel on the fixture -- an independent Pearson
implementation -- never from ``tit.stats.engine.correlation``. Fixture: 6 subjects, effects
1..6, a 4x4x4 block whose field is ``10 - effect`` plus uniform noise of width 1 (r between
about -0.9 and -1, spread enough that the largest and the smallest |r| differ at the 4 decimals
the summary prints) on a
background that is identical across subjects (r = 0, never supra-threshold), so the block is
the only possible cluster.

Run: ``.venv/bin/python -m pytest tests/test_stats_cluster_sign.py -q -p no:cacheprovider``.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from tests.stats_real_scipy import (  # noqa: F401  (fixtures)
    chain_adjacency,
    graph_components,
    real_scipy,
    seeded_permutations,
)

EFFECTS = np.arange(1.0, 7.0)
BLOCK = (slice(3, 7), slice(3, 7), slice(3, 7))


def _negative_block_fixture():
    rng = np.random.default_rng(11)
    data = np.ones((10, 10, 10, EFFECTS.size), dtype=np.float32)
    for k, e in enumerate(EFFECTS):
        data[BLOCK + (k,)] = 10.0 - e + rng.random((4, 4, 4))
    return data


def _corrcoef_per_voxel(data, effects, region):
    block = data[region].reshape(-1, effects.size).astype(np.float64)
    return np.array([np.corrcoef(v, effects)[0, 1] for v in block])


@pytest.fixture
def negative_run(real_scipy, seeded_permutations, init_pm, monkeypatch):
    import tit.stats.permutation as perm
    from tit.stats.config import CorrelationConfig

    data = _negative_block_fixture()
    template = SimpleNamespace(affine=np.eye(4), header=None)
    monkeypatch.setattr(
        perm,
        "load_group_data_ti_toolbox",
        lambda dicts, **_: (data, template, [d["subject_id"] for d in dicts]),
    )
    monkeypatch.setattr(perm, "_save_nifti", lambda *a, **k: None)
    monkeypatch.setattr(
        perm, "plot_permutation_null_distribution", lambda *a, **k: None
    )
    monkeypatch.setattr(
        perm, "plot_cluster_size_mass_correlation", lambda *a, **k: None
    )
    subjects = [
        CorrelationConfig.Subject(f"s{i}", "N", float(e))
        for i, e in enumerate(EFFECTS, 1)
    ]
    cfg = CorrelationConfig(
        analysis_name="neg",
        subjects=subjects,
        n_permutations=99,
        n_jobs=1,
        use_weights=False,
    )
    result = perm.run_correlation(cfg)
    with open(f"{result.output_dir}/analysis_summary.txt") as fh:
        summary = fh.read()
    return result, summary, _corrcoef_per_voxel(data, EFFECTS, BLOCK)


def test_negative_cluster_peak_is_its_most_negative_r(negative_run):
    result, _, r_block = negative_run
    expected_peak = r_block[np.argmax(np.abs(r_block))]

    assert result.n_significant_clusters == 1
    (cluster,) = result.clusters
    assert cluster["size"] == r_block.size == 64
    assert cluster["mean_r"] == pytest.approx(r_block.mean(), abs=1e-9)
    assert cluster["mean_r"] < -0.9
    assert cluster["peak_r"] == pytest.approx(expected_peak, abs=1e-9)
    # The peak of a negative cluster is at or below every other r in it.
    assert cluster["peak_r"] == pytest.approx(r_block.min(), abs=1e-9)
    assert cluster["peak_r"] <= cluster["mean_r"]


def test_engine_correction_reports_signed_peak(real_scipy, seeded_permutations):
    """``PermutationEngine.correct_correlation`` itself, without the runner around it."""
    from tit.stats.engine import PermutationEngine, correlation_voxelwise

    data = _negative_block_fixture()
    r, t, p, valid = correlation_voxelwise(data, EFFECTS)
    engine = PermutationEngine(cluster_threshold=0.05, n_permutations=99, n_jobs=1)
    _, _, sig_clusters, _, _, _ = engine.correct_correlation(
        data, EFFECTS, r_values=r, t_statistics=t, p_values=p, valid_mask=valid
    )
    r_block = _corrcoef_per_voxel(data, EFFECTS, BLOCK)

    (cluster,) = sig_clusters
    assert cluster["stat_value"] < 0  # signed mass of a negative-t cluster
    assert cluster["peak_r"] == pytest.approx(r_block.min(), abs=1e-9)
    assert cluster["mean_r"] == pytest.approx(r_block.mean(), abs=1e-9)


def test_summary_names_the_two_sided_test(negative_run):
    _, summary, _ = negative_run

    assert "positive correlations only" not in summary
    assert "Alternative hypothesis: two-sided" in summary.splitlines()


def test_summary_peak_r_lines_use_largest_magnitude(negative_run):
    _, summary, r_block = negative_run
    expected = f"{r_block[np.argmax(np.abs(r_block))]:.4f}"
    # The fixture can tell the rules apart at the printed precision.
    assert expected != f"{r_block.max():.4f}"
    lines = summary.splitlines()

    stats_at = lines.index("CORRELATION STATISTICS IN SIGNIFICANT VOXELS:")
    assert f"Peak r: {expected}" in lines[stats_at : stats_at + 6]
    assert f"   Peak r: {expected}" in lines
    assert f"   Mean r: {r_block.mean():.4f}" in lines


def test_surface_cluster_peaks_keep_their_sign(graph_components):
    """``_identify_surface_clusters`` on a hand-made 12-vertex chain.

    Vertices 2..5 form a negative cluster with r = (-0.6, -0.95, -0.8, -0.7); vertices 8..9 a
    positive one with r = (0.5, 0.9). A null of zeros makes both significant
    (p = 1/(m+1) = 1/100). Expected peaks are read off the r values by hand: -0.95 and 0.9.
    """
    from tit.stats.surface import _identify_surface_clusters

    n = 12
    r_full = np.zeros(n)
    r_full[2:6] = [-0.6, -0.95, -0.8, -0.7]
    r_full[8:10] = [0.5, 0.9]
    t_full = np.where(r_full != 0, np.sign(r_full) * 5.0, 0.0)
    p_full = np.where(r_full != 0, 1e-4, 1.0)

    _, sig_clusters, _ = _identify_surface_clusters(
        t_full,
        p_full,
        np.ones(n, dtype=bool),
        chain_adjacency(n),
        0.05,
        np.zeros(99),
        "mass",
        0.05,
        "two-sided",
        r_full=r_full,
    )

    by_vertices = {tuple(c["vertices"]): c for c in sig_clusters}
    assert set(by_vertices) == {(2, 3, 4, 5), (8, 9)}
    assert by_vertices[(2, 3, 4, 5)]["peak_r"] == pytest.approx(-0.95)
    assert by_vertices[(2, 3, 4, 5)]["mean_r"] == pytest.approx(-0.7625)
    assert by_vertices[(8, 9)]["peak_r"] == pytest.approx(0.9)


# ── generate_correlation_summary called directly ─────────────────────────────
# Eight voxels; the four in SIG_MASK carry r = (-0.83, -0.35, 0.48, 0.61). The two strongest r
# (-0.99, 0.95) sit OUTSIDE the mask, so a statistic taken over every voxel would be caught.
R_VALUES = np.array([-0.99, -0.83, -0.35, 0.0, 0.48, 0.61, 0.95, 0.1]).reshape(2, 2, 2)
SIG_MASK = np.array([0, 1, 1, 0, 1, 1, 0, 0]).reshape(2, 2, 2)
# Three significant clusters of mixed sign, passed in neither |mass| order nor its reverse.
# By |mass|: 3 (-40), 2 (25), 1 (-18.5). By size: 2, 1, 3. By signed mass: 2, 1, 3 / 3, 1, 2.
CLUSTERS = [
    {
        "cluster_id": 2,
        "size": 9,
        "stat_value": 25.0,
        "p_value": 0.01,
        "center_mni": [10.0, -20.0, 30.0],
        "mean_r": 0.5,
        "peak_r": 0.61,
    },
    {
        "cluster_id": 3,
        "size": 2,
        "stat_value": -40.0,
        "p_value": 0.002,
        "center_mni": [-12.0, 4.0, 8.0],
        "mean_r": -0.6,
        "peak_r": -0.83,
    },
    {
        "cluster_id": 1,
        "size": 4,
        "stat_value": -18.5,
        "p_value": 0.03,
        "center_mni": [0.0, 0.0, 0.0],
        "mean_r": -0.3,
        "peak_r": -0.35,
    },
]
TWO_SIDED_NOTE = (
    "Note: the test is two-sided. Clusters of positive and of negative r\n"
    "are formed separately and both are tested; the sign of a cluster's\n"
    "Mean r / Peak r says which direction it is.\n"
)


def _direct_summary(tmp_path, alternative):
    from tit.stats.config import CorrelationConfig
    from tit.stats.reporting import generate_correlation_summary

    cfg = CorrelationConfig(
        analysis_name="direct",
        subjects=[CorrelationConfig.Subject(f"s{i}", "N", float(i)) for i in (1, 2, 3)],
        n_permutations=99,
        use_weights=False,
    )
    out = tmp_path / f"summary_{alternative}.txt"
    generate_correlation_summary(
        cfg,
        np.ones((2, 2, 2, 3)),
        np.array([1.0, 2.0, 3.0]),
        R_VALUES,
        SIG_MASK,
        17.5,
        CLUSTERS,
        {},
        out,
        alternative=alternative,
    )
    return out.read_text()


@pytest.mark.parametrize(
    "alternative, note",
    [
        ("two-sided", TWO_SIDED_NOTE),
        (
            "greater",
            "Note: the test is one-sided (greater): only positive\n"
            "correlations can form a cluster.\n",
        ),
        (
            "less",
            "Note: the test is one-sided (less): only negative\n"
            "correlations can form a cluster.\n",
        ),
    ],
)
def test_summary_note_describes_the_alternative_it_ran(tmp_path, alternative, note):
    text = _direct_summary(tmp_path, alternative)

    assert f"Alternative hypothesis: {alternative}" in text.splitlines()
    assert note in text
    assert text.count("Note: the test is") == 1
    if alternative == "two-sided":
        assert "one-sided" not in text
    else:
        assert "two-sided" not in text


def test_correlation_summary_lists_clusters_by_magnitude(tmp_path):
    lines = _direct_summary(tmp_path, "two-sided").splitlines()

    head = lines.index("SIGNIFICANT CLUSTERS (by |cluster mass|, largest first):")
    body = [line for line in lines[head + 2 :] if line.strip()]  # after the rule
    assert lines[head + 1] == "-" * 70
    assert body[:12] == [
        "1. Cluster 3: 2 voxels, mass = -40.00, p = 0.0020",
        "   MNI Center: (-12.0, 4.0, 8.0)",
        "   Mean r: -0.6000",
        "   Peak r: -0.8300",
        "2. Cluster 2: 9 voxels, mass = 25.00, p = 0.0100",
        "   MNI Center: (10.0, -20.0, 30.0)",
        "   Mean r: 0.5000",
        "   Peak r: 0.6100",
        "3. Cluster 1: 4 voxels, mass = -18.50, p = 0.0300",
        "   MNI Center: (0.0, 0.0, 0.0)",
        "   Mean r: -0.3000",
        "   Peak r: -0.3500",
    ]
    assert "Number of Significant Clusters: 3" in lines


def test_correlation_summary_voxel_statistics_cover_the_significant_voxels(tmp_path):
    lines = _direct_summary(tmp_path, "two-sided").splitlines()
    sig_r = R_VALUES[SIG_MASK.astype(bool)]

    stats_at = lines.index("CORRELATION STATISTICS IN SIGNIFICANT VOXELS:")
    assert lines[stats_at + 2 : stats_at + 6] == [
        f"Mean r: {np.mean(sig_r):.4f}",
        "Peak r: -0.8300",  # largest |r| among (-0.83, -0.35, 0.48, 0.61), sign kept
        f"Min r:  {np.min(sig_r):.4f}",
        f"Max r:  {np.max(sig_r):.4f}",
    ]
    # Read off the fixture by hand: the mask keeps neither -0.99 nor 0.95.
    assert (np.min(sig_r), np.max(sig_r)) == (-0.83, 0.61)
    assert "Number of Significant Voxels: 4" in lines

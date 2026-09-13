"""2026-09-13: EEG array statistics against independent SciPy/MNE oracles.

Run: python -m pytest tests/numerical/test_eeg_array_stats.py -q
Fixtures are authored small arrays; expectations are recomputed with SciPy,
MNE, direct rank identities or exhaustive sign enumerations. Participant-data
reproduction is separate and no dataset is downloaded by these tests.
"""

import itertools
import numpy as np
import pytest


def test_sign_policy_is_explicit():
    from scipy import sparse
    from tit.stats.graph import find_clusters, cluster_mass

    # A chain of two positive and two negative nodes is an authored topology.
    graph = sparse.diags([np.ones(3), np.ones(3)], [-1, 1], shape=(4, 4)).tocsr()
    z = np.array([3.0, 3.0, -3.0, -3.0])
    cs = find_clusters(z, graph, 1.96, 0)
    assert [c.tolist() for c in cs] == [[0, 1], [2, 3]]
    legacy = find_clusters(z, graph, 1.96, 0, sign_policy="absolute_connected")
    assert len(legacy) == 1
    assert cluster_mass(z, legacy[0], 0) == np.abs(z).sum()


@pytest.mark.parametrize("statistic", ["t", "rank"])
def test_sampled_sign_null_matches_independent_one_node_oracle(statistic):
    from scipy import sparse, stats
    from tit.stats.graph import cluster_permutation

    x = np.array([1.0, 2.0, 4.0, 5.0, -3.0, 7.0])
    count, seed = 97, 11
    result = cluster_permutation(
        x[:, None], sparse.eye(1), statistic=statistic, n_permutations=count, seed=seed
    )

    def score(v):
        if statistic == "t":
            return stats.ttest_1samp(v, 0).statistic
        ranks = stats.rankdata(abs(v))
        n = len(v)
        return (ranks[v > 0].sum() - n * (n + 1) / 4) / np.sqrt(
            n * (n + 1) * (2 * n + 1) / 24
        )

    threshold = (
        stats.t.ppf(0.975, len(x) - 1) if statistic == "t" else stats.norm.ppf(0.975)
    )
    generator = np.random.default_rng(seed)
    expected = []
    for _ in range(count):
        z = score(x * generator.choice([-1.0, 1.0], len(x)))
        expected.append(abs(z) if abs(z) > threshold else 0.0)
    np.testing.assert_allclose(result.statistic, [score(x)])
    np.testing.assert_allclose(result.null_distribution, expected)
    assert np.all(result.pvalues >= 1 / (count + 1))


def test_independent_rank_scores_match_u_identity():
    from scipy import stats
    from tit.stats.graph import mannwhitney_z, wilcoxon_z

    a, b = np.array([1.0, 3.0, 6.0, 8.0]), np.array([2.0, 4.0, 5.0, 7.0, 9.0])
    u = stats.mannwhitneyu(a, b).statistic
    n, m = len(a), len(b)
    expected = (u - n * m / 2) / np.sqrt(n * m * (n + m + 1) / 12)
    np.testing.assert_allclose(mannwhitney_z(a[:, None], b[:, None]), [expected])
    # Only this case pins the published omission of zero and NaN differences.
    np.testing.assert_allclose(
        wilcoxon_z(np.array([0.0, np.nan, 1.0, -3.0, 5.0])[:, None]),
        wilcoxon_z(np.array([1.0, -3.0, 5.0])[:, None]),
    )


def test_source_adapter_matches_real_mne_exhaustive_null():
    # A clean child interpreter keeps host-suite MNE/joblib mocks out of the oracle.
    import subprocess
    import sys

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import numpy as np\nfrom scipy import sparse\nfrom mne.stats import spatio_temporal_cluster_1samp_test\nfrom tit.stats.graph import mne_cluster_test\nrng = np.random.default_rng(2)\nx = rng.normal(size=(5, 3)) + 1.4\ngraph = sparse.diags([np.ones(2), np.ones(2)], [-1, 1], shape=(3, 3)).tocsr()\nactual = mne_cluster_test(x, graph, n_permutations=5000)\nreference = spatio_temporal_cluster_1samp_test(x[:, None, :], adjacency=graph, n_permutations=5000, seed=42, tail=0, threshold=None, buffer_size=None, verbose=False)\nnp.testing.assert_allclose(actual[0], reference[0])\nnp.testing.assert_array_equal(actual[2], reference[2])\nnp.testing.assert_array_equal(actual[3], reference[3])\nassert len(actual[3]) == 2 ** (len(x) - 1)\n",
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_source_f_adapter_matches_real_mne():
    # A clean child interpreter keeps host-suite MNE/joblib mocks out of the oracle.
    import subprocess
    import sys

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import numpy as np\nfrom scipy import sparse\nfrom mne.stats import spatio_temporal_cluster_test\nfrom tit.stats.graph import mne_cluster_test\nrng = np.random.default_rng(6)\na, b = rng.normal(size=(6, 2)) + 2, rng.normal(size=(5, 2))\ngraph = sparse.csr_matrix([[0, 1], [1, 0]])\nactual = mne_cluster_test(a, graph, other=b, n_permutations=29)\nreference = spatio_temporal_cluster_test([a[:, None, :], b[:, None, :]], adjacency=graph, n_permutations=29, seed=42, tail=0, threshold=None, buffer_size=None, verbose=False)\nnp.testing.assert_allclose(actual[0], reference[0])\nnp.testing.assert_array_equal(actual[2], reference[2])\nnp.testing.assert_array_equal(actual[3], reference[3])\n",
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_map_correlations_match_scipy_and_perfect_policy():
    from scipy import stats
    from tit.stats.graph import pearson_columns

    rng = np.random.default_rng(8)
    x, y = rng.normal(size=(9, 4)), rng.normal(size=(9, 4))
    y[:, 0] = x[:, 0]
    x[1, 2] = np.nan
    r, p = pearson_columns(x, y)
    for col in range(x.shape[1]):
        mask = np.isfinite(x[:, col]) & np.isfinite(y[:, col])
        oracle = stats.pearsonr(x[mask, col], y[mask, col])
        np.testing.assert_allclose(r[col], oracle.statistic, atol=1e-14)
        np.testing.assert_allclose(p[col], oracle.pvalue, atol=1e-14)
    assert pearson_columns(x, x, published_policy=True)[1][0] == 1.0
    assert p[0] == 0.0


def test_map_permutation_is_seeded_and_subjectwise():
    from scipy import sparse, stats
    from tit.stats.graph import correlation_cluster_permutation

    rng = np.random.default_rng(8)
    x = rng.normal(size=(10, 2))
    y = x + rng.normal(size=x.shape) * 0.3
    result = correlation_cluster_permutation(
        x, y, sparse.csr_matrix([[0, 1], [1, 0]]), n_permutations=19, seed=7
    )
    np.testing.assert_allclose(
        result.statistic,
        [stats.spearmanr(x[:, j], y[:, j]).statistic for j in range(2)],
    )
    repeated = correlation_cluster_permutation(
        x, y, sparse.csr_matrix([[0, 1], [1, 0]]), n_permutations=19, seed=7
    )
    np.testing.assert_array_equal(result.null_distribution, repeated.null_distribution)


def test_effects_match_scipy_rank_identity_and_mean_population():
    from scipy import stats
    from tit.stats.effects import rank_biserial, bootstrap_effects

    a, b = np.array([0.0, 1.0, 3.0, 5.0]), np.array([1.0, 2.0, 7.0])
    assert rank_biserial(a, b) == pytest.approx(
        2 * stats.mannwhitneyu(a, b).statistic / (len(a) * len(b)) - 1
    )
    _, means = bootstrap_effects(a, n_bootstrap=101, seed=12)
    generator = np.random.default_rng(12)
    expected = [np.mean(generator.choice(a, len(a), replace=True)) for _ in range(101)]
    np.testing.assert_array_equal(means, expected)
    _, legacy = bootstrap_effects(a, n_bootstrap=101, seed=12, exclude_zero_draws=True)
    assert not np.array_equal(means, legacy)


def test_fdr_matches_scipy_and_keeps_families_separate():
    from scipy.stats import false_discovery_control
    from tit.stats.associations import bh_fdr, fdr_by_family

    p = np.array([0.001, 0.07, np.nan, 0.02, 0.8])
    expected = false_discovery_control(p[np.isfinite(p)])
    np.testing.assert_allclose(bh_fdr(p)[np.isfinite(p)], expected)
    q = fdr_by_family(np.array([0.01, 0.08, 0.03, 0.9]), ["a", "a", "b", "b"])
    np.testing.assert_allclose(q[:2], false_discovery_control([0.01, 0.08]))
    np.testing.assert_allclose(q[2:], false_discovery_control([0.03, 0.9]))


def test_partial_spearman_matches_three_correlation_identity():
    from scipy import stats
    from tit.stats.associations import partial_spearman

    rng = np.random.default_rng(12)
    y, x, z = rng.normal(size=(3, 17))
    a, b, c = (
        stats.spearmanr(x, y).statistic,
        stats.spearmanr(x, z).statistic,
        stats.spearmanr(y, z).statistic,
    )
    expected = (a - b * c) / np.sqrt((1 - b * b) * (1 - c * c))
    assert partial_spearman(y, x, z)[0] == pytest.approx(expected)


def test_rank_moderation_matches_direct_design_and_residual_null():
    from scipy import stats
    from tit.stats.associations import rank_moderation

    rng = np.random.default_rng(5)
    a, b = rng.normal(size=9), rng.normal(size=7)
    ya, yb = 0.7 * a + rng.normal(size=9), -0.4 * b + rng.normal(size=7)
    count, seed = 29, 4
    actual = rank_moderation(
        a, ya, b, yb, n_permutations=count, n_bootstrap=21, seed=seed
    )
    x = stats.rankdata(np.r_[a, b])
    x -= np.mean(x)
    y = stats.rankdata(np.r_[ya, yb])
    g = np.r_[np.ones(len(a)), np.zeros(len(b))]
    full = np.c_[np.ones(len(x)), x, g, x * g]
    red = full[:, :3]
    # pinv is an independent OLS path, with tolerance for SVD roundoff only.
    beta = np.linalg.pinv(full) @ y
    np.testing.assert_allclose(
        [actual.interaction, actual.slope_a, actual.slope_b],
        [beta[3], beta[1] + beta[3], beta[1]],
        atol=1e-13,
    )
    fitted = red @ (np.linalg.pinv(red) @ y)
    resid = y - fitted
    rg = np.random.default_rng(seed)
    null = [
        (np.linalg.pinv(full) @ (fitted + resid[rg.permutation(len(y))]))[3]
        for _ in range(count)
    ]
    np.testing.assert_allclose(actual.permutation_null, null, atol=1e-13)


def test_loso_is_subject_axis_and_rejects_ambiguous_ids():
    from tit.stats.robustness import leave_one_out

    x = np.arange(12).reshape(4, 3)
    rows = leave_one_out(x, lambda v: v[:, 1].mean(), subject_ids=list("abcd"))
    np.testing.assert_allclose(
        [r["estimate"] for r in rows], [(x[:, 1].sum() - v) / 3 for v in x[:, 1]]
    )
    with pytest.raises(ValueError, match="unique"):
        leave_one_out(x, np.mean, subject_ids=["a"] * 4)


def test_invalid_graph_rejected():
    from tit.stats.graph import cluster_permutation

    with pytest.raises(ValueError, match="symmetric"):
        cluster_permutation(np.ones((4, 2)), [[0, 1], [0, 0]])


def test_published_rank_score_ties_are_an_explicit_convention():
    from scipy import stats
    from tit.stats.graph import wilcoxon_z, mannwhitney_z

    # Midranks are SciPy's oracle; variance intentionally excludes tie correction.
    values = np.array([0.0, 1.0, 1.0, -2.0, 2.0, np.nan])
    finite = values[np.isfinite(values) & (values != 0)]
    ranks = stats.rankdata(np.abs(finite))
    n = len(finite)
    expected = (ranks[finite > 0].sum() - n * (n + 1) / 4) / np.sqrt(
        n * (n + 1) * (2 * n + 1) / 24
    )
    np.testing.assert_allclose(wilcoxon_z(values[:, None]), [expected])
    a, b = np.array([1.0, 1.0, 3.0]), np.array([1.0, 2.0, 3.0])
    u = stats.mannwhitneyu(a, b).statistic
    expected = (u - len(a) * len(b) / 2) / np.sqrt(
        len(a) * len(b) * (len(a) + len(b) + 1) / 12
    )
    np.testing.assert_allclose(mannwhitney_z(a[:, None], b[:, None]), [expected])


@pytest.mark.parametrize("reverse", [False, True])
def test_partial_spearman_fully_explained_ranks_are_undefined(reverse):
    from tit.stats.associations import partial_spearman

    z = np.arange(1.0, 11.0)
    y = z[::-1] if reverse else z
    r, p = partial_spearman(y, z, z[:, None])
    assert np.isnan(r) and np.isnan(p)


@pytest.mark.parametrize("scale", [1.0, 1e-20])
def test_partial_ranked_preserves_small_scale_residual_signal(scale):
    from tit.stats.associations import partial_ranked

    # Authored orthogonal centered vectors: removing z leaves independent u/v.
    z = np.array([-3.0, -1.0, 1.0, 3.0])
    u = np.array([1.0, -1.0, -1.0, 1.0])
    v = np.array([-1.0, 3.0, -3.0, 1.0])
    x, y = scale * (z + u), scale * (2 * z + u + v)
    expected = np.corrcoef(u, u + v)[0, 1]
    assert partial_ranked(y, x, z[:, None]) == pytest.approx(expected, abs=1e-14)
    assert np.isnan(partial_ranked(np.ones(4) * scale, x, z[:, None]))


def test_stored_zero_edges_do_not_connect_clusters_or_mutate_input():
    from scipy import sparse
    from tit.stats.graph import find_clusters, correlation_clusters, cluster_permutation

    graph = sparse.csr_matrix(np.ones((2, 2), dtype=bool))
    graph[0, 1] = False
    graph[1, 0] = False
    original_data, original_indices, original_indptr = (
        graph.data.copy(),
        graph.indices.copy(),
        graph.indptr.copy(),
    )
    # Explicitly stored False cells are not edges: dense oracle is identity.
    np.testing.assert_array_equal(graph.toarray(), np.eye(2, dtype=bool))
    assert [
        c.tolist() for c in find_clusters(np.array([3.0, 3.0]), graph, 1.96, 0)
    ] == [[0], [1]]
    clusters = correlation_clusters(
        np.array([0.8, 0.8]), np.array([0.001, 0.001]), graph
    )
    assert [c["nodes"].tolist() for c in clusters] == [[0], [1]]
    values = np.column_stack([np.arange(1.0, 7.0), np.arange(2.0, 8.0)])
    result = cluster_permutation(values, graph, n_permutations=19)
    assert [c.tolist() for c in result.clusters] == [[0], [1]]
    np.testing.assert_array_equal(graph.data, original_data)
    np.testing.assert_array_equal(graph.indices, original_indices)
    np.testing.assert_array_equal(graph.indptr, original_indptr)


def test_moderation_singular_bootstrap_draws_are_discarded_and_counted():
    from tit.stats.associations import rank_moderation

    a, b = np.array([0.0, 1.0]), np.array([2.0, 3.0])
    n_perm, n_boot, seed = 10, 100, 42
    result = rank_moderation(
        a, a, b, b[::-1], n_permutations=n_perm, n_bootstrap=n_boot, seed=seed
    )
    # For two distinct observations per group, a full-rank draw must retain
    # both observations in each group; unique sampled IDs are an independent oracle.
    rng = np.random.default_rng(seed)
    for _ in range(n_perm):
        rng.permutation(4)
    valid = []
    for _ in range(n_boot):
        ia, ib = rng.integers(0, 2, 2), rng.integers(0, 2, 2)
        valid.append(len(set(ia)) == 2 and len(set(ib)) == 2)
    np.testing.assert_array_equal(np.isfinite(result.bootstrap_interaction), valid)
    assert result.bootstrap_valid_count == sum(valid)
    assert result.bootstrap_valid_fraction == sum(valid) / n_boot
    legacy = rank_moderation(
        a,
        a,
        b,
        b[::-1],
        n_permutations=n_perm,
        n_bootstrap=n_boot,
        seed=seed,
        singular_bootstrap="legacy",
    )
    assert np.isfinite(legacy.bootstrap_interaction).all()
    assert legacy.bootstrap_valid_count == sum(valid)

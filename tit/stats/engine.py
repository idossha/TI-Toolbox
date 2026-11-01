"""Core statistical computation engine for cluster-based permutation testing.

Provides vectorised implementations of voxelwise t-tests, correlations,
cluster-based permutation correction, connected-component cluster analysis,
and MNE-style p-value computation.

All orchestration functions accept an optional ``logger``.
If *None* the module-level logger (``tit.stats.engine``) is used.

See Also
--------
tit.stats.permutation : High-level orchestration that drives this engine.
tit.stats.config : Configuration dataclasses consumed by the engine.
"""

import gc
import logging

import numpy as np
from joblib import Parallel, delayed
from scipy import stats as sp_stats
from scipy.ndimage import label, sum as ndimage_sum
from scipy.stats import rankdata

from tit.cpu import resolve_n_jobs

logger = logging.getLogger(__name__)


# ─── p-value computation (MNE-style) ─────────────────────────────────────


#: Relative tolerance under which a null statistic ties the observed one (see
#: :func:`pval_from_histogram`). The t maps were float32 when this was measured, so a
#: relabelling that reproduced the observed grouping in another column order moved the cluster
#: mass by float32 rounding, not float64 ulps: 4.3e-8 relative measured on the 5-vs-5 planted block of
#: ``tests/numerical/test_stats_runner_real_path.py`` (1e-6 is 23x that, about 8 float32 eps).
#: Cluster sizes are whole voxel counts, so 1e-6 cannot merge two sizes below 1e6 voxels.
TIE_RTOL = 1e-6


def pval_from_histogram(observed_stats, null_distribution, tail=0, sampled=True):
    """Compute per-cluster p-values from a permutation null distribution.

    Implements the MNE-Python approach based on Maris & Oostenveld (2007).

    Parameters
    ----------
    observed_stats : array-like
        Observed cluster-level statistics.
    null_distribution : array-like
        Max-cluster statistics from each permutation.
    tail : {0, 1, -1}, optional
        Tail of the test: 0 for two-sided, 1 for greater, -1 for less.
    sampled : bool, optional
        ``True`` (default) when *null_distribution* is a **random sample** of
        ``m`` permutations rather than the exhaustive enumeration of the
        permutation group.  The p-value is then the unbiased, valid estimator
        ``(b + 1) / (m + 1)`` of Phipson & Smyth (2010), where ``b`` counts the
        permutations at least as extreme as the observation.  Adding the
        observed statistic to its own null is what makes the test exact: the
        naive ``b / m`` can return ``p = 0``, which is not a valid p-value and
        makes the test anti-conservative at the very tail where cluster
        inference lives.  Pass ``sampled=False`` only when *null_distribution*
        really is the complete enumeration of every possible relabelling, in
        which case ``b / m`` is exact.

    Returns
    -------
    numpy.ndarray
        P-values, one per observed cluster.  With ``sampled=True`` the smallest
        attainable p-value is ``1 / (m + 1)``, never zero.

    References
    ----------
    Maris, E. & Oostenveld, R. (2007). J. Neurosci. Methods 164(1), 177-190.
    Phipson, B. & Smyth, G. K. (2010). Stat. Appl. Genet. Mol. Biol. 9(1), 39.
    """
    observed_stats = np.atleast_1d(observed_stats)
    null_distribution = np.asarray(null_distribution)
    m = null_distribution.size
    # A permutation that reproduces the observed labelling (or its mirror) gives the observed
    # statistic computed in another column order, which differs by float32 rounding; it is a
    # tie and counts as at least as extreme. TIE_RTOL is far below any real difference of two
    # cluster statistics (sizes are whole voxel counts).
    tol = TIE_RTOL * np.abs(observed_stats)

    if tail == -1:
        counts = np.array(
            [
                np.sum(null_distribution <= obs + t)
                for obs, t in zip(observed_stats, tol)
            ],
            dtype=float,
        )
    elif tail == 1:
        counts = np.array(
            [
                np.sum(null_distribution >= obs - t)
                for obs, t in zip(observed_stats, tol)
            ],
            dtype=float,
        )
    else:
        counts = np.array(
            [
                np.sum(np.abs(null_distribution) >= np.abs(obs) - t)
                for obs, t in zip(observed_stats, tol)
            ],
            dtype=float,
        )

    if sampled:
        return (counts + 1.0) / (m + 1.0)
    if m == 0:
        return np.ones_like(counts)
    return counts / m


# ─── cluster geometry: sign-separated components, oriented statistic ──────


def tail_from_alternative(alternative):
    """MNE-style tail code for an ``alternative`` string."""
    return {"greater": 1, "less": -1}.get(alternative, 0)


def label_signed(mask, t_stats, alternative):
    """Connected components that never merge voxels of opposite ``t`` sign.

    ``scipy.ndimage.label`` on a bare significance mask happily fuses a
    positive and a negative supra-threshold blob that happen to touch; the
    signed cluster mass of the fused object is then the *difference* of two
    real effects and can be ~0.  Cluster inference requires clusters to be
    sign-homogeneous, so positive and negative voxels are labelled separately
    and the negative labels offset past the positive ones.

    One-sided alternatives keep only the relevant sign, matching the
    correlation path and MNE's ``tail=+/-1`` behaviour.

    Returns ``(labelled_array, n_clusters)``.
    """
    if alternative == "greater":
        return label(mask & (t_stats > 0))
    if alternative == "less":
        return label(mask & (t_stats < 0))
    pos, n_pos = label(mask & (t_stats > 0))
    neg, n_neg = label(mask & (t_stats < 0))
    if n_neg:
        neg_sel = neg > 0
        pos[neg_sel] = neg[neg_sel] + n_pos
    return pos, n_pos + n_neg


def tail_statistic(sizes, masses, cluster_stat, tail):
    """Orient the cluster statistic so that *larger is more extreme*.

    The null distribution is a distribution of maxima, so observed and permuted
    statistics must be measured on the same, monotone "extremeness" scale:

    ``size``   -- always non-negative; clusters are already sign-restricted, so
                  the raw size is the extremeness.
    ``mass``   -- signed.  ``tail=+1`` uses the mass, ``tail=-1`` its negation,
                  ``tail=0`` its absolute value.

    Taking a plain ``max()`` of signed masses under a left or two-sided tail
    (the v2.x behaviour) selects the mass *closest to zero* among negative
    clusters, i.e. the least extreme one, and so produces a null that is far
    too small.
    """
    if cluster_stat == "size":
        return np.abs(np.asarray(sizes, dtype=float))
    masses = np.asarray(masses, dtype=float)
    if tail == 1:
        return masses
    if tail == -1:
        return -masses
    return np.abs(masses)


def peak_signed(values):
    """The value of largest magnitude, sign kept (``-0.99`` beats ``+0.5``).

    The peak of a negative-correlation cluster is its most negative ``r``;
    ``np.max`` would pick the value closest to zero, the weakest one.
    """
    values = np.asarray(values, dtype=float).ravel()
    return float(values[np.argmax(np.abs(values))])


def _max_cluster_stats(labeled, n_clusters, t_vol, cluster_stat, tail):
    """Max oriented cluster statistic over multi-voxel clusters.

    Returns ``(max_stat, size, signed_mass)`` of the winning cluster;
    ``(0, 0, 0.0)`` when there is no multi-voxel cluster.
    """
    if n_clusters == 0:
        return 0.0, 0, 0.0
    sizes = np.bincount(labeled.ravel(), minlength=n_clusters + 1)[1:]
    masses = np.asarray(
        ndimage_sum(t_vol, labeled, index=np.arange(1, n_clusters + 1)), dtype=float
    )
    multi = sizes > 1
    if not np.any(multi):
        return 0.0, 0, 0.0
    stats = tail_statistic(sizes, masses, cluster_stat, tail)
    stats = np.where(multi, stats, -np.inf)
    win = int(np.argmax(stats))
    return float(stats[win]), int(sizes[win]), float(masses[win])


# ─── correlation (vectorised) ─────────────────────────────────────────────


def correlation(
    voxel_data,
    effect_sizes,
    correlation_type="pearson",
    weights=None,
    voxel_data_preranked=False,
):
    """Vectorised correlation for all voxels at once.

    Returns (r_values, t_values, p_values) – each shape ``(n_voxels,)``.
    """
    n_voxels, n_subjects = voxel_data.shape

    if correlation_type == "spearman":
        if not voxel_data_preranked:
            voxel_data = np.apply_along_axis(rankdata, 1, voxel_data)
        effect_sizes = rankdata(effect_sizes)

    if weights is None:
        x_mean = np.mean(voxel_data, axis=1, keepdims=True)
        y_mean = np.mean(effect_sizes)
        x_centered = voxel_data - x_mean
        y_centered = effect_sizes - y_mean
        cov_xy = np.sum(x_centered * y_centered, axis=1) / (n_subjects - 1)
        std_x = np.std(voxel_data, axis=1, ddof=1)
        std_y = np.std(effect_sizes, ddof=1)
    else:
        weights = np.asarray(weights, dtype=np.float64)
        weight_sum = np.sum(weights)
        x_mean = np.sum(weights * voxel_data, axis=1, keepdims=True) / weight_sum
        y_mean = np.sum(weights * effect_sizes) / weight_sum
        x_centered = voxel_data - x_mean
        y_centered = effect_sizes - y_mean
        cov_xy = np.sum(weights * x_centered * y_centered, axis=1) / weight_sum
        var_x = np.sum(weights * (x_centered**2), axis=1) / weight_sum
        var_y = np.sum(weights * (y_centered**2)) / weight_sum
        std_x = np.sqrt(var_x)
        std_y = np.sqrt(var_y)

    denom = std_x * std_y
    valid_mask = denom > 1e-10

    r_values = np.zeros(n_voxels)
    r_values[valid_mask] = cov_xy[valid_mask] / denom[valid_mask]
    r_values = np.clip(r_values, -1.0, 1.0)

    df = n_subjects - 2
    r_squared = r_values**2
    denom_t = 1 - r_squared
    denom_t[denom_t < 1e-10] = 1e-10
    t_values = r_values * np.sqrt(df / denom_t)
    p_values = 2 * sp_stats.t.sf(np.abs(t_values), df)

    return r_values, t_values, p_values


def correlation_voxelwise(
    subject_data,
    effect_sizes,
    weights=None,
    correlation_type="pearson",
    log=None,
):
    """Voxelwise correlation between E-field and continuous outcome (ACES-style).

    Returns (r_values, t_statistics, p_values, valid_mask) – each ``(x, y, z)``.
    """
    _log = log or logger
    n_subjects = subject_data.shape[-1]
    if len(effect_sizes) != n_subjects:
        raise ValueError(
            f"effect_sizes length ({len(effect_sizes)}) != n_subjects ({n_subjects})"
        )
    if weights is not None and len(weights) != n_subjects:
        raise ValueError(
            f"weights length ({len(weights)}) != n_subjects ({n_subjects})"
        )
    if n_subjects < 3:
        raise ValueError(f"Need >= 3 subjects for correlation, got {n_subjects}")

    effect_sizes = np.asarray(effect_sizes, dtype=np.float64)

    weight_str = " (weighted)" if weights is not None else ""
    _log.info(
        "Voxelwise %s correlation%s – %d subjects",
        correlation_type.capitalize(),
        weight_str,
        n_subjects,
    )

    shape = subject_data.shape[:3]
    r_values = np.zeros(shape)
    t_statistics = np.zeros(shape)
    p_values = np.ones(shape)

    # Only where every subject has a field: a 0 is outside that subject's warped grey matter.
    valid_mask = np.all(subject_data > 0, axis=-1)
    valid_coords = np.argwhere(valid_mask)
    n_valid = len(valid_coords)
    _log.info("Valid voxels: %d", n_valid)

    voxel_data = np.zeros((n_valid, n_subjects), dtype=np.float64)
    for idx, (i, j, k) in enumerate(valid_coords):
        voxel_data[idx, :] = subject_data[i, j, k, :]

    r_1d, t_1d, p_1d = correlation(
        voxel_data, effect_sizes, correlation_type=correlation_type, weights=weights
    )

    for idx, (i, j, k) in enumerate(valid_coords):
        r_values[i, j, k] = r_1d[idx]
        t_statistics[i, j, k] = t_1d[idx]
        p_values[i, j, k] = p_1d[idx]

    _log.info(
        "r range [%.4f, %.4f], mean |r| %.4f",
        np.min(r_values[valid_mask]),
        np.max(r_values[valid_mask]),
        np.mean(np.abs(r_values[valid_mask])),
    )
    _log.info(
        "Uncorrected p<0.05: %d,  p<0.01: %d",
        np.sum((p_values < 0.05) & valid_mask),
        np.sum((p_values < 0.01) & valid_mask),
    )

    return r_values, t_statistics, p_values, valid_mask


# ─── t-tests (vectorised) ────────────────────────────────────────────────


def _safe_t(numerator, se):
    """t = numerator / se with the degenerate zero-SE cases handled like scipy.

    v2.x collapsed *every* zero-SE voxel to ``t = 0`` (hence ``p = 1``), which
    silently discards the strongest possible evidence: a contrast with zero
    within-group variance and a **nonzero** mean difference is perfect
    separation, and scipy reports ``t = +/-inf`` with ``p -> 0``.  Only the
    genuinely undefined ``0 / 0`` case (identical constant groups) is ``nan``,
    again matching :func:`scipy.stats.ttest_ind` / ``ttest_rel``.

    * numerator != 0, se == 0  ->  ``+/-inf``  (``t.sf`` then gives p = 0 or 1)
    * numerator == 0, se == 0  ->  ``nan``     (p = nan; caller masks it out)
    * se > 0                   ->  the ordinary ratio
    """
    numerator = np.asarray(numerator, dtype=np.float64)
    se = np.asarray(se, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return numerator / se


def ttest_ind(test_data, n_resp, n_non_resp, alternative="two-sided"):
    """Vectorised independent-samples t-test. Returns (t_stats, p_values).

    Welch's t with Welch-Satterthwaite df, as ``scipy.stats.ttest_ind(equal_var=False)``.
    A group of one subject has no variance estimate, so Welch's t is undefined; that design
    keeps the pooled-variance Student t (:func:`unpaired_statistic_name` says which ran).
    """
    # float64: float32 means leave constant groups a tiny non-zero SE (finite |t| ~ 1e7).
    test_data = np.asarray(test_data, dtype=np.float64)
    resp_data = test_data[:, :n_resp]
    non_resp_data = test_data[:, n_resp:]

    resp_means = np.mean(resp_data, axis=1)
    non_resp_means = np.mean(non_resp_data, axis=1)

    # Each group's SUM OF SQUARED DEVIATIONS, not ``(n - 1) * np.var(..., ddof=1)``: for a
    # group of ONE subject the latter is ``0 * nan == nan`` and every voxel of a 2-vs-1 design
    # came out degenerate (SCI-09); summing gives the singleton its true contribution, zero.
    resp_ss = np.sum((resp_data - resp_means[:, None]) ** 2, axis=1)
    non_resp_ss = np.sum((non_resp_data - non_resp_means[:, None]) ** 2, axis=1)

    if min(n_resp, n_non_resp) > 1:
        vn1 = resp_ss / (n_resp - 1) / n_resp
        vn2 = non_resp_ss / (n_non_resp - 1) / n_non_resp
        se_diff = np.sqrt(vn1 + vn2)
        with np.errstate(divide="ignore", invalid="ignore"):
            df = (vn1 + vn2) ** 2 / (vn1**2 / (n_resp - 1) + vn2**2 / (n_non_resp - 1))
        # Undefined only when both variances are 0; t is then +/-inf or nan (as scipy).
        df = np.where(np.isnan(df), 1.0, df)
    else:
        df = n_resp + n_non_resp - 2
        pooled_vars = (resp_ss + non_resp_ss) / df
        se_diff = np.sqrt(pooled_vars * (1 / n_resp + 1 / n_non_resp))
    t_stats = _safe_t(resp_means - non_resp_means, se_diff)

    match alternative:
        case "two-sided":
            p_values = 2 * sp_stats.t.sf(np.abs(t_stats), df)
        case "greater":
            p_values = sp_stats.t.sf(t_stats, df)
        case "less":
            p_values = sp_stats.t.sf(-t_stats, df)
        case _:
            raise ValueError("alternative must be 'two-sided', 'greater', or 'less'")

    return t_stats, p_values


def unpaired_statistic_name(n_resp, n_non_resp):
    """The voxel statistic :func:`ttest_ind` computes for these group sizes, for reports."""
    if min(n_resp, n_non_resp) > 1:
        return "Welch's t (unequal variances, Welch-Satterthwaite df)"
    return (
        "Student's t (pooled variance; Welch's t is undefined with a one-subject group)"
    )


def ttest_rel(test_data, n_resp, alternative="two-sided"):
    """Vectorised paired-samples t-test. Returns (t_stats, p_values)."""
    test_data = np.asarray(test_data, dtype=np.float64)  # see ttest_ind
    resp_data = test_data[:, :n_resp]
    non_resp_data = test_data[:, n_resp:]

    diff = resp_data - non_resp_data
    diff_means = np.mean(diff, axis=1)
    diff_stds = np.std(diff, axis=1, ddof=1)

    se = diff_stds / np.sqrt(n_resp)
    t_stats = _safe_t(diff_means, se)

    df = n_resp - 1
    match alternative:
        case "two-sided":
            p_values = 2 * sp_stats.t.sf(np.abs(t_stats), df)
        case "greater":
            p_values = sp_stats.t.sf(t_stats, df)
        case "less":
            p_values = sp_stats.t.sf(-t_stats, df)
        case _:
            raise ValueError("alternative must be 'two-sided', 'greater', or 'less'")

    return t_stats, p_values


def _neutralise_degenerate(t_values, p_values):
    """Replace non-finite t (and its p) with the null-effect pair (0, 1)."""
    bad = ~np.isfinite(t_values)
    if not np.any(bad):
        return t_values, p_values
    return np.where(bad, 0.0, t_values), np.where(bad, 1.0, p_values)


def check_paired_sizes(n_first, n_second):
    """Raise unless a paired test has as many first-group as second-group subjects."""
    if n_first != n_second:
        raise ValueError(
            f"Paired test requires equal sample sizes: {n_first} vs {n_second}"
        )


def exclude_degenerate(t_1d, p_1d, log):
    """Drop tests whose t is not finite; return ``(t, p, degenerate)``.

    Zero within-group variance gives ``nan`` (identical constant groups) or
    ``+/-inf`` (perfect separation). Neither carries a usable cluster mass, so
    the caller removes the ``degenerate`` entries from its valid mask; here they
    become the null-effect pair (0, 1) so no inf/nan can reach a cluster.
    """
    degenerate = ~np.isfinite(t_1d)
    if np.any(degenerate):
        log.warning(
            "Excluding %d voxel(s) with zero within-group variance "
            "(degenerate t: %d perfectly separated, %d constant)",
            int(degenerate.sum()),
            int(np.isinf(t_1d).sum()),
            int(np.isnan(t_1d).sum()),
        )
        t_1d = np.where(degenerate, 0.0, t_1d)
        p_1d = np.where(degenerate, 1.0, p_1d)
    return t_1d, p_1d, degenerate


def no_testable_voxel_error(n_with_data):
    """The error for an empty valid mask, saying which of its two causes it is.

    Every reduction over ``values[valid_mask]`` downstream would otherwise raise
    "zero-size array to reduction operation", a numpy traceback that says
    nothing about why. *n_with_data* is the number of voxels (or vertices) that
    had data before the degenerate ones were excluded.
    """
    return ValueError(
        "No voxel could be tested. "
        + (
            "Every voxel with data has zero within-group variance — a constant value "
            "across every subject in a group — and was excluded as degenerate."
            if n_with_data > 0
            else "No voxel is non-zero in every subject; the input images or the mask are "
            "empty, or the subjects' coverage does not overlap."
        )
        + " Check that the input images are the fields you meant and that the groups vary."
    )


def ttest_voxelwise(
    responders,
    non_responders,
    test_type="unpaired",
    alternative="two-sided",
    log=None,
):
    """Voxelwise t-test. Returns (p_values, t_statistics, valid_mask)."""
    _log = log or logger

    if test_type not in ("paired", "unpaired"):
        raise ValueError("test_type must be 'paired' or 'unpaired'")

    if test_type == "paired":
        check_paired_sizes(responders.shape[-1], non_responders.shape[-1])

    test_name = "Paired" if test_type == "paired" else "Unpaired"
    _log.info("Voxelwise %s t-test (alternative=%s)", test_name, alternative)

    shape = responders.shape[:3]
    p_values = np.ones(shape)
    t_statistics = np.zeros(shape)

    # Only where every subject has a field: a 0 is outside that subject's warped grey matter,
    # and testing it as a value turns group differences in coverage into "field" clusters.
    valid_mask = np.all(responders > 0, axis=-1) & np.all(non_responders > 0, axis=-1)
    valid_coords = np.argwhere(valid_mask)
    _log.info("Valid voxels (every subject > 0): %d", len(valid_coords))

    n_resp = responders.shape[-1]
    n_non_resp = non_responders.shape[-1]

    idx_i, idx_j, idx_k = valid_coords[:, 0], valid_coords[:, 1], valid_coords[:, 2]
    resp_extracted = responders[idx_i, idx_j, idx_k, :].astype(np.float64)
    non_resp_extracted = non_responders[idx_i, idx_j, idx_k, :].astype(np.float64)
    voxel_data = np.concatenate([resp_extracted, non_resp_extracted], axis=1)

    if test_type == "paired":
        t_1d, p_1d = ttest_rel(voxel_data, n_resp, alternative=alternative)
    else:
        t_1d, p_1d = ttest_ind(voxel_data, n_resp, n_non_resp, alternative=alternative)

    # Voxels whose t is not finite are degenerate (zero within-group variance:
    # ``nan`` for identical constant groups, ``+/-inf`` for perfect separation).
    # They carry no usable cluster mass, so they are dropped from valid_mask
    # rather than being allowed to poison a cluster with inf/nan.
    t_1d, p_1d, degenerate = exclude_degenerate(t_1d, p_1d, _log)
    if np.any(degenerate):
        valid_mask = valid_mask.copy()
        valid_mask[idx_i[degenerate], idx_j[degenerate], idx_k[degenerate]] = False

    t_statistics[idx_i, idx_j, idx_k] = t_1d
    p_values[idx_i, idx_j, idx_k] = p_1d

    # An empty mask is a real, reportable state of the data, not something a caller can use:
    # no voxel is non-zero in every subject, or every testable voxel was degenerate.
    if not valid_mask.any():
        raise no_testable_voxel_error(len(valid_coords))

    return p_values, t_statistics, valid_mask


# ─── single permutation workers (called in parallel) ─────────────────────


def _run_single_permutation(
    test_data,
    test_coords,
    n_resp,
    n_total,
    cluster_threshold,
    valid_mask,
    p_values_shape,
    test_type="unpaired",
    alternative="two-sided",
    cluster_stat="size",
    seed=None,
    return_indices=False,
):
    rng = np.random.default_rng(seed)
    perm_idx = None

    if test_type == "paired":
        perm_test_data = test_data.copy()
        resp_data = test_data[:, :n_resp]
        non_resp_data = test_data[:, n_resp:]
        sign_flips = rng.choice([-1, 1], size=n_resp)
        if return_indices:
            perm_idx = sign_flips
        n_voxels = test_data.shape[0]
        for i in range(n_voxels):
            mean_pair = (resp_data[i, :] + non_resp_data[i, :]) / 2
            diff_pair = (resp_data[i, :] - non_resp_data[i, :]) / 2
            perm_test_data[i, :n_resp] = mean_pair + sign_flips * diff_pair
            perm_test_data[i, n_resp:] = mean_pair - sign_flips * diff_pair
    else:
        perm_indices = rng.permutation(n_total)
        if return_indices:
            perm_idx = perm_indices
        perm_test_data = test_data[:, perm_indices]

    perm_p = np.ones(p_values_shape)
    perm_t = np.zeros(p_values_shape)

    if test_type == "paired":
        t_1d, p_1d = ttest_rel(perm_test_data, n_resp, alternative=alternative)
    else:
        t_1d, p_1d = ttest_ind(
            perm_test_data, n_resp, n_total - n_resp, alternative=alternative
        )

    # Degenerate (zero-variance) voxels can appear under a relabelling even
    # when the observed data had none; an inf mass would swamp the whole null,
    # so they are neutralised (slightly conservative, and logged upstream).
    t_1d, p_1d = _neutralise_degenerate(t_1d, p_1d)

    idx_i, idx_j, idx_k = test_coords[:, 0], test_coords[:, 1], test_coords[:, 2]
    perm_t[idx_i, idx_j, idx_k] = t_1d
    perm_p[idx_i, idx_j, idx_k] = p_1d

    tail = tail_from_alternative(alternative)
    perm_mask = (perm_p < cluster_threshold) & valid_mask
    perm_labeled, perm_n = label_signed(perm_mask, perm_t, alternative)

    max_cluster_stat, max_cluster_size, max_cluster_mass = _max_cluster_stats(
        perm_labeled, perm_n, perm_t, cluster_stat, tail
    )

    if return_indices:
        return max_cluster_stat, perm_idx, max_cluster_size, max_cluster_mass
    return max_cluster_stat, max_cluster_size, max_cluster_mass


def _run_single_correlation_permutation(
    voxel_data,
    effect_sizes,
    valid_coords,
    cluster_threshold,
    valid_mask,
    shape,
    correlation_type="pearson",
    weights=None,
    cluster_stat="mass",
    alternative="two-sided",
    seed=None,
    return_indices=False,
    voxel_data_preranked=False,
):
    n_subjects = len(effect_sizes)
    perm_idx = np.random.default_rng(seed).permutation(n_subjects)
    perm_effect = effect_sizes[perm_idx]
    perm_weights = weights[perm_idx] if weights is not None else None

    perm_r, perm_t, perm_p = correlation(
        voxel_data,
        perm_effect,
        correlation_type=correlation_type,
        weights=perm_weights,
        voxel_data_preranked=voxel_data_preranked,
    )

    perm_t, perm_p = _neutralise_degenerate(perm_t, perm_p)

    perm_p_vol = np.ones(shape)
    perm_t_vol = np.zeros(shape)
    idx_i, idx_j, idx_k = valid_coords[:, 0], valid_coords[:, 1], valid_coords[:, 2]
    perm_p_vol[idx_i, idx_j, idx_k] = perm_p
    perm_t_vol[idx_i, idx_j, idx_k] = perm_t

    tail = tail_from_alternative(alternative)
    perm_mask = (perm_p_vol < cluster_threshold) & valid_mask
    perm_labeled, perm_n = label_signed(perm_mask, perm_t_vol, alternative)

    max_cluster_stat, max_cluster_size, max_cluster_mass = _max_cluster_stats(
        perm_labeled, perm_n, perm_t_vol, cluster_stat, tail
    )

    if return_indices:
        return max_cluster_stat, perm_idx, max_cluster_size, max_cluster_mass
    return max_cluster_stat, max_cluster_size, max_cluster_mass


# ─── PermutationEngine ───────────────────────────────────────────────────


def resolve_seed(seed):
    """The permutation seed a run uses: *seed*, or a fresh 32-bit one when it is ``None``.

    Drawn here (not left to the generator) so the run can write it down and be reproduced;
    32 bits keep it exact in JSON readers that hold numbers as doubles.
    """
    return int(np.random.default_rng().integers(2**32)) if seed is None else int(seed)


class PermutationEngine:
    """Master class for cluster-based permutation testing.

    Stores all control parameters as self.* so methods only need data arrays.
    """

    def __init__(
        self,
        *,
        cluster_threshold: float = 0.05,
        n_permutations: int = 1000,
        alpha: float = 0.05,
        cluster_stat: str = "mass",
        alternative: str = "two-sided",
        n_jobs: int = -1,
        seed: int | None = None,
        log: logging.Logger | None = None,
    ):
        self.cluster_threshold = cluster_threshold
        self.n_permutations = n_permutations
        self.alpha = alpha
        self.cluster_stat = cluster_stat
        self.alternative = alternative
        self.n_jobs = n_jobs
        self.seed = seed  # None: fresh OS entropy; an int reproduces the null
        self._log = log or logger

    def correct_groups(
        self,
        responders,
        non_responders,
        *,
        p_values,
        t_statistics,
        valid_mask,
        test_type: str = "unpaired",
        perm_log_file: str | None = None,
        subject_ids_resp: list | None = None,
        subject_ids_non_resp: list | None = None,
    ) -> tuple:
        """Cluster-based permutation correction for group comparison.

        Returns ``(sig_mask, threshold, sig_clusters, null_dist, observed_clusters,
        correlation_data)``.
        """
        from .io_utils import save_permutation_details

        if self.cluster_stat == "mass" and t_statistics is None:
            raise ValueError("t_statistics required when cluster_stat='mass'")

        self._log.info(
            "Cluster-based permutation correction (%s, %s)",
            self.cluster_stat,
            self.alternative,
        )

        initial_mask = (p_values < self.cluster_threshold) & valid_mask
        labeled_array, n_clusters = label_signed(
            initial_mask, t_statistics, self.alternative
        )
        self._log.info(
            "Clusters at p<%.3f (uncorrected, sign-separated): %d",
            self.cluster_threshold,
            n_clusters,
        )

        empty = {"sizes": np.array([]), "masses": np.array([])}
        if n_clusters == 0:
            self._log.warning(
                "No clusters found. Consider increasing cluster_threshold."
            )
            return (
                np.zeros_like(p_values, dtype=int),
                0,
                [],
                np.array([]),
                [],
                empty,
            )

        # Pre-extract voxel data
        all_data = np.concatenate([responders, non_responders], axis=-1)
        n_resp = responders.shape[-1]
        n_total = n_resp + non_responders.shape[-1]

        test_coords = np.argwhere(valid_mask)
        n_test = len(test_coords)
        self._log.info("Pre-extracting %d voxels, %d subjects", n_test, n_total)

        # float64: a paired relabelling (mean +/- diff) of float32 values is then exact, so a
        # constant group stays constant instead of gaining rounding-noise variance.
        test_data = np.zeros((n_test, n_total), dtype=np.float64)
        for idx, (i, j, k) in enumerate(test_coords):
            test_data[idx, :] = all_data[i, j, k, :]
        del all_data
        gc.collect()

        self._log.info("Test data: %.1f MB", test_data.nbytes / (1024**2))

        actual_jobs = resolve_n_jobs(self.n_jobs)
        self._log.info(
            "Running %d permutations on %d cores",
            self.n_permutations,
            actual_jobs,
        )

        seeds = np.random.default_rng(self.seed).integers(
            0, 2**31, size=self.n_permutations
        )
        track = (
            perm_log_file is not None
            and subject_ids_resp is not None
            and subject_ids_non_resp is not None
        )

        if actual_jobs == 1:
            results = [
                _run_single_permutation(
                    test_data,
                    test_coords,
                    n_resp,
                    n_total,
                    self.cluster_threshold,
                    valid_mask,
                    p_values.shape,
                    test_type=test_type,
                    alternative=self.alternative,
                    cluster_stat=self.cluster_stat,
                    seed=seeds[i],
                    return_indices=track,
                )
                for i in range(self.n_permutations)
            ]
        else:
            results = Parallel(n_jobs=actual_jobs, verbose=0)(
                delayed(_run_single_permutation)(
                    test_data,
                    test_coords,
                    n_resp,
                    n_total,
                    self.cluster_threshold,
                    valid_mask,
                    p_values.shape,
                    test_type=test_type,
                    alternative=self.alternative,
                    cluster_stat=self.cluster_stat,
                    seed=seeds[i],
                    return_indices=track,
                )
                for i in range(self.n_permutations)
            )
            gc.collect()

        del test_data
        gc.collect()

        if track:
            null_stats = np.array([r[0] for r in results])
            perm_indices = [r[1] for r in results]
            null_sizes = [r[2] for r in results]
            null_masses = [r[3] for r in results]
        else:
            null_stats = np.array([r[0] for r in results])
            perm_indices = None
            null_sizes = [r[1] for r in results]
            null_masses = [r[2] for r in results]

        # Determine threshold
        sorted_null = np.sort(null_stats)[::-1]
        ti = max(1, min(int(self.alpha * self.n_permutations), len(sorted_null)))
        cluster_stat_threshold = sorted_null[ti - 1]

        stat_unit = "voxels" if self.cluster_stat == "size" else "mass units"
        self._log.info(
            "Threshold (p<%.3f): %.2f %s  " "(null min=%.2f, mean=%.2f, max=%.2f)",
            self.alpha,
            cluster_stat_threshold,
            stat_unit,
            np.min(null_stats),
            np.mean(null_stats),
            np.max(null_stats),
        )

        if perm_log_file is not None and perm_indices is not None:
            info = [
                {
                    "perm_num": i,
                    "perm_idx": perm_indices[i],
                    "max_cluster_size": null_stats[i],
                }
                for i in range(self.n_permutations)
            ]
            save_permutation_details(
                info,
                perm_log_file,
                subject_ids_resp,
                subject_ids_non_resp,
                paired=test_type == "paired",
            )
            self._log.info("Permutation log saved: %s", perm_log_file)

        # Identify significant clusters (MNE-style per-cluster p-values)
        sig_mask, sig_clusters, all_observed = _identify_significant_clusters(
            labeled_array,
            n_clusters,
            t_statistics,
            null_stats,
            self.cluster_stat,
            self.alpha,
            self.alternative,
            self._log,
        )

        self._log.info(
            "Significant: %d clusters, %d voxels",
            len(sig_clusters),
            np.sum(sig_mask),
        )

        correlation_data = {
            "sizes": np.array(null_sizes),
            "masses": np.array(null_masses),
        }
        return (
            sig_mask,
            cluster_stat_threshold,
            sig_clusters,
            null_stats,
            all_observed,
            correlation_data,
        )

    def correct_correlation(
        self,
        subject_data,
        effect_sizes,
        *,
        r_values,
        t_statistics,
        p_values,
        valid_mask,
        correlation_type: str = "pearson",
        weights=None,
        perm_log_file: str | None = None,
        subject_ids: list | None = None,
    ) -> tuple:
        """Cluster-based permutation correction for correlation analysis.

        Returns ``(sig_mask, threshold, sig_clusters, null_dist, observed_clusters,
        correlation_data)``.
        """
        from .io_utils import save_correlation_permutation_details

        effect_sizes = np.asarray(effect_sizes, dtype=np.float64)
        n_subjects = len(effect_sizes)

        self._log.info(
            "Correlation cluster correction (%s, %s, %s)",
            correlation_type,
            self.cluster_stat,
            self.alternative,
        )

        # Form initial clusters based on alternative
        initial_mask = (p_values < self.cluster_threshold) & valid_mask
        labeled_array, n_clusters = label_signed(
            initial_mask, t_statistics, self.alternative
        )
        self._log.info("Clusters at p<%.3f: %d", self.cluster_threshold, n_clusters)

        empty = {"sizes": np.array([]), "masses": np.array([])}
        if n_clusters == 0:
            self._log.warning("No clusters found.")
            return (
                np.zeros_like(p_values, dtype=int),
                0,
                [],
                np.array([]),
                [],
                empty,
            )

        # Pre-extract voxel data
        valid_coords = np.argwhere(valid_mask)
        n_valid = len(valid_coords)
        voxel_data = np.zeros((n_valid, n_subjects), dtype=np.float64)
        for idx, (i, j, k) in enumerate(valid_coords):
            voxel_data[idx, :] = subject_data[i, j, k, :]

        # Pre-rank for Spearman
        preranked = False
        if correlation_type == "spearman":
            self._log.info("Pre-ranking voxel data for Spearman (%d voxels)", n_valid)
            voxel_data = np.apply_along_axis(rankdata, 1, voxel_data)
            preranked = True

        actual_jobs = resolve_n_jobs(self.n_jobs)
        self._log.info(
            "Running %d permutations on %d cores",
            self.n_permutations,
            actual_jobs,
        )

        seeds = np.random.default_rng(self.seed).integers(
            0, 2**31, size=self.n_permutations
        )
        track = perm_log_file is not None and subject_ids is not None

        if actual_jobs == 1:
            results = [
                _run_single_correlation_permutation(
                    voxel_data,
                    effect_sizes,
                    valid_coords,
                    self.cluster_threshold,
                    valid_mask,
                    p_values.shape,
                    correlation_type=correlation_type,
                    weights=weights,
                    cluster_stat=self.cluster_stat,
                    alternative=self.alternative,
                    seed=seeds[i],
                    return_indices=track,
                    voxel_data_preranked=preranked,
                )
                for i in range(self.n_permutations)
            ]
        else:
            results = Parallel(n_jobs=actual_jobs, verbose=0)(
                delayed(_run_single_correlation_permutation)(
                    voxel_data,
                    effect_sizes,
                    valid_coords,
                    self.cluster_threshold,
                    valid_mask,
                    p_values.shape,
                    correlation_type=correlation_type,
                    weights=weights,
                    cluster_stat=self.cluster_stat,
                    alternative=self.alternative,
                    seed=seeds[i],
                    return_indices=track,
                    voxel_data_preranked=preranked,
                )
                for i in range(self.n_permutations)
            )
            gc.collect()

        del voxel_data
        gc.collect()

        if track:
            null_stats = np.array([r[0] for r in results])
            perm_indices = [r[1] for r in results]
            null_sizes = [r[2] for r in results]
            null_masses = [r[3] for r in results]
        else:
            null_stats = np.array([r[0] for r in results])
            perm_indices = None
            null_sizes = [r[1] for r in results]
            null_masses = [r[2] for r in results]

        sorted_null = np.sort(null_stats)[::-1]
        ti = max(1, min(int(self.alpha * self.n_permutations), len(sorted_null)))
        cluster_stat_threshold = sorted_null[ti - 1]

        stat_unit = "voxels" if self.cluster_stat == "size" else "mass units"
        self._log.info(
            "Threshold (p<%.3f): %.2f %s  " "(null min=%.2f, mean=%.2f, max=%.2f)",
            self.alpha,
            cluster_stat_threshold,
            stat_unit,
            np.min(null_stats),
            np.mean(null_stats),
            np.max(null_stats),
        )

        if perm_indices is not None:
            info = [
                {
                    "perm_num": i,
                    "perm_idx": perm_indices[i],
                    "max_cluster_size": null_stats[i],
                }
                for i in range(self.n_permutations)
            ]
            save_correlation_permutation_details(info, perm_log_file, subject_ids)
            self._log.info("Permutation log saved: %s", perm_log_file)

        # Identify significant clusters
        sig_mask, sig_clusters, all_observed = _identify_significant_clusters(
            labeled_array,
            n_clusters,
            t_statistics,
            null_stats,
            self.cluster_stat,
            self.alpha,
            self.alternative,
            self._log,
            r_values=r_values,
        )

        self._log.info(
            "Significant: %d clusters, %d voxels",
            len(sig_clusters),
            np.sum(sig_mask),
        )

        correlation_data = {
            "sizes": np.array(null_sizes),
            "masses": np.array(null_masses),
        }
        return (
            sig_mask,
            cluster_stat_threshold,
            sig_clusters,
            null_stats,
            all_observed,
            correlation_data,
        )


# ─── shared: identify significant clusters ───────────────────────────────


def _identify_significant_clusters(
    labeled_array,
    n_clusters,
    t_statistics,
    null_stats,
    cluster_stat,
    alpha,
    alternative,
    _log,
    r_values=None,
):
    """Post-permutation cluster identification (shared by both workflows).

    Every label is tested (negative clusters are numbered after all positive ones), and
    ``all_observed`` holds the 10 most extreme clusters by the oriented statistic.
    """
    labels = labeled_array.ravel()
    sizes = np.bincount(labels, minlength=n_clusters + 1)[1:]
    masses = np.zeros(n_clusters)
    if cluster_stat == "mass":
        t_flat = np.ravel(t_statistics)
        masses = np.bincount(labels, weights=t_flat, minlength=n_clusters + 1)[1:]
    ids = np.flatnonzero(sizes > 1) + 1  # single voxels are never clusters
    sizes, masses = sizes[ids - 1], masses[ids - 1]
    # Reported value keeps its natural units (signed mass, positive size); the comparison
    # against the null is made on the oriented statistic.
    stat_values = sizes.astype(float) if cluster_stat == "size" else masses
    tail_stats = tail_statistic(
        sizes, masses, cluster_stat, tail_from_alternative(alternative)
    )

    sig_mask = np.zeros(labeled_array.shape, dtype=int)
    sig_clusters = []
    all_observed = []

    if ids.size:
        # ``null_stats`` is already a distribution of *oriented* maxima
        # (see tail_statistic), so the comparison is always right-tailed.
        pvals = pval_from_histogram(tail_stats, null_stats, tail=1)

        for i in np.argsort(-tail_stats, kind="stable")[:10]:
            all_observed.append(
                {
                    "id": int(ids[i]),
                    "size": int(sizes[i]),
                    "stat_value": float(stat_values[i]),
                    "p_value": float(pvals[i]),
                }
            )

        _log.info("Top clusters:")
        for obs in all_observed[:5]:
            status = "SIG" if obs["p_value"] < alpha else "ns"
            _log.info(
                "  Cluster %d: %s=%.2f, size=%d, p=%.4f (%s)",
                obs["id"],
                cluster_stat,
                obs["stat_value"],
                obs["size"],
                obs["p_value"],
                status,
            )

        for i in np.flatnonzero(pvals < alpha):
            coords = np.where(labeled_array == ids[i])
            sig_mask[coords] = 1
            entry = {
                "id": int(ids[i]),
                "size": int(sizes[i]),
                "stat_value": float(stat_values[i]),
                "p_value": float(pvals[i]),
                "center_voxel": np.mean(np.stack(coords, axis=1), axis=0),
            }
            if r_values is not None:
                entry["peak_r"] = peak_signed(r_values[coords])
                entry["mean_r"] = float(np.mean(r_values[coords]))
            sig_clusters.append(entry)

    return sig_mask, sig_clusters, all_observed


# ─── cluster analysis ────────────────────────────────────────────────────


def significant_cluster_table(sig_clusters, affine, log=None):
    """The engine's significant clusters, with MNI centres, most extreme first.

    *sig_clusters* are the sign-separated clusters that passed the permutation
    test (from :meth:`PermutationEngine.correct_groups` /
    :meth:`~PermutationEngine.correct_correlation`). Relabelling the union of
    their voxels instead (as :func:`cluster_analysis` does) fuses touching
    clusters of opposite sign and loses each one's statistic and p-value.

    Each row keeps the engine's ``id`` as ``cluster_id`` plus ``size``,
    ``stat_value`` (signed mass, or size), ``p_value``, ``center_voxel``,
    ``center_mni`` (``affine`` applied to the voxel centroid) and, for a
    correlation, ``mean_r`` / ``peak_r``. Rows are ordered by ``|stat_value|``
    (the extremeness the permutation test ranks on; clusters are
    sign-homogeneous), largest first.
    """
    _log = log or logger
    affine = np.asarray(affine, dtype=float)
    rows = []
    for c in sig_clusters:
        center = np.asarray(c["center_voxel"], dtype=float)
        row = {
            "cluster_id": c["id"],
            "size": c["size"],
            "stat_value": c["stat_value"],
            "p_value": c["p_value"],
            "center_voxel": center,
            "center_mni": affine[:3, :3] @ center + affine[:3, 3],
        }
        for key in ("mean_r", "peak_r"):
            if key in c:
                row[key] = c[key]
        rows.append(row)
    rows.sort(key=lambda r: (-abs(r["stat_value"]), r["cluster_id"]))

    for r in rows[:10]:
        _log.info(
            "  Cluster %d: %d voxels, MNI (%.1f, %.1f, %.1f)",
            r["cluster_id"],
            r["size"],
            *r["center_mni"],
        )
    return rows


def cluster_analysis(sig_mask, affine, log=None):
    """Connected-component analysis with MNI coordinate mapping.

    Returns a list of cluster dicts sorted by size (descending).
    """
    import nibabel as nib

    _log = log or logger
    labeled_array, num_clusters = label(sig_mask)

    if num_clusters == 0:
        _log.info("No clusters found in significance mask")
        return []

    clusters = []
    for cid in range(1, num_clusters + 1):
        coords = np.argwhere(labeled_array == cid)
        com_voxel = np.mean(coords, axis=0)
        com_mni = nib.affines.apply_affine(affine, com_voxel)
        clusters.append(
            {
                "cluster_id": cid,
                "size": len(coords),
                "center_voxel": com_voxel,
                "center_mni": com_mni,
            }
        )

    clusters.sort(key=lambda c: c["size"], reverse=True)

    _log.info("Found %d clusters", num_clusters)
    for c in clusters[:10]:
        _log.info(
            "  Cluster %d: %d voxels, MNI (%.1f, %.1f, %.1f)",
            c["cluster_id"],
            c["size"],
            c["center_mni"][0],
            c["center_mni"][1],
            c["center_mni"][2],
        )

    return clusters

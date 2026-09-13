"""Array-only effect sizes and participant bootstrap confidence intervals.

Finite participants remain in the mean bootstrap, including exact zeros.
``exclude_zero_draws=True`` reproduces the published sleepTI bootstrap policy;
it should be requested only to reproduce that analysis, not selected implicitly.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def rank_biserial(values: np.ndarray, other: np.ndarray | None = None) -> float:
    """Signed matched-pairs or independent-samples rank-biserial effect.

    Positive values favor ``values``. Paired input is already a difference;
    zero differences are omitted from signed ranking (Wilcox convention).
    """
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if other is None:
        a = a[a != 0]
        if a.size < 2:
            return float("nan")
        ranks = stats.rankdata(np.abs(a))
        plus, minus = ranks[a > 0].sum(), ranks[a < 0].sum()
        return float((plus - minus) / (plus + minus))
    b = np.asarray(other, dtype=float)
    b = b[np.isfinite(b)]
    if min(a.size, b.size) < 2:
        return float("nan")
    ranks = stats.rankdata(np.concatenate([a, b]))
    u = float(ranks[: a.size].sum()) - a.size * (a.size + 1.0) / 2.0
    return 2.0 * u / (a.size * b.size) - 1.0


def percentile_ci(samples: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    """Finite-sample percentile interval; all-invalid input returns NaN bounds."""
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")
    v = np.asarray(samples, dtype=float)
    v = v[np.isfinite(v)]
    if not v.size:
        return float("nan"), float("nan")
    return float(np.percentile(v, 100 * alpha / 2)), float(
        np.percentile(v, 100 * (1 - alpha / 2))
    )


def bootstrap_effects(
    values: np.ndarray,
    other: np.ndarray | None = None,
    *,
    n_bootstrap: int = 5000,
    rng: np.random.Generator | None = None,
    seed: int = 42,
    exclude_zero_draws: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Return bootstrap rank-biserial effects and means / mean differences.

    Resampling is across participants and independently within each group.
    Paired data must be participant differences. Ranks are recomputed in each
    draw; zeros affect the mean but not signed ranks unless the explicit
    published compatibility option removes them before sampling.
    """
    if n_bootstrap < 1:
        raise ValueError("n_bootstrap must be positive")
    rng = np.random.default_rng(seed) if rng is None else rng
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if other is None:
        if exclude_zero_draws:
            a = a[a != 0]
        if a.size < 2:
            return np.full(n_bootstrap, np.nan), np.full(n_bootstrap, np.nan)
        draws = a[rng.integers(0, a.size, size=(n_bootstrap, a.size))]
        if exclude_zero_draws:
            ranks = stats.rankdata(np.abs(draws), axis=1)
        else:
            ranks = stats.rankdata(
                np.where(draws != 0, np.abs(draws), np.nan), axis=1, nan_policy="omit"
            )
            ranks = np.nan_to_num(ranks)
        plus = np.sum(ranks * (draws > 0), axis=1)
        minus = np.sum(ranks * (draws < 0), axis=1)
        total = plus + minus
        r = np.divide(
            plus - minus, total, out=np.full(n_bootstrap, np.nan), where=total > 0
        )
        return r, draws.mean(axis=1)
    b = np.asarray(other, dtype=float)
    b = b[np.isfinite(b)]
    if min(a.size, b.size) < 2:
        return np.full(n_bootstrap, np.nan), np.full(n_bootstrap, np.nan)
    da = a[rng.integers(0, a.size, size=(n_bootstrap, a.size))]
    db = b[rng.integers(0, b.size, size=(n_bootstrap, b.size))]
    ranks = stats.rankdata(np.concatenate([da, db], axis=1), axis=1)
    u = np.sum(ranks[:, : a.size], axis=1) - a.size * (a.size + 1.0) / 2.0
    return 2.0 * u / (a.size * b.size) - 1.0, da.mean(axis=1) - db.mean(axis=1)


def cluster_mean_r_along_subjects(
    field: np.ndarray, response: np.ndarray
) -> np.ndarray:
    """Per-bootstrap cluster mean correlation. field/response: (n_boot, n_subjects, k)."""
    valid = np.isfinite(field) & np.isfinite(response)
    x = np.where(valid, field, np.nan)
    y = np.where(valid, response, np.nan)
    x_centered = x - np.nanmean(x, axis=1, keepdims=True)
    y_centered = y - np.nanmean(y, axis=1, keepdims=True)
    numerator = np.nansum(x_centered * y_centered, axis=1)
    denominator = np.sqrt(
        np.nansum(x_centered**2, axis=1) * np.nansum(y_centered**2, axis=1)
    )
    r = np.divide(
        numerator,
        denominator,
        out=np.full_like(numerator, np.nan),
        where=denominator > 0,
    )
    r[valid.sum(axis=1) < 4] = np.nan
    return np.nanmean(r, axis=1)


def bootstrap_cluster_mean_r_ci(
    field_cluster: np.ndarray,
    response_cluster: np.ndarray,
    *,
    statistic: str,
    n_bootstrap: int,
    ci_alpha: float,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Subject-level bootstrap CI on the cluster mean correlation.

    field_cluster/response_cluster are raw (unranked) subject-by-cluster-vertex
    matrices; for Spearman each resample is re-ranked across subjects.
    """
    n_subjects = field_cluster.shape[0]
    idx = rng.integers(0, n_subjects, size=(n_bootstrap, n_subjects))
    field_draws = field_cluster[idx]
    response_draws = response_cluster[idx]
    if statistic == "spearman":
        field_draws = stats.rankdata(field_draws, axis=1, nan_policy="omit")
        response_draws = stats.rankdata(response_draws, axis=1, nan_policy="omit")
    boot_means = cluster_mean_r_along_subjects(field_draws, response_draws)
    return percentile_ci(boot_means, ci_alpha)

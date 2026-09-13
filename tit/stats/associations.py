"""Array-only associations, explicit-family FDR and rank-dose moderation."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy import stats


def residualize(y: np.ndarray, covariates: np.ndarray) -> np.ndarray:
    """OLS residuals including an intercept; inputs must be finite."""
    y = np.asarray(y, dtype=float)
    z = np.asarray(covariates, dtype=float)
    if z.size == 0:
        z = np.empty((y.size, 0))
    elif z.ndim == 1:
        z = z[:, None]
    if z.ndim != 2 or y.ndim != 1 or z.shape[0] != y.size:
        raise ValueError("covariates must have one row per outcome")
    if not np.isfinite(y).all() or not np.isfinite(z).all():
        raise ValueError("residualize requires finite inputs")
    design = np.column_stack([np.ones(y.size), z])
    return y - design @ np.linalg.lstsq(design, y, rcond=None)[0]


def partial_ranked(y: np.ndarray, x: np.ndarray, covariates: np.ndarray) -> float:
    """Partial Pearson on already ranked finite inputs, for explicit pipelines.

    Fully explained or constant inputs have undefined partial correlation.
    Residuals below least-squares roundoff are rejected relative to each
    centered input's own scale, never against an absolute magnitude floor.
    """
    y, x = np.asarray(y, dtype=float), np.asarray(x, dtype=float)
    ey, ex = residualize(y, covariates), residualize(x, covariates)

    def standardized_residual(original, residual):
        centered = original - original.mean()
        scale = np.max(np.abs(centered)) if centered.size else 0.0
        if scale == 0:
            return None
        # Scale first to avoid underflow for legitimate small-valued inputs.
        centered = centered / scale
        residual = (residual - residual.mean()) / scale
        z = np.asarray(covariates)
        columns = z.shape[1] if z.ndim == 2 else 1
        tolerance = 8 * np.finfo(float).eps * max(original.size, columns + 1)
        if np.linalg.norm(residual) <= tolerance * np.linalg.norm(centered):
            return None
        return residual

    ey, ex = standardized_residual(y, ey), standardized_residual(x, ex)
    if ey is None or ex is None:
        return float("nan")
    return float(np.corrcoef(ey, ex)[0, 1])


def partial_pvalue(
    r: float, n: int, n_covariates: int, *, published_policy: bool = False
) -> float:
    """Two-sided t approximation; not a permutation p-value."""
    df = n - n_covariates - 2
    if df <= 0 or not np.isfinite(r):
        return float("nan")
    if abs(r) >= 1:
        return float("nan") if published_policy else 0.0
    return float(2 * stats.t.sf(abs(r) * np.sqrt(df / (1 - r * r)), df))


def partial_spearman(
    y: np.ndarray, x: np.ndarray, covariates: np.ndarray
) -> tuple[float, float]:
    """Complete-case partial Spearman rho and approximate two-sided p.

    The same complete participant set is selected before ranking every input.
    A rank-deficient covariate design raises rather than reporting misleading
    degrees of freedom. Bootstrap/permutation inference is a separate choice.
    """
    y, x, z = np.asarray(y, float), np.asarray(x, float), np.asarray(covariates, float)
    if z.ndim == 1:
        z = z[:, None]
    if y.ndim != 1 or x.shape != y.shape or z.ndim != 2 or z.shape[0] != y.size:
        raise ValueError("inputs must share participant rows")
    valid = np.isfinite(y) & np.isfinite(x) & np.isfinite(z).all(axis=1)
    y, x, z = y[valid], x[valid], z[valid]
    if y.size <= z.shape[1] + 2:
        return float("nan"), float("nan")
    ry, rx, rz = stats.rankdata(y), stats.rankdata(x), stats.rankdata(z, axis=0)
    if np.linalg.matrix_rank(np.column_stack([np.ones(y.size), rz])) < z.shape[1] + 1:
        raise ValueError("covariate design is rank deficient")
    r = partial_ranked(ry, rx, rz)
    return r, partial_pvalue(r, y.size, z.shape[1])


def bh_fdr(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg q values for one explicitly supplied family.

    NaNs are omitted from this family's denominator and returned as NaNs.
    """
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1:
        raise ValueError("supply a one-dimensional family")
    finite = np.isfinite(p)
    if np.any((p[finite] < 0) | (p[finite] > 1)):
        raise ValueError("p values must lie in [0, 1]")
    q = np.full_like(p, np.nan)
    idx = np.flatnonzero(finite)
    if not idx.size:
        return q
    order = idx[np.argsort(p[idx])]
    prev = 1.0
    for rank, j in enumerate(order[::-1]):
        prev = min(prev, p[j] * idx.size / (idx.size - rank))
        q[j] = prev
    return q


def fdr_by_family(pvalues: np.ndarray, families: list[str]) -> np.ndarray:
    """Apply BH separately within the supplied family IDs; preserve row order."""
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1 or len(families) != p.size:
        raise ValueError("one family ID is required per p value")
    q = np.full_like(p, np.nan)
    family = np.asarray(families)
    for name in dict.fromkeys(families):
        mask = family == name
        q[mask] = bh_fdr(p[mask])
    return q


def moderation_design(
    dose: np.ndarray, group: np.ndarray, *, full: bool = True
) -> np.ndarray:
    """Intercept, dose, group and optional dose × group design."""
    cols = [np.ones(len(dose)), dose, group]
    if full:
        cols.append(dose * group)
    return np.column_stack(cols)


def ols_coefficients(design: np.ndarray, response: np.ndarray) -> np.ndarray:
    """Least-squares coefficients; low-level compatibility helper."""
    return np.linalg.lstsq(design, response, rcond=None)[0]


def freedman_lane(
    response: np.ndarray,
    full_design: np.ndarray,
    reduced_design: np.ndarray,
    *,
    coefficient: int,
    n_permutations: int = 10000,
    rng: np.random.Generator | None = None,
    seed: int = 42,
) -> tuple[float, float, np.ndarray]:
    """Two-sided residual permutation for a coefficient in nested fixed designs.

    Requires exchangeable reduced-model residuals across supplied rows. This
    routine does not infer exchangeability blocks or heteroscedastic corrections.
    The raw coefficient is the test statistic, matching the study's rank model.
    """
    y, full, reduced = map(
        lambda a: np.asarray(a, dtype=float), (response, full_design, reduced_design)
    )
    if (
        y.ndim != 1
        or full.ndim != 2
        or reduced.ndim != 2
        or full.shape[0] != y.size
        or reduced.shape[0] != y.size
    ):
        raise ValueError("designs must share response rows")
    if not all(np.isfinite(a).all() for a in (y, full, reduced)):
        raise ValueError("designs and response must be finite")
    if n_permutations < 1 or not 0 <= coefficient < full.shape[1]:
        raise ValueError("invalid permutation count or coefficient")
    if (
        np.linalg.matrix_rank(full) < full.shape[1]
        or np.linalg.matrix_rank(reduced) < reduced.shape[1]
    ):
        raise ValueError("design is rank deficient")
    if np.linalg.matrix_rank(np.column_stack([full, reduced])) > full.shape[1]:
        raise ValueError("reduced design must be nested in full design")
    rng = np.random.default_rng(seed) if rng is None else rng
    observed = float(ols_coefficients(full, y)[coefficient])
    fitted = reduced @ ols_coefficients(reduced, y)
    residual = y - fitted
    null = np.empty(n_permutations)
    for i in range(n_permutations):
        null[i] = ols_coefficients(full, fitted + residual[rng.permutation(y.size)])[
            coefficient
        ]
    p = float((1 + np.sum(np.abs(null) >= abs(observed))) / (n_permutations + 1))
    return observed, p, null


@dataclass(frozen=True)
class ModerationResult:
    """Rank-scale slopes, interaction and participant bootstrap distributions."""

    interaction: float
    slope_a: float
    slope_b: float
    pvalue: float
    permutation_null: np.ndarray
    bootstrap_interaction: np.ndarray
    bootstrap_slope_a: np.ndarray
    bootstrap_slope_b: np.ndarray
    bootstrap_valid_count: int
    bootstrap_valid_fraction: float


def rank_moderation(
    dose_a: np.ndarray,
    response_a: np.ndarray,
    dose_b: np.ndarray,
    response_b: np.ndarray,
    *,
    n_permutations: int = 10000,
    n_bootstrap: int = 5000,
    rng: np.random.Generator | None = None,
    seed: int = 42,
    singular_bootstrap: str = "discard",
) -> ModerationResult:
    """Pooled-rank dose × group model with group-stratified subject bootstrap.

    Group A is coded one, B zero. Finite dose/outcome pairs are retained within
    each group; all quantities are reranked after each bootstrap resample.
    Singular bootstrap designs return NaN coefficients by default. The returned
    count/fraction records identifiable draws; intervals should report this
    coverage. ``singular_bootstrap="legacy"`` reproduces historical least-squares
    coefficients even for singular draws, while still reporting their count.
    """
    if singular_bootstrap not in ("discard", "legacy"):
        raise ValueError("singular_bootstrap must be discard or legacy")
    a, ya, b, yb = map(
        lambda v: np.asarray(v, float), (dose_a, response_a, dose_b, response_b)
    )
    if a.ndim != 1 or b.ndim != 1 or ya.shape != a.shape or yb.shape != b.shape:
        raise ValueError("one response per dose is required")
    va, vb = np.isfinite(a) & np.isfinite(ya), np.isfinite(b) & np.isfinite(yb)
    a, ya, b, yb = a[va], ya[va], b[vb], yb[vb]
    if min(a.size, b.size) < 2 or n_bootstrap < 1:
        raise ValueError(
            "at least two participants per group and a positive bootstrap count are required"
        )
    rng = np.random.default_rng(seed) if rng is None else rng
    group = np.concatenate([np.ones(a.size), np.zeros(b.size)])
    rx = stats.rankdata(np.concatenate([a, b]))
    rx -= rx.mean()
    ry = stats.rankdata(np.concatenate([ya, yb]))
    full, red = moderation_design(rx, group), moderation_design(rx, group, full=False)
    beta = ols_coefficients(full, ry)
    interaction, p, null = freedman_lane(
        ry, full, red, coefficient=3, n_permutations=n_permutations, rng=rng
    )
    bi, ba, bb = (
        np.full(n_bootstrap, np.nan),
        np.full(n_bootstrap, np.nan),
        np.full(n_bootstrap, np.nan),
    )
    valid_count = 0
    for j in range(n_bootstrap):
        ia, ib = rng.integers(0, a.size, a.size), rng.integers(0, b.size, b.size)
        rx = stats.rankdata(np.concatenate([a[ia], b[ib]]))
        rx -= rx.mean()
        draw_design = moderation_design(rx, group)
        identifiable = np.linalg.matrix_rank(draw_design) == draw_design.shape[1]
        valid_count += int(identifiable)
        if not identifiable and singular_bootstrap == "discard":
            continue
        beta_draw = ols_coefficients(
            draw_design,
            stats.rankdata(np.concatenate([ya[ia], yb[ib]])),
        )
        bi[j], ba[j], bb[j] = beta_draw[3], beta_draw[1] + beta_draw[3], beta_draw[1]
    return ModerationResult(
        interaction,
        float(beta[1] + beta[3]),
        float(beta[1]),
        p,
        null,
        bi,
        ba,
        bb,
        valid_count,
        valid_count / n_bootstrap,
    )


def bh_fdr_propagate(pvalues: np.ndarray) -> np.ndarray:
    """Published per-parcel compatibility: NaNs propagate through BH sorting.

    Prefer ``bh_fdr`` with a deliberate finite-value family for new analyses.
    This exact legacy rule is separate so untestable parcels cannot silently
    change the size of a published family during migration.
    """
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1:
        raise ValueError("supply a one-dimensional family")
    n = p.size
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(q, 0, 1)
    return out

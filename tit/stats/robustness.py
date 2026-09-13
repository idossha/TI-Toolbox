"""Participant influence diagnostics; selected-region sensitivity is not validation."""

from __future__ import annotations
from collections.abc import Callable
import numpy as np
from .effects import rank_biserial

MODIFIED_Z_OUTLIER = 3.5


def modified_zscores(values: np.ndarray) -> np.ndarray:
    """Median/MAD modified z-scores; falls back to mean/SD when MAD is zero."""
    v = np.asarray(values, dtype=float)
    median = np.nanmedian(v)
    mad = np.nanmedian(np.abs(v - median))
    if mad > 0:
        return 0.6745 * (v - median) / mad
    sd = np.nanstd(v)
    if sd > 0:
        return (v - np.nanmean(v)) / sd
    return np.zeros_like(v)


def describe(values: np.ndarray) -> dict[str, float]:
    """Summary statistics for inter-individual variability."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {}
    q1, q3 = np.percentile(v, [25, 75])
    mean = float(v.mean())
    sd = float(v.std(ddof=1)) if v.size > 1 else float("nan")
    return {
        "n": int(v.size),
        "mean": mean,
        "sd": sd,
        "cv": float(sd / mean) if mean != 0 else float("nan"),
        "median": float(np.median(v)),
        "iqr": float(q3 - q1),
        "min": float(v.min()),
        "max": float(v.max()),
    }


def loso_subject_effects(values: np.ndarray, ids: list[str]) -> list[dict[str, object]]:
    """Drop each subject in turn and recompute the cluster effect.

    Returns one row per subject with the recomputed rank-biserial r and cluster
    mean, plus the change relative to the full-sample effect. A result robust to
    inter-individual variability shows small ``delta_r`` for every subject.
    """
    v = np.asarray(values, dtype=float)
    n = v.size
    full_r = rank_biserial(v)
    full_mean = float(np.nanmean(v))
    z = modified_zscores(v)
    rows: list[dict[str, object]] = []
    for i in range(n):
        keep = np.delete(v, i)
        loso_r = rank_biserial(keep)
        loso_mean = float(np.nanmean(keep))
        rows.append(
            {
                "dropped_subject": ids[i],
                "subject_value": float(v[i]),
                "modified_z": float(z[i]),
                "is_outlier": bool(abs(z[i]) > MODIFIED_Z_OUTLIER),
                "loso_rank_biserial_r": loso_r,
                "loso_mean_change": loso_mean,
                "delta_r": (
                    float(loso_r - full_r)
                    if np.isfinite(loso_r) and np.isfinite(full_r)
                    else float("nan")
                ),
                "delta_mean": float(loso_mean - full_mean),
            }
        )
    return rows


def loso_summary(
    rows: list[dict[str, object]], full_r: float, full_mean: float
) -> dict[str, object]:
    """Collapse per-subject LOSO rows into a one-line robustness verdict."""
    loso_r = np.array([r["loso_rank_biserial_r"] for r in rows], dtype=float)
    loso_m = np.array([r["loso_mean_change"] for r in rows], dtype=float)
    deltas = np.abs([r["delta_r"] for r in rows])
    worst = int(np.nanargmax(deltas)) if np.isfinite(deltas).any() else -1
    return {
        "full_rank_biserial_r": full_r,
        "full_mean_change": full_mean,
        "loso_r_min": float(np.nanmin(loso_r)),
        "loso_r_max": float(np.nanmax(loso_r)),
        "loso_mean_min": float(np.nanmin(loso_m)),
        "loso_mean_max": float(np.nanmax(loso_m)),
        "max_abs_delta_r": (
            float(np.nanmax(deltas)) if np.isfinite(deltas).any() else float("nan")
        ),
        "most_influential_subject": (
            rows[worst]["dropped_subject"] if worst >= 0 else ""
        ),
        "n_outliers": int(sum(1 for r in rows if r["is_outlier"])),
    }


def leave_one_out(
    data: np.ndarray,
    statistic: Callable[[np.ndarray], float],
    *,
    subject_ids: list[str] | None = None,
) -> list[dict]:
    """Recompute a scalar callback after omitting each participant row.

    A callback can recompute a fixed-ROI effect or run a complete estimator.
    Those are different procedures; callers must label them explicitly.
    """
    data = np.asarray(data)
    if data.ndim < 1 or data.shape[0] < 3:
        raise ValueError("at least three participant rows are required")
    ids = [str(i) for i in range(len(data))] if subject_ids is None else subject_ids
    if len(ids) != len(data) or len(set(ids)) != len(ids):
        raise ValueError("one unique subject ID is required per row")
    full = float(statistic(data))
    return [
        dict(
            dropped_subject=ids[i],
            estimate=float(statistic(np.delete(data, i, axis=0))),
            full_estimate=full,
        )
        for i in range(len(data))
    ]

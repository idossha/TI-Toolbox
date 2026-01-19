"""
Responder ML plotting utilities.

Keep imports lazy to avoid hard dependency on matplotlib/nilearn.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

from ._common import ensure_headless_matplotlib_backend, savefig_close


def _read_csv_as_rows(csv_path: Path) -> List[Dict[str, str]]:
    import csv

    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def _as_float(s: str | None) -> float | None:
    if s is None:
        return None
    ss = str(s).strip()
    if ss == "":
        return None
    try:
        return float(ss)
    except ValueError:
        return None


def _as_int(s: str | None) -> int | None:
    v = _as_float(s)
    if v is None:
        return None
    return int(v)


def plot_top_coefficients(
    *,
    parsed: Sequence[Tuple[int, str, float]],
    label_map: Dict[int, str],
    out_path: Path,
    top_k: int = 20,
    title: str = "Top coefficients",
) -> Path:
    """
    Plot top +/- coefficients as a horizontal bar chart.
    """
    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt  # type: ignore

    entries: List[Tuple[str, float]] = []
    for roi_id, stat, w in parsed:
        roi_name = label_map.get(roi_id, f"ROI_{roi_id}")
        entries.append((f"{roi_name}__{stat}", float(w)))
    if not entries:
        raise RuntimeError("No coefficients to plot")

    entries_sorted = sorted(entries, key=lambda t: t[1])
    neg = entries_sorted[: max(1, top_k // 2)]
    pos = entries_sorted[-max(1, top_k // 2) :]
    selected = neg + pos

    labels = [n for n, _w in selected]
    weights = np.asarray([w for _n, w in selected], dtype=float)
    colors = ["#d62728" if w > 0 else "#1f77b4" for w in weights]

    fig_h = max(4.0, 0.22 * len(labels) + 1.5)
    fig, ax = plt.subplots(figsize=(12, fig_h), dpi=150)
    y = np.arange(len(labels))
    ax.barh(y, weights, color=colors, alpha=0.9)
    ax.axvline(0.0, color="black", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Coefficient (from standardized features)")
    ax.set_title(title)
    fig.tight_layout()
    savefig_close(fig, str(out_path))
    return out_path


def plot_model_diagnostics_from_predictions_csv(
    *, predictions_csv: Path, out_path: Path
) -> Path:
    """
    Create a multi-panel "industry standard" diagnostics figure.
    """
    rows = _read_csv_as_rows(predictions_csv)
    if not rows:
        raise RuntimeError(f"Empty predictions CSV: {predictions_csv}")

    cols = set(rows[0].keys())
    if "proba" not in cols and "prediction" not in cols:
        raise RuntimeError(
            "Unrecognized predictions CSV format "
            f"(expected 'proba' or 'prediction' column): {sorted(cols)}"
        )

    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt  # type: ignore

    if "proba" in cols:
        from sklearn.calibration import calibration_curve  # type: ignore
        from sklearn.metrics import (  # type: ignore
            ConfusionMatrixDisplay,
            average_precision_score,
            confusion_matrix,
            precision_recall_curve,
            roc_auc_score,
            roc_curve,
        )
    else:
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score  # type: ignore

    target_col = (
        "response"
        if "response" in cols
        else next(
            (
                c
                for c in cols
                if c not in {"subject_id", "simulation_name", "proba", "prediction"}
            ),
            None,
        )
    )
    if not target_col:
        raise RuntimeError("Could not infer target column in predictions CSV")

    if "proba" in cols:
        y: List[int] = []
        p: List[float] = []
        for r in rows:
            yy = _as_int(r.get(target_col))
            pp = _as_float(r.get("proba"))
            if yy is None or pp is None:
                continue
            y.append(int(yy))
            p.append(float(pp))
        if len(y) < 2:
            raise RuntimeError("Not enough labeled prediction rows to plot diagnostics")

        y_arr = np.asarray(y, dtype=int)
        p_arr = np.asarray(p, dtype=float)

        fpr, tpr, _ = roc_curve(y_arr, p_arr)
        roc_auc = roc_auc_score(y_arr, p_arr)
        prec, rec, _ = precision_recall_curve(y_arr, p_arr)
        ap = average_precision_score(y_arr, p_arr)
        frac_pos, mean_pred = calibration_curve(
            y_arr, p_arr, n_bins=10, strategy="quantile"
        )

        thresholds = np.unique(np.clip(p_arr, 0.0, 1.0))
        best_thr = 0.5
        best_f1 = -1.0
        for thr in thresholds:
            y_hat = (p_arr >= thr).astype(int)
            tp = int(((y_hat == 1) & (y_arr == 1)).sum())
            fp = int(((y_hat == 1) & (y_arr == 0)).sum())
            fn = int(((y_hat == 0) & (y_arr == 1)).sum())
            denom = 2 * tp + fp + fn
            f1 = (2 * tp / denom) if denom > 0 else 0.0
            if f1 > best_f1:
                best_f1 = f1
                best_thr = float(thr)

        cm = confusion_matrix(y_arr, (p_arr >= best_thr).astype(int), labels=[0, 1])

        fig, axes = plt.subplots(2, 2, figsize=(12, 10), dpi=150)
        ax_roc, ax_pr, ax_cal, ax_cm = axes.ravel()

        ax_roc.plot(fpr, tpr, color="#1f77b4", linewidth=2)
        ax_roc.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1)
        ax_roc.set_xlabel("False Positive Rate")
        ax_roc.set_ylabel("True Positive Rate")
        ax_roc.set_title(f"ROC (AUC={roc_auc:.3f})")
        ax_roc.grid(True, alpha=0.2)

        ax_pr.plot(rec, prec, color="#ff7f0e", linewidth=2)
        ax_pr.set_xlabel("Recall")
        ax_pr.set_ylabel("Precision")
        ax_pr.set_title(f"Precision-Recall (AP={ap:.3f})")
        ax_pr.grid(True, alpha=0.2)

        ax_cal.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1)
        ax_cal.plot(mean_pred, frac_pos, marker="o", linewidth=2, color="#2ca02c")
        ax_cal.set_xlabel("Mean predicted probability")
        ax_cal.set_ylabel("Fraction of positives")
        ax_cal.set_title("Calibration (reliability diagram)")
        ax_cal.grid(True, alpha=0.2)

        disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=[0, 1])
        disp.plot(ax=ax_cm, cmap="Blues", colorbar=False, values_format="d")
        ax_cm.set_title(f"Confusion (thr={best_thr:.3f}, best F1={best_f1:.3f})")

        fig.suptitle("Model diagnostics (CV predictions)", y=0.99)
        fig.tight_layout()
        savefig_close(fig, str(out_path))
        return out_path

    y = []
    p = []
    for r in rows:
        yy = _as_float(r.get(target_col))
        pp = _as_float(r.get("prediction"))
        if yy is None or pp is None:
            continue
        y.append(float(yy))
        p.append(float(pp))
    if len(y) < 2:
        raise RuntimeError("Not enough labeled prediction rows to plot diagnostics")

    y_arr = np.asarray(y, dtype=float)
    p_arr = np.asarray(p, dtype=float)

    r2 = r2_score(y_arr, p_arr)
    rmse = mean_squared_error(y_arr, p_arr) ** 0.5
    mae = mean_absolute_error(y_arr, p_arr)
    residuals = y_arr - p_arr

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), dpi=150)
    ax_scatter, ax_resid, ax_resid_pred, ax_qq = axes.ravel()

    ax_scatter.scatter(y_arr, p_arr, alpha=0.7, edgecolors="none")
    lo = min(y_arr.min(), p_arr.min())
    hi = max(y_arr.max(), p_arr.max())
    ax_scatter.plot([lo, hi], [lo, hi], linestyle="--", color="gray", linewidth=1)
    ax_scatter.set_xlabel("Actual")
    ax_scatter.set_ylabel("Predicted")
    ax_scatter.set_title(f"Predicted vs actual (R2={r2:.3f})")
    ax_scatter.grid(True, alpha=0.2)

    ax_resid.hist(residuals, bins=20, color="#1f77b4", alpha=0.8)
    ax_resid.set_xlabel("Residual (actual - predicted)")
    ax_resid.set_ylabel("Count")
    ax_resid.set_title(f"Residuals (RMSE={rmse:.3f}, MAE={mae:.3f})")
    ax_resid.grid(True, alpha=0.2)

    ax_resid_pred.scatter(p_arr, residuals, alpha=0.7, edgecolors="none")
    ax_resid_pred.axhline(0.0, color="gray", linestyle="--", linewidth=1)
    ax_resid_pred.set_xlabel("Predicted")
    ax_resid_pred.set_ylabel("Residual")
    ax_resid_pred.set_title("Residuals vs predicted")
    ax_resid_pred.grid(True, alpha=0.2)

    try:
        from scipy import stats  # type: ignore

        stats.probplot(residuals, dist="norm", plot=ax_qq)
        ax_qq.set_title("Residuals QQ plot")
    except Exception:
        ax_qq.axis("off")
        ax_qq.text(
            0.5,
            0.5,
            "QQ plot unavailable\n(scientific stack missing)",
            ha="center",
            va="center",
        )

    fig.suptitle("Model diagnostics (CV predictions)", y=0.99)
    fig.tight_layout()
    savefig_close(fig, str(out_path))
    return out_path


def create_weight_map_visualizations(
    *, weight_map: Path, out_dir: Path, title: str
) -> List[Path]:
    """
    Create glass brain PNG + interactive HTML for a weight map.
    """
    import nibabel as nib  # type: ignore
    from nilearn import plotting  # type: ignore

    out_dir.mkdir(parents=True, exist_ok=True)
    img = nib.load(str(weight_map))

    name = weight_map.name
    base = name[: -len(".nii.gz")] if name.lower().endswith(".nii.gz") else weight_map.stem
    html_path = out_dir / f"{base}.html"
    glass_png = out_dir / f"{base}_glass_brain.png"

    glass = plotting.plot_glass_brain(
        img,
        title=f"{title} (glass brain)",
        display_mode="lyrz",
        colorbar=True,
        black_bg=True,
    )
    glass.savefig(str(glass_png))
    glass.close()

    view = plotting.view_img(img, title=title, colorbar=True, black_bg=True)
    view.save_as_html(str(html_path))

    return [glass_png, html_path]


def plot_intensity_response_fig5(
    *,
    voxel_values_responder: np.ndarray,
    voxel_values_non_responder: np.ndarray,
    subj_median_intensity: np.ndarray,
    subj_behavior: np.ndarray,
    subj_label: np.ndarray,
    out_path: Path,
    title: str,
    bin_width: float | None = None,
    bootstrap_samples: int = 5000,
    random_state: int = 42,
) -> Path:
    """
    Generate an Albizu-style Fig 5 relating intensity to response:
    A) normalized histogram (probability mass; bar heights sum to 1)
    B) cumulative histogram (CDF)
    C) scatter: behavior vs median intensity
    D) Gardner-Altman estimation plot + Hedges' g (responders vs non-responders)

    Notes:
    - Histograms are computed from per-voxel values within selected ROIs/voxels.
    - Median intensity is computed per subject from the same voxel set.
    """
    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt  # type: ignore

    v_r = np.asarray(voxel_values_responder, dtype=float).ravel()
    v_n = np.asarray(voxel_values_non_responder, dtype=float).ravel()
    v_r = v_r[np.isfinite(v_r)]
    v_n = v_n[np.isfinite(v_n)]

    x_med = np.asarray(subj_median_intensity, dtype=float).ravel()
    y_beh = np.asarray(subj_behavior, dtype=float).ravel()
    y_lab = np.asarray(subj_label, dtype=int).ravel()

    if x_med.shape != y_beh.shape or x_med.shape != y_lab.shape:
        raise ValueError("Subject arrays must have the same length")

    # Determine histogram bins.
    all_v = (
        np.concatenate([v_r, v_n], axis=0)
        if (v_r.size and v_n.size)
        else (v_r if v_r.size else v_n)
    )
    if all_v.size == 0:
        raise ValueError("No voxel values provided for histogram/CDF plotting")
    vmin = float(np.nanmin(all_v))
    vmax = float(np.nanmax(all_v))
    if vmin == vmax:
        vmax = vmin + 1e-9

    if bin_width is not None and float(bin_width) > 0:
        bw = float(bin_width)
        edges = np.arange(vmin, vmax + bw, bw, dtype=float)
        if edges.size < 5:
            edges = np.linspace(vmin, vmax, num=21, dtype=float)
    else:
        # Freedman–Diaconis as a sensible default; fallback to 30 bins.
        q25, q75 = np.percentile(all_v, [25.0, 75.0])
        iqr = float(q75 - q25)
        if iqr > 0 and all_v.size >= 2:
            bw = 2.0 * iqr / (all_v.size ** (1.0 / 3.0))
            if bw > 0:
                edges = np.arange(vmin, vmax + bw, bw, dtype=float)
            else:
                edges = np.linspace(vmin, vmax, num=31, dtype=float)
        else:
            edges = np.linspace(vmin, vmax, num=31, dtype=float)

    # Histogram probability mass (counts / total), and CDF.
    def _prob_mass(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        counts, _ = np.histogram(values, bins=edges)
        total = float(counts.sum())
        if total <= 0:
            pm = np.zeros_like(counts, dtype=float)
        else:
            pm = counts.astype(float) / total
        cdf = np.cumsum(pm)
        return pm, cdf

    pm_r, cdf_r = _prob_mass(v_r)
    pm_n, cdf_n = _prob_mass(v_n)
    centers = 0.5 * (edges[:-1] + edges[1:])

    # Hedges' g for median intensity between groups.
    grp_r = x_med[y_lab == 1]
    grp_n = x_med[y_lab == 0]
    grp_r = grp_r[np.isfinite(grp_r)]
    grp_n = grp_n[np.isfinite(grp_n)]
    if grp_r.size < 2 or grp_n.size < 2:
        raise ValueError("Need at least 2 subjects per group for estimation plot")

    m_r = float(np.mean(grp_r))
    m_n = float(np.mean(grp_n))
    s_r = float(np.std(grp_r, ddof=1))
    s_n = float(np.std(grp_n, ddof=1))
    n_r = int(grp_r.size)
    n_n = int(grp_n.size)
    sp = np.sqrt(((n_r - 1) * s_r**2 + (n_n - 1) * s_n**2) / (n_r + n_n - 2))
    d = (m_r - m_n) / sp if sp > 0 else float("nan")
    J = 1.0 - (3.0 / (4.0 * (n_r + n_n) - 9.0))
    g = float(J * d) if np.isfinite(d) else float("nan")

    # Bootstrap mean difference (responders - non-responders).
    rng = np.random.default_rng(int(random_state))
    B = int(max(200, bootstrap_samples))
    diffs = np.zeros((B,), dtype=float)
    for i in range(B):
        br = rng.choice(grp_r, size=n_r, replace=True)
        bn = rng.choice(grp_n, size=n_n, replace=True)
        diffs[i] = float(np.mean(br) - np.mean(bn))
    diff_mean = float(np.mean(diffs))
    ci_lo, ci_hi = np.percentile(diffs, [2.5, 97.5]).tolist()

    # --- Plot ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), dpi=150)
    axA, axB, axC, axD = axes.ravel()

    # A) histogram (probability mass)
    axA.step(centers, pm_n, where="mid", color="#1f77b4", linewidth=2, label="Non-responder")
    axA.fill_between(centers, 0, pm_n, step="mid", color="#1f77b4", alpha=0.25)
    axA.step(centers, pm_r, where="mid", color="#d62728", linewidth=2, label="Responder")
    axA.fill_between(centers, 0, pm_r, step="mid", color="#d62728", alpha=0.25)
    axA.set_xlabel("Current intensity (a.u.)")
    axA.set_ylabel("Probability mass")
    axA.set_title("A) Intensity histogram (normalized)")
    axA.grid(True, alpha=0.2)
    axA.legend(frameon=False, fontsize=9)

    # B) cumulative histogram (CDF)
    axB.step(centers, cdf_n, where="mid", color="#1f77b4", linewidth=2, label="Non-responder")
    axB.step(centers, cdf_r, where="mid", color="#d62728", linewidth=2, label="Responder")
    axB.set_xlabel("Current intensity (a.u.)")
    axB.set_ylabel("Cumulative probability")
    axB.set_title("B) CDF of intensity")
    axB.set_ylim(-0.02, 1.02)
    axB.grid(True, alpha=0.2)
    axB.legend(frameon=False, fontsize=9)

    # C) scatter: behavior vs median intensity
    mask0 = y_lab == 0
    mask1 = y_lab == 1
    axC.scatter(
        x_med[mask0],
        y_beh[mask0],
        s=40,
        alpha=0.85,
        color="#1f77b4",
        edgecolors="none",
        label="Non-responder",
    )
    axC.scatter(
        x_med[mask1],
        y_beh[mask1],
        s=40,
        alpha=0.85,
        color="#d62728",
        edgecolors="none",
        label="Responder",
    )
    axC.set_xlabel("Median intensity (per subject)")
    axC.set_ylabel("Behavior / target")
    axC.set_title("C) Behavior vs median intensity")
    axC.grid(True, alpha=0.2)
    axC.legend(frameon=False, fontsize=9)

    # D) Gardner–Altman estimation plot (median intensity)
    # Left: raw group points
    x0 = np.zeros_like(grp_n) + 0.0
    x1 = np.zeros_like(grp_r) + 1.0
    jitter0 = rng.normal(0, 0.04, size=grp_n.size)
    jitter1 = rng.normal(0, 0.04, size=grp_r.size)
    axD.scatter(x0 + jitter0, grp_n, color="#1f77b4", alpha=0.85, edgecolors="none")
    axD.scatter(x1 + jitter1, grp_r, color="#d62728", alpha=0.85, edgecolors="none")
    axD.hlines(np.mean(grp_n), -0.2, 0.2, color="#1f77b4", linewidth=3)
    axD.hlines(np.mean(grp_r), 0.8, 1.2, color="#d62728", linewidth=3)
    axD.set_xticks([0.0, 1.0])
    axD.set_xticklabels(["Non", "Resp"])
    axD.set_ylabel("Median intensity")
    axD.set_title(f"D) Estimation (Δ mean={diff_mean:.3g} [{ci_lo:.3g},{ci_hi:.3g}], Hedges g={g:.3g})")
    axD.grid(True, axis="y", alpha=0.2)

    # Inset: bootstrap distribution of mean difference
    inset = axD.inset_axes([0.55, 0.12, 0.42, 0.80])
    inset.hist(diffs, bins=30, color="gray", alpha=0.65, density=False)
    inset.axvline(diff_mean, color="black", linewidth=2)
    inset.axvline(ci_lo, color="black", linewidth=1, linestyle="--")
    inset.axvline(ci_hi, color="black", linewidth=1, linestyle="--")
    inset.set_yticks([])
    inset.set_xlabel("Δ mean (Resp - Non)")
    inset.set_title("Bootstrap Δ mean", fontsize=9)

    fig.suptitle(title, y=0.99)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    savefig_close(fig, str(out_path))
    return out_path

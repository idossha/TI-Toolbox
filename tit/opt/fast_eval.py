"""High-performance leadfield-based TI field evaluator.

Pre-resolves electrode indices and pre-normalizes ROI weights so the
hot path is pure numpy with no string lookups or SimNIBS wrapper overhead.

The evaluator operates on the **full** leadfield — focality is always
computed as ROI / rest-of-brain with no element subsetting.
"""

import logging

import numpy as np

from tit.calc import get_nTI_vectors

log = logging.getLogger(__name__)


def _fast_ti_magnitude(E1: np.ndarray, E2: np.ndarray) -> np.ndarray:
    """Compute TI modulation magnitude (Grossman 2017) without array copies.

    Equivalent to ``np.linalg.norm(get_TI_vectors(E1, E2), axis=1)`` but
    avoids intermediate (N, 3) vector allocation — returns scalar (N,) directly.

    Parameters
    ----------
    E1, E2 : (N, 3) arrays
        E-field vectors from two electrode pairs.

    Returns
    -------
    ti_mag : (N,) array
        TI modulation magnitude at each element.
    """
    n1 = np.linalg.norm(E1, axis=1)
    n2 = np.linalg.norm(E2, axis=1)

    # Ensure |E1| >= |E2|
    swap = n2 > n1
    if np.any(swap):
        E1, E2 = E1.copy(), E2.copy()
        E1[swap], E2[swap] = E2[swap], E1[swap]
        n1[swap], n2[swap] = n2[swap], n1[swap]

    # Ensure acute angle
    dot = np.einsum("ij,ij->i", E1, E2)
    flip = dot < 0
    if np.any(flip):
        if not E2.flags.owndata:
            E2 = E2.copy()
        E2[flip] = -E2[flip]
        dot[flip] = -dot[flip]

    # Cosine of angle between E1 and E2
    denom = n1 * n2
    denom[denom == 0] = 1.0
    cos_alpha = np.clip(dot / denom, -1.0, 1.0)

    # Regime 1: |E2| <= |E1| cos(alpha) → TI_mag = 2 * |E2|
    regime1 = n2 <= n1 * cos_alpha
    ti_mag = np.empty(len(E1), dtype=E1.dtype)
    ti_mag[regime1] = 2.0 * n2[regime1]

    # Regime 2: cross-product formula
    regime2 = ~regime1
    if np.any(regime2):
        h = E1[regime2] - E2[regime2]
        h_norm = np.linalg.norm(h, axis=1)
        h_norm[h_norm == 0] = 1.0
        cross_mag = np.linalg.norm(np.cross(E2[regime2], h), axis=1)
        ti_mag[regime2] = 2.0 * cross_mag / h_norm

    return ti_mag


class FastTIEvaluator:
    """Leadfield evaluator for TI/mTI field computation.

    Operates on the **full** leadfield matrix — no element subsetting.
    Focality = mean(ROI) / mean(rest-of-brain).

    Parameters
    ----------
    leadfield : (N_elec-1, M, 3) array
        Raw leadfield matrix from ``TI_utils.load_leadfield``.
    mesh : simnibs Msh
        Mesh from the same ``load_leadfield`` call.
    idx_lf : dict
        Electrode-name → leadfield-index mapping.
    """

    def __init__(self, leadfield: np.ndarray, mesh, idx_lf: dict):
        self.leadfield = leadfield
        self.mesh = mesh
        self.idx_lf = idx_lf

        # Pre-resolve electrode names → integer indices
        self.electrode_names: list[str] = []
        self.electrode_indices: dict[str, int | None] = {}
        for name, idx in idx_lf.items():
            self.electrode_names.append(name)
            self.electrode_indices[name] = idx

        # Populated by setup_evaluation()
        self.roi_indices: np.ndarray | None = None
        self.nonroi_indices: np.ndarray | None = None
        self.roi_weights: np.ndarray | None = None
        self.nonroi_weights: np.ndarray | None = None

    def setup_evaluation(
        self,
        roi_indices: np.ndarray,
        roi_volumes: np.ndarray,
        nonroi_indices: np.ndarray,
        nonroi_volumes: np.ndarray,
    ) -> None:
        """Store ROI / non-ROI indices and pre-normalize weights.

        Parameters
        ----------
        roi_indices, roi_volumes : arrays
            Target ROI elements and their volumes (for weighted mean).
        nonroi_indices, nonroi_volumes : arrays
            Non-ROI elements and volumes (denominator of focality).
        """
        self.roi_indices = roi_indices
        self.nonroi_indices = nonroi_indices

        self.roi_weights = (
            roi_volumes / roi_volumes.sum() if len(roi_volumes) else roi_volumes
        )
        self.nonroi_weights = (
            nonroi_volumes / nonroi_volumes.sum()
            if len(nonroi_volumes)
            else nonroi_volumes
        )

        log.info(
            f"FastTIEvaluator: M={self.leadfield.shape[1]} elements, "
            f"ROI={len(roi_indices)}, nonROI={len(nonroi_indices)}"
        )

    def resolve_electrode(self, name: str) -> int | None:
        """Electrode name → leadfield row index."""
        return self.electrode_indices[name]

    def pair_field(self, idx_plus: int, idx_minus: int, current_A: float) -> np.ndarray:
        """E-field for one bipolar pair on the full mesh.

        Returns
        -------
        E : (M, 3) array
        """
        lf = self.leadfield
        if idx_plus is None:
            return -current_A * lf[idx_minus]
        if idx_minus is None:
            return current_A * lf[idx_plus]
        return current_A * (lf[idx_plus] - lf[idx_minus])

    def precompute_pair_diffs(
        self, pairs: list[tuple[int | None, int | None]]
    ) -> list[np.ndarray]:
        """Pre-compute ``lf[plus] - lf[minus]`` for fixed electrode pairs.

        Used by the inner current optimizer where electrodes are fixed
        and only currents vary.

        Returns
        -------
        diffs : list of (M, 3) arrays
        """
        diffs = []
        lf = self.leadfield
        for plus_idx, minus_idx in pairs:
            if plus_idx is None:
                diffs.append(-lf[minus_idx].copy())
            elif minus_idx is None:
                diffs.append(lf[plus_idx].copy())
            else:
                diffs.append(lf[plus_idx] - lf[minus_idx])
        return diffs

    def evaluate_montage_npair(
        self,
        pair_diffs: list[np.ndarray],
        currents_A: list[float],
    ) -> dict[str, float]:
        """Evaluate an N-pair mTI montage from pre-computed pair diffs.

        Returns
        -------
        metrics : dict with roi_mean, nonroi_mean, focality, roi_max
        """
        e_fields = [I * diff for I, diff in zip(currents_A, pair_diffs)]

        if len(e_fields) == 2:
            ti_mag = _fast_ti_magnitude(e_fields[0], e_fields[1])
        else:
            ti_vectors = get_nTI_vectors(e_fields)
            ti_mag = np.linalg.norm(ti_vectors, axis=1)

        return self._compute_metrics(ti_mag)

    def focality_from_diffs(
        self,
        pair_diffs: list[np.ndarray],
        currents_A: np.ndarray,
    ) -> float:
        """Fast focality-only computation for the inner optimizer."""
        e_fields = [c * d for c, d in zip(currents_A, pair_diffs)]

        if len(e_fields) == 2:
            ti_mag = _fast_ti_magnitude(e_fields[0], e_fields[1])
        else:
            ti_vectors = get_nTI_vectors(e_fields)
            ti_mag = np.linalg.norm(ti_vectors, axis=1)

        roi_mean = ti_mag[self.roi_indices] @ self.roi_weights
        nonroi_mean = ti_mag[self.nonroi_indices] @ self.nonroi_weights
        if nonroi_mean <= 0:
            return 0.0
        return roi_mean / nonroi_mean

    def _compute_metrics(self, ti_mag: np.ndarray) -> dict[str, float]:
        """Compute ROI metrics from TI magnitude field on full mesh."""
        roi_field = ti_mag[self.roi_indices]
        nonroi_field = ti_mag[self.nonroi_indices]

        if len(roi_field) == 0:
            return {
                "roi_mean": 0.0,
                "nonroi_mean": 0.0,
                "focality": 0.0,
                "roi_max": 0.0,
            }

        roi_mean = float(roi_field @ self.roi_weights)
        roi_max = float(roi_field.max())

        if len(nonroi_field) == 0:
            return {
                "roi_mean": roi_mean,
                "nonroi_mean": 0.0,
                "focality": 0.0,
                "roi_max": roi_max,
            }

        nonroi_mean = float(nonroi_field @ self.nonroi_weights)
        focality = roi_mean / nonroi_mean if nonroi_mean > 0 else 0.0

        return {
            "roi_mean": roi_mean,
            "nonroi_mean": nonroi_mean,
            "focality": focality,
            "roi_max": roi_max,
        }

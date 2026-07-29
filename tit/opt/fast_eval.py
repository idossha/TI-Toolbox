"""High-performance leadfield-based TI field evaluator.

Pre-resolves electrode indices and pre-normalizes ROI weights so the
hot path is pure numpy with no string lookups or SimNIBS wrapper overhead.

The evaluator's *final* API (:meth:`FastTIEvaluator.evaluate_montage_npair`,
:meth:`FastTIEvaluator.evaluate_final`) always operates on the **full**
leadfield -- focality is computed as ROI / rest-of-brain with no element
subsetting, so those numbers are exact.

The *search* API (:meth:`FastTIEvaluator.focality_from_diffs`, the DE inner
loop's objective) can instead operate on a fixed, deterministic subsample of
the non-ROI elements once :meth:`FastTIEvaluator.setup_search_subsample` has
been called -- see ``tracks/active/mti-focality-core.md`` finding F10.
Computing the (expensive) N>2 modulation-depth envelope over the full
~1e5-element grey-matter mesh at every DE evaluation made the correct field
model 44x slower than the wrong-but-fast legacy metric it replaces (11 hours
for a 15k-evaluation run). The DE objective only ever needs ``roi_mean`` and
``nonroi_mean``, both weighted means, so restricting the (expensive)
per-element envelope computation to ROI (kept whole -- it is small) plus a
representative non-ROI subsample recovers correct-metric search speed
without changing what the optimizer is actually trying to estimate.
"""

import logging

import numpy as np

from tit.calc import get_nTI_vectors, mti_modulation_depth

log = logging.getLogger(__name__)

# ── N>2 envelope metric selection (finding F1) ────────────────────────────
#
# METRIC_MTI_MODULATION_DEPTH: the verified Botzanowski-derived closed form
# (tit.calc.mti_modulation_depth) -- the default, correct choice.
# METRIC_LEGACY_RECURSIVE_TI: tit.calc.get_nTI_vectors, the unvalidated
# recursive binary-tree pairing this replaces (measured -13%/+12% error at
# N=4 against time-domain ground truth). Kept reachable only so the two can
# be compared on identical montages -- not recommended for new code.
METRIC_MTI_MODULATION_DEPTH = "mti_modulation_depth"
METRIC_LEGACY_RECURSIVE_TI = "recursive_ti"

# ── N>2 electrode-pair grouping scheme (finding F11) ──────────────────────
#
# SCHEME_MULTIBAND: Botzanowski Type-2 -- adjacent electrode pairs (ep1,ep2),
# (ep3,ep4), ... each form one interference pair on its own carrier band,
# giving K = n_pairs // 2 interference pairs sharing one beat frequency.
# SCHEME_DUAL_CARRIER: Lee-2022 Type-1 -- all even-indexed electrode pairs
# (0, 2, 4, ...) share one carrier and superpose into a single aggregate
# field; all odd-indexed pairs (1, 3, 5, ...) share the other carrier and
# superpose into the second aggregate field, giving K = 1 regardless of
# n_pairs. Different physics, different optima (Botzanowski: Type-1 does not
# improve focality at all).
SCHEME_MULTIBAND = "multiband"
SCHEME_DUAL_CARRIER = "dual_carrier"


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


def _group_fields_for_scheme(
    e_fields: list[np.ndarray], scheme: str
) -> list[np.ndarray]:
    """Group per-electrode-pair fields into interference-pair sub-channels.

    ``e_fields`` is ordered ``[E_pair1, E_pair2, ..., E_pairN]`` -- one
    (N, 3) field per bipolar electrode pair, exactly what
    :meth:`FastTIEvaluator.precompute_pair_diffs` produces.

    Parameters
    ----------
    e_fields : list of (M, 3) arrays
        One field per electrode pair. Must have even length.
    scheme : {"multiband", "dual_carrier"}
        See module docstring / :data:`SCHEME_MULTIBAND` /
        :data:`SCHEME_DUAL_CARRIER`.

    Returns
    -------
    list of (M, 3) arrays
        For ``"multiband"``: ``e_fields`` unchanged (already the
        ``[E_1a, E_1b, E_2a, E_2b, ...]`` layout
        :func:`tit.calc.mti_modulation_depth` expects -- no reshaping
        needed). For ``"dual_carrier"``: exactly two arrays, the summed
        even- and odd-indexed fields.

    Raises
    ------
    ValueError
        If ``e_fields`` has odd length, or ``scheme`` is not recognized.
    """
    n = len(e_fields)
    if n % 2 != 0:
        raise ValueError(f"e_fields must have even length, got {n}")

    if scheme == SCHEME_MULTIBAND:
        return list(e_fields)

    if scheme == SCHEME_DUAL_CARRIER:
        e1 = np.sum(np.stack(e_fields[0::2], axis=0), axis=0)
        e2 = np.sum(np.stack(e_fields[1::2], axis=0), axis=0)
        return [e1, e2]

    raise ValueError(
        f"Unknown scheme {scheme!r}; expected {SCHEME_MULTIBAND!r} or "
        f"{SCHEME_DUAL_CARRIER!r}"
    )


def _ti_magnitude_npair(
    e_fields: list[np.ndarray],
    metric: str = METRIC_MTI_MODULATION_DEPTH,
    scheme: str = SCHEME_MULTIBAND,
    psi=None,
) -> np.ndarray:
    """Compute the N>2-pair TI envelope magnitude at every mesh element.

    Dispatches between the correct closed form (default) and the legacy
    unvalidated metric kept only for comparison (finding F1).

    Parameters
    ----------
    e_fields : list of (M, 3) arrays
        One field per electrode pair, ``len(e_fields) > 2``.
    metric : {"mti_modulation_depth", "recursive_ti"}
        ``"mti_modulation_depth"`` (default) routes through
        :func:`tit.calc.mti_modulation_depth` after grouping ``e_fields``
        per ``scheme``. ``"recursive_ti"`` calls the legacy
        :func:`tit.calc.get_nTI_vectors` directly on ``e_fields``
        (``scheme`` and ``psi`` are not meaningful for the legacy path and
        are ignored).
    scheme : {"multiband", "dual_carrier"}
        Electrode-pair grouping scheme (finding F11); ignored when
        ``metric="recursive_ti"``.
    psi : array-like or None
        Per-interference-pair envelope phase offset, forwarded to
        :func:`tit.calc.mti_modulation_depth` when ``metric`` is the
        default. Ignored when ``metric="recursive_ti"``.

    Returns
    -------
    (M,) array
    """
    if metric == METRIC_LEGACY_RECURSIVE_TI:
        ti_vectors = get_nTI_vectors(e_fields)
        return np.linalg.norm(ti_vectors, axis=1)

    if metric != METRIC_MTI_MODULATION_DEPTH:
        raise ValueError(
            f"Unknown metric {metric!r}; expected {METRIC_MTI_MODULATION_DEPTH!r} "
            f"or {METRIC_LEGACY_RECURSIVE_TI!r}"
        )

    grouped = _group_fields_for_scheme(e_fields, scheme)
    return mti_modulation_depth(grouped, psi=psi)["md"]


class FastTIEvaluator:
    """Leadfield evaluator for TI/mTI field computation.

    The *final* API (:meth:`evaluate_montage_npair`, :meth:`evaluate_final`)
    operates on the **full** leadfield matrix — no element subsetting.
    Focality = mean(ROI) / mean(rest-of-brain).

    The *search* API (:meth:`focality_from_diffs`) can operate on a fixed
    subsample of the non-ROI elements once :meth:`setup_search_subsample`
    has been called — see the module docstring and finding F10.

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

        # Populated by setup_search_subsample() -- None means "no
        # subsample configured", i.e. focality_from_diffs uses the full
        # non-ROI set.
        self.search_nonroi_indices: np.ndarray | None = None
        self.search_nonroi_weights: np.ndarray | None = None
        self._search_index: np.ndarray | None = None
        self._search_roi_pos: np.ndarray | None = None
        self._search_nonroi_pos: np.ndarray | None = None

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

        # Any previously configured search subsample was drawn against the
        # old non-ROI set; invalidate it so a stale subsample can't silently
        # survive a re-setup.
        self.search_nonroi_indices = None
        self.search_nonroi_weights = None
        self._search_index = None
        self._search_roi_pos = None
        self._search_nonroi_pos = None

        log.info(
            f"FastTIEvaluator: M={self.leadfield.shape[1]} elements, "
            f"ROI={len(roi_indices)}, nonROI={len(nonroi_indices)}"
        )

    def setup_search_subsample(
        self, n_nonroi_samples: int = 6000, seed: int = 0
    ) -> None:
        """Configure a fixed, deterministic non-ROI subsample for search.

        The DE objective (:meth:`focality_from_diffs`) only ever needs two
        volume-weighted means, ``roi_mean`` and ``nonroi_mean`` -- not the
        modulation-depth envelope on every one of the ~1e5 grey-matter
        elements the full leadfield carries. Computing that envelope is the
        expensive part of a search-time evaluation once the N>2 correct
        metric (finding F1) is in use (measured 44x slower than the
        wrong-but-fast legacy metric it replaces -- finding F10).

        ALL ROI elements are always kept (the ROI is small -- hundreds to
        low thousands of elements). Only the non-ROI side is subsampled:
        *n_nonroi_samples* elements are drawn **uniformly at random** (a
        fixed, seedable, deterministic simple random sample) from the
        non-ROI index set, and ``nonroi_mean`` is then computed as the
        volume-weighted mean of *that sample* using each sampled element's
        actual volume (renormalized to sum to 1 over the sample) -- the
        same weighting the full-mesh computation uses, just over fewer
        elements. This is a standard ratio-estimator for a weighted mean
        under simple random sampling: it is unbiased regardless of sample
        size and its variance shrinks as ``n_nonroi_samples`` grows. A
        sample in the low thousands estimates the true, full-mesh
        ``nonroi_mean`` far inside the 10-20% conductivity noise floor
        that already dominates the field model (see
        ``tracks/active/mti-focality-core.md`` finding F10) -- validated
        empirically to <1% relative error in ``focality`` against the full
        mesh across >=20 random montages
        (``tests/test_opt_mp.py::TestSearchSubsample``).

        After :meth:`setup_search_subsample` has been called,
        :meth:`focality_from_diffs` restricts the (expensive) envelope
        computation to ``roi_indices UNION nonroi_subsample`` instead of the
        full mesh. Call :meth:`evaluate_final` after the search completes to
        recompute exact numbers on the full mesh for the winning montage(s)
        -- search-time subsampling only ever affects search speed and
        ranking noise, never the final reported numbers.

        Must be called after :meth:`setup_evaluation` (which invalidates
        any existing subsample, since it depends on the non-ROI index set).
        Re-callable to change the sample size or reseed.

        Parameters
        ----------
        n_nonroi_samples : int, default 6000
            Number of non-ROI elements to sample. Clamped to the full
            non-ROI element count if larger (in which case subsampling is
            a no-op and every non-ROI element is used, same as not calling
            this method at all). 6000 was tuned empirically against a
            synthetic N=100,000-element benchmark: mean/worst-case
            relative error in ``focality`` of 0.33%/0.77% across 20 random
            4-pair montages (4000 measured 1.41% worst-case -- too high;
            see :class:`tit.opt.config.MultiPolarConfig`).
        seed : int, default 0
            Seed for the deterministic random subsample. The same seed
            (with the same ROI/non-ROI setup) always draws the same
            subsample.
        """
        if self.roi_indices is None or self.nonroi_indices is None:
            raise RuntimeError(
                "setup_search_subsample() requires setup_evaluation() to "
                "have been called first"
            )

        n_nonroi = len(self.nonroi_indices)
        n_samples = min(n_nonroi_samples, n_nonroi)
        rng = np.random.default_rng(seed)

        if n_samples < n_nonroi:
            sub_pos = rng.choice(n_nonroi, size=n_samples, replace=False)
            sub_pos.sort()
        else:
            sub_pos = np.arange(n_nonroi)

        self.search_nonroi_indices = self.nonroi_indices[sub_pos]
        sub_vol_weights = self.nonroi_weights[sub_pos]
        weight_sum = sub_vol_weights.sum()
        self.search_nonroi_weights = (
            sub_vol_weights / weight_sum if weight_sum > 0 else sub_vol_weights
        )

        n_roi = len(self.roi_indices)
        n_sub = len(self.search_nonroi_indices)
        self._search_index = np.concatenate(
            [self.roi_indices, self.search_nonroi_indices]
        )
        self._search_roi_pos = np.arange(n_roi)
        self._search_nonroi_pos = np.arange(n_roi, n_roi + n_sub)

        log.info(
            f"FastTIEvaluator search subsample: ROI={n_roi} (full), "
            f"nonROI={n_sub}/{n_nonroi} (subsampled, seed={seed})"
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
        metric: str = METRIC_MTI_MODULATION_DEPTH,
        scheme: str = SCHEME_MULTIBAND,
        psi=None,
    ) -> dict[str, float]:
        """Evaluate an N-pair mTI montage from pre-computed pair diffs.

        Always computed on the full mesh (no search subsampling) -- see
        :meth:`evaluate_final` for the intended "score the DE search's
        winning montage(s)" entry point built on top of this method.

        Parameters
        ----------
        pair_diffs : list of (M, 3) arrays
            Per-electrode-pair leadfield differences from
            :meth:`precompute_pair_diffs`.
        currents_A : list of float
            Per-pair current amplitude in amperes.
        metric : {"mti_modulation_depth", "recursive_ti"}
            N>2 envelope metric (finding F1); ignored for the 2-pair
            (K=1) case, which always uses the exact closed form. See
            :func:`_ti_magnitude_npair`.
        scheme : {"multiband", "dual_carrier"}
            N>2 electrode-pair grouping (finding F11); ignored for the
            2-pair case and for ``metric="recursive_ti"``.
        psi : array-like or None
            Per-interference-pair envelope phase offset; ignored for the
            2-pair case and for ``metric="recursive_ti"``.

        Returns
        -------
        metrics : dict with roi_mean, nonroi_mean, focality, roi_max
        """
        e_fields = [I * diff for I, diff in zip(currents_A, pair_diffs)]

        if len(e_fields) == 2:
            ti_mag = _fast_ti_magnitude(e_fields[0], e_fields[1])
        else:
            ti_mag = _ti_magnitude_npair(
                e_fields, metric=metric, scheme=scheme, psi=psi
            )

        return self._compute_metrics(ti_mag)

    def evaluate_final(
        self,
        pair_diffs: list[np.ndarray],
        currents_A: list[float],
        metric: str = METRIC_MTI_MODULATION_DEPTH,
        scheme: str = SCHEME_MULTIBAND,
        psi=None,
    ) -> dict[str, float]:
        """Recompute exact metrics on the full mesh for a final montage.

        Identical computation to :meth:`evaluate_montage_npair` (which is
        always full-mesh already) -- named separately so call sites make
        the "search subsample vs. final exact score" distinction from
        finding F10 explicit. Use this to (re)score the montage(s) a DE
        search returns, after :meth:`focality_from_diffs` may have used a
        non-ROI subsample (:meth:`setup_search_subsample`) during the
        search itself.

        Parameters and return value: see :meth:`evaluate_montage_npair`.
        """
        return self.evaluate_montage_npair(
            pair_diffs, currents_A, metric=metric, scheme=scheme, psi=psi
        )

    def focality_from_diffs(
        self,
        pair_diffs: list[np.ndarray],
        currents_A: np.ndarray,
        metric: str = METRIC_MTI_MODULATION_DEPTH,
        scheme: str = SCHEME_MULTIBAND,
        psi=None,
    ) -> float:
        """Fast focality-only computation for the inner DE optimizer.

        If :meth:`setup_search_subsample` has been called, the (expensive)
        envelope computation is restricted to ``roi_indices UNION
        nonroi_subsample`` instead of the full mesh (finding F10). Call
        :meth:`evaluate_final` once the search has picked a winner to
        recompute exact numbers on the full mesh.

        Parameters: see :meth:`evaluate_montage_npair`.
        """
        if self._search_index is not None:
            idx = self._search_index
            e_fields = [c * d[idx] for c, d in zip(currents_A, pair_diffs)]
        else:
            e_fields = [c * d for c, d in zip(currents_A, pair_diffs)]

        if len(e_fields) == 2:
            ti_mag = _fast_ti_magnitude(e_fields[0], e_fields[1])
        else:
            ti_mag = _ti_magnitude_npair(
                e_fields, metric=metric, scheme=scheme, psi=psi
            )

        if self._search_index is not None:
            roi_mean = ti_mag[self._search_roi_pos] @ self.roi_weights
            nonroi_mean = ti_mag[self._search_nonroi_pos] @ self.search_nonroi_weights
        else:
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

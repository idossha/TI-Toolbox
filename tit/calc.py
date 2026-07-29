#!/usr/bin/env simnibs_python
"""Temporal interference field calculation utilities.

Vectorised NumPy implementations of the TI modulation-amplitude algorithm
from Grossman et al. (2017), extended to multi-channel (mTI) configurations.
Used by the simulation engine and optimisation tools.

Public API
----------
get_TI_vectors
    Compute TI modulation-amplitude vectors for a single electrode pair.
get_nTI_vectors
    Generalised N-channel TI via recursive binary-tree pairing.
    **Deprecated** -- see its docstring; no basis in the TI literature for
    N > 2, kept only for backward compatibility with :mod:`tit.sim.mTI`.
get_mTI_vectors
    4-channel mTI (convenience wrapper around :func:`get_TI_vectors`).
mti_modulation_depth
    Verified N-pair (mTI) modulation-depth envelope with an optional
    per-pair coherent phase term.  The correct replacement for
    :func:`get_nTI_vectors` in new code.
compute_mti_metric_field, compute_mti_vectors
    Dispatch across the ``MTI_METRIC_*`` family of N-pair metrics.

Attribution
-----------
The ``MTI_METRIC_*`` constants, the ``compute_mti_vectors`` /
``compute_mti_metric_field`` dispatch functions, and the
``_botzanowski_*`` / ``_grossman_ext_*`` / ``_fibonacci_sphere`` helpers
were authored by a collaborator on the ``alba/ex-search-multipolar``
branch and are **ported here with attribution**, not reimplemented. They
were independently verified (0.00% error) against a time-domain ground
truth in ``tracks/active/mti-focality-core.md`` (Phase 1), which also
promotes the Botzanowski directional metric to the package default (it
was previously opt-in, with the unvalidated recursive-TI metric default).
:func:`mti_modulation_depth` is new work built on top of that port: it
generalises the real-weight (phase-blind) Botzanowski form with a
per-pair coherent envelope-phase term and returns the carrier power that
the ported implementation computes internally and discards.
"""

import numpy as np

# ── mTI metric family (ported from alba/ex-search-multipolar, see module
#    docstring "Attribution") ─────────────────────────────────────────────

MTI_METRIC_RECURSIVE_TI = "recursive_ti"
MTI_METRIC_BOTZANOWSKI_MAGNITUDE_AM = "botzanowski_magnitude_am"
MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM = "botzanowski_directional_am"
MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM_AVG = "botzanowski_directional_am_ti_avg"
MTI_METRIC_GROSSMAN_EXT_DIRECTIONAL_AM = "grossman_ext_directional_am"
MTI_METRIC_GROSSMAN_EXT_DIRECTIONAL_AM_AVG = "grossman_ext_directional_am_ti_avg"

MTI_METRICS = {
    MTI_METRIC_RECURSIVE_TI,
    MTI_METRIC_BOTZANOWSKI_MAGNITUDE_AM,
    MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM,
    MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM_AVG,
    MTI_METRIC_GROSSMAN_EXT_DIRECTIONAL_AM,
    MTI_METRIC_GROSSMAN_EXT_DIRECTIONAL_AM_AVG,
}

# Default metric for the compute_mti_* dispatch below. Promoted from
# MTI_METRIC_RECURSIVE_TI (unvalidated, -13%/+12% error at N=4) to the
# verified Botzanowski directional form (0.00% error) -- see
# tracks/active/mti-focality-core.md Phase 1, findings F1/F2.
_DEFAULT_MTI_METRIC = MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM


def get_TI_vectors(E1_org, E2_org):
    """
    Calculate the temporal interference (TI) modulation amplitude vectors.

    This function implements the Grossman et al. 2017 algorithm for computing
    TI vectors that represent both the direction and magnitude of maximum
    modulation amplitude when two sinusoidal electric fields interfere.

    PHYSICAL INTERPRETATION:
    When two electric fields E1(t) = E1*cos(2πf1*t) and E2(t) = E2*cos(2πf2*t)
    with slightly different frequencies are applied simultaneously, they create
    a beating pattern. The TI vector indicates:
    - DIRECTION: Spatial direction of maximum envelope modulation
    - MAGNITUDE: Maximum envelope amplitude = 2 * effective_amplitude

    ALGORITHM (Grossman et al. 2017):
    1. Preprocessing: Ensure |E1| ≥ |E2| and acute angle α < π/2
    2. Regime selection based on geometric relationship:
       - Regime 1 (parallel): |E2| ≤ |E1|cos(α) → TI = 2*E2
       - Regime 2 (oblique): |E2| > |E1|cos(α) → TI = 2*E2_perpendicular_to_h
       where h = E1 - E2

    Parameters
    ----------
    E1_org : np.ndarray, shape (N, 3)
        Electric field vectors from electrode pair 1 [V/m]
    E2_org : np.ndarray, shape (N, 3)
        Electric field vectors from electrode pair 2 [V/m]

    Returns
    -------
    TI_vectors : np.ndarray, shape (N, 3)
        TI modulation amplitude vectors [V/m]
        Direction: Maximum modulation direction
        Magnitude: Maximum envelope amplitude

    References
    ----------
    Grossman, N. et al. (2017). Noninvasive Deep Brain Stimulation via
    Temporally Interfering Electric Fields. Cell, 169(6), 1029-1041.

    See Also
    --------
    get_mTI_vectors : 4-channel mTI (two pairs of pairs).
    get_nTI_vectors : Generalised N-channel recursive TI (deprecated).
    mti_modulation_depth : Verified N-pair envelope; K=1 reduces to this
        function's magnitude exactly.
    """
    # Input validation
    assert E1_org.shape == E2_org.shape, "E1 and E2 must have same shape"
    assert E1_org.shape[1] == 3, "Vectors must be 3D"

    # Work with copies to avoid modifying input arrays
    E1 = E1_org.copy()
    E2 = E2_org.copy()

    # =================================================================
    # PREPROCESSING STEP 1: Magnitude ordering |E1| ≥ |E2|
    # =================================================================
    # Ensures consistency by always treating E1 as the "stronger" field
    # This simplifies the subsequent regime analysis
    idx_swap = np.linalg.norm(E2, axis=1) > np.linalg.norm(E1, axis=1)
    E1[idx_swap], E2[idx_swap] = E2[idx_swap], E1_org[idx_swap]

    # =================================================================
    # PREPROCESSING STEP 2: Acute angle constraint α < π/2
    # =================================================================
    # Ensures constructive interference by flipping E2 if dot product < 0
    # This avoids destructive interference scenarios
    idx_flip = np.sum(E1 * E2, axis=1) < 0
    E2[idx_flip] = -E2[idx_flip]

    # =================================================================
    # GEOMETRIC PARAMETERS CALCULATION
    # =================================================================
    # Calculate field magnitudes and angle between vectors
    normE1 = np.linalg.norm(E1, axis=1)
    normE2 = np.linalg.norm(E2, axis=1)

    # Safe cosine calculation to avoid division by zero and numerical errors
    denom = normE1 * normE2
    denom[denom == 0] = 1.0  # Prevent division by zero
    cosalpha = np.clip(np.sum(E1 * E2, axis=1) / denom, -1.0, 1.0)

    # =================================================================
    # REGIME SELECTION CRITERION
    # =================================================================
    # Critical condition from Grossman 2017: |E2| ≤ |E1| * cos(α)
    # This determines whether E2 is "small" relative to E1's projection
    regime1_mask = normE2 <= normE1 * cosalpha

    # Initialize output array
    TI_vectors = np.zeros_like(E1)

    # =================================================================
    # REGIME 1: PARALLEL ALIGNMENT (|E2| ≤ |E1| cos(α))
    # =================================================================
    # Physical interpretation: E2 is effectively "contained" within E1's projection
    # The TI amplitude is determined entirely by E2's magnitude and direction
    # Formula: TI = 2 * E2
    TI_vectors[regime1_mask] = 2.0 * E2[regime1_mask]

    # =================================================================
    # REGIME 2: OBLIQUE CONFIGURATION (|E2| > |E1| cos(α))
    # =================================================================
    # Physical interpretation: E2 has significant perpendicular component to E1
    # The TI is determined by the component of E2 perpendicular to h = E1 - E2
    # Formula: TI = 2 * E2_perpendicular_to_h
    regime2_mask = ~regime1_mask
    if np.any(regime2_mask):
        # Calculate difference vector h = E1 - E2
        h = E1[regime2_mask] - E2[regime2_mask]
        h_norm = np.linalg.norm(h, axis=1)

        # Handle degenerate case (h = 0) by setting unit norm
        h_norm[h_norm == 0] = 1.0
        e_h = h / h_norm[:, None]  # Unit vector along h

        # Project E2 onto h, then subtract to get perpendicular component
        # E2_perp = E2 - proj_h(E2) = E2 - (E2·ĥ)ĥ
        E2_parallel_component = np.sum(E2[regime2_mask] * e_h, axis=1)[:, None] * e_h
        E2_perp = E2[regime2_mask] - E2_parallel_component

        # The TI vector in regime 2 is twice the perpendicular component
        TI_vectors[regime2_mask] = 2.0 * E2_perp

    return TI_vectors


def get_nTI_vectors(fields):
    """Compute TI vectors for *N* E-fields using recursive binary-tree pairing.

    *N* must be even.  Fields are paired sequentially — ``(E1, E2)``,
    ``(E3, E4)``, etc. — then intermediate TI results are paired recursively
    until a single result remains.

    For 2 fields: ``TI(E1, E2)``
    For 4 fields: ``TI(TI(E1,E2), TI(E3,E4))``
    For 6 fields: ``TI(TI(TI(E1,E2), TI(E3,E4)), TI(E5,E6))``
    For 8 fields: ``TI(TI(TI(E1,E2), TI(E3,E4)), TI(TI(E5,E6), TI(E7,E8)))``

    .. deprecated:: mti-focality-core Phase 1
        This recursive binary-tree formulation has **no basis in the
        published TI literature** for N > 2 pairs. It is a category error:
        it feeds two already-modulated *envelope* vectors (each already
        oscillating at the beat frequency) into :func:`get_TI_vectors`, a
        formula whose Grossman et al. (2017) derivation assumes two
        *carrier* fields at distinct high frequencies -- this function
        never sees a frequency assignment at all. Measured against a
        time-domain ground truth (square -> brick-wall low-pass -> sqrt
        demodulation), it errs **-13% to +12% with no consistent sign for
        N=4**; it remains exact for N=2 (a single call to
        :func:`get_TI_vectors`).

        Kept for backward compatibility only: :mod:`tit.sim.mTI` still
        calls this function to write the intermediate ``*_mTI.msh`` field
        that downstream analysis reads, and removing it is a separate,
        out-of-scope migration. See ``tracks/active/mti-focality-core.md``
        (Phase 1, finding F1) for the full derivation of the error band.

        Use :func:`mti_modulation_depth` for any new N>2 (mTI) work -- it
        implements the verified Botzanowski-form envelope (0.00% error
        against the same ground truth) with an optional per-pair coherent
        phase term.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)
        Electric field vectors, one per electrode pair.

    Returns
    -------
    result : np.ndarray, shape (N, 3)
        Combined TI modulation amplitude vectors.

    Raises
    ------
    ValueError
        If number of fields is not even or less than 2.

    See Also
    --------
    get_TI_vectors : Core 2-field TI calculation.
    get_mTI_vectors : 4-channel convenience wrapper.
    mti_modulation_depth : Verified, non-deprecated N-pair replacement.
    """
    n = len(fields)
    if n < 2 or n % 2 != 0:
        raise ValueError(
            f"get_nTI_vectors requires an even number of fields >= 2, got {n}"
        )

    # First round: pair adjacent fields
    current = []
    for i in range(0, n, 2):
        current.append(get_TI_vectors(fields[i], fields[i + 1]))

    # Recursive rounds: pair results until one remains
    while len(current) > 1:
        next_round = []
        i = 0
        while i + 1 < len(current):
            next_round.append(get_TI_vectors(current[i], current[i + 1]))
            i += 2
        # Odd element carries forward
        if i < len(current):
            next_round.append(current[i])
        current = next_round

    return current[0]


def compute_mti_vectors(fields, metric=_DEFAULT_MTI_METRIC):
    """Compute vector-valued mTI output for metrics with a best direction.

    Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution"). Default changed from ``MTI_METRIC_RECURSIVE_TI`` to
    ``MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM``.
    """
    metric = _normalize_mti_metric(metric)
    if metric == MTI_METRIC_RECURSIVE_TI:
        return get_nTI_vectors(fields)
    if metric == MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM:
        return compute_botzanowski_directional_am_stats(fields)["vectors"]
    if metric == MTI_METRIC_GROSSMAN_EXT_DIRECTIONAL_AM:
        return compute_grossman_ext_directional_am_stats(fields)["vectors"]
    raise ValueError(f"Metric does not produce mTI vectors: {metric!r}")


def compute_mti_metric_field(fields, metric=_DEFAULT_MTI_METRIC):
    """Compute a scalar mTI field for one selected multipolar metric.

    Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution"). Default changed from ``MTI_METRIC_RECURSIVE_TI`` to
    ``MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM``.

    Parameters
    ----------
    fields : list of np.ndarray
        Electric field vectors, one array per bipolar electrode pair.
    metric : str
        One of :data:`MTI_METRICS`.

    Returns
    -------
    np.ndarray
        Scalar metric value for each mesh element/voxel.
    """
    metric = _normalize_mti_metric(metric)
    if metric == MTI_METRIC_RECURSIVE_TI:
        return np.linalg.norm(get_nTI_vectors(fields), axis=1)
    if metric == MTI_METRIC_BOTZANOWSKI_MAGNITUDE_AM:
        return compute_botzanowski_magnitude_am_vectors(fields)
    if metric == MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM:
        return np.linalg.norm(
            compute_botzanowski_directional_am_stats(fields)["vectors"], axis=1
        )
    if metric == MTI_METRIC_BOTZANOWSKI_DIRECTIONAL_AM_AVG:
        return compute_botzanowski_directional_am_stats(fields)["avg"]
    if metric == MTI_METRIC_GROSSMAN_EXT_DIRECTIONAL_AM:
        return np.linalg.norm(
            compute_grossman_ext_directional_am_stats(fields)["vectors"], axis=1
        )
    if metric == MTI_METRIC_GROSSMAN_EXT_DIRECTIONAL_AM_AVG:
        return compute_grossman_ext_directional_am_stats(fields)["avg"]
    raise ValueError(f"Unsupported mTI metric: {metric!r}")


def compute_botzanowski_magnitude_am_vectors(fields):
    """Compute direct-field AM from the envelope of ``||E(t)||``.

    Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution").
    """
    mti_amp, _env_max = _botzanowski_magnitude_am_components(fields)
    return mti_amp


def compute_botzanowski_directional_am_stats(fields):
    """Return best-direction and orientation-averaged Botzanowski AM fields.

    Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution"). Real-weight (phase-blind) form; see
    :func:`mti_modulation_depth` for the phase-aware generalisation.
    """
    vectors, peak_env, avg = _botzanowski_directional_am_components(fields)
    return {"vectors": vectors, "avg": avg, "peak_env": peak_env}


def compute_grossman_ext_directional_am_stats(fields):
    """Return best-direction and orientation-averaged full-field AM fields.

    Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution").
    """
    vectors, peak_env, avg = _grossman_ext_directional_am_components(fields)
    return {"vectors": vectors, "avg": avg, "peak_env": peak_env}


# ── mti_modulation_depth: verified, phase-aware N-pair envelope (new) ──────
#
# This is the genuinely new contribution of mti-focality-core Phase 1
# (finding F3), built on the ported real-weight form above. It reuses the
# ported _validate_field_list / _fibonacci_sphere helpers below.


def mti_modulation_depth(
    fields,
    psi=None,
    directions=None,
    num_directions=192,
    chunk_size=16384,
    refine=True,
):
    r"""Compute the coherent multi-pair TI modulation-depth envelope.

    Implements the closed-form envelope for *K* electrode pairs that share
    a common beat frequency :math:`\Delta f` but sit on separate carrier
    bands, projected onto a direction :math:`\hat n`:

    .. math::

        MD(\hat n) = \sqrt{2}\,\left[\sqrt{P+Q} - \sqrt{P-Q}\right]

        P = \tfrac12 \sum_k \left(a_k^2 + b_k^2\right)
        \qquad\text{(total carrier power along } \hat n \text{)}

        Q = \left|\sum_k a_k b_k\, e^{i\psi_k}\right|
        \qquad\text{(coherent phasor sum over pairs)}

        a_k = E_{ka}\cdot\hat n,\quad b_k = E_{kb}\cdot\hat n
        \qquad\text{(signed projections; do not take } |a_k|, |b_k| \text{)}

        \psi_k = \phi_{kb} - \phi_{ka}
        \qquad\text{(per-pair envelope phase offset, radians)}

    With ``psi=None`` (or all zeros), :math:`Q` reduces exactly to
    :math:`\left|\sum_k a_k b_k\right|` -- the real-weight form ported from
    the collaborator branch ``alba/ex-search-multipolar`` as
    :func:`_botzanowski_directional_am_components` (see module docstring
    "Attribution"). This function generalises that form with the coherent
    phasor sum, and additionally returns ``P`` -- the carrier power the
    ported implementation computes internally (as ``s0``) and discards.

    For *K* = 1 this reduces **exactly** to the standard Grossman/Huang
    two-channel modulation depth, ``2 * min(|a|, |b|)``.

    Verified against a time-domain ground truth (square -> brick-wall
    low-pass -> sqrt demodulation, per Botzanowski et al.) to < 0.01% error
    for K in {1, 2, 4, 6}, both with ``psi=None`` and with random
    per-pair phases -- see ``scripts/verify_mti_envelope.py`` and
    ``tracks/active/mti-focality-core.md`` (Phase 1, finding F3). The
    phase-blind (``psi=None``) form errs 5.7%-454% once the true
    :math:`\psi_k \neq 0`, which is why the phase term matters whenever
    per-pair envelope phase is not independently guaranteed to be zero.

    Anti-phase pairs cancel exactly: for K=2 with equal amplitudes and
    ``psi = [0, pi]``, ``MD`` is exactly 0.0 (Botzanowski Suppl. Fig. 1 --
    a 180-degree envelope offset between pairs produces no aggregate
    envelope).

    Validity requires sufficient carrier-band separation between pairs
    (finding F7); see :func:`tit.opt.config.validate_band_separation`.

    Direction-sweep sampling error (Phase 2, finding from the mti-carrier-
    metrics track)
    -----------------------------------------------------------------------
    The raw 192-direction Fibonacci-sphere sweep (``refine=False``) can only
    ever *underestimate* the true best-direction envelope -- a finite sweep
    finds a max that is less-than-or-equal to the true max -- so its bias is
    one-sided. But the *variance* of that underestimate is per-montage noise
    that tracks field geometry, and it does **not** cancel when ranking two
    candidate montages against each other. Measured against the exact K=1
    closed form (:func:`get_TI_vectors`) over random field pairs::

        sweep resolution   mean err   median err   p95 err   worst err
        n_dir=  192          1.54%       1.00%       4.28%      6.86%
        n_dir=  512          0.77%       0.53%       2.30%      2.85%
        n_dir= 2048          0.25%       0.14%       0.86%      1.41%
        n_dir= 8192          0.12%       0.07%       0.40%      0.79%
        signed error at n_dir=192: mean -1.50%, std 1.45%, range [-8.37%, 0.00%]

    For scale, Lee et al. (2020)'s entire optimized-vs-baseline hippocampus
    focality range is 1.1 -> 1.2 (a 9% effect) -- an 8%-tailed sampling
    noise floor at the production default is large enough to flip montage
    rankings.

    ``refine=True`` (the default) removes this noise with a two-tier fix
    that leaves ``num_directions=192`` unchanged as the coarse-stage
    resolution:

    - **K = 1** (a single TI pair -- two carrier fields): the best-direction
      envelope has an exact closed form (Grossman et al. 2017; the
      sign-agnostic form of Hirata et al. 2024 used here needs no
      canonicalization branch). No sweep is performed at all -- error is
      floating-point noise only (< 1e-12 vs. :func:`get_TI_vectors`, see
      ``tests/test_calc_mti.py::TestK1ExactPath``), and this path is
      *cheaper* than the sweep it replaces, not more expensive.
    - **K >= 2**: the coarse 192-direction sweep locates several diverse
      starting directions (not just the argmax -- picking only the single
      best coarse sample is not robust: the envelope surface can have
      multiple local maxima, and the samples nearest the true global
      maximum occasionally rank below a cluster of neighbouring samples
      around a different, decoy peak), then a few rounds of shrinking-
      radius local-patch search (no ``scipy`` dependency, so this stays
      testable under the project's mocked-``scipy`` test environment)
      refine each. Measured worst-case error against a 300,000-direction
      reference sweep drops from the ~6-8% figure above to **< 0.5%**
      (see ``tests/test_calc_mti.py::TestRefinementAccuracy``) at a
      measured cost of roughly **7x** the coarse sweep alone -- higher
      than the ~2x originally targeted; a lighter configuration (fewer
      seeds/rounds) was measured and did not reliably clear the 0.5%
      worst-case bar across a broad trial sweep, so accuracy was kept as
      the binding constraint. This cost is scale-invariant (measured
      flat from N=5e4 to N=2e6 elements) and still cheap in absolute
      terms -- a few seconds per 1e6 elements.

    ``refine=False`` reproduces the original (Phase 1) coarse-sweep-only
    behaviour exactly, including for K=1 -- this is what makes the
    ``psi=None`` bit-parity comparison against the ported collaborator
    implementation meaningful, and is the mode to use for that comparison.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)
        Electric field vectors ordered ``[E_1a, E_1b, E_2a, E_2b, ...]``
        -- 2K arrays for K electrode pairs, one array per sub-channel.
    psi : array-like of float, shape (K,), or None
        Per-pair envelope phase offset in radians, ``psi_k = phi_kb -
        phi_ka``. ``None`` (default) assumes every pair's envelope is
        phase-aligned (``psi_k = 0``) and takes a real-only fast path that
        is bit-identical to the ported real-weight implementation.
    directions : np.ndarray, shape (N, 3), or None
        If ``None`` (default), find the best-direction envelope per
        element -- the mode used for mTI field maps; see ``refine`` below
        for how the search is performed. If given, use the supplied
        per-element direction directly (normalised internally) with no
        search -- the mode used to project onto a known orientation (e.g.
        cortical normal) or to validate the closed form against ground
        truth at an exact, known direction. ``refine`` has no effect in
        this mode.
    num_directions : int, default 192
        Number of Fibonacci-sphere sample directions for the coarse-stage
        sweep when ``directions`` is ``None``. The default matches the
        ported implementation exactly (required for the ``psi=None``,
        ``refine=False`` bit-identity guarantee). Higher values trade
        sampling error for compute cost -- e.g. verification against an
        exact analytical optimum (K=1) needs a much finer sweep than the
        production default; see ``scripts/verify_mti_envelope.py``.
    chunk_size : int, default 16384
        Mesh elements processed per chunk during the direction sweep,
        bounding peak memory regardless of total element count.
    refine : bool, default True
        If ``True`` (default), use the accurate two-tier direction search
        described above: the K=1 exact closed form (no sweep), or coarse
        sweep + local refinement for K >= 2. If ``False``, use the original
        Phase 1 coarse-sweep-only search unconditionally (for both K=1 and
        K >= 2) at ``num_directions`` resolution -- bit-identical to Phase 1
        and to the ported collaborator implementation (when ``psi=None``).
        Kept reachable for bit-parity comparison; not recommended for new
        code since it carries the sampling error documented above.

    Returns
    -------
    dict
        ``"md"`` : np.ndarray, shape (N,)
            Best-direction (or given-direction) modulation depth [V/m].
        ``"carrier_power"`` : np.ndarray, shape (N,)
            Total carrier power ``P`` at the direction ``md`` was
            evaluated at [V/m^2] -- see finding F4 (carrier-exposure
            constraint, wired up in Phase 2).
        ``"best_direction"`` : np.ndarray, shape (N, 3)
            Unit vector the envelope was evaluated at -- the swept-best
            direction, or the (normalised) input ``directions``.

    Raises
    ------
    ValueError
        If ``fields`` is not an even-length list of identically-shaped
        ``(N, 3)`` arrays, if ``psi`` does not have shape ``(K,)``, or if
        ``directions`` (when given) does not match the field arrays' shape.

    See Also
    --------
    get_TI_vectors : Exact K=1 closed form (Grossman et al. 2017); this
        function's magnitude matches it exactly for K=1.
    get_nTI_vectors : Deprecated, unvalidated N>2 predecessor.
    compute_mti_metric_field : Dispatch across the ported MTI_METRIC_*
        family (phase-blind only).
    tit.opt.config.MTIFrequencyPlan : Records the per-pair carrier/phase
        assignment this function's ``psi`` argument is derived from.
    """
    arrs = _validate_field_list(fields)
    n_pairs = len(arrs) // 2
    psi_arr = _validate_psi(psi, n_pairs)

    if directions is not None:
        return _mti_modulation_depth_at_directions(arrs, psi_arr, directions)

    if refine and n_pairs == 1:
        md, P, best_direction = _k1_exact_envelope(arrs[0], arrs[1])
        return {"md": md, "carrier_power": P, "best_direction": best_direction}

    return _mti_modulation_depth_sweep(
        arrs, psi_arr, num_directions, chunk_size, refine
    )


def _validate_psi(psi, n_pairs):
    """Normalise/validate the per-pair envelope phase array."""
    if psi is None:
        return None
    psi_arr = np.asarray(psi, dtype=np.float64)
    if psi_arr.shape != (n_pairs,):
        raise ValueError(
            "psi must be None or have shape "
            f"({n_pairs},) -- one phase offset per electrode pair; got "
            f"shape {psi_arr.shape}"
        )
    return psi_arr


def _pairwise_products(proj_fields, psi):
    """Return (P, Q) -- carrier power and coherent phasor magnitude.

    ``proj_fields`` is a list of 2K arrays of identical shape (signed
    projections onto one or more candidate directions). When ``psi`` is
    ``None`` or all-zero, ``Q`` is computed via a real-only sum -- the
    same operation order as the ported ``_botzanowski_directional_am_components``
    -- so results are bit-identical to that implementation.
    """
    n_pairs = len(proj_fields) // 2

    P = np.zeros_like(proj_fields[0], dtype=np.float64)
    for p in proj_fields:
        P += p * p
    P *= 0.5

    use_phase = psi is not None and np.any(psi != 0.0)
    if use_phase:
        z = np.zeros_like(P, dtype=np.complex128)
        for k in range(n_pairs):
            a = proj_fields[2 * k]
            b = proj_fields[2 * k + 1]
            z += (a * b) * np.exp(1j * psi[k])
        Q = np.abs(z)
    else:
        b_sum = np.zeros_like(P)
        for k in range(n_pairs):
            a = proj_fields[2 * k]
            b = proj_fields[2 * k + 1]
            b_sum += a * b
        Q = np.abs(b_sum)

    return P, Q


def _envelope_from_PQ(P, Q):
    """MD = sqrt(2) * (sqrt(P+Q) - sqrt(P-Q)), clamped against negative
    round-off inside the square roots."""
    smin = np.maximum(P - Q, 0.0)
    smax = np.maximum(P + Q, 0.0)
    return np.sqrt(2.0 * smax) - np.sqrt(2.0 * smin)


def _k1_exact_envelope(E1, E2):
    """Exact best-direction K=1 envelope via the sign-agnostic closed form
    (Hirata et al. 2024), with no sweep and no canonicalization branch.

    .. math::

        MD = \\begin{cases}
            2\\min(|E_1|,|E_2|) & \\min(|E_1|,|E_2|) \\le \\sqrt{|E_1\\cdot E_2|} \\\\
            \\dfrac{2|E_1\\times E_2|}{\\min(|E_1-E_2|,|E_1+E_2|)} & \\text{otherwise}
        \\end{cases}

    Verified to match :func:`get_TI_vectors`'s magnitude to < 1e-12 over
    >= 1e4 random field pairs -- see
    ``tests/test_calc_mti.py::TestK1ExactPath``.

    The per-pair envelope phase ``psi`` has no effect on K=1 (a single
    complex term's magnitude is phase-invariant: ``|a*b*e^{i psi}| =
    |a*b|``), so this fast path is unconditionally correct regardless of
    hardware phase offset.

    Returns
    -------
    md : np.ndarray, shape (N,)
    carrier_power : np.ndarray, shape (N,)
        ``P = 0.5 * (a^2 + b^2)`` evaluated at the same direction as ``md``.
    best_direction : np.ndarray, shape (N, 3)
        Unit vector (sign is arbitrary -- MD and P are direction-sign
        invariant).
    """
    n = E1.shape[0]
    norm_e1 = np.linalg.norm(E1, axis=1)
    norm_e2 = np.linalg.norm(E2, axis=1)
    dot = np.sum(E1 * E2, axis=1)
    min_norm = np.minimum(norm_e1, norm_e2)

    md = np.zeros(n, dtype=np.float64)
    best_dir = np.tile(np.array([0.0, 0.0, 1.0]), (n, 1))

    # Regime A ("parallel"): the smaller field's own direction is optimal.
    regime_a = min_norm <= np.sqrt(np.abs(dot))
    if np.any(regime_a):
        use_e1 = norm_e1[regime_a] <= norm_e2[regime_a]
        e_small = np.where(use_e1[:, None], E1[regime_a], E2[regime_a])
        norm_small = np.where(use_e1, norm_e1[regime_a], norm_e2[regime_a])
        nonzero = norm_small > 0.0
        norm_small_safe = np.where(nonzero, norm_small, 1.0)
        dir_a = e_small / norm_small_safe[:, None]
        rows_a = np.flatnonzero(regime_a)
        best_dir[rows_a[nonzero]] = dir_a[nonzero]
        md[regime_a] = 2.0 * min_norm[regime_a]

    # Regime B ("oblique"): optimal direction is the component of either
    # field perpendicular to h = E1 -/+ E2 (whichever has smaller norm);
    # E1_perp == E2_perp exactly for that choice of h (both fields differ
    # from each other only along h), so projecting either field is exact.
    regime_b = ~regime_a
    if np.any(regime_b):
        e1b, e2b = E1[regime_b], E2[regime_b]
        h_minus = e1b - e2b
        h_plus = e1b + e2b
        norm_minus = np.linalg.norm(h_minus, axis=1)
        norm_plus = np.linalg.norm(h_plus, axis=1)
        use_minus = norm_minus <= norm_plus
        h = np.where(use_minus[:, None], h_minus, h_plus)
        h_norm = np.where(use_minus, norm_minus, norm_plus)
        h_nonzero = h_norm > 0.0
        h_norm_safe = np.where(h_nonzero, h_norm, 1.0)
        e_h = h / h_norm_safe[:, None]

        e2_perp = e2b - np.sum(e2b * e_h, axis=1, keepdims=True) * e_h
        perp_norm = np.linalg.norm(e2_perp, axis=1)
        perp_nonzero = perp_norm > 0.0
        perp_norm_safe = np.where(perp_nonzero, perp_norm, 1.0)
        dir_b = e2_perp / perp_norm_safe[:, None]

        cross_norm = np.linalg.norm(np.cross(e1b, e2b), axis=1)
        md_b = np.where(h_nonzero, 2.0 * cross_norm / h_norm_safe, 0.0)

        rows_b = np.flatnonzero(regime_b)
        valid = h_nonzero & perp_nonzero
        best_dir[rows_b[valid]] = dir_b[valid]
        md[regime_b] = md_b

    a = np.sum(E1 * best_dir, axis=1)
    b = np.sum(E2 * best_dir, axis=1)
    P = 0.5 * (a * a + b * b)
    return md, P, best_dir


# ── Local refinement (K>=2), pure NumPy -- no scipy dependency so this
#    stays testable under the project's mocked-scipy test environment. ─────
#
# A single-seed local search (refine only around the coarse sweep's
# argmax) is not robust on its own: the K>=2 envelope surface can have
# multiple local maxima close in value, and the discrete 192-point sweep
# occasionally ranks a *decoy* peak above the true global one while a
# sample much closer to the true peak scores lower. Refining only the
# argmax then converges on the wrong peak. Even ranking by raw amplitude
# and taking the top-M is not enough on its own: the top few coarse
# samples often cluster around the *same* decoy peak (they are spatial
# neighbours, so they tend to rank together), leaving the true peak's
# nearest sample outside the top-M despite there being "room" in M.
# Enforcing angular separation between chosen seeds (see
# ``_diverse_top_m_directions``) so they spread across distinct regions
# of the sphere fixes this at a modest, bounded extra cost -- see
# ``tests/test_calc_mti.py::TestRefinementAccuracy`` for the measured
# worst-case error this achieves.

_REFINE_N_ROUNDS = 3
_REFINE_PATCH_SIZE = 16
_REFINE_SHRINK = 0.4
_REFINE_N_SEEDS = 6
_REFINE_MIN_SEED_ANGLE_DEG = 25.0


def _local_patch_directions(centers, half_angle, n_patch):
    """Return ``n_patch`` unit directions within angular radius
    ``half_angle`` (radians) of each row of ``centers``, an array of unit
    vectors with an arbitrary leading batch shape ``(..., 3)``. Output has
    shape ``(..., n_patch, 3)``.

    Uses a deterministic low-discrepancy spherical-cap parameterisation
    (exact, not a small-angle approximation): an orthonormal tangent basis
    ``(u, v)`` perpendicular to each center, then
    ``cos(r)*center + sin(r)*(cos(phi)*u + sin(phi)*v)`` for a Fibonacci-
    spiral set of ``(r, phi)`` offsets bounded by ``half_angle``.

    Batch dimensions beyond the trailing ``3`` (e.g. an element axis and a
    seed axis) are flattened internally so the whole batch is one
    vectorised NumPy computation -- no Python-level loop over seeds.
    """
    batch_shape = centers.shape[:-1]
    c = centers.reshape(-1, 3)
    m = c.shape[0]

    ref = np.tile(np.array([1.0, 0.0, 0.0]), (m, 1))
    parallel = np.abs(np.sum(c * ref, axis=1)) > 0.99
    if np.any(parallel):
        ref[parallel] = np.array([0.0, 1.0, 0.0])

    u = np.cross(c, ref)
    u_norm = np.linalg.norm(u, axis=1, keepdims=True)
    u_norm[u_norm == 0.0] = 1.0
    u /= u_norm
    v = np.cross(c, u)

    j = np.arange(n_patch, dtype=np.float64)
    golden_angle = np.pi * (3.0 - np.sqrt(5.0))
    r = half_angle * np.sqrt((j + 0.5) / n_patch)
    phi = golden_angle * j

    cos_r = np.cos(r)
    weight_u = np.sin(r) * np.cos(phi)
    weight_v = np.sin(r) * np.sin(phi)

    patch = (
        c[:, None, :] * cos_r[None, :, None]
        + u[:, None, :] * weight_u[None, :, None]
        + v[:, None, :] * weight_v[None, :, None]
    )
    return patch.reshape(*batch_shape, n_patch, 3)


def _diverse_top_m_directions(amp, directions, n_seeds, min_angle_deg):
    """Greedily select ``n_seeds`` coarse-sweep directions per element,
    spread across the sphere rather than just the top-M by raw amplitude.

    Picks the highest-amplitude remaining direction, then masks out every
    direction within ``min_angle_deg`` of it (per element) before picking
    the next. Plain top-M-by-amplitude tends to pick several near-duplicate
    directions clustered around the *same* local peak (they are spatial
    neighbours on the Fibonacci grid, so they rank together) -- which can
    leave every seed anchored to a decoy peak while the true global
    maximum's nearest coarse sample ranks below M. Spacing seeds apart
    fixes this at the same M.

    Parameters
    ----------
    amp : np.ndarray, shape (n, num_directions)
        Coarse-sweep envelope amplitude at every direction, per element.
    directions : np.ndarray, shape (num_directions, 3)
        The coarse Fibonacci-sweep direction grid (shared across elements).
    n_seeds : int
        Number of seeds to select.
    min_angle_deg : float
        Minimum angular separation enforced between chosen seeds.

    Returns
    -------
    np.ndarray, shape (n, n_seeds)
        Column indices into ``directions``/``amp`` for the chosen seeds.
    """
    n = amp.shape[0]
    min_cos = np.cos(np.radians(min_angle_deg))
    remaining = amp.copy()
    chosen_idx = np.zeros((n, n_seeds), dtype=np.int64)

    for s in range(n_seeds):
        idx = np.argmax(remaining, axis=1)
        chosen_idx[:, s] = idx
        if s == n_seeds - 1:
            break
        cos_to_chosen = (directions @ directions[idx].T).T  # (n, num_directions)
        remaining = np.where(cos_to_chosen > min_cos, -np.inf, remaining)

    return chosen_idx


def _refine_local_directions(
    arrs_chunk,
    psi,
    directions,
    amp,
    P,
    num_directions,
):
    """Multi-seed local-patch refinement of a coarse Fibonacci-sweep result.

    Refines around ``_REFINE_N_SEEDS`` diverse coarse-sweep candidates per
    element (see :func:`_diverse_top_m_directions`), then keeps the best
    result across seeds. The seed axis is a vectorised batch dimension
    throughout the refinement rounds (no Python-level loop over seeds), so
    this costs a modest, bounded multiple of a single-seed refinement, not
    ``n_seeds``-times a per-seed Python loop.

    Parameters
    ----------
    arrs_chunk : list of np.ndarray, each shape (n, 3)
        Field arrays for the current chunk.
    psi : np.ndarray or None
        Per-pair envelope phase, shape (K,).
    directions : np.ndarray, shape (num_directions, 3)
        The coarse Fibonacci-sweep direction grid.
    amp, P : np.ndarray, each shape (n, num_directions)
        Envelope and carrier power evaluated at every coarse direction
        (already computed by the caller -- reused here to rank seeds).
    num_directions : int
        Number of coarse-sweep directions (sets the initial patch radius).

    Returns
    -------
    best_md, best_P, best_dir : the refined per-element results (never
        worse than the coarse sweep's own per-element best).
    """
    n = amp.shape[0]
    n_seeds = min(_REFINE_N_SEEDS, directions.shape[0])

    top_idx = _diverse_top_m_directions(
        amp, directions, n_seeds, _REFINE_MIN_SEED_ANGLE_DEG
    )  # (n, S)

    best_dir = directions[top_idx]  # (n, S, 3)
    best_md = np.take_along_axis(amp, top_idx, axis=1)  # (n, S)
    best_P = np.take_along_axis(P, top_idx, axis=1)  # (n, S)

    half_angle = 2.0 / np.sqrt(num_directions)
    seed_rows = np.arange(n)[:, None, None]
    seed_cols = np.arange(n_seeds)[None, :, None]

    for _ in range(_REFINE_N_ROUNDS):
        # (n, S, patch, 3)
        patch = _local_patch_directions(best_dir, half_angle, _REFINE_PATCH_SIZE)
        proj = [np.einsum("nd,nspd->nsp", field, patch) for field in arrs_chunk]
        Pc, Qc = _pairwise_products(proj, psi)  # (n, S, patch)
        ampc = _envelope_from_PQ(Pc, Qc)  # (n, S, patch)

        idx = np.argmax(ampc, axis=2)  # (n, S)
        cand_md = np.take_along_axis(ampc, idx[:, :, None], axis=2)[:, :, 0]
        cand_P = np.take_along_axis(Pc, idx[:, :, None], axis=2)[:, :, 0]
        cand_dir = patch[seed_rows, seed_cols, idx[:, :, None], :][:, :, 0, :]

        improved = cand_md > best_md
        best_md = np.where(improved, cand_md, best_md)
        best_P = np.where(improved, cand_P, best_P)
        best_dir = np.where(improved[:, :, None], cand_dir, best_dir)

        half_angle *= _REFINE_SHRINK

    best_seed = np.argmax(best_md, axis=1)  # (n,)
    final_md = np.take_along_axis(best_md, best_seed[:, None], axis=1)[:, 0]
    final_P = np.take_along_axis(best_P, best_seed[:, None], axis=1)[:, 0]
    final_dir = best_dir[np.arange(n), best_seed]
    return final_md, final_P, final_dir


def _mti_modulation_depth_sweep(arrs, psi, num_directions, chunk_size, refine):
    """Chunked Fibonacci-sphere direction sweep -- returns best-direction
    md/carrier_power/best_direction per element. When ``refine`` is True,
    each chunk's coarse-sweep result is locally refined (see
    :func:`_refine_local_directions`); when False, this reproduces the
    original Phase 1 coarse-sweep-only behaviour exactly."""
    directions = _fibonacci_sphere(num_directions)
    n_vox = arrs[0].shape[0]

    md = np.zeros(n_vox, dtype=np.float64)
    carrier_power = np.zeros(n_vox, dtype=np.float64)
    best_direction = np.zeros((n_vox, 3), dtype=np.float64)

    for start in range(0, n_vox, chunk_size):
        stop = min(start + chunk_size, n_vox)
        arrs_chunk = [field[start:stop] for field in arrs]
        proj = [field @ directions.T for field in arrs_chunk]
        P, Q = _pairwise_products(proj, psi)
        amp = _envelope_from_PQ(P, Q)

        if refine:
            chunk_md, chunk_P, chunk_dir = _refine_local_directions(
                arrs_chunk, psi, directions, amp, P, num_directions
            )
        else:
            idx = np.argmax(amp, axis=1)
            rows = np.arange(stop - start)
            chunk_md = amp[rows, idx]
            chunk_P = P[rows, idx]
            chunk_dir = directions[idx]

        md[start:stop] = chunk_md
        carrier_power[start:stop] = chunk_P
        best_direction[start:stop] = chunk_dir

    return {"md": md, "carrier_power": carrier_power, "best_direction": best_direction}


def _mti_modulation_depth_at_directions(arrs, psi, directions):
    """Evaluate the envelope at an explicit per-element direction (no search)."""
    directions = np.asarray(directions, dtype=np.float64)
    if directions.shape != arrs[0].shape:
        raise ValueError(
            "directions must have the same shape as each field array; got "
            f"{directions.shape}, expected {arrs[0].shape}"
        )
    norms = np.linalg.norm(directions, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    unit_dirs = directions / norms

    proj = [np.sum(field * unit_dirs, axis=1) for field in arrs]
    P, Q = _pairwise_products(proj, psi)
    md = _envelope_from_PQ(P, Q)

    return {"md": md, "carrier_power": P, "best_direction": unit_dirs}


def _normalize_mti_metric(metric):
    """Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution")."""
    metric = metric.value if hasattr(metric, "value") else str(metric)
    if metric not in MTI_METRICS:
        raise ValueError(f"Unsupported mTI metric: {metric!r}")
    return metric


def _botzanowski_magnitude_am_components(fields):
    """Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution")."""
    arrs = _validate_field_list(fields)
    weights = _pair_weights(len(arrs))

    s0 = np.zeros(arrs[0].shape[0], dtype=np.float64)
    for field in arrs:
        s0 += np.sum(field * field, axis=1)
    s0 *= 0.5

    b = np.zeros_like(s0)
    for pair_idx, weight in enumerate(weights):
        f1 = arrs[2 * pair_idx]
        f2 = arrs[2 * pair_idx + 1]
        b += weight * np.sum(f1 * f2, axis=1)

    abs_b = np.abs(b)
    smin = np.maximum(s0 - abs_b, 0.0)
    smax = np.maximum(s0 + abs_b, 0.0)
    env_min = np.sqrt(2 * smin)
    env_max = np.sqrt(2 * smax)
    return env_max - env_min, env_max


def _botzanowski_directional_am_components(fields):
    """Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution"). Real-weight (phase-blind) directional sweep; the
    reference implementation :func:`mti_modulation_depth` (``psi=None``)
    reproduces to floating-point equality."""
    arrs = _validate_field_list(fields)
    weights = _pair_weights(len(arrs))
    directions = _fibonacci_sphere(192)
    chunk_size = 16384

    n_vox = arrs[0].shape[0]
    best_vectors = np.zeros((n_vox, 3), dtype=np.float64)
    best_peak = np.zeros(n_vox, dtype=np.float64)
    avg_amp = np.zeros(n_vox, dtype=np.float64)

    for start in range(0, n_vox, chunk_size):
        stop = min(start + chunk_size, n_vox)
        proj_fields = [field[start:stop] @ directions.T for field in arrs]

        s0 = np.zeros_like(proj_fields[0], dtype=np.float64)
        for proj in proj_fields:
            s0 += proj * proj
        s0 *= 0.5

        b = np.zeros_like(s0, dtype=np.float64)
        for pair_idx, weight in enumerate(weights):
            p1 = proj_fields[2 * pair_idx]
            p2 = proj_fields[2 * pair_idx + 1]
            b += weight * (p1 * p2)

        abs_b = np.abs(b)
        smin = np.maximum(s0 - abs_b, 0.0)
        smax = np.maximum(s0 + abs_b, 0.0)
        env_min = np.sqrt(2 * smin)
        env_max = np.sqrt(2 * smax)
        amp = env_max - env_min

        avg_amp[start:stop] = np.mean(amp, axis=1)
        best_idx = np.argmax(amp, axis=1)
        rows = np.arange(stop - start)
        best_amp = amp[rows, best_idx]
        best_dirs = directions[best_idx]
        best_vectors[start:stop] = best_dirs * best_amp[:, None]
        best_peak[start:stop] = env_max[rows, best_idx]

    return best_vectors, best_peak, avg_amp


def _grossman_ext_directional_am_components(fields):
    """Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution")."""
    arrs = _validate_field_list(fields)
    directions = _fibonacci_sphere(192)
    chunk_size = 16384

    n_vox = arrs[0].shape[0]
    best_vectors = np.zeros((n_vox, 3), dtype=np.float64)
    best_peak_env = np.zeros(n_vox, dtype=np.float64)
    avg_amp = np.zeros(n_vox, dtype=np.float64)

    for start in range(0, n_vox, chunk_size):
        stop = min(start + chunk_size, n_vox)
        proj_fields = [field[start:stop] @ directions.T for field in arrs]

        env_psi0 = np.zeros((stop - start, directions.shape[0]), dtype=np.float64)
        env_psi_pi = np.zeros_like(env_psi0)

        for pair_idx in range(len(arrs) // 2):
            a = proj_fields[2 * pair_idx]
            b = proj_fields[2 * pair_idx + 1]
            env_psi0 += np.abs(a + b)
            env_psi_pi += np.abs(a - b)

        env_hi = np.maximum(env_psi0, env_psi_pi)
        env_lo = np.minimum(env_psi0, env_psi_pi)
        amp = env_hi - env_lo

        avg_amp[start:stop] = np.mean(amp, axis=1)
        best_idx = np.argmax(amp, axis=1)
        rows = np.arange(stop - start)
        best_amp = amp[rows, best_idx]
        best_peak_env[start:stop] = env_hi[rows, best_idx]
        best_vectors[start:stop] = directions[best_idx] * best_amp[:, None]

    return best_vectors, best_peak_env, avg_amp


def _validate_field_list(fields):
    """Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution")."""
    arrs = [np.asarray(field, dtype=np.float64) for field in fields]
    n = len(arrs)
    if n < 2 or n % 2 != 0:
        raise ValueError(f"mTI requires an even number of fields >= 2, got {n}")
    ref_shape = arrs[0].shape
    if len(ref_shape) != 2 or ref_shape[1] != 3:
        raise ValueError(f"Fields must have shape (N, 3), got {ref_shape}")
    for i, arr in enumerate(arrs[1:], start=2):
        if arr.shape != ref_shape:
            raise ValueError(
                "All fields must have identical shape; "
                f"field 1 has {ref_shape}, field {i} has {arr.shape}"
            )
    return arrs


def _pair_weights(num_fields: int):
    """Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution")."""
    return [1.0] * (num_fields // 2)


def _fibonacci_sphere(num_dirs: int) -> np.ndarray:
    """Return approximately uniform unit vectors on the sphere.

    Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution")."""
    if num_dirs < 2:
        return np.array([[0.0, 0.0, 1.0]], dtype=np.float64)
    i = np.arange(num_dirs, dtype=np.float64)
    phi = np.pi * (3.0 - np.sqrt(5.0))
    y = 1.0 - 2.0 * i / (num_dirs - 1)
    radius = np.sqrt(np.maximum(0.0, 1.0 - y * y))
    theta = phi * i
    x = np.cos(theta) * radius
    z = np.sin(theta) * radius
    return np.stack((x, y, z), axis=1)


def get_mTI_vectors(E1_org, E2_org, E3_org, E4_org):
    """Calculate multi-temporal interference (mTI) vectors from four E-fields.

    Computes TI between channels 1 and 2 to get ``TI_A``, TI between
    channels 3 and 4 to get ``TI_B``, and finally TI between ``TI_A`` and
    ``TI_B`` to produce the mTI vector field.

    Parameters
    ----------
    E1_org : np.ndarray, shape (N, 3)
        Electric field vectors for channel 1.
    E2_org : np.ndarray, shape (N, 3)
        Electric field vectors for channel 2.
    E3_org : np.ndarray, shape (N, 3)
        Electric field vectors for channel 3.
    E4_org : np.ndarray, shape (N, 3)
        Electric field vectors for channel 4.

    Returns
    -------
    mTI_vectors : np.ndarray, shape (N, 3)
        Multi-TI modulation amplitude vectors [V/m].

    Raises
    ------
    ValueError
        If any input array does not have shape ``(N, 3)`` or if the shapes
        are not identical.

    See Also
    --------
    get_TI_vectors : Core 2-field TI calculation.
    get_nTI_vectors : Generalised N-channel recursive TI (deprecated).
    """
    # Validate shapes
    for i, arr in enumerate([E1_org, E2_org, E3_org, E4_org], start=1):
        if arr.ndim != 2 or arr.shape[1] != 3:
            raise ValueError(f"E{i}_org must have shape (N, 3), got {arr.shape}")

    if not (E1_org.shape == E2_org.shape == E3_org.shape == E4_org.shape):
        raise ValueError(
            "All input arrays must have identical shapes. "
            f"Got: {[E1_org.shape, E2_org.shape, E3_org.shape, E4_org.shape]}"
        )

    # Step 1: TI between (E1, E2)
    TI_A = get_TI_vectors(E1_org, E2_org)

    # Step 2: TI between (E3, E4)
    TI_B = get_TI_vectors(E3_org, E4_org)

    # Step 3: TI between (TI_A, TI_B) → mTI
    mTI_vectors = get_TI_vectors(TI_A, TI_B)

    return mTI_vectors

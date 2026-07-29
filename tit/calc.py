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
get_mTI_vectors
    4-channel mTI (convenience wrapper around :func:`get_TI_vectors`).
compute_direct_field_peak_hf
    Peak instantaneous carrier-field magnitude across N electrode pairs
    (direction-free, worst-case phase-aligned carrier-exposure metric).

Attribution
-----------
``compute_direct_field_peak_hf`` / ``_direct_field_peak_hf_actual`` were
authored by a collaborator on the ``albantakis`` remote's ``mTI_testing`` /
``mti_formain_cleanup`` branches (Larissa Albantakis; ``alba`` and
``albantakis`` are two remote URLs for the same fork) and are **ported here
with attribution**, not reimplemented -- see
``tracks/active/mti-focality-core.md`` Phase 4. Her sibling function on the
same branches, ``compute_full_field_directional_am_vectors`` /
``_full_field_directional_am_components``, was deliberately **not** ported:
it is a simplified precursor to the Fibonacci-sphere/chunked-projection
directional-AM machinery landing separately, missing the
``max(env_psi0, env_psi_pi) - min(env_psi0, env_psi_pi)`` swap that makes
that version robust to per-pair envelope sign flips -- without the swap the
amplitude can go non-physically negative in some configurations.
"""

import numpy as np


def get_TI_vectors(E1_org, E2_org):
    """
    Calculate the temporal interference (TI) modulation amplitude vectors.

    Implements the sign-agnostic closed form of the Grossman et al. 2017
    TI algorithm (Hirata et al. 2024), which is exactly equivalent to the
    original preprocess-then-branch formulation but needs no explicit
    magnitude-ordering swap or acute-angle sign flip of the inputs, and no
    redundant negated copy of ``E2`` inside the cross-product-equivalent
    term: the regime boundary and both branches are expressed directly in
    terms of ``|E1.E2|`` and ``min(|E1-E2|, |E1+E2|)``.

    PHYSICAL INTERPRETATION:
    When two electric fields E1(t) = E1*cos(2πf1*t) and E2(t) = E2*cos(2πf2*t)
    with slightly different frequencies are applied simultaneously, they create
    a beating pattern. The TI vector indicates:
    - DIRECTION: Spatial direction of maximum envelope modulation
    - MAGNITUDE: Maximum envelope amplitude = 2 * effective_amplitude

    ALGORITHM (Hirata et al. 2024 sign-agnostic form, equivalent to
    Grossman et al. 2017):
    ::

        if min(|E1|,|E2|) <= sqrt(|E1.E2|):
            TIamp = 2 * min(|E1|,|E2|)
        else:
            TIamp = 2 * |E1 x E2| / min(|E1-E2|, |E1+E2|)

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
    Hirata, A. et al. (2024). Computationally efficient formula for
    temporal interference stimulation. Computers in Biology and Medicine,
    178, 108697. (sign-agnostic closed form adopted here; verified
    equivalent to this function's previous implementation to <1e-12 over
    >=1e4 random field pairs, see ``tests/test_calc_mti.py``.)

    See Also
    --------
    get_mTI_vectors : 4-channel mTI (two pairs of pairs).
    get_nTI_vectors : Generalised N-channel recursive TI.
    """
    # Input validation
    assert E1_org.shape == E2_org.shape, "E1 and E2 must have same shape"
    assert E1_org.shape[1] == 3, "Vectors must be 3D"

    E1 = E1_org
    E2 = E2_org

    normE1 = np.linalg.norm(E1, axis=1)
    normE2 = np.linalg.norm(E2, axis=1)
    dot = np.sum(E1 * E2, axis=1)

    # =================================================================
    # REGIME SELECTION -- sign-agnostic: min(|E1|,|E2|) <= sqrt(|E1.E2|)
    # =================================================================
    min_norm = np.minimum(normE1, normE2)
    regime1_mask = min_norm <= np.sqrt(np.abs(dot))

    # The "small" field, raw (un-negated); ties go to E2, matching the
    # strict '>' swap convention of the original preprocess-then-branch
    # form (so this stays exactly equivalent, not just close).
    use_E1_as_small = normE1 < normE2
    Es_raw = np.where(use_E1_as_small[:, None], E1, E2)

    # Acute-angle sign correction: this single scalar replaces the old
    # explicit array swap + E2 negation -- both branches below apply it
    # to the same "Es", so there is no separate canonicalization branch.
    sign = np.where(dot < 0, -1.0, 1.0)
    Es = sign[:, None] * Es_raw

    TI_vectors = np.zeros_like(E1)

    # =================================================================
    # REGIME 1: PARALLEL ALIGNMENT (min(|E1|,|E2|) <= sqrt(|E1.E2|))
    # =================================================================
    # Formula: TI = 2 * Es
    TI_vectors[regime1_mask] = 2.0 * Es[regime1_mask]

    # =================================================================
    # REGIME 2: OBLIQUE CONFIGURATION (min(|E1|,|E2|) > sqrt(|E1.E2|))
    # =================================================================
    # TI = 2 * component of Es perpendicular to h, where h is whichever
    # of (E1-E2), (E1+E2) has the smaller norm -- equal in magnitude to
    # 2*|E1 x E2| / min(|E1-E2|, |E1+E2|), with no negated-E2 copy needed
    # to build the cross-product-equivalent term.
    regime2_mask = ~regime1_mask
    if np.any(regime2_mask):
        a2 = E1[regime2_mask]
        b2 = E2[regime2_mask]
        dot2 = dot[regime2_mask]
        h_minus = a2 - b2
        h_plus = a2 + b2
        # Which of (E1-E2), (E1+E2) has the smaller norm is decided from
        # sign(dot) directly (dot>=0 -> h_minus, dot<0 -> h_plus; exactly
        # equivalent to comparing the two norms, since
        # |E1-E2|^2 - |E1+E2|^2 == -4*dot), NOT by comparing the two
        # computed norms themselves: |E1-E2| and |E1+E2| differ by O(dot),
        # so when dot is tiny relative to |E1|,|E2| (near-orthogonal
        # fields) that comparison loses the sign to floating-point
        # cancellation inside the two sqrt()s, while `dot` itself still
        # carries it exactly.
        use_minus = dot2 >= 0
        h = np.where(use_minus[:, None], h_minus, h_plus)
        h_norm = np.linalg.norm(h, axis=1)

        # Handle degenerate case (h = 0) by setting unit norm
        h_norm_safe = np.where(h_norm == 0, 1.0, h_norm)
        e_h = h / h_norm_safe[:, None]  # Unit vector along h

        # Project Es onto h, then subtract to get perpendicular component
        # Es_perp = Es - proj_h(Es) = Es - (Es.ĥ)ĥ
        Es_r2 = Es[regime2_mask]
        Es_parallel_component = np.sum(Es_r2 * e_h, axis=1)[:, None] * e_h
        Es_perp = Es_r2 - Es_parallel_component

        # The TI vector in regime 2 is twice the perpendicular component
        TI_vectors[regime2_mask] = 2.0 * Es_perp

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
    get_nTI_vectors : Generalised N-channel recursive TI.
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


# ─────────────────────────────────────────────────────────────────────────
# Peak instantaneous carrier-field magnitude (ported from the albantakis
# collaborator branches with attribution -- see module docstring
# "Attribution"). This is additive: a new, direction-free carrier-exposure
# metric, not an envelope/TI quantity, and does not change the behaviour of
# anything above.
# ─────────────────────────────────────────────────────────────────────────


def compute_direct_field_peak_hf(fields):
    """Peak instantaneous carrier-field magnitude across N electrode pairs.

    A direction-free, worst-case *phase-aligned* carrier-exposure metric:
    the norm of the signed vector sum of every pair field, i.e.::

        peak_hf = |sum_i field_i|

    assuming all HF carriers happen to line up at their peak instant. This
    is a genuinely different quantity from everything else in this module
    -- it is not an envelope/TI amplitude at all, it is a raw carrier
    load/exposure bound (Finding F4 in ``tracks/active/mti-focality-core.md``:
    carrier exposure is not currently reported by any TI-Toolbox optimizer).

    Note this is distinct from :func:`tit.fields.hf_peak`, which is the
    worst case *over both relative signs* of a single electrode pair
    (``max(|E1+E2|, |E1-E2|)``). This function instead sums every pair's
    field with one fixed sign, generalised to N >= 2 pairs.

    Parameters
    ----------
    fields : sequence of np.ndarray, each shape (N, 3)
        One field array per electrode pair, in the same ``[E1a, E1b, E2a,
        E2b, ...]`` convention as :func:`get_nTI_vectors`; must be an even
        count of at least 2.

    Returns
    -------
    np.ndarray, shape (N,)
        Peak instantaneous carrier-field magnitude [V/m].

    Raises
    ------
    ValueError
        If the field list has an odd length, fewer than 2 fields, or
        mismatched/invalid shapes.

    References
    ----------
    Ported with attribution from the ``albantakis`` collaborator branches
    (``mTI_testing`` commit ``925a3e99``, ``mti_formain_cleanup``); see
    module docstring "Attribution".

    See Also
    --------
    tit.fields.hf_peak : The 2-pair, sign-maximised carrier-peak metric.
    """
    return _direct_field_peak_hf_actual(fields)


def _direct_field_peak_hf_actual(fields):
    """Return the peak instantaneous magnitude of the full carrier sum.

    For the direct-field workflow we assume the HF carriers are
    phase-aligned at the peak instant, so the peak field is the norm of
    the signed vector sum of the pair fields.
    """
    arrs = _validate_field_list(fields)
    total = np.sum(np.stack(arrs, axis=0), axis=0)
    return np.linalg.norm(total, axis=1)


def _validate_field_list(fields):
    """Validate a list of (N, 3) field arrays for the direct-field metrics."""
    arrs = [np.asarray(field, dtype=np.float64) for field in fields]
    n = len(arrs)
    if n < 2 or n % 2 != 0:
        raise ValueError(
            f"Direct-field mTI requires an even number of fields >= 2, got {n}"
        )
    ref_shape = arrs[0].shape
    if len(ref_shape) != 2 or ref_shape[1] != 3:
        raise ValueError(f"Fields must have shape (N, 3), got {ref_shape}")
    for i, arr in enumerate(arrs[1:], start=2):
        if arr.shape != ref_shape:
            raise ValueError(
                f"All fields must have identical shape; field 1 has "
                f"{ref_shape}, field {i} has {arr.shape}"
            )
    return arrs

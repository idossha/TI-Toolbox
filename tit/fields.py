"""Carrier-derived high-frequency field metrics — single source of truth.

Safety-relevant quantities computed from the two carrier E-field vectors
``E1``, ``E2`` (each electrode pair's field amplitude), following Cassarà et al.
2025, *Safety Recommendations for Temporal Interference Stimulation in the
Brain, Part I* (Bioelectromagnetics 46(2), doi:10.1002/bem.22542):

``hf_peak`` — **peak carrier field** (Eq. 3)::

    hf_peak = max(|E1 + E2|, |E1 - E2|)

    The true peak of the instantaneous carrier field over one beat cycle
    (worst-case in-phase superposition).  This is the physically-realized peak,
    NOT the loose bound ``|E1| + |E2|`` — the latter is reached only where the
    two carriers are exactly collinear.  For fields within 90 deg of each other
    (the usual on-target case) it reduces to ``|E1 + E2|``.

``hf_sar`` — **heating driver, proportional to SAR**::

    hf_sar = |E1|^2 + |E2|^2

    The carriers are at different frequencies (incoherent), so their SAR/power
    adds rather than their amplitudes; tissue temperature rise is proportional
    to ``|E1|^2 + |E2|^2``, *not* ``(|E1| + |E2|)^2``.  A field-domain proxy in
    ``(V/m)^2``; the calibrated SAR is ``(sigma / 2 rho) * hf_sar`` (needs
    per-tissue conductivity and density).

These are distinct from the stimulation-relevant modulation envelope
(``TI_max`` / ``TI_normal``), which lives in SimNIBS ``TI_utils`` and
:mod:`tit.sim.TI`.

See Also
--------
tit.sim.TI : Writes hf_peak / hf_sar as volume fields on the TI mesh.
tit.source.fsaverage : Projects hf_peak / hf_sar onto fsaverage.
"""

from __future__ import annotations

import numpy as np


def _norm(E: np.ndarray) -> np.ndarray:
    """Per-row Euclidean norm of an ``(..., 3)`` vector array."""
    return np.linalg.norm(np.asarray(E, dtype=float), axis=-1)


def hf_peak(E1, E2) -> np.ndarray:
    """Peak carrier field ``max(|E1 + E2|, |E1 - E2|)`` (Cassarà 2025, Eq. 3).

    Parameters
    ----------
    E1, E2 : array-like, shape ``(..., 3)``
        The two carrier E-field vectors (per element or per node).

    Returns
    -------
    numpy.ndarray, shape ``(...,)``
        The worst-case peak carrier field magnitude.
    """
    E1 = np.asarray(E1, dtype=float)
    E2 = np.asarray(E2, dtype=float)
    return np.maximum(_norm(E1 + E2), _norm(E1 - E2))


def hf_sar(E1, E2) -> np.ndarray:
    """Incoherent carrier heating driver ``|E1|^2 + |E2|^2`` (proportional to SAR).

    Parameters
    ----------
    E1, E2 : array-like, shape ``(..., 3)``
        The two carrier E-field vectors (per element or per node).

    Returns
    -------
    numpy.ndarray, shape ``(...,)``
        ``|E1|^2 + |E2|^2`` in ``(V/m)^2`` — proportional to tissue heating.
    """
    return _norm(E1) ** 2 + _norm(E2) ** 2

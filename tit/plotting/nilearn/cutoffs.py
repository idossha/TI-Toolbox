"""Turn a :class:`~tit.plotting.nilearn.config.NilearnConfig`'s cutoffs into V/m.

Its own module rather than a helper inside ``__main__``: the rule here is arithmetic over
one array and has to be testable without importing the runner (which pulls in nibabel,
nilearn and :mod:`tit.stats`), and the same rule is what a caller would want before
submitting a job.

The failure this exists to prevent: ``min_cutoff`` used to default to a fixed ``0.3`` V/m,
which is above every real TI field -- ernie's MNI-space ``L_Insula`` ``TI_max`` peaks at
0.1385 V/m -- so the default run resolved an inverted display range and died three frames
deep inside matplotlib with ``minvalue must be less than or equal to maxvalue``
(job ``287e3e0c2eb94134``), a message that named neither the cutoff nor the data.

See Also
--------
tit.plotting.nilearn.__main__ : Resolves the cutoffs here, before any figure is drawn.
tit.reporting.generators.simulation : Uses the same p95/p99.9 pair for its own figures.
"""

from __future__ import annotations

import numpy as np

#: Percentiles of the averaged field's non-zero voxels used when a cutoff is not given.
#: The pair is ``tit.reporting.generators.simulation._compute_field_thresholds``'s --
#: "the top 5 % of the distribution, minus the top 0.1 % of outliers" -- which is the only
#: display range in this codebase that has ever been derived from real TI data.
DEFAULT_MIN_PERCENTILE = 95.0
DEFAULT_MAX_PERCENTILE = 99.9


def field_summary(values: np.ndarray) -> str:
    """One human sentence describing the field the cutoffs are being judged against."""
    if values.size == 0:
        return "the averaged field has no non-zero voxels"
    return (
        f"the averaged field spans {float(values.min()):.4f}-{float(values.max()):.4f} V/m "
        f"over {values.size} non-zero voxels "
        f"(median {float(np.percentile(values, 50.0)):.4f}, "
        f"p{DEFAULT_MIN_PERCENTILE:g} {float(np.percentile(values, DEFAULT_MIN_PERCENTILE)):.4f}, "
        f"p{DEFAULT_MAX_PERCENTILE:g} {float(np.percentile(values, DEFAULT_MAX_PERCENTILE)):.4f})"
    )


def blank_figure_warning(values: np.ndarray, min_cutoff: float) -> str | None:
    """One warning line when *min_cutoff* is at or above every voxel, else ``None``.

    :func:`resolve_cutoffs` only refuses an *empty* range (``min >= max``). A caller can
    still ask for a floor that is above the data while keeping a ceiling above that --
    which is exactly what the desktop panel's former default does (``min_cutoff`` 0.3 V/m
    with ``max_cutoff`` 5, measured in `tests/smoke/payloads/nilearn.json`): the job then
    succeeds and writes PDFs with nothing on them. That is the same failure as the crash,
    only silent, so the runner says so in the job log rather than leaving the reader to
    wonder why the brain is empty.
    """
    if values.size == 0:
        return None
    peak = float(values.max())
    if min_cutoff < peak:
        return None
    return (
        f"min_cutoff {min_cutoff:.4f} V/m is at or above the field's peak {peak:.4f} V/m, "
        f"so the figures will be blank: {field_summary(values)}. "
        f"Leave min_cutoff unset for the data-driven default "
        f"(p{DEFAULT_MIN_PERCENTILE:g} = "
        f"{float(np.percentile(values, DEFAULT_MIN_PERCENTILE)):.4f} V/m)."
    )


def resolve_cutoffs(
    values: np.ndarray,
    min_cutoff: float | None,
    max_cutoff: float | None,
    *,
    use_percentiles: bool = False,
) -> tuple[float, float]:
    """The display range in V/m, as two concrete numbers.

    Parameters
    ----------
    values : numpy.ndarray
        The averaged field's non-zero voxels (any shape; only its values matter).
    min_cutoff, max_cutoff : float or None
        The config's cutoffs. ``None`` means "take it from the data"
        (:data:`DEFAULT_MIN_PERCENTILE` / :data:`DEFAULT_MAX_PERCENTILE`).
    use_percentiles : bool, optional
        Read both given cutoffs as percentiles (0-100) of *values* instead of V/m.

    Returns
    -------
    tuple of float
        ``(min_cutoff, max_cutoff)`` in V/m, with the minimum strictly below the maximum.

    Raises
    ------
    ValueError
        If *values* is empty, or the resolved minimum is not below the resolved maximum.
        The message names the field's own range and the way out -- see the module
        docstring for the traceback it replaces.
    """
    if values.size == 0:
        raise ValueError(
            "no non-zero field values in the averaged data: nothing to threshold or plot"
        )

    if use_percentiles:
        lo_pct = DEFAULT_MIN_PERCENTILE if min_cutoff is None else float(min_cutoff)
        hi_pct = DEFAULT_MAX_PERCENTILE if max_cutoff is None else float(max_cutoff)
        lo = float(np.percentile(values, lo_pct))
        hi = float(np.percentile(values, hi_pct))
        given = (
            f"min_cutoff {lo_pct:g}% -> {lo:.4f} V/m, "
            f"max_cutoff {hi_pct:g}% -> {hi:.4f} V/m"
        )
    else:
        lo = (
            float(np.percentile(values, DEFAULT_MIN_PERCENTILE))
            if min_cutoff is None
            else float(min_cutoff)
        )
        hi = (
            float(np.percentile(values, DEFAULT_MAX_PERCENTILE))
            if max_cutoff is None
            else float(max_cutoff)
        )
        given = f"min_cutoff {lo:.4f} V/m, max_cutoff {hi:.4f} V/m"

    if lo >= hi:
        raise ValueError(
            f"display range is empty ({given}): {field_summary(values)}. "
            f"Lower min_cutoff below {hi:.4f} V/m, set use_percentiles=true to give it "
            f"as a percentile, or leave min_cutoff unset for the data-driven default "
            f"(p{DEFAULT_MIN_PERCENTILE:g} = "
            f"{float(np.percentile(values, DEFAULT_MIN_PERCENTILE)):.4f} V/m)."
        )
    return lo, hi

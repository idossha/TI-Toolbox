"""Carrier-exposure constraint helper for TI/mTI optimization (finding F4).

The carrier -- the un-modulated high-frequency field each electrode pair
delivers -- is not neurally inert (Opancar 2025 *Nat Commun*, Semenov 2025,
Peterchev 2025), and its off-target maximum sits under the electrodes. No
published TI optimizer constrains it. This module provides an opt-in
soft-constraint penalty on off-target carrier RMS, wired through
:class:`tit.opt.config.ExConfig`'s ``carrier_constraint`` /
``carrier_penalty_weight`` fields (both default to "off").

See ``tracks/active/mti-focality-core.md`` (finding F4) for the full
literature basis.

Public API
----------
carrier_constraint_penalty
    Compute the soft-constraint penalty for one measured carrier RMS value,
    logging whenever the constraint actually binds.
"""

import logging

logger = logging.getLogger(__name__)


def carrier_constraint_penalty(
    carrier_rms: float,
    carrier_constraint: float | None,
    carrier_penalty_weight: float,
    context: str = "",
) -> float:
    """Compute the soft-constraint penalty for one off-target carrier RMS value.

    Returns ``0.0`` (a no-op) when the constraint is disabled -- either
    ``carrier_constraint`` is ``None`` or ``carrier_penalty_weight`` is not
    positive, which is the default configuration. Otherwise returns a
    quadratic penalty for carrier RMS above the constraint, and logs a
    warning naming *context*, the measured value, and the limit every time
    the constraint actually binds -- so a user can see how often it is
    shaping results rather than having it silently reshape them.

    Parameters
    ----------
    carrier_rms : float
        Measured off-target carrier RMS [V/m] for one montage.
    carrier_constraint : float or None
        Maximum allowed off-target carrier RMS [V/m]. ``None`` disables
        the constraint entirely.
    carrier_penalty_weight : float
        Soft-constraint weight. Values ``<= 0`` disable the constraint
        even if ``carrier_constraint`` is set.
    context : str, optional
        Human-readable label (e.g. a montage name) included in the
        binding log message.

    Returns
    -------
    float
        ``carrier_penalty_weight * max(0, carrier_rms - carrier_constraint) ** 2``,
        or ``0.0`` if the constraint is disabled or not exceeded.
    """
    if carrier_constraint is None or carrier_penalty_weight <= 0.0:
        return 0.0

    excess = carrier_rms - carrier_constraint
    if excess <= 0.0:
        return 0.0

    penalty = carrier_penalty_weight * excess * excess
    label = f" ({context})" if context else ""
    logger.warning(
        "Carrier constraint bound%s: RMS=%.4f V/m exceeds limit=%.4f V/m "
        "by %.4f V/m -> penalty=%.4f",
        label,
        carrier_rms,
        carrier_constraint,
        excess,
        penalty,
    )
    return penalty

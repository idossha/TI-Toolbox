"""Core combinatorial algorithms for TI exhaustive search.

This module generates the full Cartesian product of electrode placements
and current-ratio splits that the exhaustive-search optimizer evaluates.

Public API
----------
generate_current_ratios
    Enumerate valid two-channel current splits.
generate_montage_combinations
    Yield ``(e1+, e1-, e2+, e2-, (ch1_mA, ch2_mA))`` tuples.
count_combinations
    Count total montage combinations without materializing them.

See Also
--------
tit.opt.ex.ex_search : Orchestrator that consumes these generators.
"""

from itertools import product

from .symmetry import (
    SYMMETRY_PAIRING_CROSS_PAIRS,
    SYMMETRY_PAIRING_WITHIN_PAIRS,
    SYMMETRY_PAIRINGS,
    format_mirror_map,
    symmetric_pair_options,
)


def generate_current_ratios(total_current, current_step, channel_limit):
    """Generate valid two-channel current splits for TI stimulation.

    Iterates from the maximum allowed channel-1 current down to the
    minimum in decrements of *current_step*, keeping both channels
    within ``[current_step, channel_limit]`` and summing to
    *total_current*.

    Parameters
    ----------
    total_current : float
        Total current budget in mA (split across two channels).
    current_step : float
        Step size in mA between successive ratio levels.
    channel_limit : float
        Maximum current allowed on a single channel in mA.

    Returns
    -------
    list of tuple of (float, float)
        Each element is ``(ch1_mA, ch2_mA)`` with
        ``ch1_mA + ch2_mA == total_current``.
    """
    ratios = []
    epsilon = current_step * 0.01

    max_ch1 = min(channel_limit, total_current - current_step)
    min_ch1 = max(total_current - channel_limit, current_step)

    current_ch1 = max_ch1
    while current_ch1 >= min_ch1 - epsilon:
        current_ch2 = total_current - current_ch1
        if (
            current_ch1 >= current_step - epsilon
            and current_ch2 >= current_step - epsilon
            and current_ch1 <= channel_limit + epsilon
            and current_ch2 <= channel_limit + epsilon
        ):
            ratios.append((current_ch1, current_ch2))
        current_ch1 -= current_step

    return ratios


def _valid_quad(combo):
    return len(set(combo)) == 4


def _within_pair_symmetric_combinations(e1_plus, e1_minus, e2_plus, e2_minus, mirror_map):
    """Each pair's minus electrode is the mirror of its plus electrode."""
    pair1 = list(symmetric_pair_options(e1_plus, e1_minus, mirror_map))
    pair2 = list(symmetric_pair_options(e2_plus, e2_minus, mirror_map))
    for (e1p, e1m), (e2p, e2m) in product(pair1, pair2):
        combo = (e1p, e1m, e2p, e2m)
        if _valid_quad(combo):
            yield combo


def _cross_pair_symmetric_combinations(e1_plus, e1_minus, e2_plus, e2_minus, mirror_map):
    """Pair 2 is the mirror image of pair 1 (``e2+ = mirror(e1+)``, ``e2- = mirror(e1-)``)."""
    plus_options = list(symmetric_pair_options(e1_plus, e2_plus, mirror_map))
    minus_options = list(symmetric_pair_options(e1_minus, e2_minus, mirror_map))
    for (e1p, e2p), (e1m, e2m) in product(plus_options, minus_options):
        combo = (e1p, e1m, e2p, e2m)
        if _valid_quad(combo):
            yield combo


def _electrode_combinations(
    e1_plus,
    e1_minus,
    e2_plus,
    e2_minus,
    all_combinations,
    symmetry_mirror_map=None,
    symmetry_pairing=SYMMETRY_PAIRING_WITHIN_PAIRS,
):
    """Yield valid electrode 4-tuples from the bucket or pool lists.

    With a *symmetry_mirror_map* (bucket mode only) the enumeration is
    restricted to left/right mirrored montages, following *symmetry_pairing*
    (``"within_pairs"`` or ``"cross_pairs"``).
    """
    if all_combinations:
        for combo in product(e1_plus, repeat=4):
            if _valid_quad(combo):
                yield combo
        return
    if symmetry_mirror_map is None:
        yield from product(e1_plus, e1_minus, e2_plus, e2_minus)
        return
    if symmetry_pairing not in SYMMETRY_PAIRINGS:
        raise ValueError(f"Unsupported ex-search symmetry pairing: {symmetry_pairing}")
    if symmetry_pairing == SYMMETRY_PAIRING_CROSS_PAIRS:
        yield from _cross_pair_symmetric_combinations(
            e1_plus, e1_minus, e2_plus, e2_minus, symmetry_mirror_map
        )
    else:
        yield from _within_pair_symmetric_combinations(
            e1_plus, e1_minus, e2_plus, e2_minus, symmetry_mirror_map
        )


def explain_zero_combinations(
    e1_plus,
    e1_minus,
    e2_plus,
    e2_minus,
    current_ratios,
    all_combinations,
    symmetry_mirror_map=None,
    symmetry_pairing=SYMMETRY_PAIRING_WITHIN_PAIRS,
):
    """Return a human-readable reason why the enumeration yields no candidate.

    Called only after :func:`count_combinations` returned zero; the message is
    meant to be shown to the user verbatim.
    """
    if not current_ratios:
        return (
            "no valid current ratios: check total_current, current_step and "
            "channel_limit (each channel needs at least one step and at most "
            "channel_limit, summing to total_current)"
        )
    if all_combinations:
        n = len(set(e1_plus))
        return f"pool mode needs at least 4 distinct electrodes, got {n}"

    buckets = {
        "e1_plus": e1_plus,
        "e1_minus": e1_minus,
        "e2_plus": e2_plus,
        "e2_minus": e2_minus,
    }
    empty = [key for key, values in buckets.items() if not values]
    if empty:
        return f"empty electrode bucket(s): {', '.join(empty)}"

    if symmetry_mirror_map is not None:
        mm = symmetry_mirror_map
        if symmetry_pairing == SYMMETRY_PAIRING_CROSS_PAIRS:
            checks = [("e1_plus", "e2_plus"), ("e1_minus", "e2_minus")]
            what = "cross_pairs: pair 2 must mirror pair 1"
        else:
            checks = [("e1_plus", "e1_minus"), ("e2_plus", "e2_minus")]
            what = "within_pairs: each pair's minus electrode must mirror its plus"
        for src, dst in checks:
            if not list(symmetric_pair_options(buckets[src], buckets[dst], mm)):
                return (
                    f"symmetric_bucket={symmetry_pairing}: no electrode in {src} "
                    f"has its mirror in {dst} ({what}; mirror map: "
                    f"{format_mirror_map(buckets[src], mm)}; {dst}: "
                    f"{', '.join(buckets[dst])})"
                )
        return (
            f"symmetric_bucket={symmetry_pairing}: every mirrored montage "
            "reuses an electrode (the four electrodes must be distinct)"
        )
    return "every montage was rejected by the enumeration filters"


def generate_montage_combinations(
    e1_plus,
    e1_minus,
    e2_plus,
    e2_minus,
    current_ratios,
    all_combinations,
    symmetry_mirror_map=None,
    symmetry_pairing=SYMMETRY_PAIRING_WITHIN_PAIRS,
):
    """Yield every electrode + current-ratio combination for evaluation.

    Parameters
    ----------
    e1_plus, e1_minus, e2_plus, e2_minus : list of str
        Electrode name lists for each bucket position.
    current_ratios : list of tuple of (float, float)
        Valid current splits from :func:`generate_current_ratios`.
    all_combinations : bool
        When *True*, treat all four lists as a single pool and require
        four distinct electrodes (permutation mode).
    symmetry_mirror_map : dict or None
        Electrode mirror map for symmetric bucket mode (see
        :mod:`tit.opt.ex.symmetry`); ``None`` disables the constraint.
    symmetry_pairing : str
        ``"within_pairs"`` or ``"cross_pairs"``.

    Yields
    ------
    tuple
        ``(e1p, e1m, e2p, e2m, (ch1_mA, ch2_mA))``.
    """
    for electrodes in _electrode_combinations(
        e1_plus,
        e1_minus,
        e2_plus,
        e2_minus,
        all_combinations,
        symmetry_mirror_map,
        symmetry_pairing,
    ):
        for ratio in current_ratios:
            yield (*electrodes, ratio)


def count_combinations(
    e1_plus,
    e1_minus,
    e2_plus,
    e2_minus,
    current_ratios,
    all_combinations,
    symmetry_mirror_map=None,
    symmetry_pairing=SYMMETRY_PAIRING_WITHIN_PAIRS,
):
    """Count total montage-x-ratio combinations without materializing them.

    Parameters
    ----------
    e1_plus, e1_minus, e2_plus, e2_minus : list of str
        Electrode name lists for each bucket position.
    current_ratios : list of tuple of (float, float)
        Valid current splits.
    all_combinations : bool
        Pool mode flag (see :func:`generate_montage_combinations`).

    Returns
    -------
    int
        Total number of ``(electrode_quad, ratio)`` combinations.
    """
    n_electrodes = sum(
        1
        for _ in _electrode_combinations(
            e1_plus,
            e1_minus,
            e2_plus,
            e2_minus,
            all_combinations,
            symmetry_mirror_map,
            symmetry_pairing,
        )
    )
    return n_electrodes * len(current_ratios)

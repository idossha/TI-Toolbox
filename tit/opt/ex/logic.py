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


def _electrode_combinations(e1_plus, e1_minus, e2_plus, e2_minus, all_combinations):
    """Yield valid electrode 4-tuples from the bucket or pool lists."""
    if all_combinations:
        for combo in product(e1_plus, repeat=4):
            if len(set(combo)) == 4:
                yield combo
    else:
        yield from product(e1_plus, e1_minus, e2_plus, e2_minus)


def generate_montage_combinations(
    e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, all_combinations
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

    Yields
    ------
    tuple
        ``(e1p, e1m, e2p, e2m, (ch1_mA, ch2_mA))``.
    """
    for electrodes in _electrode_combinations(
        e1_plus, e1_minus, e2_plus, e2_minus, all_combinations
    ):
        for ratio in current_ratios:
            yield (*electrodes, ratio)


def count_combinations(
    e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, all_combinations
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
            e1_plus, e1_minus, e2_plus, e2_minus, all_combinations
        )
    )
    return n_electrodes * len(current_ratios)

"""
Core algorithms for TI Exhaustive Search.

Combinatorial logic for generating current ratios and electrode montages.
"""

from itertools import product


def generate_current_ratios(total_current, current_step, channel_limit):
    """Generate valid current ratio pairs for TI stimulation.

    Returns:
        list of (ch1_current, ch2_current) tuples
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
    """Yield valid electrode 4-tuples."""
    if all_combinations:
        for combo in product(e1_plus, repeat=4):
            if len(set(combo)) == 4:
                yield combo
    else:
        yield from product(e1_plus, e1_minus, e2_plus, e2_minus)


def generate_montage_combinations(
    e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, all_combinations
):
    """Yield (e1p, e1m, e2p, e2m, (ch1_mA, ch2_mA)) tuples."""
    for electrodes in _electrode_combinations(
        e1_plus, e1_minus, e2_plus, e2_minus, all_combinations
    ):
        for ratio in current_ratios:
            yield (*electrodes, ratio)


def count_combinations(
    e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, all_combinations
):
    """Count total montage combinations without materializing them."""
    n_electrodes = sum(
        1
        for _ in _electrode_combinations(
            e1_plus, e1_minus, e2_plus, e2_minus, all_combinations
        )
    )
    return n_electrodes * len(current_ratios)

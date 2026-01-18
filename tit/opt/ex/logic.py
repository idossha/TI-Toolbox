"""
Core algorithms for TI Exhaustive Search.

This module contains the combinatorial algorithms used for generating
current ratios and electrode montages for optimization.
"""

from itertools import product


def generate_current_ratios(total_current, current_step, channel_limit):
    """Generate valid current ratio combinations for TI stimulation.

    Args:
        total_current (float): Total current in milliamps
        current_step (float): Step size for current increments in milliamps
        channel_limit (float): Maximum current per channel in milliamps

    Returns:
        tuple: (ratios, channel_limit_exceeded)
            - ratios: List of (ch1_current, ch2_current) tuples
            - channel_limit_exceeded: Boolean indicating if limit was exceeded
    """
    ratios, epsilon = [], current_step * 0.01
    min_current = max(total_current - channel_limit, current_step)
    if min_current < current_step - epsilon:
        min_current = current_step
        channel_limit_exceeded = True
    else:
        channel_limit_exceeded = False

    current_ch1 = channel_limit
    while current_ch1 >= min_current - epsilon:
        current_ch2 = total_current - current_ch1
        if (
            current_ch1 <= channel_limit + epsilon
            and current_ch2 <= channel_limit + epsilon
            and current_ch1 >= current_step - epsilon
            and current_ch2 >= current_step - epsilon
        ):
            ratios.append((current_ch1, current_ch2))
        current_ch1 -= current_step

    return ratios, channel_limit_exceeded


def calculate_total_combinations(
    e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, all_combinations
):
    """Calculate total number of montage combinations to be tested.

    Args:
        e1_plus (list): E1+ electrode names
        e1_minus (list): E1- electrode names
        e2_plus (list): E2+ electrode names
        e2_minus (list): E2- electrode names
        current_ratios (list): List of (ch1_current, ch2_current) tuples
        all_combinations (bool): If True, test all valid electrode combinations

    Returns:
        int: Total number of combinations to test
    """
    if all_combinations:
        electrode_combinations = [
            (e1p, e1m, e2p, e2m)
            for e1p, e1m, e2p, e2m in product(e1_plus, repeat=4)
            if len(set([e1p, e1m, e2p, e2m])) == 4
        ]
        return len(electrode_combinations) * len(current_ratios)
    return (
        len(e1_plus)
        * len(e1_minus)
        * len(e2_plus)
        * len(e2_minus)
        * len(current_ratios)
    )


def generate_montage_combinations(
    e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, all_combinations
):
    """Generate electrode montage combinations for testing.

    Args:
        e1_plus (list): E1+ electrode names
        e1_minus (list): E1- electrode names
        e2_plus (list): E2+ electrode names
        e2_minus (list): E2- electrode names
        current_ratios (list): List of (ch1_current, ch2_current) tuples
        all_combinations (bool): If True, generate all valid electrode combinations

    Yields:
        tuple: (e1_plus, e1_minus, e2_plus, e2_minus, current_ch1, current_ch2)
    """
    if all_combinations:
        electrode_combinations = [
            (e1p, e1m, e2p, e2m)
            for e1p, e1m, e2p, e2m in product(e1_plus, repeat=4)
            if len(set([e1p, e1m, e2p, e2m])) == 4
        ]
        for electrode_combo in electrode_combinations:
            for current_ratio in current_ratios:
                yield (*electrode_combo, current_ratio)
    else:
        for combo in product(e1_plus, e1_minus, e2_plus, e2_minus, current_ratios):
            yield combo

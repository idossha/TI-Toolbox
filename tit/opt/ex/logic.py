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

SYMMETRY_LAYOUT_AUTO = "auto"
SYMMETRY_LAYOUT_PAIRED_BUCKETS = "paired_buckets"
SYMMETRY_LAYOUT_CROSS_CHANNELS = "cross_channels"
SYMMETRY_LAYOUTS = {
    SYMMETRY_LAYOUT_AUTO,
    SYMMETRY_LAYOUT_PAIRED_BUCKETS,
    SYMMETRY_LAYOUT_CROSS_CHANNELS,
}


def _valid_channel_pairs(combo):
    """Return True when each stimulation channel has two distinct electrodes."""
    e1_plus, e1_minus, e2_plus, e2_minus = combo
    return e1_plus != e1_minus and e2_plus != e2_minus


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


def _symmetric_bucket_pairs(left_bucket, right_bucket, mirror_map):
    """Yield electrodes from *left_bucket* whose mirror is present on the right."""
    right_set = set(right_bucket)
    seen = set()
    for electrode in left_bucket:
        mirror = mirror_map.get(electrode)
        pair = (electrode, mirror)
        if mirror in right_set and electrode != mirror and pair not in seen:
            seen.add(pair)
            yield pair


def _paired_bucket_symmetry_combinations(
    e1_plus,
    e1_minus,
    e2_plus,
    e2_minus,
    mirror_map,
):
    """Yield quadrant-style symmetric tuples: E1+<->E1-, E2+<->E2-."""
    anterior_pairs = list(_symmetric_bucket_pairs(e1_plus, e1_minus, mirror_map))
    posterior_pairs = list(_symmetric_bucket_pairs(e2_plus, e2_minus, mirror_map))
    for (e1p, e1m), (e2p, e2m) in product(anterior_pairs, posterior_pairs):
        combo = (e1p, e1m, e2p, e2m)
        if _valid_channel_pairs(combo):
            yield combo


def _cross_channel_symmetry_combinations(
    e1_plus,
    e1_minus,
    e2_plus,
    e2_minus,
    mirror_map,
):
    """Yield left/right-channel symmetric tuples: E1 side mirrors E2 side."""
    anterior_pairs = list(_symmetric_bucket_pairs(e1_plus, e2_plus, mirror_map))
    posterior_pairs = list(_symmetric_bucket_pairs(e1_minus, e2_minus, mirror_map))
    for (e1p, e2p), (e1m, e2m) in product(anterior_pairs, posterior_pairs):
        combo = (e1p, e1m, e2p, e2m)
        if _valid_channel_pairs(combo):
            yield combo


def _symmetric_electrode_combinations(
    e1_plus,
    e1_minus,
    e2_plus,
    e2_minus,
    mirror_map,
    symmetry_layout,
):
    """Yield symmetric bucket tuples using the requested or auto-detected layout."""
    if symmetry_layout not in SYMMETRY_LAYOUTS:
        raise ValueError(f"Unsupported symmetry layout: {symmetry_layout}")

    paired = lambda: list(
        _paired_bucket_symmetry_combinations(
            e1_plus, e1_minus, e2_plus, e2_minus, mirror_map
        )
    )
    crossed = lambda: list(
        _cross_channel_symmetry_combinations(
            e1_plus, e1_minus, e2_plus, e2_minus, mirror_map
        )
    )

    if symmetry_layout == SYMMETRY_LAYOUT_PAIRED_BUCKETS:
        yield from paired()
    elif symmetry_layout == SYMMETRY_LAYOUT_CROSS_CHANNELS:
        yield from crossed()
    else:
        paired_combos = paired()
        crossed_combos = crossed()
        yield from (
            crossed_combos
            if len(crossed_combos) > len(paired_combos)
            else paired_combos
        )


def _electrode_combinations(
    e1_plus,
    e1_minus,
    e2_plus,
    e2_minus,
    all_combinations,
    symmetry_mirror_map=None,
    symmetry_layout=SYMMETRY_LAYOUT_AUTO,
):
    """Yield valid electrode 4-tuples from the bucket or pool lists."""
    if all_combinations:
        for combo in product(e1_plus, repeat=4):
            if len(set(combo)) == 4:
                yield combo
    elif symmetry_mirror_map is not None:
        yield from _symmetric_electrode_combinations(
            e1_plus,
            e1_minus,
            e2_plus,
            e2_minus,
            symmetry_mirror_map,
            symmetry_layout,
        )
    else:
        for combo in product(e1_plus, e1_minus, e2_plus, e2_minus):
            if _valid_channel_pairs(combo):
                yield combo


def generate_montage_combinations(
    e1_plus,
    e1_minus,
    e2_plus,
    e2_minus,
    current_ratios,
    all_combinations,
    symmetry_mirror_map=None,
    symmetry_layout=SYMMETRY_LAYOUT_AUTO,
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
        Optional electrode -> mirrored electrode map.  When provided in
        bucketed mode, only E1+/E1- and E2+/E2- mirrored pairs are evaluated.
    symmetry_layout : str
        ``"paired_buckets"`` for quadrant buckets, ``"cross_channels"`` for
        left/right channel buckets, or ``"auto"`` to choose the richer layout.

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
        symmetry_layout,
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
    symmetry_layout=SYMMETRY_LAYOUT_AUTO,
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
    symmetry_mirror_map : dict or None
        Optional electrode -> mirrored electrode map for symmetric bucket mode.
    symmetry_layout : str
        Symmetric bucket layout mode; see :func:`generate_montage_combinations`.

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
            symmetry_layout,
        )
    )
    return n_electrodes * len(current_ratios)

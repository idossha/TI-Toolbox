"""Core combinatorial algorithms for TI exhaustive search.

This module enumerates the montages and current-ratio splits the
exhaustive-search optimizer evaluates: every montage of four different
electrodes, crossed with every split. Each physical montage is taken once,
since the TI envelope ignores channel polarity (and channel order, when the
split list is its own mirror): bucket mode keeps one tuple of the bucket
product per montage; pool mode takes three pairings per four-electrode set,
in both channel orders only when the split list is not its own mirror.

Public API
----------
generate_current_ratios
    Enumerate valid two-channel current splits.
count_combinations
    Count total montage combinations without materializing them.
format_current_mA
    The text a current split is written as (result keys, ``final_output.csv``).

See Also
--------
tit.opt.ex.ex_search : Orchestrator that consumes these generators.
"""

from itertools import combinations, product
from math import comb

from .symmetry import (
    SYMMETRY_PAIRING_CROSS_PAIRS,
    SYMMETRY_PAIRING_WITHIN_PAIRS,
    SYMMETRY_PAIRINGS,
    format_mirror_map,
    symmetric_pair_options,
)


def generate_current_ratios(total_current, current_step, channel_limit=None):
    """Generate valid two-channel current splits for TI stimulation.

    With no *channel_limit* the only split is the balanced one,
    ``(total_current / 2, total_current / 2)``: an exhaustive leadfield
    study found the best montage almost always best at 1:1, so a sweep
    rarely pays for its cost. With a limit, iterates from the maximum
    allowed channel-1 current down to the minimum in decrements of
    *current_step*, keeping both channels within
    ``[current_step, channel_limit]`` and summing to *total_current*.

    Parameters
    ----------
    total_current : float
        Total current budget in mA (split across two channels).
    current_step : float
        Step size in mA between successive ratio levels.
    channel_limit : float or None
        Maximum current allowed on a single channel in mA; ``None``
        (default) means the single balanced split.

    Returns
    -------
    list of tuple of (float, float)
        Each element is ``(ch1_mA, ch2_mA)`` with
        ``ch1_mA + ch2_mA == total_current``.
    """
    if channel_limit is None:
        return [(total_current / 2, total_current / 2)]

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


_SPLIT_TOLERANCE_MA = 1e-9


def format_current_mA(value):
    """Current in mA as written in result keys and ``final_output.csv``.

    Enough decimals that two splits of one sweep never print alike (a ``.1f``
    key merged 1.95/0.05 with 1.9/0.1), without the floating-point tail of the
    sweep's repeated subtraction: ``1.0``, ``0.25``, ``1.95``.
    """
    text = f"{float(value):.10f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def ratios_mirror_symmetric(current_ratios):
    """True when the split list contains ``(b, a)`` for every ``(a, b)``.

    The TI envelope is symmetric in its two channels, so channel 1 on pair P at
    ``a`` with channel 2 on pair Q at ``b`` is the same stimulation as the swapped
    order at ``(b, a)``. The list from :func:`generate_current_ratios` is sorted by
    descending channel-1 current, so it is its own mirror exactly when entry ``i``
    channel 1 equals entry ``-1-i`` channel 2.
    """
    ratios = list(current_ratios)
    return all(
        abs(ratios[i][0] - ratios[-1 - i][1]) <= _SPLIT_TOLERANCE_MA
        for i in range(len(ratios))
    )


def _valid_quad(combo):
    return len(set(combo)) == 4


def _distinct_product(buckets):
    """``itertools.product(*buckets)`` restricted to tuples of distinct electrodes.

    Same order as the filtered product; a label listed twice in one bucket is
    one electrode. Backtracking skips used electrodes instead of generating and
    discarding them.
    """
    lists = [list(dict.fromkeys(bucket)) for bucket in buckets]
    chosen = []

    def walk(level):
        if level == len(lists):
            yield tuple(chosen)
            return
        for electrode in lists[level]:
            if electrode in chosen:
                continue
            chosen.append(electrode)
            yield from walk(level + 1)
            chosen.pop()

    yield from walk(0)


def _one_per_montage(quads, buckets, both_channel_orders, mirrored=None):
    """Keep one of *quads* per physical montage.

    A tuple is kept when it is the smallest of its equivalent tuples (either
    channel's polarity flipped; the channels swapped too when not
    *both_channel_orders*) that the enumeration also holds -- no seen-set. A
    twin is held when each electrode is in its bucket and, for a symmetric
    search, *mirrored(a, b, c, d)* accepts it.
    """
    sets = [set(bucket) for bucket in buckets]
    for quad in quads:
        a, b, c, d = quad
        twins = [(b, a, c, d), (a, b, d, c), (b, a, d, c)]
        if not both_channel_orders:
            twins += [(c, d, a, b), (d, c, a, b), (c, d, b, a), (d, c, b, a)]
        if not any(
            twin < quad
            and all(e in s for e, s in zip(twin, sets))
            and (mirrored is None or mirrored(*twin))
            for twin in twins
        ):
            yield quad


def _bucket_montages(buckets, both_channel_orders):
    """One tuple of the distinct bucket product per physical montage."""
    return _one_per_montage(_distinct_product(buckets), buckets, both_channel_orders)


def _pool_montages(pool, both_channel_orders):
    """One ``(e1+, e1-, e2+, e2-)`` per physical montage of a pool.

    TI_max is unchanged when either channel's polarity flips, so each pair is
    taken once (pool order: first-listed electrode is ``+``); four electrodes
    split into pairs three ways; the channel order matters only when the split
    list is not its own mirror (:func:`ratios_mirror_symmetric`).
    """
    labels = list(dict.fromkeys(pool))
    for a, b, c, d in combinations(labels, 4):
        for (p1, p2), (q1, q2) in (
            ((a, b), (c, d)),
            ((a, c), (b, d)),
            ((a, d), (b, c)),
        ):
            yield (p1, p2, q1, q2)
            if both_channel_orders:
                yield (q1, q2, p1, p2)


def _within_pair_symmetric_combinations(
    e1_plus, e1_minus, e2_plus, e2_minus, mirror_map
):
    """Each pair's minus electrode is the mirror of its plus electrode."""
    pair1 = list(symmetric_pair_options(e1_plus, e1_minus, mirror_map))
    pair2 = list(symmetric_pair_options(e2_plus, e2_minus, mirror_map))
    for (e1p, e1m), (e2p, e2m) in product(pair1, pair2):
        combo = (e1p, e1m, e2p, e2m)
        if _valid_quad(combo):
            yield combo


def _cross_pair_symmetric_combinations(
    e1_plus, e1_minus, e2_plus, e2_minus, mirror_map
):
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
    both_channel_orders=True,
):
    """Yield valid electrode 4-tuples from the bucket or pool lists.

    Every tuple has four distinct electrodes: a channel whose plus and minus
    electrode coincide carries no current, and one electrode is never shared by
    the two channels (as in m-ex-search, which needs all eight distinct).

    Bucket and pool mode (*all_combinations*) yield one tuple per physical
    montage, in both channel orders only when *both_channel_orders* (see
    :func:`_bucket_montages`, :func:`_pool_montages`). With a
    *symmetry_mirror_map* (bucket mode only) the enumeration is restricted to
    left/right mirrored montages, following *symmetry_pairing*
    (``"within_pairs"`` or ``"cross_pairs"``), again one per physical montage.
    """
    if all_combinations:
        yield from _pool_montages(e1_plus, both_channel_orders)
        return
    if symmetry_mirror_map is None:
        yield from _bucket_montages(
            (e1_plus, e1_minus, e2_plus, e2_minus), both_channel_orders
        )
        return
    if symmetry_pairing not in SYMMETRY_PAIRINGS:
        raise ValueError(f"Unsupported ex-search symmetry pairing: {symmetry_pairing}")
    mm = symmetry_mirror_map
    if symmetry_pairing == SYMMETRY_PAIRING_CROSS_PAIRS:
        quads = _cross_pair_symmetric_combinations(
            e1_plus, e1_minus, e2_plus, e2_minus, mm
        )

        def mirrored(a, b, c, d):
            return mm.get(a) == c and mm.get(b) == d

    else:
        quads = _within_pair_symmetric_combinations(
            e1_plus, e1_minus, e2_plus, e2_minus, mm
        )

        def mirrored(a, b, c, d):
            return mm.get(a) == b and mm.get(c) == d

    yield from _one_per_montage(
        quads,
        (e1_plus, e1_minus, e2_plus, e2_minus),
        both_channel_orders,
        mirrored,
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
    return (
        "every bucket combination reuses an electrode (the four electrodes must "
        "be distinct: a channel cannot start and end on one electrode, and the "
        "two channels cannot share one)"
    )


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
        Pool mode flag (see :func:`_pool_montages`).

    Returns
    -------
    int
        Total number of ``(electrode_quad, ratio)`` combinations.
    """
    if all_combinations:
        orders = 1 if ratios_mirror_symmetric(current_ratios) else 2
        return comb(len(dict.fromkeys(e1_plus)), 4) * 3 * orders * len(current_ratios)
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
            both_channel_orders=not ratios_mirror_symmetric(current_ratios),
        )
    )
    return n_electrodes * len(current_ratios)

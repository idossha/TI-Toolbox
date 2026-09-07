"""Combination helpers for multipolar exhaustive search.

Pure Python, no ``tit`` dependencies -- ported from collaborator Larissa
Albantakis's branch ``alba/ex-search-multipolar`` as-is.
"""

from itertools import combinations, permutations, product
from math import comb

from tit.opt.ex.symmetry import (
    SYMMETRY_PAIRING_CROSS_PAIRS,
    SYMMETRY_PAIRING_WITHIN_PAIRS,
    SYMMETRY_PAIRINGS,
    format_mirror_map,
    symmetric_pair_options as _symmetric_pair_options,
)

MEX_BUCKET_KEYS = (
    "e1_plus",
    "e1_minus",
    "e2_plus",
    "e2_minus",
    "e3_plus",
    "e3_minus",
    "e4_plus",
    "e4_minus",
)

_CROSS_PAIR_CHECKS = (
    ("e1_plus", "e3_plus"),
    ("e1_minus", "e3_minus"),
    ("e2_plus", "e4_plus"),
    ("e2_minus", "e4_minus"),
)
_WITHIN_PAIR_CHECKS = tuple(
    (f"e{idx}_plus", f"e{idx}_minus") for idx in range(1, 5)
)


def _valid_multipolar_tuple(electrodes):
    """Return True when all eight electrode positions are unique."""
    return len(electrodes) == 8 and len(set(electrodes)) == 8


def explain_zero_multipolar_combinations(
    buckets_or_pool,
    all_combinations=False,
    symmetry_mirror_map=None,
    symmetry_pairing=SYMMETRY_PAIRING_WITHIN_PAIRS,
):
    """Return a human-readable reason why the enumeration yields no candidate."""
    if all_combinations:
        n = len(dict.fromkeys(buckets_or_pool))
        return f"pool mode needs at least 8 distinct electrodes, got {n}"
    buckets = buckets_or_pool
    empty = [key for key in MEX_BUCKET_KEYS if not buckets.get(key)]
    if empty:
        return f"empty electrode bucket(s): {', '.join(empty)}"
    if symmetry_mirror_map is not None:
        mm = symmetry_mirror_map
        if symmetry_pairing == SYMMETRY_PAIRING_CROSS_PAIRS:
            checks = _CROSS_PAIR_CHECKS
            what = "cross_pairs: pairs 3/4 must mirror pairs 1/2"
        else:
            checks = _WITHIN_PAIR_CHECKS
            what = "within_pairs: each pair's minus electrode must mirror its plus"
        for src, dst in checks:
            if not list(_symmetric_pair_options(buckets[src], buckets[dst], mm)):
                return (
                    f"symmetric_bucket={symmetry_pairing}: no electrode in {src} "
                    f"has its mirror in {dst} ({what}; mirror map: "
                    f"{format_mirror_map(buckets[src], mm)}; {dst}: "
                    f"{', '.join(buckets[dst])})"
                )
        return (
            f"symmetric_bucket={symmetry_pairing}: every mirrored montage "
            "reuses an electrode (the eight electrodes must be distinct)"
        )
    return "every bucket product reuses an electrode (the eight electrodes must be distinct)"


def _within_pair_symmetry_combinations(buckets, mirror_map):
    pair_options = [
        list(
            _symmetric_pair_options(
                buckets[f"e{idx}_plus"],
                buckets[f"e{idx}_minus"],
                mirror_map,
            )
        )
        for idx in range(1, 5)
    ]
    for pairs in product(*pair_options):
        combo = tuple(electrode for pair in pairs for electrode in pair)
        if _valid_multipolar_tuple(combo):
            yield combo


def _cross_pair_symmetry_combinations(buckets, mirror_map):
    e1p_e3p = list(
        _symmetric_pair_options(buckets["e1_plus"], buckets["e3_plus"], mirror_map)
    )
    e1m_e3m = list(
        _symmetric_pair_options(buckets["e1_minus"], buckets["e3_minus"], mirror_map)
    )
    e2p_e4p = list(
        _symmetric_pair_options(buckets["e2_plus"], buckets["e4_plus"], mirror_map)
    )
    e2m_e4m = list(
        _symmetric_pair_options(buckets["e2_minus"], buckets["e4_minus"], mirror_map)
    )
    for (e1p, e3p), (e1m, e3m), (e2p, e4p), (e2m, e4m) in product(
        e1p_e3p,
        e1m_e3m,
        e2p_e4p,
        e2m_e4m,
    ):
        combo = (e1p, e1m, e2p, e2m, e3p, e3m, e4p, e4m)
        if _valid_multipolar_tuple(combo):
            yield combo


def _bucket_electrode_combinations(
    buckets,
    symmetry_mirror_map=None,
    symmetry_pairing=SYMMETRY_PAIRING_WITHIN_PAIRS,
):
    if symmetry_mirror_map is None:
        for combo in product(*(buckets[key] for key in MEX_BUCKET_KEYS)):
            if _valid_multipolar_tuple(combo):
                yield combo
        return

    if symmetry_pairing not in SYMMETRY_PAIRINGS:
        raise ValueError(
            f"Unsupported m-ex-search symmetry pairing: {symmetry_pairing}"
        )
    if symmetry_pairing == SYMMETRY_PAIRING_CROSS_PAIRS:
        yield from _cross_pair_symmetry_combinations(buckets, symmetry_mirror_map)
    else:
        yield from _within_pair_symmetry_combinations(buckets, symmetry_mirror_map)


# ---------------------------------------------------------------------------
# Pool mode: enumerate one montage per symmetry class
# ---------------------------------------------------------------------------
#
# A montage is four ordered electrode pairs in four slots. The field of pair
# ``k`` is negated by swapping its two electrodes, and ``tit.calc``'s mTI
# envelope (``P = 0.5*sum(a_k^2 + b_k^2)``, ``Q = |sum_k a_k*b_k|`` over
# beating channels, with ``psi=0``) is invariant under exactly:
#
# * permuting pairs inside one carrier group (their fields are summed),
# * swapping a channel's two groups (``a_k*b_k`` is symmetric),
# * swapping channels of identical shape (``psi=None`` -> all phase-aligned),
# * flipping the polarity of whole groups, provided every beating channel
#   ends up with the same product sign ``s_ka*s_kb`` (``Q`` is an absolute
#   value; a lone flip inside a beating channel is a real ``pi`` envelope
#   phase shift and is NOT a symmetry).
#
# ``permutations(pool, 8)`` visits each class ``|H| * |S|`` times (64x for
# the default two independent channels), so pool mode instead builds one
# canonical representative per class: choose 8 electrodes, partition them
# into 4 unordered pairs, place the (sorted) pairs into slots via one fixed
# slot map per coset of the slot-automorphism group ``H``, then fix the
# orientation of one representative pair per group (minus the constraint
# above) and enumerate the remaining polarities.

_DEFAULT_CHANNELS = (((0,), (1,)), ((2,), (3,)))


def _normalize_channels(channels):
    """Return ``channels`` as a tuple of ``(group_a, group_b)`` index tuples."""
    if channels is None:
        return _DEFAULT_CHANNELS
    norm = tuple((tuple(a), tuple(b)) for a, b in channels)
    used = sorted(i for a, b in norm for i in a + b)
    if used != [0, 1, 2, 3]:
        raise ValueError(
            "channels must reference each of the four pair slots 0-3 exactly "
            f"once (got {used})"
        )
    return norm


def _slot_automorphisms(channels):
    """Permutations of the four pair slots that preserve the channel structure."""
    shape = {frozenset((frozenset(a), frozenset(b))) for a, b in channels}
    autos = []
    for perm in permutations(range(4)):
        image = {
            frozenset((frozenset(perm[i] for i in a), frozenset(perm[i] for i in b)))
            for a, b in channels
        }
        if image == shape:
            autos.append(perm)
    return autos


def _canonical_slot_maps(channels):
    """One ``slot -> pair rank`` map per coset of the slot automorphisms.

    With the four pairs of a montage sorted (ranks 0-3), every placement of
    those pairs into slots is some map; two maps related by an automorphism
    yield equivalent montages, so only the lexicographically smallest of
    each orbit is kept. Independent of the electrodes involved.
    """
    autos = _slot_automorphisms(channels)
    keep = []
    for ranks in permutations(range(4)):
        orbit_min = min(tuple(ranks[perm[slot]] for slot in range(4)) for perm in autos)
        if ranks == orbit_min:
            keep.append(ranks)
    return keep


def _free_polarity_slots(channels):
    """Slots whose pair orientation is NOT fixed by group-flip symmetry."""
    fixed = set()
    beating_seen = False
    for group_a, group_b in channels:
        beating = bool(group_a) and bool(group_b)
        if group_a:
            fixed.add(group_a[0])
        if group_b and (not beating or not beating_seen):
            fixed.add(group_b[0])
        beating_seen = beating_seen or beating
    return [slot for slot in range(4) if slot not in fixed]


def _pair_partitions(items):
    """Yield every partition of ``items`` (even length) into unordered pairs."""
    if not items:
        yield ()
        return
    first, rest = items[0], items[1:]
    for idx, other in enumerate(rest):
        remaining = rest[:idx] + rest[idx + 1 :]
        for tail in _pair_partitions(remaining):
            yield ((first, other),) + tail


def _pool_electrode_combinations(pool, channels=None):
    pool = list(dict.fromkeys(pool))
    channels = _normalize_channels(channels)
    slot_maps = _canonical_slot_maps(channels)
    free_slots = _free_polarity_slots(channels)
    flip_patterns = list(product((False, True), repeat=len(free_slots)))
    for chosen in combinations(range(len(pool)), 8):
        for pairs in _pair_partitions(list(chosen)):
            ranked = sorted(pairs)
            for ranks in slot_maps:
                placed = [ranked[ranks[slot]] for slot in range(4)]
                for flips in flip_patterns:
                    montage = list(placed)
                    for slot, flip in zip(free_slots, flips):
                        if flip:
                            montage[slot] = montage[slot][::-1]
                    yield tuple(pool[i] for pair in montage for i in pair)


def count_pool_combinations(pool, channels=None):
    """Closed-form count of :func:`_pool_electrode_combinations`."""
    n = len(dict.fromkeys(pool))
    channels = _normalize_channels(channels)
    per_set = 105 * len(_canonical_slot_maps(channels))
    per_set *= 2 ** len(_free_polarity_slots(channels))
    return comb(n, 8) * per_set


def generate_multipolar_combinations(
    buckets_or_pool,
    all_combinations=False,
    symmetry_mirror_map=None,
    symmetry_pairing=SYMMETRY_PAIRING_WITHIN_PAIRS,
    channels=None,
):
    """Yield valid eight-electrode candidates for four bipolar pairs.

    Bucket mode is the Cartesian product of the eight buckets. Pool mode
    (``all_combinations=True``) yields one montage per class of montages
    that ``tit.calc.get_TI_vectors`` scores identically under the given
    carrier ``channels`` (``None`` = two independent TI channels).
    """
    if all_combinations:
        yield from _pool_electrode_combinations(buckets_or_pool, channels=channels)
    else:
        yield from _bucket_electrode_combinations(
            buckets_or_pool,
            symmetry_mirror_map=symmetry_mirror_map,
            symmetry_pairing=symmetry_pairing,
        )


def count_multipolar_combinations(
    buckets_or_pool,
    all_combinations=False,
    symmetry_mirror_map=None,
    symmetry_pairing=SYMMETRY_PAIRING_WITHIN_PAIRS,
    channels=None,
):
    """Count multipolar candidates without materializing them as a list."""
    if all_combinations:
        return count_pool_combinations(buckets_or_pool, channels=channels)
    return sum(
        1
        for _ in generate_multipolar_combinations(
            buckets_or_pool,
            all_combinations=all_combinations,
            symmetry_mirror_map=symmetry_mirror_map,
            symmetry_pairing=symmetry_pairing,
        )
    )

"""Combination helpers for multipolar exhaustive search.

Pure Python, no ``tit`` dependencies -- ported from collaborator Larissa
Albantakis's branch ``alba/ex-search-multipolar`` as-is.
"""

from itertools import permutations, product

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

SYMMETRY_PAIRING_WITHIN_PAIRS = "within_pairs"
SYMMETRY_PAIRING_CROSS_PAIRS = "cross_pairs"
SYMMETRY_PAIRINGS = {
    SYMMETRY_PAIRING_WITHIN_PAIRS,
    SYMMETRY_PAIRING_CROSS_PAIRS,
}


def _valid_multipolar_tuple(electrodes):
    """Return True when all eight electrode positions are unique."""
    return len(electrodes) == 8 and len(set(electrodes)) == 8


def _symmetric_pair_options(plus_bucket, minus_bucket, mirror_map):
    minus_set = set(minus_bucket)
    seen = set()
    for plus in plus_bucket:
        minus = mirror_map.get(plus)
        pair = (plus, minus)
        if minus in minus_set and plus != minus and pair not in seen:
            seen.add(pair)
            yield pair


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


def _pool_electrode_combinations(pool):
    for combo in permutations(pool, 8):
        yield combo


def generate_multipolar_combinations(
    buckets_or_pool,
    all_combinations=False,
    symmetry_mirror_map=None,
    symmetry_pairing=SYMMETRY_PAIRING_WITHIN_PAIRS,
):
    """Yield valid eight-electrode candidates for four bipolar pairs."""
    if all_combinations:
        yield from _pool_electrode_combinations(buckets_or_pool)
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
):
    """Count multipolar candidates without materializing them as a list."""
    return sum(
        1
        for _ in generate_multipolar_combinations(
            buckets_or_pool,
            all_combinations=all_combinations,
            symmetry_mirror_map=symmetry_mirror_map,
            symmetry_pairing=symmetry_pairing,
        )
    )

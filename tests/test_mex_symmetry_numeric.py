"""mEx pool mode keeps one montage per class of montages the mTI envelope scores identically.

What this pins (2026-10-22): ``tit.opt.mex.logic._pool_electrode_combinations`` claims (module
comment above ``_DEFAULT_CHANNELS``) that the envelope of ``tit.calc.get_TI_vectors`` -- with the
fields ``[pair1, pair2, pair3, pair4]``, carrier 1 = pairs 1+2, carrier 2 = pairs 3+4 -- is
unchanged by exactly 64 operations on a montage, so ``permutations(pool, 8)`` (40 320 orderings of
8 electrodes) collapses to 40 320 / 64 = 630 canonical montages. The existing tests check that
claim as algebra over index tuples; here it is checked against envelope VALUES on random fields:

* the 64 images of every canonical montage score the same as it, element by element;
* those images are exactly the 40 320 orderings, so the set of distinct values over
  ``permutations(pool, 8)`` equals the set over the 630 canonical montages;
* the 630 canonical montages score pairwise differently (none is redundant);
* a lone polarity flip inside a beating channel is NOT a symmetry: it changes the value;
* ``MExSearchEngine.compute_mti_field`` (the engine's own field assembly) agrees on the images.

The symmetry group is written out here from the physics, not read from ``_slot_automorphisms``:
the envelope is ``sqrt2*(sqrt(P+Q) - sqrt(P-Q))`` with ``P = 0.5*sum_k(a_k^2+b_k^2)`` and
``Q = |a_1 b_1 + a_2 b_2|`` (``tit/calc.py``, ``_mti_modulation_depth``). ``P`` ignores order and
sign; ``Q`` is unchanged by swapping the two pairs of one carrier, swapping the two carriers, and
flipping pair signs ``s`` with ``s1*s2 == s3*s4`` (both products flip together or neither): 8 slot
permutations x 8 sign patterns = 64.

Physics bounds per element, from the same form: ``0 <= MD`` and, since ``|a_k| <= |E_ka|`` and
``Q <= P``, ``MD <= sqrt2*sqrt(2P) <= sqrt(2*sum_k(|E_ka|^2 + |E_kb|^2))``. With carrier 2 zero
the envelope is K=1 TI: ``2*min(|a|,|b|)`` for collinear fields (Grossman et al. 2017).

Tolerances: images agree to 1e-9 V/m (measured worst 5e-12: the same sums in another order).
The K=2 path is a direction search (192 Fibonacci directions + 3 local refinement rounds) that
evaluates the exact envelope at the directions it samples, so it never exceeds the true maximum
and falls short of it by the sampling error: measured <= 1.6e-5 relative, bounded here at 1e-4.

Host leg: the NumPy sweep (numba is absent on the host). The numba kernel leg is
``tests/numerical/test_mti_kernel_symmetry.py``. Reproduce:
``.venv/bin/python -m pytest tests/test_mex_symmetry_numeric.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

from itertools import permutations, product
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from tit.calc import get_TI_vectors
from tit.opt.mex.logic import _pool_electrode_combinations

N_ELEMENTS = 3
POOL = [f"E{i}" for i in range(8)]

#: Slot permutations (image slot s takes the pair of source slot perm[s]) that keep the carriers
#: {0,1} and {2,3}: within-carrier swaps, the carrier swap, and their products.
CARRIER_PRESERVING = [
    (0, 1, 2, 3),
    (1, 0, 2, 3),
    (0, 1, 3, 2),
    (1, 0, 3, 2),
    (2, 3, 0, 1),
    (3, 2, 0, 1),
    (2, 3, 1, 0),
    (3, 2, 1, 0),
]
#: Pair polarity flips that flip both carriers' products a_k*b_k or neither.
PRODUCT_PRESERVING = [
    f for f in product((0, 1), repeat=4) if f[0] ^ f[1] == f[2] ^ f[3]
]


@pytest.fixture(scope="module")
def fields():
    rng = np.random.default_rng(20261022)
    return {e: rng.normal(size=(N_ELEMENTS, 3)) for e in POOL}


@pytest.fixture(scope="module")
def canonical():
    return list(_pool_electrode_combinations(POOL))


def _image(montage, perm, flips):
    pairs = [montage[2 * k : 2 * k + 2] for k in range(4)]
    out = []
    for slot in range(4):
        pair = pairs[perm[slot]]
        out.extend(pair[::-1] if flips[slot] else pair)
    return tuple(out)


def _pair_fields(montages, fields):
    """The four pair fields of every montage, stacked along the element axis."""
    return [
        np.concatenate([fields[m[2 * k]] - fields[m[2 * k + 1]] for m in montages])
        for k in range(4)
    ]


def _md(montages, fields):
    vec = get_TI_vectors(_pair_fields(montages, fields))
    return np.linalg.norm(vec, axis=1).reshape(len(montages), N_ELEMENTS)


def test_the_claimed_group_has_64_operations():
    assert len(CARRIER_PRESERVING) == 8 and len(PRODUCT_PRESERVING) == 8


def test_every_image_scores_like_its_canonical_montage(canonical, fields):
    assert len(canonical) == 40320 // 64 == 630
    base = _md(canonical, fields)
    images = set()
    worst = 0.0
    for perm in CARRIER_PRESERVING:
        for flips in PRODUCT_PRESERVING:
            imgs = [_image(m, perm, flips) for m in canonical]
            images.update(imgs)
            worst = max(worst, float(np.max(np.abs(_md(imgs, fields) - base))))
    assert worst <= 1e-9
    # The 630 x 64 images are every ordering of the 8 electrodes, once each, so the distinct
    # values over permutations(pool, 8) are exactly the canonical montages' values.
    assert images == set(permutations(POOL, 8))
    # ... and no two canonical montages are the same class (generic fields separate them).
    assert len({tuple(np.round(row, 9)) for row in base}) == 630


def test_a_lone_flip_inside_a_beating_channel_changes_the_value(canonical, fields):
    base = _md(canonical, fields)
    for slot in range(4):
        flips = tuple(int(s == slot) for s in range(4))
        moved = _md([_image(m, (0, 1, 2, 3), flips) for m in canonical], fields)
        # Every canonical montage changes somewhere: Q's sign flip is a real pi phase shift.
        assert np.all(np.max(np.abs(moved - base), axis=1) > 1e-6), slot


def test_the_envelope_stays_inside_its_physical_bounds(canonical, fields):
    pair_fields = _pair_fields(canonical, fields)
    md = np.linalg.norm(get_TI_vectors(pair_fields), axis=1)
    bound = np.sqrt(2 * sum(np.sum(f**2, axis=1) for f in pair_fields))
    assert np.all(md >= 0)
    assert np.all(md <= bound + 1e-12)
    # Not vacuous: the bound is approached, not 10x away.
    assert np.max(md / bound) > 0.5


def test_a_zero_second_carrier_is_the_k1_closed_form():
    rng = np.random.default_rng(7)
    n = 200
    axis = rng.normal(size=(n, 3))
    axis /= np.linalg.norm(axis, axis=1)[:, None]
    a = rng.uniform(0.05, 2.0, n)
    b = rng.uniform(0.05, 2.0, n) * rng.choice(
        [-1.0, 1.0], n
    )  # parallel or antiparallel
    zero = np.zeros((n, 3))
    md = np.linalg.norm(
        get_TI_vectors([a[:, None] * axis, b[:, None] * axis, zero, zero]), axis=1
    )
    exact = 2 * np.minimum(np.abs(a), np.abs(b))
    assert np.all(
        md <= exact * (1 + 1e-12)
    )  # a sampled direction never beats the maximum
    assert np.all(md >= exact * (1 - 1e-4))


def test_the_engine_assembles_pairs_and_carriers_as_the_symmetry_assumes(
    canonical, fields, monkeypatch
):
    """``compute_mti_field`` scores a montage and its 64 images alike (5 canonical montages)."""
    import tit.opt.mex.engine as engine_mod
    from tit.opt.mex.engine import MExSearchEngine

    names = list(fields)
    leadfield = np.stack([fields[e] for e in names])
    fake_ti = SimpleNamespace(
        get_field=lambda pair, lf, idx: pair[2]
        * (lf[idx.index(pair[0])] - lf[idx.index(pair[1])])
    )
    monkeypatch.setattr(engine_mod, "TI", fake_ti)
    # The real envelope, whatever an earlier test module left bound in the engine module.
    monkeypatch.setattr(engine_mod, "get_TI_vectors", get_TI_vectors)
    engine = MExSearchEngine("/lf.hdf5", [], "roi", MagicMock())
    engine.leadfield, engine.idx_lf = leadfield, names
    engine.roi_indices = np.array([0, 2])
    engine.roi_volumes = np.array([1.0, 3.0])
    engine.gm_indices = np.arange(N_ELEMENTS)
    engine.gm_volumes = np.ones(N_ELEMENTS)

    for montage in canonical[::126]:
        ref = engine.compute_mti_field(montage, 1.0)
        assert ref["roi_TImean_ROI"] > 0
        for perm in CARRIER_PRESERVING:
            for flips in PRODUCT_PRESERVING:
                got = engine.compute_mti_field(_image(montage, perm, flips), 1.0)
                for key in ("TImax_ROI", "TImean_ROI", "TImean_GM", "Focality"):
                    assert got[f"roi_{key}"] == pytest.approx(
                        ref[f"roi_{key}"], abs=1e-12
                    )
        lone = engine.compute_mti_field(
            _image(montage, (0, 1, 2, 3), (0, 1, 0, 0)), 1.0
        )
        assert lone["roi_TImean_GM"] != pytest.approx(ref["roi_TImean_GM"], abs=1e-9)

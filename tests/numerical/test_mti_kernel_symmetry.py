"""The numba mTI kernel scores mEx symmetry images alike and handles 0- and 1-element inputs.

Container leg of ``tests/test_mex_symmetry_numeric.py`` (which runs the NumPy sweep on the host,
where numba is absent). Here ``TIT_MTI_KERNEL=numba`` routes ``tit.calc.get_TI_vectors`` for
K=2 through ``tit._mti_kernel.sweep_refine`` -- the path an mEx search takes in the image -- and
the same physical claims are checked on it (2026-10-22):

* the 64 operations the mEx pool enumeration treats as symmetries (8 carrier-preserving slot
  permutations x 8 product-preserving polarity flips, written out from
  ``Q = |a_1 b_1 + a_2 b_2|`` in ``tit/calc.py``) leave every canonical montage's envelope
  unchanged, and their images are the 40 320 orderings of the pool;
* a lone polarity flip inside a beating channel changes it;
* ``0 <= MD <= sqrt(2*sum_k(|E_ka|^2+|E_kb|^2))`` per element;
* with a zero second carrier the envelope is ``2*min(|a|,|b|)`` for collinear fields;
* a 0-element input returns empty results and a 1-element input runs the kernel and matches the
  NumPy sweep (the kernel reproduces it step for step, ``tit.calc._fused_sweep_kernel``).

Tolerances: images 1e-9 V/m (the same sums in another order); numba vs NumPy 1e-9 (the kernel's
own contract, ``tests/helpers/mti_kernel_compare.py`` uses the same); the direction search never
exceeds the true maximum and misses it by its sampling error, measured <= 1.6e-5 relative,
bounded at 1e-4.

Reproduce (container, one docker run at a time)::

    docker run --rm --platform linux/amd64 --entrypoint bash -v $PWD:/ti-toolbox -w /ti-toolbox \\
      idossha/ti-toolbox:v3.1.1 -lc \\
      'simnibs_python -m pytest tests/numerical/test_mti_kernel_symmetry.py -q -p no:cacheprovider'
"""

from __future__ import annotations

import importlib
from itertools import permutations, product

import numpy as np
import pytest

POOL = [f"E{i}" for i in range(8)]
N_ELEMENTS = 3
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
PRODUCT_PRESERVING = [
    f for f in product((0, 1), repeat=4) if f[0] ^ f[1] == f[2] ^ f[3]
]


@pytest.fixture
def numba_kernel(monkeypatch):
    """``tit.calc`` with the numba kernel selected, or a skip when numba is not importable."""
    try:
        importlib.import_module("numba")
    except Exception as exc:  # noqa: BLE001 - any import failure means "no kernel here"
        print(f"skipping: numba is not importable ({exc})")
        pytest.skip(f"numba is not importable here ({exc}); the image has it")
    from tit import _mti_kernel, calc

    if not _mti_kernel.HAVE_NUMBA:  # first imported while the host suite mocked scipy
        importlib.reload(_mti_kernel)
    monkeypatch.setenv("TIT_MTI_KERNEL", "numba")
    assert calc._fused_sweep_kernel() is not None, "numba kernel not selected"
    return calc


def _image(montage, perm, flips):
    pairs = [montage[2 * k : 2 * k + 2] for k in range(4)]
    out = []
    for slot in range(4):
        pair = pairs[perm[slot]]
        out.extend(pair[::-1] if flips[slot] else pair)
    return tuple(out)


def _pair_fields(montages, fields):
    return [
        np.concatenate([fields[m[2 * k]] - fields[m[2 * k + 1]] for m in montages])
        for k in range(4)
    ]


def _md(calc, montages, fields):
    vec = calc.get_TI_vectors(_pair_fields(montages, fields))
    return np.linalg.norm(vec, axis=1).reshape(len(montages), N_ELEMENTS)


def test_symmetry_images_score_alike_through_the_kernel(numba_kernel):
    from tit.opt.mex.logic import _pool_electrode_combinations

    calc = numba_kernel
    rng = np.random.default_rng(20261022)
    fields = {e: rng.normal(size=(N_ELEMENTS, 3)) for e in POOL}
    canonical = list(_pool_electrode_combinations(POOL))
    assert len(canonical) == 40320 // 64

    base = _md(calc, canonical, fields)
    images, worst = set(), 0.0
    for perm in CARRIER_PRESERVING:
        for flips in PRODUCT_PRESERVING:
            imgs = [_image(m, perm, flips) for m in canonical]
            images.update(imgs)
            worst = max(worst, float(np.max(np.abs(_md(calc, imgs, fields) - base))))
    assert worst <= 1e-9
    assert images == set(permutations(POOL, 8))
    assert len({tuple(np.round(row, 9)) for row in base}) == len(canonical)

    for slot in range(4):
        flips = tuple(int(s == slot) for s in range(4))
        moved = _md(calc, [_image(m, (0, 1, 2, 3), flips) for m in canonical], fields)
        assert np.all(np.max(np.abs(moved - base), axis=1) > 1e-6), slot

    pair_fields = _pair_fields(canonical, fields)
    md = base.reshape(-1)
    bound = np.sqrt(2 * sum(np.sum(f**2, axis=1) for f in pair_fields))
    assert np.all(md >= 0) and np.all(md <= bound + 1e-12)
    assert np.max(md / bound) > 0.5


def test_a_zero_second_carrier_is_the_k1_closed_form_through_the_kernel(numba_kernel):
    calc = numba_kernel
    rng = np.random.default_rng(7)
    n = 200
    axis = rng.normal(size=(n, 3))
    axis /= np.linalg.norm(axis, axis=1)[:, None]
    a = rng.uniform(0.05, 2.0, n)
    b = rng.uniform(0.05, 2.0, n) * rng.choice([-1.0, 1.0], n)
    zero = np.zeros((n, 3))
    md = np.linalg.norm(
        calc.get_TI_vectors([a[:, None] * axis, b[:, None] * axis, zero, zero]), axis=1
    )
    exact = 2 * np.minimum(np.abs(a), np.abs(b))
    assert np.all(md <= exact * (1 + 1e-12))
    assert np.all(md >= exact * (1 - 1e-4))


def test_zero_elements_give_empty_results(numba_kernel):
    calc = numba_kernel
    empty = [np.zeros((0, 3)) for _ in range(4)]
    assert calc.get_TI_vectors(empty).shape == (0, 3)
    out = calc._mti_modulation_depth(empty)
    assert out["md"].shape == (0,) and out["best_direction"].shape == (0, 3)


def test_one_element_runs_the_kernel_and_matches_the_numpy_sweep(
    numba_kernel, monkeypatch
):
    calc = numba_kernel
    rng = np.random.default_rng(11)
    one = [rng.normal(size=(1, 3)) for _ in range(4)]
    calls = []
    kernel = calc._fused_sweep_kernel()

    def spy(*args, **kwargs):
        calls.append(args[0][0].shape)
        return kernel(*args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(calc, "_fused_sweep_kernel", lambda: spy)
        got = calc._mti_modulation_depth(one)
    assert calls == [(1, 3)], "the 1-element input did not reach the numba kernel"
    monkeypatch.setenv("TIT_MTI_KERNEL", "numpy")
    assert calc._fused_sweep_kernel() is None
    ref = calc._mti_modulation_depth(one)
    for key in ("md", "carrier_power", "best_direction"):
        assert got[key].shape == ref[key].shape
        assert np.max(np.abs(got[key] - ref[key])) <= 1e-9, key
    bound = np.sqrt(2 * sum(float(np.sum(f**2)) for f in one))
    assert 0 < float(got["md"][0]) <= bound + 1e-12

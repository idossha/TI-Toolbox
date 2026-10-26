"""The numba K>=2 sphere-maximum kernel (``tit/_calc_kernel.py``) agrees with the NumPy reference.

Pins (2026-10-26): ``tit.calc.envelope_max`` runs the K>=2 sphere maximum in a numba kernel when
numba imports, and that kernel is the same algorithm as the NumPy path in ``tit/calc.py``
(``_max_sphere`` with the kernel switched off) -- only its 3x3 eigensolver differs (Jacobi vs
LAPACK), so the two agree to round-off:

* on 10^4 seeded random elements each at K = 2, 3, 4 and on the degenerate sets of
  ``tests/test_calc.py``, kernel and NumPy maxima agree to 1e-12 relative both ways (<=1e-13
  measured), and every kernel value is attained at its returned direction (``envelope``);
* on the six real grey-matter elements an earlier solver missed (``tests/test_calc.py``), the
  kernel is never below the dense sphere search there (an oracle independent of both paths);
* null elements give 0 with the documented ``(1, 0, 0)`` direction, never NaN;
* NaN or inf in any field raises ValueError before the kernel runs (the kernel itself would
  return finite garbage), and rows the kernel flags as not converged are recomputed by NumPy.

Where the numbers come from: the NumPy reference (itself checked against dense searches in
``tests/test_calc.py``) and the dense search ``tests.test_calc.dense_max``; nothing is read back
from the kernel's own output. Runs in the image, the only place numba is installed; the host
suite pins the fallback (``tests/test_calc.py::test_without_numba_the_numpy_path_runs``).

Reproduce, one docker run at a time::

    docker run --rm --platform linux/amd64 --entrypoint simnibs_python -v $PWD:/ti-toolbox:ro \\
      -w /ti-toolbox idossha/ti-toolbox:v3.1.2 \\
      -m pytest tests/numerical/test_calc_kernel.py -q -p no:cacheprovider

Deliberately elsewhere: the algorithm's accuracy against dense searches (``tests/test_calc.py``,
NumPy path, host) and timing (``docs/dev/BENCHMARKS.md``).
"""

from __future__ import annotations

import numpy as np
import pytest

import tit.calc as calc
from tests.test_calc import (
    REAL_GM_FIELDS,
    REAL_GM_ROOT_FIELDS,
    degenerate_sets,
    dense_max,
    random_fields,
)


def both(fields, monkeypatch):
    """``(amp, n_hat)`` from the kernel, then from the NumPy reference."""
    # Per test, not per module: a module-level skip would land in the host_numerical leg's
    # report, where these tests are deselected. In the image this skip is not allowlisted
    # (dev/check_junit.py), so an image without numba goes red.
    pytest.importorskip("numba", reason="the image ships numba; the kernel needs it")
    calc._sphere_kernel.cache_clear()  # a host test may have cached None under mocked scipy
    assert (
        calc._sphere_kernel() is not None
    ), "numba imports but the kernel did not load"
    kernel = calc.envelope_max(fields, return_direction=True)
    with monkeypatch.context() as m:
        m.setattr(calc, "_sphere_kernel", lambda: None)
        numpy = calc.envelope_max(fields, return_direction=True)
    return kernel, numpy


def assert_parity(fields, monkeypatch):
    (a_k, n_k), (a_n, _) = both(fields, monkeypatch)
    np.testing.assert_allclose(a_k, a_n, rtol=1e-12, atol=1e-300)
    np.testing.assert_allclose(calc.envelope(fields, n_k), a_k, rtol=1e-12, atol=1e-15)


@pytest.mark.parametrize("k", [2, 3, 4])
def test_kernel_matches_numpy_on_random_elements(k, monkeypatch):
    assert_parity(random_fields(900 + k, 10_000, 2 * k), monkeypatch)


@pytest.mark.parametrize("name", list(degenerate_sets()))
def test_kernel_matches_numpy_on_degenerate_sets(name, monkeypatch):
    assert_parity(degenerate_sets()[name], monkeypatch)


def test_kernel_on_real_grey_matter_is_never_below_a_dense_search(monkeypatch):
    fields = list(np.concatenate([REAL_GM_FIELDS, REAL_GM_ROOT_FIELDS], axis=1))
    assert_parity(fields, monkeypatch)
    amp = calc.envelope_max(fields)
    dense = dense_max(fields, m=200_000)
    assert np.all(amp >= dense * (1 - 1e-9)), (amp - dense) / dense


def test_null_elements_give_zero_not_nan(monkeypatch):
    fields = random_fields(950, 6, 4)
    for f in fields:
        f[::2] = 0.0
    (amp, n_hat), _ = both(fields, monkeypatch)
    assert np.isfinite(amp).all() and np.isfinite(n_hat).all()
    np.testing.assert_array_equal(amp[::2], 0.0)
    np.testing.assert_array_equal(n_hat[::2], np.tile([1.0, 0.0, 0.0], (3, 1)))
    assert np.all(amp[1::2] > 0)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_input_raises_before_the_kernel(bad):
    pytest.importorskip("numba", reason="the image ships numba; the kernel needs it")
    calc._sphere_kernel.cache_clear()
    assert calc._sphere_kernel() is not None
    fields = random_fields(960, 5, 4)
    fields[2][3, 1] = bad
    with pytest.raises(ValueError, match="non-finite"):
        calc.envelope_max(fields)


def test_rows_the_kernel_flags_are_recomputed_by_numpy(monkeypatch):
    """A Jacobi solve that did not converge (unseen for finite input) marks its row not ok."""
    pytest.importorskip("numba", reason="the image ships numba; the kernel needs it")
    calc._sphere_kernel.cache_clear()
    kernel = calc._sphere_kernel()
    assert kernel is not None

    def flagging(E, *args):
        amp, n_hat, ok = kernel(E, *args)
        amp[1::3], n_hat[1::3], ok[1::3] = -7.0, 0.0, False
        return amp, n_hat, ok

    fields = random_fields(970, 30, 6)
    monkeypatch.setattr(calc, "_sphere_kernel", lambda: flagging)
    got = calc.envelope_max(fields)
    monkeypatch.setattr(calc, "_sphere_kernel", lambda: None)
    np.testing.assert_allclose(got, calc.envelope_max(fields), rtol=1e-12)

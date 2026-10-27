"""The numba K>=2 sphere-maximum kernel (``tit/_calc_kernel.py``) under the image's own numba.

Pins (2026-10-27): ``tit.calc.envelope_max`` runs the K>=2 sphere maximum in a numba kernel and
nothing else (numba is a hard dependency; there is no NumPy solver). ``tests/test_calc.py`` checks
the kernel's accuracy under the host's numba; this file re-checks it under the image's numba and
NumPy (0.64.0 / 2.3.5 in v3.1.2), where a numba upgrade could change compilation or rounding:

* the kernel is the compiled numba dispatcher, not a mock or a Python fallback;
* on 2,000 seeded random elements each at K = 2, 3, 4, on the degenerate sets and on the six real
  grey-matter elements of ``tests/test_calc.py``, every value is attained at its returned
  direction (``envelope``, 1e-12) and never below a dense sphere search (an oracle independent of
  the kernel) by more than round-off, with the dense search tight (median 1e-8);
* null elements give 0 with the documented ``(1, 0, 0)`` direction, never NaN;
* NaN or inf in any field raises ValueError before the kernel runs, and fields that overflow
  float64 once squared raise RuntimeError (the Jacobi solve cannot converge on inf).

Where the numbers come from: the dense search ``tests.test_calc.dense_max`` and the closed form
``tit.calc.envelope`` at the returned direction; nothing is read back from the kernel's own output.
Also runs on the host (``host_numerical``): it needs only numpy and numba.

Reproduce, one docker run at a time::

    docker run --rm --platform linux/amd64 --entrypoint simnibs_python -v $PWD:/ti-toolbox:ro \\
      -w /ti-toolbox idossha/ti-toolbox:v3.1.2 \\
      -m pytest tests/numerical/test_calc_kernel.py -q -p no:cacheprovider

Deliberately elsewhere: the full accuracy suite (``tests/test_calc.py``) and timing
(``docs/dev/BENCHMARKS.md``).
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.test_calc import (
    REAL_GM_FIELDS,
    REAL_GM_ROOT_FIELDS,
    degenerate_sets,
    dense_max,
    random_fields,
)
from tit import calc

pytestmark = pytest.mark.host_numerical


def assert_never_below_dense(fields, m=40_000):
    """Attained at ``n_hat`` and never below the dense search; returns the relative gap."""
    amp, n_hat = calc.envelope_max(fields, return_direction=True)
    np.testing.assert_allclose(
        calc.envelope(fields, n_hat), amp, rtol=1e-12, atol=1e-15
    )
    dense = dense_max(fields, m=m)
    assert np.all(amp >= dense * (1 - 1e-9) - 1e-15), (amp - dense) / dense
    return (amp - dense) / np.where(amp > 0, amp, 1.0)


def test_the_kernel_is_the_compiled_numba_dispatcher():
    from numba.core.registry import CPUDispatcher

    from tit import _calc_kernel

    assert calc._sphere_kernel is _calc_kernel.max_sphere
    assert isinstance(calc._sphere_kernel, CPUDispatcher)


@pytest.mark.parametrize("k", [2, 3, 4])
def test_random_elements_never_below_a_dense_search(k):
    rel = assert_never_below_dense(random_fields(900 + k, 2_000, 2 * k))
    assert np.median(rel) < 1e-8 and np.mean(rel > 1e-6) < 0.01


@pytest.mark.parametrize("name", list(degenerate_sets()))
def test_degenerate_sets_never_below_a_dense_search(name):
    assert_never_below_dense(degenerate_sets()[name])


def test_real_grey_matter_never_below_a_dense_search():
    fields = list(np.concatenate([REAL_GM_FIELDS, REAL_GM_ROOT_FIELDS], axis=1))
    assert_never_below_dense(fields, m=200_000)


def test_null_elements_give_zero_not_nan():
    fields = random_fields(950, 6, 4)
    for f in fields:
        f[::2] = 0.0
    amp, n_hat = calc.envelope_max(fields, return_direction=True)
    assert np.isfinite(amp).all() and np.isfinite(n_hat).all()
    np.testing.assert_array_equal(amp[::2], 0.0)
    np.testing.assert_array_equal(n_hat[::2], np.tile([1.0, 0.0, 0.0], (3, 1)))
    assert np.all(amp[1::2] > 0)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_input_raises_before_the_kernel(bad):
    fields = random_fields(960, 5, 4)
    fields[2][3, 1] = bad
    with pytest.raises(ValueError, match="non-finite"):
        calc.envelope_max(fields)


def test_fields_that_overflow_once_squared_raise():
    fields = [f * 1e155 for f in random_fields(971, 4, 4)]
    with (
        np.errstate(over="ignore", invalid="ignore"),
        pytest.raises(RuntimeError, match="did not converge at 4 elements"),
    ):
        calc.envelope_max(fields)

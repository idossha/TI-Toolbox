"""``tit.calc``'s two-pair envelope agrees with SimNIBS's independent implementation.

Pins (2026-10-26, the envelope API): on 10^5 seeded random field pairs with log-normal
magnitudes (ratios spanning ~4 decades),

* ``envelope_max([E1, E2])`` equals SimNIBS ``TI_utils.get_maxTI(E1, E2)`` -- Grossman 2017's
  preprocess-then-branch form, written separately from the sign-agnostic Hirata 2024 form in
  ``tit/calc.py`` -- to 1e-12 relative (measured 6e-16 on 10^6 pairs);
* ``envelope([E1, E2], n)`` equals ``TI_utils.get_dirTI(E1, E2, n)`` to 1e-9 relative wherever
  the value exceeds 1e-3 of its median (measured 5e-12). ``get_dirTI`` subtracts two projected
  norms and loses relative accuracy in the weak-modulation tail; that tail is checked against
  the exact ``2 min(|E1.n|, |E2.n|)`` instead, which ``tit.calc`` meets to 1e-10.

Where the numbers come from: SimNIBS 4.6 in the image (the only reader here that is not the code
under test) and Grossman's ``2 min(|a|, |b|)`` written out below. Runs in the image only; SimNIBS
runs in a child interpreter because the host conftest mocks it in-process. Reproduce, one docker
run at a time::

    docker run --rm --platform linux/amd64 --entrypoint simnibs_python -v $PWD:/ti-toolbox:ro \\
      -w /ti-toolbox idossha/ti-toolbox:v3.1.2 \\
      -m pytest tests/numerical/test_calc_vs_simnibs.py -q -p no:cacheprovider

Deliberately elsewhere: the K >= 2 and plane maxima, mean, and carrier metrics against dense
searches and enumeration (``tests/test_calc.py``; NumPy only, so the host runs them).
"""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

N = 100_000

#: SimNIBS runs in a child interpreter: ``tests/conftest.py`` replaces ``simnibs`` with a mock
#: for this process. The child rebuilds the same seeded fields and writes SimNIBS's answers.
_SIMNIBS = r"""
import sys, warnings
import numpy as np
from simnibs.utils import TI_utils

out, n = sys.argv[1], int(sys.argv[2])
rng = np.random.default_rng(13)
e = rng.standard_normal((2, n, 3)) * np.exp(rng.normal(0.0, 1.5, (2, n, 1)))
d = np.random.default_rng(19).standard_normal((n, 3))
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    np.savez(out, maxti=TI_utils.get_maxTI(e[0], e[1]), dirti=TI_utils.get_dirTI(e[0], e[1], d))
"""


@pytest.fixture(scope="module")
def simnibs_answers(tmp_path_factory):
    out = tmp_path_factory.mktemp("simnibs") / "ti.npz"
    proc = subprocess.run(
        [sys.executable, "-c", _SIMNIBS, str(out), str(N)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode:
        pytest.skip(
            f"skipping: needs simnibs.utils.TI_utils (run in the image): {proc.stderr[-300:]}"
        )
    rng = np.random.default_rng(13)
    e = rng.standard_normal((2, N, 3)) * np.exp(rng.normal(0.0, 1.5, (2, N, 1)))
    d = np.random.default_rng(19).standard_normal((N, 3))
    return e[0], e[1], d, np.load(out)


def test_envelope_max_is_simnibs_get_maxti(simnibs_answers):
    from tit.calc import envelope_max

    e1, e2, _, theirs = simnibs_answers
    assert np.all(theirs["maxti"] > 0)
    np.testing.assert_allclose(
        envelope_max([e1, e2]), theirs["maxti"], rtol=1e-12, atol=0
    )


def test_envelope_is_simnibs_get_dirti(simnibs_answers):
    from tit.calc import envelope

    e1, e2, n, theirs = simnibs_answers
    ours = envelope([e1, e2], n)
    dirti = theirs["dirti"]
    bulk = dirti > 1e-3 * np.median(dirti)
    assert bulk.mean() > 0.95
    np.testing.assert_allclose(ours[bulk], dirti[bulk], rtol=1e-9, atol=0)

    unit = n / np.linalg.norm(n, axis=1, keepdims=True)
    exact = 2 * np.minimum(
        np.abs(np.sum(e1 * unit, axis=1)), np.abs(np.sum(e2 * unit, axis=1))
    )
    # A field nearly perpendicular to n has a projection carrying ~eps |E| / |E.n| relative
    # rounding, whichever order sums it (measured worst 1.6e-12 of 10^5).
    np.testing.assert_allclose(ours, exact, rtol=1e-10, atol=0)

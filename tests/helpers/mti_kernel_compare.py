"""Compare the numba mTI kernel with the NumPy sweep; print max abs diffs.

Run as a subprocess by ``tests/test_mti_kernel.py`` so the test-suite's
mocked ``scipy`` (which breaks ``import numba``) is not in ``sys.modules``.
Exits non-zero when any difference exceeds the tolerance.
"""

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tit import calc  # noqa: E402
from tit.calc import get_mTI_vectors  # noqa: E402

ATOL = 1e-9


def _sweep(arrs, psi, refine, kernel):
    os.environ["TIT_MTI_KERNEL"] = kernel
    if kernel == "numba":
        assert calc._fused_sweep_kernel() is not None, "numba kernel not selected"
    else:
        assert calc._fused_sweep_kernel() is None
    return calc._mti_modulation_depth_sweep(arrs, psi, 192, 1024, refine)


def main():
    worst = 0.0
    for n_pairs in (2, 3, 4):
        rng = np.random.default_rng(1234 + n_pairs)
        n = 2500
        arrs = [
            rng.normal(size=(n, 3)) * rng.uniform(0.1, 1.0)
            for _ in range(2 * n_pairs)
        ]
        for psi in (None, np.linspace(0.3, 1.1, n_pairs)):
            for refine in (True, False):
                ref = _sweep(arrs, psi, refine, "numpy")
                got = _sweep(arrs, psi, refine, "numba")
                for key in ("md", "carrier_power", "best_direction"):
                    diff = float(np.max(np.abs(got[key] - ref[key])))
                    worst = max(worst, diff)
                    print(
                        f"K={n_pairs} psi={'y' if psi is not None else 'n'} "
                        f"refine={refine} {key}: max|diff|={diff:.3e}"
                    )

    rng = np.random.default_rng(7)
    fields = [rng.normal(size=(300, 3)) for _ in range(8)]
    channels = [([0, 2], [1, 3]), ([4], [5, 6, 7])]
    os.environ["TIT_MTI_KERNEL"] = "numpy"
    ref = get_mTI_vectors(fields, channels=channels)
    os.environ["TIT_MTI_KERNEL"] = "numba"
    got = get_mTI_vectors(fields, channels=channels)
    diff = float(np.max(np.abs(got - ref)))
    worst = max(worst, diff)
    print(f"get_mTI_vectors(channels) max|diff|={diff:.3e}")

    print(f"WORST {worst:.3e}")
    return 0 if worst <= ATOL else 1


if __name__ == "__main__":
    sys.exit(main())

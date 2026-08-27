"""Regression test: the numba mTI kernel reproduces the NumPy sweep.

The comparison runs in a subprocess because the suite's conftest mocks
``scipy``, which breaks ``import numba``. Skipped where the interpreter
cannot import numba (the host); it runs in the SimNIBS container.
"""

import subprocess
import sys
from pathlib import Path

import pytest

_HELPER = Path(__file__).resolve().parent / "helpers" / "mti_kernel_compare.py"


def _numba_importable() -> bool:
    proc = subprocess.run(
        [sys.executable, "-c", "import numba"], capture_output=True, text=True
    )
    return proc.returncode == 0


@pytest.mark.unit
@pytest.mark.skipif(not _numba_importable(), reason="numba not installed")
def test_numba_kernel_matches_numpy_sweep():
    proc = subprocess.run(
        [sys.executable, str(_HELPER)], capture_output=True, text=True, timeout=600
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WORST" in proc.stdout

"""Real-library leg for the scientific corrections (SCI-01 .. SCI-06).

``tests/conftest.py`` replaces ``scipy``, ``nibabel``, ``joblib`` and friends
with ``MagicMock`` so the fast host suite can import ``tit`` without SimNIBS.
The corrections in this directory are *numerical* claims -- cluster masses,
permutation p-values, affine determinants -- so they need the real libraries.

This conftest swaps the real packages in for the duration of the directory,
reloads the modules under test so their module-level ``from scipy...`` /
``import nibabel`` bindings point at the real implementations, and puts the
mocks back afterwards so the rest of the suite is unaffected.  Every test here
skips (with a reason) when the real libraries are not importable.
"""

import importlib
import sys

import pytest

_REAL_PACKAGES = ("numpy", "scipy", "scipy.ndimage", "scipy.stats", "nibabel")
_RELOAD_MODULES = ("tit.stats.engine", "tit.stats.nifti")


def _swap_in_real():
    """Remove mocked scipy/nibabel from sys.modules and import the real ones."""
    saved = {}
    for key in list(sys.modules):
        if key.split(".")[0] in ("scipy", "nibabel"):
            saved[key] = sys.modules.pop(key)
    try:
        for name in _REAL_PACKAGES:
            importlib.import_module(name)
    except Exception:  # pragma: no cover - environment without the real stack
        for key, mod in saved.items():
            sys.modules[key] = mod
        return None
    return saved


@pytest.fixture(scope="package", autouse=True)
def real_numeric_stack():
    saved = _swap_in_real()
    if saved is None:
        pytest.skip("real scipy/nibabel not importable in this environment")
    for name in _RELOAD_MODULES:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    yield
    # Restore the mocked stack for the remainder of the session.
    for key in list(sys.modules):
        if key.split(".")[0] in ("scipy", "nibabel"):
            del sys.modules[key]
    sys.modules.update(saved)
    for name in _RELOAD_MODULES:
        if name in sys.modules:
            try:
                importlib.reload(sys.modules[name])
            except Exception:  # pragma: no cover
                pass

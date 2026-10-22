"""Real-library leg for the scientific corrections (SCI-01 .. SCI-06).

``tests/conftest.py`` replaces ``scipy``, ``nibabel``, ``joblib`` and friends
with ``MagicMock`` so the fast host suite can import ``tit`` without SimNIBS.
The corrections in this directory are *numerical* claims -- cluster masses,
permutation p-values, affine determinants -- so they need the real libraries.

This conftest swaps the real packages in for the duration of the directory,
reloads the modules under test so their module-level ``from scipy...`` /
``import nibabel`` bindings point at the real implementations, and puts the
mocks back afterwards so the rest of the suite is unaffected.  Every test here
skips (with a reason) when the real scipy/nibabel are not importable.

Two legs run this directory:

* **The image** (``idossha/ti-toolbox``): matplotlib, pandas, SimNIBS and the rest of the
  stack are real, so every module runs.
* **A host** with real numpy/scipy/nibabel but no matplotlib (the CI venv,
  ``pip install -e '.[test]'``): only modules marked ``host_numerical`` run -- they need
  nothing beyond numpy, scipy and nibabel. Every other module skips with a reason, because
  matplotlib being absent means the rest of the image stack is absent too.
"""

import importlib
import sys

import pytest

_REQUIRED = ("numpy", "scipy", "scipy.ndimage", "scipy.stats", "nibabel")
# matplotlib is real here for the tests in this directory that draw: nothing in
# `tit/figures` needs it any more (the ROI artefact is a scene file, not a
# picture), but the host suite's mock answers any attribute, which turns a real
# `from matplotlib.x import y` into an unhelpful "not a package" error.
_DRAWING = ("matplotlib", "matplotlib.pyplot")
_SWAPPED = ("scipy", "nibabel", "matplotlib")
_RELOAD_MODULES = ("tit.stats.engine", "tit.stats.nifti")

#: Whether real matplotlib imported in this session; False on a host without it.
_STACK = {"matplotlib": False}

#: Modules written before the marker existed that need only numpy, scipy and nibabel. A new
#: module opts in with ``pytestmark = pytest.mark.host_numerical`` instead of being listed.
_HOST_NUMERICAL_MODULES = frozenset(
    {
        "test_sci01_cluster_sign.py",
        "test_sci02_grid_consistency.py",
        "test_sci04_sci06_pvalues_degenerate.py",
        "test_sci09_singleton_group.py",
    }
)


def pytest_collection_modifyitems(config, items):
    """Mark the listed pre-marker modules ``host_numerical``."""
    for item in items:
        if item.path.name in _HOST_NUMERICAL_MODULES:
            item.add_marker(pytest.mark.host_numerical)


def _root(key: str) -> str:
    return key.split(".")[0]


def _swap_in_real():
    """Remove the mocked packages from sys.modules and import the real ones.

    Returns the saved mocks, or ``None`` when real scipy/nibabel are not importable. A
    missing matplotlib is not fatal: its mock is put back and ``_STACK`` records it.
    """
    saved = {}
    for key in list(sys.modules):
        if _root(key) in _SWAPPED:
            saved[key] = sys.modules.pop(key)
    try:
        for name in _REQUIRED:
            importlib.import_module(name)
    except Exception:  # pragma: no cover - environment without the real stack
        _put_back(saved)
        return None
    try:
        for name in _DRAWING:
            importlib.import_module(name)
        _STACK["matplotlib"] = True
    except Exception:
        _STACK["matplotlib"] = False
        for key in [k for k in sys.modules if _root(k) == "matplotlib"]:
            del sys.modules[key]
        sys.modules.update({k: v for k, v in saved.items() if _root(k) == "matplotlib"})
    return saved


def _put_back(saved):
    """Drop every real module the swap imported and restore the mocks.

    Restoring only the saved keys is not enough: on the host, real scipy and nibabel import before
    matplotlib fails, and their submodules (``nibabel.affines`` ...) stayed in ``sys.modules``
    beside the restored mock ``nibabel``. ``patch("nibabel.affines.apply_affine")`` in a later
    module then patched the real function while the code under test called the mock's.
    """
    for key in list(sys.modules):
        if _root(key) in _SWAPPED:
            del sys.modules[key]
    sys.modules.update(saved)


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
    _put_back(saved)
    _STACK["matplotlib"] = False
    for name in _RELOAD_MODULES:
        if name in sys.modules:
            try:
                importlib.reload(sys.modules[name])
            except Exception:  # pragma: no cover
                pass


@pytest.fixture(autouse=True)
def _image_stack_unless_host_numerical(request, real_numeric_stack):
    """Skip a module that needs the image's stack when matplotlib (and so it) is absent."""
    if _STACK["matplotlib"] or request.node.get_closest_marker("host_numerical"):
        return
    print("skipping: matplotlib is not importable, so this is not the image")
    pytest.skip(
        "needs the image's library stack (matplotlib absent here); run tests/numerical "
        "in idossha/ti-toolbox -- only host_numerical modules run on a bare host"
    )

"""What a catalog read imports: not SimNIBS, or the first visit to a page waits for it.

Pins the 2026-11-07 fix to the Simulator's job table, whose montage read spent 7.6-10 s loading
SimNIBS through ``tit/sim/__init__.py``. The host suite mocks SimNIBS in ``sys.modules``, which would
hide the import, so the first test asks a fresh interpreter. It holds on the host, where SimNIBS is
absent and an import would fail, and in the image, where it would load:
``docker exec -w /ti-toolbox <c> simnibs_python -m pytest tests/test_lazy_package_imports.py``.

Timings are in docs/dev/BENCHMARKS.md, not here. That a job's own entry points still load SimNIBS is
checked in the image; here the mocks stand in for it and only the names are pinned.
"""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "statement",
    [
        "import tit.sim",
        "from tit.sim.utils import load_montage_data",
        "from tit.opt.flex.manifest import read_manifest",
        "from tit.opt.ex.roi import read_roi_center",
    ],
)
def test_a_catalog_read_does_not_import_simnibs(statement):
    probe = f"{statement}\nimport sys\nassert 'simnibs' not in sys.modules, 'simnibs loaded'\n"
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize("package", ["tit.sim", "tit.opt.flex", "tit.opt.ex"])
def test_every_public_name_still_resolves(package):
    module = importlib.import_module(package)
    assert module.__all__
    for name in module.__all__:
        assert getattr(module, name) is not None


def test_the_lazy_names_are_the_real_objects():
    import tit.opt.ex
    import tit.opt.flex
    import tit.sim
    from tit.opt.ex.engine import ExSearchEngine
    from tit.opt.ex.ex import run_ex_search
    from tit.opt.flex.flex import run_flex_search
    from tit.sim.base import BaseSimulation

    assert tit.sim.BaseSimulation is BaseSimulation
    assert tit.opt.flex.run_flex_search is run_flex_search
    assert tit.opt.ex.ExSearchEngine is ExSearchEngine
    assert tit.opt.ex.run_ex_search is run_ex_search


@pytest.mark.parametrize("package", ["tit.sim", "tit.opt.flex", "tit.opt.ex"])
def test_an_unknown_name_is_still_an_attribute_error(package):
    with pytest.raises(AttributeError, match="no_such_name"):
        getattr(importlib.import_module(package), "no_such_name")

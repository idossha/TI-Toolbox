"""Runtime selection, authored source fixture; no scientific library mocks needed."""

import sys
from types import ModuleType

import pytest

from tit.opt.flex import runtime


@pytest.fixture(autouse=True)
def clear_runtime_cache():
    runtime.integration_module.cache_clear()
    previous = sys.modules.get(runtime._MODULE)
    yield
    runtime.integration_module.cache_clear()
    if previous is None:
        sys.modules.pop(runtime._MODULE, None)
    else:
        sys.modules[runtime._MODULE] = previous


def test_checkout_wins_from_unrelated_cwd(tmp_path, monkeypatch):
    source = tmp_path / "patch.py"
    source.write_text("class TesFlexOptimization:\n    optim_parameters = None\n")
    monkeypatch.setattr(runtime, "_SOURCE", source)
    monkeypatch.chdir(tmp_path.parent)
    cls = runtime.optimization_class()
    assert cls.__module__ == runtime._MODULE
    assert cls().optim_parameters is None
    assert runtime.optimization_class() is cls


def test_absent_resource_uses_installed(tmp_path, monkeypatch):
    name = "simnibs.optimization.tes_flex_optimization"
    parent = ModuleType(name)
    installed = ModuleType(name + ".tes_flex_optimization")
    installed.TesFlexOptimization = type("Installed", (), {})
    parent.tes_flex_optimization = installed
    monkeypatch.setitem(sys.modules, name, parent)
    monkeypatch.setattr(runtime, "_SOURCE", tmp_path / "absent")
    assert runtime.optimization_class() is installed.TesFlexOptimization


def test_broken_present_patch_fails_without_fallback(tmp_path, monkeypatch):
    source = tmp_path / "broken.py"
    source.write_text("raise ImportError('incompatible dependency')\n")
    monkeypatch.setattr(runtime, "_SOURCE", source)
    with pytest.raises(ImportError, match="incompatible dependency"):
        runtime.integration_module()
    assert runtime._MODULE not in sys.modules

"""Tests that verify example scripts in scripts/ have valid syntax and reference real APIs."""

import os
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _script_paths():
    """Yield all .py files under scripts/."""
    if not SCRIPTS_DIR.is_dir():
        return
    for p in sorted(SCRIPTS_DIR.glob("*.py")):
        yield p


def _read_script(name: str) -> str:
    """Return the source text of a script file."""
    path = SCRIPTS_DIR / name
    assert path.is_file(), f"Expected script not found: {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Syntax validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScriptSyntax:
    @pytest.mark.parametrize("script", list(_script_paths()), ids=lambda p: p.name)
    def test_scripts_have_valid_python_syntax(self, script):
        """Every .py file under scripts/ must be syntactically valid Python."""
        source = script.read_text(encoding="utf-8")
        compile(source, str(script), "exec")


# ---------------------------------------------------------------------------
# API reference checks (string-based, no execution)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSimulatorScriptAPI:
    def test_simulator_script_references_valid_api(self):
        src = _read_script("simulator.py")
        assert "SimulationConfig" in src
        assert "run_simulation" in src


@pytest.mark.unit
class TestAnalyzerScriptAPI:
    def test_analyzer_script_references_valid_api(self):
        src = _read_script("analyzer.py")
        assert "Analyzer" in src


@pytest.mark.unit
class TestOptimizerScriptAPI:
    def test_optimizer_script_references_valid_api(self):
        src = _read_script("optimizer.py")
        assert "FlexConfig" in src
        assert "run_flex_search" in src


@pytest.mark.unit
class TestPreprocessScriptAPI:
    def test_preprocess_script_references_valid_api(self):
        src = _read_script("preprocess.py")
        assert "run_pipeline" in src


@pytest.mark.unit
class TestClusterPermutationScriptAPI:
    def test_cluster_permutation_script_references_valid_api(self):
        src = _read_script("cluster_permutation.py")
        assert "run_group_comparison" in src
        assert "GroupComparisonConfig" in src
        assert "TestType" in src

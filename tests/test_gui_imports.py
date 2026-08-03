"""
Unit tests for GUI module hygiene and importability.

These tests verify coding-standard compliance (no stale framework
references, no leftover debug widgets) and that key GUI modules can
be imported without crashing.
"""

import json
import os
import sys
import types
from pathlib import Path

import pytest

# Root of the tit/gui package on disk
GUI_ROOT = Path(__file__).resolve().parent.parent / "tit" / "gui"


def _all_py_sources() -> list[Path]:
    """Return every .py file under tit/gui/ (recursive)."""
    return sorted(GUI_ROOT.rglob("*.py"))


def _mock_simnibs_ti_utils() -> None:
    """Install minimal ``simnibs.utils.TI_utils`` stand-ins.

    ``tit.gui.ex_search_tab`` imports ``tit.opt.ex.engine.ExSearchEngine``,
    which does ``from simnibs.utils import TI_utils as TI`` at module level.
    conftest.py's global mock hierarchy doesn't cover that specific
    submodule, so tests that import ``tit.gui.ex_search_tab`` need this
    stand-in first (real SimNIBS is unavailable outside Docker).
    """
    simnibs_mod = sys.modules.setdefault("simnibs", types.ModuleType("simnibs"))
    utils_mod = sys.modules.setdefault(
        "simnibs.utils", types.ModuleType("simnibs.utils")
    )
    ti_utils_mod = sys.modules.setdefault(
        "simnibs.utils.TI_utils", types.ModuleType("simnibs.utils.TI_utils")
    )
    setattr(simnibs_mod, "utils", utils_mod)
    setattr(utils_mod, "TI_utils", ti_utils_mod)


# ============================================================================
# Source-code hygiene checks (no Qt import needed)
# ============================================================================


class TestGuiSourceHygiene:
    """Static checks over gui/ source files."""

    @pytest.mark.unit
    def test_no_pyside6_references(self):
        """No gui/ file should import PySide6 — the project uses PyQt5."""
        violations: list[str] = []
        for py_file in _all_py_sources():
            source = py_file.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(source.splitlines(), start=1):
                if "from PySide6" in line or "import PySide6" in line:
                    rel = py_file.relative_to(GUI_ROOT.parent.parent)
                    violations.append(f"{rel}:{i}: {line.strip()}")

        assert violations == [], "Found PySide6 imports in gui/ files:\n" + "\n".join(
            violations
        )

    @pytest.mark.unit
    def test_no_debug_checkbox_references(self):
        """No gui/ file should reference the removed debug_checkbox widget."""
        violations: list[str] = []
        for py_file in _all_py_sources():
            source = py_file.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(source.splitlines(), start=1):
                if "debug_checkbox" in line:
                    rel = py_file.relative_to(GUI_ROOT.parent.parent)
                    violations.append(f"{rel}:{i}: {line.strip()}")

        assert (
            violations == []
        ), "Found debug_checkbox references in gui/ files:\n" + "\n".join(violations)


# ============================================================================
# Import tests (require PyQt5 at runtime)
# ============================================================================


class TestGuiImports:
    """Verify that key GUI modules can be imported."""

    @pytest.mark.unit
    def test_gui_components_init(self):
        """tit.gui.components can be imported without error."""
        pyqt5 = pytest.importorskip("PyQt5")
        from tit.gui.components import (  # noqa: F401
            ConsoleWidget,
            ElectrodeConfigWidget,
            ROIPickerWidget,
            RunStopButtons,
            SolverParamsWidget,
            SubjectRow,
            SubjectRowManager,
            detect_message_type_from_content,
        )

    @pytest.mark.unit
    def test_ex_search_config_writer_includes_project_dir(self):
        """GUI Ex-Search JSON includes project_dir required by backend CLI."""
        pytest.importorskip("PyQt5")
        _mock_simnibs_ti_utils()

        from tit.gui.ex_search_tab import ExSearchTab
        from tit.opt.config import ExConfig

        config = ExConfig(
            subject_id="ernie",
            leadfield_hdf="/leadfields/ernie_leadfield_easycap.hdf5",
            roi_name="18_Left_Amyg.csv",
            electrodes=ExConfig.BucketElectrodes(
                e1_plus=["E1"],
                e1_minus=["E2"],
                e2_plus=["E3"],
                e2_minus=["E4"],
            ),
        )

        config_path = ExSearchTab._write_ex_config(config, "/project")
        try:
            with open(config_path) as f:
                data = json.load(f)
        finally:
            os.unlink(config_path)

        assert data["project_dir"] == "/project"
        assert data["electrodes"]["_type"] == "BucketElectrodes"

    @pytest.mark.unit
    def test_ex_search_coordinate_space_value(self):
        """Subject/MNI radio state maps to ExConfig.roi_coordinate_space."""
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab

        assert ExSearchTab.coordinate_space_value(False) == "subject"
        assert ExSearchTab.coordinate_space_value(True) == "mni"

    @pytest.mark.unit
    def test_ex_search_atlas_roi_chip_key_roundtrip(self):
        """Chip keys round-trip through atlas_roi_chip_key / atlas_roi_from_chip_key."""
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab

        key = ExSearchTab.atlas_roi_chip_key("/atlas/aseg.mgz", 17)
        assert ExSearchTab.atlas_roi_from_chip_key(key) == ("/atlas/aseg.mgz", 17)

        # label=None -> whole file as a binary mask
        key_whole = ExSearchTab.atlas_roi_chip_key("/atlas/mask.nii.gz", None)
        assert ExSearchTab.atlas_roi_from_chip_key(key_whole) == (
            "/atlas/mask.nii.gz",
            None,
        )

    @pytest.mark.unit
    def test_ex_search_build_roi_atlas_entries(self):
        """Selected atlas-ROI chips become ExConfig.AtlasROI-shaped dicts."""
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab
        from tit.opt.config import ExConfig

        keys = [
            ExSearchTab.atlas_roi_chip_key("/atlas/aseg.mgz", 17),
            ExSearchTab.atlas_roi_chip_key("/atlas/mask.nii.gz", None),
        ]
        entries = ExSearchTab.build_roi_atlas_entries(keys)
        assert entries == [
            {"atlas_path": "/atlas/aseg.mgz", "label": 17},
            {"atlas_path": "/atlas/mask.nii.gz", "label": None},
        ]

        # Feeds straight into ExConfig.roi_atlas without further conversion.
        config = ExConfig(
            subject_id="ernie",
            leadfield_hdf="/leadfields/ernie_leadfield_easycap.hdf5",
            roi_name="18_Left_Amyg.csv",
            roi_atlas=entries,
            electrodes=ExConfig.BucketElectrodes(
                e1_plus=["E1"],
                e1_minus=["E2"],
                e2_plus=["E3"],
                e2_minus=["E4"],
            ),
        )
        assert config.roi_atlas == [
            ExConfig.AtlasROI(atlas_path="/atlas/aseg.mgz", label=17),
            ExConfig.AtlasROI(atlas_path="/atlas/mask.nii.gz", label=None),
        ]

    @pytest.mark.unit
    def test_ex_search_tab_compiles(self):
        """tit/gui/ex_search_tab.py is syntactically valid Python.

        Unlike the other tests in this class, this one needs no PyQt5 (or
        any other import) at all -- py_compile only parses/compiles to
        bytecode, it never executes module-level code -- so it actually
        runs (not skips) on hosts without PyQt5 installed.
        """
        import py_compile

        py_compile.compile(str(GUI_ROOT / "ex_search_tab.py"), doraise=True)

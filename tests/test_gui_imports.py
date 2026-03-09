"""
Unit tests for GUI module hygiene and importability.

These tests verify coding-standard compliance (no stale framework
references, no leftover debug widgets) and that key GUI modules can
be imported without crashing.
"""

from pathlib import Path

import pytest

# Root of the tit/gui package on disk
GUI_ROOT = Path(__file__).resolve().parent.parent / "tit" / "gui"


def _all_py_sources() -> list[Path]:
    """Return every .py file under tit/gui/ (recursive)."""
    return sorted(GUI_ROOT.rglob("*.py"))


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

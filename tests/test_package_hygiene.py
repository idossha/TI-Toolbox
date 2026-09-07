"""Source-level hygiene guards over the ``tit`` package.

Successor to the deleted ``test_gui_imports.py``: v3 ships no PyQt interface
(the desktop app in ``desktop/`` drives ``tit.server`` over HTTP), so nothing
under ``tit/`` may import Qt again -- the container image deletes PyQt5
outright, and such an import would only fail at runtime.
"""

from pathlib import Path

import pytest

TIT_ROOT = Path(__file__).resolve().parent.parent / "tit"


def _all_py_sources() -> list[Path]:
    """Every ``.py`` file under ``tit/`` (recursive)."""
    return sorted(TIT_ROOT.rglob("*.py"))


@pytest.mark.unit
def test_sources_exist() -> None:
    """Guard against the sweep below silently checking nothing."""
    assert len(_all_py_sources()) > 50


@pytest.mark.unit
def test_no_qt_imports() -> None:
    """No file under ``tit/`` may import PyQt5, PyQt6 or PySide6."""
    violations: list[str] = []
    for py_file in _all_py_sources():
        source = py_file.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            if any(pkg in stripped for pkg in ("PyQt5", "PyQt6", "PySide6")):
                violations.append(f"{py_file.relative_to(TIT_ROOT.parent)}:{i}: {stripped}")

    assert violations == [], "Qt imports found under tit/ (v3 ships no PyQt GUI):\n" + "\n".join(
        violations
    )


@pytest.mark.unit
def test_gui_package_is_gone() -> None:
    """``tit/gui`` was deleted in v3; it must not come back."""
    assert not (TIT_ROOT / "gui").exists()

"""tit.blender exports, and its shared helper modules, carry nothing without a caller.

``tit/blender/utils.py`` had grown ten functions nothing called (config readers, electrode
CSV parsing, cylinder geometry, a PLY exporter) and ``scene_setup.py`` three (a point light, a
fixed camera, a material assigner), each kept alive by nothing at all. This guard reads the
source off disk, so it needs neither SimNIBS nor Blender:

- every name ``tit.blender`` exports lazily (``_EXPORTS``) is used by production code under
  ``tit/`` or ``dev/``, or documented for users in ``docs/wiki``;
- every public top-level function of ``utils.py`` and ``scene_setup.py`` is used by production
  code (a name or attribute load, or an import), other than its own definition.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLENDER = ROOT / "tit" / "blender"
PRODUCTION = [ROOT / "tit", ROOT / "dev"]
WIKI = ROOT / "docs" / "wiki"
HELPER_MODULES = ("utils.py", "scene_setup.py")


def _uses(tree: ast.AST) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            used.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            used.update(alias.name for alias in node.names)
    return used


USED: set[str] = set()
for _base in PRODUCTION:
    for _path in _base.rglob("*.py"):
        USED |= _uses(ast.parse(_path.read_text(encoding="utf-8")))

WIKI_TEXT = "\n".join(p.read_text(encoding="utf-8") for p in WIKI.rglob("*.md"))


def _exports() -> list[str]:
    tree = ast.parse((BLENDER / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_EXPORTS" for t in node.targets
        ):
            return list(ast.literal_eval(node.value))
    raise AssertionError("tit/blender/__init__.py has no _EXPORTS mapping")


def _public_functions(module: str) -> list[str]:
    tree = ast.parse((BLENDER / module).read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]


EXPORTS = _exports()
HELPERS = [(m, name) for m in HELPER_MODULES for name in _public_functions(m)]


def test_the_guard_sees_the_live_helpers() -> None:
    """A reader that found nothing would pass the cases below vacuously."""
    assert {"run_montage", "MontageConfig", "run_regions"} <= set(EXPORTS)
    assert ("utils.py", "extract_scalp_from_msh") in HELPERS
    assert ("scene_setup.py", "create_hero_camera") in HELPERS
    assert {"extract_scalp_from_msh", "create_hero_camera", "import_stl"} <= USED


def test_the_deleted_helpers_had_no_caller() -> None:
    for gone in (
        "get_montage_from_config",
        "find_electrode_csv",
        "create_electrode_geometry",
        "export_mesh_to_ply",
        "add_point_light",
        "add_camera",
        "assign_material",
    ):
        assert gone not in USED, gone
        assert gone not in {name for _, name in HELPERS}, gone


@pytest.mark.parametrize("name", EXPORTS)
def test_each_export_has_a_caller_or_a_user_page(name: str) -> None:
    documented = re.search(rf"\b{re.escape(name)}\b", WIKI_TEXT) is not None
    assert name in USED or documented, (
        f"tit.blender exports {name!r}, but no production code uses it and no wiki page "
        "documents it"
    )


@pytest.mark.parametrize("module,name", HELPERS, ids=lambda v: str(v))
def test_each_shared_helper_has_a_production_caller(module: str, name: str) -> None:
    assert (
        name in USED
    ), f"tit/blender/{module}: {name}() has no caller outside the tests; delete it"

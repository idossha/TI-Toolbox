"""Every name ``tit.plotting.nilearn`` exports is used by the toolbox or documented (p35).

What this pins, 2026-10-22: a name in ``tit/plotting/nilearn/__init__.py``'s ``__all__`` is
*live* when

1. code in ``tit/`` outside the module that defines it (and outside the package
   ``__init__.py`` that re-exports it) refers to it -- the runner calling a renderer, a
   module building on ``NilearnVisualizer``; or
2. ``docs/wiki`` mentions it -- the scripting API the user guide promises; or
3. the body of another live exported function refers to it (``render_fsaverage_map`` draws
   every map ``render_surface_stats_result`` writes).

Anything else is a dead entry point that the generated API reference keeps advertising. The
single-subject helpers (``create_pdf_entry_point``, ``create_glass_brain_entry_point``,
``create_html_entry_point``) were exported here, reachable only from their own argparse
``main()`` that nothing ran since the desktop app replaced the Qt extension.

The rule reads source off disk with :mod:`ast` (no import of nilearn or matplotlib), so it
holds on any host. A synthetic package proves it fires: an export used only by its own
module's ``main`` is reported, and the three ways of being live are not.

Reproduce: ``.venv/bin/python -m pytest tests/test_nilearn_public_api_guard.py -q -p no:cacheprovider``.
Deliberately elsewhere: ``tit.blender``'s exports (package p44).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]


def _exports(init: Path) -> list[str]:
    """The literal ``__all__`` list of a package ``__init__.py``."""
    for node in ast.parse(init.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            return list(ast.literal_eval(node.value))
    raise AssertionError(f"{init} has no literal __all__")


def _names_used(tree: ast.AST) -> set[str]:
    """Every name loaded or attribute read in *tree* (imports and definitions excluded)."""
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
    return used


def _definitions(package: Path) -> dict[str, tuple[Path, ast.AST]]:
    """Top-level ``def``/``class`` name -> (its module, its node) across *package*."""
    found = {}
    for module in sorted(package.glob("*.py")):
        for node in ast.parse(module.read_text()).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                found[node.name] = (module, node)
    return found


def dead_exports(package: Path, code_root: Path, wiki: Path) -> list[str]:
    """Names in *package*'s ``__all__`` that no rule in the module docstring makes live."""
    init = package / "__init__.py"
    exported = _exports(init)
    defs = _definitions(package)
    missing = [name for name in exported if name not in defs]
    assert not missing, f"__all__ names with no top-level definition: {missing}"

    used_by_module = {
        path: _names_used(ast.parse(path.read_text()))
        for path in sorted(code_root.rglob("*.py"))
        if path != init
    }
    wiki_text = "\n".join(p.read_text() for p in sorted(wiki.rglob("*.md")))

    live = set()
    for name in exported:
        home = defs[name][0]
        if any(name in used for path, used in used_by_module.items() if path != home):
            live.add(name)
        elif re.search(rf"\b{re.escape(name)}\b", wiki_text):
            live.add(name)
    grew = True
    while grew:
        reached = (
            set().union(*(_names_used(defs[n][1]) for n in live)) if live else set()
        )
        grew = bool((reached & set(exported)) - live)
        live |= reached & set(exported)
    return [name for name in exported if name not in live]


def test_every_nilearn_export_is_used_or_documented():
    package = REPO / "tit/plotting/nilearn"
    assert _exports(package / "__init__.py"), "found no exports to check"
    assert dead_exports(package, REPO / "tit", REPO / "docs/wiki") == []


def test_the_nilearn_package_carries_no_version_of_its_own():
    # tit has one version (tit/__init__.py); the package's "1.0.0" never moved.
    tree = ast.parse((REPO / "tit/plotting/nilearn/__init__.py").read_text())
    assigned = {
        t.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Name)
    }
    assert "__version__" not in assigned


def _is_script(path: Path) -> bool:
    """Whether *path* has a top-level ``if __name__ == "__main__":`` block."""
    for node in ast.parse(path.read_text()).body:
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        ):
            return True
    return False


def test_no_nilearn_module_is_a_script_of_its_own():
    # The one way to run these figures is `python -m tit.plotting.nilearn config.json`.
    modules = sorted((REPO / "tit/plotting/nilearn").glob("*.py"))
    scripts = [p.name for p in modules if _is_script(p)]
    assert "__main__.py" in scripts, "the rule found no scripts"
    assert sorted(set(scripts) - {"__main__.py"}) == []


# ── the rule fires on a planted dead export ─────────────────────────────────


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture()
def planted(tmp_path):
    code = tmp_path / "tit"
    pkg = code / "plotting" / "fake"
    _write(
        pkg / "__init__.py",
        "from .slices import used, orphan\nfrom .surface import documented, drawer\n"
        '__all__ = ["used", "orphan", "documented", "drawer"]\n',
    )
    _write(
        pkg / "slices.py",
        "def used():\n    return 1\n\n\ndef orphan():\n    return 2\n\n\n"
        "def main():\n    return orphan()\n",
    )
    _write(
        pkg / "surface.py",
        "def drawer():\n    return 3\n\n\ndef documented():\n    return drawer()\n",
    )
    _write(
        pkg / "__main__.py",
        "from tit.plotting.fake.slices import used\n\n\nused()\n",
    )
    wiki = tmp_path / "wiki"
    _write(wiki / "scripting.md", "Call `tit.plotting.fake.documented(...)`.\n")
    return pkg, code, wiki


def test_an_export_reached_only_from_its_own_main_is_reported(planted):
    assert dead_exports(*planted) == ["orphan"]


def test_an_export_mentioned_only_in_a_docstring_elsewhere_is_still_dead(planted):
    pkg, code, wiki = planted
    _write(code / "other.py", '"""See ``orphan`` in slices."""\n')
    assert dead_exports(pkg, code, wiki) == ["orphan"]


def test_a_caller_in_another_module_makes_it_live(planted):
    pkg, code, wiki = planted
    _write(code / "other.py", "from tit.plotting.fake import orphan\n\norphan()\n")
    assert dead_exports(pkg, code, wiki) == []


def test_without_the_wiki_page_the_documented_pair_is_dead(planted):
    pkg, code, wiki = planted
    (wiki / "scripting.md").unlink()
    assert dead_exports(pkg, code, wiki) == ["orphan", "documented", "drawer"]

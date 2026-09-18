"""The packaged example notebook must call the ``tit`` API that actually exists.

``tit/server/examples/example_workflow.ipynb`` is seeded into every project (and
``examples/notebooks/example_workflow.ipynb`` is a symlink to it), so a stale
import or keyword argument reaches every user as a traceback on their first
notebook. Executing it needs SimNIBS, a head model and an hour; this test
instead checks each code cell **off its source text** against the real package:

* every ``from X import Y`` resolves;
* every keyword passed to an imported callable (or a dataclass such as
  ``FlexConfig``) binds against that callable's real signature;
* every attribute read off ``pm`` exists on :class:`PathManager`, and every
  attribute read off the analysis result exists on :class:`AnalysisResult`;
* the project root comes from ``TIT_PROJECT_DIR`` and nothing names a host path.

The end-to-end run in the container is ``dev/run_example_notebook.sh``.

Reproduce: ``python3 -m pytest -q tests/test_example_notebook_api.py``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PACKAGED = REPO / "tit" / "server" / "examples" / "example_workflow.ipynb"
SYMLINK = REPO / "examples" / "notebooks" / "example_workflow.ipynb"


def _code_cells() -> list[str]:
    document = json.loads(PACKAGED.read_text())
    return ["".join(c["source"]) for c in document["cells"] if c["cell_type"] == "code"]


def test_the_repository_copy_is_the_packaged_file() -> None:
    """One source of truth: ``examples/notebooks/`` points at the packaged file."""
    assert SYMLINK.is_symlink(), "examples/notebooks/example_workflow.ipynb must be a symlink"
    assert SYMLINK.resolve() == PACKAGED.resolve()


def test_every_cell_is_a_program() -> None:
    for index, source in enumerate(_code_cells()):
        compile(source, f"<cell {index}>", "exec")


def _imports(tree: ast.Module) -> dict[str, object]:
    """Resolve ``from X import Y [as Z]`` and ``import X`` to the real objects."""
    bound: dict[str, object] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = importlib.import_module(node.module or "")
            for alias in node.names:
                assert hasattr(module, alias.name), f"{node.module} has no {alias.name}"
                bound[alias.asname or alias.name] = getattr(module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound[alias.asname or alias.name] = importlib.import_module(alias.name)
    return bound


def _resolve(node: ast.expr, bound: dict[str, object]) -> object | None:
    """``Name`` or dotted ``Attribute`` chain rooted at an imported name."""
    if isinstance(node, ast.Name):
        return bound.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _resolve(node.value, bound)
        if base is None:
            return None
        assert hasattr(base, node.attr), f"{base!r} has no attribute {node.attr}"
        return getattr(base, node.attr)
    return None


def test_every_import_and_keyword_resolves_against_tit() -> None:
    cells = _code_cells()
    bound: dict[str, object] = {}
    checked: list[str] = []
    for source in cells:
        tree = ast.parse(source)
        bound.update(_imports(tree))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _resolve(node.func, bound)
            if target is None or not callable(target):
                continue
            try:
                signature = inspect.signature(target)
            except (TypeError, ValueError):
                continue
            keywords = {k.arg: None for k in node.keywords if k.arg is not None}
            positional = [None] * len(node.args)
            try:
                signature.bind_partial(*positional, **keywords)
            except TypeError as exc:
                name = getattr(target, "__qualname__", repr(target))
                raise AssertionError(f"{name}({', '.join(keywords)}): {exc}") from exc
            checked.append(getattr(target, "__qualname__", repr(target)))
    # The calls the walkthrough is built on must actually have been checked.
    for expected in (
        "fetch_ernie",
        "run_pipeline",
        "FlexConfig",
        "run_flex_search",
        "upsert_montage",
        "load_montages",
        "SimulationConfig",
        "run_simulation",
        "Analyzer",
    ):
        assert any(expected in name for name in checked), f"{expected} was never called"


def test_every_attribute_read_off_pm_and_the_result_exists() -> None:
    from tit.analyzer import AnalysisResult
    from tit.opt import FlexResult
    from tit.paths import PathManager

    source = "\n".join(_code_cells())
    used = set(re.findall(r"\bpm\.([A-Za-z_][A-Za-z0-9_]*)", source))
    assert used, "the notebook must derive its paths from pm"
    assert used <= set(dir(PathManager)), used - set(dir(PathManager))

    fields = {f.name for f in AnalysisResult.__dataclass_fields__.values()}
    assert set(re.findall(r"\broi\.([A-Za-z_][A-Za-z0-9_]*)", source)) <= fields

    flex_fields = {f.name for f in FlexResult.__dataclass_fields__.values()}
    assert set(re.findall(r"\bresult\.([A-Za-z_][A-Za-z0-9_]*)", source)) <= flex_fields


def test_the_project_root_is_the_env_or_one_edited_line() -> None:
    source = "\n".join(_code_cells())
    assert 'os.environ.get("TIT_PROJECT_DIR")' in source
    assert "edit me" in source
    assert "/Users/" not in source and "C:\\" not in source and "/mnt/" not in source


def test_cortical_regions_carry_the_hemisphere() -> None:
    """``analyze_cortex`` region names are ``lh.<name>``/``rh.<name>``, never bare."""
    source = "\n".join(_code_cells())
    regions = re.findall(r"region=\"([^\"]+)\"", source)
    assert regions
    for region in regions:
        assert region.startswith(("lh.", "rh.")), region


def test_the_expensive_search_is_small_by_default() -> None:
    """A fresh user waits minutes, not hours: the flex cell is a reduced search."""
    source = "\n".join(_code_cells())
    assert re.search(r"n_multistart=1\b", source)
    assert re.search(r"max_iterations=\d+", source)
    assert re.search(r"population_size=\d+", source)


def test_the_wiki_page_is_rendered_from_the_notebook() -> None:
    """``docs/wiki/example-notebook.md`` is generated below its marker, never hand-edited."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("render", REPO / "dev" / "render_example_notebook.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    _, body = module.split(module.PAGE.read_text())
    assert body == module.render(), "run python3 dev/render_example_notebook.py"

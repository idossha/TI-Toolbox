"""Python the docs show, and the ``python -m tit.X`` commands they cite, run against the real API.

What this pins
--------------
Every fenced ```python block in ``docs/wiki/*.md``, ``README.md`` and
``agent-plugin/skills/*/SKILL.md`` (fences indented inside list items are dedented)
and every ``examples/scripts/*.py`` is checked off its source text against the
installed ``tit`` package, the way ``tests/test_example_notebook_api.py`` checks
the packaged notebook:

* it compiles;
* every ``from tit... import X`` resolves through ``getattr`` (so ``tit.blender``'s
  lazy ``__getattr__`` exports count, and a name a package does not export fails);
* every keyword passed to an imported callable, a nested class or enum reached
  from it (``FlexConfig.SphericalROI``), or a method of an instance built from an
  imported class (``analyzer = Analyzer(...); analyzer.analyze_sphere(...)``)
  binds against the real ``inspect.signature``.

Every ``python -m tit.X`` / ``simnibs_python -m tit.X`` command in the wiki,
``docs/dev/TESTING.md``, the README and the skills names a module with a
``__main__`` guard or a package with ``__main__.py``; ``tit.<a|b>`` alternations
are expanded, ``tit.<module>`` placeholders skipped.

The expectations are the real signatures (no number here is typed from the
docs); floors on the counts keep a broken fence parser from passing on zero.
Reproduce: ``.venv/bin/python -m pytest tests/test_docs_code_api.py tests/test_scripts.py -q``.
Executing the scripts needs SimNIBS and a head model; that is not done here.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import textwrap
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

FENCE = re.compile(
    r"^(?P<indent>[ \t]*)```(?:python|py)[ \t]*\n(?P<body>.*?)^(?P=indent)```",
    re.DOTALL | re.MULTILINE,
)
MODULE_COMMAND = re.compile(
    r"(?:python3?|simnibs_python)\s+-m\s+(tit(?:\.(?:<[^>]*>|[A-Za-z_]\w*))*)"
)

#: Module names the docs cite on purpose although no such module exists, with why.
HYPOTHETICAL_MODULES = {
    "tit.reporting.generators.my_report": (
        "ti-codebase skill, 'How to add a new component': the name a contributor gives "
        "a new report generator"
    ),
}


@dataclass(frozen=True)
class Block:
    """One code block: where it is (``path:line`` of its first line) and its source."""

    path: str
    line: int
    source: str

    @property
    def label(self) -> str:
        return f"{self.path}:{self.line}"


def doc_files() -> list[Path]:
    return (
        sorted((REPO / "docs" / "wiki").glob("*.md"))
        + [REPO / "README.md"]
        + sorted((REPO / "agent-plugin" / "skills").glob("*/SKILL.md"))
    )


def python_blocks(path: Path, root: Path = REPO) -> list[Block]:
    """Every ```python fence in a markdown file, dedented to its fence's indent."""
    text = path.read_text(encoding="utf-8")
    blocks = []
    for match in FENCE.finditer(text):
        line = text.count("\n", 0, match.start("body")) + 1
        source = textwrap.dedent(match.group("body"))
        blocks.append(Block(path.relative_to(root).as_posix(), line, source))
    return blocks


def _import_module(name: str) -> types.ModuleType:
    return importlib.import_module(name)


def _getattr(base: object, attr: str) -> object:
    """``getattr`` that also imports a not-yet-imported submodule of a package."""
    if hasattr(base, attr):
        return getattr(base, attr)
    if isinstance(base, types.ModuleType):
        return _import_module(f"{base.__name__}.{attr}")
    raise AttributeError(attr)


class _Checker:
    """Resolves one block's ``tit`` imports and calls; collects problems."""

    def __init__(self, block: Block) -> None:
        self.block = block
        self.problems: list[str] = []
        self.bound: dict[str, object] = {}
        self.instances: dict[str, type] = {}
        self.imports = 0
        self.calls: list[str] = []

    def at(self, node: ast.AST) -> str:
        return f"{self.block.path}:{self.block.line + getattr(node, 'lineno', 1) - 1}"

    def run(self) -> None:
        try:
            tree = ast.parse(self.block.source)
        except SyntaxError as exc:
            line = self.block.line + (exc.lineno or 1) - 1
            self.problems.append(f"{self.block.path}:{line}: not Python: {exc.msg}")
            return
        self._bind_imports(tree)
        self._bind_instances(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self._check_call(node)
            elif isinstance(node, ast.Attribute) and _root(node) in self.bound:
                # Enum members and nested classes read without a call
                # (`test_type=GroupComparisonConfig.TestType.UNPAIRED`).
                self._resolve(node)
        self.problems = list(dict.fromkeys(self.problems))

    def _bind_imports(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[0] == "tit"
            ):
                try:
                    module = _import_module(node.module)
                except ImportError as exc:
                    self.problems.append(
                        f"{self.at(node)}: import {node.module}: {exc}"
                    )
                    continue
                for alias in node.names:
                    self.imports += 1
                    try:
                        self.bound[alias.asname or alias.name] = _getattr(
                            module, alias.name
                        )
                    except (AttributeError, ImportError):
                        self.problems.append(
                            f"{self.at(node)}: {node.module} has no {alias.name}"
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] != "tit":
                        continue
                    self.imports += 1
                    try:
                        module = _import_module(alias.name)
                    except ImportError as exc:
                        self.problems.append(
                            f"{self.at(node)}: import {alias.name}: {exc}"
                        )
                        continue
                    if alias.asname:
                        self.bound[alias.asname] = module
                    else:
                        self.bound["tit"] = _import_module("tit")

    def _bind_instances(self, tree: ast.Module) -> None:
        """``name = ImportedClass(...)``, when every assignment to ``name`` agrees."""
        seen: dict[str, set[object]] = {}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            value = node.value
            cls = None
            if isinstance(value, ast.Call):
                cls = self._resolve(value.func, report=False)
            seen.setdefault(target.id, set()).add(cls if inspect.isclass(cls) else None)
        for name, classes in seen.items():
            if len(classes) == 1 and None not in classes:
                self.instances[name] = next(iter(classes))

    def _resolve(self, node: ast.expr, *, report: bool = True) -> object | None:
        """A ``Name``/``Attribute`` chain rooted at an imported name or a known instance."""
        if isinstance(node, ast.Name):
            return self.bound.get(node.id)
        if not isinstance(node, ast.Attribute):
            return None
        if isinstance(node.value, ast.Name) and node.value.id in self.instances:
            cls = self.instances[node.value.id]
            if not hasattr(cls, node.attr):
                if report:
                    self.problems.append(
                        f"{self.at(node)}: {cls.__qualname__} has no attribute {node.attr}"
                    )
                return None
            return _Method(getattr(cls, node.attr))
        base = self._resolve(node.value, report=report)
        if base is None or isinstance(base, _Method):
            return None
        try:
            return _getattr(base, node.attr)
        except (AttributeError, ImportError):
            if report:
                name = getattr(base, "__qualname__", None) or getattr(
                    base, "__name__", repr(base)
                )
                self.problems.append(
                    f"{self.at(node)}: {name} has no attribute {node.attr}"
                )
            return None

    def _check_call(self, node: ast.Call) -> None:
        target = self._resolve(node.func)
        if target is None:
            return
        method = isinstance(target, _Method)
        func = target.func if method else target
        if not callable(func):
            return
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return
        if any(isinstance(a, ast.Starred) for a in node.args):
            positional: list[None] = []
        else:
            positional = [None] * (len(node.args) + (1 if method else 0))
        keywords = {k.arg: None for k in node.keywords if k.arg is not None}
        name = getattr(func, "__qualname__", repr(func))
        try:
            signature.bind_partial(*positional, **keywords)
        except TypeError as exc:
            self.problems.append(
                f"{self.at(node)}: {name}({', '.join(keywords)}): {exc}"
            )
            return
        self.calls.append(name)


def _root(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


@dataclass(frozen=True)
class _Method:
    """An unbound method reached through an instance of an imported class."""

    func: object


def check_blocks(blocks: list[Block]) -> tuple[list[str], int, list[str]]:
    """``(problems, imports resolved, calls bound)`` over ``blocks``."""
    problems: list[str] = []
    imports = 0
    calls: list[str] = []
    for block in blocks:
        checker = _Checker(block)
        checker.run()
        problems += checker.problems
        imports += checker.imports
        calls += checker.calls
    return problems, imports, calls


def script_blocks() -> list[Block]:
    scripts = sorted((REPO / "examples" / "scripts").glob("*.py"))
    return [
        Block(p.relative_to(REPO).as_posix(), 1, p.read_text(encoding="utf-8"))
        for p in scripts
    ]


def _docs_blocks() -> list[Block]:
    return [block for path in doc_files() for block in python_blocks(path)]


# -- tests ------------------------------------------------------------------------


def test_the_docs_python_blocks_compile_and_resolve_against_tit() -> None:
    blocks = _docs_blocks()
    assert len(blocks) >= 30, f"only {len(blocks)} python blocks found -- fence parser?"
    problems, imports, calls = check_blocks(blocks)
    print(f"{len(blocks)} blocks, {imports} tit imports, {len(calls)} calls bound")
    assert not problems, "\n".join(problems)
    assert imports >= 60, f"only {imports} tit imports resolved (73 on 2026-10-22)"
    assert len(calls) >= 40, f"only {len(calls)} calls bound (51 on 2026-10-22)"


def test_an_indented_fence_inside_a_list_item_is_checked() -> None:
    """example-data.md's fence sits in a list item; dedenting must keep it."""
    blocks = python_blocks(REPO / "docs" / "wiki" / "example-data.md")
    sources = "\n".join(b.source for b in blocks)
    assert "fetch_ernie(PROJECT)" in sources
    _problems, _imports, calls = check_blocks(blocks)
    assert any(c.endswith("fetch_ernie") for c in calls), calls


def test_a_stale_keyword_fails_with_its_file_and_line(tmp_path: Path) -> None:
    doc = tmp_path / "fixture.md"
    doc.write_text(
        "# Fixture\n"
        "\n"
        "Some prose.\n"
        "\n"
        "```python\n"
        "from tit.sim import SimulationConfig\n"
        "\n"
        "config = SimulationConfig(subject_id='ernie', nonexistent_kw=1)\n"
        "```\n",
        encoding="utf-8",
    )
    blocks = python_blocks(doc, root=tmp_path)
    assert [b.line for b in blocks] == [6]  # the fence opens on line 5
    problems, _imports, _calls = check_blocks(blocks)
    assert len(problems) == 1
    assert problems[0].startswith(
        "fixture.md:8: SimulationConfig(subject_id, nonexistent_kw)"
    )
    assert "nonexistent_kw" in problems[0]


@pytest.mark.parametrize(
    ("source", "expected", "line"),
    [
        ("from tit.opt.flex import FlexConfig\n", "tit.opt.flex has no FlexConfig", 10),
        (
            "from tit.blender import NoSuchConfig\n",
            "tit.blender has no NoSuchConfig",
            10,
        ),
        (
            "from tit.opt import FlexConfig\nFlexConfig.SphericalROI(x=1, bogus=2)\n",
            "bogus",
            11,
        ),
        (
            "from tit.analyzer import Analyzer\n"
            "a = Analyzer(subject_id='x', simulation='s', space='mesh')\n"
            "a.analyze_sphere(center=(0, 0, 0), radius=5, centre_space='MNI')\n",
            "centre_space",
            12,
        ),
        (
            "from tit.analyzer import Analyzer\n"
            "a = Analyzer(subject_id='x', simulation='s', space='mesh')\n"
            "a.analyse_sphere(center=(0, 0, 0))\n",
            "Analyzer has no attribute analyse_sphere",
            12,
        ),
        (
            "from tit.stats import GroupComparisonConfig\n"
            "GroupComparisonConfig(test_type=GroupComparisonConfig.TestType.UNPAIRD)\n",
            "has no attribute UNPAIRD",
            11,
        ),
        (
            "import tit.sim\ntit.sim.run_simulaton(None)\n",
            "has no attribute run_simulaton",
            11,
        ),
    ],
)
def test_each_kind_of_drift_is_caught(source: str, expected: str, line: int) -> None:
    problems, _imports, _calls = check_blocks([Block("probe.md", 10, source)])
    assert len(problems) == 1 and expected in problems[0], problems
    assert problems[0].startswith(f"probe.md:{line}: "), problems


def test_the_blender_lazy_exports_resolve() -> None:
    problems, imports, _calls = check_blocks(
        [Block("probe.md", 1, "from tit.blender import MontageConfig, run_montage\n")]
    )
    assert problems == [] and imports == 2


def _cited_modules() -> list[tuple[str, str]]:
    files = (
        sorted((REPO / "docs" / "wiki").glob("*.md"))
        + [REPO / "docs" / "dev" / "TESTING.md", REPO / "README.md"]
        + sorted((REPO / "agent-plugin" / "skills").glob("*/SKILL.md"))
    )
    cited: list[tuple[str, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in MODULE_COMMAND.finditer(text):
            where = (
                f"{path.relative_to(REPO)}:{text.count(chr(10), 0, match.start()) + 1}"
            )
            for module in _expand(match.group(1)):
                cited.append((where, module))
    return cited


def _expand(dotted: str) -> list[str]:
    """``tit.<a|b.c>`` -> ``[tit.a, tit.b.c]``; a ``<placeholder>`` without ``|`` -> ``[]``."""
    match = re.search(r"<([^>]*)>", dotted)
    if match is None:
        return [dotted]
    if "|" not in match.group(1):
        return []
    head, tail = dotted[: match.start()], dotted[match.end() :]
    return [m for alt in match.group(1).split("|") for m in _expand(head + alt + tail)]


def _runnable(module: str) -> bool:
    path = REPO.joinpath(*module.split("."))
    if (path / "__main__.py").is_file():
        return True
    source = path.with_suffix(".py")
    if not source.is_file():
        return False
    return bool(
        re.search(r"^if __name__ == ['\"]__main__['\"]:", source.read_text(), re.M)
    )


def test_every_cited_module_command_names_a_runnable_module() -> None:
    cited = _cited_modules()
    assert len(cited) >= 40, f"only {len(cited)} `-m tit.X` commands found -- regex?"
    broken = [
        f"{where}: python -m {module}"
        for where, module in cited
        if module not in HYPOTHETICAL_MODULES and not _runnable(module)
    ]
    assert not broken, "cited modules with no __main__:\n" + "\n".join(broken)
    # The alternation form is expanded, not skipped.
    assert "tit.opt.mex" in {m for _w, m in cited}


def test_module_expansion() -> None:
    assert _expand("tit.sim") == ["tit.sim"]
    assert _expand("tit.<module>") == []
    assert _expand("tit.<sim|opt.flex>") == ["tit.sim", "tit.opt.flex"]
    assert not _runnable("tit.no_such_module")
    assert not _runnable("tit.calc")  # a library module with no __main__ guard

"""Coverage configuration excludes only what it says it excludes.

What this pins
--------------
``.coveragerc`` ``exclude_lines`` are regexes that coverage.py applies with
``re.search`` to every source line; when a matched line opens a block (a
``def``, an ``if``), coverage drops the *whole block* (coverage.py docs,
"Excluding code from coverage.py": "if the excluded line introduces a block,
the entire block is excluded").  An unanchored ``pass`` therefore hid every
function whose signature says ``passes=`` or ``st="pass"`` and every
``if qc.passed:`` branch -- 467 lines in the 2026-10 coverage report.

* Every line any exclude regex matches in ``tit/`` must be one of the
  statement shapes the patterns exist for (bare ``pass``, a ``pragma: no
  cover`` comment, ``if TYPE_CHECKING:``, the ``__main__`` guard, ``raise
  NotImplementedError/AssertionError``, ``@abstractmethod``, ``def
  __repr__/__str__``).  The shapes are hand-written from the comments in
  ``.coveragerc`` itself, not read from the patterns.
* coverage.py's own parser, fed the configured patterns, keeps the functions
  the old pattern hid (found by name with ``ast``, not by line number).
* Every ``omit`` pattern matches a file under ``tit/`` and carries a reason
  comment; ``codecov.yml`` has no ``ignore`` list of its own, every flag path
  matches a file coverage reports, and the flags declared are exactly the flags
  CI uploads.

Reproduce: ``.venv/bin/python -m pytest tests/test_coveragerc.py -q``.
The coverage numbers themselves come from the CI host leg (``--cov=tit``).
"""

from __future__ import annotations

import ast
import configparser
import fnmatch
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
COVERAGERC = REPO / ".coveragerc"
CODECOV = REPO / "codecov.yml"
CIRCLECI = REPO / ".circleci" / "config.yml"
TIT = REPO / "tit"

# The statement shapes an exclusion may land on, written from the intent comments in
# .coveragerc ("Standard pragma", "debug code", "defensive assertion code", "non-runnable
# code", "abstract methods", "pass statements").  Matched against the stripped line.
ALLOWED_SHAPES = (
    re.compile(r"pass\s*(#.*)?"),
    re.compile(r".*#\s*pragma:\s*no cover.*"),
    re.compile(r"(el)?if (typing\.)?TYPE_CHECKING:\s*(#.*)?"),
    re.compile(r"if __name__ == ['\"]__main__['\"]:\s*(#.*)?"),
    re.compile(r"raise (NotImplementedError|AssertionError)\b.*"),
    re.compile(r"@(abc\.)?abstractmethod\s*(#.*)?"),
    re.compile(r"def __(repr|str)__\(.*"),
)


def _report_section() -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    parser.read(COVERAGERC, encoding="utf-8")
    return parser["report"]


def _exclude_patterns() -> list[str]:
    raw = _report_section()["exclude_lines"]
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _omit_patterns() -> list[str]:
    parser = configparser.ConfigParser()
    parser.read(COVERAGERC, encoding="utf-8")
    raw = parser["run"]["omit"]
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _tit_sources() -> list[Path]:
    return sorted(p for p in TIT.rglob("*.py") if "__pycache__" not in p.parts)


def _omitted(path: Path, patterns: list[str]) -> bool:
    """coverage.py's omit rule: a pattern without a leading wildcard is cwd-relative."""
    text = str(path)
    for pattern in patterns:
        if not pattern.startswith(("*", "/")):
            pattern = str(REPO / pattern)
        if fnmatch.fnmatch(text, pattern):
            return True
    return False


def _measured_files() -> list[str]:
    """Repo-relative paths coverage reports: ``source = tit`` minus ``omit``."""
    omit = _omit_patterns()
    return [
        p.relative_to(REPO).as_posix() for p in _tit_sources() if not _omitted(p, omit)
    ]


def _excluded_by_coverage(path: Path) -> set[int]:
    """Lines coverage.py itself excludes in ``path`` under the configured patterns."""
    from coverage.misc import join_regex
    from coverage.parser import PythonParser

    parser = PythonParser(
        text=path.read_text(encoding="utf-8"),
        filename=str(path),
        exclude=join_regex(_exclude_patterns()),
    )
    parser.parse_source()
    return set(parser.excluded)


def _function_span(path: Path, name: str) -> tuple[int, int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node.lineno, node.end_lineno
    raise AssertionError(f"{path.relative_to(REPO)} has no function {name}")


def test_every_line_an_exclude_pattern_matches_is_an_allowed_shape() -> None:
    """Lines matched the way coverage.py matches them (one MULTILINE search per pattern)."""
    from coverage.parser import PythonParser

    patterns = _exclude_patterns()
    assert patterns, ".coveragerc has no exclude_lines to check"
    matched = 0
    offenders: list[str] = []
    for path in _tit_sources():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        parser = PythonParser(text=text, filename=str(path))
        hits: set[int] = set()
        for pattern in patterns:
            hits |= parser.lines_matching(pattern)
        for number in sorted(hits):
            line = lines[number - 1] if number <= len(lines) else ""
            matched += 1
            if not any(shape.fullmatch(line.strip()) for shape in ALLOWED_SHAPES):
                offenders.append(f"{path.relative_to(REPO)}:{number}: {line.strip()}")
    # The patterns exist for real code: bare `pass` and the __main__ guard occur in tit/.
    assert matched > 50, f"exclude_lines matched only {matched} lines -- parser broke?"
    assert not offenders, (
        f"{len(offenders)} line(s) excluded from coverage that are not an excludable "
        "statement (a matched block header drops its whole block):\n  "
        + "\n  ".join(offenders[:40])
    )


@pytest.mark.parametrize(
    ("relpath", "function"),
    [
        ("tit/scene/build.py", "one_ring_mode_filter"),  # signature: passes=...
        ("tit/reporting/html/components.py", "gate_scale"),  # signature: st="pass"
        ("tit/reporting/html/components.py", "verdict"),  # return "pass", ...
        ("tit/pre/qsi/dti_extractor.py", "extract_dti_tensor"),  # if qc.passed:
        ("tit/reporting/generators/dti_qc.py", "build_html"),  # if passed:
    ],
)
def test_coverage_measures_functions_whose_text_says_pass(
    relpath: str, function: str
) -> None:
    path = REPO / relpath
    start, end = _function_span(path, function)
    hidden = sorted(n for n in _excluded_by_coverage(path) if start <= n <= end)
    assert not hidden, (
        f"coverage.py excludes {len(hidden)} line(s) of {relpath}::{function} "
        f"(lines {hidden[0]}..{hidden[-1]})"
    )


def test_bare_pass_is_still_excluded() -> None:
    """The anchored pattern keeps doing its job on a real ``pass`` statement."""
    from coverage.misc import join_regex
    from coverage.parser import PythonParser

    source = "def f():\n    try:\n        x = 1\n    except OSError:\n        pass\n"
    parser = PythonParser(text=source, exclude=join_regex(_exclude_patterns()))
    parser.parse_source()
    assert parser.excluded == {5}


def test_every_omit_pattern_matches_a_file_and_says_why() -> None:
    patterns = _omit_patterns()
    assert patterns, ".coveragerc [run] omit is empty"
    sources = _tit_sources()
    dead = [p for p in patterns if not any(_omitted(s, [p]) for s in sources)]
    assert not dead, f"omit patterns that match no file under tit/: {dead}"

    lines = COVERAGERC.read_text(encoding="utf-8").splitlines()
    unexplained = []
    for pattern in patterns:
        index = next(i for i, line in enumerate(lines) if line.strip() == pattern)
        previous = next(
            (lines[j].strip() for j in range(index - 1, -1, -1) if lines[j].strip()),
            "",
        )
        if not previous.startswith("#"):
            unexplained.append(pattern)
    assert (
        not unexplained
    ), f"omit patterns without a reason comment above them: {unexplained}"


def test_codecov_flags_name_reported_files_and_equal_the_uploads() -> None:
    config = yaml.safe_load(CODECOV.read_text(encoding="utf-8"))
    measured = _measured_files()
    assert len(measured) > 100, f"only {len(measured)} measured files -- omit broke?"

    def matches(pattern: str) -> bool:
        if pattern.endswith("/"):
            return any(f.startswith(pattern) for f in measured)
        return any(
            fnmatch.fnmatch(f, pattern) or f == pattern or f.startswith(pattern + "/")
            for f in measured
        )

    flags = config.get("flags", {}) or {}
    dead_paths = [
        f"{name}: {path}"
        for name, flag in flags.items()
        for path in flag.get("paths", [])
        if not matches(path)
    ]
    assert (
        not dead_paths
    ), f"codecov.yml flag paths that match no reported file: {dead_paths}"

    ci_text = CIRCLECI.read_text(encoding="utf-8")
    uploaded = set(re.findall(r"(?:^|\s)-F\s+(\S+)", ci_text))
    assert uploaded, ".circleci/config.yml uploads no Codecov flag"
    assert set(flags) == uploaded, (
        f"codecov.yml declares flags {sorted(flags)} but CI uploads {sorted(uploaded)}: "
        "a declared flag that is never uploaded reports nothing"
    )


def test_codecov_has_no_second_ignore_list() -> None:
    """What is left unmeasured is decided once, in ``.coveragerc`` ``omit``.

    codecov.yml's ``ignore`` list hid library code from the reported number (its
    ``tit/tools/**`` covered modules sim, catalog and viewspec import) while the
    coverage run measured it, so a reader of either saw a different scope.
    """
    config = yaml.safe_load(CODECOV.read_text(encoding="utf-8"))
    assert "ignore" not in config, f"codecov.yml ignore: {config['ignore']}"
    flagged = [name for name, flag in config["flags"].items() if "ignore" in flag]
    assert not flagged, f"codecov.yml flags with their own ignore list: {flagged}"


def test_package_inits_with_real_code_are_measured() -> None:
    """A blanket ``*/__init__.py`` omit hid the 464-line example-data downloader."""
    measured = set(_measured_files())
    assert "tit/examples/__init__.py" in measured
    assert "tit/server/routes/__init__.py" in measured

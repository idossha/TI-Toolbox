"""The API site's ``tit.constants`` table names constants that exist, with their real values.

What this pins (2026-10-22): ``docs/api_mkdocs/docs/pipeline/core.md`` "## Constants" is the
published description of :mod:`tit.constants`. Every constant it names must be an attribute of
the module (a ``PREFIX_*`` entry must match at least one), every value it shows beside a name
must be that attribute's value, and every line of its code sample must evaluate to the value its
comment states. The table used to present 19 constants nothing read (``DIR_SIMNIBS``,
``DEFAULT_RADIUS_MM``, ``PLOT_DPI``...) as the module's public surface; they were deleted and
the table now names only live constants. Deleting a constant the page still names fails here.

Where the expected values come from: the page itself (hand-written for readers); the module is
the thing checked against it.

Reproduce: ``.venv/bin/python -m pytest tests/test_api_docs_constants.py -q``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tit import constants

CORE_MD = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "api_mkdocs"
    / "docs"
    / "pipeline"
    / "core.md"
)

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\*|\(\))?$")


def constants_section(text: str) -> str:
    """The body of the page's ``## Constants`` section."""
    start = text.index("## Constants\n")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def table_problems(section: str) -> tuple[int, list[str]]:
    """Names and ``name (value)`` pairs in the table that disagree with :mod:`tit.constants`.

    Returns the number of names checked and one message per disagreement.
    """
    checked = 0
    problems: list[str] = []
    for row in section.splitlines():
        if not row.startswith("| **"):
            continue
        examples = row.split("|")[2]
        for match in re.finditer(
            r"(?<!\()`([^`]+)`(?:\s*\((`?)([^()`]*(?:\([^`]*\))?[^`]*?)\2\))?", examples
        ):
            name, value = match.group(1), match.group(3)
            if not _NAME.match(name):
                continue
            checked += 1
            bare = name.rstrip("*").removesuffix("()")
            if name.endswith("*"):
                if not any(attr.startswith(bare) for attr in vars(constants)):
                    problems.append(f"no constant starts with {bare}")
                continue
            if not hasattr(constants, bare):
                problems.append(f"{bare} is not in tit.constants")
                continue
            if value:
                actual = getattr(constants, bare)
                if value not in (str(actual), repr(actual)):
                    problems.append(f"{bare} is {actual!r}, the page says {value}")
    return checked, problems


def sample_problems(section: str) -> tuple[int, list[str]]:
    """Lines ``const.<expr>  # <value>`` of the code sample whose value differs."""
    checked = 0
    problems: list[str] = []
    for line in section.splitlines():
        if not line.startswith("const."):
            continue
        expr, _, comment = line.partition("#")
        comment = comment.strip()
        checked += 1
        # The value, or the value before a ": explanation".
        for candidate in (comment, comment.split(":", 1)[0]):
            try:
                expected = ast.literal_eval(candidate)
                break
            except (ValueError, SyntaxError):
                continue
        else:
            problems.append(f"{expr.strip()}: the comment {comment!r} is not a value")
            continue
        try:
            actual = eval(expr.strip(), {"__builtins__": {}}, {"const": constants})
        except AttributeError as err:
            problems.append(f"{expr.strip()}: {err}")
            continue
        if actual != expected:
            problems.append(f"{expr.strip()} is {actual!r}, the page says {expected!r}")
    return checked, problems


def test_every_constant_the_api_page_names_exists_with_the_value_shown():
    checked, problems = table_problems(constants_section(CORE_MD.read_text()))
    assert checked >= 20, f"only {checked} names found: the table parser lost the table"
    assert problems == []


def test_the_api_page_code_sample_evaluates_to_its_comments():
    checked, problems = sample_problems(constants_section(CORE_MD.read_text()))
    assert checked >= 3, f"only {checked} sample lines found"
    assert problems == []


def test_the_checker_catches_a_missing_constant_and_a_wrong_value():
    section = (
        "## Constants\n\n| Category | Examples |\n|---|---|\n"
        "| **Gone** | `DIR_SIMNIBS`, `FIELD_TI_MAX` (`TI_min`) |\n"
        "| **Glob** | `NO_SUCH_PREFIX_*` |\n\n"
        "```python\nconst.TI_ELECTRODE_PAIRS   # 3\n```\n"
    )
    checked, problems = table_problems(section)
    assert checked == 3
    assert problems == [
        "DIR_SIMNIBS is not in tit.constants",
        "FIELD_TI_MAX is 'TI_max', the page says TI_min",
        "no constant starts with NO_SUCH_PREFIX_",
    ]
    checked, problems = sample_problems(section)
    assert checked == 1
    assert problems == ["const.TI_ELECTRODE_PAIRS is 2, the page says 3"]

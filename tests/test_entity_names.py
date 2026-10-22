"""The server's two name rules answer exactly what ``tests/fixtures/entity_names.json`` says.

What this pins: ``tit.paths.is_valid_name`` (``NAME_RE``, every user-supplied name that becomes
one path component) and ``tit.catalog.is_safe_name`` (a new montage, free-hand placement or ROI)
return the fixture's verdict for every name in it. The desktop's ``isValidEntityName`` /
``isSafeName`` (``desktop/src/renderer/pages/_shared/entityNames.ts``) are pinned to the same file
by ``desktop/tests/unit/entity-names.test.ts``, so the Save and Run gates refuse exactly what the
server refuses.

Where the expected values come from: the fixture was typed from the rules' documentation (the
``NAME_RE`` comment in ``tit/paths.py`` and the ``is_safe_name`` docstring), not computed by
these functions. Reproduce: ``.venv/bin/python -m pytest tests/test_entity_names.py -q``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tit.catalog import is_safe_name
from tit.paths import is_valid_name, validate_name

FIXTURE = Path(__file__).parent / "fixtures" / "entity_names.json"
DATA = json.loads(FIXTURE.read_text())
CASES = DATA["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["why"] for c in CASES])
def test_is_valid_name_matches_the_fixture(case: dict) -> None:
    assert is_valid_name(case["name"]) is case["is_valid_name"], case["why"]


@pytest.mark.parametrize("case", CASES, ids=[c["why"] for c in CASES])
def test_is_safe_name_matches_the_fixture(case: dict) -> None:
    assert is_safe_name(case["name"]) is case["is_safe_name"], case["why"]


@pytest.mark.parametrize(
    "case", [c for c in CASES if not c["is_valid_name"]], ids=lambda c: c["why"]
)
def test_validate_name_refuses_with_the_rule(case: dict) -> None:
    """The sentence the desktop shows (``ENTITY_NAME_RULE``) is the one the server raises."""
    with pytest.raises(ValueError) as raised:
        validate_name(case["name"], "montage")
    assert DATA["valid_name_rule"] in str(raised.value)


def test_the_fixture_exercises_both_verdicts_of_both_rules() -> None:
    """A table where one rule never says no could not catch a rule that always says yes."""
    for rule in ("is_valid_name", "is_safe_name"):
        assert {c[rule] for c in CASES} == {True, False}, rule
    # The rules differ: a name valid as a path component but not as a saved entry is in it.
    assert any(c["is_valid_name"] and not c["is_safe_name"] for c in CASES)
    # Every safe name is also a valid path component (the catalog rule is the stricter one).
    assert all(c["is_valid_name"] for c in CASES if c["is_safe_name"])

"""The server's notebook-name rule, case by case, against the table the desktop reads too.

What it pins: ``tit/server/notebooks.py::normalise_name`` and the desktop's ``proposeName``
(``desktop/src/renderer/pages/notebooks/index.tsx``, which names an imported ``.ipynb``) state one
rule twice. Drift between them shows up as an import the page lets through and the server then
refuses, or one the page refuses although the server would take it.

Where the expected values come from: ``tests/fixtures/notebook_names.json``, verdicts written by
hand from the rule in its ``_about`` (unicode, a leading dot, 128 vs 129 characters, a trailing
space, ``a/b``, the ``examples/`` prefix). ``desktop/tests/unit/notebook-names-table.test.ts``
checks ``proposeName`` against the same rows. A row with ``server_known_gap`` is a disagreement
this package found and does not own the fix for; it is a strict xfail, so the fix turns it red
until the marker is removed.

Reproduce: ``.venv/bin/python -m pytest tests/test_notebook_names_table.py -q``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tit.server.notebooks import NotebookError, normalise_name

TABLE = json.loads(
    (Path(__file__).parent / "fixtures" / "notebook_names.json").read_text()
)
ROWS = TABLE["rows"]


def _case(row: dict):
    marks = []
    if "server_known_gap" in row:
        marks.append(pytest.mark.xfail(strict=True, reason=row["server_known_gap"]))
    return pytest.param(row, id=row["why"], marks=marks)


def test_the_table_covers_both_verdicts_and_the_length_boundary() -> None:
    assert any(row["server"] is None for row in ROWS)
    assert any(row["server"] is not None for row in ROWS)
    assert {row.get("length") for row in ROWS} >= {128, 129}
    for row in ROWS:
        if "length" in row:
            assert len(row["name"]) == row["length"], row["why"]


@pytest.mark.parametrize("row", [_case(row) for row in ROWS])
def test_normalise_name_matches_the_table(row: dict) -> None:
    if row["server"] is None:
        with pytest.raises(NotebookError) as excinfo:
            normalise_name(row["name"])
        assert excinfo.value.code == "bad-name"
    else:
        assert normalise_name(row["name"]) == row["server"]


@pytest.mark.parametrize(
    "row",
    [r for r in ROWS if r["client"] is not None and "server_known_gap" not in r],
    ids=lambda r: r["why"],
)
def test_a_name_the_page_proposes_is_one_the_server_accepts(row: dict) -> None:
    """What the import sends (``proposeName``'s output) the server must not refuse.

    The file it makes is the trimmed proposal plus the suffix: ``abc .ipynb`` is proposed as
    ``abc `` and saved as ``abc.ipynb`` (the server trims before it looks for the suffix).
    """
    assert normalise_name(row["client"]) == row["client"].strip() + ".ipynb"

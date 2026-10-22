"""``.github/workflows/README.md`` describes the workflows that exist (2026-10-22).

What this pins:
- The README's table names exactly the workflow files in ``.github/workflows/``: a
  deleted workflow cannot keep its row and a new one cannot go undocumented.
- The ``python-security.yml`` row says what the workflow does with its Bandit results.
  The workflow prints the JSON to the job summary and uploads no SARIF, so the row must
  say the results do not reach the Security tab (a 2026-10-22 edit claimed they did);
  it must name ``--exit-zero`` exactly when the workflow runs Bandit with it.

Where the expected values come from: the workflow YAML files on disk, never the README.

Reproduce: ``.venv/bin/python -m pytest tests/test_workflows_readme.py -q``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"
README = WORKFLOWS / "README.md"


def _rows() -> dict[str, str]:
    """Map each workflow file named in the README's table to its row text."""
    rows: dict[str, str] = {}
    for line in README.read_text().splitlines():
        match = re.match(r"\| `([^`]+\.ya?ml)` \|", line)
        if match:
            rows[match.group(1)] = line
    return rows


def test_the_table_names_exactly_the_workflow_files():
    on_disk = {p.name for p in WORKFLOWS.iterdir() if p.suffix in {".yml", ".yaml"}}
    assert on_disk, "no workflow files found"
    assert set(_rows()) == on_disk


def test_the_security_row_says_where_the_bandit_results_go():
    workflow = (WORKFLOWS / "python-security.yml").read_text()
    row = _rows()["python-security.yml"]
    uploads_sarif = "upload-sarif" in workflow
    says_not_uploaded = re.search(r"\bnot\b[^.|]*Security tab", row) is not None
    assert "Security tab" in row
    assert says_not_uploaded is (not uploads_sarif), row
    assert ("job summary" in row) is ("GITHUB_STEP_SUMMARY" in workflow), row
    assert ("--exit-zero" in row) is ("--exit-zero" in workflow), row

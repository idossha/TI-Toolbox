#!/usr/bin/env python3
"""Render the packaged example notebook into its wiki page.

Usage::

    python3 dev/render_example_notebook.py          # rewrite docs/wiki/example-notebook.md
    python3 dev/render_example_notebook.py --check  # exit 1 if the page has drifted

``tit/server/examples/example_workflow.ipynb`` is the one source: the app seeds it into
every project, ``examples/notebooks/`` symlinks to it and the docs deploy copies it as the
download. The wiki page mirrors it cell for cell, so it is **generated** from the notebook
below the marker line and never hand-edited there. Markdown cells are pasted verbatim;
code cells become ``python`` fences. ``tests/test_example_notebook_api.py`` runs the
``--check`` so the page cannot drift silently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NOTEBOOK = REPO / "tit" / "server" / "examples" / "example_workflow.ipynb"
PAGE = REPO / "docs" / "wiki" / "example-notebook.md"
MARKER = "<!-- generated from tit/server/examples/example_workflow.ipynb by dev/render_example_notebook.py; do not edit below -->"


def render() -> str:
    """The page body below the marker, rendered from the notebook."""
    document = json.loads(NOTEBOOK.read_text())
    parts: list[str] = []
    for cell in document["cells"]:
        source = "".join(cell["source"]).rstrip("\n")
        if cell["cell_type"] == "markdown":
            parts.append(source)
        elif cell["cell_type"] == "code":
            parts.append(f"```python\n{source}\n```")
    return "\n\n".join(parts) + "\n"


def split(page: str) -> tuple[str, str]:
    """The hand-written head (through the marker line) and the generated body."""
    if MARKER not in page:
        raise SystemExit(f"{PAGE}: marker line missing:\n{MARKER}")
    head, _, body = page.partition(MARKER + "\n")
    return head + MARKER + "\n\n", body.lstrip("\n")


def main(argv: list[str]) -> int:
    check = "--check" in argv
    head, current = split(PAGE.read_text())
    wanted = render()
    if current == wanted:
        print(f"{PAGE.relative_to(REPO)}: up to date")
        return 0
    if check:
        print(
            f"{PAGE.relative_to(REPO)} has drifted from {NOTEBOOK.relative_to(REPO)}; "
            "run python3 dev/render_example_notebook.py",
            file=sys.stderr,
        )
        return 1
    PAGE.write_text(head + wanted)
    print(f"{PAGE.relative_to(REPO)}: rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

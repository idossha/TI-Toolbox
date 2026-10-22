#!/usr/bin/env python3
"""Fail the docs build when the built site's search index is missing or wrong.

The live search returned "No results" for every query for weeks: the index was made
by a Jekyll plugin that GitHub Pages' safe-mode build never runs, and nothing looked
at the built site. This check does, after ``build_search_index.py`` has run:

- ``search/search.json`` exists and is a JSON array;
- it has one entry per source page with a ``permalink`` and without ``search: false``,
  counted from the Markdown front matter, not from the built HTML;
- every title is non-empty, every URL is a page the site publishes, and no URL is
  the search page itself.

Run against a built site::

    python docs/tests/check_search_index.py _site [--source docs]

Exit status: 0 index is right, 1 index is missing or wrong, 2 no site to check.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

DOCS_DIR = Path(__file__).resolve().parents[1]
_NOT_SOURCES = {"api", "api_mkdocs", "vendor", "tests", "node_modules"}


def expected_pages(source: Path) -> list[str]:
    """Return the permalinks of the Markdown pages search should list."""
    urls = []
    for path in sorted(source.rglob("*.md")):
        rel = path.relative_to(source).parts
        if rel[0] in _NOT_SOURCES or any(p.startswith(("_", ".")) for p in rel):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        match = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---", text, re.S)
        if not match:
            continue
        front = match.group(1)
        permalink = re.search(r"^permalink:\s*[\"']?([^\"'\s]+)", front, re.M)
        if permalink and not re.search(r"^search:\s*false\s*$", front, re.M):
            urls.append(permalink.group(1))
    return urls


def _built(site: Path, url: str) -> Path:
    path = site / url.lstrip("/")
    return path / "index.html" if url.endswith("/") else path


def index_problems(site: Path, expected: list[str]) -> list[str]:
    """Return what is wrong with ``<site>/search/search.json``."""
    index = site / "search" / "search.json"
    if not index.is_file():
        return [f"{index} does not exist"]
    try:
        entries = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"{index} is not JSON: {error}"]
    if not isinstance(entries, list):
        return [f"{index} is not a JSON array"]
    problems = []
    if len(entries) != len(expected):
        indexed = {e.get("url") for e in entries if isinstance(e, dict)}
        missing = sorted(set(expected) - indexed)
        extra = sorted(indexed - set(expected))
        problems.append(
            f"{len(entries)} entries for {len(expected)} searchable pages "
            f"(not indexed: {missing}; not a searchable page: {extra})"
        )
    for number, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append(f"entry {number} is not an object")
            continue
        url = entry.get("url")
        if not isinstance(url, str) or not url.startswith("/"):
            problems.append(f"entry {number} has no site URL: {url!r}")
            continue
        if not str(entry.get("title") or "").strip():
            problems.append(f"{url}: empty title")
        if not isinstance(entry.get("content"), str):
            problems.append(f"{url}: no content text")
        if url.rstrip("/").endswith("/search") or url == "/search/":
            problems.append(f"{url}: the search page indexes itself")
        elif not _built(site, url).is_file():
            problems.append(f"{url}: no page is published there")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Check one built site's search index."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("site", type=Path, help="built site directory (_site)")
    parser.add_argument("--source", type=Path, default=DOCS_DIR, help="docs source")
    args = parser.parse_args(argv)
    if not (args.site / "index.html").is_file():
        print(f"error: no built site at {args.site}", file=sys.stderr)
        return 2
    expected = expected_pages(args.source)
    if not expected:
        print(
            f"error: no source pages with a permalink in {args.source}", file=sys.stderr
        )
        return 2
    problems = index_problems(args.site, expected)
    if problems:
        print(f"search index: {len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"Search index lists all {len(expected)} searchable pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

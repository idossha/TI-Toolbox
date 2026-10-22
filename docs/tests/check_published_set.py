#!/usr/bin/env python3
"""Fail the docs build when the built site publishes a file outside the public sections.

Developer notes once went live: ``_config.yml`` excluded ``dev/*.md`` files one by
one, ``dev/notes/`` was not on the list, and GitHub Pages' optional-front-matter
plugin rendered the notes (with local checkout paths in them) as public pages. This
guard reads the build output, so it holds whatever the include/exclude rules,
plugins or a new directory do: every file in the site must sit under one of the
public sections, or be one of the generated root files.

Run against a built site::

    python docs/tests/check_published_set.py _site

Exit status: 0 only public files, 1 something else is published, 2 no site to check.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

# The site's public sections (docs/_data/nav.yml plus search, notes and assets) and
# the API reference that CI builds into api/.
ALLOWED_PREFIXES = (
    "wiki/",
    "installation/",
    "releases/",
    "about/",
    "search/",
    "api/",
    "notes/",
    "assets/",
)
# Root files: the home page and what jekyll-feed and jekyll-sitemap generate.
ALLOWED_FILES = ("index.html", "feed.xml", "sitemap.xml", "robots.txt")


def unexpected_files(paths: Sequence[str]) -> list[str]:
    """Return the site-relative paths that are not in a public section."""
    return sorted(
        path
        for path in paths
        if path not in ALLOWED_FILES and not path.startswith(ALLOWED_PREFIXES)
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Check one built site directory."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python docs/tests/check_published_set.py SITE", file=sys.stderr)
        return 2
    site = Path(args[0])
    files = (
        [p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()]
        if site.is_dir()
        else []
    )
    if "index.html" not in files:
        print(f"error: no built site at {site}", file=sys.stderr)
        return 2
    leaked = unexpected_files(files)
    if leaked:
        print(
            f"{len(leaked)} file(s) published outside the public sections:",
            file=sys.stderr,
        )
        for path in leaked:
            print(f"  {path}", file=sys.stderr)
        return 1
    print(f"All {len(files)} published files are in public sections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

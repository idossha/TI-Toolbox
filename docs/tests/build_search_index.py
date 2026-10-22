#!/usr/bin/env python3
"""Write the docs search index, ``search/search.json``, from the built site.

The search page (``assets/js/search/results.js``) fetches this file. Jekyll cannot
generate it on GitHub Pages: ``actions/jekyll-build-pages`` builds in safe mode, which
never loads ``_plugins/``, so a generator plugin ran locally and silently not in CI.
Reading the rendered HTML instead means titles and snippets are what readers see:
no raw Liquid (``{{ site.baseurl }}``), no Markdown syntax, no math source.

One entry per page rendered through the site layout, except the home page, the search
page and any page whose front matter says ``search: false``:

- ``title``: the first non-empty ``<h1>`` of the page body (release notes carry an
  empty front-matter title and their heading in the body), else the ``<title>``;
- ``content``: the page body's text, without scripts, styles and math;
- ``url``: the site-relative URL (``/wiki/simulator/``); the search page prefixes the
  base URL, so one index serves the local preview and the published site.

Usage::

    python docs/tests/build_search_index.py _site [--source docs]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Sequence

DOCS_DIR = Path(__file__).resolve().parents[1]
INDEX_PATH = Path("search") / "search.json"
SKIP_DIRS = ("api/", "assets/", "search/")
_SKIPPED_TAGS = {"script", "style", "noscript", "template", "svg"}
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}
# Tags that start a new line of text; inline tags (a, code, em) join their neighbours.
_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "details",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "summary",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
_MATH = re.compile(r"\\\(.*?\\\)|\\\[.*?\\\]|\$\$.*?\$\$", re.S)


class _PageText(HTMLParser):
    """Collect the body text and first non-empty ``<h1>`` of one built page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.site_layout = False
        self.head_title: list[str] = []
        self._stack: list[tuple[str, str]] = []  # (tag, body region it opens or "")
        self._regions: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._h1: list[str] | None = None
        self.h1 = ""
        self.article: list[str] = []
        self.main: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html" and "data-baseurl" in values:
            self.site_layout = True
        if tag in _BLOCK_TAGS:
            self._emit(" ")
        if tag in _VOID_TAGS:
            return
        classes = (values.get("class") or "").split()
        opens = (
            "article" if "docs__article" in classes else "main" if tag == "main" else ""
        )
        if opens:
            self._regions.append(opens)
        self._stack.append((tag, opens))
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "h1" and not self.h1 and self._regions:
            self._h1 = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._emit(" ")
        if tag in _VOID_TAGS:
            return
        while self._stack:
            open_tag, opens = self._stack.pop()
            if opens:
                self._regions.pop()
            if open_tag in _SKIPPED_TAGS:
                self._skip_depth -= 1
            if open_tag == "title":
                self._in_title = False
            if open_tag == "h1" and self._h1 is not None:
                self.h1 = " ".join("".join(self._h1).split())
                self._h1 = None
            if open_tag == tag:
                break

    def _emit(self, text: str) -> None:
        if self._skip_depth or not self._regions:
            return
        if self._h1 is not None:
            self._h1.append(text)
        (self.article if "article" in self._regions else self.main).append(text)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.head_title.append(data)
        self._emit(data)


def page_entry(page_html: str, url: str) -> dict[str, str] | None:
    """Return the index entry for one built page, or ``None`` if it is not a site page."""
    parser = _PageText()
    parser.feed(page_html)
    parser.close()
    if not parser.site_layout:
        return None
    text = "".join(parser.article if "".join(parser.article).strip() else parser.main)
    text = " ".join(_MATH.sub(" ", text).split())
    title = parser.h1
    if not title:
        head = " ".join("".join(parser.head_title).split())
        title = re.split(r"\s+\|\s+", head)[0] if head else ""
    return {"title": title or url, "content": text, "url": url}


def unsearchable_urls(source: Path) -> set[str]:
    """Return the permalinks whose front matter says ``search: false``."""
    urls: set[str] = set()
    for path in source.rglob("*"):
        rel = path.relative_to(source).parts
        if path.suffix not in (".md", ".html") or any(
            p.startswith(("_", ".")) for p in rel
        ):
            continue
        if rel[0] in ("api", "api_mkdocs", "vendor", "tests"):
            continue
        head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
        match = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---", head, re.S)
        if not match or not re.search(r"^search:\s*false\s*$", match.group(1), re.M):
            continue
        permalink = re.search(r"^permalink:\s*[\"']?([^\"'\s]+)", match.group(1), re.M)
        if permalink:
            urls.add(permalink.group(1))
    return urls


def page_url(rel: str) -> str:
    """Map a built file (``wiki/a/index.html``) to its URL (``/wiki/a/``)."""
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def build_index(site: Path, source: Path) -> list[dict[str, str]]:
    """Return the search entries for every searchable page of *site*."""
    skip = unsearchable_urls(source) | {"/"}
    entries = []
    for page in sorted(site.rglob("*.html")):
        rel = page.relative_to(site).as_posix()
        url = page_url(rel)
        if rel.startswith(SKIP_DIRS) or url in skip:
            continue
        entry = page_entry(page.read_text(encoding="utf-8", errors="ignore"), url)
        if entry is not None:
            entries.append(entry)
    return entries


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``<site>/search/search.json``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("site", type=Path, help="built site directory (_site)")
    parser.add_argument("--source", type=Path, default=DOCS_DIR, help="docs source")
    args = parser.parse_args(argv)
    if not (args.site / "index.html").is_file():
        print(f"error: no built site at {args.site}", file=sys.stderr)
        return 2
    entries = build_index(args.site, args.source)
    if not entries:
        print(f"error: no searchable pages in {args.site}", file=sys.stderr)
        return 1
    out = args.site / INDEX_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(entries)} search entries to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

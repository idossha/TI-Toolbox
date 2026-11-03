#!/usr/bin/env python3
"""Fail the docs build when switching pages could flash, re-flow or jump again.

Clicking a page in the wiki sidebar made the screen blink: the sidebar's own scroll
went back to the top on every page (the clicked entry jumped by however far the reader
had scrolled it), ``<html>`` had no background of its own, the flowchart thumbnails on
Pre-processing painted as black squares until they decoded, and the ``js`` class that
collapses sidebar groups was set from ``<body>``. This guard reads the sources, so the
pre-paint pieces cannot be dropped or moved behind the stylesheet unnoticed:

* ``_includes/head.html``: ``<meta name="color-scheme">``, an inline ``<style>`` giving
  ``html`` a background, and the inline script adding the ``js`` class, all before the
  first stylesheet; ``_layouts/default.html`` includes that head before ``<body>``.
* ``_includes/docs.html``: the inline script restoring the sidebar scroll
  (``sessionStorage``) sits right after the sidebar, before the article is parsed.
* ``assets/css/style.scss``: ``@view-transition { navigation: auto; }``, a background on
  ``html``, and no ``opacity`` / ``visibility`` / ``animation`` / ``transition`` on the
  page-level elements (a load-time fade or a colour animating in from defaults).

Run against the docs source::

    python docs/tests/check_no_flash.py docs

Exit status: 0 clean, 1 a rule is broken, 2 a file to check is missing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Sequence

FILES = {
    "head": "_includes/head.html",
    "layout": "_layouts/default.html",
    "docs": "_includes/docs.html",
    "css": "assets/css/style.scss",
}
# Elements that cover the page: fading or animating any of them blinks the whole screen.
PAGE_LEVEL = {
    "html", "body", "main", ".site-main", ".docs", ".docs__article",
    ".docs__sidebar", ".wiki-content", ".wiki-content-inner",
}
FADE = re.compile(r"(?:^|[;{\s])(opacity|visibility|animation[\w-]*|transition[\w-]*)\s*:")


def _first_stylesheet(html: str) -> int:
    match = re.search(r"<link\b[^>]*\brel=[\"']stylesheet[\"']", html)
    return match.start() if match else -1


def head_problems(head: str) -> list[str]:
    """The pre-paint pieces must come before the first stylesheet in ``<head>``."""
    css_at = _first_stylesheet(head)
    if css_at < 0:
        return ["head.html: no <link rel=\"stylesheet\"> found"]
    before = head[:css_at]
    problems = []
    if not re.search(r"<meta\s+name=[\"']color-scheme[\"']", before):
        problems.append("head.html: <meta name=\"color-scheme\"> missing before the stylesheet")
    styles = re.findall(r"<style>(.*?)</style>", before, re.S)
    if not any(re.search(r"\bhtml\b[^{]*\{[^}]*background", s) for s in styles):
        problems.append("head.html: inline <style> giving html a background missing before the stylesheet")
    scripts = re.findall(r"<script>(.*?)</script>", before, re.S)
    if not any(re.search(r"documentElement\.classList\.add\(\s*[\"']js[\"']", s) for s in scripts):
        problems.append("head.html: inline script adding the \"js\" class missing before the stylesheet")
    return problems


def layout_problems(layout: str) -> list[str]:
    """The default layout must render that head before ``<body>``."""
    head_at = layout.find("include head.html")
    body_at = layout.find("<body")
    if head_at < 0 or body_at < 0 or head_at > body_at:
        return ["default.html: does not include head.html before <body>"]
    return []


def sidebar_problems(docs: str) -> list[str]:
    """The sidebar scroll is restored by an inline script between the sidebar and the article."""
    side_end = docs.find("</aside>")
    article_at = docs.find('class="docs__article')
    between = docs[side_end:article_at] if 0 <= side_end < article_at else ""
    if not re.search(r"<script>[^<]*sessionStorage", between):
        return ["docs.html: inline script restoring the sidebar scroll missing right after the sidebar"]
    return []


def _strip_comments(scss: str) -> str:
    scss = re.sub(r"/\*.*?\*/", "", scss, flags=re.S)
    return re.sub(r"(?m)(^|\s)//.*$", r"\1", scss)


def css_problems(scss: str) -> list[str]:
    """View transitions on, ``html`` painted, no fade or animation on page-level elements."""
    scss = _strip_comments(scss)
    problems = []
    if not re.search(r"@view-transition\s*\{[^}]*navigation\s*:\s*auto", scss):
        problems.append("style.scss: @view-transition { navigation: auto; } missing")
    # shortcut: only brace-free blocks are read, so a fade nested inside an SCSS block is
    # missed; upgrade to a real SCSS parser if one is ever hidden that way.
    html_painted = False
    for selector, body in re.findall(r"([^{};]+)\{([^{}]*)\}", scss):
        names = {s.split()[-1].split(":")[0] for s in selector.split(",") if s.split()}
        if "html" in names and re.search(r"(^|[;\s])background(-color)?\s*:", body):
            html_painted = True
        page = sorted(names & PAGE_LEVEL)
        if page and not selector.lstrip().startswith("@"):
            for prop in FADE.findall(body):
                problems.append(f"style.scss: {prop} on {', '.join(page)} (a load-time fade or animation)")
    if not html_painted:
        problems.append("style.scss: html has no background")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Check one docs source directory."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python docs/tests/check_no_flash.py DOCS_DIR", file=sys.stderr)
        return 2
    root = Path(args[0])
    missing = [rel for rel in FILES.values() if not (root / rel).is_file()]
    if missing:
        print(f"error: cannot check, missing under {root}: {', '.join(missing)}", file=sys.stderr)
        return 2
    text = {key: (root / rel).read_text(encoding="utf-8") for key, rel in FILES.items()}
    problems = (
        head_problems(text["head"])
        + layout_problems(text["layout"])
        + sidebar_problems(text["docs"])
        + css_problems(text["css"])
    )
    if problems:
        print(f"{len(problems)} page-switch flash problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("Pre-paint head, sidebar scroll restore and view transitions are in place.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

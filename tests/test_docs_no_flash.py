"""Switching wiki pages does not flash: the guard on the pre-paint pieces is self-tested.

What this pins
    ``docs/tests/check_no_flash.py`` (run in the Deploy Docs workflow) fails when the
    default layout's head loses the color-scheme meta, the inline html background or
    the inline ``js``-class script, or moves them behind the stylesheet; when the
    sidebar scroll restore leaves its place between the sidebar and the article; when
    the CSS loses ``@view-transition { navigation: auto; }`` or the html background; or
    when a page-level element gains an opacity/visibility/animation/transition.

Where the expectations come from
    The fixtures are minimal hand-written documents shaped like the repository's files
    (2026-11-03); each red case breaks exactly one rule. The bug they guard against
    was measured headless on the local site (Playwright 1.62, Chromium, 150 ms added
    latency): before the fix the sidebar's scrollTop went 120 -> 0 on every sidebar
    click and the Pre-processing thumbnails painted black for ~5 frames.

Deliberately elsewhere
    The browser-level behaviour itself is not re-run in CI (no Jekyll server there).
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, DOCS / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load("check_no_flash")

HEAD = """<head>
  <meta name="color-scheme" content="light">
  <style>html,body{background:#fff}</style>
  <script>document.documentElement.classList.add("js")</script>
  <link rel="stylesheet" href="/assets/css/style.css">
</head>"""
LAYOUT = "<html>\n  {%- include head.html -%}\n  <body>\n  </body>\n</html>"
DOCS_HTML = """<aside class="docs__sidebar" id="docs-sidebar"></aside>
  <script>(function(s){ try { sessionStorage.getItem('k'); } catch (e) {} })()</script>
  <article class="docs__article wiki-content"></article>"""
CSS = """// comment with body { opacity: 0 } inside
@view-transition { navigation: auto; }
html { background: var(--color-bg); }
body { color: red; }
.sidebar-nav__ext { opacity: 0.7; }
.card { transition: background 0.15s; }
"""


def test_the_accepted_shape_passes():
    assert guard.head_problems(HEAD) == []
    assert guard.layout_problems(LAYOUT) == []
    assert guard.sidebar_problems(DOCS_HTML) == []
    assert guard.css_problems(CSS) == []


def test_js_class_script_after_the_stylesheet_fails():
    head = HEAD.replace(
        '  <script>document.documentElement.classList.add("js")</script>\n', ""
    ).replace("</head>", '<script>document.documentElement.classList.add("js")</script></head>')
    assert guard.head_problems(head) == [
        'head.html: inline script adding the "js" class missing before the stylesheet'
    ]


def test_missing_html_background_or_color_scheme_in_head_fails():
    assert len(guard.head_problems(HEAD.replace("html,body{background:#fff}", "p{}"))) == 1
    assert len(guard.head_problems(HEAD.replace('name="color-scheme"', 'name="x"'))) == 1
    assert guard.head_problems("<head></head>") == ['head.html: no <link rel="stylesheet"> found']


def test_layout_without_head_before_body_fails():
    assert guard.layout_problems("<body></body>{% include head.html %}") != []


def test_sidebar_scroll_restore_moved_or_dropped_fails():
    assert guard.sidebar_problems(DOCS_HTML.replace("sessionStorage", "localThing")) != []
    moved = DOCS_HTML.replace(
        "<aside", "<script>sessionStorage</script><aside", 1
    ).replace("sessionStorage.getItem('k')", "0")
    assert guard.sidebar_problems(moved) != []


def test_css_without_view_transition_or_html_background_fails():
    assert guard.css_problems(CSS.replace("navigation: auto", "navigation: none")) == [
        "style.scss: @view-transition { navigation: auto; } missing"
    ]
    assert guard.css_problems(CSS.replace("html { background", "html { color")) == [
        "style.scss: html has no background"
    ]


def test_load_time_fade_on_a_page_level_element_fails():
    for rule in (
        "body { opacity: 0; }",
        "main.site-main, .docs__article { animation: fade-in .3s; }",
        "html.js body:not(.ready) { visibility: hidden; }",
        "body { transition: background-color .2s; }",
    ):
        assert guard.css_problems(CSS + rule) != [], rule


def test_main_exit_codes(tmp_path, capsys):
    assert guard.main([str(DOCS)]) == 0
    assert guard.main([]) == 2
    assert guard.main([str(tmp_path)]) == 2
    copy = tmp_path / "docs"
    for rel in guard.FILES.values():
        (copy / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(DOCS / rel, copy / rel)
    assert guard.main([str(copy)]) == 0
    css = copy / guard.FILES["css"]
    css.write_text(css.read_text() + "\nbody { opacity: 0; }\n")
    assert guard.main([str(copy)]) == 1
    assert "opacity on body" in capsys.readouterr().err

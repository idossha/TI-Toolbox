"""The docs search index is built from the rendered site and checked on the built site.

What this pins
    ``assets/js/search/results.js`` fetches ``search/search.json``. A Jekyll plugin made
    it, and GitHub Pages' safe-mode build never runs plugins, so the live search said
    "No results" for every query. Even where the plugin ran it indexed unrendered page
    source: 25 release notes with ``title: ""`` gave blank result links, and snippets
    carried ``{{ site.baseurl }}`` and Markdown. ``docs/tests/build_search_index.py``
    now writes the index from the built HTML; ``docs/tests/check_search_index.py``
    checks it against the source pages.

Where the expected values come from
    The fixture site below is hand-written HTML shaped like this site's layouts
    (``_includes/docs.html``: sidebar, ``article.docs__article`` with an empty
    ``h1.docs__title`` for release notes, on-this-page aside; ``_layouts/about.html``:
    ``main`` with no article). Every expected title, URL and text is written by hand
    from that HTML. On 2026-10-22 a real ``bundle exec jekyll build`` of this tree gave
    73 entries, the same count the old Ruby plugin produced on the same tree.

Reproduce on a real build::

    cd docs && bundle exec jekyll build && python3 tests/build_search_index.py _site \\
        && python3 tests/check_search_index.py _site

Deliberately elsewhere
    How the results page renders entries: ``docs/tests/search-results.test.mjs``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, DOCS / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load("build_search_index")
checker = _load("check_search_index")


def _layout(body: str, title: str = "Page | Temporal Interference Toolbox") -> str:
    return (
        '<!DOCTYPE html><html lang="en" data-baseurl="/TI-Toolbox"><head>'
        f"<title>{title}</title><style>.x {{ color: red }}</style>"
        '<script>var q = "{{ site.baseurl }}"; var m = "$$x$$";</script></head>'
        '<body><header><a href="/TI-Toolbox/">Site header</a></header>'
        f'<main class="site-main">{body}</main><footer>Footer text</footer></body></html>'
    )


def _docs(article: str, heading: str) -> str:
    return _layout(
        '<div class="docs"><aside class="docs__sidebar"><a href="/x/">Sidebar link</a>'
        '</aside><article class="docs__article wiki-content"><div class="wiki-content-inner">'
        f'<h1 class="docs__title">{heading}</h1>{article}</div></article>'
        '<aside class="docs__toc"><p class="docs__toc-title">On this page</p></aside></div>'
    )


GUIDE = _docs(
    '<p>Use the <a href="/TI-Toolbox/wiki/b/">simulator</a>.</p>'
    '<h2 id="field">Field</h2><p>The envelope \\(E_{AM}\\) peaks.</p>'
    "<p>\\[ |E| = 2 \\min(a, b) \\]</p>"
    '<script>console.log("inline {% raw %}")</script>'
    "<ul><li>first</li><li>second</li></ul>",
    "Alpha guide",
)
RELEASE = _docs(
    '<h1 id="release-v100">Release v1.0.0</h1><p><strong>Release Date</strong>: May 1</p>',
    "",
)
ABOUT = _layout(
    '<div class="page"><div class="page__inner"><h1 class="page__title">About</h1>'
    "<p>Open-source TI research.</p></div></div>",
    title="About | Temporal Interference Toolbox",
)
STANDALONE = '<!doctype html><html lang="en"><head><title>Notes</title></head><body><h1>Notes</h1></body></html>'


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "_site"
    pages = {
        "index.html": _layout("<section>Home hero</section>"),
        "wiki/a/index.html": GUIDE,
        "releases/v1.0.0/index.html": RELEASE,
        "about/index.html": ABOUT,
        "search/index.html": _docs("<div>Search page</div>", "Search Results"),
        "wiki/hidden/index.html": _docs("<p>Hidden</p>", "Hidden"),
        "notes/standalone.html": STANDALONE,
        "api/index.html": _layout("<p>API</p>"),
        "assets/other/report.html": _layout("<p>Report</p>"),
    }
    for rel, text in pages.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    fronts = {
        "index.md": "layout: home",
        "wiki/a.md": "title: Alpha guide\npermalink: /wiki/a/",
        "wiki/search.md": "title: Search Results\npermalink: /search/\nsearch: false",
        "wiki/hidden.md": "title: Hidden\npermalink: /wiki/hidden/\nsearch: false",
        "wiki/about.md": "layout: about\ntitle: About\npermalink: /about/",
        "releases/v1.0.0.md": 'title: ""\nnav_title: "Release v1.0.0"\npermalink: /releases/v1.0.0/',
        "_layouts/x.md": "permalink: /layout-only/",
        "api/page.md": "permalink: /api/page/",
    }
    for rel, front in fronts.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(f"---\n{front}\n---\n\n# Heading\n", encoding="utf-8")
    (root / "wiki" / "no-front-matter.md").write_text("# Loose\n", encoding="utf-8")
    return root


def _index(site: Path, source: Path) -> dict[str, dict[str, str]]:
    assert builder.main([str(site), "--source", str(source)]) == 0
    entries = json.loads((site / "search" / "search.json").read_text(encoding="utf-8"))
    by_url = {entry["url"]: entry for entry in entries}
    assert len(by_url) == len(entries), "an URL is indexed twice"
    return by_url


# ── the index builder ───────────────────────────────────────────────────────


def test_one_entry_per_searchable_page(site, source):
    assert sorted(_index(site, source)) == ["/about/", "/releases/v1.0.0/", "/wiki/a/"]


def test_titles_come_from_the_first_non_empty_h1(site, source):
    index = _index(site, source)
    assert index["/wiki/a/"]["title"] == "Alpha guide"
    # Front-matter title is "" and h1.docs__title is empty: the body's h1 names it.
    assert index["/releases/v1.0.0/"]["title"] == "Release v1.0.0"
    assert index["/about/"]["title"] == "About"


def test_article_text_is_the_rendered_body_only(site, source):
    content = _index(site, source)["/wiki/a/"]["content"]
    assert (
        content
        == "Alpha guide Use the simulator. Field The envelope peaks. first second"
    )


def test_page_without_an_article_uses_main(site, source):
    assert (
        _index(site, source)["/about/"]["content"] == "About Open-source TI research."
    )


def test_no_liquid_markdown_math_or_chrome_reaches_the_index(site, source):
    for entry in _index(site, source).values():
        text = entry["content"]
        for fragment in ("{{", "{%", "](", "\\(", "\\[", "$$", "color: red"):
            assert fragment not in text, (entry["url"], fragment)
        for chrome in ("Sidebar link", "On this page", "Site header", "Footer text"):
            assert chrome not in text, (entry["url"], chrome)


def test_rebuilding_does_not_index_the_index(site, source):
    first = _index(site, source)
    assert _index(site, source) == first


def test_missing_site_is_reported_not_indexed(tmp_path, capsys):
    assert builder.main([str(tmp_path / "nope")]) == 2


def test_site_with_no_searchable_page_fails(tmp_path, source, capsys):
    site = tmp_path / "bare"
    site.mkdir()
    (site / "index.html").write_text(_layout("<p>Home</p>"), encoding="utf-8")
    assert builder.main([str(site), "--source", str(source)]) == 1


# ── the built-site check ────────────────────────────────────────────────────


def test_expected_pages_count_front_matter_independently(source):
    # wiki/a, wiki/about, releases/v1.0.0: search:false, underscore, api/ and
    # front-matter-less files do not count.
    assert sorted(checker.expected_pages(source)) == [
        "/about/",
        "/releases/v1.0.0/",
        "/wiki/a/",
    ]


def test_check_passes_on_a_built_index(site, source, capsys):
    _index(site, source)
    assert checker.main([str(site), "--source", str(source)]) == 0


def test_check_exits_2_without_a_site(tmp_path, source, capsys):
    assert checker.main([str(tmp_path / "missing"), "--source", str(source)]) == 2


def test_check_fails_when_no_index_was_written(site, source, capsys):
    assert checker.main([str(site), "--source", str(source)]) == 1
    assert "does not exist" in capsys.readouterr().err


def _plant(site: Path, entries) -> None:
    (site / "search").mkdir(exist_ok=True)
    (site / "search" / "search.json").write_text(json.dumps(entries), encoding="utf-8")


def test_check_fails_on_a_planted_empty_index(site, source, capsys):
    _plant(site, [])
    assert checker.main([str(site), "--source", str(source)]) == 1
    assert "0 entries for 3 searchable pages" in capsys.readouterr().err


def test_check_fails_on_blank_titles_and_bad_urls(site, source, capsys):
    good = list(_index(site, source).values())
    cases = {
        "empty title": [dict(good[0], title="")] + good[1:],
        "no page is published": [dict(good[0], url="/wiki/gone/")] + good[1:],
        "indexes itself": [dict(good[0], url="/search/")] + good[1:],
        "4 entries for 3": good + [dict(good[0])],
        "not JSON": "{oops",
        "not a JSON array": {"url": "/wiki/a/"},
    }
    for message, entries in cases.items():
        if isinstance(entries, str):
            (site / "search" / "search.json").write_text(entries, encoding="utf-8")
        else:
            _plant(site, entries)
        assert checker.main([str(site), "--source", str(source)]) == 1, message
        assert message in capsys.readouterr().err, message


def test_this_repository_has_pages_to_index():
    urls = checker.expected_pages(DOCS)
    assert len(urls) > 60
    assert "/releases/changelog/" in urls and "/wiki/simulator/" in urls
    assert "/search/" not in urls
    assert not any(url.startswith("/dev/") for url in urls)


def test_search_plugin_is_gone_and_serve_builds_the_index():
    assert not (DOCS / "_plugins" / "search_generator.rb").exists()
    serve = (DOCS / "serve.sh").read_text(encoding="utf-8")
    build = serve.index("jekyll build")
    index = serve.index("tests/build_search_index.py")
    serve_at = serve.index("jekyll serve")
    assert build < index < serve_at
    assert "--skip-initial-build" in serve[serve_at:]

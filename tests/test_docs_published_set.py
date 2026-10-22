"""The docs site publishes only its public pages: no developer notes, the changelog kept.

What this pins
    ``docs/_config.yml`` says "Developer references stay private to the checkout; the
    changelog is included". It used to exclude ``dev/*.md`` files one by one, so
    ``dev/notes/`` went live (GitHub Pages' optional-front-matter plugin rendered the
    notes, local checkout paths included). This file reimplements Jekyll 3.9's
    include/exclude filter (``Jekyll::EntryFilter``, the version GitHub Pages runs),
    walks ``docs/`` with the rules from ``_config.yml`` and requires every published
    page to be one a reader can reach: a ``docs/_data/nav.yml`` entry, a release note,
    or one of the few pages linked from elsewhere (home, search, about, the TI field
    metrics note). The published-set check on the built site
    (``docs/tests/check_published_set.py``) is self-tested here too.

Where the expectations come from
    The filter's behaviour was observed on real Jekyll 3.9.5 builds of this repository
    (2026-10-22, ``bundle exec jekyll build``): with the per-file excludes the build
    copied ``dev/notes/*.md`` into the site; with ``exclude: [dev/]`` and
    ``include: [dev/CHANGELOG.md]`` the changelog page vanished (an include matches a
    bare entry name, never a path inside an excluded directory); with
    ``include: [CHANGELOG.md]`` the changelog stayed and ``dev/notes`` went. The live
    site (sitemap, 2026-10-22) served both ``dev/notes`` pages.

Deliberately elsewhere
    Links and anchors: ``tests/test_docs_check_links.py``. The search index:
    ``tests/test_docs_search_index.py``.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, DOCS / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


published_set = _load("check_published_set")


# ── Jekyll 3.9 EntryFilter, reimplemented ───────────────────────────────────


def _config_list(config_text: str, key: str) -> list[str]:
    """Read a top-level YAML list (``key:`` then ``  - item`` lines)."""
    match = re.search(
        rf"^{key}:\s*\n((?:[ \t]+(?:-.*|#.*)\n?|\s*\n)*)", config_text, re.M
    )
    if not match:
        return []
    items = []
    for line in match.group(1).splitlines():
        item = re.match(r"^\s+-\s*(.+?)\s*$", line)
        if item:
            items.append(item.group(1).strip("\"'"))
    return items


def _join(base: str, item: str) -> str:
    """Ruby ``File.join``: one separator between the parts, trailing slash kept."""
    return base.rstrip("/") + "/" + item.lstrip("/")


def _glob_include(source: str, patterns: list[str], entry: str) -> bool:
    """``EntryFilter#glob_include?``: fnmatch, or the path starts with the pattern."""
    entry_path = _join(source, entry)
    for pattern in patterns:
        item = _join(source, pattern)
        if fnmatch.fnmatchcase(entry_path, item) or entry_path.startswith(item):
            return True
    return False


def jekyll_published(source: Path, include: list[str], exclude: list[str]) -> list[str]:
    """Return the source files Jekyll 3.9 reads (site-relative, POSIX).

    ``included?`` sees the bare entry name; ``excluded?`` sees the path relative to
    the source with a leading slash. An included entry skips the special/backup/
    excluded checks; a rejected directory is never descended into.
    """
    src = source.as_posix()
    out: list[str] = []

    def walk(rel_dir: str) -> None:
        for path in sorted((source / rel_dir).iterdir()):
            name = path.name
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if not _glob_include(src, include, name):
                if name[0] in "._#~" or name.endswith("~"):
                    continue
                if _glob_include(src, exclude, "/" + rel):
                    continue
            if path.is_dir():
                walk(rel)
            else:
                out.append(rel)

    walk("")
    return out


def _front_matter(path: Path) -> dict[str, str] | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---", text, re.S)
    if not match:
        return None
    meta = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith((" ", "-")):
            meta[key.strip()] = value.strip().strip("\"'")
    return meta


# Pages linked from outside the sidebars: the home page, the header's search and
# about links, and the TI field metrics note linked from the wiki.
EXTRA_URLS = {"/", "/search/", "/about/", "/notes/ti-field-metrics.html"}
RELEASE_NOTE = re.compile(r"^releases/v\d+\.\d+\.\d+\.md$")
# Static HTML that is not a page: the MkDocs API reference and embedded report assets.
STATIC_HTML_PREFIXES = ("api/", "assets/")


def page_violations(docs: Path, published: list[str], nav_urls: set[str]) -> list[str]:
    """Return the published .md/.html files a reader is not meant to reach."""
    problems = []
    for rel in published:
        if not rel.endswith((".md", ".html")):
            continue
        if rel.startswith("dev/") and rel != "dev/CHANGELOG.md":
            problems.append(f"{rel}: developer file published")
            continue
        meta = _front_matter(docs / rel)
        if meta is None and rel.endswith(".html"):
            if rel.startswith(STATIC_HTML_PREFIXES) or "/" + rel in EXTRA_URLS:
                continue
            problems.append(f"{rel}: static HTML outside api/ and assets/")
            continue
        url = (meta or {}).get("permalink") or ("/" if rel == "index.md" else "")
        if url in nav_urls or url in EXTRA_URLS or RELEASE_NOTE.match(rel):
            continue
        problems.append(
            f"{rel}: published at {url or 'a default URL'}, linked from nowhere"
        )
    return problems


def _repo_rules() -> tuple[list[str], list[str]]:
    config = (DOCS / "_config.yml").read_text(encoding="utf-8")
    return _config_list(config, "include"), _config_list(config, "exclude")


def _nav_urls() -> set[str]:
    nav = (DOCS / "_data" / "nav.yml").read_text(encoding="utf-8")
    return set(re.findall(r"\burl:\s*([^\s,}]+)", nav))


# ── the filter reproduces what real Jekyll 3.9.5 builds did ─────────────────


def _tree(tmp_path: Path) -> Path:
    for rel in ("dev/CHANGELOG.md", "dev/TESTING.md", "dev/notes/plan.md", "wiki/a.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x\n")
    return tmp_path


def test_per_file_excludes_leave_dev_notes_published(tmp_path):
    files = jekyll_published(_tree(tmp_path), ["dev/CHANGELOG.md"], ["dev/TESTING.md"])
    assert "dev/notes/plan.md" in files
    assert "dev/TESTING.md" not in files


def test_excluding_dev_drops_a_path_shaped_include(tmp_path):
    # Observed: with these two rules Jekyll 3.9.5 built no /releases/changelog/ page.
    files = jekyll_published(_tree(tmp_path), ["dev/CHANGELOG.md"], ["dev/"])
    assert not [f for f in files if f.startswith("dev/")]
    assert "wiki/a.md" in files


def test_excluding_dev_keeps_a_basename_include(tmp_path):
    files = jekyll_published(_tree(tmp_path), ["CHANGELOG.md"], ["dev/"])
    assert [f for f in files if f.startswith("dev/")] == ["dev/CHANGELOG.md"]


def test_excluded_directory_prefix_does_not_swallow_a_sibling_name(tmp_path):
    (tmp_path / "devices.md").write_text("x\n")
    assert "devices.md" in jekyll_published(_tree(tmp_path), [], ["dev/"])


def test_config_list_reader_reads_the_include_list():
    sample = "include:\n  - a.md\n  # note\n  - _b\n\nexclude:\n  - c/\n"
    assert _config_list(sample, "include") == ["a.md", "_b"]
    assert _config_list(sample, "exclude") == ["c/"]


# ── this repository ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def published() -> list[str]:
    include, exclude = _repo_rules()
    files = jekyll_published(DOCS, include, exclude)
    assert len(files) > 100, "the walk found no site to check"
    return files


def test_no_developer_file_is_published(published):
    assert [f for f in published if f.startswith("dev/")] == ["dev/CHANGELOG.md"]


def test_the_changelog_page_is_still_published(published):
    assert "dev/CHANGELOG.md" in published
    assert _front_matter(DOCS / "dev" / "CHANGELOG.md")["permalink"] in _nav_urls()


def test_every_published_page_is_reachable(published):
    pages = [
        f
        for f in published
        if f.endswith((".md", ".html")) and not f.startswith("api/")
    ]
    assert len(pages) > 70, "too few pages: the walk or the rules are wrong"
    assert page_violations(DOCS, published, _nav_urls()) == []


def test_a_planted_unlisted_page_is_a_violation(tmp_path):
    docs = tmp_path
    (docs / "wiki").mkdir()
    (docs / "wiki" / "secret.md").write_text(
        "---\npermalink: /wiki/secret/\n---\n# S\n"
    )
    (docs / "wiki" / "ok.md").write_text("---\npermalink: /wiki/ok/\n---\n# O\n")
    (docs / "releases").mkdir()
    (docs / "releases" / "v9.9.9.md").write_text(
        "---\npermalink: /releases/v9.9.9/\n---\n"
    )
    files = jekyll_published(docs, [], [])
    problems = page_violations(docs, files, {"/wiki/ok/"})
    assert problems == [
        "wiki/secret.md: published at /wiki/secret/, linked from nowhere"
    ]


# ── the built-site check ────────────────────────────────────────────────────


def _site(tmp_path: Path, *extra: str) -> Path:
    site = tmp_path / "_site"
    for rel in (
        "index.html",
        "feed.xml",
        "wiki/a/index.html",
        "api/index.html",
        *extra,
    ):
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_text("<html></html>")
    return site


def test_built_site_with_public_sections_only_passes(tmp_path, capsys):
    assert published_set.main([str(_site(tmp_path))]) == 0


def test_built_site_with_a_planted_dev_note_fails(tmp_path, capsys):
    site = _site(tmp_path, "dev/notes/x.html", "dev/notes/y.md")
    assert published_set.main([str(site)]) == 1
    err = capsys.readouterr().err
    assert "dev/notes/x.html" in err and "dev/notes/y.md" in err


def test_root_file_outside_the_allowlist_fails(tmp_path, capsys):
    assert published_set.main([str(_site(tmp_path, "secrets.html"))]) == 1


def test_missing_or_empty_site_cannot_be_checked(tmp_path, capsys):
    assert published_set.main([str(tmp_path / "nope")]) == 2
    (tmp_path / "empty").mkdir()
    assert published_set.main([str(tmp_path / "empty")]) == 2
    assert published_set.main([]) == 2

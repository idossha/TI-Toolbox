#!/usr/bin/env python3
"""Fail the docs build when a link, anchor, script, stylesheet or frame does not resolve.

Jekyll builds a page whose links point nowhere without a warning. ``check_assets.py``
covers media tags; this guard covers the rest of the built site:

- every in-site ``<a href>`` target exists, and its ``#fragment`` is an ``id`` (or
  ``<a name>``) on the target page, as kramdown actually emitted it;
- every ``<script src>``, ``<link href>`` and ``<iframe src>`` target exists;
- with ``--repo``: every file named in ``docs/_data/atlases.json`` is published under
  ``assets/atlas``, every ``docs/wiki`` permalink is published (the agent plugin builds
  its links as ``SITE_BASE + permalink``), every absolute docs-site URL written in the
  app, the plugin, the README, the release notes, ``tit/``, ``resources/`` and
  ``container/`` resolves (case-sensitively: GitHub Pages paths are), and the heading ids
  :func:`heading_ids` computes from each page's Markdown equal the ids kramdown built,
  which keeps the pre-merge deep-link test (``tests/test_docs_deeplinks.py``) honest.

Run against a built site::

    python docs/tests/check_links.py _site --repo .

Exit status: 0 everything resolves, 1 something does not, 2 nothing could be checked
(no site, an empty site, or an unreadable repository).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import unquote, urlparse

DOCS_DIR = Path(__file__).resolve().parents[1]

# Pages these tools generate on their own; their links are not this site's Markdown.
SKIP_SOURCE_DIRS = ("api/", "assets/vendor/")

# Where absolute docs-site URLs are written outside the docs sources.
REPO_URL_SOURCES = (
    "desktop/src",
    "agent-plugin",
    "README.md",
    "docs/releases",
    "docs/dev/CHANGELOG.md",
    "tit",
    "resources",
    "container",
)
_SKIP_REPO_DIRS = {"node_modules", "__pycache__", ".venv", "dist", "out", ".git"}

_DOCS_URL = re.compile(r"https?://idossha\.github\.io/[A-Za-z0-9._~%/#?=&+:@-]*")
_REF = re.compile(
    r"<(a|link|script|iframe)\b[^>]*?\s(href|src)\s*=\s*[\"']([^\"']*)[\"']",
    re.IGNORECASE,
)
_ID_ATTR = re.compile(r"(?<![\w-])id\s*=\s*[\"']([^\"']+)[\"']")
_NAME_ATTR = re.compile(r"<a\b[^>]*?(?<![\w-])name\s*=\s*[\"']([^\"']+)[\"']", re.I)
_HEADING_ID = re.compile(
    r"<h[1-6]\b[^>]*?(?<![\w-])id\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE
)
_SCRIPT_BODY = re.compile(r"(<script\b[^>]*>).*?(</script>)", re.IGNORECASE | re.S)
_COMMENT = re.compile(r"<!--.*?-->", re.S)


# ── site configuration ──────────────────────────────────────────────────────


def site_address(config_text: str) -> tuple[str, str]:
    """Return ``(url, baseurl)`` from the text of ``docs/_config.yml``."""
    url = re.search(r"^url:\s*[\"']?([^\"'\s#]+)", config_text, re.M)
    base = re.search(r"^baseurl:\s*[\"']?([^\"'\s#]*)", config_text, re.M)
    if not url or base is None:
        raise ValueError("docs/_config.yml has no url/baseurl")
    return url.group(1).rstrip("/"), base.group(1).rstrip("/")


# ── kramdown's GFM heading ids ──────────────────────────────────────────────


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Return the flat ``key: value`` front matter and the body of a page."""
    match = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", text, re.S)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not line.startswith((" ", "\t", "-")):
            meta[key.strip()] = value.strip().strip("\"'")
    return meta, text[match.end() :]


def _plain_heading_text(raw: str) -> str:
    """Reduce a heading's Markdown to the text kramdown keeps in ``raw_text``.

    Code spans keep their content verbatim; outside them links keep their text,
    images and tags vanish, entities decode, and ``--``/``---`` become dashes
    (which the id rule then drops).
    """
    parts = re.split(r"(`+)(.+?)\1", raw)
    out: list[str] = []
    for index in range(0, len(parts), 3):
        text = parts[index]
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"---|--", "—", text)
        text = re.sub(r"(?<![\w\\])_(\S(?:.*?\S)?)_(?![\w])", r"\1", text)
        text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|<>])", r"\1", text)
        out.append(html.unescape(text))
        if index + 2 < len(parts):
            out.append(parts[index + 2].strip())
    return "".join(out)


def _gfm_slug(text: str) -> str:
    """Apply kramdown-parser-gfm's ``generate_gfm_header_id`` to plain text."""
    kept = [
        ch
        for ch in text.lower()
        if ch in "- \t"
        or unicodedata.category(ch)[0] in "LM"
        or unicodedata.category(ch) in ("Nd", "Pc")
    ]
    return "".join(kept).replace(" ", "-").replace("\t", "-")


def _strip_code_blocks(lines: list[str]) -> list[str]:
    """Blank out fenced code so a ``# comment`` inside it is not a heading."""
    out: list[str] = []
    fence: str | None = None
    for line in lines:
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence is None and marker:
            fence = marker.group(1)[0] * len(marker.group(1))
            out.append("")
        elif fence is not None:
            if re.match(r"^ {0,3}" + re.escape(fence) + r"[`~]*\s*$", line):
                fence = None
            out.append("")
        else:
            out.append(line)
    return out


def heading_ids(markdown: str) -> list[str]:
    """Return the heading ids kramdown (GFM input) gives a Markdown body, in order.

    The rule (``kramdown-parser-gfm`` ``generate_gfm_header_id``): an explicit
    ``{#id}`` wins; otherwise the heading's text is lowercased, every character
    other than a letter, mark, digit, connector, ``-`` or space is dropped, spaces
    become ``-``, and a repeated id gets ``-1``, ``-2`` ... in document order.
    """
    lines = _strip_code_blocks(markdown.splitlines())
    counts: dict[str, int] = {}
    ids: list[str] = []
    previous_blank = True
    for index, line in enumerate(lines):
        text: str | None = None
        atx = re.match(r"^#{1,6}[ \t]+(.*)$", line)
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if atx:
            text = atx.group(1).rstrip()
        elif (
            previous_blank
            and line.strip()
            and re.match(r"^ {0,3}[^ \t]", line)
            and re.match(r"^[-=][-=]*[ \t]*$", following)
            and not re.match(r"^ {0,3}(?:[-*+]|\d+\.)[ \t]|^ {0,3}[<|>{]", line)
        ):
            text = line.strip()
        previous_blank = not line.strip()
        if text is None:
            continue
        explicit = re.search(r"[\t ]\{#([A-Za-z_:][\w:.\-]*)\}$", text)
        if explicit:
            ids.append(explicit.group(1))
            continue
        text = re.sub(r"[\t ]#+$", "", text).rstrip()
        if not text:
            continue
        slug = _gfm_slug(_plain_heading_text(text))
        seen = counts.get(slug, -1) + 1
        counts[slug] = seen
        ids.append(f"{slug}-{seen}" if seen else slug)
    return ids


def anchor_ids(markdown: str) -> set[str]:
    """Return every fragment a page built from *markdown* can be linked to."""
    body = "\n".join(_strip_code_blocks(markdown.splitlines()))
    return (
        set(heading_ids(markdown))
        | set(_ID_ATTR.findall(body))
        | set(_NAME_ATTR.findall(body))
    )


# ── built-site checks ───────────────────────────────────────────────────────


def element_ids(page_html: str) -> set[str]:
    """Return the ``id`` and ``<a name>`` values a fragment can land on."""
    page_html = _COMMENT.sub("", page_html)
    return set(_ID_ATTR.findall(page_html)) | set(_NAME_ATTR.findall(page_html))


def references(page_html: str) -> list[tuple[str, str]]:
    """Return ``(tag, url)`` for each ``a``/``link``/``script``/``iframe`` reference.

    Inline script bodies and comments are dropped first, so a URL assembled in
    JavaScript text is not mistaken for markup.
    """
    page_html = _COMMENT.sub("", _SCRIPT_BODY.sub(r"\1\2", page_html))
    return [(tag.lower(), url) for tag, _attr, url in _REF.findall(page_html)]


def _is_external(url: str, own_prefix: str) -> bool:
    if url.startswith(own_prefix + "/") or url == own_prefix:
        return False
    return url.startswith("//") or bool(urlparse(url).scheme)


def resolve(
    site: Path, page_rel: str, url: str, baseurl: str, own_prefix: str
) -> tuple[Path, str] | None:
    """Return the built file *url* names from *page_rel* and its fragment.

    ``None`` means the URL leaves the site (another origin, ``mailto:``, ``data:``).
    """
    url = html.unescape(url.strip())
    if _is_external(url, own_prefix):
        return None
    if url.startswith(own_prefix):
        url = url[len(own_prefix) :] or "/"
        url = baseurl + url if baseurl else url
    parsed = urlparse(url)
    path, fragment = unquote(parsed.path), unquote(parsed.fragment)
    if not path:
        return site / page_rel, fragment
    if baseurl and (path == baseurl or path.startswith(baseurl + "/")):
        path = path[len(baseurl) :] or "/"
    if path.startswith("/"):
        target = site / path.lstrip("/")
    else:
        target = (site / page_rel).parent / path
    if path.endswith("/") or target.is_dir():
        target = target / "index.html"
    elif not target.exists() and target.with_suffix(".html").exists():
        target = target.with_suffix(".html")
    return target, fragment


def check_site(site: Path, baseurl: str, site_url: str) -> tuple[int, list[str]]:
    """Check every reference in every built page; return ``(pages, problems)``."""
    own_prefix = site_url + baseurl
    problems: list[str] = []
    id_cache: dict[Path, set[str]] = {}
    pages = 0
    for page in sorted(site.rglob("*.html")):
        rel = page.relative_to(site).as_posix()
        if rel.startswith(SKIP_SOURCE_DIRS):
            continue
        pages += 1
        text = page.read_text(encoding="utf-8", errors="ignore")
        for tag, url in references(text):
            if not url or url == "#" or url.startswith("javascript:"):
                continue
            if "{{" in url or "{%" in url:
                problems.append(f"{rel}: <{tag}> {url} is unrendered Liquid")
                continue
            hit = resolve(site, rel, url, baseurl, own_prefix)
            if hit is None:
                continue
            target, fragment = hit
            if not target.is_file():
                problems.append(
                    f"{rel}: <{tag}> {url} -> no file {target.relative_to(site) if target.is_relative_to(site) else target}"
                )
                continue
            if fragment and tag == "a" and target.suffix == ".html":
                if target not in id_cache:
                    id_cache[target] = element_ids(
                        target.read_text(encoding="utf-8", errors="ignore")
                    )
                if fragment not in id_cache[target]:
                    problems.append(
                        f"{rel}: <a> {url} -> no id '{fragment}' on "
                        f"{target.relative_to(site).as_posix()}"
                    )
    return pages, problems


# ── repository checks (need --repo) ─────────────────────────────────────────


def atlas_filenames(spec: object) -> list[str]:
    """Return every ``filename`` value in the atlas browser's data file."""
    found: list[str] = []
    if isinstance(spec, dict):
        for key, value in spec.items():
            if key == "filename" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(atlas_filenames(value))
    elif isinstance(spec, list):
        for value in spec:
            found.extend(atlas_filenames(value))
    return found


def check_atlases(site: Path, docs: Path) -> list[str]:
    """Every atlas file the atlas browser fetches is published under assets/atlas."""
    spec = json.loads((docs / "_data" / "atlases.json").read_text(encoding="utf-8"))
    names = atlas_filenames(spec)
    if not names:
        return ["docs/_data/atlases.json names no atlas file"]
    return [
        f"docs/_data/atlases.json: assets/atlas/{name} is not published"
        for name in names
        if not (site / "assets" / "atlas" / name).is_file()
    ]


def _iter_text_files(repo: Path, sources: Iterable[str]) -> Iterable[Path]:
    for source in sources:
        root = repo / source
        if root.is_file():
            yield root
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if any(part in _SKIP_REPO_DIRS for part in path.relative_to(repo).parts):
                continue
            if path.is_file() and path.stat().st_size < 5_000_000:
                yield path


def docs_urls(text: str) -> list[str]:
    """Return the literal docs-site URLs in *text* (template-built ones excluded)."""
    urls: list[str] = []
    for match in _DOCS_URL.finditer(text):
        nxt = text[match.end() : match.end() + 1]
        if nxt in ("$", "{"):
            continue
        urls.append(match.group(0).rstrip(".:?#,"))
    return urls


def check_repo_urls(
    site: Path, repo: Path, baseurl: str, site_url: str
) -> tuple[int, list[str]]:
    """Every absolute docs-site URL written in the repository resolves."""
    own_prefix = site_url + baseurl
    problems: list[str] = []
    count = 0
    for path in _iter_text_files(repo, REPO_URL_SOURCES):
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        rel = path.relative_to(repo).as_posix()
        for url in docs_urls(data.decode("utf-8", errors="ignore")):
            count += 1
            if not (url == own_prefix or url.startswith(own_prefix + "/")):
                problems.append(
                    f"{rel}: {url} is not under {own_prefix}/ (paths are case-sensitive)"
                )
                continue
            target, fragment = resolve(site, "index.html", url, baseurl, own_prefix)
            if not target.is_file():
                problems.append(f"{rel}: {url} -> nothing is published there")
            elif fragment and target.suffix == ".html":
                ids = element_ids(target.read_text(encoding="utf-8", errors="ignore"))
                if fragment not in ids:
                    problems.append(f"{rel}: {url} -> no id '{fragment}' on that page")
    return count, problems


def source_pages(docs: Path) -> dict[str, Path]:
    """Map each published Markdown page's URL path to its source file."""
    pages: dict[str, Path] = {}
    candidates = [docs / "index.md", docs / "dev" / "CHANGELOG.md"]
    candidates += sorted((docs / "wiki").glob("*.md"))
    candidates += sorted((docs / "releases").glob("*.md"))
    for path in candidates:
        if not path.is_file():
            continue
        meta, _body = split_front_matter(path.read_text(encoding="utf-8"))
        url = meta.get("permalink") or ("/" if path.name == "index.md" else "")
        if url:
            pages[url] = path
    return pages


def _built_file(site: Path, url: str) -> Path:
    return (
        site / url.lstrip("/") / "index.html"
        if url.endswith("/")
        else site / url.lstrip("/")
    )


def check_permalinks(site: Path, docs: Path) -> list[str]:
    """Every ``docs/wiki`` permalink is published (the plugin links to them)."""
    problems: list[str] = []
    for url, source in source_pages(docs).items():
        if source.parent.name == "wiki" and not _built_file(site, url).is_file():
            problems.append(
                f"{source.relative_to(docs.parent).as_posix()}: permalink {url} is not published"
            )
    return problems


def check_heading_parity(site: Path, docs: Path) -> tuple[int, list[str]]:
    """The ids computed from each page's Markdown equal the ids kramdown built."""
    problems: list[str] = []
    compared = 0
    for url, source in source_pages(docs).items():
        built = _built_file(site, url)
        if not built.is_file():
            continue
        compared += 1
        _meta, body = split_front_matter(source.read_text(encoding="utf-8"))
        computed = set(heading_ids(body)) | {
            m.group(1)
            for m in _HEADING_ID.finditer(
                "\n".join(_strip_code_blocks(body.splitlines()))
            )
        }
        emitted = set(
            _HEADING_ID.findall(
                _COMMENT.sub("", built.read_text(encoding="utf-8", errors="ignore"))
            )
        )
        if computed != emitted:
            rel = source.relative_to(docs.parent).as_posix()
            missing = sorted(emitted - computed)
            extra = sorted(computed - emitted)
            problems.append(
                f"{rel}: heading ids differ from the built page "
                f"(built only: {missing}; computed only: {extra})"
            )
    return compared, problems


# ── entry point ─────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    """Check the built site (and, with ``--repo``, the repository's docs URLs)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("site", type=Path, help="built site directory (_site)")
    parser.add_argument("--repo", type=Path, help="repository root for the URL scan")
    parser.add_argument("--baseurl", help="override docs/_config.yml baseurl")
    args = parser.parse_args(argv)

    site: Path = args.site
    if not site.is_dir() or not any(site.rglob("*.html")):
        print(f"error: no built site with HTML pages at {site}", file=sys.stderr)
        return 2
    docs = (args.repo / "docs") if args.repo else DOCS_DIR
    try:
        site_url, baseurl = site_address(
            (docs / "_config.yml").read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.baseurl is not None:
        baseurl = args.baseurl.rstrip("/")

    pages, problems = check_site(site, baseurl, site_url)
    summary = [f"{pages} pages"]
    if args.repo:
        try:
            problems += check_atlases(site, docs)
        except (OSError, ValueError) as error:
            print(f"error: cannot read the atlas list: {error}", file=sys.stderr)
            return 2
        problems += check_permalinks(site, docs)
        urls, url_problems = check_repo_urls(site, args.repo, baseurl, site_url)
        compared, parity = check_heading_parity(site, docs)
        problems += url_problems + parity
        # An empty scan is a broken guard, not a clean repository.
        if not urls:
            problems.append(f"no docs-site URL found under {args.repo}")
        if not compared:
            problems.append("no built page matched a Markdown source")
        summary += [f"{urls} repository docs URLs", f"{compared} pages' heading ids"]
    if problems:
        print(f"{len(problems)} broken link(s):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("All links resolve: " + ", ".join(summary) + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
